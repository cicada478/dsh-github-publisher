# dsh-github-publisher

English | [中文](README.md)

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)
![Dependencies](https://img.shields.io/badge/dependencies-none-brightgreen.svg)

> A [DSH](https://github.com/deepseek-ai) skill that standardises the path from a local project to a public GitHub release, and enforces sensitive-information review plus human verification before anything becomes visible.

---

## Table of Contents

- [1. What this is](#1-what-this-is)
- [2. The problem it solves](#2-the-problem-it-solves)
- [3. Installation](#3-installation)
- [4. Usage](#4-usage)
- [5. Pipeline and the two gates](#5-pipeline-and-the-two-gates)
- [6. Decision classes](#6-decision-classes)
- [7. Sensitive-information scanning](#7-sensitive-information-scanning)
- [8. Commit identity and private email](#8-commit-identity-and-private-email)
- [9. SHA256 checksums](#9-sha256-checksums)
- [10. Scripts](#10-scripts)
- [11. Repository layout](#11-repository-layout)
- [12. References](#12-references)
- [13. Known limitations](#13-known-limitations)
- [14. Contributing](#14-contributing)
- [15. License](#15-license)

---

## 1. What this is

`dsh-github-publisher` is a DSH skill that helps an AI agent prepare and perform a GitHub publication:

- **Pre-upload compliance audit** — directory structure, `.gitignore`, licensing, metadata consistency
- **Sensitive-information review** — API keys, tokens, passwords, personal data, payment credentials, including secrets written into logs
- **README and Release-note drafting** — bilingual drafts following published conventions
- **Commit-identity governance** — enforcement of the GitHub noreply private address
- **SHA256 checksums** — a verifiable `SHA256SUMS` for release artifacts
- **Controlled upload** — GitHub CLI and git throughout, with a private-first repository

The design goal is **reviewability**: every rule traces to a public source, and every conclusion can be independently checked. See [section 12](#12-references).

## 2. The problem it solves

The risk in publishing is not "does `git push` work". It is a small set of mistakes that **cannot be undone afterwards**:

| Risk | Consequence |
|---|---|
| A key, token, or password is committed | Once pushed, deleting it is not enough — it remains in history and caches, and the credential must be rotated |
| A real email address enters a commit | Permanently public in `git log`, and GitHub links it to your account |
| A secret is written into a log file | Logs are commonly committed, and rarely read before committing |
| A checksum file carries a BOM or CRLF | `sha256sum -c` fails on Linux and the artifact's integrity cannot be verified |
| Checksums are missing | Users cannot verify that a downloaded artifact is authentic |
| A repository is publicised before review | Content is visible to the world before a human has read the README |

This skill blocks these **locally**, and defaults to **not publishing**.

## 3. Installation

The skill follows DSH's local skill discovery rules: a skill is a directory bundle `<root>/<name>/SKILL.md`, scanned **one level deep only**.

DSH scans these skill roots in priority order:

| Rank | Source | Path |
|---|---|---|
| 100 | `project-dsh` | `<projectRoot>/.dsh/skills` |
| 200 | `project-agents` | `<projectRoot>/.agents/skills` |
| 300 | `custom` | config `customSkillDirs` |
| 400 | `user-dsh` | `<DSH_HOME>/skills` (default `~/.dsh/skills`) |
| 500 | `user-agents` | `<AGENTS_HOME>/skills` (default `~/.agents/skills`) |

The **project root** is the nearest ancestor containing `.git`; without one, the current working directory is used.

### Option 1: project-scoped

Place the skill directory under the target project's `.dsh/skills/`. Project-scoped skills should be committed so that collaborators get them on clone.

```powershell
# run from the target project root
New-Item -ItemType Directory -Force .dsh\skills | Out-Null
Copy-Item -Recurse <this-repo>\.dsh\skills\github-project-publisher .dsh\skills\
```

> The target project must contain `.git`, otherwise the project root cannot be resolved and the skill may not be discovered.

### Option 2: user-scoped

Install into `~/.dsh/skills/` to make it available in every project.

```powershell
Copy-Item -Recurse <this-repo>\.dsh\skills\github-project-publisher $env:USERPROFILE\.dsh\skills\
```

### Verifying the installation

Once installed, the skill appears in the session skill catalog. Load it with:

```text
/github-project-publisher
```

## 4. Usage

A DSH skill can be invoked two ways:

| Surface | Syntax | Behaviour |
|---|---|---|
| User invocation | `/github-project-publisher` | Typing it injects the skill's instructions into that step |
| Model invocation | the `skill` tool, with the name as argument | The agent loads it when the task matches the skill's description |

> The prefix is a slash `/`, not `$`. `/name` must be a whitespace-delimited standalone token.

### 4.1 Examples

```text
/github-project-publisher 检查当前项目，完善 README 和 Release 文案，并准备发布到 GitHub。
```

```text
/github-project-publisher 帮我审查这个项目有没有泄露密钥，然后生成 README。
```

```text
/github-project-publisher 只做上传前检查，先不要创建仓库。
```

```text
/github-project-publisher 检查最近的提交，确认作者和提交者邮箱都是 noreply 地址。
```

```text
/github-project-publisher 为 dist/ 下的产物生成 SHA256 校验和，并起草 Release 文案。
```

### 4.2 Output and gates

After the checks the skill **does not upload**. It presents:

1. **An audit report** — grouped by severity, with problem locations and no raw secret values
2. **A README draft** — for you to edit
3. **A Release-note draft** — for you to edit

Only an **explicit publish instruction** leads to a private repository being created and pushed; only a **second explicit instruction** makes it public.

## 5. Pipeline and the two gates

| # | Stage | Main actions | Gate |
|---|---|---|---|
| 0 | Recon | Ecosystem, package manager, git state | automatic |
| 1 | Compliance audit | Structure, `.gitignore`, license, metadata | automatic |
| 2 | **Sensitive-information scan** | Working tree + staged + history + artifacts | 🔴 **hard block** |
| 3 | Identity | Set noreply, verify author and committer | automatic |
| 4 | Documentation | README, CHANGELOG, LICENSE | drafts |
| 5 | Release artifacts | Version derivation, Release notes, **SHA256 checksums** | automatic + logged |
| 6 | **Human review gate** | Present report and drafts, **stop, do not upload** | 🔴 **first approval** |
| 7 | First upload | Create a **private** repository → push | requires first approval |
| 8 | Post-upload verification | Re-scan remotely, confirm visibility is still private | automatic |
| 9 | Publish | Make public + publish the Release with checksums | 🔴 **second approval** |

**Why two gates**: the first blocks the *upload*, the second blocks the *publication*. The private repository is itself a third layer — even if every earlier check missed something, the content stays inside your account.

## 6. Decision classes

Confusing "what to ask" with "what not to ask" produces two failures at once: silent defaults on questions that matter, and noise on questions that do not. Every decision point is assigned to one of four classes:

| Class | Meaning | Examples |
|---|---|---|
| 🟦 **Ask** | Irreversible or intent-dependent; presented as an option card | repository name, visibility, license, documentation language |
| 🟧 **Confirm** | Destructive or safety-loosening; needs an explicit yes | rewrite history, force-push, publicise, waive a BLOCKER |
| 🟩 **Default and log** | Unconditional; do not ask, but record it | secret scan, SHA256 checksums, `.gitignore`, `.gitattributes`, local noreply identity |
| 🔴 **Never** | Refused without an explicit instruction | publicise, force-push to an existing remote, delete remote content, change global git config, echo a secret |

The full table is in [`references/interaction.md`](.dsh/skills/github-project-publisher/references/interaction.md).

The key design point is the third row: actions that are **always** required — such as generating SHA256 checksums — must not be put to a vote. Asking every time trains the user to confirm without reading, which makes both the asked and the unasked questions meaningless. Do it, and put the record in the audit report.

## 7. Sensitive-information scanning

### Four scan surfaces

| Surface | Coverage | Why it is needed |
|---|---|---|
| Working tree | All version-controlled files | The baseline check |
| Staged | `git diff --cached` | Precisely "what is about to be committed" |
| **Git history** | All commits | **Removing a file from HEAD is not enough** — the secret is still in history and visible via `git log -p` |
| Logs and artifacts | `*.log`, `dist/`, notebook output, CI config | Corresponds to CWE-532, and is the most commonly overlooked |

### Detection engine

**External tool first, built-in rules as fallback:**

1. If `gitleaks` is present, run `gitleaks detect`
2. Otherwise try `trufflehog`
3. If neither is available, fall back to the built-in rule set and **state which engine was used**

A fallback materially reduces coverage, so the output must say so — otherwise it implies unchanged scrutiny.

### Blocking on a hit

On a `BLOCKER` finding:

- `git commit` and `git push` are **forbidden**
- The **file path and line number** are reported
- The **value is never echoed** — only a mask such as `AKIA…(20)`

The last point is deliberate: the audit report is itself a disclosure surface. Printing a key into a terminal, a CI log, or a session record simply moves the leak elsewhere. See [CWE-532](https://cwe.mitre.org/data/definitions/532.html).

### Self-scan false positives and exemptions

The skill scans **itself** — its own documentation contains example addresses and placeholder keys. Without handling, the first self-run reports false positives.

False positives are the primary failure mode of such tools: once alerts are ignored a few times, the hard block is dead in practice. Two exemption paths therefore exist:

**Path 1 — placeholder auto-downgrade (preferred)**

Recognised documentation placeholders are downgraded to `INFO` and excluded from findings: `example.com`, `your_`, `xxxx`, `<...>`, `AKIAIOSFODNN7EXAMPLE`, `12345678+username@users.noreply.github.com`, and others.

**Path 2 — explicit allowlist (requires a reason)**

In the scanned project's `.github-upload-audit/allowlist.txt`:

```text
SEC-001  .dsh/skills/*/references/*.md  *  -- 文档示例中的占位密钥
SEC-006  README.md  42  -- 示例邮箱
```

Format: `<rule-id> <path-glob> <line|*> -- <reason>`.

**An entry without a reason is rejected** and reported as a problem. Every applied exemption is written into the audit report — part of the "every deliberate action leaves a trace" principle.

> **Deliberately not implemented**: exempting "everything inside a fenced code block". That would let a real key pasted into a README slide through — and pasting a key into a README is one of the most common disclosure shapes. A single explicit, justified exemption is preferable to a rule that silently passes things.

## 8. Commit identity and private email

Before committing to a public repository, the identity **must** be set to the private address GitHub provides:

```powershell
# Format: <numeric ID>+<username>@users.noreply.github.com
git config --local user.name  "your-handle"
git config --local user.email "149449562+your-handle@users.noreply.github.com"
```

### Two easy mistakes

**First: `--author` does not cover the committer.**

`git commit --author=...` overrides the **author** only; the **committer** always comes from `user.name` / `user.email`. So using `--author` alone does not protect you. The correct fix is to set `user.email` itself to the noreply address.

Also, `--author` requires the `Name <email>` form — **the angle brackets are not optional**.

**Second: the verification command itself leaks the address.**

Running this prints the real address into the terminal, logs, and session records:

```bash
git log --format='%an <%ae> | %cn <%ce>'   # ❌ do not use where logs are retained
```

Use a **verdict-only** form instead, with `--all` to cover history not reachable from HEAD:

```powershell
# prints the count of NON-private addresses: 0 means pass
$bad = git log --all --format="%ae%n%ce" | Sort-Object -Unique |
       Where-Object { $_ -notmatch '^(\d+\+)?[A-Za-z0-9-]+@users\.noreply\.github\.com$' }
"non-noreply hits: $($bad.Count)"
```

Avoid `<`, `>`, and `|` in the format string. They are safe when quoted in PowerShell and bash, but fail outright in `cmd.exe`.

### Also enable server-side blocking

GitHub → Settings → Emails → enable:

- *Keep my email addresses private*
- *Block command line pushes that expose my email address*

Then GitHub refuses the push even if the local check was missed. Local check plus server-side backstop.

> **An honest limit**: if a real address has **already been pushed** to a public repository, rewriting history **cannot recall it** — it may already be forked, cached, or archived. Once exposure is possible, the only fully sufficient remediation is to rotate the credential and accept that the address is public.

## 9. SHA256 checksums

Release artifacts **must** ship with SHA256 checksums. This is a "default and log" action: it is not asked about, but it is recorded.

```powershell
python .\.dsh\skills\github-project-publisher\scripts\make_checksums.py dist\* --out SHA256SUMS
```

The generated `SHA256SUMS` is coreutils-compatible:

```text
<64 lowercase hex digits>  <relative path>
```

Two spaces, forward-slash paths, entries sorted for reproducibility.

### Three fatal details

| Detail | Consequence |
|---|---|
| Must be **UTF-8 without BOM** | A BOM makes `sha256sum -c` fail outright on Linux |
| Must use **LF** line endings | CRLF breaks parsing or produces mismatches |
| Needs `Get-FileHash`, not `sha256sum` | `sha256sum` does not exist on Windows; the output must be reformatted into coreutils form |

The script writes files with `open(path, "w", encoding="utf-8", newline="\n")` precisely to avoid both problems.

## 10. Scripts

All scripts use the **Python standard library only** — a deliberate constraint, because an audit tool that needs installed dependencies cannot be run with confidence in a locked-down environment.

| Script | Purpose |
|---|---|
| `scripts/scan_secrets.py` | Secret and PII scan across four surfaces (external tool first, built-in fallback) |
| `scripts/check_identity.py` | Verify author and committer are both noreply; prints a verdict only |
| `scripts/make_checksums.py` | Generate and verify coreutils-compatible `SHA256SUMS` |
| `scripts/audit_repo.py` | Aggregate the checks into Markdown and JSON reports |
| `scripts/selftest.py` | Self-test; runs entirely in temporary directories |

```powershell
# self-test
python .\.dsh\skills\github-project-publisher\scripts\selftest.py

# scan the current project
python .\.dsh\skills\github-project-publisher\scripts\scan_secrets.py --worktree --history

# verify commit identity
python .\.dsh\skills\github-project-publisher\scripts\check_identity.py

# full audit
python .\.dsh\skills\github-project-publisher\scripts\audit_repo.py
```

Arguments and exit codes are documented in [`scripts/README.md`](.dsh/skills/github-project-publisher/scripts/README.md).

## 11. Repository layout

```text
dsh-github-publisher/
├─ README.md                 Chinese (primary)
├─ README.en.md              English (this file)
├─ LICENSE                   MIT
├─ CHANGELOG.md              Keep a Changelog
├─ CONTRIBUTING.md           Includes the commit convention and bilingual sync rule
├─ SECURITY.md               Security policy and threat model
├─ .gitignore
├─ .gitattributes            Line-ending governance (LF inside the repository)
├─ .github/
│  ├─ workflows/ci.yml       CI quality gates (tests, scan, encoding, bilingual, frontmatter)
│  ├─ ISSUE_TEMPLATE/
│  ├─ PULL_REQUEST_TEMPLATE.md
│  └─ dependabot.yml
├─ .github-upload-audit/
│  └─ allowlist.txt          Exemption list (reports are ignored; this file is tracked)
└─ .dsh/skills/github-project-publisher/
   ├─ SKILL.md                         Agent-facing instructions
   ├─ references/
   │  ├─ standards.md                  Citation list (rule ↔ source mapping)
   │  ├─ checks.md                     Check catalog (rule IDs, severities)
   │  ├─ interaction.md                Decision classes
   │  ├─ templates.md                  Document templates
   │  ├─ commit-convention.md          Commit convention (中文)
   │  └─ commit-convention.en.md       Commit convention (English)
   └─ scripts/                         Standard-library-only Python
```

## 12. References

Every rule traces to at least one of the following **primary** sources; conversely, every source below supports at least one executable rule — there are no decorative citations.

### Commit messages and versioning

| Source | Rules it supports |
|---|---|
| [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) | Three-part commit structure, `type` semantics, `!` and `BREAKING CHANGE` footers, footer construction |
| [@commitlint/config-conventional](https://github.com/conventional-changelog/commitlint/tree/master/%40commitlint/config-conventional) | The `type` allow-list (11 values), `header-max-length`, `subject-case`, `subject-full-stop` |
| [Semantic Versioning 2.0.0](https://semver.org/) | Version derivation: `fix`→PATCH, `feat`→MINOR, breaking→MAJOR |
| [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/) | CHANGELOG structure and section headings |

### Documentation structure

| Source | Rules it supports |
|---|---|
| [standard-readme](https://github.com/RichardLitt/standard-readme) | README section skeleton (Title / Badges / Install / Usage / Contributing / License) |
| [GitHub Docs: About READMEs](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes) | How GitHub renders and surfaces a README |

### Licensing

| Source | Rules it supports |
|---|---|
| [SPDX License List](https://spdx.org/licenses/) | Standard license identifiers |
| [Choose a License](https://choosealicense.com/) | License selection criteria |

### Security and privacy

| Source | Rules it supports |
|---|---|
| [CWE-798: Use of Hard-coded Credentials](https://cwe.mitre.org/data/definitions/798.html) | Hard-coded keys, tokens, and passwords (SEC-001 – SEC-003) |
| [CWE-532: Insertion of Sensitive Information into Log File](https://cwe.mitre.org/data/definitions/532.html) | Log/artifact scan surface, report masking, verdict-only identity checks |
| [The Twelve-Factor App §III. Config](https://12factor.net/config) | Configuration in the environment, not in code |
| [FIPS 180-4](https://csrc.nist.gov/pubs/fips/180-4/upd1/final) | The SHA-256 algorithm definition |

### Git and platform

| Source | Rules it supports |
|---|---|
| [gitattributes(5)](https://git-scm.com/docs/gitattributes) | `.gitattributes` rules, binary detection, `export-ignore` |
| [GitHub Docs: Configuring Git to handle line endings](https://docs.github.com/en/get-started/getting-started-with-git/configuring-git-to-handle-line-endings) | LF inside the repository, with the `*.bat` / `*.cmd` CRLF exception |
| [github/gitignore](https://github.com/github/gitignore) | `.gitignore` template source |
| [GitHub Docs: Setting your commit email address](https://docs.github.com/en/account-and-profile/setting-up-and-managing-your-personal-account-on-github/managing-email-preferences/setting-your-commit-email) | Noreply address format and server-side blocking |
| [GitHub Docs: Community profiles](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/about-community-profiles-for-public-repositories) | `SECURITY.md`, `CONTRIBUTING.md`, issue and PR templates |
| [GitHub CLI manual](https://cli.github.com/manual/) | The authoritative source for `gh repo create`, `gh release create`, `gh repo edit` |

### Normative language and baseline

| Source | Rules it supports |
|---|---|
| [BCP 14: RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) + [RFC 8174](https://www.rfc-editor.org/info/rfc8174) | Normative keywords throughout this documentation (uppercase only) |
| [OpenSSF Scorecard](https://github.com/ossf/scorecard) | Design reference for the repository security baseline checks |

> The complete three-way mapping of rule ID ↔ source ↔ check is in [`references/standards.md`](.dsh/skills/github-project-publisher/references/standards.md).

## 13. Known limitations

A security review tool **cannot** achieve zero misses. This project states its limits explicitly:

- The built-in rule set covers only common credential shapes; business-specific sensitive data formats are not recognised
- Without `gitleaks` or `trufflehog` installed, detection falls back to the built-in rules and coverage drops substantially
- Binary files, encrypted archives, and text embedded in images are not scanned
- Placeholder auto-downgrade relies on a fixed list and can be defeated by a deliberately constructed string
- Scanning the working tree **cannot** find credentials already committed in history

**None of this constitutes a guarantee that a clean result means the project is safe.** Every publish decision still requires human verification — which is exactly why the skill enforces two manual gates.

## 14. Contributing

Please read [CONTRIBUTING.md](CONTRIBUTING.md) first. In short:

- Commit messages must follow the [commit convention](.dsh/skills/github-project-publisher/references/commit-convention.en.md)
- Documentation changes must be applied to **both** languages
- A new rule requires a **source** and a **false-positive assessment**
- Scripts **must not** introduce third-party dependencies
- All text files are UTF-8 without BOM, LF endings

## 15. License

[MIT](LICENSE) © 2026 cicada478
