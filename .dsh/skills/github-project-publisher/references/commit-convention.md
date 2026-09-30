# Git Commit Message 规范

[English](commit-convention.en.md) | 中文

> **基准**：本规范以 [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) 为强制基准，`type` 集合采用 [@commitlint/config-conventional](https://github.com/conventional-changelog/commitlint/tree/master/%40commitlint/config-conventional) 的推荐值（源自 [Angular 提交信息约定](https://github.com/angular/angular/blob/main/contributing-docs/commit-message-guidelines.md)），并补充 GitHub 平台约定。
>
> **规范性用语**：本文中的 **必须（MUST）**、**禁止（MUST NOT）**、**应当（SHOULD）**、**可以（MAY）** 按 [BCP 14](https://www.rfc-editor.org/info/bcp14)（[RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) 与 [RFC 8174](https://www.rfc-editor.org/info/rfc8174)）解释。**必须**为强制项，**应当**为强烈建议，**可以**为可选项。
>
> 依 [RFC 8174](https://www.rfc-editor.org/info/rfc8174)，上述关键词**仅在全大写书写时**才具有规范性含义。本文因此始终以 `MUST` / `SHOULD` / `MAY` 等全大写形式标注规范性等级；中文译文（必须 / 应当 / 可以）仅为阅读便利，不单独构成规范约束。

## 目录

- [1. 提交信息结构](#1-提交信息结构)
- [2. type（必须）](#2-type必须)
- [3. scope（可选）](#3-scope可选)
- [4. description（必须）](#4-description必须)
- [5. body（可选）](#5-body可选)
- [6. footer（可选）](#6-footer可选)
- [7. 破坏性变更](#7-破坏性变更)
- [8. 与 SemVer 和 CHANGELOG 的对应](#8-与-semver-和-changelog-的对应)
- [9. revert 提交](#9-revert-提交)
- [10. GitHub 平台约定](#10-github-平台约定)
- [11. 工具链](#11-工具链)
- [12. 示例集](#12-示例集)
- [13. 反例对照表](#13-反例对照表)
- [14. 依据来源](#14-依据来源)
- [15. 修订记录](#15-修订记录)

---

## 1. 提交信息结构

提交信息**必须**由三段构成，后两段可选：

```text
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

逐行说明：

| 行 | 组成 | 强制性 |
|---|---|---|
| 第 1 行（header） | `type` + 可选 `scope` + 可选 `!` + **冒号加一个空格** + `description` | type 与 description 必须 |
| 第 2 行 | **空行** | 有 body 或 footer 时必须 |
| 第 3 行起 | body | 可选 |
| 空行后 | 一个或多个 footer | 可选 |

> **注意**：冒号**必须**紧贴 `type` 或 `scope` 的右括号，冒号后**必须**恰好一个空格。
> 正确：`feat(auth): add OAuth2 login`
> 错误：`feat(auth) : add OAuth2 login`（冒号前多空格）、`feat(auth):add OAuth2 login`（冒号后缺空格）

完整语法（方括号表示可选，`!` 不可与 scope 调换位置）：

```text
type[(scope)][!]: description
```

---

## 2. type（必须）

`type` 是一个名词，用于说明本次提交的**性质**。`type` **必须**小写（commitlint `type-case: lower-case`）。

### 2.1 标准 type 清单

以下 11 个 `type` 取自 `@commitlint/config-conventional` 的 `type-enum`，是 commitlint 校验通过的白名单：

| type | 含义 | 是否进 CHANGELOG | SemVer 影响 |
|---|---|---|---|
| `feat` | 新增功能 | ✅ Features | **MINOR** |
| `fix` | 修复缺陷 | ✅ Bug Fixes | **PATCH** |
| `perf` | 性能优化 | ✅ Performance Improvements | PATCH（工具默认） |
| `revert` | 撤销先前的提交 | ✅ Reverts | — |
| `docs` | 仅文档变更 | ❌ 默认隐藏 | — |
| `style` | 不影响代码含义的变更（空白、格式、缺失分号等） | ❌ 默认隐藏 | — |
| `refactor` | 既不修复缺陷也不新增功能的代码变更 | ❌ 默认隐藏 | — |
| `test` | 新增或修正测试 | ❌ 默认隐藏 | — |
| `build` | 影响构建系统或外部依赖的变更（scope 例：`gulp`、`broccoli`、`npm`） | ❌ 默认隐藏 | — |
| `ci` | CI 配置文件与脚本的变更（scope 例：`travis`、`circle`、`github`） | ❌ 默认隐藏 | — |
| `chore` | 其他不修改 `src` 或测试文件的杂项变更 | ❌ 默认隐藏 | — |

> `feat` 与 `fix` 是规范中**唯一具有语义定义**的两个 type，其余 type 不影响版本号（除非含破坏性变更）。
> `perf` 的版本影响规范未作规定，"PATCH" 是 semantic-release 等工具的默认行为。

### 2.2 禁止使用的 type

> 本节为**本规范自行约定**，并非 Conventional Commits 或 commitlint 的规定。其判据是：一个 type **必须**能映射到明确的语义与 CHANGELOG 归属，否则无法参与版本推导与变更日志生成。

下列写法**禁止**使用：

| 写法 | 原因 |
|---|---|
| `init` | 非标准 type，源自已废弃的 AngularJS 约定；初始化应使用 `chore` |
| `update` / `change` / `modify` | 语义空洞，无法映射到任何规范 type |
| `Feat` / `FIX` | `type` 必须全小写 |
| `BREAKING CHANGE` | **它不是 type**，是 footer token 或 `!` 标记，见第 7 节 |
| `feature` | 标准写法是 `feat` |
| `bugfix` | 标准写法是 `fix` |
| `wip` | 开发中提交应在合并前 squash，不应进入主干历史 |

### 2.3 团队扩展 type

规范允许在 `feat` / `fix` 之外自定义 type。扩展**必须**同时满足：

1. 在 `commitlint.config.js` 的 `type-enum` 中显式登记；
2. 在本文档的 2.1 表格中补充一行，写明含义与 CHANGELOG 归属；
3. 全小写、单词、无缩写歧义。

未登记的 type 会导致 commitlint 校验失败。

---

## 3. scope（可选）

`scope` 用于说明提交影响的**范围**，是描述代码库某一部分的名词，**必须**用圆括号包裹并紧跟在 `type` 之后。

- `scope` **应当**小写，多单词用 `-` 连接（kebab-case）：`feat(user-profile): ...`
- `scope` **禁止**包含空格：`feat(user profile): ...` ❌
- `scope` 取值**应当**在项目内保持稳定，建议取自目录名或模块名的有限集合，例如：
  - 分层架构：`api`、`ui`、`db`、`config`
  - 按包管理：`parser`、`cli`、`core`
- 改动跨多个范围时，**应当**拆分成多个提交（规范的明确建议），而非省略 scope 或堆叠 scope。

---

## 4. description（必须）

`description` 是 header 中冒号加空格之后的简短摘要。

| 规则 | 要求 | 依据 |
|---|---|---|
| 位置 | **必须**紧跟冒号加一个空格 | 规范 Rule 5 |
| 空值 | **禁止**为空 | commitlint `subject-empty: never` |
| 长度 | header 整体 **必须** ≤ 100 字符；**应当** ≤ 72；理想 ≤ 50 | 见下方说明 |
| 语态 | **应当**使用祈使语气、现在时描述"这次提交做了什么" | commitlint prompt、Angular 约定 |
| 大小写 | 英文**应当**小写开头，**禁止** Sentence case / Start Case / PascalCase / 全大写 | commitlint `subject-case` |
| 句末标点 | **禁止**以句号 `.` 结尾 | commitlint `subject-full-stop: never` |
| 内容 | **应当**说明"做了什么"，而非"改动了哪个文件" | 规范 Rule 5 |

**关于长度的准确表述**——三个来源不可混为一谈：

| 来源 | 规定 |
|---|---|
| Conventional Commits 1.0.0 | 对长度**无任何规定** |
| `@commitlint/config-conventional` | `header-max-length: 100`（Error 级，强制） |
| Git 社区惯例（Tim Pope 的 50/72 规则） | 标题 ≤ 50、正文每行 ≤ 72，属**建议**而非规范 |

**中文项目注意**：50/72 是针对英文（等宽字符）的经验值，一个汉字约占两个英文字符宽度。纯中文提交**应当**按显示宽度理解该建议，标题控制在 25 个汉字左右。

**语言一致性**：同一仓库内提交信息**应当**保持单一语言。开源项目建议使用英文，以便社区检索与自动生成 CHANGELOG。

---

## 5. body（可选）

body 提供本次变更的**上下文与动机**，回答"为什么"而不只是"是什么"。

- body **必须**与 description 之间**空一行**（commitlint `body-leading-blank: always`）
- body 为自由格式，**可以**包含任意数量由换行分隔的段落
- 每行**应当** ≤ 100 字符（commitlint `body-max-line-length: 100`）
- 适合写入 body 的内容：问题背景、方案取舍、被否决的替代方案、迁移影响、性能数据

---

## 6. footer（可选）

footer 用于承载**结构化元数据**，遵循 [git trailer 约定](https://git-scm.com/docs/git-interpret-trailers)。

- footer **必须**位于 body 之后，且**空一行**（commitlint `footer-leading-blank: always`）
- 每个 footer 的构成为：**token** + 分隔符 + **value**
- 分隔符**必须**是 `: `（冒号加空格）或 ` #`（空格加井号）两者之一
- token 中的空白字符**必须**用 `-` 替代，以区别于多段 body
- **唯一例外**：`BREAKING CHANGE` **可以**作为带空格的 token 使用
- `BREAKING-CHANGE` 与 `BREAKING CHANGE` 作为 footer token 时**同义**
- footer 每行**应当** ≤ 100 字符（commitlint `footer-max-line-length: 100`）

**常用 token**：

| token | 用途 | 示例 |
|---|---|---|
| `BREAKING CHANGE` | 声明破坏性变更 | `BREAKING CHANGE: 移除 v1 配置格式支持` |
| `Refs` | 关联 issue 或被撤销的提交 | `Refs: #123` 或 `Refs: 676104e, a215868` |
| `Closes` | 合并后自动关闭 issue | `Closes: #123` |
| `Reviewed-by` | 代码评审者 | `Reviewed-by: Z` |
| `Co-authored-by` | 共同作者（**GitHub 会据此添加头像与贡献记录**） | `Co-authored-by: Name <email@example.com>` |
| `Signed-off-by` | 开发者原创声明（DCO） | `Signed-off-by: Name <email@example.com>` |

---

## 7. 破坏性变更

破坏性变更**必须**通过以下**两种方式之一**声明，位置在 **header 或 footer**：

**方式一：`!` 标记（位于 header）**

`!` **必须**紧贴在冒号**之前**，即位于 `type` 或 `scope` 之后：

```text
feat!: drop support for Node 6
feat(api)!: change response envelope
```

若使用 `!`，footer 中的 `BREAKING CHANGE:` **可以**省略，此时 description 即被视为破坏性变更的说明。

**方式二：`BREAKING CHANGE` footer**

`BREAKING CHANGE` **必须**全大写，后接冒号、空格与说明：

```text
feat: allow provided config object to extend other configs

BREAKING CHANGE: `extends` key in config file is now used for extending other config files
```

**要点**：

- 破坏性变更**可以**属于**任意 type**，不限于 `feat`——`fix!:`、`refactor!:` 同样合法
- 两种方式**可以**同时使用（此时**应当**在两者中分别写明，避免读者只看到一处）
- `BREAKING CHANGE` 的大小写是**规范中唯一的例外**：其余单位均不区分大小写，但此 token **必须**大写

---

## 8. 与 SemVer 和 CHANGELOG 的对应

这是采用 Conventional Commits 的**根本目的**：让版本号与变更日志可以从提交历史**自动推导**。

### 8.1 版本号推导

| 提交内容 | 版本递增段 | 说明 |
|---|---|---|
| 含 `BREAKING CHANGE`（任意 type） | **MAJOR** | `1.4.2` → `2.0.0` |
| `feat` | **MINOR** | `1.4.2` → `1.5.0` |
| `fix` | **PATCH** | `1.4.2` → `1.4.3` |

依据：[Semantic Versioning 2.0.0](https://semver.org/) 摘要节 + Conventional Commits FAQ。

### 8.2 CHANGELOG 归属

采用 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 组织方式时，`conventional-changelog` 的默认分组为：

- `feat` → **Features**（新功能）
- `fix` → **Bug Fixes**（缺陷修复）
- `perf` → **Performance Improvements**（性能改进）
- `revert` → **Reverts**（回退）
- 其余 type 默认**不出现**在 CHANGELOG 中（可通过 `hidden` 配置调整）

---

## 9. revert 提交

Conventional Commits **未规定** revert 的具体行为，而是交由工具处理。本规范采纳规范 FAQ 中的推荐做法：

- 使用 `revert` 作为 type
- 在 footer 中用 `Refs` 标注被撤销的提交 SHA

```text
revert: let us never again speak of the noodle incident

Refs: 676104e, a215868
```

使用 `git revert` 自动生成的提交**应当**在保留机器可读 footer 的前提下，把标题改写为符合本规范的祈使句。`git revert` 默认生成的 body（`This reverts commit <sha>.`）**可以**保留。

**注意**：`revert` 撤销的是**任意先前提交**，不限于最近一次。撤销多个提交时，**应当**在 footer 中逐一列出 SHA。

---

## 10. GitHub 平台约定

### 10.1 自动关闭 issue

在 footer 或 body 中使用 GitHub 的关闭关键字，PR 合并后会自动关闭对应 issue：

```text
Closes #123
Fixes #123
Resolves #123
```

同一关键字后列举多个 issue：`Closes #123, #124`。
仅作引用而不关闭，使用 `Refs #123`。

### 10.2 squash merge 场景

使用 GitHub 的 [Squash and merge](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/about-merge-methods-on-github) 时，PR 标题会成为最终提交的标题。因此：

- PR 标题**必须**同样遵循本规范（`type(scope): description`）
- 分支内的中间提交**可以**不规范，但**应当**在合并前整理
- 合并时**应当**检查 GitHub 预填的提交信息，删除 `* fix typo` 一类的自动汇总行

### 10.3 共同作者

在提交信息末尾添加 `Co-authored-by` trailer，GitHub 会将其识别为共同作者并计入贡献图：

```text
Co-authored-by: Name <email@example.com>
```

### 10.4 提交者邮箱

向公开仓库提交时**必须**使用 GitHub 提供的隐私邮箱，避免真实邮箱写入永久公开的提交历史：

```bash
# 邮箱格式：<数字ID>+<用户名>@users.noreply.github.com
git config user.name "Your Name"
git config user.email "12345678+username@users.noreply.github.com"
```

`--author` 只覆盖 author，**不覆盖 committer**；两者均由 `user.name` / `user.email` 决定。发布前**必须**核验两者是否均为隐私邮箱。

**禁止**把邮箱原文输出到终端、日志或会话记录——核验命令本身就是一个泄露面（对应 [CWE-532](https://cwe.mitre.org/data/definitions/532.html)）。**应当**只输出判定结果，命中条数为 `0` 即通过。格式串**应当**避免 `<`、`>`、`|` 等 shell 特殊字符，并使用 `--all` 覆盖非 HEAD 可达的历史。

Bash / Git Bash：

```bash
# 输出「非隐私邮箱」的条数：0 为通过
git log --all --format="%ae%n%ce" | sort -u \
  | grep -cvE '^([0-9]+\+)?[A-Za-z0-9-]+@users\.noreply\.github\.com$'
```

PowerShell：

```powershell
# 输出「非隐私邮箱」的条数：0 为通过
$bad = git log --all --format="%ae%n%ce" | Sort-Object -Unique |
       Where-Object { $_ -notmatch '^(\d+\+)?[A-Za-z0-9-]+@users\.noreply\.github\.com$' }
"non-noreply hits: $($bad.Count)"
```

若结果非 `0`，**应当**只报告命中条数与涉及的提交范围，而**不得**回显地址本身。需要定位具体提交时可使用 `git log --all --format="%h %ae"`，但须注意该输出同样包含地址。

详见 [GitHub 文档：设置提交邮箱](https://docs.github.com/en/account-and-profile/setting-up-and-managing-your-personal-account-on-github/managing-email-preferences/setting-your-commit-email)。

---

## 11. 工具链

规范需要**生成**与**校验**两个环节配合：commitizen 负责写对，commitlint 负责拦住写错的。

### 11.1 commitlint（提交时强制校验）

```bash
npm install --save-dev @commitlint/cli @commitlint/config-conventional husky
```

`commitlint.config.js`：

```js
export default {
  extends: ['@commitlint/config-conventional'],
  // 如需扩展 type，在此登记
  rules: {
    'type-enum': [
      2,
      'always',
      [
        'build', 'chore', 'ci', 'docs', 'feat', 'fix',
        'perf', 'refactor', 'revert', 'style', 'test',
      ],
    ],
  },
};
```

启用 Git hook：

```bash
npx husky init
echo 'npx --no -- commitlint --edit "$1"' > .husky/commit-msg
```

此后不符合规范的提交信息会被**直接拒绝**。

### 11.2 commitizen（交互式生成）

```bash
npm install -g commitizen
commitizen init cz-conventional-changelog --save --save-exact
```

用 `git cz` 替代 `git commit`（先 `git add`），按提示选择 type、填写 scope（选填）与 subject。

### 11.3 手工核验

```bash
# 查看最近若干条提交的 header
git log --oneline -20

# 校验单条信息（无需提交）
echo "feat(auth): add OAuth2 login" | npx commitlint
```

---

## 12. 示例集

**仅 header，无 body 与 footer**

```text
docs: correct spelling of CHANGELOG
```

**带 scope**

```text
feat(lang): add Polish language
```

**带 `!` 标记的破坏性变更**

```text
feat!: send an email to the customer when a product is shipped
```

```text
feat(api)!: send an email to the customer when a product is shipped
```

**同时使用 `!` 与 `BREAKING CHANGE` footer**

```text
feat!: drop support for Node 6

BREAKING CHANGE: use JavaScript features not available in Node 6.
```

**仅用 footer 声明破坏性变更**

```text
feat: allow provided config object to extend other configs

BREAKING CHANGE: `extends` key in config file is now used for extending other config files
```

**多段 body 与多个 footer**

```text
fix: prevent racing of requests

Introduce a request id and a reference to latest request. Dismiss
incoming responses other than from latest request.

Remove timeouts which were used to mitigate the racing issue but are
obsolete now.

Reviewed-by: Z
Refs: #123
```

**revert**

```text
revert: let us never again speak of the noodle incident

Refs: 676104e, a215868
```

---

## 13. 反例对照表

| ❌ 错误写法 | 违反的规则 | ✅ 正确写法 |
|---|---|---|
| `feat : add login` | 冒号前多空格 | `feat: add login` |
| `feat:add login` | 冒号后缺空格 | `feat: add login` |
| `Feat: add login` | type 必须小写 | `feat: add login` |
| `feature: add login` | 非标准 type | `feat: add login` |
| `init: 初始化项目` | `init` 非标准 type | `chore: 初始化项目` |
| `update code` | 缺 type | `chore: update dependencies` |
| `fix: Fixed the login bug.` | 非祈使语气、首字母大写、句末句号 | `fix: correct login failure on expired token` |
| `fix: 修复了登录失败的问题。` | 句末句号、描述冗余 | `fix: 修正令牌过期时的登录失败` |
| `feat(用户 登录): add login` | scope 含空格、应小写 | `feat(auth): add login` |
| `feat(auth): 新功能` | description 无信息量 | `feat(auth): support OAuth2 login` |
| `feat(auth): add login`<br>（下一行直接接 body） | body 前缺空行 | header 后空一行再写 body |
| `chore: bump deps`<br>`BREAKING CHANGE: ...` | footer 与 body 之间缺空行 | 空一行后写 footer |
| `fix: 修复bug` | 无标点分隔、描述过简 | `fix(parser): handle empty array input` |

---

## 14. 依据来源

一手来源（规范性依据）优先列出：

1. [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) —— 本规范的强制基准，第 1–7、9 节均直接引自其 Specification 与 FAQ
2. [@commitlint/config-conventional](https://github.com/conventional-changelog/commitlint/tree/master/%40commitlint/config-conventional) —— `type` 白名单与全部校验阈值（`header-max-length`、`subject-case`、`subject-full-stop` 等）
3. [Angular 提交信息约定](https://github.com/angular/angular/blob/main/contributing-docs/commit-message-guidelines.md) —— commitlint 推荐 type 集合的源头
4. [Semantic Versioning 2.0.0](https://semver.org/) —— 第 8.1 节版本号推导
5. [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/) —— 第 8.2 节 CHANGELOG 组织方式
6. [git-interpret-trailers](https://git-scm.com/docs/git-interpret-trailers) —— 第 6 节 footer 约定的来源
7. [BCP 14：RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) 与 [RFC 8174](https://www.rfc-editor.org/info/rfc8174) —— 本文规范性用语的定义；RFC 8174 明确关键词**仅在全大写时**具有规范含义
8. [GitHub 文档：设置提交邮箱](https://docs.github.com/en/account-and-profile/setting-up-and-managing-your-personal-account-on-github/managing-email-preferences/setting-your-commit-email) —— 第 10.4 节
9. [GitHub 文档：用关键字关联 issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue) —— 第 10.1 节
10. [GitHub 文档：创建含多位作者的提交](https://docs.github.com/en/pull-requests/committing-changes-to-your-project/creating-and-editing-commits/creating-a-commit-with-multiple-authors) —— 第 10.3 节
11. [GitHub 文档：关于合并方式](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/about-merge-methods-on-github) —— 第 10.2 节 squash merge
12. [A Note About Git Commit Messages](https://tbaggery.com/2008/04/19/a-note-about-git-commit-messages.html) —— Tim Pope 的 50/72 规则，第 4 节长度建议的出处（**社区惯例，非规范**）

---

## 15. 修订记录

### v2.2 — 增加英文版

新增 [commit-convention.en.md](commit-convention.en.md)，与本文件保持**章节与引用的一一对应**（各 16 个二级章节、12 条引用）。

两份文件**必须**同步修订：任何一方新增、修改或删除规则时，另一方**必须**在同一次变更中完成对应更新。仅改动其中一份即视为文档缺陷。

### v2.1 — 补齐引用的闭合性

按"每条规则可追溯到引用、每个引用对应至少一条规则"的标准复查，修补三处缺口：

| 缺口 | 处理 | 依据 |
|---|---|---|
| 规范性用语只引 RFC 2119 | 改为 BCP 14（RFC 2119 + RFC 8174），并说明关键词仅在全大写时具规范含义 | [RFC 8174](https://www.rfc-editor.org/info/rfc8174) |
| §10.2 squash merge 无出处 | 补 GitHub 合并方式文档 | [GitHub 合并方式](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/about-merge-methods-on-github) |
| §2.2 禁止 type 清单无出处 | 显式标注为"本规范自行约定"，不冒充规范条文 | — |
| §10.4 核验命令会把邮箱原文回显到终端 | 改为只输出判定条数的形式，加 `--all`，并避免格式串含 shell 特殊字符 | [CWE-532](https://cwe.mitre.org/data/definitions/532.html) |

### v2.0 — 依一手规范全面校订

**修正的错误**

| 项 | 原文 | 修正 |
|---|---|---|
| header 格式 | `type(scope) : subject` | `type(scope): subject`，冒号紧贴括号、后接一个空格 |
| `BREAKING CHANGE` 归类 | 列在 type 清单中 | 移出 type，作为 footer token 与 `!` 标记说明（第 7 节） |
| `init` | 列为可用 type | 删除；`type-enum` 收敛为 commitlint 标准 11 项 |
| description 长度 | "不超过50个字符" | 拆分为规范（无规定）/ commitlint（100）/ 社区建议（50-72）三个来源 |
| `revert` 含义 | "撤销上一次的 commit" | 可撤销任意先前提交，补充 `Refs` footer 写法 |
| `build` 示例 | "grunt换成了 npm" | 更正为"影响构建系统或外部依赖"，示例降级为 scope |
| `style` 含义 | "代码格式改变" | 补充"不影响代码含义"这一限定 |
| type 清单收尾 | `……` | 删除省略号，改为显式的扩展准入规则（第 2.3 节） |

**补充的内容**

- 完整三段式骨架与逐行强制性说明（第 1 节）
- footer 构造规则：token、两种分隔符、`-` 替代空格、`BREAKING-CHANGE` 同义（第 6 节）
- 大小写规则与 `BREAKING CHANGE` 大写例外
- description 的语态、大小写、句末标点规则（第 4 节）
- body 与 footer 的空行要求（第 5、6 节）
- 与 SemVer / CHANGELOG 的对应表（第 8 节）
- scope 的命名约定与取值建议（第 3 节）
- GitHub 平台约定：issue 自动关闭、squash merge、共同作者、隐私邮箱（第 10 节）
- 完整工具链：commitlint + husky + commitizen 及可运行的配置（第 11 节）
- 反例对照表（第 13 节）
- 目录与规范性用语说明

**体例调整**

- References 改为按一手来源优先排序，并逐条标注其在本文中的对应章节
- 移除二手博客来源（原文 `init` 等错误即源于此）
- 原第 21、63 行整段粘贴的英文改为中文表述，英文仅保留在示例代码块中
- 原文用列表符号充当标题的写法改为标准 Markdown 标题层级
