"""提交身份核验：author 与 committer 邮箱是否都是 GitHub 隐私邮箱。

为什么只输出"判定"而不输出地址
--------------------------------
核验命令本身就是一个泄露面：把 ``git log --format="%ae"`` 的结果打到终端，等于
把本来想保护的地址写进了终端回滚缓冲、CI 日志和会话记录。这正对应 CWE-532
（把敏感信息写入日志文件）。因此本脚本：

* 默认**绝不**打印任何地址，连掩码形式也不打印；
* ``--show-domain`` 是唯一的例外，且只显示域名、本地部分整体替换为 ``***``；
* 判定结果用"条数 + 去重地址数"表达，足够驱动后续动作。

退出码：0 通过；1 不通过；2 执行错误。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _common import (  # noqa: E402
    SEVERITY_BLOCKER,
    SEVERITY_INFO,
    Finding,
    configure_stdio,
    find_repo_root,
    mask_email,
    print_banner,
    resolve_repo_root,
    run_command,
    to_posix,
    utc_timestamp,
    write_text_utf8,
)

# GitHub 隐私邮箱：<数字ID>+<用户名>@users.noreply.github.com
# 也接受不带数字 ID 的旧式 <用户名>@users.noreply.github.com。
NOREPLY_PATTERN = r"^(\d+\+)?[A-Za-z0-9._-]+@users\.noreply\.github\.com$"
NOREPLY_RE = re.compile(NOREPLY_PATTERN)


def is_noreply(address: str) -> bool:
    """判断地址是否为 GitHub 隐私邮箱。空地址不算通过。"""
    return bool(NOREPLY_RE.match((address or "").strip()))


def build_noreply(user_id: str, username: str) -> str:
    """按 ``ID+USERNAME`` 生成隐私邮箱。用户名里的 ``@`` 会被剔除。"""
    ident = (user_id or "").strip()
    name = (username or "").strip().lstrip("@")
    if not name:
        raise ValueError("用户名不能为空")
    if ident:
        return "{0}+{1}@users.noreply.github.com".format(ident, name)
    return "{0}@users.noreply.github.com".format(name)


# ---------------------------------------------------------------------------
# 采集
# ---------------------------------------------------------------------------


def _history_addresses(repo_root: Path, all_refs: bool = True) -> Tuple[List[str], List[str], str]:
    """返回 ``(author 地址列表, committer 地址列表, 错误说明)``。

    使用 ``%ae%x00%ce%x00`` 以 NUL 分隔，避免地址里出现异常字符时切错列。
    格式串刻意不含 ``<``、``>``、``|`` 等 shell 特殊字符。
    """
    args = ["git", "log", "--format=%ae%x00%ce%x00"]
    if all_refs:
        args.insert(2, "--all")
    code, stdout, stderr = run_command(args, cwd=repo_root, timeout=300)
    if code != 0:
        message = (stderr or "").strip()
        if "does not have any commits" in message or "不存在任何提交" in message:
            return [], [], ""
        return [], [], message or "git log 执行失败"
    fields = stdout.split("\x00")
    authors: List[str] = []
    committers: List[str] = []
    index = 0
    while index + 1 < len(fields):
        authors.append(fields[index].strip())
        committers.append(fields[index + 1].strip())
        index += 2
    return authors, committers, ""


def _config_value(repo_root: Path, key: str, scope: Optional[str] = None) -> Optional[str]:
    args = ["git", "config"]
    if scope:
        args.append(scope)
    args.extend(["--get", key])
    code, stdout, _ = run_command(args, cwd=repo_root, timeout=60)
    if code != 0:
        return None
    value = stdout.strip()
    return value or None


def collect_identity(
    repo_root: Path, all_refs: bool = True, show_domain: bool = False
) -> Dict[str, object]:
    """采集全部身份信息。返回结构化结果，**不含**任何未脱敏地址。

    ``show_domain=True`` 时脱敏值保留域名（本地部分仍为 ``***``）；
    否则一律是 ``***@***``。原始地址只在本函数内存活，绝不进入返回值。
    """
    authors, committers, error = _history_addresses(repo_root, all_refs=all_refs)
    entries = [(address, "author") for address in authors]
    entries.extend((address, "committer") for address in committers)

    distinct: List[str] = []
    seen: set = set()
    non_noreply: List[Tuple[str, str]] = []
    for address, role in entries:
        if not address:
            continue
        lowered = address.lower()
        if lowered not in seen:
            seen.add(lowered)
            distinct.append(address)
        if not is_noreply(address):
            non_noreply.append((address, role))

    distinct_non_noreply: List[str] = []
    seen_bad: set = set()
    for address, _role in non_noreply:
        lowered = address.lower()
        if lowered not in seen_bad:
            seen_bad.add(lowered)
            distinct_non_noreply.append(address)

    effective = {
        "user.email": _config_value(repo_root, "user.email"),
        "user.name": _config_value(repo_root, "user.name"),
    }
    local_email = _config_value(repo_root, "user.email", scope="--local")
    global_email = _config_value(repo_root, "user.email", scope="--global")

    identity_ok = bool(effective["user.email"]) and is_noreply(str(effective["user.email"]))
    verdict = (not distinct_non_noreply) and identity_ok and not error

    return {
        "repo_root": to_posix(repo_root),
        "scope": "全部引用（--all）" if all_refs else "仅 HEAD 可达",
        "history_entries": len(entries),
        "distinct_addresses": len(distinct),
        "non_noreply_entries": len(non_noreply),
        "distinct_non_noreply": len(distinct_non_noreply),
        "non_noreply_addresses_masked": [
            # 注意 mask_email 的第一个参数是地址本身；这里必须逐个传入，
            # 不能写成 mask_email(列表, show_domain=...) —— 那只会把列表当成
            # 一个"非邮箱字符串"截断成 ''.join 后的第一个字符。
            mask_email(address, show_domain=show_domain)
            for address in distinct_non_noreply
        ],
        "effective_email_masked": mask_email(
            str(effective["user.email"]), show_domain=show_domain
        )
        if effective["user.email"]
        else "(未设置)",
        "effective_name_present": bool(effective["user.name"]),
        "local_email_masked": mask_email(str(local_email), show_domain=show_domain)
        if local_email
        else "(未设置)",
        "global_email_masked": mask_email(str(global_email), show_domain=show_domain)
        if global_email
        else "(未设置)",
        "identity_email_is_noreply": identity_ok,
        "error": error,
        "verdict": "pass" if verdict else "fail",
        "history_readable": not error,
    }


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------


def render_text(report: Dict[str, object], show_domain: bool = False) -> str:
    lines: List[str] = []
    lines.append("核验范围：{0}".format(report["scope"]))
    lines.append(
        "历史条目：{0} 条（author + committer）".format(report["history_entries"])
    )
    lines.append("去重后的地址数：{0}".format(report["distinct_addresses"]))
    lines.append(
        "非隐私邮箱命中：{0} 条；涉及 {1} 个不同地址".format(
            report["non_noreply_entries"], report["distinct_non_noreply"]
        )
    )
    effective_display = str(report.get("effective_email_masked") or "(未设置)")
    lines.append(
        "当前仓库 user.email：{0}（{1}）".format(
            effective_display,
            "是隐私邮箱" if report.get("identity_email_is_noreply") else "不是隐私邮箱",
        )
    )
    lines.append(
        "配置来源：--local {0}；--global {1}".format(
            report.get("local_email_masked", "(未设置)"),
            report.get("global_email_masked", "(未设置)"),
        )
    )
    if report.get("error"):
        lines.append("历史读取失败：{0}".format(report["error"]))

    if show_domain and report.get("non_noreply_addresses_masked"):
        lines.append("命中的地址（仅域名，--show-domain）：")
        # report 里存放的已经是脱敏值（***@域名）；此处不再做任何解码。
        for item in report["non_noreply_addresses_masked"]:
            lines.append("  {0}".format(item))
    else:
        lines.append("地址值：不输出（默认只报判定与条数）")

    lines.append("")
    lines.append(
        "判定：{0}".format("通过（全部为 GitHub 隐私邮箱）" if report["verdict"] == "pass"
                          else "未通过（存在非隐私邮箱）")
    )
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check_identity.py",
        description=(
            "核验 author 与 committer 邮箱是否均为 GitHub 隐私邮箱"
            "（<数字ID>+<用户名>@users.noreply.github.com）。"
            "只输出判定与条数，默认不回显任何地址。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "退出码：0 通过；1 不通过；2 执行错误。\n"
            "注意：--author 只覆盖 author，不覆盖 committer；"
            "两者都由 user.name / user.email 决定，因此必须核验两者。\n"
            "示例：python .\\check_identity.py --all\n"
            "      python .\\check_identity.py --fix-local 149449562+cicada478"
        ),
    )
    parser.add_argument("--repo", metavar="DIR", default=None, help="项目根目录（默认 git 仓库根）")
    parser.add_argument(
        "--all",
        dest="all_refs",
        action="store_true",
        default=True,
        help="核验全部引用的历史（默认开启）",
    )
    parser.add_argument(
        "--no-all",
        dest="all_refs",
        action="store_false",
        help="只核验 HEAD 可达的历史",
    )
    parser.add_argument(
        "--show-domain",
        action="store_true",
        help="允许显示命中地址的域名（本地部分仍为 ***）；默认完全不显示",
    )
    parser.add_argument(
        "--fix-local",
        metavar="ID+USERNAME",
        default=None,
        help="把 <ID+USERNAME>@users.noreply.github.com 写入仓库级 user.email（只改 --local）",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text", help="输出格式")
    parser.add_argument("--out", metavar="PATH", default=None, help="写入报告文件（UTF-8 无 BOM、LF）")
    return parser


def apply_fix_local(repo_root: Path, spec: str) -> Tuple[bool, str]:
    """把隐私邮箱写入仓库级配置。只改 ``--local``，绝不碰全局配置。"""
    text = (spec or "").strip()
    if "@" in text:
        address = text  # 允许直接传完整地址
        if not is_noreply(address):
            return False, "传入的地址不是 GitHub 隐私邮箱格式，已拒绝写入"
    else:
        user_id, _, username = text.partition("+")
        try:
            address = build_noreply(user_id, username or user_id)
        except ValueError as exc:
            return False, str(exc)
    code, _stdout, stderr = run_command(
        ["git", "config", "--local", "user.email", address], cwd=repo_root
    )
    if code != 0:
        return False, (stderr or "git config --local 执行失败").strip()
    return True, "已写入仓库级 user.email（仅 --local，未改动全局配置）"


def main(argv: Optional[Sequence[str]] = None) -> int:
    configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)

    repo_root = resolve_repo_root(args.repo)
    if not repo_root.is_dir():
        print("执行错误：目录不存在 {0}".format(to_posix(repo_root)), file=sys.stderr)
        return 2

    try:
        if args.fix_local:
            ok, message = apply_fix_local(repo_root, args.fix_local)
            print(("已修正：" if ok else "修正失败：") + message)
            if not ok:
                return 2
        report = collect_identity(
            repo_root, all_refs=args.all_refs, show_domain=args.show_domain
        )
    except Exception as exc:
        print("执行错误：{0}: {1}".format(type(exc).__name__, exc), file=sys.stderr)
        return 2

    text_report = render_text(report, show_domain=args.show_domain)
    findings: List[Finding] = []
    if report["verdict"] != "pass":
        findings.append(
            Finding(
                rule_id="GIT-001",
                severity=SEVERITY_BLOCKER,
                path="(git config / git log)",
                line=0,
                message=(
                    "author 或 committer 邮箱不是 GitHub 隐私邮箱：命中 {0} 条，"
                    "涉及 {1} 个不同地址".format(
                        report["non_noreply_entries"], report["distinct_non_noreply"]
                    )
                ),
                evidence_masked="",
            )
        )
    payload = {
        "tool": "check_identity",
        "generated_at": utc_timestamp(),
        "rule": "GIT-001",
        "pattern": NOREPLY_PATTERN,
        "report": report,
        "findings": [item.to_dict() for item in findings],
        "exit_code": 0 if report["verdict"] == "pass" else 1,
    }

    if args.format == "json":
        output = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    else:
        output = text_report

    if args.out:
        write_text_utf8(Path(args.out), output)
        print("报告已写入：{0}".format(to_posix(Path(args.out))))
        print(text_report)
    else:
        print(output)
    return 1 if report["verdict"] != "pass" else 0


if __name__ == "__main__":
    sys.exit(main())
