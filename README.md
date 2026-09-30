# dsh-github-publisher

[English](README.en.md) | 中文

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)
![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)

> 一个适用于 [DSH](https://github.com/deepseek-ai) 的 skill：把「本地项目 → GitHub 公开发布」这条链路标准化，并强制在公开前完成敏感信息审查与人工核验。

---

## 目录

- [1. 这是什么](#1-这是什么)
- [2. 它解决什么问题](#2-它解决什么问题)
- [3. 安装](#3-安装)
- [4. 使用](#4-使用)
- [5. 工作流程与两道闸门](#5-工作流程与两道闸门)
- [6. 决策分级](#6-决策分级)
- [7. 敏感信息审查](#7-敏感信息审查)
- [8. 提交身份与隐私邮箱](#8-提交身份与隐私邮箱)
- [9. SHA256 校验和](#9-sha256-校验和)
- [10. 脚本](#10-脚本)
- [11. 目录结构](#11-目录结构)
- [12. 依据来源](#12-依据来源)
- [13. 已知限制](#13-已知限制)
- [14. 贡献](#14-贡献)
- [15. 许可](#15-许可)

---

## 1. 这是什么

`dsh-github-publisher` 是一个 DSH skill，帮助 AI Agent 完成从本地项目到 GitHub 的发布准备与上传，包括：

- **上传前项目规范检查**：目录结构、`.gitignore`、许可证、元数据一致性
- **敏感信息审查**：API key、密钥、密码、个人信息、支付凭证，含被写入日志的情况
- **README 与 Release 文案撰写**：按业界规范生成双语初稿
- **提交身份治理**：强制使用 GitHub noreply 隐私邮箱
- **SHA256 校验和**：为发布物生成可校验的 `SHA256SUMS`
- **受控上传**：全程使用 GitHub CLI 与 git，新建仓库默认私有

设计目标是**可复核**：每条规则都能追溯到公开依据，每个结论都能被独立验证。依据来源见[第 12 节](#12-依据来源)。

## 2. 它解决什么问题

发布一个项目时的风险不在于「git push 会不会用」，而在于几类**事后无法挽回**的错误：

| 风险 | 后果 |
|---|---|
| 密钥、令牌、密码被提交 | 一旦推送，即使立刻删除也留在历史与缓存中，必须轮换密钥 |
| 真实邮箱写入提交 | 永久公开在 `git log` 中；GitHub 会把它关联到你的账号 |
| 敏感信息被写进日志文件 | 日志常被一并提交，且很少有人在提交前翻阅 |
| 校验和带 BOM 或 CRLF | Linux 使用者 `sha256sum -c` 失败，发布物完整性无法验证 |
| 校验和缺失 | 使用者无法验证下载的产物是否被篡改 |
| 未经核验就公开仓库 | 敏感内容在人工阅读 README 之前就已对全网可见 |

本 skill 的处理方式是：**在本地就把这些问题挡住**，并且**默认不公开**。

## 3. 安装

本 skill 遵循 DSH 的本地 skill 发现规则：skill 是目录 bundle `<根目录>/<名称>/SKILL.md`，只扫描**一层深**。

DSH 按以下优先级扫描 skill 根目录：

| 优先级 | 来源 | 路径 |
|---|---|---|
| 100 | `project-dsh` | `<项目根>/.dsh/skills` |
| 200 | `project-agents` | `<项目根>/.agents/skills` |
| 300 | `custom` | 配置项 `customSkillDirs` |
| 400 | `user-dsh` | `<DSH_HOME>/skills`（默认 `~/.dsh/skills`） |
| 500 | `user-agents` | `<AGENTS_HOME>/skills`（默认 `~/.agents/skills`） |

其中**项目根**是最近的、包含 `.git` 的祖先目录；没有 `.git` 时回退到当前工作目录。

### 方式一：项目级安装

把 skill 目录放进目标项目的 `.dsh/skills/` 下。项目级 skill 应随仓库提交，团队成员 clone 后即可使用。

```powershell
# 在目标项目根目录执行
New-Item -ItemType Directory -Force .dsh\skills | Out-Null
Copy-Item -Recurse <本仓库>\.dsh\skills\github-project-publisher .dsh\skills\
```

> 目标项目必须存在 `.git`，否则项目根无法确定，skill 可能不被发现。

### 方式二：用户级安装

安装到 `~/.dsh/skills/`，所有项目均可使用。

```powershell
Copy-Item -Recurse <本仓库>\.dsh\skills\github-project-publisher $env:USERPROFILE\.dsh\skills\
```

### 验证安装

安装后 skill 会出现在会话的 skill 目录中。加载它即可：

```text
/github-project-publisher
```

## 4. 使用

DSH 中 skill 有两种调用方式：

| 方式 | 语法 | 说明 |
|---|---|---|
| 用户调用 | `/github-project-publisher` | 在消息中输入，skill 指令会注入该步骤 |
| 模型调用 | `skill` 工具，参数为名称 | Agent 在任务与 skill 描述匹配时自行加载 |

> 注意前缀是斜杠 `/`，不是 `$`。`/名称` 必须是一个由空白分隔的独立 token。

### 4.1 使用举例

```text
/github-project-publisher 检查当前项目，完善 README 和 Release 文案，并准备发布到 GitHub。
```

```text
/github-project-publisher 帮我审查这个项目有没有泄露密钥，然后生成 README。
```

```text
/github-project-publisher 只做上传前检查，先不要创建仓库。
```

```text
/github-project-publisher 检查最近的提交，确认作者和提交者邮箱都是 noreply 地址。
```

```text
/github-project-publisher 为 dist/ 下的产物生成 SHA256 校验和，并起草 Release 文案。
```

### 4.2 输出与闸门

skill 在检查完成后**不会直接上传**。它会先呈交：

1. **审计报告**——按严重级别分组，列出问题位置（不回显敏感值原文）
2. **README 初稿**——待你修改
3. **Release 文案初稿**——待你修改

只有在你**明确下达发布指令**后，才会创建私有仓库并推送；再经**第二次明确指令**，才会将仓库公开。

## 5. 工作流程与两道闸门

| # | 阶段 | 主要动作 | 闸门 |
|---|---|---|---|
| 0 | 侦察 | 识别生态、包管理器、git 状态 | 默认执行 |
| 1 | 合规审计 | 目录规范、`.gitignore`、许可证、元数据 | 默认执行 |
| 2 | **敏感信息审查** | 工作区 + 暂存区 + 历史 + 日志产物 | 🔴 **硬阻断** |
| 3 | 身份治理 | 写入 noreply 邮箱、校验 author 与 committer | 默认执行 |
| 4 | 文档生成 | README、CHANGELOG、LICENSE | 生成初稿 |
| 5 | 发布物准备 | 版本号推导、Release 文案、**SHA256 校验和** | 默认执行 + 留痕 |
| 6 | **人工核验闸门** | 呈交报告与文案，**停止，不上传** | 🔴 **第一次放行** |
| 7 | 首次上传 | 创建**私有**仓库 → push | 需第一次放行 |
| 8 | 上传后复核 | 远程二次扫描、确认可见性仍为 private | 默认执行 |
| 9 | 发布 | 公开仓库 + 正式发布 Release（附校验和） | 🔴 **第二次放行** |

**为什么是两道闸门**：第 6 道挡的是「上传动作」，第 9 道挡的是「公开动作」。私有仓库本身构成第三层缓冲——即使前面的检查全部漏过，内容也只在你的账号内。

## 6. 决策分级

混淆「该问的」与「不该问的」会同时造成两种失败：把必答题默认掉（风险），和不必要的追问（噪音）。本项目把每个决策点明确归入四类：

| 类别 | 含义 | 示例 |
|---|---|---|
| 🟦 **必须问** | 不可逆或取决于你的意图，必须用选项卡询问 | 仓库名、可见性、许可证、文案语言 |
| 🟧 **二次确认** | 破坏性或放宽限制的操作，需明确「是」 | 改写 git 历史、force push、仓库转公开、豁免 BLOCKER |
| 🟩 **默认执行 + 留痕** | 无条件该做的事，不问，但必须记录 | 敏感信息扫描、SHA256 校验和、补 `.gitignore`、设本地 noreply 身份 |
| 🔴 **红线** | 无明确指令绝不执行 | 公开仓库、force push 到已有远程、删除远程内容、修改全局 git 配置、回显密钥原文 |

完整分级表见 [`references/interaction.md`](.dsh/skills/github-project-publisher/references/interaction.md)。

**其中「默认执行」类的设计要点**：像 SHA256 校验和这种每次都必须做的事，**不要**拿来提问。「每次都问」的结果是用户养成无脑确认的习惯，问与不问都失去意义。正确做法是默认执行，并把执行记录写进审计报告。

## 7. 敏感信息审查

### 四个扫描面

| 扫描面 | 覆盖内容 | 为什么需要 |
|---|---|---|
| 工作区 | 全部受版本控制的文件 | 最基础的检查 |
| 暂存区 | `git diff --cached` | 精确对应「即将提交的内容」 |
| **git 历史** | 全部提交 | **只从 HEAD 删除无效**——密钥仍在历史中，`git log -p` 可见 |
| 日志与产物 | `*.log`、`dist/`、notebook 输出、CI 配置 | 对应 CWE-532，最容易被忽略 |

### 检测引擎

**外部工具优先，内置规则兜底**：

1. 检测到 `gitleaks` 则调用 `gitleaks detect`
2. 否则检测 `trufflehog`
3. 两者都不可用时降级到内置规则集，并在输出中**明确说明使用了哪个引擎**

降级会显著降低覆盖率，因此输出中必须标注，否则会让人误以为检查强度未变。

### 命中即阻断

发现 `BLOCKER` 级别的命中时：

- **禁止**执行 `git commit` 与 `git push`
- 输出**文件路径与行号**
- **不回显密钥原文**，仅给掩码（如 `AKIA…(20)`）

最后一条是刻意的：审计报告本身也是泄露面。若报告把密钥打印到终端、CI 日志或会话记录里，就等于换了个地方泄露。对应 [CWE-532](https://cwe.mitre.org/data/definitions/532.html)。

### 自指假阳性与豁免机制

本 skill 会扫描**自己**——它的文档里含有示例邮箱和占位密钥。若不做处理，首次自举就会误报。

假阳性是这类工具最主要的失效模式：告警被忽略几次之后，硬阻断机制就名存实亡了。因此本项目设计了**两条**豁免路径：

**路径一：占位符自动降级（优先）**

匹配到公认的占位形式时自动降级为 `INFO`，不计入 findings：`example.com`、`your_`、`xxxx`、`<...>`、`AKIAIOSFODNN7EXAMPLE`、`12345678+username@users.noreply.github.com` 等。

**路径二：显式白名单（需理由）**

写入被测项目的 `.github-upload-audit/allowlist.txt`：

```text
SEC-001  .dsh/skills/*/references/*.md  *  -- 文档示例中的占位密钥
SEC-006  README.md  42  -- 示例邮箱
```

格式为 `<规则ID> <路径通配> <行号|*> -- <理由>`。

**无理由的豁免条目会被拒绝**，并作为问题报告出来。每一次生效的豁免都会写入审计报告——这是「每个刻意动作都留痕」原则的一部分。

> **刻意不采用的方案**：把「代码块内的一切」整体豁免。那会让一个真实密钥被放进 README 时直接溜过去。宁可多一次带理由的显式豁免，也不要一个会静默放行的规则。

## 8. 提交身份与隐私邮箱

向公开仓库提交前，**必须**把身份设为 GitHub 提供的隐私邮箱：

```powershell
# 格式：<数字ID>+<用户名>@users.noreply.github.com
git config --local user.name  "your-handle"
git config --local user.email "149449562+your-handle@users.noreply.github.com"
```

### 两个容易踩的点

**其一：`--author` 管不到 committer。**

`git commit --author=...` 只覆盖 **author**；**committer** 永远取自 `user.name` / `user.email`。所以只写 `--author` 并不能保护你。正确做法是把 `user.email` 本身设为 noreply。

另外 `--author` 的值必须是 `Name <email>` 形式，**尖括号不能省**。

**其二：核验命令本身会泄露邮箱。**

直接运行下面这条会把真实邮箱打印到终端、日志与会话记录中：

```bash
git log --format='%an <%ae> | %cn <%ce>'   # ❌ 不要在日志会被留存的地方使用
```

应当使用**只输出判定**的形式，并加 `--all` 以覆盖非 HEAD 可达的历史：

```powershell
# 输出「非隐私邮箱」的条数：0 为通过
$bad = git log --all --format="%ae%n%ce" | Sort-Object -Unique |
       Where-Object { $_ -notmatch '^(\d+\+)?[A-Za-z0-9-]+@users\.noreply\.github\.com$' }
"non-noreply hits: $($bad.Count)"
```

格式串**应避免** `<`、`>`、`|` 等 shell 特殊字符——它们在 PowerShell 与 bash 中被引号保护时可用，但在 `cmd.exe` 中会直接失败。

### 建议同时开启服务端拦截

GitHub → Settings → Emails → 勾选：

- *Keep my email addresses private*
- *Block command line pushes that expose my email address*

这样即使本地配置漏了，GitHub 也会拒收推送。本地检查 + 服务端兜底。

> **诚实的边界**：如果真实邮箱**已经推送过**公开仓库，改写历史**不能收回**它——可能已被 fork、缓存或归档服务收录。此时唯一彻底的处理是轮换与该邮箱绑定的账号安全设置，并接受它已公开的事实。

## 9. SHA256 校验和

发布物**必须**附带 SHA256 校验和。这属于「默认执行」类，不提问，但必须留痕。

```powershell
python .\.dsh\skills\github-project-publisher\scripts\make_checksums.py dist\* --out SHA256SUMS
```

生成的 `SHA256SUMS` 为 coreutils 兼容格式：

```text
<64位小写十六进制>  <相对路径>
```

两个空格分隔，路径使用正斜杠，条目排序以保证可复现。

### 三个致命细节

| 细节 | 后果 |
|---|---|
| 必须 **UTF-8 无 BOM** | 带 BOM 会让 Linux 侧 `sha256sum -c` 直接失败 |
| 必须 **LF 行尾** | CRLF 会让校验值不匹配或解析失败 |
| 需用 `Get-FileHash` 而非 `sha256sum` | Windows 上没有 `sha256sum`，需自行格式化成 coreutils 兼容形式 |

脚本写文件时统一使用 `open(path, "w", encoding="utf-8", newline="\n")`，就是为了同时避免 BOM 与 CRLF。

## 10. 脚本

全部为 **Python 纯标准库**实现——这是刻意约束，因为一个审计工具如果自身需要安装依赖才能运行，就无法在被审计的受限环境中被信任地执行。

| 脚本 | 用途 |
|---|---|
| `scripts/scan_secrets.py` | 敏感信息扫描（四个扫描面，外部工具优先 + 内置规则兜底） |
| `scripts/check_identity.py` | 核验 author 与 committer 是否均为 noreply 地址（只输出判定） |
| `scripts/make_checksums.py` | 生成与验证 coreutils 兼容的 `SHA256SUMS` |
| `scripts/audit_repo.py` | 汇总检查并输出审计报告（Markdown + JSON） |
| `scripts/selftest.py` | 自测，在临时目录中运行，不触碰真实仓库状态 |

```powershell
# 自测
python .\.dsh\skills\github-project-publisher\scripts\selftest.py

# 扫描当前项目
python .\.dsh\skills\github-project-publisher\scripts\scan_secrets.py --worktree --history

# 核验提交身份
python .\.dsh\skills\github-project-publisher\scripts\check_identity.py

# 完整审计
python .\.dsh\skills\github-project-publisher\scripts\audit_repo.py
```

详细参数与退出码见 [`scripts/README.md`](.dsh/skills/github-project-publisher/scripts/README.md)。

## 11. 目录结构

```text
dsh-github-publisher/
├─ README.md                 中文说明（本文件）
├─ README.en.md              English
├─ LICENSE                   MIT
├─ CHANGELOG.md              依 Keep a Changelog
├─ CONTRIBUTING.md           贡献指南（含提交规范与双语同步规则）
├─ SECURITY.md               安全策略与威胁模型
├─ .gitignore
├─ .gitattributes            行尾治理（仓库内统一 LF）
├─ .github/
│  ├─ workflows/ci.yml       CI 质量门禁（自测、扫描、编码、双语、frontmatter）
│  ├─ ISSUE_TEMPLATE/
│  ├─ PULL_REQUEST_TEMPLATE.md
│  └─ dependabot.yml
├─ .github-upload-audit/
│  └─ allowlist.txt          豁免清单（报告不入库，本文件入库）
└─ .dsh/skills/github-project-publisher/
   ├─ SKILL.md                         面向 Agent 的指令
   ├─ references/
   │  ├─ standards.md                  依据来源清单（规则 ↔ 引用 映射）
   │  ├─ checks.md                     检查项目录（规则 ID / 严重级别）
   │  ├─ interaction.md                决策分级（必问/确认/默认/红线）
   │  ├─ templates.md                  文档模板集
   │  ├─ commit-convention.md          提交规范
   │  └─ commit-convention.en.md       Commit convention (English)
   └─ scripts/                         Python 纯标准库脚本
```

## 12. 依据来源

本项目的每条规则都追溯到以下**一手来源**中的至少一条；反过来，下列每个来源也都至少支撑一条可执行规则——不存在装饰性引用。

### 提交信息与版本

| 依据来源 | 支撑的规则 |
|---|---|
| [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) | 提交信息三段式结构、`type` 语义、`!` 与 `BREAKING CHANGE` footer、footer 构造规则 |
| [@commitlint/config-conventional](https://github.com/conventional-changelog/commitlint/tree/master/%40commitlint/config-conventional) | `type` 白名单（11 项）、`header-max-length`、`subject-case`、`subject-full-stop` 等校验阈值 |
| [Semantic Versioning 2.0.0](https://semver.org/) | 版本推导：`fix`→PATCH、`feat`→MINOR、BREAKING→MAJOR |
| [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/) | CHANGELOG 结构与分类标题 |

### 文档结构

| 依据来源 | 支撑的规则 |
|---|---|
| [standard-readme](https://github.com/RichardLitt/standard-readme) | README 章节骨架（Title / Badges / Install / Usage / Contributing / License） |
| [GitHub Docs: About READMEs](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes) | README 的平台行为与展示规则 |

### 许可

| 依据来源 | 支撑的规则 |
|---|---|
| [SPDX License List](https://spdx.org/licenses/) | 许可证的标准标识符 |
| [Choose a License](https://choosealicense.com/) | 许可证选择的判断依据 |

### 安全与隐私

| 依据来源 | 支撑的规则 |
|---|---|
| [CWE-798: Use of Hard-coded Credentials](https://cwe.mitre.org/data/definitions/798.html) | 硬编码密钥、令牌、密码的检测规则（SEC-001 ~ SEC-003） |
| [CWE-532: Insertion of Sensitive Information into Log File](https://cwe.mitre.org/data/definitions/532.html) | 日志与产物扫描面、审计报告脱敏、核验命令只输出判定 |
| [The Twelve-Factor App §III. Config](https://12factor.net/config) | 配置置于环境变量，而非代码 |
| [FIPS 180-4](https://csrc.nist.gov/pubs/fips/180-4/upd1/final) | SHA-256 算法定义 |

### Git 与平台

| 依据来源 | 支撑的规则 |
|---|---|
| [gitattributes(5)](https://git-scm.com/docs/gitattributes) | `.gitattributes` 规则、二进制判定、`export-ignore` |
| [GitHub Docs: Configuring Git to handle line endings](https://docs.github.com/en/get-started/getting-started-with-git/configuring-git-to-handle-line-endings) | 仓库内统一 LF、`.bat`/`.cmd` 的 CRLF 例外 |
| [github/gitignore](https://github.com/github/gitignore) | `.gitignore` 模板来源 |
| [GitHub Docs: Setting your commit email address](https://docs.github.com/en/account-and-profile/setting-up-and-managing-your-personal-account-on-github/managing-email-preferences/setting-your-commit-email) | noreply 邮箱格式与服务端拦截设置 |
| [GitHub Docs: Healthy contributions](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions) | `SECURITY.md`、`CONTRIBUTING.md`、Issue 与 PR 模板 |
| [GitHub CLI manual](https://cli.github.com/manual/) | `gh repo create`、`gh release create` 等命令的权威出处 |

### 规范性与基线

| 依据来源 | 支撑的规则 |
|---|---|
| [BCP 14: RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) + [RFC 8174](https://www.rfc-editor.org/info/rfc8174) | 本项目文档的规范性用语（MUST/SHOULD/MAY 仅在全大写时具规范含义） |
| [OpenSSF Scorecard](https://github.com/ossf/scorecard) | 仓库安全基线的检查项设计参考 |

> 完整的「规则编号 ↔ 依据来源 ↔ 检查项」三方映射表见 [`references/standards.md`](.dsh/skills/github-project-publisher/references/standards.md)。

## 13. 已知限制

安全审查工具**不可能**做到零漏检。本项目明确声明以下限制：

- 内置规则集只覆盖常见凭据形态，无法识别业务自定义的敏感数据格式
- 未安装 `gitleaks` / `trufflehog` 时，检测能力退化为内置规则，覆盖率显著下降
- 二进制文件、加密压缩包、图片内嵌文本不在扫描范围内
- 占位符自动降级依赖一份固定的占位符清单，可能被刻意构造的字符串绕过
- 仅扫描工作区**无法**发现历史中已提交的凭据

**这些限制不构成「未发现问题即代表安全」的保证。** 任何发布决定仍需人工核验——这正是本 skill 设置两道人工闸门的原因。

## 14. 贡献

请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。要点：

- 提交信息必须遵循[提交规范](.dsh/skills/github-project-publisher/references/commit-convention.md)
- 文档改动必须**中英同步**
- 新增规则必须提供**依据来源**与**误报风险评估**
- 脚本**不得**引入第三方依赖
- 所有文本文件为 UTF-8 无 BOM、LF 行尾

## 15. 许可

[MIT](LICENSE) © 2026 cicada478
