# 脚本层

本目录是 `github-project-publisher` 的自动化层。全部脚本**只使用 Python 标准库**，无任何第三方依赖。

对应文档：规则编号与严重级别见 [`../references/checks.md`](../references/checks.md)，依据来源见 [`../references/standards.md`](../references/standards.md)。

---

## 为什么坚持零依赖

这不是偷懒，而是功能要求：**一个审计工具如果自身需要安装依赖才能运行，就无法在被审计的受限环境中被信任地执行**。依赖安装本身也是一条供应链风险——为了检查别人有没有泄露凭据，先往自己机器上装一堆包，逻辑上是倒置的。

因此所有脚本只依赖 Python 3.9+ 标准库。CI 矩阵同时跑 3.9 与 3.13，以验证这一声明成立。

---

## 脚本一览

| 脚本 | 用途 | 退出码 |
|---|---|---|
| [`scan_secrets.py`](#scan_secretspy) | 敏感信息扫描（四个扫描面） | 0 干净 / 1 有 BLOCKER 或 MAJOR / 2 执行错误 |
| [`check_identity.py`](#check_identitypy) | 核验 author 与 committer 是否均为 noreply | 0 通过 / 1 不通过 / 2 执行错误 |
| [`make_checksums.py`](#make_checksumspy) | 生成与校验 coreutils 兼容的 SHA256SUMS | 0 成功 / 1 校验失败 / 2 用法错误 |
| [`audit_repo.py`](#audit_repopy) | 聚合审计并输出报告 | 0 无 BLOCKER / 1 有 BLOCKER / 2 执行错误 |
| [`selftest.py`](#selftestpy) | 脚本层自检（72 个用例） | 0 全通过 / 1 有失败 / 2 用法错误 |
| `_common.py` | 共享层：脱敏、占位符识别、豁免清单解析、Finding 模型 | — |
| `_normalize_eol.py` | 一次性维护工具：把本目录的文本文件归一化为 UTF-8 无 BOM + LF | 0 |

**约定**：`_` 前缀表示非独立入口（`_common.py` 是被导入的模块）。`_normalize_eol.py` 虽是入口，但属于仓库维护工具而非审计流程的一部分。

---

## scan_secrets.py

扫描密钥、凭据与个人信息。**外部引擎优先**（`gitleaks` / `trufflehog`），缺失或失败时回退内置规则集，并在输出中**明确说明实际使用了哪个引擎**——降级会显著降低覆盖率，不说明等于虚报结论强度。

### 四个扫描面

```powershell
python .\scan_secrets.py --worktree                 # 工作树（默认）
python .\scan_secrets.py --staged                   # 暂存区 git diff --cached
python .\scan_secrets.py --history                  # 全部提交历史
python .\scan_secrets.py --artifacts                # 日志与产物
python .\scan_secrets.py --worktree --staged --history --artifacts   # 四者齐上
```

**四个扫描面缺一不可。** 只扫工作树无法发现历史中已提交的凭据；密钥从 `HEAD` 删掉之后，仍然可以通过 `git log -p` 看到。

### 常用参数

| 参数 | 作用 |
|---|---|
| `--repo DIR` | 项目根目录，默认取 git 仓库根 |
| `--no-external` | 不用外部引擎，只用内置规则 |
| `--paranoid` | 即使外部引擎有命中，也强制再跑一遍内置规则 |
| `--codeblock-soft` | 围栏代码块内的 `SEC-*` 命中降为 MAJOR，但**仍然报告**（默认关闭） |
| `--exclude GLOB` | 跳过匹配的路径，可重复 |
| `--format json` | 机器可读输出 |
| `--out PATH` | 写入文件（UTF-8 无 BOM、LF） |
| `--quiet` | 只输出判定行 |

### 输出与脱敏

**证据一律脱敏，最多显示前 4 个字符**（如 `AKIA…(20)`）。审计报告本身就是泄露面：把密钥打印到终端、CI 日志或会话记录里，只是把泄露换了个地方。

按严重级别统计后给出判定与退出码。

---

## check_identity.py

核验 author 与 committer 是否均为 GitHub 隐私邮箱（`<数字ID>+<用户名>@users.noreply.github.com`）。

```powershell
python .\check_identity.py                  # 默认核验全部引用（--all）
python .\check_identity.py --no-all         # 只核验 HEAD 可达的历史
python .\check_identity.py --show-domain    # 允许显示命中地址的域名
python .\check_identity.py --fix-local 149449562+cicada478
```

### 两个关键设计

**其一：只输出判定与条数，默认不回显任何地址。**

```powershell
# 输出形如：
#   当前仓库 user.email：***@users.noreply.github.com（是隐私邮箱）
#   配置来源：--local ***@users.noreply.github.com；--global ***@***
```

注意 `--global` 那一行：指向**个人邮箱服务**的域名会整体隐藏为 `***@***`，只连接串形式也不保留用户名。原因很实际——用户名常常就是工号或邮箱本地部分，属同一个泄露面。

这条设计对应 [CWE-532](https://cwe.mitre.org/data/definitions/532.html)：**核验命令本身就是一个泄露面**。

**其二：`--fix-local` 只写仓库级配置。**

`--author` 只覆盖 author，**不覆盖 committer**；两者都由 `user.name` / `user.email` 决定。因此单用 `--author` 并不能保护你。`--fix-local` 写入 `.git/config` 的 `user.email`，**不改动全局配置**。

`non_noreply_entries` 与 `distinct_non_noreply` 是两个不同的数字：前者是**被污染的字段数**（同一次提交的 author 与 committer 算两条），后者是**去重后的地址数**。同一次提交两者都为真实邮箱时，前者是 2、后者是 1。两个数字都报告，信息量更大。

---

## make_checksums.py

生成或校验 coreutils 兼容的 `SHA256SUMS`。

```powershell
# 生成
python .\make_checksums.py dist\app.zip dist\docs --out SHA256SUMS

# 校验
python .\make_checksums.py --verify SHA256SUMS
```

### 三个致命细节

| 细节 | 后果 |
|---|---|
| **UTF-8 无 BOM** | 带 BOM 会让 Linux 侧 `sha256sum -c` 直接失败，使用者只会看到"校验失败"，从而合理地怀疑发布物被篡改 |
| **LF 行尾** | CRLF 破坏解析或导致不匹配 |
| **两个空格分隔** | coreutils 格式为 `<摘要>  <路径>`，恰好两个空格 |

脚本写文件时统一使用 `open(path, "w", encoding="utf-8", newline="\n")`，正是为了同时避免 BOM 与 CRLF。

`--verify` 会逐条校验并报告不匹配、缺失与格式错误的条目；**任何不匹配都返回退出码 1**。

---

## audit_repo.py

聚合审计：静态检查 + 密钥扫描 + 身份核验 + 校验和检查，输出 Markdown 与 JSON 报告到 `.github-upload-audit/`。

静态检查中有两条容易被忽略但后果隐蔽的：

**`GIT-005` —— `.gitignore` 对已被跟踪的文件无效。**

```powershell
# 探测方式（脚本内部使用同一条命令）
git ls-files --cached --ignored --exclude-standard
```

输出的是「**既被跟踪、又匹配 `.gitignore`**」的文件。这个交集里的文件，忽略规则**一个字的作用都没有**，仍会随每次提交更新。

典型事故：先把 `.env` 提交了，想起来不对，往 `.gitignore` 写一行，于是以为安全了。

**这比根本不写 `.gitignore` 更危险**——不写至少还会警惕，写了就没人再看第二眼。

报告会逐条列出命中的文件（超过 10 个时改为汇总），并给出修复方式：

```powershell
git rm --cached <文件>      # 从版本控制移除，保留本地文件
```

**`GIT-004` —— 历史中的超大文件。**

| 体积 | 级别 | 后果 |
|---|---|---|
| > 50 MB | `MINOR` | 推送时警告，且仓库体积永久变大——每次 clone 都要下载 |
| > 100 MB | **`MAJOR`** | **GitHub 直接拒收推送**，不改写历史就无法发布 |

```powershell
# 探测方式（脚本内部为一次批量查询，不是逐个对象起进程）
git rev-list --objects --all | git cat-file --batch-check='%(objecttype) %(objectsize) %(rest)'
```

**从 `HEAD` 删除无效。** 对象一旦进入历史就永远在那里；要真正移除必须改写历史，而那会改变所有相关提交的 SHA。所以这条检查的价值恰恰在于**推送之前**发现——一旦被拒，代价就从"删个文件"变成了"改写历史"。

默认执行；用 `--no-large-files` 可跳过（会记入未覆盖清单）。它是一次对象列表遍历，通常远快于 `--history` 的补丁扫描，但超大仓库上仍可能较慢。

```powershell
python .\audit_repo.py
python .\audit_repo.py --dry-run                     # 照常计算，不写任何文件
python .\audit_repo.py --no-history                  # 跳过历史扫描（更快）
python .\audit_repo.py --repo C:\path\proj
```

报告固定包含：运行时间、工具版本、**实际使用的扫描面与引擎**、按严重级别分组的结果、**全部生效的豁免及其理由**、已降级的占位符计数、以及**「本次审计未能覆盖」一节**。

最后一节不可省略：它是使用者判断结论强度的唯一依据。

**该目录下的报告默认不入库**（可能含问题位置信息），但 `allowlist.txt` **必须入库**——它是配置，不是产物。

---

## selftest.py

脚本层自检，72 个用例，不依赖 pytest。

```powershell
python .\selftest.py
python .\selftest.py --list          # 列出全部用例名
python .\selftest.py --only mask     # 只跑名字含 "mask" 的用例
python .\selftest.py --verbose       # 保留临时目录便于排查
python .\selftest.py --force-failure # 自检的自检
```

### `--force-failure` 为什么存在

"失败时也要清理临时目录"这条要求，如果只靠人工偶尔验证，迟早会退化。`--force-failure` 故意让第一个用例失败，从而让**失败路径每次都能被自动检验**——脚本会打印清理确认行，例如：

```text
清理确认：.../.selftest-tmp 仍存在 = False
```

### 临时目录策略

优先使用系统临时区；不可写时回退到 `<仓库根>/.selftest-tmp/run-<pid>/`。**无论成败都会删除**，并在开始时打印实际采用的策略，以便把"环境导致的失败"与"真正的测试失败"区分开。

### 为什么需要回退

在 DSH 的受限模式下，**临时区是扁平可写的**：可以创建目录，可以在顶层写文件，但**无法向刚创建的目录内写文件**（`PermissionError [Errno 13]`），也无法删除该目录。`tempfile.TemporaryDirectory()` 因此在这种环境中直接失败，而在 GitHub Actions 上正常。

### 清理 git 仓库时的只读陷阱

清理逻辑必须**先清除只读属性再重试**：

```python
def force_rmtree(path):
    def onerror(func, p, exc_info):
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except Exception:
            pass
    shutil.rmtree(path, onerror=onerror)
```

原因是 **git 把松散对象文件写成只读属性**，而 Windows 上 `shutil.rmtree` 遇到只读文件即中止。自测里有多个用例会临时 `git init` 并提交，不清除属性就会残留目录——而且失败是静默的（`ignore_errors=True` 会吞掉它）。

`onerror` 而非 `onexc`：后者是 Python 3.12+ 的 API，而 CI 矩阵包含 3.9。

---

## 豁免清单

文件：被测项目根目录下的 `.github-upload-audit/allowlist.txt`

### 格式

```text
<规则ID>  <路径通配>  <行号|*>  -- <理由>
```

```text
SEC-001  .dsh/skills/*/references/*.md  *   -- 文档示例中的占位密钥
SEC-006  README.md                      42  -- 示例邮箱地址
SEC-006  README.md                      12-14  -- 行号支持区间
```

### 理由必填，且必须由该条目自身给出

- 行内 `--` 之后，或
- 紧邻上方以 `# reason:` 开头的注释行

**普通的 `#` 注释不构成理由。** 这一点是刻意的：如果"上面随便有条注释"就能当作理由，那么文件头注释迟早会被当成理由，"理由必填"这条约束就形同虚设。

**无理由、字段不足、规则 ID 非法、行号非法的条目一律被拒绝**，并作为问题单独报告出来，不予采信。

### 优先使用占位符自动降级

以下形式会被自动识别为文档占位符并降级为 `INFO`（不计入发现项，但在报告中单列计数）：`example.com`、`your_`、`xxxx`、`<...>`、`changeme`、`redacted`、`AKIAIOSFODNN7EXAMPLE`、`12345678+username@users.noreply.github.com` 等。

**只有自动降级不适用时才写豁免。** 加条目前先自问：这个命中是真的不是敏感信息，还是我只是希望它不是？后者应当**改文档**（把真实值换成占位形式），而不是加豁免。

### 刻意不采用的方案

**不使用「代码块内一律豁免」的规则。** 那会让一个真实密钥被放进 README 示例时直接溜过去——而"把密钥贴进 README"恰恰是最常见的事故形态之一。确实需要降低噪声时用 `--codeblock-soft`：降级为 MAJOR 但**仍然报告**。

---

## 环境要求

- Python **3.9 或更高**（CI 同时验证 3.9 与 3.13）
- `git` 在 PATH 中
- 可选：`gitleaks` 或 `trufflehog`（缺失时回退内置规则，覆盖率下降并在输出中说明）
- 可选：`gh`（仅发布流程需要，审计本身不需要）

所有文本文件统一 **UTF-8 无 BOM + LF**。这不是风格偏好：`SHA256SUMS` 带 BOM 会让 Linux 侧校验失败。仓库已通过 `.gitattributes` 强制 `eol=lf`。

---

## 退出码约定

| 码 | 含义 |
|---|---|
| `0` | 通过 |
| `1` | 未通过（存在 BLOCKER/MAJOR、校验失败、或自测有失败） |
| `2` | 执行错误（用法错误、目录不存在、依赖缺失） |

**区分 1 与 2 是有意的**：`1` 表示"检查跑了，结论是不通过"；`2` 表示"检查根本没跑成"。把后者当成前者，会让人误以为项目被检查过了。CI 应当让两者都失败，但报告措辞必须区分。
