<!--
  提交 PR 前请通读本清单。
  未勾选的项请说明原因，而不是留空。
-->

## 变更说明

<!-- 这个 PR 改了什么？为什么需要改？ -->

## 关联 issue

<!-- 例如 Closes #12。无关联 issue 可写「无」。 -->

## 变更类型

<!-- 勾选一项或多项 -->

- [ ] 新增敏感信息检测规则
- [ ] 新增仓库规范检查项
- [ ] 修复缺陷
- [ ] 改进文档
- [ ] 改进脚本实现（无行为变化）
- [ ] 其他配置或构建变更

---

## 提交前自检

- [ ] `python .\.dsh\skills\github-project-publisher\scripts\selftest.py` 全部通过
- [ ] `python .\.dsh\skills\github-project-publisher\scripts\scan_secrets.py --worktree` 无 BLOCKER 命中
- [ ] 提交信息遵循 [提交规范](.dsh/skills/github-project-publisher/references/commit-convention.md)
- [ ] 所有文本文件为 UTF-8 **无 BOM**、**LF** 行尾
- [ ] 未引入任何第三方 Python 依赖（脚本仅用标准库）

## 文档闭环（涉及规则改动时必填）

- [ ] 已在 `references/standards.md` 中补充或更新**依据来源**
- [ ] 已确认"每条规则可追溯到引用、每个引用对应至少一条规则"仍然成立
- [ ] 已在 `references/checks.md` 中登记或更新**规则 ID 与严重级别**
- [ ] 已在 `selftest.py` 中补充**正例与反例**各至少一个
- [ ] 已在 `CHANGELOG.md` 的 `[Unreleased]` 下登记本次变更

## 双语同步（涉及文档改动时必填）

- [ ] 若改动了 `README.md`，已同步更新 `README.en.md`
- [ ] 若改动了 `references/commit-convention.md`，已同步更新 `commit-convention.en.md`
- [ ] 两份文件的章节与引用保持一一对应

## 安全审查

- [ ] 本次变更是**收紧**检测，而非放宽
- [ ] 若放宽了任何规则或新增了豁免，已在下方说明理由
- [ ] 未在代码、测试、示例或本 PR 描述中写入任何真实密钥、令牌或邮箱地址
- [ ] 新增的文档示例使用了公认的占位形式（如 `example.com`、`your_`、`<...>`）

<!-- 若放宽了规则或新增豁免，请在此说明理由： -->

## 验证方式

<!-- 说明 reviewer 如何独立验证你的改动是有效的，而不只是"看起来对" -->
