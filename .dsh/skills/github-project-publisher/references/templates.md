# 文档模板集

生成文档时使用本文件的模板。模板是**骨架**，不是填空练习——其中的说明性注释必须替换为真实内容，而不是保留。

依据来源见 [`standards.md`](standards.md)。

---

## 0. 双语输出约定

沿用本仓库的既定模式：**中文为主文件，英文为 `.en.md` 镜像。**

| 中文 | 英文 |
|---|---|
| `README.md` | `README.en.md` |
| `docs/xxx.md` | `docs/xxx.en.md` |

规则：

- 两份文件顶部互相链接：`[English](README.en.md) | 中文` / `English | [中文](README.md)`
- 两份文件**必须**保持章节结构一一对应
- 改动其中一份时，**必须**在同一次变更中更新另一份
- 校验方式：比对两份文件的标题数量与引用数量是否一致（对应规则 `DOC-005`）

**为什么是两份文件而不是单文件内联双语**：内联会使文档长度翻倍，且每条规则要维护两份，容易漂移；两份文件各自读起来自然，且符合 GitHub 的既有惯例。

---

## 1. README 模板

```markdown
# <项目名>

[English](README.en.md) | 中文

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![<语言/运行时>](https://img.shields.io/badge/<...>-<...>-blue.svg)

> 一句话说明这是什么、给谁用。

## 目录

- [1. 这是什么](#1-这是什么)
- [2. 安装](#2-安装)
- [3. 使用](#3-使用)
- [4. 依据来源](#4-依据来源)
- [5. 许可](#5-许可)

## 1. 这是什么

<!-- 三到五句。说明问题域、能力边界与不做什么。 -->

## 2. 安装

<!-- 前置条件、安装命令、验证方式。每条命令都应可直接复制执行。 -->

## 3. 使用

### 3.1 基本用法

### 3.2 使用举例

<!-- 给 3~5 个可直接复制的例子，覆盖常见场景。 -->

## 4. 依据来源

<!--
  若项目遵循任何公开规范，必须逐条列出并标注出处。
  只列真正被遵循的；列了却不遵循比不列更糟。
-->

| 依据来源 | 支撑的规则 |
|---|---|
| [<规范名>](<url>) | <具体遵循了什么> |

## 5. 已知限制

<!--
  必须包含这一节。声明工具做不到什么，是让使用者能正确判断结论强度的前提。
  把限制写在 README 里，而不是只在出问题后才提及。
-->

## 6. 许可

[<许可证名>](LICENSE) © <年份> <版权持有人>
```

### 撰写要点

| 要点 | 说明 |
|---|---|
| 徽章 | 只放**不依赖仓库状态**的徽章（许可证、语言版本）。仓库尚未创建时，stars / issues 类徽章会 404 |
| 目录 | 章节超过 5 个时提供目录 |
| 示例 | 每个示例都应可直接复制执行，且结果可预期 |
| 依据来源 | **只列真正遵循的规范**。装饰性引用会让人无法判断哪些约束是真实存在的 |
| 已知限制 | 不可省略。没有限制声明的安全类工具，会被误读为"通过即安全" |

---

## 2. CHANGELOG 模板

依 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。分类标题用英文（保证与 `conventional-changelog` 等工具互操作），条目正文用项目主语言。

```markdown
# Changelog

本文件记录本项目的所有重要变更。

格式遵循 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning 2.0.0](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
<!-- 新功能。对应 conventional commits 的 feat -->

### Changed
<!-- 对既有功能的变更。对应 refactor，部分 feat 也归入此处 -->

### Deprecated
<!-- 即将移除的功能 -->

### Removed
<!-- 本版移除的功能 -->

### Fixed
<!-- 缺陷修复。对应 fix -->

### Security
<!-- 安全相关修复。任何凭据泄露、校验绕过、权限问题都归此类并置顶 -->

## [x.y.z] - YYYY-MM-DD

### Added
- <条目>（<提交短哈希或 PR 链接>）

[Unreleased]: https://github.com/<owner>/<repo>/compare/vx.y.z...HEAD
[x.y.z]: https://github.com/<owner>/<repo>/compare/vx.y.w...vx.y.z
```

### 从提交历史生成

| 提交 type | 归入分类 | 是否收录 |
|---|---|---|
| `feat` | Added | ✅ |
| `fix` | Fixed | ✅ |
| `perf` | Changed | ✅ |
| `revert` | Removed | ✅ |
| `refactor` | Changed | 视影响决定 |
| `docs` `style` `test` `build` `ci` `chore` | — | ❌ 默认不收录 |
| 任意含 `BREAKING CHANGE` | Changed（置顶并醒目标注） | ✅ 必须收录 |

### 撰写要点

- **写"用户能感知的变化"，不写"改了哪些文件"**
- `Security` 分类必须置顶于同版本其他分类之前
- 破坏性变更必须在版本标题下**独立醒目段落**说明迁移方式
- 版本号推导：`fix`→PATCH，`feat`→MINOR，含破坏性变更→MAJOR

---

## 3. Release 文案模板

Release 面向**已经使用该项目的用户**，因此重点不是"新增了什么"，而是**"我需要做什么"**。

```markdown
## <版本号> — <一句话主题>

<!-- 若含破坏性变更，此段落必须存在且置顶 -->

### ⚠️ 破坏性变更

**影响范围**：<谁会受影响>

**变更内容**：<什么行为变了>

**迁移方式**：
```<语言>
<可直接执行的迁移步骤>
```

---

### 新增

- <面向用户的描述，说明这个能力解决了什么问题>（#<issue>）

### 修复

- <用户此前会遇到什么现象，现在如何>（#<issue>）

### 变更

- <行为调整及其原因>

---

### 安装

```<语言>
<安装或升级命令>
```

### 校验和

本版本发布资产经 SHA-256 校验，清单见随附的 `SHA256SUMS`：

```bash
sha256sum -c SHA256SUMS
```

| 文件 | SHA-256 |
|---|---|
| `<文件名>` | `<前 16 位…>` |

<!--
  完整校验和写入 SHA256SUMS 文件并作为发布资产附带。
  表格中只展示前 16 位便于核对；完整值以文件为准。
-->

### 完整变更

<compare 链接>
```

### 撰写要点

| 要点 | 说明 |
|---|---|
| 破坏性变更置顶 | 用户最需要先知道的是"会不会弄坏我的东西" |
| 迁移步骤可执行 | 不要写"请相应调整"，要给出具体命令或代码 |
| 面向现象而非实现 | "修复了在某些网络下超时的问题"优于"修复了重试逻辑的 off-by-one" |
| 校验和必须出现 | 这是可验证性的体现，不是可选项 |
| 版本号推导需展示 | 说明为什么是 MINOR 而不是 PATCH，让人能复核 |

---

## 4. 审计报告模板

由 `scripts/audit_repo.py` 生成。以下为结构约定。

```markdown
# 上传前审计报告

| 项 | 值 |
|---|---|
| 运行时间（UTC） | <ISO 8601> |
| 项目根 | `<绝对路径>` |
| Python | <版本> |
| git | <版本> |
| gh | <版本> |
| 检测引擎 | `gitleaks` <版本> / `trufflehog` <版本> / 内置规则 |
| 扫描面 | 工作区 ✅ · 暂存区 ✅ · 历史 ✅ · 日志产物 ✅ |

## 结论

**<通过 / 未通过>** — BLOCKER <n> · MAJOR <n> · MINOR <n> · INFO <n>

## BLOCKER

| 规则 | 位置 | 说明 | 掩码证据 |
|---|---|---|---|
| `SEC-001` | `config/settings.py:42` | 疑似硬编码访问令牌 | `AKIA…(20)` |

## MAJOR

<!-- 同上结构；无则写「无」 -->

## MINOR

<!-- 同上结构；无则写「无」 -->

## 已应用的豁免

| 规则 | 路径 | 行 | 理由 |
|---|---|---|---|
| `SEC-001` | `.dsh/skills/*/references/*.md` | * | 文档示例中的占位密钥 |

## 已降级的占位符示例

<n> 条（不计入问题，见 `references/checks.md` 第 4.2 节）

## 默认执行项留痕

| 事项 | 结果 |
|---|---|
| 敏感信息扫描 | 四个扫描面，引擎 `<...>` |
| SHA256 校验和 | 生成 `SHA256SUMS`，覆盖 <n> 个文件 |
| `.gitignore` | 已存在 / 新增 <n> 条规则 |
| `.gitattributes` | 已存在 / 已创建 |
| 本地提交身份 | 已设为 noreply（仅 local） |
| 上传后复核 | 未执行（尚未上传） |

## 本次审计未能覆盖

<!-- 此节内容必须完整保留，不得删减 -->
```

### 撰写要点

| 要点 | 说明 |
|---|---|
| **绝不回显原文** | 掩码格式：前 4 字符 + `…` + `(长度)`；邮箱仅显示 `***@域名` |
| 必须记录引擎与扫描面 | 未安装外部工具时覆盖率显著下降，不记录等于虚报结论强度 |
| 必须记录豁免 | 无留痕的豁免等于静默放行 |
| 必须保留"未能覆盖"节 | 这是让使用者判断结论强度的唯一依据 |

---

## 5. 许可证选择指引

许可证**必须**询问用户，不得代为选择——它是法律声明，不是技术偏好。提供选项时按下表给出描述。

| 许可证 | 一句话描述 | 适用情形 |
|---|---|---|
| **MIT** | 最简短、最宽松；仅要求保留版权与许可声明 | 工具类、库、文档；希望被最广泛复用 |
| **Apache-2.0** | 在 MIT 基础上增加明确的专利授权与商标条款，并要求标注修改 | 可能涉及专利；需企业法务审核 |
| **GPL-3.0** | 强 copyleft；衍生作品必须以同样许可开源 | 希望保证项目及改进持续开源 |
| **MPL-2.0** | 文件级 copyleft；被修改的文件需开源，新增文件可闭源 | 介于 MIT 与 GPL 之间的折中 |
| **CC0-1.0 / Unlicense** | 放弃全部著作权，进入公有领域 | 注意：缺少完整的专利授权与担保免责条款，自由软件基金会不推荐用于软件 |

选定后：

1. 从 [SPDX](https://spdx.org/licenses/) 或 [Choose a License](https://choosealicense.com/) 取得**标准原文**，不要手工改写
2. 填写 `Copyright (c) <年份> <版权持有人>`
3. 同步更新包清单中的许可证字段（`package.json` 的 `license`、`pyproject.toml` 的 `license`），与 `LICENSE` 文件保持一致——不一致会触发规则 `META-002`
4. 在 README 末尾添加许可章节

---

## English summary

Templates are skeletons, and their guidance comments must be replaced with real content rather than kept. Bilingual output follows the repository convention: a Chinese primary file plus an `.en.md` mirror, cross-linked at the top, kept in one-to-one section correspondence, and validated by comparing heading and reference counts (rule `DOC-005`).

Three template-level requirements are worth calling out. First, a README **must** carry a "known limitations" section: a security tool that declares no limits will be read as "a pass means safe". Second, the audit report **must** record the engine and scan surfaces actually used, because falling back to built-in rules materially weakens coverage and omitting that fact overstates the strength of the conclusion. Third, a license is a legal statement rather than a technical preference, so it is always asked for and never chosen on the user's behalf, and the standard SPDX text is used verbatim rather than retyped.
