"""敏感信息扫描：工作树 / 暂存区 / 提交历史 / 产物文件。

设计要点
--------
1. **外部工具优先，内置规则兜底**：若 PATH 上有 ``gitleaks``（或 ``trufflehog``）
   就先跑外部引擎；外部引擎缺失或运行失败时自动回退到内置规则集，并在输出中
   明确标注本次使用了哪个引擎（engine），避免"看起来扫过了其实没扫"。
2. **绝不输出明文**：所有证据一律经过 :func:`_common.mask_evidence` 脱敏，
   最多显示前 4 个字符加省略号与总长度（CWE-532）。
3. **豁免双通道**：
   (a) 占位符自动识别 —— 文档里的示例密钥/示例邮箱降级为 INFO，单独计数，
       不计入发现项，避免"示例太多导致告警疲劳、真警报被忽略"；
   (b) 显式豁免清单 —— 项目根的 ``.github-upload-audit/allowlist.txt``，
       每条豁免**必须**写明理由，缺理由的条目被拒绝并单独报告。
4. 故意**不**实现"代码块内一律豁免"。``--codeblock-soft`` 只是把代码块内的
   命中从 BLOCKER 降为 MAJOR 且照样报告，防止真密钥藏在 README 里溜走。

退出码：0 = 无 BLOCKER/MAJOR；1 = 存在 BLOCKER 或 MAJOR；2 = 执行错误。
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from _common import (  # noqa: E402  (路径注入后再导入是刻意的)
    AUDIT_DIRNAME,
    DEFAULT_EXCLUDED_DIRS,
    MAX_FILE_BYTES,
    SEVERITIES,
    SEVERITY_BLOCKER,
    SEVERITY_INFO,
    SEVERITY_MAJOR,
    Finding,
    configure_stdio,
    count_by_severity,
    is_placeholder,
    is_self_scan_hit,
    load_allowlist,
    make_finding,
    mask_evidence,
    path_matches_any,
    print_banner,
    read_text_utf8,
    relative_posix,
    resolve_repo_root,
    run_command,
    sort_findings,
    to_posix,
    tool_version,
    truncate_head,
    utc_timestamp,
    which,
    walk_files,
    write_text_utf8,
)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

SURFACE_WORKTREE = "worktree"
SURFACE_STAGED = "staged"
SURFACE_HISTORY = "history"
SURFACE_ARTIFACTS = "artifacts"

ENGINE_BUILTIN = "builtin"
ENGINE_GITLEAKS = "gitleaks"
ENGINE_TRUFFLEHOG = "trufflehog"

# 熵阈值：低于此值的"疑似密钥"多为变量名或文档描述，直接丢弃以压制误报。
ENTROPY_THRESHOLD = 3.2

ARTIFACT_GLOBS = (
    "*.log",
    "*.log.*",
    "logs/*",
    "log/*",
    "dist/*",
    "build/*",
    "out/*",
    "target/*",
    "*.ipynb",
    ".github/workflows/*.yml",
    ".github/workflows/*.yaml",
    ".gitlab-ci.yml",
    ".travis.yml",
    "azure-pipelines.yml",
    "Jenkinsfile",
    ".circleci/config.yml",
    "*.out",
    "*.err",
)

# 明显是示例/占位容器的文件：不参与"产物"高亮，但仍会被普通扫描覆盖。
SKIP_BINARY_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".bmp", ".webp", ".pdf",
    ".zip", ".gz", ".tgz", ".bz2", ".7z", ".rar", ".woff", ".woff2",
    ".ttf", ".otf", ".xlsx", ".docx", ".pptx", ".pyc", ".so", ".dll",
    ".exe", ".bin", ".jar", ".class", ".mp3", ".mp4", ".mov", ".wasm",
)

# ---------------------------------------------------------------------------
# 文档（待扫描的文本单元）
# ---------------------------------------------------------------------------


class Document:
    """一段带归属位置的可扫描文本。

    ``lines`` 保留原始行号映射（索引 0 对应 ``first_line_no`` 行），
    这样 diff / 历史扫描也能给出"文件:行号"。
    """

    __slots__ = ("path", "lines", "first_line_no", "label")

    def __init__(
        self,
        path: str,
        lines: Sequence[str],
        first_line_no: int = 1,
        label: str = "",
    ) -> None:
        self.path = to_posix(path)
        self.lines = list(lines)
        self.first_line_no = first_line_no
        self.label = label

    def line_number(self, index: int) -> int:
        return self.first_line_no + index

    def text(self) -> str:
        return "\n".join(self.lines)


# ---------------------------------------------------------------------------
# 校验算法
# ---------------------------------------------------------------------------


def luhn_ok(digits: str) -> bool:
    """Luhn 校验：用于剔除随机 16 位数字，避免把订单号当卡号。"""
    if not digits.isdigit():
        return False
    total = 0
    parity = len(digits) % 2
    for index, char in enumerate(digits):
        value = int(char)
        if index % 2 == parity:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0


def iban_ok(candidate: str) -> bool:
    """IBAN mod-97 校验（ISO 13616）。"""
    compact = re.sub(r"\s+", "", candidate).upper()
    if not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$", compact):
        return False
    rearranged = compact[4:] + compact[:4]
    digits = []
    for char in rearranged:
        if char.isdigit():
            digits.append(char)
        else:
            digits.append(str(ord(char) - 55))
    try:
        return int("".join(digits)) % 97 == 1
    except ValueError:
        return False


_CN_ID_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_CN_ID_CHECK = "10X98765432"


def cn_id_ok(candidate: str) -> bool:
    """中国大陆居民身份证号校验（GB 11643-1999，含校验位与出生日期）。"""
    text = candidate.strip().upper()
    if not re.match(r"^\d{17}[\dX]$", text):
        return False
    year = int(text[6:10])
    month = int(text[10:12])
    day = int(text[12:14])
    if not (1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31):
        return False
    total = sum(int(text[i]) * _CN_ID_WEIGHTS[i] for i in range(17))
    return _CN_ID_CHECK[total % 11] == text[17]


def shannon_entropy(text: str) -> float:
    """香农熵（比特/字符），用于区分随机密钥与自然语言。"""
    if not text:
        return 0.0
    counts = Counter(text)
    length = float(len(text))
    entropy = 0.0
    for count in counts.values():
        probability = count / length
        entropy -= probability * math.log2(probability)
    return entropy


# "看起来像标识符而不是密钥"的形态：邮箱片段、URL、域名、UUID、路径。
# 这些串熵值往往很高，会被通用密钥规则误报。
_IDENTIFIER_PATTERNS = (
    re.compile(r"^[\w.+\-]+@[\w.\-]+"),          # 邮箱片段
    re.compile(r"^[a-z][a-z0-9+.\-]*://", re.I),  # URL
    re.compile(r"^[\w\-]+(\.[\w\-]+)+"),          # 域名 / 带点的标识符
    re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"),  # UUID
    re.compile(r"^/|^[A-Za-z]:[\\/]"),            # 路径
)
_URLISH_SUFFIXES = (
    "noreply.github.com",
    ".com", ".org", ".net", ".io", ".cn", ".dev", ".internal", ".local",
    ".json", ".yaml", ".yml", ".toml", ".md",
)


def _looks_like_identifier_not_secret(value: str) -> bool:
    """排除"高熵但不是密钥"的串，例如邮箱片段与域名。

    ``user.email "12345678+username@users.noreply"`` 这种赋值会同时被
    通用密钥规则捕获；它显然不是密钥，必须挡掉。
    """
    text = (value or "").strip()
    if not text:
        return False
    if " " in text or "\t" in text:
        return True
    for pattern in _IDENTIFIER_PATTERNS:
        if pattern.match(text):
            return True
    lowered = text.lower()
    for suffix in _URLISH_SUFFIXES:
        if lowered.endswith(suffix):
            return True
    return False


def _next_to_word_char(line: str, start: int, end: int) -> bool:
    """判断命中区间是否紧贴字母/下划线（属于标识符的一部分）。"""
    if start > 0 and (line[start - 1].isalnum() or line[start - 1] == "_"):
        return True
    if end < len(line) and (line[end].isalnum() or line[end] == "_"):
        return True
    return False


# ---------------------------------------------------------------------------
# 正则规则集
# ---------------------------------------------------------------------------

# SEC-001：硬编码的 API 密钥 / 访问令牌
SEC001_SPECIFIC = (
    ("AWS 访问密钥 ID", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GitHub 令牌", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("Slack 令牌", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
    ("Google API 密钥", re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b")),
    (
        "Google 服务账号私钥",
        re.compile(r'"private_key"\s*:\s*"(?P<value>[^"]{20,})"'),
    ),
    (
        "Azure 存储密钥",
        re.compile(r"(?i)\bAccountKey\s*=\s*(?P<value>[A-Za-z0-9+/=]{40,})"),
    ),
    ("Stripe 密钥", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}")),
    ("OpenAI 密钥", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
)

SEC001_GENERIC = re.compile(
    r"""(?ix)
    (?P<key>api[_-]?key|apikey|secret[_-]?key|access[_-]?token|auth[_-]?token|
             client[_-]?secret|bearer[_-]?token|private[_-]?key|secret)
    \s*[:=]\s*
    ["'](?P<value>[^"'\r\n]{16,})["']
    """
)

# SEC-002：私钥
SEC002_RE = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")

# SEC-003：代码或配置中的明文口令
SEC003_RE = re.compile(
    r"""(?ix)
    (?P<key>password|passwd|pwd)
    \s*[:=]\s*
    ["'](?P<value>[^"'\r\n]{6,})["']
    """
)

# SEC-004：含凭据的连接串
SEC004_RE = re.compile(
    r"""(?ix)
    \b(?P<scheme>mysql|mariadb|postgres|postgresql|mongodb(?:\+srv)?|redis|rediss|
                  amqp|amqps|mssql|clickhouse)
    ://
    (?P<user>[^:@/\s"'<>]+):(?P<password>[^@/\s"'<>]+)@
    """
)

# SEC-005：支付类凭据
SEC005_CARD_RE = re.compile(r"(?<![\dA-Za-z])(?:\d[ -]?){12,18}\d(?![\dA-Za-z])")
SEC005_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}[ ]?[A-Z0-9]{1,4}\b")
# 卡号语境词：出现这些词时，纯数字串也按卡号候选处理。
SEC005_CONTEXT_RE = re.compile(
    r"(?i)\b(card|card_?no|card_?number|pan|credit|debit|visa|mastercard|amex|"
    r"unionpay|cc_?num|卡号|银行卡|信用卡|借记卡)\b"
)

# SEC-006：个人信息
SEC006_EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"
)
SEC006_CN_ID_RE = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
SEC006_PHONE_RE = re.compile(
    r"(?i)(?:手机|电话|手机号|联系方式|phone|mobile|tel|telephone|contact)"
    r"\s*[:：=]\s*(\+?86[ \-]?)?(1[3-9]\d{9}|0\d{2,3}[ \-]?\d{7,8}|\+?[1-9]\d{6,14})"
)

# SEC-008：敏感值写入日志输出
#
# 顺序很重要：必须让 logger/log/console/print 这些"带点调用"的形式先匹配，
# 否则 ``logger.info(...)`` 会被 ``\binfo\b`` 抢先匹配，pattern 停在 ``logger``
# 后面，紧接着的 ``.info(`` 就对不上 ``\.\w+\(``，整条日志语句判定失败。
SEC008_LOG_RE = re.compile(
    r"""(?ix)
    (?P<prefix>
        \[\s*(?:info|warn|warning|error|debug|trace|notice)\s*\] |
        \b(?:logger|logging|log|console|print)\b\s*(?:\.\w+)?\s*\( |
        \b(?:INFO|WARN|WARNING|ERROR|DEBUG|TRACE)\b |
        \b(?:printk|syslog)\b
    )
    """
)
SEC008_SECRET_RE = re.compile(
    r"""(?ix)
    (
        \bAKIA[0-9A-Z]{16}\b |
        \bgh[pousr]_[A-Za-z0-9]{36,}\b |
        \bxox[baprs]-[A-Za-z0-9-]{10,} |
        \bAIza[0-9A-Za-z\-_]{35}\b |
        \bsk-[A-Za-z0-9]{20,}\b |
        -----BEGIN [A-Z0-9 ]*PRIVATE KEY----- |
        # 键名 + 引号包裹的值。引号前允许出现反斜杠转义（\"），
        # 否则 log/print 语句里最常见的 \"...\" 形式会漏报。
        (?:api[_-]?key|apikey|secret[_-]?key|access[_-]?token|auth[_-]?token|
           client[_-]?secret|token|secret|password|passwd|pwd)
        \s*[:=]\s*\\?["'][^"'\r\n]{8,}\\?["']
    )
    """
)

# SEC-009：JWT
SEC009_RE = re.compile(
    r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"
)

# SEC-007：云凭据文件
SEC007_AWS_RE = re.compile(r"(?i)^\s*aws_secret_access_key\s*=\s*(?P<value>\S{16,})")
SEC007_NPM_RE = re.compile(r"(?i)_authToken\s*=\s*(?P<value>\S{8,})")
SEC007_PYPIRC_RE = re.compile(r"(?i)^\s*password\s*[:=]\s*(?P<value>\S{6,})")

# 代码块围栏：仅用于 --codeblock-soft 的降级判定，绝不用于豁免。
FENCE_RE = re.compile(r"^\s*(```|~~~)")


def _code_fence_flags(lines: Sequence[str]) -> List[str]:
    """逐行标记代码块状态。

    返回 ``"inside"`` / ``"fence"`` / ``""``：

    * ``"inside"``：位于成对围栏之间，可被 ``--codeblock-soft`` 软化；
    * ``"fence"``：围栏行本身（``` 或 ~~~）。**不参与软化**——围栏行上的密钥
      往往贴在反引号里，属于正文而非示例内容，软化它会成为绕过通道；
    * ``""``：普通正文。
    """
    flags: List[str] = []
    inside = False
    for line in lines:
        if FENCE_RE.match(line):
            flags.append("fence")
            inside = not inside
        else:
            flags.append("inside" if inside else "")
    return flags


# ---------------------------------------------------------------------------
# 内置规则引擎
# ---------------------------------------------------------------------------


def _emit(
    rule_id: str,
    doc: Document,
    index: int,
    message: str,
    value: str,
    severity: Optional[str] = None,
) -> Finding:
    finding = make_finding(
        rule_id,
        doc.path,
        doc.line_number(index),
        message,
        evidence=value,
        engine=ENGINE_BUILTIN,
        severity=severity,
    )
    if doc.label:
        finding.extra["source"] = doc.label
    return finding


def scan_document(doc: Document) -> List[Finding]:
    """对单个文档逐行套用内置规则。"""
    findings: List[Finding] = []
    fence_flags = _code_fence_flags(doc.lines)
    for index, raw_line in enumerate(doc.lines):
        line = raw_line.rstrip("\n")
        if not line.strip():
            continue
        finder = _LineFinder(doc, index, line, findings)
        finder.run_specific_keys()
        finder.run_generic_keys()
        finder.run_private_keys()
        finder.run_passwords()
        finder.run_connection_strings()
        finder.run_payment()
        finder.run_personal_info()
        finder.run_credentials_files()
        finder.run_logs()
        finder.run_jwt()
    return findings


class _LineFinder:
    """把一行文本送进各条规则的辅助对象（避免超长函数与重复参数）。"""

    def __init__(self, doc: Document, index: int, line: str, sink: List[Finding]) -> None:
        self.doc = doc
        self.index = index
        self.line = line
        self.sink = sink
        # 已被"精确规则"占用的字符区间：用于避免同一条密钥被报两次
        # （例如 api_key = "AKIA…" 会同时被 AWS 规则和通用键名规则命中）。
        self.occupied: List[Tuple[int, int]] = []

    def add(
        self,
        rule_id: str,
        message: str,
        value: str,
        severity: Optional[str] = None,
    ) -> None:
        self.sink.append(_emit(rule_id, self.doc, self.index, message, value, severity))

    def _overlaps_occupied(self, start: int, end: int) -> bool:
        for occupied_start, occupied_end in self.occupied:
            if start < occupied_end and occupied_start < end:
                return True
        return False

    # -- SEC-001 -----------------------------------------------------------
    def run_specific_keys(self) -> None:
        for label, pattern in SEC001_SPECIFIC:
            for match in pattern.finditer(self.line):
                if label == "Google 服务账号私钥" and match.group(0).startswith('"private_key"'):
                    # 服务账号私钥按 SEC-002 处理更贴切，此处不重复报。
                    continue
                self.occupied.append(match.span())
                value = match.groupdict().get("value") or match.group(0)
                self.add("SEC-001", "疑似硬编码{0}".format(label), value)

    def run_generic_keys(self) -> None:
        for match in SEC001_GENERIC.finditer(self.line):
            if self._overlaps_occupied(*match.span("value")):
                continue  # 已经由精确规则报过，不再重复
            value = match.group("value")
            if shannon_entropy(value) < ENTROPY_THRESHOLD:
                continue  # 熵太低，多半是变量名或文档描述
            if _looks_like_identifier_not_secret(value):
                continue  # 邮箱片段、URL、路径等：不是密钥
            self.add(
                "SEC-001",
                "疑似硬编码密钥（键名 {0}，熵 {1:.2f}）".format(
                    match.group("key"), shannon_entropy(value)
                ),
                value,
            )

    # -- SEC-002 -----------------------------------------------------------
    def run_private_keys(self) -> None:
        match = SEC002_RE.search(self.line)
        if match:
            self.add("SEC-002", "私钥内容出现在文件中", "-----BEGIN PRIVATE KEY-----")
        for match in re.finditer(r'"private_key"\s*:\s*"(?P<value>[^"]{20,})"', self.line):
            self.add("SEC-002", "服务账号 JSON 内嵌私钥", match.group("value"))

    # -- SEC-003 -----------------------------------------------------------
    def run_passwords(self) -> None:
        for match in SEC003_RE.finditer(self.line):
            value = match.group("value")
            if shannon_entropy(value) < 2.0:
                continue
            self.add(
                "SEC-003",
                "疑似明文口令（键名 {0}）".format(match.group("key")),
                value,
            )

    # -- SEC-004 -----------------------------------------------------------
    def run_connection_strings(self) -> None:
        for match in SEC004_RE.finditer(self.line):
            self.add(
                "SEC-004",
                "连接串内嵌用户名与口令（{0}）".format(match.group("scheme")),
                match.group(0),
            )

    # -- SEC-005 -----------------------------------------------------------
    def run_payment(self) -> None:
        """银行卡号：Luhn 校验 + 上下文门控。

        单靠"Luhn + 位数"会误报：时间戳、构建号、追踪号里恰好通过 Luhn 的
        16 位数字并不罕见（例如 ``build = 2026092912345678``）。误报会让使用者
        学会忽略告警，最终让阻断机制失效，因此追加一条上下文门控：

        * 命中处紧邻数字（是更长数字串的一段）→ 跳过，交给更长的候选处理；
        * 命中处带分隔符（``4111 1111 1111 1111``）→ 可信；
        * 同一行出现卡号相关词（card/pan/credit/卡号…）→ 可信。
        """
        seen: set = set()
        for match in SEC005_CARD_RE.finditer(self.line):
            raw = match.group(0)
            if raw[0].isdigit() and match.start() > 0 and self.line[match.start() - 1].isdigit():
                continue  # 前面还有数字，说明这是更长数字串的尾部
            if raw[-1].isdigit() and match.end() < len(self.line) and self.line[match.end()].isdigit():
                continue  # 后面还有数字，同上
            if _next_to_word_char(self.line, match.start(), match.end()):
                continue  # 与字母/下划线相连，属于标识符的一部分

            digits = re.sub(r"[ -]", "", raw)
            if not 13 <= len(digits) <= 19:
                continue
            if digits in seen or not luhn_ok(digits):
                continue
            has_separator = " " in raw or "-" in raw
            has_context = SEC005_CONTEXT_RE.search(self.line) is not None
            if not (has_separator or has_context):
                continue  # 纯数字串且无卡号语境：按噪音跳过，避免告警疲劳
            seen.add(digits)
            self.add(
                "SEC-005",
                "疑似银行卡号（通过 Luhn 校验{0}）".format(
                    "，含分隔符" if has_separator else "，命中卡号语境词"
                ),
                raw,
            )
        for match in SEC005_IBAN_RE.finditer(self.line):
            if iban_ok(match.group(0)):
                self.add("SEC-005", "疑似 IBAN（通过 mod-97 校验）", match.group(0))

    # -- SEC-006 -----------------------------------------------------------
    def run_personal_info(self) -> None:
        for match in SEC006_EMAIL_RE.finditer(self.line):
            self.add("SEC-006", "个人信息：邮箱地址", match.group(0))
        for match in SEC006_CN_ID_RE.finditer(self.line):
            if cn_id_ok(match.group(0)):
                self.add("SEC-006", "个人信息：中国大陆身份证号", match.group(0))
        for match in SEC006_PHONE_RE.finditer(self.line):
            self.add("SEC-006", "个人信息：电话号码", match.group(0))

    # -- SEC-007 -----------------------------------------------------------
    def run_credentials_files(self) -> None:
        path = self.doc.path
        lowered = path.lower()
        if lowered.endswith(".aws/credentials") or lowered.endswith("/credentials"):
            match = SEC007_AWS_RE.search(self.line)
            if match:
                self.add("SEC-007", "AWS 凭据文件中的 secret access key", match.group("value"))
        if lowered.endswith(".npmrc"):
            match = SEC007_NPM_RE.search(self.line)
            if match:
                self.add("SEC-007", ".npmrc 中的 _authToken", match.group("value"))
        if lowered.endswith(".pypirc"):
            match = SEC007_PYPIRC_RE.search(self.line)
            if match:
                self.add("SEC-007", ".pypirc 中的明文口令", match.group("value"))
        if lowered.endswith(".pem") or lowered.endswith(".key"):
            if SEC002_RE.search(self.line):
                self.add("SEC-007", "仓库内出现私钥文件", "-----BEGIN PRIVATE KEY-----")

    # -- SEC-008 -----------------------------------------------------------
    def run_logs(self) -> None:
        """敏感值写入日志。

        这里刻意**先找密钥值、再判断是否在日志语境**，而不是反过来要求
        "行内先出现日志关键字"。原实现要求日志关键字与键名赋值紧邻，
        结果 ``logger.info("... api_key = \\"...\\"")`` 这种最常见的形式反而漏报——
        漏报比误报危险得多，因为它表现为"静默通过"。
        """
        secret_match = SEC008_SECRET_RE.search(self.line)
        if not secret_match:
            return
        if not SEC008_LOG_RE.search(self.line):
            return
        self.add("SEC-008", "敏感值被写入日志输出", secret_match.group(0))

    # -- SEC-009 -----------------------------------------------------------
    def run_jwt(self) -> None:
        for match in SEC009_RE.finditer(self.line):
            token = match.group(0)
            if token.count(".") != 2:
                continue
            if not _jwt_header_ok(token):
                continue
            self.add("SEC-009", "JWT 形态令牌", token)


def _jwt_header_ok(token: str) -> bool:
    """校验 JWT 头部能 base64url 解码且含 alg，进一步压制误报。"""
    head = token.split(".", 1)[0]
    padding = "=" * (-len(head) % 4)
    try:
        decoded = base64.urlsafe_b64decode(head + padding)
    except (ValueError, TypeError):
        return False
    try:
        payload = json.loads(decoded.decode("utf-8", errors="replace"))
    except ValueError:
        return False
    return isinstance(payload, dict) and ("alg" in payload or "typ" in payload)


# ---------------------------------------------------------------------------
# 扫描面：工作树 / 暂存区 / 历史 / 产物
# ---------------------------------------------------------------------------


def _read_document(path: Path, repo_root: Path) -> Optional[Document]:
    if path.suffix.lower() in SKIP_BINARY_SUFFIXES:
        return None
    text = read_text_utf8(path, max_bytes=MAX_FILE_BYTES)
    if text is None:
        return None
    rel = relative_posix(path, repo_root)
    return Document(rel, _split_lines(text))


def _split_lines(text: str) -> List[str]:
    """按行切分并抹掉 CR。

    必须显式处理 CR：Windows 工作树里大量文件是 CRLF，若用 ``split("\\n")``
    会在每行末尾留下 ``\\r``，既让"行内容"匹配出现偏差，也让文档里的行号
    说明与真实文件对不上（``str.splitlines()`` 才不会留下 ``\\r``）。
    """
    return text.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def collect_worktree(repo_root: Path, excludes: Sequence[str] = ()) -> Tuple[List[Document], int]:
    """遍历工作树。返回 ``(文档列表, 因二进制/过大而跳过的文件数)``。"""
    documents: List[Document] = []
    skipped = 0
    for path in walk_files(repo_root):
        rel = relative_posix(path, repo_root)
        if excludes and path_matches_any(rel, excludes):
            continue
        document = _read_document(path, repo_root)
        if document is None:
            skipped += 1
            continue
        documents.append(document)
    return documents, skipped


def collect_artifacts(repo_root: Path) -> Tuple[List[Document], int]:
    """只挑日志与产物类文件（含 .ipynb、CI 配置）。"""
    documents: List[Document] = []
    skipped = 0
    for path in walk_files(repo_root):
        rel = relative_posix(path, repo_root)
        if not path_matches_any(rel, ARTIFACT_GLOBS):
            continue
        document = _read_document(path, repo_root)
        if document is None:
            skipped += 1
            continue
        document.label = "artifact"
        documents.append(document)
    return documents, skipped


_DIFF_FILE_RE = re.compile(r"^\+\+\+ b/(?P<path>.+)$")
_DIFF_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,\d+)? @@")


def _documents_from_unified_diff(diff_text: str, label: str) -> Tuple[List[Document], int]:
    """把 unified diff 切成"每个文件一段、带新文件行号"的文档。"""
    documents: List[Document] = []
    current_path: Optional[str] = None
    current_lines: List[str] = []
    current_start = 1
    new_line_no = 1
    binary = 0

    def flush() -> None:
        nonlocal current_lines
        if current_path is not None and current_lines:
            documents.append(Document(current_path, current_lines, current_start, label))
        current_lines = []

    for raw in diff_text.splitlines():
        if raw.startswith("diff --git "):
            flush()
            current_path = None
            continue
        if raw.startswith("Binary files ") or raw.startswith("GIT binary patch"):
            binary += 1
            continue
        match = _DIFF_FILE_RE.match(raw)
        if match:
            flush()
            current_path = match.group("path").strip()
            current_start = 1
            new_line_no = 1
            continue
        hunk = _DIFF_HUNK_RE.match(raw)
        if hunk:
            flush()
            new_line_no = int(hunk.group("start"))
            current_start = new_line_no
            continue
        if current_path is None or raw.startswith(("--- ", "index ", "new file", "deleted file",
                                                   "similarity index", "rename ", "old mode",
                                                   "new mode", "\\ No newline")):
            continue
        if raw.startswith("+"):
            if len(current_lines) == 0:
                current_start = new_line_no
            current_lines.append(raw[1:])
            new_line_no += 1
        elif raw.startswith("-"):
            continue
        else:
            # 上下文行：diff 中不参与新增内容判定，仅用于推进行号。
            new_line_no += 1
    flush()
    return documents, binary


def collect_staged(repo_root: Path) -> Tuple[List[Document], int, str]:
    code, stdout, stderr = run_command(
        ["git", "diff", "--cached", "--unified=0", "--no-color", "--no-ext-diff"],
        cwd=repo_root,
    )
    if code != 0:
        return [], 0, stderr.strip() or "git diff --cached 执行失败"
    documents, binary = _documents_from_unified_diff(stdout, "staged")
    return documents, binary, ""


_HISTORY_HEADER = "GPP-COMMIT %H"


def collect_history(repo_root: Path, all_refs: bool = True) -> Tuple[List[Document], int, str]:
    """扫描全部提交历史。显式提醒：这一步在大型仓库上很慢。"""
    args = ["git", "log", "--format=" + _HISTORY_HEADER, "--no-color", "-p", "--no-ext-diff"]
    if all_refs:
        args.insert(2, "--all")
    code, stdout, stderr = run_command(args, cwd=repo_root, timeout=1800)
    if code != 0:
        return [], 0, stderr.strip() or "git log 执行失败"

    documents: List[Document] = []
    binary = 0
    chunk: List[str] = []
    commit = ""
    for raw in stdout.splitlines():
        if raw.startswith("GPP-COMMIT "):
            if chunk:
                docs, bin_count = _documents_from_unified_diff("\n".join(chunk), commit)
                documents.extend(docs)
                binary += bin_count
            commit = raw.split(" ", 1)[1].strip()[:12]
            chunk = []
            continue
        chunk.append(raw)
    if chunk:
        docs, bin_count = _documents_from_unified_diff("\n".join(chunk), commit)
        documents.extend(docs)
        binary += bin_count
    return documents, binary, ""


# ---------------------------------------------------------------------------
# 外部引擎
# ---------------------------------------------------------------------------


_GITLEAKS_SEVERITY = {
    "critical": SEVERITY_BLOCKER,
    "high": SEVERITY_BLOCKER,
    "medium": SEVERITY_MAJOR,
    "low": SEVERITY_MAJOR,
    "info": SEVERITY_INFO,
}


def parse_gitleaks_report(text: str) -> List[Finding]:
    """解析 gitleaks JSON 报告，统一映射到 EXT- 前缀规则编号。"""
    findings: List[Finding] = []
    try:
        payload = json.loads(text)
    except ValueError:
        return findings
    if isinstance(payload, dict):
        records = payload.get("findings") or payload.get("Leaks") or []
    elif isinstance(payload, list):
        records = payload
    else:
        records = []
    for record in records:
        if not isinstance(record, dict):
            continue
        rule = str(record.get("RuleID") or record.get("ruleID") or record.get("rule") or "unknown")
        secret = str(record.get("Secret") or record.get("secret") or "")
        path = str(record.get("File") or record.get("file") or "")
        line = record.get("StartLine") or record.get("startLine") or record.get("line") or 0
        try:
            line_no = int(line)
        except (TypeError, ValueError):
            line_no = 0
        severity = _GITLEAKS_SEVERITY.get(
            str(record.get("Severity") or "").lower(), SEVERITY_BLOCKER
        )
        findings.append(
            Finding(
                rule_id="EXT-{0}".format(re.sub(r"[^A-Za-z0-9]+", "-", rule).strip("-").upper()),
                severity=severity,
                path=to_posix(path),
                line=line_no,
                message="外部引擎 gitleaks 命中规则 {0}".format(rule),
                evidence_masked=mask_evidence(secret) if secret else "",
                engine=ENGINE_GITLEAKS,
            )
        )
    return findings


def parse_trufflehog_report(text: str) -> List[Finding]:
    """解析 trufflehog JSONL 输出。"""
    findings: List[Finding] = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            record = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(record, dict):
            continue
        detector = str(record.get("DetectorName") or record.get("detector_name") or "unknown")
        path = str(record.get("SourceMetadata", {}).get("Data", {}).get("Filesystem", {}).get("file", "")) \
            if isinstance(record.get("SourceMetadata"), dict) else ""
        line = record.get("SourceMetadata", {}).get("Data", {}).get("Filesystem", {}).get("line", 0) \
            if isinstance(record.get("SourceMetadata"), dict) else 0
        try:
            line_no = int(line)
        except (TypeError, ValueError):
            line_no = 0
        findings.append(
            Finding(
                rule_id="EXT-{0}".format(re.sub(r"[^A-Za-z0-9]+", "-", detector).strip("-").upper()),
                severity=SEVERITY_BLOCKER,
                path=to_posix(path),
                line=line_no,
                message="外部引擎 trufflehog 命中检测器 {0}".format(detector),
                evidence_masked="",
                engine=ENGINE_TRUFFLEHOG,
            )
        )
    return findings


def run_gitleaks(repo_root: Path) -> Tuple[List[Finding], str]:
    """执行 gitleaks 并解析结果。返回 ``(发现项, 状态说明)``。"""
    if which("gitleaks") is None:
        return [], "gitleaks 不在 PATH 中"
    tmp_dir = tempfile.mkdtemp(prefix="gpp-gitleaks-")
    report_path = Path(tmp_dir) / "gitleaks.json"
    version_code, version_out, _ = run_command(["gitleaks", "version"], timeout=60)
    legacy = version_code == 0 and re.match(r"^\s*[0-7]\.", version_out.strip())
    if legacy:
        args = [
            "gitleaks", "detect", "--no-banner", "--no-git",
            "--report-format", "json", "--report-path", str(report_path),
            "--source", str(repo_root),
        ]
    else:
        args = [
            "gitleaks", "detect", "--no-banner",
            "--report-format", "json", "--report-path", str(report_path),
            "--source", str(repo_root),
        ]
    code, stdout, stderr = run_command(args, cwd=repo_root, timeout=900)
    if not report_path.is_file():
        return [], "gitleaks 未生成报告（exit={0}）：{1}".format(code, (stderr or "").strip()[:200])
    try:
        text = report_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return [], "读取 gitleaks 报告失败：{0}".format(exc)
    findings = parse_gitleaks_report(text)
    return findings, "gitleaks 完成，命中 {0} 条".format(len(findings))


def run_trufflehog(repo_root: Path) -> Tuple[List[Finding], str]:
    if which("trufflehog") is None:
        return [], "trufflehog 不在 PATH 中"
    code, stdout, stderr = run_command(
        ["trufflehog", "filesystem", "--json", "--no-update", str(repo_root)],
        cwd=repo_root,
        timeout=900,
    )
    if code not in (0, 183):
        return [], "trufflehog 执行失败（exit={0}）：{1}".format(code, (stderr or "").strip()[:200])
    findings = parse_trufflehog_report(stdout)
    return findings, "trufflehog 完成，命中 {0} 条".format(len(findings))


def run_external_report_file(path: Path) -> Tuple[List[Finding], str]:
    """读取预先由外部工具生成的报告（用于 CI 复用或引擎离线验证）。"""
    text = read_text_utf8(path, max_bytes=64 * 1024 * 1024)
    if text is None:
        return [], "外部报告不可读：{0}".format(path)
    try:
        payload = json.loads(text)
    except ValueError:
        findings = parse_trufflehog_report(text)
        return findings, "按 trufflehog JSONL 解析，命中 {0} 条".format(len(findings))
    if isinstance(payload, (list, dict)):
        findings = parse_gitleaks_report(json.dumps(payload))
        if findings:
            return findings, "按 gitleaks JSON 解析，命中 {0} 条".format(len(findings))
        findings = parse_trufflehog_report(text)
        return findings, "按 trufflehog JSONL 解析，命中 {0} 条".format(len(findings))
    return [], "外部报告格式无法识别"


# ---------------------------------------------------------------------------
# 结果分类：占位符降级 / 豁免 / 代码块软化
# ---------------------------------------------------------------------------


class ScanOutcome:
    """一次完整扫描的结果容器。"""

    def __init__(self) -> None:
        self.findings: List[Finding] = []
        self.info_findings: List[Finding] = []
        self.placeholders: List[Dict[str, object]] = []
        self.self_hits: List[Dict[str, object]] = []
        self.exemptions: List[Dict[str, object]] = []
        self.external_notes: List[str] = []
        self.engines: List[str] = []
        self.surfaces: List[str] = []
        self.files_scanned = 0
        self.files_skipped = 0
        self.invalid_allow_entries: List[Dict[str, object]] = []


def _line_text_of(doc: Document, line_no: int) -> str:
    index = line_no - doc.first_line_no
    if 0 <= index < len(doc.lines):
        return doc.lines[index]
    return ""


def classify(
    findings: Iterable[Finding],
    documents: Sequence[Document],
    allowlist,
    codeblock_soft: bool = False,
) -> ScanOutcome:
    """把原始命中分为：占位符降级 / 被豁免 / 正式发现项。

    只有占位符会被"降级"（进 INFO 且不计入发现项）；
    被豁免的条目仍然会作为记录写进报告——每一步刻意的操作都必须留下痕迹。
    """
    outcome = ScanOutcome()
    doc_index: Dict[str, Document] = {}
    for doc in documents:
        doc_index.setdefault(doc.path, doc)

    for finding in findings:
        reason_kind, detail = is_placeholder(finding.evidence_masked)
        # 证据已脱敏，占位符判定必须用原文；因此这里回查原文。
        original = _original_value(doc_index.get(finding.path), finding)
        if original:
            reason_kind, detail = is_placeholder(original)
        if reason_kind:
            downgraded = Finding(
                rule_id=finding.rule_id,
                severity=SEVERITY_INFO,
                path=finding.path,
                line=finding.line,
                message="{0}（占位符示例：{1}）".format(finding.message, detail),
                evidence_masked=finding.evidence_masked,
                engine=finding.engine,
            )
            outcome.info_findings.append(downgraded)
            outcome.placeholders.append(
                {
                    "rule_id": finding.rule_id,
                    "path": finding.path,
                    "line": finding.line,
                    "marker": detail,
                    "source_kind": "placeholder",
                    "evidence_masked": finding.evidence_masked,
                }
            )
            continue

        if is_self_scan_hit(finding.rule_id, finding.path):
            # 规则定义文件里的规则字面量：单独列出，不污染 BLOCKER 计数。
            outcome.self_hits.append(
                {
                    "rule_id": finding.rule_id,
                    "path": finding.path,
                    "line": finding.line,
                    "marker": "规则定义字面量",
                    "source_kind": "self_hit",
                    "evidence_masked": finding.evidence_masked,
                }
            )
            continue

        rule = allowlist.lookup(finding.rule_id, finding.path, finding.line) if allowlist else None
        if rule is not None:
            outcome.exemptions.append(
                {
                    "rule_id": finding.rule_id,
                    "path": finding.path,
                    "line": finding.line,
                    "matched_glob": rule.path_glob,
                    "reason": rule.reason,
                    "allowlist_line": rule.source_line,
                }
            )
            continue

        if codeblock_soft and finding.rule_id.startswith("SEC-") and doc_index:
            doc = doc_index.get(finding.path)
            if doc is not None:
                index = finding.line - doc.first_line_no
                flags = _code_fence_flags(doc.lines)
                if 0 <= index < len(flags) and flags[index] == "inside":
                    finding = Finding(
                        rule_id=finding.rule_id,
                        severity=SEVERITY_MAJOR,
                        path=finding.path,
                        line=finding.line,
                        message="{0}（位于围栏代码块内，--codeblock-soft 降级但仍报告）".format(
                            finding.message
                        ),
                        evidence_masked=finding.evidence_masked,
                        engine=finding.engine,
                    )
        outcome.findings.append(finding)
    return outcome


def _original_value(doc: Optional[Document], finding: Finding) -> str:
    """从原始行里取回命中值，用于占位符判定（判定后立即丢弃，不外泄）。"""
    if doc is None:
        return ""
    line = _line_text_of(doc, finding.line)
    if not line:
        return ""
    if finding.rule_id == "SEC-006":
        # SEC006_EMAIL_RE 的本地部分是贪婪匹配，能取回完整邮箱
        # （早期版本给本地部分加了 \b 前缀、且依赖非贪婪边界，会把
        #  1+u@users.noreply.github.com 截成 ...@users.noreply 而无法识别占位符）。
        match = SEC006_EMAIL_RE.search(line)
        if match:
            return match.group(0)
    if finding.rule_id == "SEC-009":
        match = SEC009_RE.search(line)
        if match:
            return match.group(0)
    if finding.rule_id == "SEC-002":
        return "-----BEGIN PRIVATE KEY-----"
    if finding.rule_id == "SEC-004":
        # 连接串必须整体回查：只看密码字段会把 mysql://user:pass@ 的占位形式漏掉。
        match = SEC004_RE.search(line)
        if match:
            return match.group(0)
    for pattern in (
        SEC001_GENERIC, SEC003_RE, SEC008_SECRET_RE,
    ):
        match = pattern.search(line)
        if match:
            groups = match.groupdict()
            return groups.get("value") or groups.get("password") or match.group(0)
    for _label, pattern in SEC001_SPECIFIC:
        match = pattern.search(line)
        if match:
            return match.groupdict().get("value") or match.group(0)
    return ""


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------


def build_payload(outcome: ScanOutcome, allowlist, duration_note: str = "") -> Dict[str, object]:
    findings = sort_findings(outcome.findings)
    counts = count_by_severity(findings)
    return {
        "tool": "scan_secrets",
        "generated_at": utc_timestamp(),
        "engines": outcome.engines,
        "surfaces": outcome.surfaces,
        "files_scanned": outcome.files_scanned,
        "files_skipped": outcome.files_skipped,
        "counts": counts,
        "findings": [item.to_dict() for item in findings],
        "placeholder_downgrades": {
            "count": len(outcome.placeholders),
            "records": outcome.placeholders,
        },
        "self_scan_hits": {
            "count": len(outcome.self_hits),
            "records": outcome.self_hits,
            "note": (
                "扫描器自身的规则定义文件里必然出现规则字面量（例如 "
                "-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----）。这些是规则而非密钥，"
                "单独列出以免污染 BLOCKER 计数；并未跳过这些文件。"
            ),
        },
        "exemptions": {
            "count": len(outcome.exemptions),
            "records": outcome.exemptions,
            "allowlist_path": to_posix(allowlist.path) if getattr(allowlist, "path", None) else "",
        },
        "invalid_allow_entries": outcome.invalid_allow_entries,
        "external_notes": outcome.external_notes,
        "notes": duration_note,
        "exit_code": compute_exit_code(findings),
    }


def compute_exit_code(findings: Sequence[Finding]) -> int:
    for item in findings:
        if item.severity in (SEVERITY_BLOCKER, SEVERITY_MAJOR):
            return 1
    return 0


def render_text(outcome: ScanOutcome, allowlist) -> str:
    findings = sort_findings(outcome.findings)
    counts = count_by_severity(findings)
    lines: List[str] = []
    lines.append("扫描引擎：{0}".format(" + ".join(outcome.engines) or "未执行"))
    lines.append("扫描面：{0}".format("、".join(outcome.surfaces) or "无"))
    lines.append(
        "文件数：已扫描 {0}，跳过（二进制/过大）{1}".format(
            outcome.files_scanned, outcome.files_skipped
        )
    )
    for note in outcome.external_notes:
        lines.append("引擎说明：{0}".format(note))
    if getattr(allowlist, "path", None) is not None:
        if allowlist.loaded:
            lines.append(
                "豁免清单：{0}（生效 {1} 条，非法 {2} 条）".format(
                    to_posix(allowlist.path), len(allowlist.rules), len(allowlist.invalid)
                )
            )
        else:
            lines.append("豁免清单：未提供（{0} 不存在）".format(to_posix(allowlist.path)))
    lines.append("")
    lines.append("按严重级别统计：")
    for level in SEVERITIES:
        lines.append("  {0:<8} {1}".format(level, counts.get(level, 0)))
    lines.append("")

    if findings:
        lines.append("发现项（证据已脱敏，最多显示前 4 个字符）：")
        for item in findings:
            lines.append("  " + item.format_line())
    else:
        lines.append("发现项：无")

    lines.append("")
    lines.append("已降级的占位符示例 {0} 条（不计入发现项）".format(len(outcome.placeholders)))
    for record in outcome.placeholders[:20]:
        lines.append(
            "  INFO {0} {1}:{2} 占位符标记 {3}".format(
                record["rule_id"], record["path"], record["line"], record["marker"]
            )
        )
    if len(outcome.placeholders) > 20:
        lines.append("  …… 其余 {0} 条见 JSON 报告".format(len(outcome.placeholders) - 20))

    lines.append("")
    lines.append(
        "扫描器自扫描命中 {0} 条（规则定义文件中的规则字面量，非密钥，不计入发现项）".format(
            len(outcome.self_hits)
        )
    )
    for record in outcome.self_hits[:10]:
        lines.append(
            "  INFO {0} {1}:{2} 规则定义字面量".format(
                record["rule_id"], record["path"], record["line"]
            )
        )
    if len(outcome.self_hits) > 10:
        lines.append("  …… 其余 {0} 条见 JSON 报告".format(len(outcome.self_hits) - 10))

    lines.append("")
    lines.append("已应用的豁免 {0} 条（每条都附理由）：".format(len(outcome.exemptions)))
    for record in outcome.exemptions:
        lines.append(
            "  {0} {1}:{2} 理由：{3}".format(
                record["rule_id"], record["path"], record["line"], record["reason"]
            )
        )
    if outcome.invalid_allow_entries:
        lines.append("")
        lines.append("非法豁免条目 {0} 条（缺少理由或格式错误，已被拒绝）：".format(
            len(outcome.invalid_allow_entries)
        ))
        for record in outcome.invalid_allow_entries:
            lines.append(
                "  第 {0} 行：{1}".format(record["source_line"], record["reason"])
            )

    lines.append("")
    verdict = "通过（无 BLOCKER / MAJOR）" if compute_exit_code(findings) == 0 else "未通过（存在 BLOCKER 或 MAJOR）"
    lines.append("判定：{0}".format(verdict))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scan_secrets.py",
        description=(
            "扫描密钥、凭据与个人信息（默认扫描工作树）。"
            "外部引擎优先（gitleaks / trufflehog），失败或缺失时回退内置规则集。"
            "所有证据输出前一律脱敏，最多显示前 4 个字符。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "退出码：0 无 BLOCKER/MAJOR；1 存在 BLOCKER 或 MAJOR；2 执行错误。\n"
            "豁免：项目根 .github-upload-audit/allowlist.txt，"
            "格式「规则编号 路径通配 行号|* -- 理由」，缺理由的条目会被拒绝。\n"
            "示例：python .\\scan_secrets.py --worktree --format json --out report.json"
        ),
    )
    parser.add_argument("--repo", metavar="DIR", default=None, help="项目根目录（默认 git 仓库根）")
    parser.add_argument("--worktree", action="store_true", help="扫描工作树（默认开启）")
    parser.add_argument("--staged", action="store_true", help="扫描暂存区（git diff --cached）")
    parser.add_argument(
        "--history",
        action="store_true",
        help="扫描全部提交历史（git log --all -p）；大仓库上明显更慢",
    )
    parser.add_argument(
        "--artifacts",
        action="store_true",
        help="额外扫描日志与产物（*.log、dist/、build/、*.ipynb 输出、CI 配置）",
    )
    parser.add_argument(
        "--no-external",
        action="store_true",
        help="不使用 gitleaks / trufflehog，只用内置规则集",
    )
    parser.add_argument(
        "--paranoid",
        action="store_true",
        help="即使外部引擎命中，也强制再跑一遍内置规则集",
    )
    parser.add_argument(
        "--external-report",
        metavar="PATH",
        default=None,
        help="复用外部工具已生成的 JSON 报告（gitleaks JSON 或 trufflehog JSONL）",
    )
    parser.add_argument(
        "--codeblock-soft",
        action="store_true",
        help="默认关闭：围栏代码块内的 SEC-* 命中降为 MAJOR，但仍然报告（不豁免）",
    )
    parser.add_argument(
        "--exclude",
        metavar="GLOB",
        action="append",
        default=[],
        help="跳过匹配该 glob 的相对路径（可重复）",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="输出格式，默认 text",
    )
    parser.add_argument("--out", metavar="PATH", default=None, help="把报告写入文件（UTF-8 无 BOM、LF）")
    parser.add_argument("--quiet", action="store_true", help="静默模式：只输出退出码对应的判定行")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)

    if not (args.worktree or args.staged or args.history or args.artifacts):
        args.worktree = True  # 默认扫描工作树

    try:
        return _run(args)
    except Exception as exc:  # 执行错误统一映射到退出码 2
        print("执行错误：{0}: {1}".format(type(exc).__name__, exc), file=sys.stderr)
        return 2


def _run(args) -> int:
    repo_root = resolve_repo_root(args.repo)
    if not repo_root.is_dir():
        print("执行错误：目录不存在 {0}".format(repo_root), file=sys.stderr)
        return 2

    allowlist = load_allowlist(repo_root)
    outcome = ScanOutcome()
    for record in getattr(allowlist, "invalid", []):
        outcome.invalid_allow_entries.append(
            {"source_line": record.source_line, "reason": record.reason}
        )

    documents: List[Document] = []
    surfaces: List[str] = []

    if args.worktree:
        docs, skipped = collect_worktree(repo_root, excludes=args.exclude)
        documents.extend(docs)
        outcome.files_skipped += skipped
        surfaces.append("工作树")

    if args.artifacts:
        docs, skipped = collect_artifacts(repo_root)
        documents.extend(docs)
        outcome.files_skipped += skipped
        surfaces.append("日志与产物")

    if args.staged:
        docs, _binary, error = collect_staged(repo_root)
        if error:
            outcome.external_notes.append("暂存区扫描失败：{0}".format(error))
        documents.extend(docs)
        surfaces.append("暂存区")

    if args.history:
        docs, _binary, error = collect_history(repo_root)
        if error:
            outcome.external_notes.append("历史扫描失败：{0}".format(error))
        documents.extend(docs)
        surfaces.append("提交历史")

    # 去重：同一份内容可能同时来自工作树与产物面。
    unique: Dict[Tuple[str, int, str], Document] = {}
    for doc in documents:
        unique.setdefault((doc.path, doc.first_line_no, doc.label), doc)
    documents = list(unique.values())

    outcome.files_scanned = len(documents)
    outcome.surfaces = surfaces

    raw_findings: List[Finding] = []
    for doc in documents:
        raw_findings.extend(scan_document(doc))
    outcome.engines = [ENGINE_BUILTIN]

    # --- 外部引擎 ---
    external_findings: List[Finding] = []
    if args.external_report:
        report_path = Path(args.external_report)
        if not report_path.is_absolute():
            report_path = repo_root / report_path
        found, note = run_external_report_file(report_path)
        external_findings.extend(found)
        outcome.external_notes.append(note)
    elif not args.no_external:
        if which("gitleaks"):
            found, note = run_gitleaks(repo_root)
            external_findings.extend(found)
            outcome.external_notes.append(note)
        elif which("trufflehog"):
            found, note = run_trufflehog(repo_root)
            external_findings.extend(found)
            outcome.external_notes.append(note)
        else:
            outcome.external_notes.append(
                "未检测到 gitleaks / trufflehog，本次仅使用内置规则集（内置规则覆盖 SEC-001..SEC-009）"
            )
    else:
        outcome.external_notes.append("--no-external：跳过外部引擎，仅使用内置规则集")

    if external_findings:
        engines = sorted({item.engine for item in external_findings if item.engine})
        if args.external_report:
            outcome.engines = engines + [ENGINE_BUILTIN]
        elif "gitleaks" in engines or "trufflehog" in engines:
            outcome.engines = engines + [ENGINE_BUILTIN]
    elif args.paranoid:
        outcome.external_notes.append("--paranoid：外部引擎无命中，仍完整执行内置规则集")

    # 外部结果与内置结果在同一位置重复时，保留内置结果（规则编号可用于豁免）。
    builtin_sites = {(item.path, item.line) for item in raw_findings}
    deduped_external = [
        item for item in external_findings if (item.path, item.line) not in builtin_sites
    ]
    raw_findings.extend(deduped_external)

    classified = classify(raw_findings, documents, allowlist, codeblock_soft=args.codeblock_soft)
    outcome.findings = classified.findings
    outcome.placeholders = classified.placeholders
    outcome.exemptions = classified.exemptions
    outcome.info_findings = classified.info_findings

    payload = build_payload(outcome, allowlist)
    text_report = render_text(outcome, allowlist)

    if args.format == "json":
        output = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    else:
        output = (
            "=" * 72
            + "\n敏感信息扫描报告\n"
            + "=" * 72
            + "\n"
            + "目标：{0}\n时间：{1}\n".format(to_posix(repo_root), utc_timestamp())
            + "-" * 72
            + "\n"
            + text_report
        )

    if args.out:
        write_text_utf8(Path(args.out), output)
        print("报告已写入：{0}".format(to_posix(Path(args.out))))
        if not args.quiet:
            print(text_report)
    elif args.quiet:
        print("判定：{0}".format("通过" if payload["exit_code"] == 0 else "未通过"))
    else:
        print(output)

    return int(payload["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
