"""github-project-publisher 脚本层的共享约定。

本模块集中定义所有脚本共用的常量与工具函数，目的是：
1. 规则编号（rule id）与严重级别（severity）只在此处定义一次，避免各脚本漂移；
2. 敏感信息脱敏（masking）只在此处实现一次，确保任何输出路径都不可能泄露原文
   （对应 CWE-532：把敏感信息写入日志文件）；
3. 标准输出编码只在此处重配置一次，保证在 Windows cp936 控制台下不会抛
   UnicodeEncodeError。

仅使用 Python 标准库，不使用任何第三方依赖。
"""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# 版本与路径常量
# ---------------------------------------------------------------------------

TOOL_NAME = "github-project-publisher"
TOOL_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Python 版本要求
# ---------------------------------------------------------------------------

# 本套脚本使用 Python 3.9 才有的语法与标准库接口。
MIN_PYTHON = (3, 9)


def python_version_supported(version_info=None) -> bool:
    """判断解释器版本是否满足要求。

    单独抽成函数是为了能被自检覆盖：否则"版本太低"这条路径永远只能靠
    真去找一个旧解释器来验证，实际上就等于没验证过。
    """
    info = sys.version_info if version_info is None else version_info
    return (int(info[0]), int(info[1])) >= MIN_PYTHON


def _require_supported_python() -> None:
    """在导入期挡掉过旧的解释器，并给出可执行的说明。

    为什么要在导入期做：若放任不管，3.8 及更早会在某一行深处抛出
    SyntaxError 或 AttributeError。使用者（以及 Agent）看到的报错与真实原因
    无关，很容易判定成"脚本有 bug"，于是去改一个根本没问题的脚本。

    退出码取 2 而不是 1：按本项目的约定，
    **2 表示「检查根本没有跑成」，1 表示「跑了但没通过」**。
    两者混同会把一次未执行的检查读成一次通过。
    """
    if python_version_supported():
        return
    wanted = "{0}.{1}".format(*MIN_PYTHON)
    actual = "{0}.{1}.{2}".format(*sys.version_info[:3])
    sys.stderr.write(
        "{0} 需要 Python {1} 或更高版本，当前解释器为 {2}（{3}）。\n"
        "请改用受支持的解释器后重跑，可依次尝试：\n"
        "  python / python3 / py -3\n"
        "若以上都不满足，可使用 DSH 提供的解释器——\n"
        "  调用 load_workspace_dependencies，用其返回的 python 路径。\n"
        "退出码 2 表示「检查没有跑成」，不是「检查通过」。\n".format(
            TOOL_NAME, wanted, actual, sys.executable
        )
    )
    raise SystemExit(2)


_require_supported_python()

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------

SCRIPTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPTS_DIR.parent

ALLOWLIST_RELPATH = ".github-upload-audit/allowlist.txt"
AUDIT_DIRNAME = ".github-upload-audit"
CHECKSUM_FILENAME = "SHA256SUMS"

# 工作树遍历时永远跳过的目录：体积大或与提交内容无关。
DEFAULT_EXCLUDED_DIRS = (
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".idea",
    ".vscode",
)

# 单文件扫描上限（字节）。超过则跳过并记为 INFO，避免扫描巨型产物。
MAX_FILE_BYTES = 4 * 1024 * 1024

# ---------------------------------------------------------------------------
# 标准输出编码：Windows cp936 控制台不能直接打印中文/生僻字符。
# ---------------------------------------------------------------------------


def configure_stdio() -> None:
    """把 stdout/stderr 改为 UTF-8，失败不影响正常逻辑。"""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or not hasattr(stream, "reconfigure"):
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            # 某些被重定向的流不支持重配置，忽略即可。
            pass


# ---------------------------------------------------------------------------
# 严重级别
# ---------------------------------------------------------------------------

SEVERITY_BLOCKER = "BLOCKER"
SEVERITY_MAJOR = "MAJOR"
SEVERITY_MINOR = "MINOR"
SEVERITY_INFO = "INFO"

SEVERITIES = (SEVERITY_BLOCKER, SEVERITY_MAJOR, SEVERITY_MINOR, SEVERITY_INFO)

_SEVERITY_RANK = {
    SEVERITY_BLOCKER: 0,
    SEVERITY_MAJOR: 1,
    SEVERITY_MINOR: 2,
    SEVERITY_INFO: 3,
}


def severity_rank(severity: str) -> int:
    """返回严重级别排序权重，未知级别按 INFO 处理。"""
    return _SEVERITY_RANK.get(severity, 3)


def normalize_severity(severity: str) -> str:
    """把大小写不一致的级别名归一化，未知值降级为 INFO。"""
    upper = str(severity or "").strip().upper()
    return upper if upper in _SEVERITY_RANK else SEVERITY_INFO


# ---------------------------------------------------------------------------
# 发现项（finding）数据结构
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    """一条审计发现。

    evidence_masked 字段**必须**已经脱敏，禁止放入原始密钥或完整邮箱。
    """

    rule_id: str
    severity: str
    path: str
    line: int
    message: str
    evidence_masked: str = ""
    engine: str = ""
    extra: Dict[str, object] = field(default_factory=dict)

    def sort_key(self) -> Tuple[int, str, str, int]:
        return (severity_rank(self.severity), self.path, self.rule_id, self.line)

    def to_dict(self) -> Dict[str, object]:
        data: Dict[str, object] = {
            "rule_id": self.rule_id,
            "severity": self.severity,
            "path": self.path,
            "line": self.line,
            "message": self.message,
            "evidence_masked": self.evidence_masked,
        }
        if self.engine:
            data["engine"] = self.engine
        if self.extra:
            data["extra"] = self.extra
        return data

    def format_line(self) -> str:
        """统一的单行文本形式：SEVERITY rule_id path:line message"""
        location = self.path
        if self.line and self.line > 0:
            location = "{0}:{1}".format(self.path, self.line)
        text = "{0} {1} {2} {3}".format(self.severity, self.rule_id, location, self.message)
        if self.evidence_masked:
            text += " [证据: {0}]".format(self.evidence_masked)
        return text


def sort_findings(findings: Iterable[Finding]) -> List[Finding]:
    return sorted(findings, key=lambda item: item.sort_key())


def count_by_severity(findings: Iterable[Finding]) -> Dict[str, int]:
    counts = {level: 0 for level in SEVERITIES}
    for item in findings:
        counts[normalize_severity(item.severity)] = counts.get(
            normalize_severity(item.severity), 0
        ) + 1
    return counts


# ---------------------------------------------------------------------------
# 脱敏（masking）
# ---------------------------------------------------------------------------

MASK_SUFFIX = "\u2026"  # 单字符省略号 …

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_CREDENTIAL_URL_RE = re.compile(r"^([a-zA-Z][a-zA-Z0-9+.\-]*)://([^:@/\s]+):([^@/\s]+)@")

# 文档示例域名：显示出来不会泄露个人信息，便于作者定位文档位置。
PLACEHOLDER_DOMAINS = (
    "example.com",
    "example.org",
    "example.net",
    "example.edu",
    "example.test",
    "users.noreply.github.com",
    "localhost",
)

# 这些域名指向个人邮箱服务，一律不再显示域名（只保留 ***@***）。
_PERSONAL_MAIL_DOMAINS = (
    "gmail.com",
    "googlemail.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "yahoo.com",
    "qq.com",
    "foxmail.com",
    "163.com",
    "126.com",
    "sina.com",
    "sohu.com",
    "aliyun.com",
    "icloud.com",
    "me.com",
    "protonmail.com",
    "proton.me",
    "yandex.com",
    "zoho.com",
    "yeah.net",
)


def truncate_head(value: str, keep: int = 4) -> str:
    """只保留前 keep 个字符，后接省略号与总长度：``AKIA…(20)``。"""
    text = "" if value is None else str(value)
    if keep < 0:
        keep = 0
    head = text[:keep]
    return "{0}{1}({2})".format(head, MASK_SUFFIX, len(text))


def _looks_placeholder_email(address: str) -> bool:
    lowered = address.lower()
    if any(domain in lowered for domain in PLACEHOLDER_DOMAINS):
        return True
    for token in ("your_", "your-", "xxxx", "placeholder", "changeme", "redacted"):
        if token in lowered:
            return True
    return False


def mask_email(address: str, show_domain: bool = False) -> str:
    """邮箱脱敏：本地部分整体替换为 ***。

    默认只在域名属于文档示例域名时才显示域名；
    ``show_domain=True``（由调用方显式请求）时才显示非个人邮箱的域名。
    个人邮箱域名一律**不显示**。
    """
    text = (address or "").strip().strip("<>").strip()
    if "@" not in text:
        return truncate_head(text)
    local, _, domain = text.rpartition("@")
    lowered_domain = domain.lower()
    if any(lowered_domain == d or lowered_domain.endswith("." + d) for d in PLACEHOLDER_DOMAINS):
        return "***@{0}".format(domain)
    if any(lowered_domain == d or lowered_domain.endswith("." + d) for d in _PERSONAL_MAIL_DOMAINS):
        return "***@***"
    if not show_domain:
        return "***@***"
    return "***@{0}".format(domain)


def mask_url(value: str) -> str:
    """连接串脱敏：只保留协议，用户名与口令整体替换。

    不保留用户名片段——用户名常常就是工号或邮箱本地部分，属于同一个泄露面。
    """
    match = _CREDENTIAL_URL_RE.match(value or "")
    if not match:
        return truncate_head(value)
    return "{0}://***:***@".format(match.group(1))


def mask_evidence(value: str, show_domain: bool = False) -> str:
    """通用脱敏入口：按证据形态选择策略，绝不泄露原文。"""
    text = "" if value is None else str(value)
    if text == "":
        return ""
    if _CREDENTIAL_URL_RE.match(text):
        return mask_url(text)
    if _EMAIL_RE.match(text):
        return mask_email(text, show_domain=show_domain)
    return truncate_head(text)


# ---------------------------------------------------------------------------
# 占位符自动识别（降级为 INFO，不计入发现项）
# ---------------------------------------------------------------------------

# 文档中常见的占位写法。命中即降级，并在报告中单独计数。
PLACEHOLDER_MARKERS = (
    "example.com",
    "example.org",
    "example.net",
    "example.edu",
    "your_",
    "your-",
    "xxxx",
    "XXXX",
    "placeholder",
    "changeme",
    "change-me",
    "redacted",
    "****",
    "AKIAIOSFODNN7EXAMPLE",
    "12345678+username@users.noreply.github.com",
    "email@example.com",
    "users.noreply.github.com",
    "<your",
    "yourname",
    "your-name",
    "username@",
    "dev-secret",
    "dummy",
    "fake",
    "sample",
    "test-key",
    "testkey",
    "not-a-real",
    "todo",
    "yourpassword",
    "your_password",
    # 文档里给连接串占位用的写法：mysql://user:password@host
    "mysql://user",
    "postgres://user",
    "postgresql://user",
    "mongodb://user",
    "redis://user",
    "amqp://user",
)

# 连接串里"用户名/口令都是通用占位词"的情形：mysql://user:pass@
# 这类字符串出现在文档里是为了展示格式，不是真实凭据。
_PLACEHOLDER_URL_RE = re.compile(
    r"""(?ix)
    ^[a-z][a-z0-9+.\-]*://
    (?P<user>user|username|yourname|your_user|admin|
              <[^>]+>|\$\{[^}]+\})
    :
    (?P<password>pass|password|passwd|pwd|secret|changeme|
                   <[^>]+>|\$\{[^}]+\})
    @
    """
)

_ANGLE_TEMPLATE_RE = re.compile(r"<[^<>\s]{2,}>")


def is_placeholder(value: str) -> Tuple[bool, str]:
    """判断命中值是否为文档占位符。返回 ``(是否占位, 命中的标记)``。"""
    text = "" if value is None else str(value)
    lowered = text.lower()
    for marker in PLACEHOLDER_MARKERS:
        if marker.lower() in lowered:
            return True, marker
    # 角括号模板：<YOUR_TOKEN>、<token>、<email@example.com>
    if _ANGLE_TEMPLATE_RE.search(text) and ("<" in text and ">" in text):
        return True, "<...>"
    # 连接串占位：mysql://user:pass@（用户名与口令都是通用词）
    if _PLACEHOLDER_URL_RE.match(text):
        return True, "user:pass 占位连接串"
    return False, ""


# ---------------------------------------------------------------------------
# 自扫描命中（self-hit）
# ---------------------------------------------------------------------------
#
# 扫描器自己的规则定义文件里必然存在规则样式的字面量：
#   ``-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----``、``eyJ[A-Za-z0-9_\-]{10,}`` …
# 这些是"规则"，不是"密钥"，但正则匹配分不清二者。
#
# 处理方式刻意选择"单独列出"而不是"跳过这些文件"：
#   * 跳过 = 真密钥只要放在扫描器源码里就能溜过去，等于自毁防线；
#   * 降级为占位符 = 会在 INFO 里被当成"文档示例"，掩盖真实误报；
#   * 单独列出 = 位置与规则编号照样可见，审计留痕，但不污染 BLOCKER 计数。
#
# 判据刻意收得很窄：文件名匹配 ``scan_secrets.py`` / ``_common.py``，
# 且规则编号属于本工具自定义的 SEC-00x 段。
SELF_SCAN_FILENAMES = (
    "scan_secrets.py",
    "_common.py",
    "selftest.py",
    "audit_repo.py",
)


def is_self_scan_hit(rule_id: str, path: str) -> bool:
    """判断该命中是否为扫描器规则定义文件中的规则字面量。"""
    if not str(rule_id).startswith("SEC-"):
        return False
    name = to_posix(path).rsplit("/", 1)[-1].lower()
    return name in SELF_SCAN_FILENAMES


# ---------------------------------------------------------------------------
# 显式豁免清单（allowlist）
# ---------------------------------------------------------------------------


@dataclass
class AllowRule:
    """一条生效的豁免记录。reason 非空是硬性要求。"""

    rule_id: str
    path_glob: str
    line: str
    reason: str
    source_line: int

    def matches(self, rule_id: str, path: str, line: int) -> bool:
        if self.rule_id not in ("*", rule_id):
            return False
        if not fnmatch.fnmatchcase(path, self.path_glob) and not fnmatch.fnmatch(
            path, self.path_glob
        ):
            return False
        if self.line == "*":
            return True
        spec = self.line.strip()
        if "-" in spec:
            head, _, tail = spec.partition("-")
            try:
                low, high = int(head), int(tail)
            except ValueError:
                return False
            return low <= line <= high
        try:
            return int(spec) == line
        except ValueError:
            return False


@dataclass
class InvalidAllowEntry:
    """格式非法的豁免条目（缺理由、字段不足等）。"""

    source_line: int
    reason: str
    raw_masked: str


@dataclass
class Allowlist:
    """豁免清单：解析结果 + 生效记录。"""

    path: Optional[Path] = None
    rules: List[AllowRule] = field(default_factory=list)
    invalid: List[InvalidAllowEntry] = field(default_factory=list)
    loaded: bool = False

    def lookup(self, rule_id: str, path: str, line: int) -> Optional[AllowRule]:
        for rule in self.rules:
            if rule.matches(rule_id, path, line):
                return rule
        return None


def _is_comment_line(stripped: str) -> bool:
    return stripped.startswith("#")


def parse_allowlist_text(text: str, source: str = ALLOWLIST_RELPATH) -> Allowlist:
    """解析豁免清单文本。

    行格式（空白分隔，``--`` 之后为理由）::

        <rule_id>  <path-glob>  <line|*>  --  <reason>

    规则：

    * 理由必须由**该条目自身**给出：要么是行内 ``-- 理由``，
      要么是紧邻上方以 ``# reason:`` 开头的注释行。
    * 普通的 ``#`` 注释**不构成理由**。这一点是刻意的：如果"上面随便有条注释"
      就能当作理由，那么清单里迟早会出现"看上去有理由、其实是文件头注释"
      的条目，理由必填这条约束就形同虚设。
    * 同一行内可用 `` # `` 追加行尾注释（不构成理由）。
    * **理由为空即视为无效条目**并单独报告——没有理由的豁免不被接受。
    """
    entries = Allowlist()
    entries.loaded = True
    pending_reason = ""
    for index, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if stripped == "":
            pending_reason = ""
            continue
        if _is_comment_line(stripped):
            comment = stripped.lstrip("#").strip()
            if comment.lower().startswith(_REASON_PREFIX):
                pending_reason = comment[len(_REASON_PREFIX):].strip()
            else:
                pending_reason = ""  # 普通注释不构成理由
            continue

        body = stripped
        inline_reason = ""
        if "--" in body:
            body, _, inline_reason = body.partition("--")
            inline_reason = inline_reason.strip()
        else:
            # 去掉行尾注释，避免把 "# 说明" 误当作 path。
            hash_index = body.find("#")
            if hash_index > 0:
                body = body[:hash_index].strip()

        fields = body.split()
        if len(fields) < 3:
            entries.invalid.append(
                InvalidAllowEntry(
                    source_line=index,
                    reason="字段不足，需要 <规则编号> <路径通配> <行号|*> -- <理由>",
                    raw_masked=truncate_head(stripped, 0),
                )
            )
            pending_reason = ""
            continue

        rule_id, path_glob, line_spec = fields[0], fields[1], fields[2]
        reason = inline_reason or pending_reason.strip()
        if not reason:
            entries.invalid.append(
                InvalidAllowEntry(
                    source_line=index,
                    reason="缺少理由（行内 -- 之后，或上方 # reason: 注释，必须写明豁免原因）",
                    raw_masked=truncate_head(stripped, 0),
                )
            )
            pending_reason = ""
            continue

        if not _RULE_ID_RE.match(rule_id) and rule_id != "*":
            entries.invalid.append(
                InvalidAllowEntry(
                    source_line=index,
                    reason="规则编号格式不合法（应为 <AREA>-<NNN>）",
                    raw_masked=truncate_head(stripped, 0),
                )
            )
            pending_reason = ""
            continue

        if line_spec != "*":
            ok = _LINE_SPEC_RE.match(line_spec) is not None
            if not ok:
                entries.invalid.append(
                    InvalidAllowEntry(
                        source_line=index,
                        reason="行号必须是 * 或整数（可写 12-14 区间）",
                        raw_masked=truncate_head(stripped, 0),
                    )
                )
                pending_reason = ""
                continue

        entries.rules.append(
            AllowRule(
                rule_id=rule_id,
                path_glob=path_glob.replace("\\", "/"),
                line=line_spec,
                reason=reason,
                source_line=index,
            )
        )
        pending_reason = ""
    return entries


_RULE_ID_RE = re.compile(r"^(SEC|GIT|META|DOC|REL|ID)-\d{3}$")
_LINE_SPEC_RE = re.compile(r"^\d+(-\d+)?$")

# 独立成行的理由注释前缀：``# reason: 文档示例中的占位密钥``
_REASON_PREFIX = "reason:"


def load_allowlist(repo_root: Path) -> Allowlist:
    """从项目根读取 ``.github-upload-audit/allowlist.txt``（缺失则返回空清单）。"""
    path = Path(repo_root) / ALLOWLIST_RELPATH
    entries = Allowlist(path=path, loaded=False)
    if not path.is_file():
        return entries
    text = read_text_utf8(path)
    if text is None:
        return entries
    parsed = parse_allowlist_text(text, source=ALLOWLIST_RELPATH)
    parsed.path = path
    parsed.loaded = True
    return parsed


# ---------------------------------------------------------------------------
# 文件遍历与读写
# ---------------------------------------------------------------------------


def to_posix(path: Path | str) -> str:
    """把任意路径转成 POSIX 风格的字符串（统一用 / 分隔）。"""
    return str(path).replace("\\", "/")


def relative_posix(path: Path, root: Path) -> str:
    """返回相对 root 的 POSIX 风格路径；不在 root 下时返回原路径。"""
    try:
        rel = Path(path).resolve().relative_to(Path(root).resolve())
    except (ValueError, OSError):
        return to_posix(path)
    return to_posix(rel)


def read_text_utf8(path: Path, max_bytes: int = MAX_FILE_BYTES) -> Optional[str]:
    """读文本文件。返回 None 表示二进制、过大或不可读。

    会剥离可能存在的 UTF-8 BOM，避免 BOM 被当成正文的一部分参与匹配。
    """
    try:
        if not Path(path).is_file():
            return None
        size = Path(path).stat().st_size
        if size > max_bytes:
            return None
        with open(path, "rb") as handle:
            raw = handle.read(max_bytes + 1)
    except OSError:
        return None
    if len(raw) > max_bytes:
        return None
    if b"\x00" in raw[:4096]:
        return None  # 二进制文件
    for encoding in ("utf-8", "utf-8-sig"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    if text.startswith("\ufeff"):
        text = text[1:]
    return text


def write_text_utf8(path: Path, text: str) -> None:
    """写文本文件：UTF-8 无 BOM、LF 行尾。

    注意 ``newline="\\n"``：不加这个参数时 Windows 会把 ``\\n`` 变成 CRLF，
    而 CRLF 会破坏 ``SHA256SUMS``（Linux 侧 ``sha256sum -c`` 直接失败）。
    """
    target = Path(path)
    if target.parent and str(target.parent) not in ("", "."):
        target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def strip_bom(text: str) -> str:
    return text[1:] if text.startswith("\ufeff") else text


def is_probably_text(raw: bytes) -> bool:
    if b"\x00" in raw[:4096]:
        return False
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def walk_files(
    root: Path,
    exclude_dirs: Sequence[str] = DEFAULT_EXCLUDED_DIRS,
    follow_symlinks: bool = False,
) -> List[Path]:
    """递归收集 root 下的普通文件，跳过已知的大目录。

    使用 ``os.walk`` 而非 ``Path.rglob`` 以便就地裁剪目录。
    """
    results: List[Path] = []
    root = Path(root)
    if root.is_file():
        return [root]
    if not root.is_dir():
        return results
    excluded = {name.lower() for name in exclude_dirs}
    for current, dirnames, filenames in os.walk(root, followlinks=follow_symlinks):
        dirnames[:] = sorted(
            name
            for name in dirnames
            if name.lower() not in excluded and not name.startswith(".git")
        )
        for name in sorted(filenames):
            results.append(Path(current) / name)
    return results


def path_matches_any(rel_path: str, patterns: Sequence[str]) -> bool:
    """用 fnmatch 逐条匹配相对路径（大小写不敏感地再试一次）。"""
    for pattern in patterns or ():
        normalized = pattern.replace("\\", "/")
        if fnmatch.fnmatchcase(rel_path, normalized):
            return True
        if fnmatch.fnmatch(rel_path.lower(), normalized.lower()):
            return True
    return False


# ---------------------------------------------------------------------------
# 外部依赖探测与子进程
# ---------------------------------------------------------------------------


def which(program: str) -> Optional[str]:
    """探测可执行文件是否在 PATH 中（延迟导入 shutil 以缩小导入面）。"""
    import shutil

    return shutil.which(program)


def run_command(
    args: Sequence[str],
    cwd: Optional[Path] = None,
    timeout: int = 600,
    stdin_text: Optional[str] = None,
) -> Tuple[int, str, str]:
    """执行外部命令，返回 ``(returncode, stdout, stderr)``。

    ``stdin_text`` 用于需要从标准输入批量喂数据的子命令，例如
    ``git cat-file --batch-check``（GIT-004 用它一次性取回全部对象的大小，
    比逐个对象起进程快几个数量级）。

    失败（不存在、超时、权限）统一返回 ``(-1, "", 说明)``，调用方据此降级。
    """
    try:
        completed = subprocess.run(
            list(args),
            cwd=str(cwd) if cwd else None,
            input=stdin_text.encode("utf-8") if stdin_text is not None else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # 包含 TimeoutExpired
        return -1, "", "{0}: {1}".format(type(exc).__name__, exc)
    encoding = "utf-8"
    stdout = completed.stdout.decode(encoding, errors="replace")
    stderr = completed.stderr.decode(encoding, errors="replace")
    return completed.returncode, stdout, stderr


def find_repo_root(start: Optional[Path] = None) -> Optional[Path]:
    """定位 git 仓库根目录；找不到返回 None。"""
    base = Path(start) if start else Path.cwd()
    code, stdout, _ = run_command(["git", "rev-parse", "--show-toplevel"], cwd=base)
    if code != 0:
        return None
    line = stdout.strip().splitlines()
    if not line:
        return None
    return Path(line[0].strip())


def repo_name_from_remote(repo_root: Path) -> Tuple[str, str]:
    """返回 ``(仓库名, 来源说明)``。优先 remote origin，其次目录名。"""
    if repo_root is None:
        return "", "未知"
    code, stdout, _ = run_command(
        ["git", "config", "--get", "remote.origin.url"], cwd=repo_root
    )
    if code == 0 and stdout.strip():
        url = stdout.strip()
        tail = url.rstrip("/").split("/")[-1]
        if tail.endswith(".git"):
            tail = tail[:-4]
        for sep in (":", "/"):
            if sep in tail:
                tail = tail.rsplit(sep, 1)[-1]
        return tail, "git remote origin"
    return Path(repo_root).name, "本地目录名"


def tool_version(program: str, args: Sequence[str] = ("--version",)) -> str:
    """返回 ``程序 版本``；不可用时返回 ``程序 (未安装)``。"""
    if which(program) is None:
        return "{0} (未安装)".format(program)
    code, stdout, stderr = run_command([program] + list(args), timeout=60)
    text = (stdout or stderr).strip().splitlines()
    version = text[0].strip() if text else ""
    return "{0} {1}".format(program, version) if version else "{0} (无法获取版本)".format(program)


def utc_timestamp(compact: bool = False) -> str:
    """UTC 时间戳。compact=True 时用于文件名：20260929T054500Z。"""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    if compact:
        return now.strftime("%Y%m%dT%H%M%SZ")
    return now.strftime("%Y-%m-%d %H:%M:%S UTC")


# ---------------------------------------------------------------------------
# 规则目录与严重级别映射（各脚本共用，避免漂移）
# ---------------------------------------------------------------------------

RULE_SEVERITY: Dict[str, str] = {
    # scan_secrets
    "SEC-001": SEVERITY_BLOCKER,
    "SEC-002": SEVERITY_BLOCKER,
    "SEC-003": SEVERITY_BLOCKER,
    "SEC-004": SEVERITY_BLOCKER,
    "SEC-005": SEVERITY_BLOCKER,
    "SEC-006": SEVERITY_BLOCKER,
    "SEC-007": SEVERITY_BLOCKER,
    "SEC-008": SEVERITY_BLOCKER,
    "SEC-009": SEVERITY_BLOCKER,
    # check_identity
    "GIT-001": SEVERITY_BLOCKER,
    # audit_repo 静态检查
    # GIT-004 的级别按体积分档：50~100MB 为 MINOR；超过 100MB 时由调用方
    # 覆盖为 MAJOR，因为 GitHub 会直接拒收推送。此处登记的是默认（较低）档。
    "GIT-004": SEVERITY_MINOR,
    "GIT-005": SEVERITY_MAJOR,
    "META-001": SEVERITY_BLOCKER,
    "META-002": SEVERITY_BLOCKER,
    "META-003": SEVERITY_MINOR,
    "META-004": SEVERITY_MINOR,
    "META-005": SEVERITY_MAJOR,
    "META-006": SEVERITY_MAJOR,
    "DOC-001": SEVERITY_MINOR,
    "DOC-002": SEVERITY_MINOR,
    "DOC-003": SEVERITY_MINOR,
    "REL-001": SEVERITY_INFO,
    "ID-001": SEVERITY_INFO,
}

RULE_TITLES: Dict[str, str] = {
    "SEC-001": "硬编码 API 密钥 / 访问令牌",
    "SEC-002": "私钥文件内容",
    "SEC-003": "代码或配置中的明文口令",
    "SEC-004": "含凭据的连接串",
    "SEC-005": "支付类凭据（银行卡号 / IBAN）",
    "SEC-006": "个人信息（邮箱 / 身份证号 / 手机号）",
    "SEC-007": "云服务凭据文件",
    "SEC-008": "敏感值写入日志输出",
    "SEC-009": "JWT 形态令牌",
    "GIT-001": "提交身份不是 GitHub 隐私邮箱",
    "GIT-004": "历史中存在超大文件",
    "GIT-005": ".gitignore 对已被跟踪的文件无效",
    "META-001": "缺少 LICENSE",
    "META-002": "包清单声明的许可证与 LICENSE 文件不一致",
    "META-003": "缺少 README",
    "META-004": "缺少 .gitignore",
    "META-005": "缺少 .gitattributes",
    "META-006": "仓库名不是纯 ASCII",
    "DOC-001": "缺少 CHANGELOG",
    "DOC-002": "缺少 SECURITY.md",
    "DOC-003": "缺少 CONTRIBUTING.md",
    "REL-001": "发布产物没有对应的 SHA256 记录",
    "ID-001": "仓库内存在与本次结论矛盾的陈旧审计报告",
}


def rule_severity(rule_id: str, default: str = SEVERITY_INFO) -> str:
    return RULE_SEVERITY.get(rule_id, default)


def make_finding(
    rule_id: str,
    path: str,
    line: int,
    message: str,
    evidence: str = "",
    engine: str = "",
    severity: Optional[str] = None,
) -> Finding:
    """按规则目录生成发现项，evidence 会被强制脱敏。"""
    level = severity or rule_severity(rule_id)
    return Finding(
        rule_id=rule_id,
        severity=level,
        path=to_posix(path),
        line=line,
        message=message,
        evidence_masked=mask_evidence(evidence) if evidence else "",
        engine=engine,
    )


# ---------------------------------------------------------------------------
# 通用 argparse 辅助
# ---------------------------------------------------------------------------


def add_repo_argument(parser) -> None:
    parser.add_argument(
        "--repo",
        metavar="DIR",
        default=None,
        help="目标项目根目录（默认自动探测 git 仓库根，探测失败则用当前目录）",
    )


def resolve_repo_root(explicit: Optional[str]) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    detected = find_repo_root()
    if detected is not None:
        return detected
    return Path.cwd().resolve()


def print_banner(title: str) -> None:
    """统一的标题行，便于在长输出中定位。"""
    print("=" * 72)
    print("{0} v{1} — {2}".format(TOOL_NAME, TOOL_VERSION, title))
    print("=" * 72)


def display_width(text: str) -> int:
    """按终端显示宽度估算字符串宽度（中日韩字符算 2 列）。"""
    width = 0
    for char in text:
        if unicodedata.combining(char):
            continue
        width += 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1
    return width


def pad_display(text: str, width: int) -> str:
    return text + " " * max(0, width - display_width(text))


__all__ = [
    "TOOL_NAME",
    "TOOL_VERSION",
    "SCRIPTS_DIR",
    "SKILL_DIR",
    "ALLOWLIST_RELPATH",
    "AUDIT_DIRNAME",
    "CHECKSUM_FILENAME",
    "DEFAULT_EXCLUDED_DIRS",
    "MAX_FILE_BYTES",
    "SEVERITY_BLOCKER",
    "SEVERITY_MAJOR",
    "SEVERITY_MINOR",
    "SEVERITY_INFO",
    "SEVERITIES",
    "RULE_SEVERITY",
    "RULE_TITLES",
    "Finding",
    "AllowRule",
    "Allowlist",
    "InvalidAllowEntry",
    "configure_stdio",
    "severity_rank",
    "normalize_severity",
    "sort_findings",
    "count_by_severity",
    "truncate_head",
    "mask_email",
    "mask_url",
    "mask_evidence",
    "is_placeholder",
    "PLACEHOLDER_MARKERS",
    "is_self_scan_hit",
    "SELF_SCAN_FILENAMES",
    "parse_allowlist_text",
    "load_allowlist",
    "to_posix",
    "relative_posix",
    "read_text_utf8",
    "write_text_utf8",
    "strip_bom",
    "is_probably_text",
    "walk_files",
    "path_matches_any",
    "which",
    "run_command",
    "find_repo_root",
    "repo_name_from_remote",
    "tool_version",
    "utc_timestamp",
    "rule_severity",
    "make_finding",
    "add_repo_argument",
    "resolve_repo_root",
    "print_banner",
    "display_width",
    "pad_display",
]
