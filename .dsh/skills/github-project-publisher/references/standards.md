# 依据来源清单

本文件是本 skill 的**权威引用表**。每条规则追溯到一手来源，每个来源至少支撑一条可执行规则。

规则编号、严重级别与豁免机制见 [`checks.md`](checks.md)。

---

## 1. 引用准入标准

一条来源要被列入本表，必须同时满足：

1. **一手性**：优先 RFC、规范正文、官方文档、厂商安全公告。**二手博客不作为依据来源**——提交规范的原始草稿正是因为依据二手博客，才把 `init` 误列为标准 type、把 `BREAKING CHANGE` 误列为 type。
2. **对应性**：它必须支撑至少一条**可执行**的检查项或规则。无法落到具体规则的引用是装饰，不予收录。
3. **稳定性**：有版本号、编号或长期归档。变化频繁的页面需在表中标注为"参考"而非"规范"。
4. **可解析**：URL 有效。链接失效的来源应替换或移除，而不是保留。

反向要求同样成立：**每条规则必须能指向本表中的至少一条来源**。若一条规则找不到来源，它要么属于"本规范自行约定"（须显式标注），要么不应存在。

> 存在"本规范自行约定"是正当的，但**必须标注**。把团队约定伪装成规范条文，会让使用者无法判断哪些可以偏离。

---

## 2. 引用表

### 2.1 提交信息与版本

| # | 来源 | 版本 | 支撑规则 | 性质 |
|---|---|---|---|---|
| 1 | [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) | 1.0.0 | `DOC-004`；提交信息三段式结构、`type` 语义、`!` 与 `BREAKING CHANGE` footer、footer 构造 | 规范 |
| 2 | [@commitlint/config-conventional](https://github.com/conventional-changelog/commitlint/tree/master/%40commitlint/config-conventional) | master | `type` 白名单（11 项）、`header-max-length`、`subject-case`、`subject-full-stop`、`body-leading-blank` 等阈值 | 规范实现 |
| 3 | [Angular 提交信息约定](https://github.com/angular/angular/blob/main/contributing-docs/commit-message-guidelines.md) | main | 第 2 条 type 集合的源头 | 规范来源 |
| 4 | [Semantic Versioning](https://semver.org/) | 2.0.0 | 版本推导：`fix`→PATCH、`feat`→MINOR、BREAKING→MAJOR | 规范 |
| 5 | [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) | 1.1.0 | `DOC-001`；CHANGELOG 结构与分类标题 | 规范 |

### 2.2 文档结构

| # | 来源 | 版本 | 支撑规则 | 性质 |
|---|---|---|---|---|
| 6 | [standard-readme](https://github.com/RichardLitt/standard-readme) | main | `META-003`、`DOC-004`；README 章节骨架 | 社区规范 |
| 7 | [GitHub Docs: About READMEs](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes) | 2026 校核 | `DOC-004`；README 的平台展示行为 | 官方文档 |

### 2.3 许可

| # | 来源 | 版本 | 支撑规则 | 性质 |
|---|---|---|---|---|
| 8 | [SPDX License List](https://spdx.org/licenses/) | 滚动更新 | `META-002`；许可证标准标识符 | 标准 |
| 9 | [Choose a License](https://choosealicense.com/) | 滚动更新 | `META-001`；许可证选择判断 | 官方参考 |

### 2.4 安全与隐私

| # | 来源 | 版本 | 支撑规则 | 性质 |
|---|---|---|---|---|
| 10 | [CWE-798: Use of Hard-coded Credentials](https://cwe.mitre.org/data/definitions/798.html) | 4.x | `SEC-001` ~ `SEC-007`、`SEC-009` | 标准 |
| 11 | [CWE-532: Insertion of Sensitive Information into Log File](https://cwe.mitre.org/data/definitions/532.html) | 4.x | `SEC-008`；审计报告脱敏；核验命令只输出判定 | 标准 |
| 12 | [The Twelve-Factor App §III. Config](https://12factor.net/config) | — | `SEC-001` ~ `SEC-004`；配置置于环境变量而非代码 | 方法论 |
| 13 | [FIPS 180-4](https://csrc.nist.gov/pubs/fips/180-4/upd1/final) | upd1 | `REL-001` ~ `REL-004`；SHA-256 算法定义 | 标准 |

### 2.5 Git 与平台

| # | 来源 | 版本 | 支撑规则 | 性质 |
|---|---|---|---|---|
| 14 | [gitattributes(5)](https://git-scm.com/docs/gitattributes) | git 2.50 | `META-005`；`.gitattributes` 规则、二进制判定、`export-ignore` | 官方手册 |
| 15 | [gitignore(5)](https://git-scm.com/docs/gitignore) | git 2.50 | `GIT-005`；忽略规则对已跟踪文件无效 | 官方手册 |
| 16 | [git-interpret-trailers](https://git-scm.com/docs/git-interpret-trailers) | git 2.50 | footer / trailer 构造 | 官方手册 |
| 17 | [GitHub Docs: Configuring Git to handle line endings](https://docs.github.com/en/get-started/getting-started-with-git/configuring-git-to-handle-line-endings) | 2026 校核 | `META-005`；仓库内统一 LF、`.bat`/`.cmd` 的 CRLF 例外 | 官方文档 |
| 18 | [github/gitignore](https://github.com/github/gitignore) | main | `META-004`；`.gitignore` 模板来源 | 官方仓库 |
| 19 | [GitHub Docs: Setting your commit email address](https://docs.github.com/en/account-and-profile/setting-up-and-managing-your-personal-account-on-github/managing-email-preferences/setting-your-commit-email) | 2026 校核 | `GIT-001`、`GIT-002`；noreply 格式与服务端拦截 | 官方文档 |
| 20 | [GitHub Docs: About community profiles for public repositories](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/about-community-profiles-for-public-repositories) | 2026 校核 | `DOC-002`、`DOC-003`；社区健康文件的识别规则 | 官方文档 |
| 21 | [GitHub Docs: About large files on GitHub](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github) | 2026 校核 | `GIT-004`；50 MB 警告 / 100 MB 拒收阈值 | 官方文档 |
| 22 | [GitHub Docs: About merge methods](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/about-merge-methods-on-github) | 2026 校核 | squash merge 下 PR 标题即提交标题 | 官方文档 |
| 23 | [GitHub Docs: Linking a pull request to an issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue) | 2026 校核 | `Closes` / `Fixes` 关键字自动关闭 issue | 官方文档 |
| 24 | [GitHub CLI manual](https://cli.github.com/manual/) | gh 2.101 | `gh repo create`、`gh release create`、`gh repo edit` 的权威出处 | 官方手册 |

### 2.6 规范性与安全基线

| # | 来源 | 版本 | 支撑规则 | 性质 |
|---|---|---|---|---|
| 25 | [BCP 14: RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) + [RFC 8174](https://www.rfc-editor.org/info/rfc8174) | — | 本项目及全部 references 的规范性用语 | 标准 |
| 26 | [OpenSSF Scorecard](https://github.com/ossf/scorecard) | main | 仓库安全基线检查项的设计参考 | 社区标准 |
| 27 | [A Note About Git Commit Messages](https://tbaggery.com/2008/04/19/a-note-about-git-commit-messages.html) | 2008 | 提交标题 50 / 正文 72 的**长度建议** | **社区惯例，非规范** |

> 第 27 条是唯一被显式标注为"社区惯例"的条目，因为它的性质与其他条目不同：它是一个人的经验建议，不是任何标准。把它与 Conventional Commits 并列而不加区分，会让人误以为 50 字符是规范要求。

---

## 3. 规则 ↔ 来源 反向索引

用于回答"这条规则凭什么是规则"。

| 规则 ID | 依据 |
|---|---|
| `SEC-001` | CWE-798；12-Factor §III |
| `SEC-002` | CWE-798；12-Factor §III |
| `SEC-003` | CWE-798；12-Factor §III |
| `SEC-004` | CWE-798；12-Factor §III |
| `SEC-005` | CWE-798；12-Factor §III |
| `SEC-006` | CWE-798；12-Factor §III |
| `SEC-007` | CWE-798；12-Factor §III |
| `SEC-008` | CWE-532 |
| `SEC-009` | CWE-798；12-Factor §III |
| `SEC-010` | **本规范自行约定** |
| `GIT-001`、`GIT-002`、`GIT-003` | GitHub 提交邮箱文档 |
| `GIT-004` | GitHub 大文件文档 |
| `GIT-005` | gitignore(5) |
| `META-001` | Choose a License |
| `META-002` | SPDX License List |
| `META-003` | standard-readme |
| `META-004` | github/gitignore |
| `META-005` | gitattributes(5)；GitHub 行尾文档 |
| `META-006` | **本规范自行约定** |
| `DOC-001` | Keep a Changelog |
| `DOC-002`、`DOC-003` | GitHub 社区健康文件文档 |
| `DOC-004` | standard-readme；GitHub About READMEs |
| `DOC-005` | **本规范自行约定** |
| `REL-001` | FIPS 180-4 |
| `REL-002` | FIPS 180-4 |
| `REL-003` | FIPS 180-4 |
| `REL-004` | FIPS 180-4 |
| `ID-001` | **本规范自行约定** |

显式标注为"本规范自行约定"的共 5 条（`SEC-010`、`META-006`、`DOC-005`、`ID-001`，以及提交规范中 §2.2 的禁止 type 清单）。它们没有外部标准依据，因此**可以被项目按需覆盖**，而不构成对规范的偏离。

> **为什么逐个列出而不写成 `SEC-001 ~ SEC-007`**：区间写法虽然简洁，却使闭合性无法被机械校验——一个只匹配规则 ID 字面量的检查器会把区间内的规则全部判为"缺少依据"。本节的价值恰恰在于它能被脚本验证，因此宁可多几行也要逐个列出。

---

## 4. 校核与维护

### 4.1 校核记录

| 项 | 说明 |
|---|---|
| 校核方式 | 逐条通过 HTTP 请求确认返回 200 |
| 已确认可解析 | 全部 27 条中的 GitHub 文档族（`about-readmes`、`healthy contributions`、合并方式）、`rfc8174`、`conventionalcommits`、`commitlint` 源码 |
| 未逐一确认 | 其余条目使用长期稳定的规范与官方手册路径 |

### 4.2 一个必须说明的限制

**沙箱会话内无法校验链接可达性。**

在 DSH 的受限模式下，子进程的网络出口是被阻断的：从 PowerShell 发起 `Invoke-WebRequest` 会失败（表现为 TLS 凭据错误或连接被拒），而宿主进程的抓取能力不受影响。因此：

- 审计脚本**不尝试**校验引用 URL 的可达性，也不应因此判定审计失败
- 引用有效性的维护依赖人工定期检查，或在不受限的环境中执行

需要校验时，在不受限环境运行；在 PowerShell 5.1 中还需先启用 TLS 1.2：

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri <url> -Method Head -UseBasicParsing
```

### 4.3 更新流程

修改规则或来源时：

1. 更新本文件的引用表与反向索引
2. 若来源有版本号，确认版本仍准确
3. 确认闭合性仍然成立：**不存在无来源的规则，也不存在无规则的引用**
4. 在 [`../CHANGELOG.md`](../../../CHANGELOG.md) 的 `[Unreleased]` 下登记

---

## English summary

This is the skill's authoritative citation list. A source qualifies only if it is **primary** (RFCs, specification text, official docs, vendor advisories — second-hand blog posts are explicitly excluded, since the original commit-convention draft inherited its `init` and `BREAKING CHANGE` errors from one), **mapped to at least one executable rule**, **stable** (versioned or archived), and **resolvable**.

The inverse requirement also holds: every rule must point to at least one source. Where no external standard exists, the rule is explicitly labelled **a convention of this document** rather than passed off as specification text — five rules carry that label and may therefore be overridden per project without constituting a deviation.

One entry, Tim Pope's 50/72 guidance, is explicitly marked as **community practice, not a specification**, because presenting it alongside Conventional Commits without that distinction would imply the 50-character subject limit is normative. It is not.

**Known limitation**: link reachability cannot be verified inside a sandboxed DSH session, because network egress from child processes is blocked while host-side fetching still works. The audit therefore does not test URL reachability and must not fail because of it.
