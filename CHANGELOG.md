# Changelog

本文件记录本项目的所有重要变更。

格式遵循 [Keep a Changelog 1.1.0](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [Semantic Versioning 2.0.0](https://semver.org/lang/zh-CN/)。

变更分类沿用 Keep a Changelog 的标准标题（Added / Changed / Deprecated / Removed / Fixed / Security），以保证与 `conventional-changelog`、`semantic-release` 等工具链互操作。条目标题用英文，正文用中文。

## [1.0.0] - 2026-10-01

首个版本。经人工核验后按 SemVer 定为 1.0.0：功能完整、可供使用，公开接口自此冻结——规则的增删、脚本参数与退出码约定、豁免清单格式的变更都需要主版本号或次版本号。

以下内容自开发以来累积，构成 1.0.0。

> **实现状态**：`references/checks.md` 登记的 31 条规则**全部有明确的执行方式**——多数由脚本或 CI 自动检查；`GIT-002`、`GIT-003`、`DOC-004` 由 Agent 判断而非脚本强制，因为它们的判据依赖上下文，硬编码反而会制造误报。完整的"规则 → 执行方式"对照见 [`references/checks.md`](.dsh/skills/github-project-publisher/references/checks.md) 第 7 节。
>
> 保留这一节的原因：把规则登记在目录里却当作已被检查，正是本 skill 要防止的那类错误。文档比实现更乐观，与文档比实现更保守，同样有害。

### Added

- `references/README.md`：**规范层索引**。说明三层结构（判定标准 / 依据 / 操作）、阅读顺序，以及「为什么是这六份文件，而不是更少或更多」——包括依据为何必须单独成文件（否则规则与依据互相背书，读者分不清哪句是引用、哪句是本项目自订），操作层为何与判定层分开（否则会出现把「默认执行」的事拿去提问这一具体错误）
- README 中英双版新增 **「5.1 实现逻辑：三层与五步」**：把「扫描 → 定级 → 报告 → 人工 → 上传」五步与规范层 / 执行层 / 呈现层的分工写清楚，并说明规范与执行为何必须分开、报告为何必须带「未能覆盖」清单
- README 中英双版的目录结构图按**规范层 / 执行层**重排，并为每个脚本标注职责
- DSH skill `github-project-publisher`，含 `SKILL.md` 与 `references/` 文档集
- 提交规范 `references/commit-convention.md` 及英文镜像版，依 [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) 与 `@commitlint/config-conventional` 全面校订
- 依据来源清单 `references/standards.md`：每条规则可追溯到一手来源，每个来源对应至少一条可执行规则
- 检查项目录 `references/checks.md`：规则 ID、四级严重度、判定与修复方式
- 交互决策分级 `references/interaction.md`：区分必问、二次确认、默认执行与红线四类
- 文档模板集 `references/templates.md`：README、CHANGELOG、Release 文案、审计报告
- Python 脚本（纯标准库，零依赖）：敏感信息扫描、noreply 身份核验、SHA256 校验和生成、仓库审计汇总
- 脚本自测 `tests/selftest.py`（1.0.0 起位于仓库根，不随 skill 分发），在临时目录中运行，不触碰真实仓库状态
- 检查项 `GIT-005`：探测「已被跟踪、又匹配 `.gitignore`」的文件。忽略规则对这类文件完全无效，而它的存在会制造"已经安全了"的错觉——这比不写 `.gitignore` 更危险。实现方式为 `git ls-files --cached --ignored --exclude-standard`
- 检查项 `GIT-004`：探测历史中的超大文件。超过 50 MB 为 MINOR（推送时警告、仓库体积永久变大），超过 100 MB 覆盖为 MAJOR（GitHub 会直接拒收推送）。实现方式为 `git rev-list --objects --all` 配合 `git cat-file --batch-check` 的一次批量查询；可用 `--no-large-files` 跳过，跳过时记入未覆盖清单
- 控制台摘要现在会显示「未能覆盖」条目。此前这类信息只写进 Markdown 报告，而 `--dry-run` 不写报告——于是覆盖缺口在最容易被用来"快速看一眼"的模式下完全不可见，容易把"没检查"误读成"检查通过"
- 根目录规范文件：`.gitignore`、`.gitattributes`、`LICENSE`、`SECURITY.md`、`CONTRIBUTING.md`
- GitHub 平台文件：Issue 模板、PR 模板、Dependabot 配置
- `.github/workflows/ci.yml`：CI 质量门禁——自测、敏感信息扫描、提交身份核验、编码与行尾检查、双语一致性检查、`SKILL.md` frontmatter 校验。**工作流不含任何发布步骤**，自动化不得绕过两道人工闸门
- `.github-upload-audit/allowlist.txt`：显式豁免清单。审计报告不入库，但本清单作为配置入库，否则豁免记录会随报告一起丢失
- 脚本的 **Python 版本守卫**：解释器低于 3.9 时以退出码 2 退出，并说明它实际拿到的是哪个解释器。此前没有守卫，旧解释器会在深处抛出与真实原因无关的报错，容易被误判成"脚本有 bug"。判据抽成可测函数 `python_version_supported`，由自检覆盖
- `SKILL.md` 与 README 补齐 **Python 版本要求（3.9+）与解释器查找顺序**：`python` → `python3` → `py -3` → `load_workspace_dependencies` 返回的 DSH 自带解释器。此前四份文档中只有 `scripts/README.md` 与 `CONTRIBUTING.md` 提到版本，而 `SKILL.md`（Agent 实际读取的那份）一个字都没写；"`python` 不一定存在、也不一定是预期版本"则完全没有记录
- CI 矩阵增加 **Python 3.14**。只在 3.9 与 3.13 上验证，等于默认新版本不会破坏任何东西——而本机环境恰好已经跑在 3.14 上
- `SKILL.md` 补充 DSH 沙箱下的推送故障处置：schannel TLS 后端在受限会话中无法获取凭据（`SEC_E_NO_CREDENTIALS`），应对本仓库改用 OpenSSL；`!<命令>` 形式的凭据助手需要启动 shell，同样被沙箱拦下，应当请求用户批准而不是绕开——尤其不得把令牌塞进远程 URL

### Security

- 敏感信息扫描覆盖四个扫描面：工作区、暂存区、git 历史、日志与产物
- 命中即硬阻断：发现 BLOCKER 时禁止提交与推送，并输出文件与行号
- 审计报告不回显密钥原文，仅输出位置与掩码，避免报告本身成为泄露源（对应 [CWE-532](https://cwe.mitre.org/data/definitions/532.html)）
- 提交身份强制使用 GitHub noreply 邮箱，核验命令仅输出判定结果，不打印地址
- `SHA256SUMS` 以 UTF-8 无 BOM、LF 行尾写入，确保 Linux 侧 `sha256sum -c` 可用
- 新建仓库默认私有：先完成上传与完整检查，再人工决定是否公开

### Changed

- **把自测移出 skill bundle**：`scripts/selftest.py` → `tests/selftest.py`。它是**开发用基础设施**，skill 的使用者不会运行它；而它携带的约 110 条伪造样本会迫使**每一个**安装本 skill 的仓库去写豁免。移出后 skill 包体量减少约 28%（脚本 6876 → 约 4930 行），且 skill 自带的豁免清单从 8 条缩到 1 条（只剩 `scan_secrets.py` 的规则字面量）。自测能力不受影响：仓库的 CI 与本地仍完整运行它（80 个用例）。代价：安装后的副本不再能自证——验证能力只在仓库里。

### Fixed


- **修正"项目级安装会把误报带给宿主项目"**：收窄自扫描判据后只剩宿主项目的豁免清单生效，于是把本 skill **项目级安装**进任何仓库，那个仓库都会收到 **57 条 BLOCKER** 误报（`selftest.py` 54 条、`scan_secrets.py` 3 条），而它并没有做错任何事、也没有立场替别人的文件写豁免。现改为**两份清单合并生效**：宿主项目的 `.github-upload-audit/allowlist.txt` 与 skill 目录内的 `skill-allowlist.txt`。两份格式与「理由必填」要求完全相同，报告逐条标明来源（`[skill]` / `[项目]`）。实测宿主项目已降为 **0 条**，且 skill 自带清单**不会**放过非 skill 路径——有回归用例守住这一点
- **修正一个危险的清理缺陷**：自测在系统临时区策略下会**删除整个系统临时目录**——`_cleanup_work_dir` 无条件执行 `force_rmtree(root.parent)`，而该策略下 `root` 就是 `<TEMP>/gpp-selftest-XXXX`，其父目录即 `<TEMP>` 本身。实测中它删掉了会话的临时目录，导致此后所有受限沙箱命令都因"临时目录不存在"被拒绝。现只在父目录确实是我们自己的 `.selftest-tmp` 时才一并收掉
- **修正自扫描豁免的盲区**：原先按**文件名整份豁免** 4 个文件，实测静默吞掉 112 条命中，其中 `_common.py` 与 `audit_repo.py` 本来一条都不产生（豁免纯属多余），而报告仍写着"并未跳过这些文件"——报告与事实相反。现改为**文件名 + 命中文本含正则元字符**双重判据；非正则字面量的命中照常上报，改由 `.github-upload-audit/allowlist.txt` 逐条显式豁免（现有 8 条目，全部附理由并进入报告）。已实测：真实形态的令牌放进名为 `selftest.py` 的文件会被报为 BLOCKER，改动前则被无声放过
- 删除 `selftest.py` 中废弃的 `WORK_DIR_NAME`（旧命名方案残留，定义后从未引用）与重复的 `_TEMP_HOLDERS` 定义
- **消除了一处重复实现**：扫描编排（收集各扫描面文档 → 扫描 → 打来源标签）此前在 `scan_secrets._run` 与 `audit_repo._run_secret_scan` 里各写了一份，于是「修一处必漏另一处」——上一版那个假 BLOCKER 缺陷正是这样产生的。现抽取为 `scan_secrets.collect_and_scan`，两个入口共用；扫描面标签也改由收集过程返回，不再从参数另行推导（此前两者的**顺序甚至不一致**）
- **修正 `--no-artifacts` 实际无效**：`audit_repo` 的两个分支都无条件向扫描器传入 `--artifacts`，该开关从未生效；而"扫描面"标签又另行按该开关推导，结果是**报告声明未扫描产物面、实际却扫了**。现在四种开关组合均按预期生效，并有逐一验证
- 重新生成 `SHA256SUMS`：此前改动后未同步，校验已失效（15 条中 5 条不匹配）。**这一点是审计自身报出来的**
- **修正了一处会产生假 BLOCKER 的缺陷**：占位符判定一律回查工作树文档，而同一路径在历史里的行号与工作树**未必一致**——上游多插几行就整体位移，历史中的文档示例因而被误报成 BLOCKER。现在每条发现项记录它来自哪份文档（工作树 / 产物 / 暂存区 / 提交），判定回查**产生它的那一份**。该缺陷在仓库出现第二次提交、README 行号位移之后立刻显形：审计突然报出 4 条 BLOCKER，全部指向 AWS 的公开示例密钥 `AKIAIOSFODNN7EXAMPLE`
- 新增回归用例 `test_history_placeholder_survives_line_shift`，走**审计那条路径**，并断言"确实扫了历史面"以防用例空过；已验证该用例在移除来源标签时确实失败
- 修正了提交规范中 `type(scope) : subject` 的多余空格：正确形式为 `type(scope): subject`
- 修正了将 `BREAKING CHANGE` 误列为 `type` 的概念性错误：它是 footer token 或 `!` 标记，可属于任意 type
- 移除了非标准 type `init`
- 修正了"description 不超过 50 字符"的表述：规范对长度无规定，100 为 commitlint 强制值，50 为社区建议
- 修正了把 `--author` 当作可同时设置 committer 的误解：`--author` 只覆盖 author

---

[Unreleased]: https://github.com/cicada478/dsh-github-publisher/commits/main
[1.0.0]: https://github.com/cicada478/dsh-github-publisher/releases/tag/v1.0.0
