"""聚合审计：把静态检查、密钥扫描、身份核验、校验和检查合成一份报告。

设计要点
--------
* **降级而非崩溃**：三个子模块通过 ``import`` 复用，任何一个导入失败只记一条
  警告并继续，剩余检查照常执行。审计工具本身失败比"少检查一项"更糟。
* **报告即披露面**：报告里只写脱敏后的证据（CWE-532）。所有豁免、降级、
  未覆盖项都必须留痕——每一步刻意的操作都要可追溯。
* **显式声明未覆盖范围**：报告固定包含"本次审计未能覆盖"一节，避免读者把
  "没报错"误读为"没问题"。

退出码：0 无 BLOCKER；1 存在 BLOCKER；2 执行错误。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _common import (  # noqa: E402
    AUDIT_DIRNAME,
    CHECKSUM_FILENAME,
    RULE_SEVERITY,
    RULE_TITLES,
    SEVERITIES,
    SEVERITY_BLOCKER,
    SEVERITY_INFO,
    SEVERITY_MAJOR,
    SEVERITY_MINOR,
    Finding,
    configure_stdio,
    count_by_severity,
    make_finding,
    print_banner,
    read_text_utf8,
    relative_posix,
    repo_name_from_remote,
    resolve_repo_root,
    run_command,
    sort_findings,
    to_posix,
    tool_version,
    utc_timestamp,
    walk_files,
    write_text_utf8,
)

# ---------------------------------------------------------------------------
# 子模块导入（可降级）
# ---------------------------------------------------------------------------

_MODULE_STATUS: Dict[str, str] = {}

try:
    import scan_secrets as _scan_secrets  # type: ignore

    _MODULE_STATUS["scan_secrets"] = "ok"
except Exception as exc:  # pragma: no cover - 仅在模块缺失时触发
    _scan_secrets = None  # type: ignore
    _MODULE_STATUS["scan_secrets"] = "{0}: {1}".format(type(exc).__name__, exc)

try:
    import check_identity as _check_identity  # type: ignore

    _MODULE_STATUS["check_identity"] = "ok"
except Exception as exc:  # pragma: no cover
    _check_identity = None  # type: ignore
    _MODULE_STATUS["check_identity"] = "{0}: {1}".format(type(exc).__name__, exc)

try:
    import make_checksums as _make_checksums  # type: ignore

    _MODULE_STATUS["make_checksums"] = "ok"
except Exception as exc:  # pragma: no cover
    _make_checksums = None  # type: ignore
    _MODULE_STATUS["make_checksums"] = "{0}: {1}".format(type(exc).__name__, exc)

MODULE_STATUS = _MODULE_STATUS

REPORT_PREFIX = "report-"

# 发布产物候选：位于这些目录，或根目录下的归档/安装包。
ARTIFACT_DIRS = ("dist", "build", "artifacts", "release", "out")
ARTIFACT_SUFFIXES = (
    ".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar",
    ".whl", ".exe", ".msi", ".dmg", ".deb", ".rpm", ".jar", ".apk",
    ".sha256", ".sig", ".asc",
)

DOC_REQUIREMENTS = (
    ("META-001", "LICENSE", "LICENSE", SEVERITY_BLOCKER, "缺少 LICENSE：仓库没有明确授权，他人默认无权使用"),
    ("META-003", "README", "README", SEVERITY_MINOR, "缺少 README：访客无法判断项目用途与用法"),
    ("META-004", ".gitignore", ".gitignore", SEVERITY_MINOR, "缺少 .gitignore：构建产物与本地配置容易误入提交"),
    (
        "META-005",
        ".gitattributes",
        ".gitattributes",
        SEVERITY_MAJOR,
        "缺少 .gitattributes：Windows 提交的 CRLF 会进入仓库，Linux/macOS 使用者会看到整文件 diff",
    ),
    ("DOC-001", "CHANGELOG", "CHANGELOG", SEVERITY_MINOR, "缺少 CHANGELOG：使用者无法了解版本间变化"),
    ("DOC-002", "SECURITY.md", "SECURITY.md", SEVERITY_MINOR, "缺少 SECURITY.md：安全问题缺少报告渠道"),
    ("DOC-003", "CONTRIBUTING.md", "CONTRIBUTING.md", SEVERITY_MINOR, "缺少 CONTRIBUTING.md：贡献流程未说明"),
)

README_CANDIDATES = ("README.md", "README.rst", "README.txt", "README", "readme.md")
CHANGELOG_CANDIDATES = ("CHANGELOG.md", "CHANGELOG.rst", "CHANGELOG.txt", "CHANGELOG", "CHANGES.md")
LICENSE_CANDIDATES = ("LICENSE", "LICENSE.md", "LICENSE.txt", "LICENCE", "COPYING")

# 许可证名称归一化：把各种写法收敛到 SPDX 标识。
LICENSE_ALIASES: Dict[str, Tuple[str, ...]] = {
    "MIT": ("mit license", "the mit license", "mit"),
    "Apache-2.0": ("apache license 2.0", "apache-2.0", "apache 2.0", "apache software license"),
    "GPL-3.0": ("gnu general public license v3", "gpl-3.0", "gplv3"),
    "GPL-2.0": ("gnu general public license v2", "gpl-2.0", "gplv2"),
    "LGPL-3.0": ("gnu lesser general public license v3", "lgpl-3.0"),
    "BSD-3-Clause": ("bsd 3-clause", "bsd-3-clause", "three-clause bsd"),
    "BSD-2-Clause": ("bsd 2-clause", "bsd-2-clause", "two-clause bsd"),
    "MPL-2.0": ("mozilla public license 2.0", "mpl-2.0"),
    "AGPL-3.0": ("gnu affero general public license", "agpl-3.0"),
    "Unlicense": ("the unlicense", "unlicense"),
    "ISC": ("isc license", "isc"),
    "CC0-1.0": ("cc0 1.0", "cc0-1.0"),
    "EPL-2.0": ("eclipse public license 2.0", "epl-2.0"),
}


# ---------------------------------------------------------------------------
# 静态检查
# ---------------------------------------------------------------------------


def _first_existing(repo_root: Path, candidates: Sequence[str]) -> Optional[Path]:
    """按候选名（大小写不敏感）寻找仓库根下的文件。"""
    lowered = {name.lower(): name for name in candidates}
    try:
        entries = {item.name.lower(): item for item in repo_root.iterdir()}
    except OSError:
        return None
    for key, original in lowered.items():
        if key in entries:
            return entries[key]
        # README.md / README.rst 这类前缀候选
        for name, path in entries.items():
            if name.startswith(key.split(".")[0].lower()) and path.is_file():
                if original.startswith(key.split(".")[0]):
                    return path
    return None


def check_file_presence(repo_root: Path, findings: List[Finding]) -> Dict[str, Optional[Path]]:
    """META-001/003/004/005、DOC-001/002/003：必要的仓库文件是否存在。"""
    found: Dict[str, Optional[Path]] = {}
    found["LICENSE"] = _first_existing(repo_root, LICENSE_CANDIDATES)
    found["README"] = _first_existing(repo_root, README_CANDIDATES)
    found["CHANGELOG"] = _first_existing(repo_root, CHANGELOG_CANDIDATES)
    found[".gitignore"] = _first_existing(repo_root, (".gitignore",))
    found[".gitattributes"] = _first_existing(repo_root, (".gitattributes",))
    found["SECURITY.md"] = _first_existing(repo_root, ("SECURITY.md", "SECURITY.rst"))
    found["CONTRIBUTING.md"] = _first_existing(repo_root, ("CONTRIBUTING.md", "CONTRIBUTING.rst"))

    for rule_id, key, _label, severity, message in DOC_REQUIREMENTS:
        if found.get(key) is None:
            findings.append(
                make_finding(
                    rule_id,
                    ".",
                    0,
                    message,
                    severity=severity,
                    engine="audit_repo",
                )
            )
    return found


def normalize_license(text: str) -> Optional[str]:
    """把许可证文本归一化为 SPDX 标识；无法识别返回 None。"""
    if not text:
        return None
    lowered = text.lower()
    best: Optional[Tuple[int, str]] = None
    for spdx, aliases in LICENSE_ALIASES.items():
        for alias in aliases:
            if alias in lowered:
                if best is None or len(alias) > best[0]:
                    best = (len(alias), spdx)
    return best[1] if best else None


def _declared_license_from_text(text: str, manifest: str) -> Optional[str]:
    """从清单文件里提取声明的许可证。"""
    if manifest.endswith(".json"):
        try:
            payload = json.loads(text)
        except ValueError:
            return None
        if isinstance(payload, dict):
            value = payload.get("license")
            if isinstance(value, str):
                return value
            if isinstance(value, dict) and isinstance(value.get("type"), str):
                return value["type"]
            for key in ("license", "licenses"):
                if isinstance(payload.get(key), str):
                    return payload[key]
        return None
    if manifest.endswith((".toml", ".cfg", ".ini")):
        match = re.search(r'(?im)^\s*license\s*=\s*["\']([^"\']+)["\']', text)
        if match:
            return match.group(1)
        match = re.search(r"(?im)^\s*License\s*::\s*([^\r\n]+)", text)
        if match:
            return match.group(1).strip()
        return None
    match = re.search(r'(?im)^\s*license\s*[:=]\s*["\']?([^"\'\r\n]+)', text)
    if match:
        return match.group(1).strip()
    return None


MANIFESTS = (
    "package.json",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "Cargo.toml",
    "composer.json",
    "pom.xml",
    "Gemfile",
    "*.gemspec",
)


def check_license_consistency(
    repo_root: Path, license_path: Optional[Path], findings: List[Finding]
) -> Tuple[Optional[str], Optional[str]]:
    """META-002：清单声明的许可证与 LICENSE 文件是否一致。"""
    declared: Optional[str] = None
    declared_in = ""
    for name in MANIFESTS:
        candidates = sorted(repo_root.glob(name)) if "*" in name else [repo_root / name]
        for candidate in candidates:
            if not candidate.is_file():
                continue
            text = read_text_utf8(candidate)
            if text is None:
                continue
            value = _declared_license_from_text(text, candidate.name)
            if value:
                declared = value
                declared_in = relative_posix(candidate, repo_root)
                break
        if declared:
            break

    file_license: Optional[str] = None
    if license_path is not None:
        text = read_text_utf8(license_path, max_bytes=256 * 1024)
        if text:
            file_license = normalize_license(text)

    if declared and file_license:
        declared_norm = normalize_license(declared)
        if declared_norm and declared_norm != file_license:
            findings.append(
                make_finding(
                    "META-002",
                    declared_in,
                    0,
                    "清单声明的许可证（{0}）与 LICENSE 文件（{1}）不一致".format(
                        declared, file_license
                    ),
                    severity=SEVERITY_BLOCKER,
                    engine="audit_repo",
                )
            )
        elif declared_norm is None:
            findings.append(
                make_finding(
                    "META-002",
                    declared_in,
                    0,
                    "清单声明的许可证无法识别，无法与 LICENSE 文件比对（声明值：{0}）".format(
                        declared
                    ),
                    severity=SEVERITY_INFO,
                    engine="audit_repo",
                )
            )
    return declared, file_license


def check_repo_name(repo_root: Path, findings: List[Finding]) -> Tuple[str, str]:
    """META-006：仓库名必须是纯 ASCII。"""
    name, source = repo_name_from_remote(repo_root)
    if not name:
        return name, source
    if not name.isascii():
        findings.append(
            make_finding(
                "META-006",
                ".",
                0,
                "仓库名不是纯 ASCII（来源：{0}）：URL 会被百分号编码，"
                "shell 脚本与 CI 中直接引用容易出错".format(source),
                severity=SEVERITY_MAJOR,
                engine="audit_repo",
            )
        )
    return name, source


# 逐条列出的上限。超过之后改为汇总一条，避免把报告刷成文件清单。
GIT005_MAX_LISTED = 10


def check_tracked_ignored(
    repo_root: Path, findings: List[Finding]
) -> Tuple[List[str], str]:
    """GIT-005：找出「已被跟踪」且「又匹配 .gitignore」的文件。

    ``.gitignore`` 只影响**尚未被跟踪**的文件；对已经进入版本控制的文件，
    它一个字的作用都没有。最常见的错误是先把 ``.env`` 提交了，想起来不对，
    再往 ``.gitignore`` 里写一行，于是以为安全了——而它照样会随每次提交更新。

    这种「以为被保护了，其实没有」比根本不写 ``.gitignore`` 更危险：
    不写至少还会警惕，写了就没人再看第二眼。

    探测方式就是 git 原生的交集查询：

        git ls-files --cached --ignored --exclude-standard

    返回 ``(命中的路径列表, 说明)``；说明非空表示本次未能完成检查，
    调用方应把它记入「未能覆盖」而不是当作通过。
    """
    code, out, err = run_command(
        ["git", "ls-files", "--cached", "--ignored", "--exclude-standard"],
        cwd=repo_root,
        timeout=120,
    )
    if code != 0:
        return [], "git ls-files 执行失败：{0}".format(
            (err or "").strip() or "退出码 {0}".format(code)
        )

    paths = [line.strip() for line in out.splitlines() if line.strip()]
    if not paths:
        return [], ""

    listed = paths[:GIT005_MAX_LISTED]
    for rel in listed:
        posix = to_posix(rel)
        findings.append(
            make_finding(
                "GIT-005",
                posix,
                0,
                "该文件已被 git 跟踪，同时又匹配 .gitignore 中的规则——"
                "忽略规则对它完全无效，它仍会随每次提交更新。"
                "修复：git rm --cached {0}（保留本地文件），再提交".format(posix),
                severity=SEVERITY_MAJOR,
                engine="audit_repo",
            )
        )

    if len(paths) > len(listed):
        rest = [to_posix(item) for item in paths[len(listed):]]
        preview = "、".join(rest[:10])
        if len(rest) > 10:
            preview += " 等"
        findings.append(
            make_finding(
                "GIT-005",
                ".",
                0,
                "另有 {0} 个文件同样「已跟踪且被忽略」，未逐条列出：{1}。"
                "完整清单可用 git ls-files --cached --ignored --exclude-standard 获取".format(
                    len(rest), preview
                ),
                severity=SEVERITY_MAJOR,
                engine="audit_repo",
            )
        )

    return paths, ""


# GitHub 对大文件的阈值：超过警告线即永久影响每一次克隆，
# 超过硬上限则推送会被直接拒收。
LARGE_FILE_WARN_BYTES = 50 * 1024 * 1024
LARGE_FILE_LIMIT_BYTES = 100 * 1024 * 1024
GIT004_MAX_LISTED = 10


def _human_size(num_bytes: int) -> str:
    """把字节数写成便于阅读的形式。"""
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024.0 or unit == "GB":
            if unit == "B":
                return "{0} B".format(num_bytes)
            return "{0:.2f} {1}".format(value, unit)
        value /= 1024.0
    return "{0:.2f} GB".format(value)


def check_large_files(
    repo_root: Path,
    findings: List[Finding],
    warn_bytes: int = LARGE_FILE_WARN_BYTES,
    limit_bytes: int = LARGE_FILE_LIMIT_BYTES,
) -> Tuple[List[Tuple[int, str]], str]:
    """GIT-004：历史中的超大文件。

    GitHub 的阈值：超过 50 MB 推送时警告，超过 100 MB **直接拒收**。

    关键在于「从 HEAD 删掉」不等于「消失了」。对象一旦进入历史就永远在那里，
    每次 clone 都要下载；要真正移除必须改写历史，而那会改变所有相关提交的 SHA。
    因此这条检查的价值在于**推送之前**发现——一旦被拒，代价就变成了改写历史。

    实现用一次批量查询，而不是逐个对象起进程：

        git rev-list --objects --all
          | git cat-file --batch-check='%(objecttype) %(objectsize) %(rest)'

    返回 ``(按体积降序的 (字节数, 路径) 列表, 说明)``；说明非空表示未能完成，
    调用方应记入「未能覆盖」而不是当作通过。
    """
    code, out, err = run_command(
        ["git", "rev-list", "--objects", "--all"], cwd=repo_root, timeout=300
    )
    if code != 0:
        return [], "git rev-list 执行失败：{0}".format(
            (err or "").strip() or "退出码 {0}".format(code)
        )
    if not out.strip():
        return [], ""          # 尚无提交，谈不上历史大文件

    code, listing, err = run_command(
        ["git", "cat-file", "--batch-check=%(objecttype) %(objectsize) %(rest)"],
        cwd=repo_root,
        timeout=600,
        stdin_text=out,
    )
    if code != 0:
        return [], "git cat-file 执行失败：{0}".format(
            (err or "").strip() or "退出码 {0}".format(code)
        )

    entries: List[Tuple[int, str]] = []
    for line in listing.splitlines():
        parts = line.split(" ", 2)
        if len(parts) != 3 or parts[0] != "blob":
            continue
        try:
            size = int(parts[1])
        except ValueError:
            continue
        if size < warn_bytes:
            continue
        entries.append((size, parts[2].strip() or "(无路径)"))

    entries.sort(key=lambda item: (-item[0], item[1]))
    if not entries:
        return [], ""

    # 区分「还在当前版本里」与「只在历史里」——两者的处置方式完全不同：
    # 前者可以 git rm --cached 止血，后者写 .gitignore 毫无意义。
    code, tracked_raw, _ = run_command(
        ["git", "ls-files", "--cached"], cwd=repo_root, timeout=120
    )
    tracked = set()
    if code == 0:
        tracked = {line.strip() for line in tracked_raw.splitlines() if line.strip()}

    for size, rel in entries[:GIT004_MAX_LISTED]:
        if size > limit_bytes:
            consequence = (
                "超过硬上限 {0}——GitHub 会直接拒收推送，"
                "在改写历史之前无法发布".format(_human_size(limit_bytes))
            )
            severity = SEVERITY_MAJOR
        else:
            consequence = (
                "超过警告线 {0}——推送时会被警告，且仓库体积永久变大，"
                "每一次 clone 都要下载它".format(_human_size(warn_bytes))
            )
            severity = SEVERITY_MINOR
        if rel in tracked:
            status_note = (
                "该路径**当前仍被跟踪**：git rm --cached 只能让它不再随新提交进入，"
                "**历史里的副本原封不动，体积不会变小**"
            )
        else:
            status_note = (
                "该路径在当前版本中**已不存在**，只留在历史里——"
                "此时写 .gitignore 没有任何意义（没有可忽略的对象）"
            )
        findings.append(
            make_finding(
                "GIT-004",
                to_posix(rel),
                0,
                "历史中的超大文件 {0}：{1}。{2}。"
                "要真正移除必须改写历史".format(
                    _human_size(size), consequence, status_note
                ),
                severity=severity,
                engine="audit_repo",
            )
        )

    if len(entries) > GIT004_MAX_LISTED:
        rest = entries[GIT004_MAX_LISTED:]
        findings.append(
            make_finding(
                "GIT-004",
                ".",
                0,
                "另有 {0} 个超过 {1} 的历史对象未逐条列出，最大者 {2}（{3}）。"
                "完整清单可用 git rev-list --objects --all 配合 "
                "git cat-file --batch-check 获取".format(
                    len(rest), _human_size(warn_bytes), _human_size(rest[0][0]),
                    to_posix(rest[0][1])
                ),
                severity=SEVERITY_MINOR,
                engine="audit_repo",
            )
        )

    return entries, ""


def _load_checksum_entries(repo_root: Path) -> Dict[str, str]:
    """读取 SHA256SUMS（含 SHA512SUMS）里的 路径 -> 摘要 映射。"""
    entries: Dict[str, str] = {}
    if _make_checksums is not None:
        for candidate in (
            repo_root / CHECKSUM_FILENAME,
            repo_root / "SHA512SUMS",
            repo_root / "checksums.txt",
        ):
            if not candidate.is_file():
                continue
            text = read_text_utf8(candidate, max_bytes=8 * 1024 * 1024) or ""
            parsed, _malformed = _make_checksums.parse_sums_text(text)
            for digest, record in parsed:
                entries[record] = digest
        return entries
    # 降级：手工解析（避免因模块缺失而完全放弃该项检查）
    for candidate in (repo_root / CHECKSUM_FILENAME, repo_root / "SHA512SUMS"):
        text = read_text_utf8(candidate, max_bytes=8 * 1024 * 1024)
        if not text:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("  ", 1)
            if len(parts) == 2:
                entries[parts[1]] = parts[0]
    return entries


def check_release_artifacts(repo_root: Path, findings: List[Finding]) -> Dict[str, object]:
    """REL-001：发布产物是否有对应的 SHA256 记录。"""
    artifacts: List[str] = []
    for path in walk_files(repo_root):
        rel = relative_posix(path, repo_root)
        lowered = rel.lower()
        if lowered.startswith(AUDIT_DIRNAME + "/"):
            continue
        parent = lowered.rsplit("/", 1)[0] if "/" in lowered else ""
        if parent in ARTIFACT_DIRS or any(
            part in ARTIFACT_DIRS for part in lowered.split("/")[:-1]
        ):
            artifacts.append(rel)
        elif "/" not in lowered and lowered.endswith(ARTIFACT_SUFFIXES):
            artifacts.append(rel)

    entries = _load_checksum_entries(repo_root)
    has_sums = bool(entries)
    unchecked: List[str] = []
    for rel in artifacts:
        if rel in entries:
            continue
        if "/" in rel and entries:
            # 记录路径可能相对于产物目录（dist/app.zip 记为 app.zip）
            basename = rel.rsplit("/", 1)[1]
            if basename in entries:
                continue
        unchecked.append(rel)

    if unchecked:
        findings.append(
            make_finding(
                "REL-001",
                unchecked[0],
                0,
                "{0} 个发布产物没有对应的摘要记录{1}：{2}".format(
                    len(unchecked),
                    "" if has_sums else "（未找到 {0}）".format(CHECKSUM_FILENAME),
                    "、".join(unchecked[:8]) + ("……" if len(unchecked) > 8 else ""),
                ),
                severity=SEVERITY_INFO,
                engine="audit_repo",
            )
        )
    return {
        "artifact_count": len(artifacts),
        "checksum_entries": len(entries),
        "unchecked": unchecked,
    }


def _parse_report_timestamp(name: str) -> str:
    """从 report-<UTC 时间戳>.md 中取出时间戳部分。"""
    stem = name[len(REPORT_PREFIX):]
    for suffix in (".md", ".json"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
    return stem


def check_stale_reports(repo_root: Path, findings: List[Finding]) -> Dict[str, object]:
    """ID-001：仓库里存在与本次结论矛盾的陈旧审计报告。

    审计报告本身也是披露面，且旧的结论会与新结论冲突。这里只在
    "旧报告有 BLOCKER 而本次没有" 这种明确矛盾时提示，不做主观判断。
    """
    audit_dir = repo_root / AUDIT_DIRNAME
    inspected: List[str] = []
    stale: List[Dict[str, object]] = []
    if not audit_dir.is_dir():
        return {"inspected": inspected, "stale": stale}
    try:
        candidates = sorted(audit_dir.glob(REPORT_PREFIX + "*.json"))
    except OSError:
        return {"inspected": inspected, "stale": stale}
    for candidate in candidates:
        text = read_text_utf8(candidate, max_bytes=16 * 1024 * 1024)
        if not text:
            continue
        try:
            payload = json.loads(text)
        except ValueError:
            continue
        if not isinstance(payload, dict):
            continue
        counts = payload.get("counts") or {}
        if not isinstance(counts, dict):
            continue
        inspected.append(candidate.name)
        try:
            blockers = int(counts.get(SEVERITY_BLOCKER, 0) or 0)
        except (TypeError, ValueError):
            blockers = 0
        declared_exit = payload.get("exit_code")
        if blockers > 0 or declared_exit == 1:
            stale.append(
                {
                    "report": candidate.name,
                    "stale_timestamp": _parse_report_timestamp(candidate.name),
                    "blockers": blockers,
                    "declared_exit_code": declared_exit,
                }
            )
    if stale:
        newest = sorted(item["stale_timestamp"] for item in stale)[-1]
        findings.append(
            make_finding(
                "ID-001",
                to_posix(audit_dir.name) + "/",
                0,
                "存在 {0} 份结论为「未通过」的审计报告，与本次运行可能矛盾"
                "（最新一份时间戳 {1}）；报告目录应列入 .gitignore，"
                "上传前请确认它不会随仓库分发".format(len(stale), newest),
                severity=SEVERITY_INFO,
                engine="audit_repo",
            )
        )
    return {"inspected": inspected, "stale": stale}


# ---------------------------------------------------------------------------
# 聚合
# ---------------------------------------------------------------------------


class AuditResult:
    """一次聚合审计的完整结果。"""

    def __init__(self) -> None:
        self.repo_root: Path = Path.cwd()
        self.generated_at: str = utc_timestamp()
        self.timestamp_compact: str = utc_timestamp(compact=True)
        self.findings: List[Finding] = []
        self.placeholders: List[Dict[str, object]] = []
        self.self_hits: List[Dict[str, object]] = []
        self.exemptions: List[Dict[str, object]] = []
        self.invalid_allow_entries: List[Dict[str, object]] = []
        self.engines: List[str] = []
        self.surfaces: List[str] = []
        self.tool_versions: List[str] = []
        self.warnings: List[str] = []
        self.limitations: List[str] = []
        self.identity: Dict[str, object] = {}
        self.artifacts: Dict[str, object] = {}
        self.repo_name: str = ""
        self.repo_name_source: str = ""
        self.declared_license: Optional[str] = None
        self.file_license: Optional[str] = None
        self.scan_stats: Dict[str, object] = {}
        self.checksum_summary: Dict[str, object] = {}
        self.markdown_path: Optional[Path] = None
        self.json_path: Optional[Path] = None

    @property
    def blockers(self) -> List[Finding]:
        return [item for item in self.findings if item.severity == SEVERITY_BLOCKER]

    def exit_code(self) -> int:
        return 1 if self.blockers else 0


def _tool_versions() -> List[str]:
    versions = [
        "python {0}".format(sys.version.split()[0]),
        tool_version("git"),
        tool_version("gh"),
        tool_version("gitleaks", ("version",)),
        tool_version("trufflehog"),
    ]
    return versions


def run_audit(repo_root: Path, options) -> AuditResult:
    """执行全部检查。任何子检查失败都降级为警告，不中断整体。"""
    result = AuditResult()
    result.repo_root = Path(repo_root)
    result.tool_versions = _tool_versions()

    # --- 静态检查 ---
    present = check_file_presence(result.repo_root, result.findings)
    result.declared_license, result.file_license = check_license_consistency(
        result.repo_root, present.get("LICENSE"), result.findings
    )
    result.repo_name, result.repo_name_source = check_repo_name(
        result.repo_root, result.findings
    )
    tracked_ignored, git005_note = check_tracked_ignored(
        result.repo_root, result.findings
    )
    result.scan_stats["tracked_ignored"] = len(tracked_ignored)
    if git005_note:
        result.warnings.append("GIT-005 未完成：{0}".format(git005_note))
        result.limitations.append(
            "「已跟踪且被忽略」的文件检查（GIT-005）未完成：{0}".format(git005_note)
        )

    if getattr(options, "no_large_files", False):
        result.limitations.append(
            "已通过 --no-large-files 跳过历史大文件检查（GIT-004）："
            "超过 100 MB 的历史对象会让 GitHub 直接拒收推送，"
            "跳过此项意味着该风险未经检查"
        )
    else:
        large_files, git004_note = check_large_files(result.repo_root, result.findings)
        result.scan_stats["large_files"] = len(large_files)
        if git004_note:
            result.warnings.append("GIT-004 未完成：{0}".format(git004_note))
            result.limitations.append(
                "历史大文件检查（GIT-004）未完成：{0}".format(git004_note)
            )

    result.artifacts = check_release_artifacts(result.repo_root, result.findings)
    stale = check_stale_reports(result.repo_root, result.findings)
    result.scan_stats["stale_reports"] = stale

    if not (result.repo_root / ".github-upload-audit").is_dir():
        result.limitations.append(
            "未找到 {0}/ 目录：本次没有可对照的历史审计报告，"
            "ID-001（陈旧报告矛盾）实际上未被触发过".format(AUDIT_DIRNAME)
        )

    # --- 密钥扫描 ---
    if _scan_secrets is None:
        result.warnings.append(
            "scan_secrets 模块不可用（{0}），本次未执行密钥扫描——"
            "这是最关键的检查项，报告不能视为通过".format(MODULE_STATUS["scan_secrets"])
        )
        result.limitations.append("密钥与个人信息扫描未执行（模块导入失败）")
    else:
        try:
            scan_result, surface_list = _run_secret_scan(result, options)
            result.findings.extend(scan_result.findings)
            result.placeholders = scan_result.placeholders
            result.self_hits = scan_result.self_hits
            result.exemptions = scan_result.exemptions
            result.invalid_allow_entries = scan_result.invalid_allow_entries
            result.engines = scan_result.engines
            result.surfaces = surface_list
            result.scan_stats["files_scanned"] = scan_result.files_scanned
            result.scan_stats["files_skipped"] = scan_result.files_skipped
            for note in scan_result.external_notes:
                result.warnings.append(note)
            if _scan_secrets.ENGINE_BUILTIN in scan_result.engines and len(
                scan_result.engines
            ) == 1:
                result.limitations.append(
                    "未安装 gitleaks / trufflehog，本次仅使用内置规则集（SEC-001..SEC-009）："
                    "覆盖范围弱于外部引擎，判定为「通过」的置信度相应下降"
                )
        except Exception as exc:
            result.warnings.append(
                "密钥扫描执行失败（{0}: {1}），该项检查未完成".format(
                    type(exc).__name__, exc
                )
            )
            result.limitations.append("密钥与个人信息扫描未完成")

    # --- 身份核验 ---
    if _check_identity is None:
        result.warnings.append(
            "check_identity 模块不可用（{0}），GIT-001 未核验".format(
                MODULE_STATUS["check_identity"]
            )
        )
        result.limitations.append("提交身份核验（GIT-001）未执行")
    else:
        try:
            identity = _check_identity.collect_identity(result.repo_root)
            result.identity = identity
            if identity.get("error"):
                result.warnings.append(
                    "git 历史读取失败：{0}".format(identity["error"])
                )
                result.limitations.append("历史提交身份未能完整核验")
            if identity.get("verdict") != "pass":
                result.findings.append(
                    make_finding(
                        "GIT-001",
                        "(git config / git log)",
                        0,
                        "author 或 committer 邮箱不是 GitHub 隐私邮箱："
                        "命中 {0} 条，涉及 {1} 个不同地址（地址值不输出）".format(
                            identity.get("non_noreply_entries"),
                            identity.get("distinct_non_noreply"),
                        ),
                        severity=SEVERITY_BLOCKER,
                        engine="check_identity",
                    )
                )
        except Exception as exc:
            result.warnings.append(
                "身份核验执行失败（{0}: {1}）".format(type(exc).__name__, exc)
            )
            result.limitations.append("提交身份核验（GIT-001）未完成")

    # --- 校验和检查（只读，不生成） ---
    if _make_checksums is None:
        result.warnings.append(
            "make_checksums 模块不可用（{0}），校验和结构检查降级为手工解析".format(
                MODULE_STATUS["make_checksums"]
            )
        )
    sums_path = result.repo_root / CHECKSUM_FILENAME
    if sums_path.is_file():
        verify = None
        if _make_checksums is not None:
            try:
                verify = _make_checksums.verify_sums_file(sums_path)
            except Exception as exc:
                result.warnings.append(
                    "校验和文件读取失败（{0}: {1}）".format(type(exc).__name__, exc)
                )
        if verify is not None:
            result.checksum_summary = {
                "path": CHECKSUM_FILENAME,
                "total": verify.total,
                "matched": verify.matched,
                "mismatched": verify.mismatched,
                "missing": verify.missing,
                "malformed": verify.malformed,
            }
            if not verify.ok:
                result.limitations.append(
                    "现有 {0} 未能全部通过校验（{1}）："
                    "上传前应重新生成".format(CHECKSUM_FILENAME, verify.summary())
                )
    else:
        result.checksum_summary = {"path": CHECKSUM_FILENAME, "exists": False}

    # --- 未覆盖范围 ---
    result.limitations.extend(_default_limitations(result, options))
    return result


def _run_secret_scan(result: AuditResult, options):
    """按扫描面调用 scan_secrets。返回 ``(ScanOutcome, 扫描面标签列表)``。"""
    surfaces: List[str] = []
    argv: List[str] = ["--repo", to_posix(result.repo_root), "--format", "json"]
    if getattr(options, "no_history", False):
        argv.extend(["--worktree", "--staged", "--artifacts"])
        if not getattr(options, "no_artifacts", False):
            surfaces = ["工作树", "暂存区", "日志与产物"]
        else:
            surfaces = ["工作树", "暂存区"]
    else:
        argv.extend(["--worktree", "--staged", "--history", "--artifacts"])
        surfaces = ["工作树", "暂存区", "提交历史", "日志与产物"]
    if getattr(options, "no_external", False):
        argv.append("--no-external")
    if getattr(options, "codeblock_soft", False):
        argv.append("--codeblock-soft")
    if getattr(options, "allowlist", None):
        pass  # 豁免清单由 scan_secrets 自行从项目根读取

    parser = _scan_secrets.build_parser()
    parsed = parser.parse_args(argv)
    if not (parsed.worktree or parsed.staged or parsed.history or parsed.artifacts):
        parsed.worktree = True

    repo_root = Path(parsed.repo)
    allowlist = _scan_secrets.load_allowlist(repo_root)
    outcome = _scan_secrets.ScanOutcome()
    for record in getattr(allowlist, "invalid", []):
        outcome.invalid_allow_entries.append(
            {"source_line": record.source_line, "reason": record.reason}
        )

    documents = []
    if parsed.worktree:
        docs, skipped = _scan_secrets.collect_worktree(repo_root, excludes=parsed.exclude)
        documents.extend(docs)
        outcome.files_skipped += skipped
    if parsed.artifacts:
        docs, skipped = _scan_secrets.collect_artifacts(repo_root)
        documents.extend(docs)
        outcome.files_skipped += skipped
    if parsed.staged:
        docs, _binary, error = _scan_secrets.collect_staged(repo_root)
        if error:
            outcome.external_notes.append("暂存区扫描失败：{0}".format(error))
        documents.extend(docs)
    if parsed.history:
        docs, _binary, error = _scan_secrets.collect_history(repo_root)
        if error:
            outcome.external_notes.append("历史扫描失败：{0}".format(error))
        documents.extend(docs)

    unique: Dict[Tuple[str, int, str], object] = {}
    for doc in documents:
        unique.setdefault((doc.path, doc.first_line_no, doc.label), doc)
    documents = list(unique.values())
    outcome.files_scanned = len(documents)
    outcome.surfaces = surfaces

    raw_findings: List[Finding] = []
    for doc in documents:
        # 给发现项打上来源标签，供后续占位符判定回查**产生它的那一份**文档。
        # 历史里的行号与工作树未必一致，记错来源会把文档示例误报成 BLOCKER。
        #
        # ⚠️ 这是一段**重复实现**：同样的编排逻辑在 scan_secrets.run_scan 里
        # 还有一份。因此任何改动都必须同时落到两处——只改一边就会漏，
        # 本次缺陷正是这样产生的。长期应当让本函数直接复用 run_scan，
        # 而不是继续维护第二份拷贝。
        for finding in _scan_secrets.scan_document(doc):
            if doc.label:
                finding.extra["source_label"] = doc.label
            raw_findings.append(finding)
    outcome.engines = [_scan_secrets.ENGINE_BUILTIN]

    external_findings: List[Finding] = []
    if not parsed.no_external:
        if _scan_secrets.which("gitleaks"):
            found, note = _scan_secrets.run_gitleaks(repo_root)
            external_findings.extend(found)
            outcome.external_notes.append(note)
        elif _scan_secrets.which("trufflehog"):
            found, note = _scan_secrets.run_trufflehog(repo_root)
            external_findings.extend(found)
            outcome.external_notes.append(note)
        else:
            outcome.external_notes.append(
                "未检测到 gitleaks / trufflehog，本次仅使用内置规则集"
            )
    else:
        outcome.external_notes.append("--no-external：跳过外部引擎")

    if external_findings:
        engines = sorted({item.engine for item in external_findings if item.engine})
        outcome.engines = engines + [_scan_secrets.ENGINE_BUILTIN]

    builtin_sites = {(item.path, item.line) for item in raw_findings}
    raw_findings.extend(
        item for item in external_findings if (item.path, item.line) not in builtin_sites
    )

    classified = _scan_secrets.classify(
        raw_findings, documents, allowlist, codeblock_soft=parsed.codeblock_soft
    )
    outcome.findings = classified.findings
    outcome.placeholders = classified.placeholders
    outcome.self_hits = classified.self_hits
    outcome.exemptions = classified.exemptions
    outcome.info_findings = classified.info_findings
    return outcome, surfaces


def _default_limitations(result: AuditResult, options) -> List[str]:
    """固定写入报告的"未覆盖"清单。"""
    limitations = [
        "密钥扫描只覆盖本次选定的扫描面；未推送过的本地文件、IDE 缓存、"
        "浏览器配置等不在此列。",
        "内置规则集基于正则与校验位，无法识别自定义格式的凭据"
        "（如内部系统自研的 token 格式）。",
        "本审计不做二进制内容分析：图片、可执行文件、压缩包内部未扫描。",
        "个人信息扫描只覆盖邮箱、中国大陆身份证号与带标签的电话号码；"
        "姓名、住址、银行卡以外的个人标识不在覆盖范围。",
        "依赖项自身的漏洞（SCA）、许可证兼容性分析、代码安全审查（SAST）"
        "均不属于本次审计范围。",
        "本报告不能证明不存在敏感信息，只能说明在既定规则与扫描面下未发现。",
    ]
    if getattr(options, "no_history", False):
        limitations.insert(
            0,
            "已通过 --no-history 跳过提交历史扫描：历史中的密钥仍然可见于 "
            "git log -p，本次结论不覆盖该风险。",
        )
    if getattr(options, "no_external", False):
        limitations.insert(0, "已通过 --no-external 跳过外部引擎，仅使用内置规则集。")
    if getattr(options, "no_artifacts", False):
        limitations.insert(0, "已通过 --no-artifacts 跳过日志与产物扫描。")
    return limitations


# ---------------------------------------------------------------------------
# 报告渲染
# ---------------------------------------------------------------------------


def render_markdown(result: AuditResult, options) -> str:
    findings = sort_findings(result.findings)
    counts = count_by_severity(findings)
    lines: List[str] = []
    lines.append("# GitHub 上传前审计报告")
    lines.append("")
    lines.append("- 运行时间：{0}".format(result.generated_at))
    lines.append("- 仓库根目录：`{0}`".format(to_posix(result.repo_root)))
    lines.append(
        "- 仓库名：`{0}`（来源：{1}{2}）".format(
            result.repo_name or "(未知)",
            result.repo_name_source,
            "，纯 ASCII" if result.repo_name and result.repo_name.isascii() else "",
        )
    )
    lines.append("- 分析工具：github-project-publisher scripts v{0}".format(_tool_version_string()))
    lines.append("")

    lines.append("## 工具版本")
    lines.append("")
    for version in result.tool_versions:
        lines.append("- {0}".format(version))
    lines.append("")

    lines.append("## 扫描面")
    lines.append("")
    if result.surfaces:
        for surface in result.surfaces:
            lines.append("- {0}".format(surface))
    else:
        lines.append("- （未执行密钥扫描）")
    lines.append("")
    lines.append(
        "- 扫描引擎：{0}".format(" + ".join(result.engines) if result.engines else "未执行")
    )
    if result.scan_stats.get("files_scanned") is not None:
        lines.append(
            "- 已扫描文件：{0}（跳过二进制/过大 {1}）".format(
                result.scan_stats.get("files_scanned", 0),
                result.scan_stats.get("files_skipped", 0),
            )
        )
    if result.scan_stats.get("tracked_ignored") is not None:
        lines.append(
            "- 「已跟踪且被 .gitignore 覆盖」的文件：{0} 个（GIT-005；"
            "非 0 表示忽略规则对它们无效）".format(
                result.scan_stats.get("tracked_ignored", 0)
            )
        )
    if result.scan_stats.get("large_files") is not None:
        lines.append(
            "- 历史中超过 50 MB 的对象：{0} 个（GIT-004；超过 100 MB 会被 GitHub 拒收）".format(
                result.scan_stats.get("large_files", 0)
            )
        )
    lines.append("")

    lines.append("## 结果汇总")
    lines.append("")
    lines.append("| 严重级别 | 数量 |")
    lines.append("|---|---|")
    for level in SEVERITIES:
        lines.append("| {0} | {1} |".format(level, counts.get(level, 0)))
    lines.append("")

    lines.append("## 发现项（按严重级别分组）")
    lines.append("")
    if findings:
        for level in SEVERITIES:
            group = [item for item in findings if item.severity == level]
            if not group:
                continue
            lines.append("### {0}（{1} 条）".format(level, len(group)))
            lines.append("")
            lines.append("| 规则 | 位置 | 说明 | 证据（脱敏） |")
            lines.append("|---|---|---|---|")
            for item in group:
                location = "{0}:{1}".format(item.path, item.line) if item.line else item.path
                lines.append(
                    "| `{0}` | `{1}` | {2} | `{3}` |".format(
                        item.rule_id,
                        _escape_cell(location),
                        _escape_cell(item.message),
                        _escape_cell(item.evidence_masked) or "—",
                    )
                )
            lines.append("")
    else:
        lines.append("无发现项。")
        lines.append("")

    lines.append("## 已应用的豁免")
    lines.append("")
    if result.exemptions:
        lines.append("| 规则 | 位置 | 匹配的通配 | 理由 | 清单行 |")
        lines.append("|---|---|---|---|---|")
        for record in result.exemptions:
            lines.append(
                "| `{0}` | `{1}:{2}` | `{3}` | {4} | {5} |".format(
                    record.get("rule_id"),
                    _escape_cell(str(record.get("path", ""))),
                    record.get("line"),
                    _escape_cell(str(record.get("matched_glob", ""))),
                    _escape_cell(str(record.get("reason", ""))),
                    record.get("allowlist_line", ""),
                )
            )
        lines.append("")
        lines.append(
            "> 每一条豁免都必须在 `.github-upload-audit/allowlist.txt` 中写明理由；"
            "缺少理由的条目会被拒绝，并计入下方的「非法条目」一节。"
        )
    else:
        lines.append("无。本次未使用任何手工豁免。")
    lines.append("")
    if result.invalid_allow_entries:
        lines.append("### 被拒绝的非法豁免条目")
        lines.append("")
        for record in result.invalid_allow_entries:
            lines.append(
                "- 清单第 {0} 行：{1}".format(
                    record.get("source_line"), record.get("reason")
                )
            )
        lines.append("")

    lines.append("## 已降级的占位符示例")
    lines.append("")
    lines.append(
        "共 {0} 条命中被识别为文档占位符（示例密钥、`example.com` 邮箱等），"
        "降级为 INFO 且不计入发现项。".format(len(result.placeholders))
    )
    lines.append("")
    if result.placeholders:
        lines.append("| 规则 | 位置 | 占位标记 |")
        lines.append("|---|---|---|")
        for record in result.placeholders[:50]:
            lines.append(
                "| `{0}` | `{1}:{2}` | {3} |".format(
                    record.get("rule_id"),
                    _escape_cell(str(record.get("path", ""))),
                    record.get("line"),
                    _escape_cell(str(record.get("marker", ""))),
                )
            )
        if len(result.placeholders) > 50:
            lines.append("")
            lines.append("（其余 {0} 条见 JSON 报告）".format(len(result.placeholders) - 50))
        lines.append("")

    if result.self_hits:
        lines.append("## 扫描器自扫描命中")
        lines.append("")
        lines.append(
            "{0} 条命中来自扫描器自身的规则定义文件（规则字面量，非密钥）。"
            "这些文件未被跳过，只是单独归类。".format(len(result.self_hits))
        )
        lines.append("")

    lines.append("## 提交身份核验（GIT-001）")
    lines.append("")
    identity = result.identity or {}
    if identity:
        lines.append("- 核验范围：{0}".format(identity.get("scope", "(未知)")))
        lines.append("- 历史条目：{0} 条".format(identity.get("history_entries", 0)))
        lines.append("- 去重地址数：{0}".format(identity.get("distinct_addresses", 0)))
        lines.append(
            "- 非隐私邮箱命中：{0} 条，涉及 {1} 个不同地址".format(
                identity.get("non_noreply_entries", 0),
                identity.get("distinct_non_noreply", 0),
            )
        )
        lines.append(
            "- 仓库级 user.email：{0}（{1}）".format(
                identity.get("effective_email_masked", "(未设置)"),
                "是隐私邮箱" if identity.get("identity_email_is_noreply") else "不是隐私邮箱",
            )
        )
        lines.append("- 地址值：本报告不输出任何地址明文（CWE-532）")
    else:
        lines.append("- 未执行（模块不可用）")
    lines.append("")

    lines.append("## 发布产物与校验和（REL-001）")
    lines.append("")
    artifacts = result.artifacts or {}
    lines.append("- 识别到的发布产物：{0} 个".format(artifacts.get("artifact_count", 0)))
    lines.append("- 校验和条目：{0} 条".format(artifacts.get("checksum_entries", 0)))
    unchecked = artifacts.get("unchecked") or []
    lines.append(
        "- 缺少摘要记录的产物：{0} 个{1}".format(
            len(unchecked),
            "（{0}）".format("、".join(str(item) for item in unchecked[:5])) if unchecked else "",
        )
    )
    summary = result.checksum_summary or {}
    if summary.get("exists") is False:
        lines.append("- 未找到 {0}：上传前应运行 make_checksums.py 生成".format(CHECKSUM_FILENAME))
    elif summary.get("total") is not None:
        lines.append(
            "- 现有 {0}：共 {1} 条，匹配 {2}，不匹配 {3}，缺失 {4}".format(
                summary.get("path", CHECKSUM_FILENAME),
                summary.get("total"),
                summary.get("matched"),
                len(summary.get("mismatched") or []),
                len(summary.get("missing") or []),
            )
        )
    lines.append("")

    if result.warnings:
        lines.append("## 运行警告")
        lines.append("")
        for warning in result.warnings:
            lines.append("- {0}".format(warning))
        lines.append("")

    lines.append("## 本次审计未能覆盖")
    lines.append("")
    for item in result.limitations:
        lines.append("- {0}".format(item))
    lines.append("")

    lines.append("## 判定")
    lines.append("")
    if result.blockers:
        lines.append(
            "**未通过**：存在 {0} 条 BLOCKER。按硬性规则，禁止 `git commit` 与 `git push`，"
            "直到逐项处置完成。".format(len(result.blockers))
        )
    else:
        lines.append(
            "**通过**：未发现 BLOCKER。注意「通过」仅表示在既定规则与扫描面下"
            "未发现问题，不构成不存在敏感信息的证明。"
        )
    lines.append("")
    lines.append(
        "> 本报告由 `audit_repo.py` 生成；报告本身也是披露面，"
        "所有证据均已脱敏（最多保留前 4 个字符）。"
    )
    lines.append("")
    return "\n".join(lines)


def _escape_cell(text: str) -> str:
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def _tool_version_string() -> str:
    try:
        import _common

        return _common.TOOL_VERSION
    except Exception:  # pragma: no cover
        return "1.0.0"


def build_json_payload(result: AuditResult, options) -> Dict[str, object]:
    findings = sort_findings(result.findings)
    return {
        "tool": "audit_repo",
        "generated_at": result.generated_at,
        "timestamp": result.timestamp_compact,
        "repo_root": to_posix(result.repo_root),
        "repo_name": result.repo_name,
        "repo_name_source": result.repo_name_source,
        "tool_versions": result.tool_versions,
        "engines": result.engines,
        "surfaces": result.surfaces,
        "counts": count_by_severity(findings),
        "findings": [item.to_dict() for item in findings],
        "placeholder_downgrades": {
            "count": len(result.placeholders),
            "records": result.placeholders,
        },
        "self_scan_hits": {"count": len(result.self_hits), "records": result.self_hits},
        "exemptions": {"count": len(result.exemptions), "records": result.exemptions},
        "invalid_allow_entries": result.invalid_allow_entries,
        "identity": result.identity,
        "artifacts": result.artifacts,
        "checksums": result.checksum_summary,
        "licenses": {
            "declared": result.declared_license,
            "file": result.file_license,
        },
        "scan_stats": result.scan_stats,
        "warnings": result.warnings,
        "limitations": result.limitations,
        "module_status": MODULE_STATUS,
        "blocker_count": len(result.blockers),
        "exit_code": result.exit_code(),
    }


def render_console_summary(result: AuditResult) -> str:
    findings = sort_findings(result.findings)
    counts = count_by_severity(findings)
    lines: List[str] = []
    lines.append("仓库：{0}".format(to_posix(result.repo_root)))
    lines.append("引擎：{0}".format(" + ".join(result.engines) if result.engines else "未执行"))
    lines.append(
        "扫描面：{0}".format("、".join(result.surfaces) if result.surfaces else "无")
    )
    lines.append(
        "统计：BLOCKER {0}｜MAJOR {1}｜MINOR {2}｜INFO {3}".format(
            counts.get(SEVERITY_BLOCKER, 0),
            counts.get(SEVERITY_MAJOR, 0),
            counts.get(SEVERITY_MINOR, 0),
            counts.get(SEVERITY_INFO, 0),
        )
    )
    lines.append(
        "占位符降级 {0} 条；豁免 {1} 条；非法豁免条目 {2} 条".format(
            len(result.placeholders), len(result.exemptions), len(result.invalid_allow_entries)
        )
    )
    if result.scan_stats.get("tracked_ignored") is not None:
        lines.append(
            "已跟踪且被 .gitignore 覆盖的文件（GIT-005）：{0} 个".format(
                result.scan_stats.get("tracked_ignored", 0)
            )
        )
    if result.scan_stats.get("large_files") is not None:
        lines.append(
            "历史中超过 50 MB 的对象（GIT-004）：{0} 个".format(
                result.scan_stats.get("large_files", 0)
            )
        )
    if findings:
        lines.append("发现项：")
        for item in findings:
            lines.append("  " + item.format_line())
    else:
        lines.append("发现项：无")
    for warning in result.warnings:
        lines.append("警告：{0}".format(warning))
    # 「未能覆盖」必须在控制台也可见。只写进 Markdown 报告是不够的：
    # --dry-run 不写报告，而它恰恰是最容易被用来「快速看一眼」的模式。
    # 看不见覆盖缺口，就会把「没检查」误读成「检查通过」。
    if result.limitations:
        lines.append("本次审计未能覆盖 {0} 项：".format(len(result.limitations)))
        for item in result.limitations[:3]:
            lines.append("  - {0}".format(item))
        if len(result.limitations) > 3:
            lines.append(
                "  …其余 {0} 项见 Markdown 报告的「本次审计未能覆盖」一节".format(
                    len(result.limitations) - 3
                )
            )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="audit_repo.py",
        description=(
            "GitHub 上传前聚合审计：静态检查 + 密钥扫描 + 身份核验 + 校验和检查，"
            "输出 Markdown 与 JSON 报告到 .github-upload-audit/。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "退出码：0 无 BLOCKER；1 存在 BLOCKER；2 执行错误。\n"
            "示例：python .\\audit_repo.py\n"
            "      python .\\audit_repo.py --repo C:\\path\\proj --no-history --dry-run"
        ),
    )
    parser.add_argument("--repo", metavar="DIR", default=None, help="项目根目录（默认 git 仓库根）")
    parser.add_argument("--out-dir", metavar="DIR", default=None, help="报告输出目录（默认 <repo>/.github-upload-audit）")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="照常计算全部结果，但不写任何文件",
    )
    parser.add_argument(
        "--no-history",
        action="store_true",
        help="跳过提交历史扫描（更快；但历史中的密钥仍可见，会写入未覆盖清单）",
    )
    parser.add_argument(
        "--no-artifacts",
        action="store_true",
        help="跳过日志与产物扫描",
    )
    parser.add_argument(
        "--no-large-files",
        action="store_true",
        help="跳过历史大文件检查（GIT-004）。默认执行：它是一次对象列表遍历，"
             "通常远快于历史密钥扫描，但超大仓库上仍可能较慢",
    )
    parser.add_argument(
        "--no-external",
        action="store_true",
        help="不使用 gitleaks / trufflehog",
    )
    parser.add_argument(
        "--codeblock-soft",
        action="store_true",
        help="围栏代码块内的 SEC-* 命中降为 MAJOR 但仍报告",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text", help="控制台输出格式")
    parser.add_argument("--quiet", action="store_true", help="只输出判定与报告路径")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)

    repo_root = resolve_repo_root(args.repo)
    if not repo_root.is_dir():
        print("执行错误：目录不存在 {0}".format(to_posix(repo_root)), file=sys.stderr)
        return 2

    try:
        result = run_audit(repo_root, args)
    except Exception as exc:
        print("执行错误：{0}: {1}".format(type(exc).__name__, exc), file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir) if args.out_dir else (repo_root / AUDIT_DIRNAME)
    markdown = render_markdown(result, args)
    payload = build_json_payload(result, args)
    json_text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    if not args.dry_run:
        base = REPORT_PREFIX + result.timestamp_compact
        md_path = out_dir / (base + ".md")
        json_path = out_dir / (base + ".json")
        try:
            write_text_utf8(md_path, markdown)
            write_text_utf8(json_path, json_text)
        except OSError as exc:
            print("执行错误：无法写入报告（{0}）".format(exc), file=sys.stderr)
            return 2
        result.markdown_path = md_path
        result.json_path = json_path

    print_banner("聚合审计报告")
    if args.format == "json":
        print(json_text)
    elif args.quiet:
        print(render_console_summary(result))
    else:
        print(render_console_summary(result))
    print("")
    if args.dry_run:
        print("--dry-run：未写入任何文件（报告内容已在上面展示）")
    else:
        print("Markdown 报告：{0}".format(to_posix(result.markdown_path)))
        print("JSON 报告：{0}".format(to_posix(result.json_path)))
    print("判定：{0}".format("未通过（存在 BLOCKER）" if result.blockers else "通过（无 BLOCKER）"))
    return result.exit_code()


if __name__ == "__main__":
    sys.exit(main())
