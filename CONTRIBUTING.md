# 贡献指南

感谢你考虑为本项目贡献。本项目的目标是**可复核**：每条规则都能追溯到公开依据，每个结论都能被独立验证。贡献时请遵循同样的标准。

## 提交规范

所有提交**必须**遵循提交规范：

- 中文版：[commit-convention.md](.dsh/skills/github-project-publisher/references/commit-convention.md)
- English: [commit-convention.en.md](.dsh/skills/github-project-publisher/references/commit-convention.en.md)

最关键的几条：

- 格式为 `type(scope): description`，**冒号前不得有空格**
- `type` 必须小写，取值限于 `feat` `fix` `docs` `style` `refactor` `perf` `test` `build` `ci` `chore` `revert`
- description 使用祈使语气，**不加句末句号**
- 破坏性变更通过 `!` 标记或 `BREAKING CHANGE:` footer 声明

## 双语同步规则

本仓库文档以**中文为主、英文为镜像**：

| 中文 | 英文 |
|---|---|
| `README.md` | `README.en.md` |
| `references/commit-convention.md` | `references/commit-convention.en.md` |

**改动其中一份时，必须在同一次提交中更新另一份。** 两份文件必须保持章节与引用的一一对应。只改一份视为文档缺陷。

## 开发环境

**无需任何第三方依赖。**

```powershell
python --version
# 需 3.9 或更高版本

python .\tests\selftest.py
```

脚本**只使用 Python 标准库**，这是刻意约束而非偷懒：一个审计工具如果自身需要安装依赖才能运行，就无法在被审计的受限环境中被信任地执行。请勿为此引入 pip 依赖。

## 文件编码要求

所有文本文件**必须是 UTF-8 无 BOM、行尾 LF**。

这不是风格偏好，而是功能要求：`SHA256SUMS` 若带 BOM，会导致 Linux 侧 `sha256sum -c` 校验失败。`.gitattributes` 已强制 `eol=lf`，但请注意部分 Windows 编辑器会自行添加 BOM。

新增或修改脚本时，写文件必须使用：

```python
open(path, "w", encoding="utf-8", newline="\n")
```

`newline="\n"` 是为了防止 Windows 上产生 CRLF。

## 提交前自检

```powershell
python .\tests\selftest.py
python .\.dsh\skills\github-project-publisher\scripts\scan_secrets.py --worktree
```

第一条必须全部通过；第二条应无 BLOCKER 命中。

### 沙箱环境的一个限制

在 DSH 的受限模式下，**临时区是扁平可写的**：可以创建目录，可以在临时区顶层写文件，但**无法向刚创建的目录内写文件**（`PermissionError [Errno 13]`），也无法删除该目录。`tempfile.TemporaryDirectory()` 因此会在这种环境中直接失败，而在 GitHub Actions 上正常。

自测脚本必须同时适配两种情况：优先使用 `tempfile.TemporaryDirectory()`，遇到 `PermissionError` 时回退到工作区内的临时目录（如 `.selftest-tmp/`），并在 `finally` 中清理。脚本应打印实际采用的策略，以便把"沙箱导致的失败"与"真正的测试失败"区分开。

## Pull Request 流程

1. 从 `main` 开出分支
2. 提交信息遵循上述规范
3. **若新增或修改了规则**，必须同步更新 `references/standards.md` 中的依据来源，并保持"每条规则可追溯到引用、每个引用对应至少一条规则"的闭合性
4. **若新增了检查项**，必须在 `references/checks.md` 登记规则 ID 与严重级别，并补充自测用例
5. 在 PR 描述中说明：改了什么、为什么、如何验证

## 安全相关贡献

涉及敏感信息检测规则的改动，请在 PR 中额外提供：

- **正例**（应当命中）与**反例**（不应命中）各至少一个，并写入 `selftest.py`
- 该规则的**依据来源**：CWE 编号、厂商文档或规范链接
- **误报风险评估**：说明什么正常代码可能被误判

缺少依据来源的检测规则不会被合并。"学院派"的核心要求是每条规则可追溯，而不是规则越多越好——一条无法追溯来源的规则，既是噪音，也是假阳性的来源。

## 豁免机制

若你的贡献引入了会被扫描器命中的文档示例，**不要**放宽扫描规则，而应在被测项目中通过豁免机制处理：

- 优先依赖占位符自动降级（使用 `example.com`、`your_`、`<...>` 等公认占位形式）
- 确需显式豁免时，写入 `.github-upload-audit/allowlist.txt`，并**必须**填写理由

**无理由的豁免不允许存在**——豁免记录会进入审计报告，这是"每个刻意动作都留痕"原则的一部分。

## 许可

贡献即表示你同意以本仓库的 [MIT 许可证](LICENSE) 授权你的贡献。
