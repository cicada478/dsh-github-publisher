# Git Commit Message Convention

English | [中文](commit-convention.md)

> **Baseline**: This convention takes [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) as its mandatory baseline, adopts the `type` set recommended by [@commitlint/config-conventional](https://github.com/conventional-changelog/commitlint/tree/master/%40commitlint/config-conventional) (itself derived from the [Angular commit message convention](https://github.com/angular/angular/blob/main/contributing-docs/commit-message-guidelines.md)), and adds GitHub platform conventions on top.
>
> **Normative language**: The key words **MUST**, **MUST NOT**, **SHOULD**, and **MAY** in this document are to be interpreted as described in [BCP 14](https://www.rfc-editor.org/info/bcp14) ([RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/info/rfc8174)) when, and only when, they appear in all capitals. Per [RFC 8174](https://www.rfc-editor.org/info/rfc8174), any other capitalization carries its ordinary meaning and is not normative.

## Table of Contents

- [1. Commit Message Structure](#1-commit-message-structure)
- [2. type (REQUIRED)](#2-type-required)
- [3. scope (OPTIONAL)](#3-scope-optional)
- [4. description (REQUIRED)](#4-description-required)
- [5. body (OPTIONAL)](#5-body-optional)
- [6. footer (OPTIONAL)](#6-footer-optional)
- [7. Breaking Changes](#7-breaking-changes)
- [8. Relation to SemVer and CHANGELOG](#8-relation-to-semver-and-changelog)
- [9. revert Commits](#9-revert-commits)
- [10. GitHub Platform Conventions](#10-github-platform-conventions)
- [11. Toolchain](#11-toolchain)
- [12. Examples](#12-examples)
- [13. Anti-pattern Reference](#13-anti-pattern-reference)
- [14. References](#14-references)
- [15. Revision History](#15-revision-history)

---

## 1. Commit Message Structure

A commit message **MUST** consist of three parts, the latter two being OPTIONAL:

```text
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

Line by line:

| Line | Composition | Requirement |
|---|---|---|
| Line 1 (header) | `type` + OPTIONAL `scope` + OPTIONAL `!` + **colon and one space** + `description` | `type` and `description` are REQUIRED |
| Line 2 | **blank line** | REQUIRED when a body or footer is present |
| From line 3 | body | OPTIONAL |
| After a blank line | one or more footers | OPTIONAL |

> **Note**: The colon **MUST** immediately follow the `type` or the closing parenthesis of `scope`, and **MUST** be followed by exactly one space.
> Correct: `feat(auth): add OAuth2 login`
> Wrong: `feat(auth) : add OAuth2 login` (space before colon), `feat(auth):add OAuth2 login` (no space after colon)

Full grammar (brackets denote optional elements; `!` cannot be moved):

```text
type[(scope)][!]: description
```

---

## 2. type (REQUIRED)

`type` is a noun describing the **nature** of the change. It **MUST** be lowercase (commitlint `type-case: lower-case`).

### 2.1 Standard types

The following 11 `type` values come from the `type-enum` of `@commitlint/config-conventional` and form the allow-list that commitlint enforces:

| type | Meaning | In CHANGELOG | SemVer impact |
|---|---|---|---|
| `feat` | A new feature | ✅ Features | **MINOR** |
| `fix` | A bug fix | ✅ Bug Fixes | **PATCH** |
| `perf` | A performance improvement | ✅ Performance Improvements | PATCH (tool default) |
| `revert` | Reverts a previous commit | ✅ Reverts | — |
| `docs` | Documentation only | ❌ hidden by default | — |
| `style` | Changes that do not affect the meaning of the code (whitespace, formatting, missing semicolons) | ❌ hidden by default | — |
| `refactor` | A code change that neither fixes a bug nor adds a feature | ❌ hidden by default | — |
| `test` | Adding or correcting tests | ❌ hidden by default | — |
| `build` | Changes affecting the build system or external dependencies (example scopes: `gulp`, `broccoli`, `npm`) | ❌ hidden by default | — |
| `ci` | Changes to CI configuration files and scripts (example scopes: `travis`, `circle`, `github`) | ❌ hidden by default | — |
| `chore` | Other changes that do not modify `src` or test files | ❌ hidden by default | — |

> `feat` and `fix` are the only types with semantics defined by the specification. No other type affects the version number unless it carries a breaking change.
> The specification says nothing about the version impact of `perf`; "PATCH" reflects the default behavior of tools such as semantic-release.

### 2.2 Forbidden types

> This section is a **convention of this document**, not a rule of Conventional Commits or commitlint. Its criterion is that a `type` **MUST** map to a definite meaning and CHANGELOG section, otherwise it cannot participate in version derivation or changelog generation.

The following are **MUST NOT** be used:

| Form | Reason |
|---|---|
| `init` | Not a standard type; inherited from the obsolete AngularJS convention. Use `chore` for initialization |
| `update` / `change` / `modify` | Semantically empty; maps to no standard type |
| `Feat` / `FIX` | `type` **MUST** be entirely lowercase |
| `BREAKING CHANGE` | **It is not a type.** It is a footer token or a `!` marker — see section 7 |
| `feature` | The standard spelling is `feat` |
| `bugfix` | The standard spelling is `fix` |
| `wip` | Work-in-progress commits should be squashed before merging and never enter mainline history |

### 2.3 Team extensions

The specification permits custom types beyond `feat` and `fix`. An extension **MUST** satisfy all of the following:

1. It is explicitly registered in the `type-enum` of `commitlint.config.js`.
2. A row is added to the table in section 2.1 stating its meaning and CHANGELOG section.
3. It is a single lowercase word with no ambiguous abbreviation.

An unregistered type causes commitlint validation to fail.

---

## 3. scope (OPTIONAL)

`scope` describes the **area** affected by the commit. It is a noun naming a section of the codebase, and **MUST** be wrapped in parentheses immediately after `type`.

- `scope` **SHOULD** be lowercase, with multi-word scopes joined by `-` (kebab-case): `feat(user-profile): ...`
- `scope` **MUST NOT** contain spaces: `feat(user profile): ...` ❌
- `scope` values **SHOULD** remain stable across the project. Suggested sources are directory or module names, for example:
  - Layered architecture: `api`, `ui`, `db`, `config`
  - Package-oriented: `parser`, `cli`, `core`
- When a change spans multiple scopes, **SHOULD** split it into multiple commits rather than omitting or stacking scopes. This is the specification's explicit recommendation.

---

## 4. description (REQUIRED)

`description` is the short summary following the colon and space in the header.

| Rule | Requirement | Source |
|---|---|---|
| Position | **MUST** immediately follow the colon and one space | Spec rule 5 |
| Empty | **MUST NOT** be empty | commitlint `subject-empty: never` |
| Length | The header **MUST** be ≤ 100 characters, **SHOULD** be ≤ 72, and ideally ≤ 50 | See below |
| Mood | **SHOULD** use the imperative mood, present tense, describing what the commit does | commitlint prompt, Angular convention |
| Case | In English, **SHOULD** start lowercase and **MUST NOT** use sentence case, start case, PascalCase, or all caps | commitlint `subject-case` |
| Trailing punctuation | **MUST NOT** end with a period `.` | commitlint `subject-full-stop: never` |
| Content | **SHOULD** state what changed, not which files were touched | Spec rule 5 |

**On length** — three different sources that must not be conflated:

| Source | Rule |
|---|---|
| Conventional Commits 1.0.0 | **No length requirement whatsoever** |
| `@commitlint/config-conventional` | `header-max-length: 100` (Error level, enforced) |
| Git community practice (Tim Pope's 50/72 rule) | Subject ≤ 50, body lines ≤ 72 — a **recommendation, not a specification** |

**For CJK-language commits**: the 50/72 guidance assumes monospace Latin characters, and a CJK character occupies roughly twice the width. Treat it as a display-width budget instead — about 25 CJK characters for the subject.

**Language consistency**: commit messages within a repository **SHOULD** use a single language. English is recommended for open-source projects, since it aids community search and automatic CHANGELOG generation.

---

## 5. body (OPTIONAL)

The body supplies **context and motivation** — answering *why*, not merely *what*.

- The body **MUST** be separated from the description by **one blank line** (commitlint `body-leading-blank: always`)
- The body is free-form and **MAY** consist of any number of newline-separated paragraphs
- Each line **SHOULD** be ≤ 100 characters (commitlint `body-max-line-length: 100`)
- Suitable content: problem background, design trade-offs, rejected alternatives, migration impact, performance figures

---

## 6. footer (OPTIONAL)

Footers carry **structured metadata** and follow the [git trailer convention](https://git-scm.com/docs/git-interpret-trailers).

- Footers **MUST** appear after the body, separated by **one blank line** (commitlint `footer-leading-blank: always`)
- Each footer consists of a **token**, a separator, and a **value**
- The separator **MUST** be either `: ` (colon and space) or ` #` (space and hash)
- Whitespace inside a token **MUST** be replaced by `-`, to distinguish the footer section from a multi-paragraph body
- **Sole exception**: `BREAKING CHANGE` **MAY** be used as a token containing a space
- `BREAKING-CHANGE` is **synonymous** with `BREAKING CHANGE` when used as a footer token
- Footer lines **SHOULD** be ≤ 100 characters (commitlint `footer-max-line-length: 100`)

**Common tokens**:

| token | Purpose | Example |
|---|---|---|
| `BREAKING CHANGE` | Declares a breaking change | `BREAKING CHANGE: drop support for the v1 config format` |
| `Refs` | References issues or reverted commits | `Refs: #123` or `Refs: 676104e, a215868` |
| `Closes` | Auto-closes the issue on merge | `Closes: #123` |
| `Reviewed-by` | Reviewer | `Reviewed-by: Z` |
| `Co-authored-by` | Co-author (**GitHub uses this to add avatars and contribution credit**) | `Co-authored-by: Name <email@example.com>` |
| `Signed-off-by` | Developer Certificate of Origin (DCO) | `Signed-off-by: Name <email@example.com>` |

---

## 7. Breaking Changes

A breaking change **MUST** be declared in one of **exactly two ways**, located in the **header or a footer**:

**Method 1: the `!` marker (in the header)**

The `!` **MUST** sit immediately **before the colon**, that is, after `type` or `scope`:

```text
feat!: drop support for Node 6
feat(api)!: change response envelope
```

If `!` is used, the `BREAKING CHANGE:` footer **MAY** be omitted; the description is then taken as the explanation of the breaking change.

**Method 2: the `BREAKING CHANGE` footer**

`BREAKING CHANGE` **MUST** be uppercase, followed by a colon, a space, and the description:

```text
feat: allow provided config object to extend other configs

BREAKING CHANGE: `extends` key in config file is now used for extending other config files
```

**Key points**:

- A breaking change **MAY** belong to **any type**, not only `feat` — `fix!:` and `refactor!:` are equally valid
- Both methods **MAY** be used together; when they are, the change **SHOULD** be described in both places so a reader who sees only one still understands it
- The casing of `BREAKING CHANGE` is the **sole case-sensitivity exception** in the specification: every other unit is case-insensitive, but this token **MUST** be uppercase

---

## 8. Relation to SemVer and CHANGELOG

This is the **fundamental purpose** of adopting Conventional Commits: letting the version number and the changelog be **derived automatically** from commit history.

### 8.1 Version derivation

| Commit content | Version segment | Example |
|---|---|---|
| Contains `BREAKING CHANGE` (any type) | **MAJOR** | `1.4.2` → `2.0.0` |
| `feat` | **MINOR** | `1.4.2` → `1.5.0` |
| `fix` | **PATCH** | `1.4.2` → `1.4.3` |

Source: [Semantic Versioning 2.0.0](https://semver.org/) summary and the Conventional Commits FAQ.

### 8.2 CHANGELOG sections

When organized per [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), the default grouping of `conventional-changelog` is:

- `feat` → **Features**
- `fix` → **Bug Fixes**
- `perf` → **Performance Improvements**
- `revert` → **Reverts**
- All other types are **omitted** from the CHANGELOG by default (adjustable via the `hidden` option)

---

## 9. revert Commits

Conventional Commits **does not define** revert behavior; it leaves this to tooling. This convention adopts the approach recommended in the specification's FAQ:

- Use `revert` as the type
- Reference the reverted commit SHAs in a `Refs` footer

```text
revert: let us never again speak of the noodle incident

Refs: 676104e, a215868
```

A commit generated by `git revert` **SHOULD** have its subject rewritten into the imperative form required by this convention, while retaining the machine-readable footer. The body that `git revert` generates by default (`This reverts commit <sha>.`) **MAY** be kept.

**Note**: `revert` reverts **any previous commit**, not only the most recent one. When reverting several commits, **SHOULD** list each SHA in the footer.

---

## 10. GitHub Platform Conventions

### 10.1 Auto-closing issues

Using GitHub's closing keywords in a footer or body auto-closes the corresponding issue when the pull request merges:

```text
Closes #123
Fixes #123
Resolves #123
```

List several issues after one keyword: `Closes #123, #124`.
To reference without closing, use `Refs #123`.

### 10.2 Squash merge

When using GitHub's [Squash and merge](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/about-merge-methods-on-github), the pull request title becomes the final commit subject. Therefore:

- The PR title **MUST** also follow this convention (`type(scope): description`)
- Intermediate commits on the branch **MAY** be non-conforming, but **SHOULD** be tidied before merging
- Before merging, **SHOULD** review GitHub's prefilled commit message and delete auto-generated summary lines such as `* fix typo`

### 10.3 Co-authors

Adding a `Co-authored-by` trailer at the end of the commit message makes GitHub recognize that person as a co-author and count them in the contribution graph:

```text
Co-authored-by: Name <email@example.com>
```

### 10.4 Committer email

Commits to a public repository **MUST** use the private email address GitHub provides, so a real address never enters permanently public commit history:

```bash
# Format: <numeric ID>+<username>@users.noreply.github.com
git config user.name "Your Name"
git config user.email "12345678+username@users.noreply.github.com"
```

`--author` overrides the author only and does **NOT** override the committer; both are determined by `user.name` / `user.email`. Before publishing, you **MUST** verify that both are private addresses.

Printing email addresses to the terminal, a log, or a session record is **MUST NOT** — the verification command is itself a disclosure surface (corresponding to [CWE-532](https://cwe.mitre.org/data/definitions/532.html)). The check **SHOULD** emit only a verdict, where a hit count of `0` means pass. Format strings **SHOULD** avoid shell metacharacters such as `<`, `>`, and `|`, and use `--all` to cover history not reachable from HEAD.

Bash / Git Bash:

```bash
# Prints the count of NON-private addresses: 0 means pass
git log --all --format="%ae%n%ce" | sort -u \
  | grep -cvE '^([0-9]+\+)?[A-Za-z0-9-]+@users\.noreply\.github\.com$'
```

PowerShell:

```powershell
# Prints the count of NON-private addresses: 0 means pass
$bad = git log --all --format="%ae%n%ce" | Sort-Object -Unique |
       Where-Object { $_ -notmatch '^(\d+\+)?[A-Za-z0-9-]+@users\.noreply\.github\.com$' }
"non-noreply hits: $($bad.Count)"
```

If the result is not `0`, report only the hit count and the affected commit range; echoing the addresses themselves is **MUST NOT**. `git log --all --format="%h %ae"` can locate the specific commits, but note that its output also contains addresses.

See [GitHub Docs: Setting your commit email address](https://docs.github.com/en/account-and-profile/setting-up-and-managing-your-personal-account-on-github/managing-email-preferences/setting-your-commit-email).

---

## 11. Toolchain

A convention needs both a **generation** and a **validation** stage: commitizen helps you write it correctly, commitlint stops it when you don't.

### 11.1 commitlint (enforced on commit)

```bash
npm install --save-dev @commitlint/cli @commitlint/config-conventional husky
```

`commitlint.config.js`:

```js
export default {
  extends: ['@commitlint/config-conventional'],
  // Register any team extension types here
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

Enable the Git hook:

```bash
npx husky init
echo 'npx --no -- commitlint --edit "$1"' > .husky/commit-msg
```

Non-conforming commit messages are then **rejected outright**.

### 11.2 commitizen (interactive generation)

```bash
npm install -g commitizen
commitizen init cz-conventional-changelog --save --save-exact
```

Use `git cz` instead of `git commit` (after `git add`), then pick the type and fill in the scope (optional) and subject.

### 11.3 Manual verification

```bash
# Show the headers of recent commits
git log --oneline -20

# Validate a single message without committing
echo "feat(auth): add OAuth2 login" | npx commitlint
```

---

## 12. Examples

**Header only, no body or footer**

```text
docs: correct spelling of CHANGELOG
```

**With a scope**

```text
feat(lang): add Polish language
```

**Breaking change via the `!` marker**

```text
feat!: send an email to the customer when a product is shipped
```

```text
feat(api)!: send an email to the customer when a product is shipped
```

**Both `!` and a `BREAKING CHANGE` footer**

```text
feat!: drop support for Node 6

BREAKING CHANGE: use JavaScript features not available in Node 6.
```

**Breaking change declared by footer alone**

```text
feat: allow provided config object to extend other configs

BREAKING CHANGE: `extends` key in config file is now used for extending other config files
```

**Multi-paragraph body with multiple footers**

```text
fix: prevent racing of requests

Introduce a request id and a reference to latest request. Dismiss
incoming responses other than from latest request.

Remove timeouts which were used to mitigate the racing issue but are
obsolete now.

Reviewed-by: Z
Refs: #123
```

**Revert**

```text
revert: let us never again speak of the noodle incident

Refs: 676104e, a215868
```

---

## 13. Anti-pattern Reference

| ❌ Wrong | Rule violated | ✅ Correct |
|---|---|---|
| `feat : add login` | Space before the colon | `feat: add login` |
| `feat:add login` | Missing space after the colon | `feat: add login` |
| `Feat: add login` | `type` must be lowercase | `feat: add login` |
| `feature: add login` | Not a standard type | `feat: add login` |
| `init: bootstrap project` | `init` is not a standard type | `chore: bootstrap project` |
| `update code` | Missing type | `chore: update dependencies` |
| `fix: Fixed the login bug.` | Not imperative, starts uppercase, trailing period | `fix: correct login failure on expired token` |
| `fix: this commit fixes the problem where the user could not log in once the token had expired.` | Trailing period; far too verbose for a subject | `fix: correct login failure on expired token` |
| `feat(user login): add login` | Scope contains a space | `feat(auth): add login` |
| `feat(auth): new feature` | Description carries no information | `feat(auth): support OAuth2 login` |
| `feat(auth): add login`<br>(body on the very next line) | Body needs a leading blank line | Leave one blank line after the header |
| `chore: bump deps`<br>`BREAKING CHANGE: ...` | Footer needs a leading blank line | Leave one blank line before the footer |
| `fix: bugfix` | No separator, description too terse | `fix(parser): handle empty array input` |

---

## 14. References

Primary (normative) sources are listed first:

1. [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) — the mandatory baseline; sections 1–7 and 9 are drawn directly from its Specification and FAQ
2. [@commitlint/config-conventional](https://github.com/conventional-changelog/commitlint/tree/master/%40commitlint/config-conventional) — the `type` allow-list and every validation threshold (`header-max-length`, `subject-case`, `subject-full-stop`, and others)
3. [Angular commit message convention](https://github.com/angular/angular/blob/main/contributing-docs/commit-message-guidelines.md) — origin of the type set commitlint recommends
4. [Semantic Versioning 2.0.0](https://semver.org/) — version derivation in section 8.1
5. [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/) — CHANGELOG organization in section 8.2
6. [git-interpret-trailers](https://git-scm.com/docs/git-interpret-trailers) — source of the footer convention in section 6
7. [BCP 14: RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/info/rfc8174) — definition of the normative key words; RFC 8174 clarifies that they are normative **only in all capitals**
8. [GitHub Docs: Setting your commit email address](https://docs.github.com/en/account-and-profile/setting-up-and-managing-your-personal-account-on-github/managing-email-preferences/setting-your-commit-email) — section 10.4
9. [GitHub Docs: Linking a pull request to an issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/using-issues/linking-a-pull-request-to-an-issue) — section 10.1
10. [GitHub Docs: Creating a commit with multiple authors](https://docs.github.com/en/pull-requests/committing-changes-to-your-project/creating-and-editing-commits/creating-a-commit-with-multiple-authors) — section 10.3
11. [GitHub Docs: About merge methods](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/about-merge-methods-on-github) — squash merge in section 10.2
12. [A Note About Git Commit Messages](https://tbaggery.com/2008/04/19/a-note-about-git-commit-messages.html) — Tim Pope's 50/72 rule, the source of the length guidance in section 4 (**community practice, not a specification**)

---

## 15. Revision History

### v2.2 — English edition added

Added [commit-convention.en.md](commit-convention.en.md), maintained in **one-to-one correspondence** with the Chinese original (16 level-2 sections and 12 references in each).

The two files **MUST** be revised together: any rule added, changed, or removed in one **MUST** be mirrored in the other within the same change. Updating only one of them is a documentation defect.

### v2.1 — Closing the reference set

Re-audited against the standard "every rule traces to a reference, and every reference supports at least one rule", closing three gaps:

| Gap | Resolution | Source |
|---|---|---|
| Normative language cited RFC 2119 alone | Switched to BCP 14 (RFC 2119 + RFC 8174) and stated that key words are normative only in all capitals | [RFC 8174](https://www.rfc-editor.org/info/rfc8174) |
| Section 10.2 (squash merge) had no source | Added the GitHub merge-methods documentation | [GitHub merge methods](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/about-merge-methods-on-github) |
| Section 2.2 (forbidden types) had no source | Explicitly labeled as a convention of this document rather than a specification rule | — |
| Section 10.4 verification command echoed raw addresses | Changed to a verdict-only form, added `--all`, and removed shell metacharacters from the format string | [CWE-532](https://cwe.mitre.org/data/definitions/532.html) |

### v2.0 — Full revision against primary sources

**Corrected errors**

| Item | Original | Correction |
|---|---|---|
| Header format | `type(scope) : subject` | `type(scope): subject` — colon immediately after the parenthesis, one space after the colon |
| `BREAKING CHANGE` classification | Listed among the types | Moved out of the type list; documented as a footer token and `!` marker (section 7) |
| `init` | Listed as a usable type | Removed; `type-enum` reduced to commitlint's 11 standard values |
| description length | "no more than 50 characters" | Split into three distinct sources: specification (none) / commitlint (100) / community practice (50–72) |
| `revert` meaning | "reverts the most recent commit" | Reverts any previous commit; added the `Refs` footer form |
| `build` example | "grunt replaced by npm" | Corrected to "affects the build system or external dependencies"; the example is now a scope |
| `style` meaning | "code formatting change" | Added the qualifier "does not affect the meaning of the code" |
| Type list terminator | `……` | Removed the ellipsis in favor of explicit extension criteria (section 2.3) |

**Added**

- The complete three-part skeleton with per-line requirements (section 1)
- Footer construction: token, two separators, `-` substitution, `BREAKING-CHANGE` synonym (section 6)
- Casing rules and the `BREAKING CHANGE` uppercase exception
- Mood, case, and trailing-punctuation rules for `description` (section 4)
- Blank-line requirements for body and footer (sections 5 and 6)
- SemVer / CHANGELOG mapping tables (section 8)
- `scope` naming conventions and suggested values (section 3)
- GitHub platform conventions: issue auto-close, squash merge, co-authors, private email (section 10)
- A complete toolchain — commitlint + husky + commitizen — with runnable configuration (section 11)
- The anti-pattern reference (section 13)
- Table of contents and the normative-language note

**Editorial**

- References reordered with primary sources first, each annotated with the sections it supports
- Removed a second-hand blog source (the source of the original `init` and similar errors)
- Untranslated English blocks pasted mid-document were rewritten to match the surrounding style
- List items used as headings were replaced with proper Markdown heading levels
