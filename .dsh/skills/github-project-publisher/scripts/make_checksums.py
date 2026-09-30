"""生成并校验 coreutils 兼容的 SHA256SUMS。

三条硬性要求，任何一条不满足都会让 Linux 侧的 ``sha256sum -c`` 直接失败：

1. **UTF-8 无 BOM**。BOM 会变成第一个文件路径的一部分，校验必然不匹配。
2. **LF 行尾**。CRLF 会让路径末尾多一个 ``\\r``。
3. **两个空格** 分隔摘要与路径（coreutils 的 text mode 格式），路径用正斜杠。

本脚本用 ``open(..., newline="\\n")`` 写入，不使用 shell 重定向——重定向在 Windows
上会重新引入 CRLF。

退出码：0 成功 / 全部匹配；1 校验失败（不匹配或缺失）；2 用法或执行错误。
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _common import (  # noqa: E402
    DEFAULT_EXCLUDED_DIRS,
    configure_stdio,
    path_matches_any,
    to_posix,
    walk_files,
    write_text_utf8,
)

SUPPORTED_ALGOS = ("sha256", "sha512")

# 默认排除：校验和文件自身与常见的审计产物，避免"自己校验自己"的循环。
DEFAULT_EXCLUDES = ("SHA256SUMS", "*.sha256", "*.sha256sum", ".github-upload-audit/*")


def hash_file(path: Path, algo: str, chunk_size: int = 1024 * 1024) -> str:
    """流式计算文件摘要，返回小写十六进制。"""
    digest = hashlib.new(algo)
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def expand_inputs(
    inputs: Sequence[Path],
    excludes: Sequence[str],
    relative_to: Optional[Path] = None,
) -> Tuple[List[Tuple[Path, str]], int]:
    """把文件/目录参数展开成 ``(绝对路径, 记录路径)`` 列表。

    记录路径用正斜杠；重复的记录路径只保留一次（先出现的优先）。
    """
    collected: List[Tuple[Path, str]] = []
    seen: set = set()
    skipped = 0
    for item in inputs:
        path = Path(item)
        if path.is_dir():
            candidates = walk_files(path, exclude_dirs=DEFAULT_EXCLUDED_DIRS)
        elif path.is_file():
            candidates = [path]
        else:
            skipped += 1
            continue
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except OSError:
                skipped += 1
                continue
            if relative_to is not None:
                try:
                    record = to_posix(resolved.relative_to(Path(relative_to).resolve()))
                except ValueError:
                    record = to_posix(resolved)
            elif path.is_dir():
                try:
                    record = to_posix(resolved.relative_to(path.resolve()))
                except ValueError:
                    record = resolved.name
            else:
                record = resolved.name
            if path_matches_any(record, excludes):
                skipped += 1
                continue
            if record in seen:
                continue
            seen.add(record)
            collected.append((resolved, record))
    collected.sort(key=lambda pair: pair[1])
    return collected, skipped


def render_sums(entries: Sequence[Tuple[str, str]], algo_label: str) -> str:
    """生成 coreutils 格式文本：``<摘要>  <路径>``（两个空格），每行 LF 结尾。"""
    lines: List[str] = []
    lines.append("# {0} checksums — 由 github-project-publisher/make_checksums.py 生成".format(algo_label))
    lines.append("# 格式与 coreutils `sha256sum -c` 兼容；请勿手工编辑（BOM/CRLF 会破坏校验）")
    for digest, record in entries:
        lines.append("{0}  {1}".format(digest, record))
    return "\n".join(lines) + "\n"


def build_sums(
    inputs: Sequence[Path],
    algo: str = "sha256",
    excludes: Sequence[str] = (),
    relative_to: Optional[Path] = None,
    algo_label: Optional[str] = None,
) -> Tuple[str, int, int]:
    """返回 ``(文本, 条目数, 跳过数)``。"""
    entries, skipped = expand_inputs(inputs, excludes, relative_to=relative_to)
    if not entries:
        return "", 0, skipped
    rows: List[Tuple[str, str]] = []
    label = algo_label or algo.upper()
    for absolute, record in entries:
        rows.append((hash_file(absolute, algo), record))
    rows.sort(key=lambda pair: pair[1])
    return render_sums(rows, label), len(rows), skipped


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------


class VerifyResult:
    """校验结果统计。"""

    def __init__(self) -> None:
        self.total = 0
        self.matched = 0
        self.mismatched: List[str] = []
        self.missing: List[str] = []
        self.malformed: List[str] = []

    @property
    def ok(self) -> bool:
        return not (self.mismatched or self.missing or self.malformed)

    def summary(self) -> str:
        return (
            "共 {0} 条：匹配 {1}，不匹配 {2}，缺失 {3}，格式错误 {4}".format(
                self.total,
                self.matched,
                len(self.mismatched),
                len(self.missing),
                len(self.malformed),
            )
        )


def parse_sums_text(text: str, default_algo: str = "sha256") -> Tuple[List[Tuple[str, str]], List[str]]:
    """解析校验和文件。返回 ``(条目列表, 格式错误行号说明)``。

    兼容两种格式：coreutils 的 ``<摘要>  <路径>``（两个空格，或一个空格加 ``*``）
    与 BSD 的 ``SHA256 (path) = <摘要>``。
    """
    entries: List[Tuple[str, str]] = []
    malformed: List[str] = []
    for index, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip("\ufeff").rstrip("\r\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("SHA256 (") or line.startswith("SHA512 ("):
            head, _, tail = line.partition(") = ")
            path = head.split("(", 1)[1]
            digest = tail.strip()
            if not _looks_like_digest(digest):
                malformed.append("第 {0} 行：BSD 格式但摘要不合法".format(index))
                continue
            entries.append((digest, path))
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2:
            # 单个空格 + '*' 也是合法写法
            star_parts = line.split(" *", 1)
            if len(star_parts) == 2:
                parts = star_parts
            else:
                malformed.append("第 {0} 行：缺少摘要与路径的分隔（需要两个空格）".format(index))
                continue
        digest, path = parts[0].strip(), parts[1]
        if not _looks_like_digest(digest):
            malformed.append("第 {0} 行：摘要不是十六进制串".format(index))
            continue
        if not path:
            malformed.append("第 {0} 行：路径为空".format(index))
            continue
        entries.append((digest, path))
    return entries, malformed


def _looks_like_digest(text: str) -> bool:
    if len(text) not in (64, 128):
        return False
    return all(char in "0123456789abcdefABCDEF" for char in text)


def verify_sums_file(
    sums_path: Path,
    base_dir: Optional[Path] = None,
    algo: Optional[str] = None,
) -> VerifyResult:
    """逐条校验。**只报告路径与判定**，绝不打印文件内容。"""
    result = VerifyResult()
    path = Path(sums_path)
    if not path.is_file():
        result.malformed.append("校验和文件不存在：{0}".format(to_posix(path)))
        return result
    raw = path.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        result.malformed.append("校验和文件带 UTF-8 BOM，Linux 侧 sha256sum -c 会失败")
    if b"\r\n" in raw:
        result.malformed.append("校验和文件包含 CRLF 行尾，Linux 侧 sha256sum -c 会失败")
    text = raw.decode("utf-8", errors="replace")
    entries, malformed = parse_sums_text(text)
    result.malformed.extend(malformed)
    base = Path(base_dir) if base_dir else path.parent
    for digest, record in entries:
        result.total += 1
        if record.startswith("/") or (len(record) > 1 and record[1] == ":"):
            # 记录了绝对路径：直接按当前平台解析，不做相对拼接。
            target = Path(record)
        else:
            # 记录路径统一是 POSIX 风格；按当前平台还原分隔符。
            target = Path(base).joinpath(*record.split("/"))
        if not target.is_file():
            result.missing.append(record)
            continue
        local_algo = algo or ("sha512" if len(digest) == 128 else "sha256")
        try:
            actual = hash_file(target, local_algo)
        except OSError:
            result.missing.append(record)
            continue
        if actual.lower() == digest.lower():
            result.matched += 1
        else:
            result.mismatched.append(record)
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="make_checksums.py",
        description=(
            "生成或校验 coreutils 兼容的 SHA256SUMS。"
            "输出为 UTF-8 无 BOM、LF 行尾、摘要与路径之间两个空格、路径用正斜杠。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "退出码：0 成功 / 全部匹配；1 校验失败；2 用法或执行错误。\n"
            "示例：python .\\make_checksums.py dist\\app.zip --out SHA256SUMS\n"
            "      python .\\make_checksums.py --verify SHA256SUMS"
        ),
    )
    parser.add_argument("paths", nargs="*", metavar="PATH", help="要计算摘要的文件或目录（目录会被递归展开）")
    parser.add_argument("--out", metavar="PATH", default="SHA256SUMS", help="输出文件，默认 SHA256SUMS")
    parser.add_argument(
        "--algo",
        choices=SUPPORTED_ALGOS,
        default="sha256",
        help="摘要算法，仅支持 sha256（默认）或 sha512",
    )
    parser.add_argument(
        "--relative-to",
        metavar="DIR",
        default=None,
        help="记录路径相对于该目录（默认：目录参数相对于自身，文件参数只记文件名）",
    )
    parser.add_argument(
        "--exclude",
        metavar="GLOB",
        action="append",
        default=[],
        help="排除匹配该 glob 的路径（可重复）",
    )
    parser.add_argument(
        "--algo-label",
        metavar="LABEL",
        default=None,
        help="注释行中的算法标签（仅影响注释，默认取算法名大写）",
    )
    parser.add_argument(
        "--verify",
        metavar="PATH",
        default=None,
        help="校验模式：读取该校验和文件并逐条校验，不写入任何文件",
    )
    parser.add_argument(
        "--base-dir",
        metavar="DIR",
        default=None,
        help="校验模式下解析记录路径的基准目录（默认校验和文件所在目录）",
    )
    parser.add_argument("--quiet", action="store_true", help="只输出判定行")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.verify:
            return _run_verify(args)
        return _run_generate(args)
    except Exception as exc:
        print("执行错误：{0}: {1}".format(type(exc).__name__, exc), file=sys.stderr)
        return 2


def _run_verify(args) -> int:
    result = verify_sums_file(
        Path(args.verify),
        base_dir=Path(args.base_dir) if args.base_dir else None,
        algo=args.algo if args.algo in SUPPORTED_ALGOS else None,
    )
    print("校验和文件：{0}".format(to_posix(Path(args.verify))))
    print(result.summary())
    for record in result.malformed:
        print("  结构问题：{0}".format(record))
    for record in result.mismatched:
        print("  不匹配：{0}".format(record))
    for record in result.missing:
        print("  缺失：{0}".format(record))
    print("判定：{0}".format("全部匹配" if result.ok else "未通过"))
    return 0 if result.ok else 1


def _run_generate(args) -> int:
    inputs = [Path(item) for item in args.paths]
    if not inputs:
        print("用法错误：至少需要一个文件或目录参数（或用 --verify 校验）", file=sys.stderr)
        return 2
    missing = [item for item in inputs if not item.exists()]
    if missing:
        print(
            "用法错误：路径不存在 — {0}".format(
                "、".join(to_posix(item) for item in missing)
            ),
            file=sys.stderr,
        )
        return 2

    excludes = list(DEFAULT_EXCLUDES) + list(args.exclude)
    if args.out:
        excludes.append(Path(args.out).name)

    text, count, skipped = build_sums(
        inputs,
        algo=args.algo,
        excludes=excludes,
        relative_to=Path(args.relative_to) if args.relative_to else None,
        algo_label=args.algo_label,
    )
    if count == 0:
        print("用法错误：没有可计算的文件（全部被排除或路径为空）", file=sys.stderr)
        return 2

    out_path = Path(args.out)
    write_text_utf8(out_path, text)
    if not args.quiet:
        print("已写入：{0}".format(to_posix(out_path)))
        print("算法：{0}；条目：{1}；排除/跳过：{2}".format(args.algo, count, skipped))
        print("编码：UTF-8 无 BOM；行尾：LF；格式：<摘要>  <路径>（两个空格）")
        preview = text.splitlines()
        for line in preview[:8]:
            print("  " + line)
        if len(preview) > 8:
            print("  …… 其余 {0} 行见文件".format(len(preview) - 8))
    return 0


if __name__ == "__main__":
    sys.exit(main())
