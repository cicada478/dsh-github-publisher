# 安全策略

[English](#english)

## 支持的版本

本项目尚未发布正式版本。首个版本发布前，仅 `main` 分支接受安全修复。

| 版本 | 支持状态 |
|---|---|
| `main`（未发布） | ✅ 接受修复 |
| 已发布的标签版本 | ⏳ 尚无 |

## 报告漏洞

**请勿通过公开 issue 报告安全漏洞。**

请使用 GitHub 的私有漏洞报告功能：

1. 打开本仓库的 **Security** 标签页
2. 点击 **Report a vulnerability**
3. 填写复现步骤、影响范围与你的判断依据

该通道经 GitHub Security Advisories 传输，只有维护者可见。

## 本项目的特殊威胁模型

本项目与其他项目不同：**它的功能就是防止敏感信息泄露**。因此本项目自身的缺陷可能直接造成用户凭据泄露。以下缺陷按**最高优先级**处理：

| 缺陷类型 | 后果 |
|---|---|
| 扫描器漏检，且未作为已知限制写入文档 | 用户据此认为项目"已安全"，从而推送了真实凭据 |
| 扫描器报告回显了密钥原文 | 审计报告本身成为新的泄露源（CWE-532） |
| `SHA256SUMS` 生成时写入 BOM | Linux 侧 `sha256sum -c` 校验失败，发布物完整性无法验证 |
| 身份核验错误地报告"通过" | 真实邮箱随提交永久公开，且无法收回 |
| 豁免机制可被绕过，或豁免静默生效 | 硬阻断失效，且无留痕可查 |

报告上述问题时，请一并说明你使用的**扫描面**（工作区 / 暂存区 / 历史 / 产物）与**引擎**（外部工具或内置规则），因为这些直接决定漏检是否属于已知限制而非缺陷。

## 已知限制

安全审查工具不可能做到零漏检。本项目已知并**明确声明**的限制：

- 内置规则集只覆盖常见凭据形态，无法识别业务自定义的敏感数据格式
- 未安装 `gitleaks` / `trufflehog` 时检测能力退化为内置规则，覆盖率显著下降
- 二进制文件、加密压缩包、图片内嵌文本不在扫描范围内
- 扫描结果取决于扫描面选择：仅扫描工作区**无法**发现历史中已提交的凭据
- 占位符自动降级依赖一份固定的占位符清单，可能被刻意构造的字符串绕过

**以上限制不构成"未发现问题即代表安全"的保证。** 任何发布决定仍需人工核验，这正是本 skill 设置两道人工闸门的原因。

## 披露流程

1. 你提交私下报告
2. 维护者确认收到并给出初步判断
3. 修复在私有分支完成，并补充对应自测用例
4. 修复发布后公开致谢，除非你要求匿名

---

## English

### Reporting a vulnerability

**Do not report security vulnerabilities through public issues.** Open this repository's **Security** tab and click **Report a vulnerability**. The report travels through GitHub Security Advisories and is visible only to maintainers.

### Threat model specific to this project

This project exists to **prevent** sensitive-information disclosure, so a defect in it can directly leak a user's credentials. The following are treated as highest priority:

- A scanner miss that is not documented as a known limitation
- A scanner report that echoes a secret value (CWE-532)
- A `SHA256SUMS` file corrupted by a BOM, breaking `sha256sum -c` on Linux
- An identity check that wrongly reports a pass, permanently publishing a real email address
- An exemption mechanism that can be bypassed or applied silently

When reporting, state which **scan surfaces** (working tree / staged / history / artifacts) and which **engine** (external tool or built-in rules) you used — this determines whether the miss is a known limitation or a defect.

### Known limitations

The built-in rule set covers only common credential shapes; without `gitleaks` or `trufflehog` installed, coverage degrades substantially; binary files, encrypted archives, and text embedded in images are not scanned; and scanning only the working tree cannot find credentials already committed in history. **None of this constitutes a guarantee that a clean result means the project is safe.** Every publish decision still requires human verification, which is why the skill enforces two manual gates.
