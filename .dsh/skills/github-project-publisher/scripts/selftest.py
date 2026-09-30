"""零依赖自检：用普通函数列表跑测试，不依赖 pytest 或任何第三方包。

为什么自己写 runner
--------------------
这些脚本的运行环境可能是"裸机上的一个 Python 解释器"——没有网络、不允许
``pip install``。如果自检依赖 pytest，那么最需要它的时候（离线、受限环境）
它恰好不可用。因此 runner 只用标准库，几十行就够。

约定
----
* 每个测试函数只接收一个 ``sandbox`` 路径参数；
* ``sandbox`` 是每次调用独占的临时目录，测试之间互不影响；
* **绝不触碰真实仓库状态**：不写入工作区、不改 git 配置、不创建提交；
* 需要 git 的测试在 sandbox 里 ``git init`` 一个全新仓库。

用法::

    python selftest.py
    python selftest.py --verbose
    python selftest.py --only mask
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import _common  # noqa: E402
import audit_repo  # noqa: E402
import check_identity  # noqa: E402
import make_checksums  # noqa: E402
import scan_secrets  # noqa: E402

_common.configure_stdio()

# 自检工作目录名（回退策略使用）。
WORK_DIR_NAME = ".selftest-work"

# TemporaryDirectory 句柄：需要在 finally 里显式清理，故在模块级持有。
_TEMP_HOLDERS: List[tempfile.TemporaryDirectory] = []


# ---------------------------------------------------------------------------
# 极简测试框架
# ---------------------------------------------------------------------------


class CheckFailure(AssertionError):
    """断言失败。与普通异常区分开，便于输出更干净的提示。"""


def check(condition: bool, message: str = "断言失败") -> None:
    if not condition:
        raise CheckFailure(message)


def check_eq(actual, expected, message: str = "") -> None:
    if actual != expected:
        raise CheckFailure(
            "{0}期望 {1!r}，实际 {2!r}".format(message + "：" if message else "", expected, actual)
        )


def check_in(needle: str, haystack: str, message: str = "") -> None:
    if needle not in haystack:
        raise CheckFailure(
            "{0}期望包含 {1!r}".format(message + "：" if message else "", needle)
        )


TEST_FUNCTIONS: List[Tuple[str, Callable[[Path], None]]] = []


def test(func: Callable[[Path], None]) -> Callable[[Path], None]:
    """把函数登记为测试用例。"""
    TEST_FUNCTIONS.append((func.__name__, func))
    return func


class _QuietStream(io.StringIO):
    """可被 ``reconfigure`` 调用的字符串流，避免 configure_stdio 抛错。"""

    def reconfigure(self, **_kwargs) -> None:  # noqa: D401
        return None


def capture_output(func: Callable[[], object]) -> Tuple[object, str, str]:
    """执行 func，返回 ``(返回值, stdout, stderr)``。"""
    out, err = _QuietStream(), _QuietStream()
    with redirect_stdout(out), redirect_stderr(err):
        result = func()
    return result, out.getvalue(), err.getvalue()


def git(args: Sequence[str], cwd: Path, identity: Optional[Tuple[str, str]] = None) -> Tuple[int, str]:
    """在 sandbox 内执行 git，返回 ``(returncode, 输出)``。

    identity 为 ``(name, email)`` 时，通过 ``-c user.name/-c user.email`` 传递提交身份。
    这一点很关键：**不能**用 ``GIT_AUTHOR_EMAIL`` / ``GIT_COMMITTER_EMAIL`` 环境变量，
    因为它们的优先级高于仓库级的 ``user.email``，会把"仓库身份是真实邮箱"这一
    待测条件直接抹掉（测试会假通过）。
    """
    env = dict(os.environ)
    # 清掉可能来自外部环境的身份变量，避免污染被测行为。
    for key in (
        "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL",
        "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM",
    ):
        env.pop(key, None)
    command = ["git"]
    config_args = ["-c", "core.autocrlf=false", "-c", "commit.gpgsign=false"]
    if identity is not None:
        config_args.extend(["-c", "user.name={0}".format(identity[0])])
        config_args.extend(["-c", "user.email={0}".format(identity[1])])
    command.extend(config_args)
    command.extend(args)
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
    )
    return completed.returncode, completed.stdout.decode("utf-8", errors="replace")


def commit_as(repo: Path, filename: str, content: str, message: str, identity: Tuple[str, str]) -> None:
    """用指定身份新增一个文件并提交（用于构造历史身份信息）。"""
    write_text(repo / filename, content)
    code, out = git(["add", filename], repo)
    check_eq(code, 0, "git add 应当成功：{0}".format(out))
    code, out = git(["commit", "-qm", message], repo, identity=identity)
    check_eq(code, 0, "git commit 应当成功：{0}".format(out))


def run_script(
    script: Path,
    argv: Sequence[str],
    cwd: Path,
) -> Tuple[int, str]:
    """在独立进程里运行某个脚本（用于退出码等只能进程级观察的行为）。"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    for key in (
        "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL",
        "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL",
    ):
        env.pop(key, None)
    completed = subprocess.run(
        [sys.executable, str(script)] + list(argv),
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
    )
    return completed.returncode, completed.stdout.decode("utf-8", errors="replace")


def write_text(path: Path, text: str) -> None:
    """测试用写文件：一律 LF，避免平台差异导致断言漂移。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def scan_lines(lines: Sequence[str], path: str = "sample.txt") -> List[_common.Finding]:
    """把若干行当作一个文档送进内置规则引擎。"""
    document = scan_secrets.Document(path, list(lines))
    return scan_secrets.scan_document(document)


def scan_lines_with_documents(
    lines: Sequence[str], path: str = "sample.txt"
) -> Tuple[List[_common.Finding], List[scan_secrets.Document]]:
    """同 scan_lines，但一并返回文档，供 classify 回查原文。

    classify 的占位符判定必须拿到**原文**：发现项携带的证据已经脱敏，
    拿掩码值（如 ``AKIA…(20)``）去比对占位符清单永远匹配不上，
    占位符就会被误报成 BLOCKER。生产路径始终传入 documents，
    因此单元测试也必须传入，否则测的不是真实行为。
    """
    document = scan_secrets.Document(path, list(lines))
    return scan_secrets.scan_document(document), [document]


def rules_hit(lines: Sequence[str], path: str = "sample.txt") -> List[str]:
    return [item.rule_id for item in scan_lines(lines, path)]


def scan_temp_file(sandbox: Path, name: str, text: str) -> List[_common.Finding]:
    """写入 sandbox 里的文件并扫描它（走真实的读文件路径）。"""
    target = sandbox / name
    write_text(target, text)
    document = scan_secrets._read_document(target, sandbox)
    check(document is not None, "文档应当可读：{0}".format(name))
    return scan_secrets.scan_document(document)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 校验算法
# ---------------------------------------------------------------------------


@test
def test_luhn_accepts_valid_card_numbers(sandbox: Path) -> None:
    for number in (
        "4111111111111111",  # Visa 测试号
        "5500005555555559",  # Mastercard 测试号
        "378282246310005",  # Amex 测试号
        "6011111111111117",  # Discover 测试号
    ):
        check(scan_secrets.luhn_ok(number), "Luhn 应接受 {0}".format(number))


@test
def test_luhn_rejects_invalid_card_numbers(sandbox: Path) -> None:
    for number in (
        "4111111111111112",
        "1234567890123456",
        "5500005555555550",
        "0000000000000001",
    ):
        check(not scan_secrets.luhn_ok(number), "Luhn 应拒绝 {0}".format(number))
    check(not scan_secrets.luhn_ok("4111-1111"), "非纯数字应被拒绝")


@test
def test_iban_mod97_validation(sandbox: Path) -> None:
    check(scan_secrets.iban_ok("GB82 WEST 1234 5698 7654 32"), "应接受合法 IBAN")
    check(scan_secrets.iban_ok("DE89370400440532013000"), "应接受合法 IBAN")
    check(not scan_secrets.iban_ok("GB82 WEST 1234 5698 7654 33"), "应拒绝校验位错误的 IBAN")


@test
def test_cn_id_checksum_validation(sandbox: Path) -> None:
    # 11 个合法样本（校验位按 GB 11643 计算）
    check(scan_secrets.cn_id_ok("11010519491231002X"), "应接受合法身份证号")
    check(not scan_secrets.cn_id_ok("110105194912310021"), "应拒绝校验位错误的身份证号")
    check(not scan_secrets.cn_id_ok("11010519491331002X"), "应拒绝月份非法的身份证号")


@test
def test_shannon_entropy_separates_random_from_words(sandbox: Path) -> None:
    random_like = "a8Fj2Lq9Zx7Bv3Nw5Rt1Yc6Md0Pe4Gh2"
    words = "your_api_key_here"
    check(
        scan_secrets.shannon_entropy(random_like) > scan_secrets.shannon_entropy(words),
        "随机串的熵应高于占位词",
    )
    check(scan_secrets.shannon_entropy("") == 0.0, "空串熵为 0")


# ---------------------------------------------------------------------------
# 脱敏
# ---------------------------------------------------------------------------


@test
def test_masking_never_reveals_more_than_four_leading_chars(sandbox: Path) -> None:
    secret = "AKIAZZ7XQ2VKLM4NPQRS"
    masked = _common.mask_evidence(secret)
    check(not masked.startswith(secret), "脱敏结果不得包含完整密钥")
    check(secret not in masked, "脱敏结果不得包含完整密钥")
    leading = masked.split("\u2026")[0]
    check(len(leading) <= 4, "最多保留 4 个前导字符，实际 {0}".format(len(leading)))
    check_in("(20)", masked, "应附带总长度")
    check_eq(masked, "AKIA\u2026(20)", "掩码格式应为 AKIA…(20)")


@test
def test_masking_handles_short_values(sandbox: Path) -> None:
    check_eq(_common.mask_evidence("abc"), "abc\u2026(3)")
    check_eq(_common.mask_evidence(""), "")
    check_eq(_common.truncate_head("abcdefgh", 2), "ab\u2026(8)")


@test
def test_masking_email_hides_local_part(sandbox: Path) -> None:
    masked = _common.mask_evidence("real.person@163.com")
    check(not masked.startswith("real"), "邮箱本地部分不得出现")
    check("163.com" not in masked, "个人邮箱域名默认不得出现")
    check(masked.startswith("***@"), "邮箱应脱敏为 ***@…")

    example = _common.mask_email("someone@example.com")
    check_eq(example, "***@example.com", "文档示例域名可以保留")

    noreply = _common.mask_email("149449562+cicada478@users.noreply.github.com")
    check("cicada478" not in noreply, "noreply 用户名不得出现")
    check_eq(noreply, "***@users.noreply.github.com")


@test
def test_masking_credential_url_hides_user_and_password(sandbox: Path) -> None:
    masked = _common.mask_evidence("postgres://app_user:s3cr3t-p4ss@db.internal:5432/prod")
    check("app_user" not in masked, "连接串用户名不得出现")
    check("s3cr3t" not in masked, "连接串口令不得出现")
    check(masked.startswith("postgres://"), "应保留协议以便定位")
    check_in("***:***@", masked, "用户名与口令都应被替换")


# ---------------------------------------------------------------------------
# 占位符自动降级
# ---------------------------------------------------------------------------


@test
def test_placeholder_detection_covers_documented_forms(sandbox: Path) -> None:
    placeholders = (
        "AKIAIOSFODNN7EXAMPLE",
        "12345678+username@users.noreply.github.com",
        "email@example.com",
        "someone@example.org",
        "your_api_key_here",
        "your-token-value",
        "xxxxxxxxxxxx",
        "XXXXXXXX",
        "REPLACE_WITH_PLACEHOLDER",
        "changeme",
        "redacted-value",
        "<YOUR_API_KEY>",
        "<token>",
        "mysql://user:pass@",
        "postgres://user:password@localhost:5432/db",
    )
    for value in placeholders:
        hit, marker = _common.is_placeholder(value)
        check(hit, "应识别为占位符：{0}".format(value))
        check(bool(marker), "应给出命中标记：{0}".format(value))


@test
def test_placeholder_detection_does_not_swallow_real_values(sandbox: Path) -> None:
    real_values = (
        "AKIAZZ7XQ2VKLM4NPQRS",
        "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8",
        "alice@realcompany.cn",
        "mysql://app_user:s3cr3t@db.internal/prod",
        "a8Fj2Lq9Zx7Bv3Nw5Rt1Yc6Md0Pe4Gh2",
    )
    for value in real_values:
        hit, _marker = _common.is_placeholder(value)
        check(not hit, "真实值不应被当成占位符：{0}".format(value))


@test
def test_placeholder_hits_are_downgraded_not_reported(sandbox: Path) -> None:
    findings, documents = scan_lines_with_documents(
        [
            "示例密钥：AKIAIOSFODNN7EXAMPLE",
            "示例邮箱：someone@example.com",
            "配置模板：api_key = \"<YOUR_API_KEY>\"",
            "文档示例：git config user.email \"12345678+username@users.noreply.github.com\"",
        ]
    )
    check(len(findings) > 0, "占位符应当先被规则命中，再降级")
    outcome = scan_secrets.classify(findings, documents, None)
    check_eq(len(outcome.findings), 0, "占位符不得进入发现项")
    check(len(outcome.placeholders) == len(findings), "全部命中都应记入占位符降级")
    for record in outcome.placeholders:
        check(bool(record["marker"]), "占位符记录应带有命中标记")
        check(bool(record["evidence_masked"]), "占位符记录也必须是脱敏值")


@test
def test_real_secret_is_not_downgraded(sandbox: Path) -> None:
    findings = scan_lines(['api_key = "a8Fj2Lq9Zx7Bv3Nw5Rt1Yc6Md0Pe4Gh2"'])
    outcome = scan_secrets.classify(findings, [], None)
    check(len(outcome.findings) >= 1, "真密钥必须留在发现项里")
    check_eq(outcome.findings[0].severity, "BLOCKER", "真密钥应为 BLOCKER")
    check_eq(len(outcome.placeholders), 0, "真密钥不应被降级")


# ---------------------------------------------------------------------------
# 内置规则集：正样本必须命中
# ---------------------------------------------------------------------------


@test
def test_sec001_detects_api_keys_and_tokens(sandbox: Path) -> None:
    samples = {
        "aws": 'AWS_ACCESS_KEY_ID = "AKIAZZ7XQ2VKLM4NPQRS"',
        "github": 'token = "ghp_' + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8" + '"',
        "slack": 'slack = "xoxb-1234567890-abcdefghijkl"',
        "google": 'key = "AIza' + "SyD9aBcDeFgHiJkLmNoPqRsTuVwXyZ01234" + '"',
        "stripe": 'stripe = "sk_live_' + "abcdefghijklmnopqrstuvwx" + '"',
        "openai": 'openai = "sk-' + "abcdefghijklmnopqrstuvwx" + '"',
        "azure": "AccountKey=abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGH==",
        "generic": 'api_key = "a8Fj2Lq9Zx7Bv3Nw5Rt1Yc6Md0Pe4Gh2"',
    }
    for label, line in samples.items():
        check_in("SEC-001", rules_hit([line]), "{0} 样本应当命中 SEC-001".format(label))


@test
def test_sec001_ignores_low_entropy_placeholders(sandbox: Path) -> None:
    # 均为占位/变量名写法：要么熵不足，要么被占位符机制接管。
    for line in (
        'api_key = "your_api_key_here"',
        'secret = "changeme"',
        'token = "xxxxxxxxxxxxxxxx"',
        "api_key = os.environ['API_KEY']",
        "token = get_token()",
    ):
        for finding in scan_lines([line]):
            original = line
            check(
                not (
                    finding.rule_id == "SEC-001"
                    and not _common.is_placeholder(original)[0]
                ),
                "低熵占位写法不应报 SEC-001：{0}".format(line),
            )


@test
def test_sec002_detects_private_keys(sandbox: Path) -> None:
    hits = rules_hit(
        [
            "-----BEGIN RSA PRIVATE KEY-----",
            "-----BEGIN OPENSSH PRIVATE KEY-----",
            "-----BEGIN PRIVATE KEY-----",
        ]
    )
    check_eq(hits.count("SEC-002"), 3, "三种私钥头都应命中 SEC-002")


@test
def test_sec003_detects_passwords(sandbox: Path) -> None:
    hits = rules_hit(
        [
            'password = "Sup3rS3cret!"',
            "passwd: 'hunter2x9'",
            'pwd = "Tr0ub4dor&3"',
        ]
    )
    check(hits.count("SEC-003") >= 3, "口令赋值应命中 SEC-003，实际 {0}".format(hits))


@test
def test_sec003_ignores_env_lookup_and_short_values(sandbox: Path) -> None:
    for line in (
        "password = os.environ['DB_PASSWORD']",
        "password = None",
        'password = ""',
        "password = getpass()",
    ):
        check("SEC-003" not in rules_hit([line]), "不应命中 SEC-003：{0}".format(line))


@test
def test_sec004_detects_connection_strings(sandbox: Path) -> None:
    for line in (
        "DATABASE_URL=postgresql://app_user:s3cr3t@db.internal:5432/prod",
        "url = 'mysql://root:hunter2@127.0.0.1/app'",
        "mongo = \"mongodb://admin:p4ssw0rd@cluster0.example.net/db\"",
        "cache = redis://default:r3d1s@cache.internal:6379",
    ):
        check("SEC-004" in rules_hit([line]), "应命中 SEC-004：{0}".format(line))


@test
def test_sec004_ignores_connection_strings_without_credentials(sandbox: Path) -> None:
    for line in (
        "url = 'postgresql://db.internal:5432/prod'",
        "redis://cache.internal:6379/0",
        "mongodb://cluster0.example.net/db",
    ):
        check("SEC-004" not in rules_hit([line]), "不应命中 SEC-004：{0}".format(line))


@test
def test_sec005_detects_payment_credentials(sandbox: Path) -> None:
    hits = rules_hit(
        [
            "card = 4111 1111 1111 1111",
            "pan=5500005555555559",
            "iban = GB82 WEST 1234 5698 7654 32",
        ]
    )
    check("SEC-005" in hits, "支付类凭据应命中 SEC-005，实际 {0}".format(hits))


@test
def test_sec005_ignores_random_digit_runs(sandbox: Path) -> None:
    for line in (
        "order_id = 1234567890123456",
        "trace = 9999999999999999",
        "build = 2026092912345678",
    ):
        check("SEC-005" not in rules_hit([line]), "不应命中 SEC-005：{0}".format(line))


@test
def test_sec006_detects_personal_information(sandbox: Path) -> None:
    check("SEC-006" in rules_hit(["联系人 alice@realcompany.cn"]), "邮箱应命中 SEC-006")
    check(
        "SEC-006" in rules_hit(["身份证 11010519491231002X"]),
        "合法身份证号应命中 SEC-006",
    )
    check("SEC-006" in rules_hit(["手机：13800138000"]), "带标签的手机号应命中 SEC-006")


@test
def test_sec006_ignores_invalid_ids_and_unlabelled_digits(sandbox: Path) -> None:
    for line in (
        "version = 20260929123456789",
        "checksum 110105194912310021",  # 校验位错误
        "reference 13800138000123",
    ):
        check("SEC-006" not in rules_hit([line]), "不应命中 SEC-006：{0}".format(line))


@test
def test_sec007_detects_credential_files(sandbox: Path) -> None:
    findings = scan_temp_file(
        sandbox,
        ".aws/credentials",
        "[default]\naws_access_key_id = AKIAZZ7XQ2VKLM4NPQRS\n"
        "aws_secret_access_key = wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY\n",
    )
    check(any(item.rule_id == "SEC-007" for item in findings), "AWS 凭据文件应命中 SEC-007")

    npmrc = scan_temp_file(sandbox, "sub/.npmrc", "//registry.npmjs.org/:_authToken=npm_aBcDeFgHiJkLmNoPqRsTuVwXyZ012345\n")
    check(any(item.rule_id == "SEC-007" for item in npmrc), ".npmrc 的 _authToken 应命中 SEC-007")

    service_account = scan_temp_file(
        sandbox,
        "sa.json",
        '{\n  "type": "service_account",\n  "private_key": "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC"\n}\n',
    )
    check(
        any(item.rule_id in ("SEC-007", "SEC-002") for item in service_account),
        "服务账号 JSON 的 private_key 应被检出",
    )


@test
def test_sec008_detects_secrets_written_to_logs(sandbox: Path) -> None:
    for line in (
        'logger.info("[INFO] api_key = \\"a8Fj2Lq9Zx7Bv3Nw5Rt1Yc6Md0Pe4Gh2\\"")',
        "INFO token = ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8",
        'ERROR password = "Sup3rS3cret!"',
    ):
        check("SEC-008" in rules_hit([line]), "日志中的敏感值应命中 SEC-008：{0}".format(line))


@test
def test_sec008_ignores_ordinary_log_lines(sandbox: Path) -> None:
    for line in (
        '[INFO] server started on port 8080',
        'logger.info("user logged in")',
        "[WARN] retrying request in 5s",
    ):
        check("SEC-008" not in rules_hit([line]), "普通日志不应命中 SEC-008：{0}".format(line))


@test
def test_sec009_detects_jwt_shaped_tokens(sandbox: Path) -> None:
    token = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        ".eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIn0"
        ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    check("SEC-009" in rules_hit(["Authorization: Bearer " + token]), "JWT 应命中 SEC-009")


@test
def test_sec009_ignores_base64_lookalikes(sandbox: Path) -> None:
    for line in (
        "https://example.com/eyJhbGciOiJIUzI1NiJ9",
        "value = eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0",
        "data = ALKVJFLKJDLKJFDLKJFLKJDLKFJLDKJFDLKJFLK",
    ):
        check("SEC-009" not in rules_hit([line]), "不应命中 SEC-009：{0}".format(line))


@test
def test_base64_ish_lookalikes_do_not_reach_blocker(sandbox: Path) -> None:
    # 长 base64 串容易被误判；这里确认它不会直接变成 BLOCKER 发现项。
    blob = "TWFuIGlzIGRpc3Rpbmd1aXNoZWQsIG5vdCBvbmx5IGJ5IGhpcyByZWFzb24="
    findings = scan_lines(["payload = \"{0}\"".format(blob)])
    outcome = scan_secrets.classify(findings, [], None)
    for item in outcome.findings:
        check("base64" not in item.message.lower(), "不应把 base64 串当作密钥")


# ---------------------------------------------------------------------------
# 豁免清单
# ---------------------------------------------------------------------------


@test
def test_allowlist_accepts_valid_entry_with_reason(sandbox: Path) -> None:
    parsed = _common.parse_allowlist_text(
        "# 敏感信息扫描豁免清单\n"
        "SEC-001  .dsh/skills/*/references/*.md  *  -- 文档示例中的占位密钥\n"
    )
    check_eq(len(parsed.invalid), 0, "合法条目不应被判为无效")
    check_eq(len(parsed.rules), 1, "应解析出 1 条规则")
    rule = parsed.rules[0]
    check_eq(rule.rule_id, "SEC-001")
    check_eq(rule.line, "*")
    check_eq(rule.reason, "文档示例中的占位密钥")


@test
def test_allowlist_accepts_exact_line_number(sandbox: Path) -> None:
    parsed = _common.parse_allowlist_text("SEC-006  README.md  42  -- 示例邮箱\n")
    check_eq(len(parsed.rules), 1)
    check(parsed.lookup("SEC-006", "README.md", 42) is not None, "第 42 行应命中")
    check(parsed.lookup("SEC-006", "README.md", 43) is None, "第 43 行不应命中")


@test
def test_allowlist_rejects_entry_without_reason(sandbox: Path) -> None:
    parsed = _common.parse_allowlist_text(
        "# 这是一个普通注释，不能充当理由\n"
        "SEC-001  docs/*.md  *\n"
    )
    check_eq(len(parsed.rules), 0, "缺理由的条目不得生效")
    check_eq(len(parsed.invalid), 1, "缺理由的条目必须被报告")
    check_in("缺少理由", parsed.invalid[0].reason, "应说明缺理由")


@test
def test_allowlist_reason_prefix_comment_is_accepted(sandbox: Path) -> None:
    parsed = _common.parse_allowlist_text(
        "# reason: 该文件是文档示例集合\n"
        "SEC-001  docs/*.md  *\n"
    )
    check_eq(len(parsed.rules), 1, "显式 # reason: 注释可作为理由")
    check_eq(parsed.rules[0].reason, "该文件是文档示例集合")


@test
def test_allowlist_rejects_malformed_entries(sandbox: Path) -> None:
    parsed = _common.parse_allowlist_text(
        "SEC-001  docs/*.md\n"  # 字段不足
        "BOGUS-999  docs/*.md  *  -- 规则编号非法\n"
        "SEC-002  docs/*.md  abc  -- 行号非法\n"
    )
    check_eq(len(parsed.rules), 0, "非法条目都不应生效")
    check_eq(len(parsed.invalid), 3, "三条非法条目都应被报告")


@test
def test_allowlist_glob_matching(sandbox: Path) -> None:
    parsed = _common.parse_allowlist_text(
        "SEC-001  .dsh/skills/*/references/*.md  *  -- 文档示例\n"
    )
    rule = parsed.rules[0]
    check(
        rule.matches("SEC-001", ".dsh/skills/github-project-publisher/references/checks.md", 12),
        "glob 应匹配 references 下的文档",
    )
    check(not rule.matches("SEC-001", "src/config.py", 1), "glob 不应匹配源码")
    check(not rule.matches("SEC-002", ".dsh/skills/x/references/a.md", 1), "规则编号必须精确匹配")


@test
def test_allowlist_exemption_is_applied_and_traced(sandbox: Path) -> None:
    entries = _common.parse_allowlist_text(
        "SEC-006  docs/sample.md  *  -- 文档中刻意公开的联系邮箱\n"
    )
    findings = scan_lines(["联系邮箱 alice@realcompany.cn"], path="docs/sample.md")
    outcome = scan_secrets.classify(findings, [], entries)
    check_eq(len(outcome.findings), 0, "被豁免的命中不应进入发现项")
    check_eq(len(outcome.exemptions), 1, "豁免必须留下记录")
    record = outcome.exemptions[0]
    check_eq(record["rule_id"], "SEC-006")
    check_eq(record["reason"], "文档中刻意公开的联系邮箱")
    check(bool(record["matched_glob"]), "记录应包含匹配到的通配式")


@test
def test_load_allowlist_from_project_root(sandbox: Path) -> None:
    write_text(
        sandbox / _common.ALLOWLIST_RELPATH,
        "# 说明\nSEC-006  README.md  *  -- 示例邮箱\n",
    )
    loaded = _common.load_allowlist(sandbox)
    check(loaded.loaded, "清单应被识别为已加载")
    check_eq(len(loaded.rules), 1)
    missing = _common.load_allowlist(sandbox / "nowhere")
    check(not missing.loaded, "缺失清单应标记为未加载")
    check_eq(len(missing.rules), 0)


@test
def test_codeblock_soft_downgrades_but_still_reports(sandbox: Path) -> None:
    document = scan_secrets.Document(
        "docs/guide.md",
        [
            "正文里的真密钥：",
            'key = "AKIAZZ7XQ2VKLM4NPQRS"',
            "```python",
            'api_key = "AKIAZZ7XQ2VKLM4NPQRS"',
            "```",
        ],
    )
    findings = scan_secrets.scan_document(document)
    strict = scan_secrets.classify(findings, [document], None, codeblock_soft=False)
    check(
        all(item.severity == "BLOCKER" for item in strict.findings),
        "默认状态下代码块内外都应是 BLOCKER",
    )
    check_eq(len(strict.findings), 2, "默认状态应报告正文与代码块两处")

    soft = scan_secrets.classify(findings, [document], None, codeblock_soft=True)
    inside = [item for item in soft.findings if item.line == 4]
    outside = [item for item in soft.findings if item.line == 2]
    check_eq(len(inside), 1, "--codeblock-soft 仍必须报告代码块内的命中")
    check_eq(inside[0].severity, "MAJOR", "代码块内的命中应降为 MAJOR")
    check_eq(outside[0].severity, "BLOCKER", "代码块外的命中不得被软化")


@test
def test_self_scan_hits_are_classified_separately(sandbox: Path) -> None:
    check(
        _common.is_self_scan_hit("SEC-002", ".dsh/skills/x/scripts/_common.py"),
        "扫描器源码里的规则字面量应被识别为自扫描命中",
    )
    check(
        not _common.is_self_scan_hit("SEC-002", "src/config.py"),
        "普通文件不得被当成自扫描命中",
    )
    check(
        not _common.is_self_scan_hit("META-001", "_common.py"),
        "非 SEC 规则不参与自扫描归类",
    )


# ---------------------------------------------------------------------------
# 校验和
# ---------------------------------------------------------------------------


@test
def test_checksum_round_trip_and_tamper_detection(sandbox: Path) -> None:
    write_text(sandbox / "dist" / "app.zip", "release-artifact-bytes\n")
    write_text(sandbox / "dist" / "notes.txt", "release notes\n")

    text, count, _skipped = make_checksums.build_sums(
        [sandbox / "dist"], relative_to=sandbox / "dist"
    )
    check_eq(count, 2, "应生成两条摘要")
    sums = sandbox / "dist" / "SHA256SUMS"
    _common.write_text_utf8(sums, text)

    result = make_checksums.verify_sums_file(sums)
    check(result.ok, "刚生成的校验和应当全部匹配：{0}".format(result.summary()))
    check_eq(result.matched, 2)

    # 篡改后必须失败
    write_text(sandbox / "dist" / "app.zip", "tampered-bytes\n")
    tampered = make_checksums.verify_sums_file(sums)
    check(not tampered.ok, "篡改后校验必须失败")
    check_in("app.zip", " ".join(tampered.mismatched), "应报告不匹配的具体文件")

    # 缺失文件同样必须失败
    (sandbox / "dist" / "notes.txt").unlink()
    missing = make_checksums.verify_sums_file(sums)
    check(not missing.ok, "文件缺失时校验必须失败")
    check_in("notes.txt", " ".join(missing.missing), "应报告缺失的具体文件")


@test
def test_checksum_file_has_no_bom_and_no_crlf(sandbox: Path) -> None:
    write_text(sandbox / "dist" / "a.bin", "aaa\n")
    text, _count, _skipped = make_checksums.build_sums(
        [sandbox / "dist"], relative_to=sandbox / "dist"
    )
    target = sandbox / "SHA256SUMS"
    _common.write_text_utf8(target, text)
    raw = target.read_bytes()
    check(not raw.startswith(b"\xef\xbb\xbf"), "SHA256SUMS 不得带 BOM")
    check(b"\r" not in raw, "SHA256SUMS 不得包含 CR")
    check(raw.endswith(b"\n"), "应以 LF 结尾")


@test
def test_checksum_format_is_coreutils_compatible(sandbox: Path) -> None:
    write_text(sandbox / "dist" / "b.bin", "bbb\n")
    write_text(sandbox / "dist" / "a.bin", "aaa\n")
    text, _count, _skipped = make_checksums.build_sums(
        [sandbox / "dist"], relative_to=sandbox / "dist"
    )
    data_lines = [line for line in text.split("\n") if line and not line.startswith("#")]
    check_eq(len(data_lines), 2, "应有两行数据")
    check_eq(data_lines[0].split("  ")[1], "a.bin", "路径应按字典序排序")
    check_eq(data_lines[1].split("  ")[1], "b.bin", "路径应按字典序排序")
    for line in data_lines:
        digest, _sep, path = line.partition("  ")
        check_eq(len(digest), 64, "sha256 摘要应为 64 个十六进制字符")
        check(digest == digest.lower(), "摘要必须是小写十六进制")
        check("\\" not in path, "路径必须使用正斜杠")
        check("\t" not in line, "分隔符必须是两个空格，不能用制表符")


@test
def test_checksum_sha512_and_algo_label(sandbox: Path) -> None:
    write_text(sandbox / "dist" / "a.bin", "aaa\n")
    text, _count, _skipped = make_checksums.build_sums(
        [sandbox / "dist"], algo="sha512", relative_to=sandbox / "dist",
        algo_label="SHA512-CUSTOM",
    )
    check_in("SHA512-CUSTOM", text, "注释行应使用自定义算法标签")
    data_lines = [line for line in text.split("\n") if line and not line.startswith("#")]
    check_eq(len(data_lines[0].split("  ")[0]), 128, "sha512 摘要应为 128 个字符")


@test
def test_checksum_exclude_and_relative_paths(sandbox: Path) -> None:
    write_text(sandbox / "dist" / "keep.bin", "keep\n")
    write_text(sandbox / "dist" / "skip.log", "skip\n")
    text, count, _skipped = make_checksums.build_sums(
        [sandbox / "dist"],
        relative_to=sandbox / "dist",
        excludes=["*.log"],
    )
    check_eq(count, 1, "被排除的文件不应进入校验和")
    check("skip.log" not in text, "排除项不得出现")
    check_in("  keep.bin", text, "应记录相对路径")


@test
def test_checksum_verify_detects_bom_and_crlf_in_existing_file(sandbox: Path) -> None:
    target = sandbox / "SHA256SUMS"
    with open(target, "wb") as handle:
        handle.write(
            b"\xef\xbb\xbf"
            + ("0" * 64).encode("ascii")
            + b"  a.bin\r\n"
        )
    result = make_checksums.verify_sums_file(target)
    problems = " ".join(result.malformed)
    check_in("BOM", problems, "应报告 BOM 问题")
    check_in("CRLF", problems, "应报告 CRLF 问题")


@test
def test_checksum_parse_accepts_bsd_and_star_formats(sandbox: Path) -> None:
    entries, malformed = make_checksums.parse_sums_text(
        "SHA256 (dist/a.bin) = {0}\n{0} *dist/b.bin\n".format("a" * 64)
    )
    check_eq(len(malformed), 0, "两种格式都应被接受")
    check_eq(len(entries), 2, "应解析出两条摘要")
    check_eq(entries[0][1], "dist/a.bin")


# ---------------------------------------------------------------------------
# 提交身份
# ---------------------------------------------------------------------------


@test
def test_noreply_pattern_accepts_and_rejects(sandbox: Path) -> None:
    check(
        check_identity.is_noreply("149449562+cicada478@users.noreply.github.com"),
        "带数字 ID 的隐私邮箱应通过",
    )
    check(
        check_identity.is_noreply("cicada478@users.noreply.github.com"),
        "不带数字 ID 的隐私邮箱也应通过",
    )
    check(not check_identity.is_noreply("someone@163.com"), "普通邮箱必须被拒绝")
    check(not check_identity.is_noreply("someone@gmail.com"), "个人邮箱必须被拒绝")
    check(
        not check_identity.is_noreply("someone@users.noreply.github.com.evil.com"),
        "伪造后缀必须被拒绝",
    )
    check(not check_identity.is_noreply(""), "空地址必须被拒绝")


@test
def test_build_noreply_derives_address(sandbox: Path) -> None:
    check_eq(
        check_identity.build_noreply("149449562", "cicada478"),
        "149449562+cicada478@users.noreply.github.com",
    )
    check_eq(
        check_identity.build_noreply("149449562", "@cicada478"),
        "149449562+cicada478@users.noreply.github.com",
    )
    check_eq(
        check_identity.build_noreply("", "cicada478"),
        "cicada478@users.noreply.github.com",
    )
    try:
        check_identity.build_noreply("149449562", "")
    except ValueError:
        pass
    else:
        raise CheckFailure("空用户名应抛出 ValueError")


@test
def test_check_identity_never_prints_an_address(sandbox: Path) -> None:
    private_address = "someone.real@163.com"
    noreply = "149449562+cicada478@users.noreply.github.com"
    code, _output = git(["init", "-q"], sandbox)
    check_eq(code, 0, "git init 应当成功")
    git(["config", "--local", "user.email", private_address], sandbox)
    git(["config", "--local", "user.name", "Real Person"], sandbox)
    write_text(sandbox / "a.txt", "hello\n")
    git(["add", "a.txt"], sandbox)
    code, output = git(["commit", "-qm", "chore: init"], sandbox)
    check_eq(code, 0, "测试提交应当成功：{0}".format(output))

    # 制造一条 noreply 提交，验证两种地址混合时仍然不泄露
    git(["config", "--local", "user.email", noreply], sandbox)
    write_text(sandbox / "b.txt", "world\n")
    git(["add", "b.txt"], sandbox)
    git(["commit", "-qm", "chore: 第二次提交"], sandbox)

    report, stdout, stderr = capture_output(
        lambda: check_identity.collect_identity(sandbox, all_refs=True)
    )
    # render_text 是**返回**字符串而不是打印（CLI 层才 print）。
    # 断言必须针对返回值；对 stdout 断言会得到恒真的空断言——
    # 看似有覆盖，实则零验证。
    text_report, rendered_stdout, _ = capture_output(
        lambda: check_identity.render_text(report, show_domain=False)
    )
    visible = stdout + stderr + rendered_stdout + str(text_report)
    check(private_address not in visible, "输出中不得出现真实地址")
    check("someone.real" not in visible, "输出中不得出现地址本地部分")
    check("163.com" not in visible, "输出中不得出现个人邮箱域名")
    check(noreply not in visible, "输出中不得出现 noreply 全地址")
    check("cicada478" not in visible, "输出中不得出现 noreply 用户名")
    check_eq(report["verdict"], "fail", "存在非隐私邮箱时应判定为不通过")
    # 同一次提交里 author 与 committer 是**两个字段**，却只是**一个地址**。
    # 两个数字都报告，信息量更大；此处断言必须区分二者。
    check_eq(report["non_noreply_entries"], 2, "author 与 committer 各计一条，共 2 条")
    check_eq(report["distinct_non_noreply"], 1, "去重后只有 1 个不同地址")
    check_in("未通过", str(text_report))
    check_in("***@", str(text_report), "应使用掩码表达命中")


@test
def test_check_identity_passes_on_all_noreply_history(sandbox: Path) -> None:
    git(["init", "-q"], sandbox)
    git(["config", "--local", "user.email", "149449562+cicada478@users.noreply.github.com"], sandbox)
    git(["config", "--local", "user.name", "cicada478"], sandbox)
    write_text(sandbox / "a.txt", "hello\n")
    git(["add", "a.txt"], sandbox)
    git(["commit", "-qm", "chore: init"], sandbox)

    report, stdout, _ = capture_output(lambda: check_identity.collect_identity(sandbox))
    text_report, rendered_stdout, _ = capture_output(
        lambda: check_identity.render_text(report, show_domain=False)
    )
    check_eq(report["verdict"], "pass", "全部为隐私邮箱时应通过")
    check_eq(report["non_noreply_entries"], 0)
    # collect_identity 同样返回而不打印，只查它的 stdout 是恒真的。
    # 必须连同渲染文本与结构化结果一起查，否则这条断言零覆盖。
    visible = (
        stdout
        + rendered_stdout
        + str(text_report)
        + json.dumps(report, ensure_ascii=False)
    )
    check("cicada478" not in visible, "通过时也不得回显地址")


@test
def test_check_identity_show_domain_still_hides_local_part(sandbox: Path) -> None:
    git(["init", "-q"], sandbox)
    git(["config", "--local", "user.email", "someone.real@company.example.org"], sandbox)
    git(["config", "--local", "user.name", "Real"], sandbox)
    write_text(sandbox / "a.txt", "x\n")
    git(["add", "a.txt"], sandbox)
    git(["commit", "-qm", "chore: init"], sandbox)

    report, _stdout, _stderr = capture_output(
        lambda: check_identity.collect_identity(sandbox, show_domain=True)
    )
    text_report, rendered_stdout, _ = capture_output(
        lambda: check_identity.render_text(report, show_domain=True)
    )
    # 断言针对 render_text 的返回值：--show-domain 只允许显示域名，
    # 本地部分必须始终被隐藏。
    visible = str(text_report) + rendered_stdout
    check("someone.real" not in visible, "即使 --show-domain，本地部分也不得出现")
    check_in("***@", visible)


@test
def test_identity_report_has_no_raw_address_fields(sandbox: Path) -> None:
    git(["init", "-q"], sandbox)
    git(["config", "--local", "user.email", "private.person@gmail.com"], sandbox)
    git(["config", "--local", "user.name", "P"], sandbox)
    write_text(sandbox / "a.txt", "x\n")
    git(["add", "a.txt"], sandbox)
    git(["commit", "-qm", "chore: init"], sandbox)
    report, _o, _e = capture_output(lambda: check_identity.collect_identity(sandbox))
    serialized = json.dumps(report, ensure_ascii=False)
    check("private.person" not in serialized, "结构化结果里也不得出现地址明文")
    check("gmail.com" not in serialized, "个人邮箱域名不得出现在结构化结果里")


# ---------------------------------------------------------------------------
# 聚合审计的静态检查
# ---------------------------------------------------------------------------


@test
def test_meta001_flags_missing_license(sandbox: Path) -> None:
    findings: List[_common.Finding] = []
    audit_repo.check_file_presence(sandbox, findings)
    by_rule = {item.rule_id: item for item in findings}
    check("META-001" in by_rule, "缺少 LICENSE 应报 META-001")
    check_eq(by_rule["META-001"].severity, "BLOCKER", "META-001 应为 BLOCKER")
    check("META-003" in by_rule, "缺少 README 应报 META-003")
    check_eq(by_rule["META-003"].severity, "MINOR")
    check("META-004" in by_rule, "缺少 .gitignore 应报 META-004")
    check("META-005" in by_rule, "缺少 .gitattributes 应报 META-005")
    check_eq(by_rule["META-005"].severity, "MAJOR", "META-005 应为 MAJOR")
    check("DOC-001" in by_rule, "缺少 CHANGELOG 应报 DOC-001")
    check("DOC-002" in by_rule, "缺少 SECURITY.md 应报 DOC-002")
    check("DOC-003" in by_rule, "缺少 CONTRIBUTING.md 应报 DOC-003")


@test
def test_meta_checks_are_silent_when_files_exist(sandbox: Path) -> None:
    write_text(sandbox / "LICENSE", "MIT License\n\nCopyright (c) 2026 tester\n")
    write_text(sandbox / "README.md", "# demo\n")
    write_text(sandbox / ".gitignore", "__pycache__/\n")
    write_text(sandbox / ".gitattributes", "* text=auto eol=lf\n")
    write_text(sandbox / "CHANGELOG.md", "# Changelog\n")
    write_text(sandbox / "SECURITY.md", "# Security\n")
    write_text(sandbox / "CONTRIBUTING.md", "# Contributing\n")
    findings: List[_common.Finding] = []
    present = audit_repo.check_file_presence(sandbox, findings)
    check_eq(findings, [], "文件齐全时不应有发现项")
    check(present["LICENSE"] is not None and present["README"] is not None)


@test
def test_meta002_detects_license_mismatch(sandbox: Path) -> None:
    write_text(sandbox / "LICENSE", "MIT License\n\nCopyright (c) 2026 tester\n")
    write_text(
        sandbox / "package.json",
        json.dumps({"name": "demo", "license": "Apache-2.0"}, ensure_ascii=False),
    )
    findings: List[_common.Finding] = []
    declared, file_license = audit_repo.check_license_consistency(
        sandbox, sandbox / "LICENSE", findings
    )
    check_eq(declared, "Apache-2.0")
    check_eq(file_license, "MIT")
    check_eq(len(findings), 1, "不一致应报一条")
    check_eq(findings[0].rule_id, "META-002")
    check_eq(findings[0].severity, "BLOCKER")


@test
def test_meta002_is_silent_when_consistent_or_absent(sandbox: Path) -> None:
    write_text(sandbox / "LICENSE", "MIT License\n\nPermission is hereby granted...\n")
    write_text(sandbox / "package.json", json.dumps({"license": "MIT"}))
    findings: List[_common.Finding] = []
    audit_repo.check_license_consistency(sandbox, sandbox / "LICENSE", findings)
    check_eq(findings, [], "一致时不应报错")

    empty = sandbox / "empty"
    empty.mkdir()
    findings2: List[_common.Finding] = []
    audit_repo.check_license_consistency(empty, None, findings2)
    check_eq(findings2, [], "没有清单也没有 LICENSE 时不应报 META-002")


@test
def test_meta006_flags_non_ascii_repository_name(sandbox: Path) -> None:
    findings: List[_common.Finding] = []
    original = audit_repo.repo_name_from_remote

    def fake_remote(_root: Path):
        return "项目-中文名", "test"

    audit_repo.repo_name_from_remote = fake_remote  # type: ignore[assignment]
    try:
        name, _source = audit_repo.check_repo_name(sandbox, findings)
    finally:
        audit_repo.repo_name_from_remote = original  # type: ignore[assignment]
    check_eq(name, "项目-中文名")
    check_eq(len(findings), 1)
    check_eq(findings[0].rule_id, "META-006")
    check_eq(findings[0].severity, "MAJOR")


@test
def test_meta006_accepts_ascii_name(sandbox: Path) -> None:
    findings: List[_common.Finding] = []
    original = audit_repo.repo_name_from_remote

    def fake_remote(_root: Path):
        return "my-project", "test"

    audit_repo.repo_name_from_remote = fake_remote  # type: ignore[assignment]
    try:
        audit_repo.check_repo_name(sandbox, findings)
    finally:
        audit_repo.repo_name_from_remote = original  # type: ignore[assignment]
    check_eq(findings, [], "纯 ASCII 仓库名不应报 META-006")


@test
def test_git005_flags_tracked_but_ignored_files(sandbox: Path) -> None:
    """GIT-005：.gitignore 对已跟踪文件无效——最常见的「假安全」。"""
    git(["init", "-q"], sandbox)
    git(
        ["config", "--local", "user.email",
         "149449562+cicada478@users.noreply.github.com"],
        sandbox,
    )
    git(["config", "--local", "user.name", "cicada478"], sandbox)

    write_text(sandbox / ".env", "API_KEY=dummy\n")
    git(["add", ".env"], sandbox)
    git(["commit", "-qm", "chore: add env"], sandbox)

    # 事后再把它写进 .gitignore：对**已被跟踪**的文件毫无作用
    write_text(sandbox / ".gitignore", ".env\n")
    git(["add", ".gitignore"], sandbox)
    git(["commit", "-qm", "chore: ignore env"], sandbox)

    findings: List[_common.Finding] = []
    paths, note = audit_repo.check_tracked_ignored(sandbox, findings)
    check_eq(note, "", "检查应当正常完成")
    check_eq(paths, [".env"], "应找出同时被跟踪且被忽略的文件")
    check_eq(len(findings), 1)
    check_eq(findings[0].rule_id, "GIT-005")
    check_eq(findings[0].severity, "MAJOR")
    check_eq(findings[0].path, ".env")
    check("git rm --cached" in findings[0].message, "应给出可执行的修复方式")


@test
def test_git005_silent_when_ignore_is_effective(sandbox: Path) -> None:
    """只被忽略、并未被跟踪的文件不应命中 GIT-005。"""
    git(["init", "-q"], sandbox)
    git(
        ["config", "--local", "user.email",
         "149449562+cicada478@users.noreply.github.com"],
        sandbox,
    )
    git(["config", "--local", "user.name", "cicada478"], sandbox)

    write_text(sandbox / ".gitignore", "*.log\n")
    write_text(sandbox / "app.log", "noise\n")
    write_text(sandbox / "keep.txt", "keep\n")
    git(["add", ".gitignore", "keep.txt"], sandbox)
    git(["commit", "-qm", "chore: init"], sandbox)

    findings: List[_common.Finding] = []
    paths, note = audit_repo.check_tracked_ignored(sandbox, findings)
    check_eq(note, "", "检查应当正常完成")
    check_eq(paths, [], "未被跟踪的忽略文件不应命中")
    check_eq(findings, [], "忽略规则生效时不应报 GIT-005")


@test
def test_git004_flags_large_objects_by_threshold(sandbox: Path) -> None:
    """GIT-004：按体积分档——超过硬上限为 MAJOR，仅超警告线为 MINOR。"""
    git(["init", "-q"], sandbox)
    git(
        ["config", "--local", "user.email",
         "149449562+cicada478@users.noreply.github.com"],
        sandbox,
    )
    git(["config", "--local", "user.name", "cicada478"], sandbox)

    # 注入很小的阈值，避免自测里真的造 50 MB 文件
    warn_bytes, limit_bytes = 1024, 4096
    with open(sandbox / "warn.bin", "wb") as handle:
        handle.write(b"\0" * 2048)      # 介于警告线与硬上限之间
    with open(sandbox / "over.bin", "wb") as handle:
        handle.write(b"\0" * 8192)      # 超过硬上限
    write_text(sandbox / "small.txt", "x\n")
    git(["add", "-A"], sandbox)
    git(["commit", "-qm", "chore: add files"], sandbox)

    findings: List[_common.Finding] = []
    entries, note = audit_repo.check_large_files(
        sandbox, findings, warn_bytes=warn_bytes, limit_bytes=limit_bytes
    )
    check_eq(note, "", "检查应当正常完成")
    check_eq(
        [name for _size, name in entries],
        ["over.bin", "warn.bin"],
        "应按体积降序，且只含超过警告线的对象",
    )
    by_path = {item.path: item for item in findings}
    check_eq(len(findings), 2)
    check_eq(by_path["over.bin"].rule_id, "GIT-004")
    check_eq(by_path["over.bin"].severity, "MAJOR", "超过硬上限应为 MAJOR")
    check_eq(by_path["warn.bin"].severity, "MINOR", "仅超警告线应为 MINOR")
    check("改写历史" in by_path["over.bin"].message, "应说明从 HEAD 删除无效")


@test
def test_git004_silent_without_large_objects(sandbox: Path) -> None:
    git(["init", "-q"], sandbox)
    git(
        ["config", "--local", "user.email",
         "149449562+cicada478@users.noreply.github.com"],
        sandbox,
    )
    git(["config", "--local", "user.name", "cicada478"], sandbox)
    write_text(sandbox / "a.txt", "small\n")
    git(["add", "-A"], sandbox)
    git(["commit", "-qm", "chore: init"], sandbox)

    findings: List[_common.Finding] = []
    entries, note = audit_repo.check_large_files(sandbox, findings)
    check_eq(note, "", "检查应当正常完成")
    check_eq(entries, [], "没有大对象时不应有命中")
    check_eq(findings, [], "不应报 GIT-004")


@test
def test_git004_handles_repository_without_commits(sandbox: Path) -> None:
    """尚无提交时 GIT-004 不应报错，也不应产生发现项。"""
    git(["init", "-q"], sandbox)
    findings: List[_common.Finding] = []
    entries, note = audit_repo.check_large_files(sandbox, findings)
    check_eq(note, "", "无提交不应视为失败")
    check_eq(entries, [])
    check_eq(findings, [])


@test
def test_rel001_flags_artifacts_without_checksum(sandbox: Path) -> None:
    write_text(sandbox / "dist" / "app.zip", "bytes\n")
    findings: List[_common.Finding] = []
    stats = audit_repo.check_release_artifacts(sandbox, findings)
    check_eq(stats["artifact_count"], 1, "应识别到 1 个发布产物")
    check_eq(len(findings), 1, "缺少摘要记录应报 REL-001")
    check_eq(findings[0].rule_id, "REL-001")
    check_eq(findings[0].severity, "INFO", "REL-001 应为 INFO")

    # 补上 SHA256SUMS 后应当安静
    _common.write_text_utf8(
        sandbox / "SHA256SUMS",
        "{0}  app.zip\n".format("a" * 64),
    )
    findings2: List[_common.Finding] = []
    stats2 = audit_repo.check_release_artifacts(sandbox, findings2)
    check_eq(stats2["unchecked"], [], "有摘要记录时不应再报")
    check_eq(findings2, [], "有摘要记录时不应有发现项")


@test
def test_python_version_guard(sandbox: Path) -> None:
    """版本守卫的判据本身要被验证。

    否则「解释器太旧」这条路径只能靠真去找一个旧解释器来覆盖，
    实际上等于没测——而它恰恰是使用者最容易撞上、也最容易被误判的一条：
    报错看起来像脚本有 bug，真实原因却是解释器不对。
    """
    check_eq(_common.MIN_PYTHON, (3, 9), "最低版本应声明为 3.9")
    for supported in ((3, 9), (3, 13), (3, 14), (4, 0)):
        check(
            _common.python_version_supported(supported),
            "Python {0}.{1} 应受支持".format(*supported),
        )
    for unsupported in ((2, 7), (3, 6), (3, 8)):
        check(
            not _common.python_version_supported(unsupported),
            "Python {0}.{1} 不应受支持".format(*unsupported),
        )
    # 当前解释器必须通过守卫，否则本次自检根本跑不起来
    check(_common.python_version_supported(), "当前解释器应满足最低版本要求")


@test
def test_history_placeholder_survives_line_shift(sandbox: Path) -> None:
    """回归：历史里的文档示例不因行号位移而被误报成 BLOCKER。

    同一路径在工作树、暂存区、历史里各有一份文档，而它们的行号**未必一致**——
    上游多插几行，后续行号就整体位移。占位符判定若一律回查工作树，就会拿
    错误的行去比对，把文档里的示例密钥报成 BLOCKER。

    这不是无害的噪音：假阳性正是杀死阻断机制的主要方式。告警被忽略几次之后，
    真正的命中也没人看了。

    本次缺陷之所以出现，是因为编排逻辑在 `scan_secrets.run_scan` 与
    `audit_repo._run_secret_scan` 里各有一份——只修一边就会漏掉另一边。
    因此这个用例走的是**审计那条路径**。
    """
    git(["init", "-q"], sandbox)
    git(
        ["config", "--local", "user.email",
         "149449562+cicada478@users.noreply.github.com"],
        sandbox,
    )
    git(["config", "--local", "user.name", "cicada478"], sandbox)

    write_text(sandbox / "doc.md", "line1\nline2\n示例：AKIAIOSFODNN7EXAMPLE\n")
    git(["add", "-A"], sandbox)
    git(["commit", "-qm", "chore: add doc"], sandbox)

    # 在占位符之前插入三行：历史里的行号与工作树从此错位
    write_text(
        sandbox / "doc.md",
        "new1\nnew2\nnew3\nline1\nline2\n示例：AKIAIOSFODNN7EXAMPLE\n",
    )
    git(["add", "-A"], sandbox)
    git(["commit", "-qm", "chore: shift lines"], sandbox)

    result = audit_repo.AuditResult()
    result.repo_root = sandbox
    options = audit_repo.build_parser().parse_args(["--repo", str(sandbox)])
    scan_result, _surfaces = audit_repo._run_secret_scan(result, options)

    # 先确认这条用例不是空过：没扫历史面的话，它就什么都没验证。
    check_in("提交历史", _surfaces, "必须真的扫了历史面，否则本用例形同虚设")

    blockers = [item for item in scan_result.findings if item.severity == "BLOCKER"]
    check_eq(
        blockers,
        [],
        "行号位移不应把历史里的占位符变成 BLOCKER：{0}".format(
            [item.format_line() for item in blockers]
        ),
    )
    check(
        len(scan_result.placeholders) >= 2,
        "工作树与历史两份都该被识别为占位符，实际 {0} 条".format(
            len(scan_result.placeholders)
        ),
    )


@test
def test_id001_detects_contradicting_stale_report(sandbox: Path) -> None:
    audit_dir = sandbox / _common.AUDIT_DIRNAME
    write_text(
        audit_dir / "report-19700101T000000Z.json",
        json.dumps({"counts": {"BLOCKER": 3}, "exit_code": 1}),
    )
    findings: List[_common.Finding] = []
    stats = audit_repo.check_stale_reports(sandbox, findings)
    check_eq(len(stats["inspected"]), 1, "应检查到 1 份历史报告")
    check_eq(len(stats["stale"]), 1, "应识别出结论矛盾的报告")
    check_eq(len(findings), 1, "应报 ID-001")
    check_eq(findings[0].rule_id, "ID-001")


@test
def test_id001_silent_without_stale_reports(sandbox: Path) -> None:
    findings: List[_common.Finding] = []
    stats = audit_repo.check_stale_reports(sandbox, findings)
    check_eq(findings, [], "没有报告目录时不应报 ID-001")
    check_eq(stats["inspected"], [])

    write_text(
        sandbox / _common.AUDIT_DIRNAME / "report-20260101T000000Z.json",
        json.dumps({"counts": {"BLOCKER": 0}, "exit_code": 0}),
    )
    findings2: List[_common.Finding] = []
    audit_repo.check_stale_reports(sandbox, findings2)
    check_eq(findings2, [], "结论一致的旧报告不应触发 ID-001")


@test
def test_rule_severity_table_is_consistent(sandbox: Path) -> None:
    expected = {
        "SEC-001": "BLOCKER", "SEC-008": "BLOCKER", "SEC-009": "BLOCKER",
        "GIT-001": "BLOCKER", "META-001": "BLOCKER", "META-002": "BLOCKER",
        # GIT-004 登记的是较低档（50~100 MB）；超过 100 MB 时由调用方覆盖为 MAJOR
        "GIT-004": "MINOR", "GIT-005": "MAJOR",
        "META-003": "MINOR", "META-004": "MINOR", "META-005": "MAJOR",
        "META-006": "MAJOR", "DOC-001": "MINOR", "DOC-002": "MINOR",
        "DOC-003": "MINOR", "REL-001": "INFO", "ID-001": "INFO",
    }
    for rule_id, severity in expected.items():
        check_eq(_common.rule_severity(rule_id), severity, "规则 {0} 的级别".format(rule_id))
    for rule_id in _common.RULE_SEVERITY:
        check(rule_id in _common.RULE_TITLES, "规则 {0} 缺少标题".format(rule_id))
        check_in(
            _common.RULE_SEVERITY[rule_id],
            _common.SEVERITIES,
            "规则 {0} 的级别必须是四档之一".format(rule_id),
        )


@test
def test_audit_report_renders_required_sections(sandbox: Path) -> None:
    result = audit_repo.AuditResult()
    result.repo_root = sandbox
    result.repo_name = "demo"
    result.repo_name_source = "test"
    result.tool_versions = ["python 3.13.5", "git 2.50"]
    result.engines = ["builtin"]
    result.surfaces = ["工作树"]
    result.limitations = ["示例限制"]
    result.placeholders = [{"rule_id": "SEC-001", "path": "a.md", "line": 1, "marker": "example.com"}]
    result.exemptions = [
        {"rule_id": "SEC-006", "path": "README.md", "line": 3,
         "matched_glob": "README.md", "reason": "示例邮箱", "allowlist_line": 5}
    ]
    result.findings.append(
        _common.make_finding("META-005", ".", 0, "缺少 .gitattributes", severity="MAJOR")
    )
    markdown = audit_repo.render_markdown(result, argparse.Namespace())
    for section in (
        "运行时间", "工具版本", "扫描面", "结果汇总", "发现项",
        "已应用的豁免", "已降级的占位符示例", "本次审计未能覆盖", "判定",
    ):
        check_in(section, markdown, "报告应包含小节 {0}".format(section))
    check_in("示例邮箱", markdown, "豁免理由必须写入报告")
    check_in("示例限制", markdown, "未覆盖项必须写入报告")
    check_in("META-005", markdown)


@test
def test_audit_json_payload_is_serializable_and_traceable(sandbox: Path) -> None:
    result = audit_repo.AuditResult()
    result.repo_root = sandbox
    result.placeholders = [{"rule_id": "SEC-001", "path": "a.md", "line": 1, "marker": "x"}]
    result.exemptions = [
        {"rule_id": "SEC-006", "path": "README.md", "line": 1,
         "matched_glob": "README.md", "reason": "理由", "allowlist_line": 1}
    ]
    result.findings.append(
        _common.make_finding("META-003", ".", 0, "缺少 README", severity="MINOR")
    )
    payload = audit_repo.build_json_payload(result, argparse.Namespace())
    text = json.dumps(payload, ensure_ascii=False)
    check_in("\"counts\"", text)
    check_eq(payload["exemptions"]["count"], 1, "豁免必须写入 JSON")
    check_eq(payload["placeholder_downgrades"]["count"], 1, "占位符降级必须写入 JSON")
    check_eq(payload["exit_code"], 0, "只有 MINOR 时退出码应为 0")
    result.findings.append(
        _common.make_finding("SEC-001", "a.py", 1, "密钥", evidence="AKIAZZ7XQ2VKLM4NPQRS")
    )
    payload2 = audit_repo.build_json_payload(result, argparse.Namespace())
    check_eq(payload2["exit_code"], 1, "存在 BLOCKER 时退出码应为 1")
    serialized = json.dumps(payload2, ensure_ascii=False)
    check("AKIAZZ7XQ2VKLM4NPQRS" not in serialized, "JSON 报告不得含未脱敏证据")
    check_in("AKIA\u2026", serialized)


# ---------------------------------------------------------------------------
# 读文件的健壮性
# ---------------------------------------------------------------------------


@test
def test_crlf_file_is_scanned_without_stray_carriage_returns(sandbox: Path) -> None:
    target = sandbox / "crlf.md"
    with open(target, "wb") as handle:
        handle.write(b"first line\r\napi_key = \"AKIAZZ7XQ2VKLM4NPQRS\"\r\n")
    document = scan_secrets._read_document(target, sandbox)
    check(document is not None, "CRLF 文件应当可读")
    for line in document.lines:  # type: ignore[union-attr]
        check("\r" not in line, "扫描时不应残留 CR：{0!r}".format(line))
    findings = scan_secrets.scan_document(document)  # type: ignore[arg-type]
    check_eq([item.line for item in findings], [2], "行号应指向第 2 行")


@test
def test_bom_is_stripped_from_read_files(sandbox: Path) -> None:
    target = sandbox / "bom.md"
    with open(target, "wb") as handle:
        handle.write("\ufeff# 标题\n".encode("utf-8"))
    text = _common.read_text_utf8(target)
    check(text is not None, "文件应当可读")
    check(not text.startswith("\ufeff"), "读取时应剥离 BOM")  # type: ignore[union-attr]


@test
def test_binary_files_are_skipped(sandbox: Path) -> None:
    target = sandbox / "blob.bin"
    with open(target, "wb") as handle:
        handle.write(b"\x00\x01\x02PNG\x00")
    check(_common.read_text_utf8(target) is None, "二进制文件应返回 None")


@test
def test_walk_files_skips_heavy_directories(sandbox: Path) -> None:
    write_text(sandbox / "keep.txt", "keep\n")
    write_text(sandbox / "node_modules" / "dep.js", "module.exports = 1\n")
    write_text(sandbox / ".git" / "config", "[core]\n")
    write_text(sandbox / "src" / "deep" / "x.py", "x = 1\n")
    found = {_common.relative_posix(path, sandbox) for path in _common.walk_files(sandbox)}
    check_in("keep.txt", found)
    check_in("src/deep/x.py", found)
    check(not any(name.startswith("node_modules/") for name in found), "应跳过 node_modules")
    check(not any(name.startswith(".git/") for name in found), "应跳过 .git")


@test
def test_make_finding_forces_masking(sandbox: Path) -> None:
    finding = _common.make_finding(
        "SEC-001", "a.py", 3, "疑似密钥", evidence="AKIAZZ7XQ2VKLM4NPQRS"
    )
    check("AKIAZZ7XQ2VKLM4NPQRS" not in json.dumps(finding.to_dict(), ensure_ascii=False))
    check_eq(finding.evidence_masked, "AKIA\u2026(20)")
    check_eq(finding.format_line().split()[0], "BLOCKER", "格式化输出首列应为严重级别")


# ---------------------------------------------------------------------------
# 文档中真实存在的占位符（回归测试）
# ---------------------------------------------------------------------------


@test
def test_repository_documentation_placeholders_are_downgraded(sandbox: Path) -> None:
    """回归：本技能文档里的示例密钥/示例邮箱必须降级，而不是报 BLOCKER。

    这是"告警疲劳"的直接防线：如果文档自身的示例都会触发阻断，使用者很快就会
    学会忽略全部告警，阻断机制随之失效。
    """
    skill_dir = SCRIPTS_DIR.parent
    targets = [
        skill_dir / "references" / "commit-convention.md",
        skill_dir / "SKILL.md",
    ]
    checked = 0
    for target in targets:
        if not target.is_file():
            continue
        document = scan_secrets._read_document(target, skill_dir)
        if document is None:
            continue
        checked += 1
        findings = scan_secrets.scan_document(document)
        outcome = scan_secrets.classify(findings, [document], None)
        for item in outcome.findings:
            raise CheckFailure(
                "技能文档中的占位符未被降级：{0} {1}:{2}".format(
                    item.rule_id, item.path, item.line
                )
            )
    check(checked > 0, "至少应检查到一份技能文档")


@test
def test_documented_noreply_example_is_a_placeholder(sandbox: Path) -> None:
    line = 'git config user.email "12345678+username@users.noreply.github.com"'
    findings = scan_lines([line])
    check(len(findings) > 0, "该示例行应当先被规则命中")
    outcome = scan_secrets.classify(findings, [], None)
    check_eq(len(outcome.findings), 0, "文档中的 noreply 占位地址必须降级，不能阻断")


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------


# 自检临时根目录名：**唯一**的命名方案，固定放在仓库根下，且只有这一层。
# 无论测试成败都会在 finally 中删除。
SCRATCH_DIR_NAME = ".selftest-tmp"

# TemporaryDirectory 句柄：需要在 finally 里显式清理，故在模块级持有。
_TEMP_HOLDERS: List[tempfile.TemporaryDirectory] = []


def force_rmtree(path: Path, attempts: int = 6, delay: float = 0.12) -> bool:
    """删除目录树，返回**是否确实删掉了**。

    这里要处理两个 Windows 特有的坑，二者都不处理就会留下垃圾：

    1. **只读文件**：git 把松散对象（``.git/objects/xx/…``）写成只读属性，
       ``shutil.rmtree`` 碰到就抛 ``PermissionError`` 并中止。所以要先
       ``os.chmod(S_IWRITE)`` 再重试。
    2. **句柄残留**：子进程（``git``）退出后，它的"当前目录"句柄可能短暂留存，
       于是目录本身一时删不掉；等一会儿再试通常就好了。

    **返回值不能忽略。** 此前这里把失败静默吞掉，结果是自检打印
    "77 通过，0 失败" 的同时在仓库里留下 ``.selftest-tmp/`` 空目录——
    "测试全绿但承诺没兑现"正是本项目最反对的那种报告。

    用 ``onerror`` 而不是 ``onexc``：后者是 Python 3.12+ 才有的参数，
    而本套脚本要求兼容 3.9+。
    """

    def _on_error(func, target, _exc_info) -> None:
        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except OSError:
            pass  # 本轮尽力；是否真的删掉了由外层检查

    if not path.exists():
        return True
    for attempt in range(attempts):
        shutil.rmtree(str(path), ignore_errors=False, onerror=_on_error)
        if not path.exists():
            return True
        time.sleep(delay * (attempt + 1))
    return not path.exists()


def _project_root() -> Path:
    """返回放置 scratch 目录的仓库根。

    优先用 git 仓库根（``.selftest-tmp`` 正好落在 .gitignore 覆盖的那一层）；
    不是 git 仓库时退回脚本目录的上一层。
    """
    detected = _common.find_repo_root(SCRIPTS_DIR)
    if detected is not None:
        return detected
    return SCRIPTS_DIR.parent


def _scratch_is_usable(root: Path) -> bool:
    """验证目录"真的能往里写文件"——只创建出目录本身并不足以证明可用。"""
    try:
        probe = root / "write-probe.txt"
        with open(probe, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("probe\n")
        probe.unlink()
        return True
    except OSError:
        return False


def _prepare_work_dir() -> Tuple[Path, str]:
    """准备自检的临时根目录，返回 ``(路径, 策略说明)``。

    两种策略，按顺序尝试：

    1. ``tempfile.TemporaryDirectory()``（首选，与 CI / GitHub Actions 行为一致）；
    2. 失败时退回 **仓库根下的唯一专用目录** ``<repo>/.selftest-tmp/run-<pid>/``。

    为什么需要第 2 种：受限沙箱的临时区是"平铺可写"的——能创建目录、能写顶层
    文件，但不能往刚创建出来的目录里写文件（``PermissionError``），于是第 1 种
    在本机直接不可用；而自检必须在本地也能跑。

    两种策略的共同保证：

    * 只有 ``.selftest-tmp`` 这一个命名方案，没有第二种写法；
    * 绝不在仓库根直接落地文件，也绝不写在 ``scripts/`` 里；
    * 无论测试通过还是失败，都在 ``finally`` 中删除。
    """
    try:
        holder = tempfile.TemporaryDirectory(prefix="gpp-selftest-")
        root = Path(holder.name)
        if _scratch_is_usable(root):
            _TEMP_HOLDERS.append(holder)
            return root, "tempfile.TemporaryDirectory（系统临时区）"
        holder.cleanup()
    except OSError:
        pass

    scratch_root = _project_root() / SCRATCH_DIR_NAME
    force_rmtree(scratch_root)
    run_dir = scratch_root / "run-{0}".format(os.getpid())
    run_dir.mkdir(parents=True, exist_ok=True)
    if not _scratch_is_usable(run_dir):
        raise OSError(
            "系统临时区不可写，且 {0} 也无法写入文件".format(_common.to_posix(run_dir))
        )
    return run_dir, "工作区回退目录 {0}/（系统临时区不可写）".format(SCRATCH_DIR_NAME)


def _cleanup_work_dir(root: Path) -> bool:
    """删除临时根目录与 scratch 父目录；返回是否**确实全部删掉**。"""
    for holder in _TEMP_HOLDERS:
        try:
            holder.cleanup()
        except OSError:
            pass
    _TEMP_HOLDERS.clear()
    removed = force_rmtree(root)
    # run-<pid> 的父目录（.selftest-tmp）也要收掉，否则会在仓库里留一个空目录。
    removed = force_rmtree(root.parent) and removed
    return removed


def run_all(filters: Sequence[str], verbose: bool, force_failure: bool = False) -> int:
    selected = [
        (name, func)
        for name, func in TEST_FUNCTIONS
        if not filters or any(token in name for token in filters)
    ]
    if not selected:
        print("没有匹配的测试用例（过滤器：{0}）".format("、".join(filters)))
        return 2

    try:
        work, strategy = _prepare_work_dir()
    except OSError as exc:
        print("执行错误：无法准备临时目录（{0}）".format(exc), file=sys.stderr)
        return 2

    print("=" * 72)
    print("github-project-publisher 自检 — 共 {0} 个用例".format(len(selected)))
    print("临时目录策略：{0}".format(strategy))
    print("临时目录：{0}".format(_common.to_posix(work)))
    print("（只在此目录内创建文件，绝不修改仓库状态、git 配置或已有文件）")
    print("=" * 72)

    passed = 0
    failures: List[Tuple[str, str]] = []
    cleanup_failed = False
    scratch_root = _project_root() / SCRATCH_DIR_NAME
    try:
        for index, (name, func) in enumerate(selected, start=1):
            sandbox = work / "{0:02d}-{1}".format(index, name)
            shutil.rmtree(sandbox, ignore_errors=True)
            sandbox.mkdir(parents=True, exist_ok=True)
            try:
                if force_failure:
                    # --force-failure：故意失败一次，用于验证"失败路径同样会清理"。
                    # 该开关只制造失败，不改变任何断言。
                    write_text(sandbox / "intentional.txt", "intentional\n")
                    raise CheckFailure("--force-failure：故意制造的失败，用于验证清理")
                func(sandbox)
            except CheckFailure as exc:
                failures.append((name, str(exc)))
                print("FAIL {0}".format(name))
                print("     {0}".format(exc))
            except Exception:  # 未预期的异常：打印完整栈便于定位
                detail = traceback.format_exc()
                failures.append((name, detail.strip().splitlines()[-1]))
                print("FAIL {0}（未预期异常）".format(name))
                print(detail)
            else:
                passed += 1
                print("PASS {0}".format(name))
            finally:
                if not verbose:
                    # 用 force_rmtree 而不是 shutil.rmtree(ignore_errors=True)：
                    # 后者不清只读属性，对创建过 git 仓库的用例必然失败，
                    # 而且失败是静默的——每个用例留一个目录，最后堆在仓库里。
                    force_rmtree(sandbox)
            if force_failure:
                break
    finally:
        if verbose:
            print("--verbose：保留临时目录以便排查：{0}".format(_common.to_posix(work)))
        else:
            cleanup_ok = _cleanup_work_dir(work)
            remaining = scratch_root.exists()
            print(
                "清理确认：{0} 仍存在 = {1}".format(
                    _common.to_posix(scratch_root), remaining
                )
            )
            if not cleanup_ok or remaining:
                cleanup_failed = True

    print("-" * 72)
    print("结果：{0} 通过，{1} 失败，共 {2}".format(passed, len(failures), len(selected)))
    if failures:
        print("失败用例：")
        for name, reason in failures:
            print("  - {0}: {1}".format(name, reason))
    if cleanup_failed:
        print(
            "清理失败：临时目录未被完全删除（{0}）。\n"
            "    这不影响上面的测试结论，但它违反了「无论成败都会删除」的承诺。\n"
            "    残留物已被 .gitignore 覆盖，不会进入提交；请手动删除后重跑。".format(
                _common.to_posix(scratch_root)
            )
        )
    # 清理失败也要反映到退出码：一个「测试全绿却留下垃圾」的运行，
    # 不应该被 CI 当成成功。
    return 1 if (failures or cleanup_failed) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="selftest.py",
        description=(
            "github-project-publisher 脚本层自检。"
            "不依赖 pytest 或任何第三方包，只在专用的临时目录中创建文件，"
            "不修改真实仓库状态。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "退出码：0 全部通过；1 存在失败；2 用法错误。\n"
            "临时目录：优先系统临时区；不可写时退回 <仓库根>/.selftest-tmp/run-<pid>/，"
            "无论成败都会删除。\n"
            "示例：python .\\selftest.py\n"
            "      python .\\selftest.py --verbose\n"
            "      python .\\selftest.py --only mask\n"
            "      python .\\selftest.py --list"
        ),
    )
    parser.add_argument("--verbose", action="store_true", help="保留测试产出的临时目录，便于排查")
    parser.add_argument(
        "--only",
        metavar="TOKEN",
        action="append",
        default=[],
        help="只运行名字中包含该片段的用例（可重复）",
    )
    parser.add_argument("--list", action="store_true", help="列出全部用例名后退出")
    parser.add_argument(
        "--force-failure",
        action="store_true",
        help="自检的自检：故意让第一个用例失败，用于验证失败路径同样会清理临时目录",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.list:
        for name, _func in TEST_FUNCTIONS:
            print(name)
        return 0
    try:
        return run_all(args.only, args.verbose, force_failure=args.force_failure)
    except Exception as exc:
        print("执行错误：{0}: {1}".format(type(exc).__name__, exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
