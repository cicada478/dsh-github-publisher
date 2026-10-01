# references/ 索引

本目录是 skill 的**规范层**：说明「什么必须成立、由谁负责、依据是什么」。

它**不描述怎么执行**——每个检查的具体用法、参数与退出码在 [`../scripts/README.md`](../scripts/README.md)；
面向 Agent 的入口指令在 [`../SKILL.md`](../SKILL.md)。

## 三层结构

| 层 | 文件 | 回答的问题 | 什么时候读 |
|---|---|---|---|
| **判定标准** | [`checks.md`](checks.md) | 有哪些规则？编号与严重级别是什么？由脚本还是 Agent 执行？什么情况可以豁免？ | 需要判定某件事是否构成问题时 |
| | [`commit-convention.md`](commit-convention.md) · [`.en.md`](commit-convention.en.md) | 提交信息怎么写？ | 生成或检查提交信息时 |
| **依据** | [`standards.md`](standards.md) | 每条规则的依据是哪份一手来源？ | 质疑某条规则、或新增规则时 |
| **操作** | [`interaction.md`](interaction.md) | 哪些必须问、哪些要二次确认、哪些默认执行、哪些绝不做？ | 遇到任何一个决策点时 |
| | [`templates.md`](templates.md) | README / CHANGELOG / Release 文案 / 审计报告长什么样？ | 生成文档时 |

## 阅读顺序

1. **`checks.md`** —— 先知道「什么算问题」
2. **`interaction.md`** —— 再知道「发现了问题该怎么办、什么事根本不该问」
3. **`templates.md`** —— 然后知道「该产出什么」
4. **`standards.md`** —— 有疑问时查依据
5. **`commit-convention.md`** —— 只在写提交信息时需要

## 为什么是这六份，而不是更少或更多

**依据为什么单独成文件。** `checks.md` 回答「规则是什么」，`standards.md` 回答「凭什么」。合并成一份会让两者互相背书——一份文档里写「因为 RFC 2119 规定…，所以本规则成立」，读者无法分辨哪句是引用、哪句是本项目自己的约定。分开之后有一条可检验的约束：

> 每条规则至少追溯到一份一手来源；每份来源至少支撑一条可执行规则。

这条闭合性由 CI 机器校验，不是靠人自觉。**没有外部来源的规则必须显式标注「本规范自行约定」**——这条标注本身就是信息。

**操作层为什么与判定层分开。** `checks.md` 说「这是一条 BLOCKER」，`interaction.md` 说「发现 BLOCKER 之后该怎么办」。前者是事实判断，后者是行为约定。混在一起会导致一个常见错误：把「默认执行」的事拿去提问。把 SHA256 校验和这种每次都必须做的事拿来问，结果是使用者养成无脑确认的习惯，**问与不问都失去意义**。

**提交规范为什么自带英文镜像。** 它是唯一需要与外部工具链（`commitlint`、`semantic-release`）互操作的子规范，而这类工具的术语与规则以英文为准。中英两份由 CI 逐项比对章节数与表格行数，防止漂移。

**为什么不继续拆。** 六份已经接近「一份文件回答一类问题」的粒度：再拆会出现大量交叉引用，读者要在文件之间反复跳转；合并则会重新混入上面那些本应分开的关切。**目录结构的目标是让每份文件有唯一的、说得出口的职责**，而不是让文件数变少。

---

## English summary

`references/` holds the specification layer: what must be true, who is responsible, and on what authority. It does not describe execution — that lives in [`../scripts/README.md`](../scripts/README.md).

Three layers: **criteria** ([`checks.md`](checks.md), [`commit-convention.md`](commit-convention.md)), **authority** ([`standards.md`](standards.md)), and **operation** ([`interaction.md`](interaction.md), [`templates.md`](templates.md)).

`standards.md` is separate from `checks.md` because a single document that states both a rule and its authority makes the two look alike: the reader cannot tell a citation from this project's own convention. Separation makes one constraint checkable, by machine, in CI: every rule traces to at least one primary source, and every source supports at least one executable rule. A rule with no external source must be labelled "本规范自行约定" — the label itself is information.

`interaction.md` is separate from `checks.md` because "this is a BLOCKER" is a judgement about fact, while "here is what to do about it" is a behavioural convention. Mixing them produces a specific failure: asking about work that should simply be done. Ask about a checksum every time and the user learns to confirm without reading, which destroys the value of every question that matters.
