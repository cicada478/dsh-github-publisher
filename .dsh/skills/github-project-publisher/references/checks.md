# 检查项目录

[English summary](#english-summary)

本文件定义 skill 的全部检查项、规则编号、严重级别、豁免机制，以及**审计无法覆盖的范围**。

规则与依据来源的映射见 [`standards.md`](standards.md)。

---

## 1. 规则编号

格式：`<领域>-<三位序号>`

| 前缀 | 领域 | 典型对象 |
|---|---|---|
| `SEC` | 安全与隐私 | 密钥、凭据、个人信息、日志泄露 |
| `GIT` | 版本控制 | 提交身份、历史、忽略规则 |
| `META` | 项目元数据 | 许可证、仓库名、平台配置文件 |
| `DOC` | 文档 | README、CHANGELOG、社区健康文件 |
| `REL` | 发布物 | 校验和、发布资产 |
| `ID` | 审计自身 | 报告的时效性与一致性 |

编号**不回收**。删除某条规则后，其编号作废而非移作他用，以免历史报告出现歧义。

## 2. 严重级别与阻断策略

| 级别 | 含义 | 阻断行为 |
|---|---|---|
| `BLOCKER` | 可能造成不可逆的信息泄露或完整性问题 | **硬阻断**：禁止 `git commit` 与 `git push`。仅可通过逐项人工豁免放行，且豁免记入报告 |
| `MAJOR` | 会造成实际问题或显著降低可维护性 | 需人工确认后方可继续；未确认则视为未通过 |
| `MINOR` | 与业界规范不符，但不影响安全 | 提示，不阻断 |
| `INFO` | 仅记录，供人工判断 | 不阻断，不计入 findings 计数 |

**判定原则**：级别取决于**后果是否可逆**，而非修复难度。真实邮箱写入已推送的公开历史属于 `BLOCKER`——不是因为它难修，而是因为它**修不好**。

---

## 3. 检查项

### 3.1 安全与隐私（SEC）

| ID | 检查项 | 级别 | 依据 |
|---|---|---|---|
| `SEC-001` | 硬编码的 API key / 访问令牌（AWS、GitHub、Slack、Google、通用 `api_key` 赋值） | BLOCKER | [CWE-798](https://cwe.mitre.org/data/definitions/798.html)、[12-Factor §III](https://12factor.net/config) |
| `SEC-002` | 私钥文件内容（`-----BEGIN ... PRIVATE KEY-----`） | BLOCKER | CWE-798 |
| `SEC-003` | 代码或配置中的明文密码 | BLOCKER | CWE-798 |
| `SEC-004` | 含凭据的连接串（`mysql://user:pass@`、`postgres://`、`mongodb://`、`redis://`） | BLOCKER | CWE-798 |
| `SEC-005` | 支付凭证（通过 Luhn 校验的卡号、IBAN） | BLOCKER | CWE-798 |
| `SEC-006` | 个人信息（邮箱地址、身份证号、手机号） | BLOCKER | CWE-798 |
| `SEC-007` | 云凭据文件（`.aws/credentials`、含 `_authToken` 的 `.npmrc`、服务账号 JSON 的 `private_key`） | BLOCKER | CWE-798 |
| `SEC-008` | 敏感值被写入日志输出 | BLOCKER | [CWE-532](https://cwe.mitre.org/data/definitions/532.html) |
| `SEC-009` | JWT 形态的令牌 | BLOCKER | CWE-798 |
| `SEC-010` | 代码块内的疑似密钥（默认关闭，`--codeblock-soft` 开启时降为 MAJOR 但仍报告） | MAJOR | 本规范自行约定 |

**扫描面**（四者全部执行，缺一不可）：

| 参数 | 覆盖 |
|---|---|
| `--worktree` | 工作区全部受版本控制的文件 |
| `--staged` | `git diff --cached`，即即将提交的内容 |
| `--history` | 全部提交。**只从 HEAD 删除无效**，历史中的密钥仍可通过 `git log -p` 看到 |
| `--artifacts` | `*.log`、`dist/`、`build/`、notebook 输出、CI 配置 |

### 3.2 版本控制（GIT）

| ID | 检查项 | 级别 | 依据 |
|---|---|---|---|
| `GIT-001` | author 或 committer 邮箱不是 GitHub noreply 地址 | BLOCKER | [GitHub 提交邮箱](https://docs.github.com/en/account-and-profile/setting-up-and-managing-your-personal-account-on-github/managing-email-preferences/setting-your-commit-email) |
| `GIT-002` | 历史中存在真实邮箱，需要改写 | MAJOR | 同上 |
| `GIT-003` | 尚未推送，改写历史无外部影响（此时改写最安全） | INFO | 同上 |
| `GIT-004` | 历史中存在超大文件（>50 MB 警告，>100 MB 会被 GitHub 拒收） | MINOR | [GitHub 大文件限制](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github) |
| `GIT-005` | `.gitignore` 无法保护**已被跟踪**的文件 | MAJOR | [gitignore(5)](https://git-scm.com/docs/gitignore) |

> `GIT-005` 值得单独说明：`.gitignore` 对已跟踪文件**完全无效**。把 `.env` 加进 `.gitignore` 后仍然提交它，是极常见的错误。必须同时 `git rm --cached`。
>
> `GIT-004` 的级别**按体积分档**，上表登记的 `MINOR` 是较低档：
>
> | 体积 | 实际级别 | 后果 |
> |---|---|---|
> | 50 – 100 MB | `MINOR` | 推送时警告，且仓库体积永久变大 |
> | > 100 MB | **`MAJOR`**（由调用方覆盖） | **GitHub 直接拒收推送**，不改写历史就无法发布 |
>
> 之所以分档而不拆成两条规则：这是**同一个条件**（历史中的大对象）在不同量级下的后果差异，不是两个独立问题。之所以要覆盖级别：`MAJOR` 的定义是"会造成实际问题"，而 100 MB 确实会让发布流程卡死——用 `MINOR` 描述它，等于让一个会阻断发布的问题看起来只是提示。

### 3.3 项目元数据（META）

| ID | 检查项 | 级别 | 依据 |
|---|---|---|---|
| `META-001` | 缺少 `LICENSE` | BLOCKER | [Choose a License](https://choosealicense.com/) |
| `META-002` | 包清单声明的许可证与 `LICENSE` 文件不一致 | BLOCKER | [SPDX](https://spdx.org/licenses/) |
| `META-003` | 缺少 README | MINOR | [standard-readme](https://github.com/RichardLitt/standard-readme) |
| `META-004` | 缺少 `.gitignore` | MINOR | [github/gitignore](https://github.com/github/gitignore) |
| `META-005` | 缺少 `.gitattributes` | MAJOR | [gitattributes(5)](https://git-scm.com/docs/gitattributes) |
| `META-006` | 仓库名不是纯 ASCII | MAJOR | 本规范自行约定 |

> `META-005` 定为 MAJOR 的理由：Windows 开发者的 CRLF 会进入仓库，Linux/macOS 使用者看到整文件 diff。它不威胁安全，但会持续制造噪音与合并冲突。
>
> `META-006` 的理由：非 ASCII 仓库名在 URL 中会被百分号编码，在命令行、CI 脚本与克隆脚本中容易出错。GitHub 允许，但不建议。
>
> **判定对象的优先级**：先取已配置的**远程仓库名**，无远程时才回退到**本地目录名**，并在消息中标注来源。因此「本地目录是中文、远程仓库名是 ASCII」时，该命中属**预期内的提示**，不表示远程仓库名有问题；配置远程后它会自动消失。反过来说，如果只有本地目录名可查，就不要把这条命中当作远程仓库命名有误的证据。

### 3.4 文档（DOC）

| ID | 检查项 | 级别 | 依据 |
|---|---|---|---|
| `DOC-001` | 缺少 `CHANGELOG` | MINOR | [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) |
| `DOC-002` | 缺少 `SECURITY.md` | MINOR | [社区健康文件](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions) |
| `DOC-003` | 缺少 `CONTRIBUTING.md` | MINOR | 同上 |
| `DOC-004` | README 缺少必需章节 | MINOR | standard-readme |
| `DOC-005` | 双语文件不同步（章节数或引用数不一致） | MAJOR | 本规范自行约定 |

> `DOC-005` 的理由：双语文档最大的风险是漂移。只改一份会使另一份逐渐变成错误信息，比没有英文版更糟。

### 3.5 发布物（REL）

| ID | 检查项 | 级别 | 依据 |
|---|---|---|---|
| `REL-001` | 存在发布资产但无对应校验和 | MAJOR | [FIPS 180-4](https://csrc.nist.gov/pubs/fips/180-4/upd1/final) |
| `REL-002` | `SHA256SUMS` 带 UTF-8 BOM | BLOCKER | 同上 |
| `REL-003` | `SHA256SUMS` 为 CRLF 行尾 | BLOCKER | 同上 |
| `REL-004` | 校验和不匹配 | BLOCKER | 同上 |

> `REL-002` / `REL-003` 定为 BLOCKER 的理由：它们使发布物的完整性**无法被验证**。这不是格式洁癖——带 BOM 的文件在 Linux 上会让 `sha256sum -c` 直接失败，而使用者只会看到「校验失败」，从而合理地怀疑发布物被篡改。其后果与「校验和缺失」同级甚至更糟。

### 3.6 审计自身（ID）

| ID | 检查项 | 级别 | 依据 |
|---|---|---|---|
| `ID-001` | 存在与本次运行结论矛盾的旧审计报告 | INFO | 本规范自行约定 |

---

## 4. 豁免机制

### 4.1 为什么必须有豁免机制

本 skill 会扫描**它自己**。它的文档中包含示例邮箱与占位密钥，若不处理，首次自举就会产生误报。

假阳性是这类工具最主要的失效模式：告警被忽略几次之后，使用者会形成「反正都是误报」的预期，硬阻断随之名存实亡。因此豁免机制不是可选项，而是让阻断机制**可信**的前提。

同时必须承认风险：豁免机制本身就是一个绕过通道。因此设计原则是——**豁免必须显式、必须带理由、必须留痕**。

### 4.2 路径一：占位符自动降级（优先使用）

匹配到公认占位形式时自动降级为 `INFO`，不计入 findings。至少覆盖：

```text
example.com          example.org          example.net
your_                your-                <...>（尖括号模板）
xxxx / XXXX          placeholder          changeme
redacted             CHANGEME             dummy
AKIAIOSFODNN7EXAMPLE                      12345678+username@users.noreply.github.com
email@example.com   test@example.com     noreply@example.com
```

报告中单列一行：「已降级的占位符示例 N 条」。它们仍会被列出，只是不计为问题——**降级不等于隐藏**。

**一个必须区分的特殊情况：`*@users.noreply.github.com` 不是敏感信息。**

它是 GitHub 提供的**隐私保护地址**，用途正是避免真实邮箱泄露，且会公开出现在每条提交中。把它当作 `SEC-006` 的个人信息命中，等于惩罚正确做法。

处理方式：扫描器**应当**将 noreply 域名整体豁免。本实现通过把 `users.noreply.github.com` 纳入占位符域名清单（`_common.py` 的 `PLACEHOLDER_DOMAINS`）达成——任何 noreply 地址都会自动降级为 `INFO`，不计入发现项。

因此本仓库的 [`.github-upload-audit/allowlist.txt`](../../../.github-upload-audit/allowlist.txt) 现在**有 8 条生效条目**，全部用于两类命中：自测里为验证规则而构造的**伪造样本**，以及规则定义文件里的**正则字面量**。

**加条目前必须自问：这个命中是真的不是敏感信息，还是我只是希望它不是？** 后者应当改文档，而不是加豁免。

#### 4.2.1 自扫描豁免：为什么不能按文件名

扫描器自己的源码与自测里必然出现"看起来像密钥"的字符串。曾经的做法是按**文件名整份豁免**（`selftest.py`、`audit_repo.py`、`_common.py`、`scan_secrets.py`），那是错的。实测后果：

| 文件 | 实际命中 | 按文件名豁免的后果 |
|---|---|---|
| `selftest.py` | **约 110 条**伪造样本 | 全部被静默吞掉 |
| `_common.py` | **0 条** | 豁免纯属多余 |
| `audit_repo.py` | **0 条** | 豁免纯属多余 |
| `scan_secrets.py` | 6 条正则字面量 | 这 6 条确实该豁免 |

更糟的是报告里写着"并未跳过这些文件"，而实际结果既无发现项、也无自扫描记录——**报告与事实相反**。真实密钥若误入这些文件，会被无声放过。

现在的判据**必须同时满足两条**：文件名属于真正定义规则的文件（只剩 `scan_secrets.py` 与 `_common.py`），**且**命中文本里含正则元字符（真实密钥与真实邮箱不会出现 `[`、`\`、`|`）。判据不成立的命中**照常上报**，再由本节的白名单机制逐条显式豁免并写明理由。

**验证方式**：把一个真实形态的令牌放进名为 `selftest.py` 的文件，扫描器会报 `BLOCKER SEC-001`；改动前它会被无声放过。

### 4.3 路径二：显式白名单（需理由）

**有两份清单，格式完全相同，区别只在谁在担保：**

| 清单 | 位置 | 担保的对象 |
|---|---|---|
| **宿主项目自己的** | 被测项目根目录下的 `.github-upload-audit/allowlist.txt` | 该项目自身确实不是敏感信息的命中 |
| **skill 自带的** | skill 目录内的 `skill-allowlist.txt` | skill 自身的规则定义与自测夹具 |

**为什么必须分两份。** skill 会被**项目级安装**进各个仓库，而 skill 自己的规则定义与自测里必然出现"看起来像密钥"的字符串。若这些只能由宿主项目来豁免，那么每个安装它的仓库都会收到一批误报——实测 **57 条 BLOCKER**，全部来自 skill 自身文件，而那个仓库并没有做错任何事，也没有立场替别人的文件担保。

因此把"skill 自己的豁免"放进 skill 随它分发。路径用 `*/github-project-publisher/scripts/...` 这类前缀通配，以便在任何安装位置命中。

**注意这仍不是"整份文件豁免"**：条目按 **规则 + 路径** 生效，其他规则在这两个文件里的命中照常上报，报告里逐条列出被豁免的内容、来源与理由。

> **已知局限（未消除）**：同一规则在同一文件里的**新增**命中也会被覆盖。要消除它需要按**内容指纹**豁免（类似 `.gitleaksignore` 的做法），属于后续改进。

格式（空白分隔，`--` 之后为自由文本理由）：

```text
# 以 # 开头的行为注释
<规则ID>  <路径通配>  <行号|*>  -- <理由>
```

示例：

```text
SEC-001  .dsh/skills/*/references/*.md  *   -- 文档示例中的占位密钥
SEC-006  README.md                      42  -- 示例邮箱地址
SEC-003  docs/configuration.md          *   -- 配置示例中的占位密码字段
```

匹配规则：

- `规则ID` 精确匹配
- `路径通配` 以 `fnmatch` 匹配**仓库相对路径**（使用正斜杠）
- `行号` 为 `*`（任意行）或精确行号

**约束**：

1. **理由为空或缺失的条目无效**，并作为问题报告出来，不予采信。没有理由的豁免等于静默放行。
2. 每一条生效的豁免都会写入审计报告，含规则 ID、路径、行号与原文理由。
3. 格式错误的行会被报告，而不是被忽略。

### 4.4 刻意不采用的方案

**不使用「代码块内一律豁免」的规则。**

那看起来方便，但会让一个真实密钥被放进 README 示例时直接溜过去——而「把密钥贴进 README」恰恰是最常见的事故形态之一。

若确实需要降低代码块的噪音，使用 `--codeblock-soft`：将代码块内的疑似命中**降级为 MAJOR 并仍然报告**，绝不静默丢弃。

---

## 5. 审计报告

每次运行输出两份文件到 `.github-upload-audit/`：

- `report-<UTC 时间戳>.md` —— 供人阅读
- `report-<UTC 时间戳>.json` —— 供程序消费

该目录**默认加入 `.gitignore`**，因为报告含问题位置信息。

Markdown 报告必须包含：

1. 运行时间（UTC）与执行者
2. 工具版本：Python、git、gh，以及检测到的 `gitleaks` / `trufflehog`
3. **实际使用的扫描面与引擎**（决定结论的强度）
4. 按严重级别分组的结果表
5. 全部生效的豁免及其理由
6. 已降级的占位符示例计数
7. **本次审计未能覆盖的范围**（见下节）

**报告不得回显任何密钥或邮箱原文。** 掩码格式：前 4 字符 + `…` + 长度，如 `AKIA…(20)`；邮箱仅显示 `***@域名`。

---

## 6. 审计无法覆盖的范围

这一节必须原样出现在每份报告中。它不是免责声明，而是让使用者能正确判断结论强度的必要信息。

- 内置规则集只覆盖常见凭据形态，**无法识别业务自定义的敏感数据格式**
- 未安装 `gitleaks` / `trufflehog` 时覆盖率显著下降
- 二进制文件、加密压缩包、图片内嵌文本**不在扫描范围内**
- 历史扫描基于 `git log`，**已删除分支上不可达的提交无法被发现**
- 占位符清单是固定列表，可被刻意构造的字符串绕过
- 扫描结果依赖扫描面选择

**结论**：审计通过**不等于**项目安全。任何发布决定仍需人工核验。

---

## 7. 实现状态

**规则被登记 ≠ 规则会被自动检查。** 本节说明每条规则的实际执行方式，以免读者把"文档里写了"误读成"工具会拦下来"。这是本目录中最容易被高估的一节，因此单独列出。

| 实现方式 | 含义 |
|---|---|
| **脚本** | 由 `scripts/` 中的脚本自动检查，命中即按级别处置 |
| **CI** | 由 `.github/workflows/ci.yml` 检查，不通过则 CI 失败 |
| **Agent** | 无自动判据，由执行 skill 的 Agent 在流程中判断，并在报告中说明依据 |
| **未实现** | 已登记但目前没有任何检查手段。**不得视为已覆盖** |

| 规则 | 实现方式 | 位置 |
|---|---|---|
| `SEC-001` ~ `SEC-009` | 脚本 | `scripts/scan_secrets.py` |
| `SEC-010` | 脚本（需 `--codeblock-soft` 显式开启，默认关闭） | `scripts/scan_secrets.py` |
| `GIT-001` | 脚本 | `scripts/check_identity.py` |
| `GIT-002` | Agent（判据数据由 `check_identity.py` 的 `non_noreply_entries` 提供，但需人工判断是否值得改写历史） | — |
| `GIT-003` | Agent（依赖"是否已存在远程"，无自动判据） | — |
| `GIT-004` | 脚本（阈值分档：>50 MB 为 MINOR，>100 MB 覆盖为 MAJOR） | `scripts/audit_repo.py` |
| `GIT-005` | 脚本（`git ls-files --cached --ignored --exclude-standard`） | `scripts/audit_repo.py` |
| `META-001` ~ `META-006` | 脚本 | `scripts/audit_repo.py` |
| `DOC-001` ~ `DOC-003` | 脚本 | `scripts/audit_repo.py` |
| `DOC-004` | Agent（章节完整性判据见 `templates.md` 第 1 节） | — |
| `DOC-005` | CI + Agent（CI 逐组比对两份文件的章节数与表格行数） | `.github/workflows/ci.yml` |
| `REL-001` | 脚本 | `scripts/audit_repo.py` |
| `REL-002`、`REL-003` | CI（全仓库 BOM / CRLF 门禁；未按规则 ID 单独标记） | `.github/workflows/ci.yml` |
| `REL-004` | 脚本（`make_checksums.py --verify`；未按规则 ID 单独标记） | `scripts/make_checksums.py` |
| `ID-001` | 脚本 | `scripts/audit_repo.py` |

**未实现的规则：无。** 31 条登记规则全部有明确的执行方式。

回顾这段过程，有一条教训值得留下——因为它是关于"未实现"这个标签本身的：

- `GIT-005` 曾与 `GIT-004` 一同标为"未实现"。补它时发现，探测方式只是一条 git 原生命令（`git ls-files --cached --ignored --exclude-standard`），成本远低于预期。**它未实现的真实原因是委派清单的范围遗漏，不是技术代价。**
- `GIT-004` 的"代价较高"在当时是真的，但补实现后发现用一次批量查询（`git rev-list --objects --all` 配合 `git cat-file --batch-check`）即可完成，同样低于预估。

**"技术上有代价"是一个很容易被接受的挡箭牌，而它往往没有被真正核实过。** 两条规则并排躺在文档里，标签一模一样，理由却一个真一个假。要区分它们，唯一的办法是去实际估一次成本，而不是照抄下判断那一刻的措辞。

> 一个值得保留的教训：`checks.md` 最初登记了 31 条规则，而脚本只实现了 21 条的 ID。落差不是通过放宽文档消除的，而是通过**如实标注执行方式**消除的。文档比实现更乐观，比文档比实现更保守，都同样有害。

---

## English summary

Rule IDs follow `<AREA>-<NNN>` with AREA in {SEC, GIT, META, DOC, REL, ID}; numbering is never reused. Severity is assigned by **whether the consequence is reversible**, not by how hard it is to fix — a real email address in already-pushed public history is a BLOCKER because it cannot be undone.

Four scan surfaces are mandatory: working tree, staged diff, full git history, and log/artifact files. Scanning the working tree alone cannot find a credential that was already committed.

The exemption mechanism exists because the skill scans its own documentation and would otherwise report false positives on first use — and false positives are the primary failure mode of a blocking tool. Two paths are supported: automatic downgrade of recognised documentation placeholders (reported as a count, never hidden), and an explicit allowlist at `.github-upload-audit/allowlist.txt` whose entries **must carry a reason**; an entry without one is invalid and reported as a problem. Every applied exemption is recorded in the audit report. A blanket "exempt everything inside a fenced code block" rule is deliberately **not** implemented, because a real key pasted into a README is one of the most common disclosure shapes.

Every report must include the surfaces and engine actually used, plus an explicit list of what the audit could not cover. A passing audit is not evidence that a project is safe.
