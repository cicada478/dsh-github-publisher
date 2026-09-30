# Changelog

本文件记录本项目的所有重要变更。

格式遵循 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [Semantic Versioning 2.0.0](https://semver.org/lang/zh-CN/)。

变更分类沿用 Keep a Changelog 的标准标题（Added / Changed / Deprecated / Removed / Fixed / Security），以保证与 `conventional-changelog`、`semantic-release` 等工具链互操作。条目标题用英文，正文用中文。

## [Unreleased]

本项目尚未发布正式版本。以下内容构成首个版本，待人工核验后按 SemVer 确定版本号。

> **实现状态**：`references/checks.md` 登记的 31 条规则**全部有明确的执行方式**——多数由脚本或 CI 自动检查；`GIT-002`、`GIT-003`、`DOC-004` 由 Agent 判断而非脚本强制，因为它们的判据依赖上下文，硬编码反而会制造误报。完整的"规则 → 执行方式"对照见 [`references/checks.md`](.dsh/skills/github-project-publisher/references/checks.md) 第 7 节。
>
> 保留这一节的原因：把规则登记在目录里却当作已被检查，正是本 skill 要防止的那类错误。文档比实现更乐观，与文档比实现更保守，同样有害。

### Added

- DSH skill `github-project-publisher`，含 `SKILL.md` 与 `references/` 文档集
- 提交规范 `references/commit-convention.md` 及英文镜像版，依 [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) 与 `@commitlint/config-conventional` 全面校订
- 依据来源清单 `references/standards.md`：每条规则可追溯到一手来源，每个来源对应至少一条可执行规则
- 检查项目录 `references/checks.md`：规则 ID、四级严重度、判定与修复方式
- 交互决策分级 `references/interaction.md`：区分必问、二次确认、默认执行与红线四类
- 文档模板集 `references/templates.md`：README、CHANGELOG、Release 文案、审计报告
- Python 脚本（纯标准库，零依赖）：敏感信息扫描、noreply 身份核验、SHA256 校验和生成、仓库审计汇总
- 脚本自测 `scripts/selftest.py`，在临时目录中运行，不触碰真实仓库状态
- 检查项 `GIT-005`：探测「已被跟踪、又匹配 `.gitignore`」的文件。忽略规则对这类文件完全无效，而它的存在会制造"已经安全了"的错觉——这比不写 `.gitignore` 更危险。实现方式为 `git ls-files --cached --ignored --exclude-standard`
- 检查项 `GIT-004`：探测历史中的超大文件。超过 50 MB 为 MINOR（推送时警告、仓库体积永久变大），超过 100 MB 覆盖为 MAJOR（GitHub 会直接拒收推送）。实现方式为 `git rev-list --objects --all` 配合 `git cat-file --batch-check` 的一次批量查询；可用 `--no-large-files` 跳过，跳过时记入未覆盖清单
- 控制台摘要现在会显示「未能覆盖」条目。此前这类信息只写进 Markdown 报告，而 `--dry-run` 不写报告——于是覆盖缺口在最容易被用来"快速看一眼"的模式下完全不可见，容易把"没检查"误读成"检查通过"
- 根目录规范文件：`.gitignore`、`.gitattributes`、`LICENSE`、`SECURITY.md`、`CONTRIBUTING.md`
- GitHub 平台文件：Issue 模板、PR 模板、Dependabot 配置
- `.github/workflows/ci.yml`：CI 质量门禁——自测、敏感信息扫描、提交身份核验、编码与行尾检查、双语一致性检查、`SKILL.md` frontmatter 校验。**工作流不含任何发布步骤**，自动化不得绕过两道人工闸门
- `.github-upload-audit/allowlist.txt`：显式豁免清单。审计报告不入库，但本清单作为配置入库，否则豁免记录会随报告一起丢失

### Security

- 敏感信息扫描覆盖四个扫描面：工作区、暂存区、git 历史、日志与产物
- 命中即硬阻断：发现 BLOCKER 时禁止提交与推送，并输出文件与行号
- 审计报告不回显密钥原文，仅输出位置与掩码，避免报告本身成为泄露源（对应 [CWE-532](https://cwe.mitre.org/data/definitions/532.html)）
- 提交身份强制使用 GitHub noreply 邮箱，核验命令仅输出判定结果，不打印地址
- `SHA256SUMS` 以 UTF-8 无 BOM、LF 行尾写入，确保 Linux 侧 `sha256sum -c` 可用
- 新建仓库默认私有：先完成上传与完整检查，再人工决定是否公开

### Fixed

- 修正了提交规范中 `type(scope) : subject` 的多余空格：正确形式为 `type(scope): subject`
- 修正了将 `BREAKING CHANGE` 误列为 `type` 的概念性错误：它是 footer token 或 `!` 标记，可属于任意 type
- 移除了非标准 type `init`
- 修正了"description 不超过 50 字符"的表述：规范对长度无规定，100 为 commitlint 强制值，50 为社区建议
- 修正了把 `--author` 当作可同时设置 committer 的误解：`--author` 只覆盖 author

---

[Unreleased]: https://github.com/cicada478/dsh-github-publisher/commits/main
