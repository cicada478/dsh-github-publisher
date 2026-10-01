---
name: github-project-publisher
description: "Publish a local project to GitHub end to end, covering pre-upload compliance audit; hard-blocking sensitive-information scan (API keys, tokens, passwords, personal data, payment credentials, secrets in logs); bilingual README and Release notes; GitHub noreply commit-identity enforcement; SHA256 checksums; and upload via gh/git to a private-first repository. Use for 上传 GitHub、发布到 GitHub、写 README、写 Release 文案、检查密钥或隐私泄露、生成校验和、准备开源发布. Stops for human review before uploading."
---

# GitHub project publisher

Take a locally developed project and prepare and perform its publication to GitHub. Work in the order below. The two gates are hard stops, not checkpoints to narrate and pass through.

Operate on the project the user named. If they named none, use the current working directory. **That target is usually outside the session workspace**, so file writes there require their own approval — tell the user this before you are blocked by it rather than after.

## Non-negotiable rules

1. **Never upload without an explicit instruction.** Passing the checks is not authorization. When the checks finish, present the drafts and stop.
2. **Never make a repository public** without a second, explicit instruction. New repositories are created **private**, always.
3. **Hard-block on secrets.** A `BLOCKER` finding forbids `git commit` and `git push`. Report the file and line.
4. **Never echo a secret or an email address** into the terminal, a report, a commit message, or a session record. Mask to at most the first 4 characters, e.g. `AKIA…(20)`. The audit report is itself a disclosure surface (CWE-532).
5. **Never modify global git configuration.** Use `--local` only.
6. **Never force-push, delete remote content, or rewrite history** without a per-item explicit confirmation.
7. **Treat `MAJOR` as a decision, not a warning.** A `MAJOR` finding does not block by itself, but it **does** require explicit human confirmation before you continue. Name each one, say what it means, and wait. Do not walk past it silently — a `MAJOR` that nobody decided on is indistinguishable from one that was never reported.

## Pipeline

### 0. Recon

Determine and report, without modifying anything: the project root (nearest ancestor containing `.git`, otherwise the working directory), the ecosystem and package manager (from manifest files), existing remotes, whether the tree has commits yet, `gh auth status`, and which secret-scanning engines are installed.

Engines matter: if neither `gitleaks` nor `trufflehog` is present, coverage falls back to the built-in rules and is materially weaker. Say so in the report instead of reporting an unqualified pass.

### 1. Compliance audit

Run `<skill-dir>/scripts/audit_repo.py` against the project root. It aggregates the static checks, the secret scan, and the identity check into one report.

Then close the gaps it found that are safe to close automatically: create a missing `.gitignore` from the ecosystem template, create a missing `.gitattributes` with `* text=auto eol=lf` (and `eol=crlf` for `*.bat` / `*.cmd`), and never add `.dsh/` to `.gitignore` when the project carries project-scoped skills.

**Not every finding is auto-closeable, and the ones that look like housekeeping are the dangerous ones.**

- `GIT-005` — a file that is tracked *and* matches `.gitignore` — is fixed with `git rm --cached`, which removes the file from version control.
- `GIT-004` — a file over 50 MB in history — is fixed only by rewriting history, which changes every affected SHA. Over 100 MB, GitHub refuses the push outright, so this blocks publication until it is dealt with. **`.gitignore` does not help here**: it prevents future commits and does nothing about the copy already in history.

Both change what the repository contains, so both are **per-item confirmations**, never automatic fixes. The findings read like tidying up; the actions are not.

**Read the `GIT-004` message before offering options.** It states whether the path is *still tracked* or *only in history*, and the correct options differ between those cases — never offer "add it to `.gitignore`" for a file that is no longer in the working tree, because there is nothing left to ignore. Prepared option cards with the trade-offs spelled out are in `references/interaction.md` section 6.

Confirm the repository name is pure ASCII. A non-ASCII name works but is percent-encoded in URLs and breaks casual use in shell scripts and CI.

### 2. Sensitive-information scan — BLOCKING

**Do not scan twice.** `audit_repo.py` in step 1 already ran this scan across all four surfaces; read its result. Invoke `scan_secrets.py` directly only when you need something the aggregate report does not carry — a single surface, `--format json`, or `--codeblock-soft` to re-classify a code-block hit:

```text
python <skill-dir>/scripts/scan_secrets.py --worktree --staged --history --artifacts
```

All four surfaces are required. Scanning the working tree alone cannot find a credential already committed, and a secret removed from `HEAD` is still in history and still visible via `git log -p`.

On any `BLOCKER`:

- Do not commit, do not push.
- Report file, line, rule ID, and severity.
- Report the value only as a mask.
- Offer remediation as a **per-item confirmation**: remove the file and add it to `.gitignore`, purge it from history, or — if it may already have been pushed — rotate the credential. Rotation is the only remediation that is actually sufficient once exposure is possible; say that plainly.

Exemptions follow `<skill-dir>/references/checks.md`. Prefer placeholder auto-downgrade. A manual allowlist entry **requires a reason**; an entry without one is invalid and must be reported as a problem, not honoured.

### 3. Commit identity

Run `<skill-dir>/scripts/check_identity.py`. It prints a verdict only and never an address.

If the effective `user.email` is not a GitHub noreply address, set it **locally**:

```text
git config --local user.email "<numeric-id>+<username>@users.noreply.github.com"
```

`--author` overrides the author only and does **not** override the committer, which always comes from `user.name` / `user.email`. Setting `--author` alone therefore does not protect the user. Also tell them to enable GitHub's *Block command line pushes that expose my email address*, so the server refuses the push even if the local check is missed.

If a real address is already in history, rewriting changes every affected SHA. Present it as a per-item confirmation and state the honest limit: once pushed to a public repository, the address cannot be recalled.

### 4. Documentation drafts

Draft, in the language the user chose (default: bilingual, Chinese primary plus an English mirror):

- **README** — structure from `<skill-dir>/references/templates.md`, which follows standard-readme.
- **CHANGELOG** — Keep a Changelog sections; derive entries from commit history by Conventional Commits type.
- **Release notes** — group `feat` / `fix` / `perf` / `revert`, call out breaking changes, derive the version by SemVer (`fix`→PATCH, `feat`→MINOR, breaking→MAJOR) and show the reasoning.
- **LICENSE** — only when absent; ask which license, never choose silently.

Never present a draft as final. These are the documents the user most needs to read.

### 5. Release artifacts and checksums

Run `<skill-dir>/scripts/make_checksums.py` over the release artifacts. This is unconditional — do not ask whether to do it. Record it in the audit report.

The output must be UTF-8 **without BOM** and **LF**, or `sha256sum -c` fails on Linux. The script handles this; do not regenerate the file by shell redirection, which reintroduces both problems.

---

## GATE 1 — human review

Stop here. Present:

1. the audit report path and its findings grouped by severity,
2. the README draft,
3. the Release-note draft,
4. the identity verdict,
5. the checksum summary,
6. anything the audit could not cover.

Then wait. Do not create a repository and do not push until the user explicitly asks. If they ask only for the checks, the task ends here.

---

### 6. Create the private repository and push

Only after Gate 1. Use `gh` and `git`; prefer them over any other mechanism.

```text
gh repo create <name> --private --source=<path> --remote=origin --push
```

Confirm the repository is private after creation (`gh repo view --json visibility`). Verify the pushed remote before announcing success — a local commit is not evidence that a push landed.

**If a push fails with a TLS error under DSH's file sandbox.** Windows git defaults to the `schannel` backend, which cannot acquire credentials in a confined session:

```text
schannel: AcquireCredentialsHandle failed: SEC_E_NO_CREDENTIALS (0x8009030E)
```

This is a property of the confined environment, not of the machine — the same command succeeds outside DSH, and `gh` is unaffected because it uses Go's own TLS stack. Point git at OpenSSL **for this repository only**:

```text
git config --local http.sslBackend openssl
```

A credential helper written as `!<command>` also needs git to spawn a shell, which the same confinement blocks (`couldn't create signal pipe`). That step needs the user to approve wider access — ask, rather than routing around it. **Do not put a token in the remote URL to bypass the helper**: the token would then live in `.git/config`, in the shell history, and in this session's record.

### 7. Post-upload verification

Re-check the remote: visibility is still `private`, the pushed commit's author and committer are both noreply, and no BLOCKER-class file reached the remote history. If any fails, say so immediately and stop.

---

## GATE 2 — publish

Making the repository public is a separate, explicit decision. Present what is about to become visible and wait for a second instruction. Then:

```text
gh repo edit <name> --visibility public --accept-visibility-change-consequences
gh release create <tag> --draft --notes-file <file> --title <title>
```

Add the checksum file as a release asset. Publish the release only when the repository visibility decision is settled.

## Decision policy

Route every decision point into exactly one class. Full table in `<skill-dir>/references/interaction.md`.

| Class | Behaviour | Examples |
|---|---|---|
| **Ask** | Present an option card with descriptions and a recommendation | repository name, target account, visibility, license, documentation language |
| **Confirm** | Require an explicit yes for this specific item | rewrite history, force-push, publicize, waive a BLOCKER |
| **Default and log** | Do it without asking, and record it | secret scan, SHA256 checksums, `.gitignore`, `.gitattributes`, local noreply identity |
| **Never** | Refuse without an explicit instruction | publicize, force-push to an existing remote, delete remote content, change global git config, echo a secret |

Do not ask about items in the third row. A question that is asked every time trains the user to answer it without reading, which destroys the value of every other question. Do it, and put the record in the report.

## Scripts

Resolve paths relative to this skill's base directory, which the `skill` tool reports.

| Script | Purpose |
|---|---|
| `scripts/audit_repo.py` | Aggregate audit; writes Markdown and JSON reports |
| `scripts/scan_secrets.py` | Secret and PII scan across four surfaces |
| `scripts/check_identity.py` | Noreply identity verdict; prints no addresses |
| `scripts/make_checksums.py` | Generate and verify coreutils-compatible `SHA256SUMS` |
| `scripts/selftest.py` | Self-test; runs in temporary directories |

They use the Python standard library only. Do not install packages for them.

**Version requirement and finding an interpreter.** They need **Python 3.9 or newer**. On anything older they exit with code `2` and a message naming the interpreter they actually got, rather than failing somewhere deeper with an error that has nothing to do with the real cause.

`python` is not guaranteed to exist, and is not guaranteed to be the version you expect — on Linux and macOS it may be absent, or may still be Python 2. Resolve an interpreter **before** running anything, trying in order:

1. `python`
2. `python3`
3. `py -3` (the Windows launcher)
4. the Python returned by `load_workspace_dependencies` — DSH supplies one, and it is the only path guaranteed to exist in a DSH deployment

Use the first that reports 3.9 or newer, and use that same interpreter for every script in the run. **If none qualifies, say so and stop.** Do not attempt a partial run, and never read "the command produced no output" as a pass.

Arguments, exit codes, and worked examples for each: `scripts/README.md`.

**Exit codes are uniform across every script**: `0` the check passed, `1` the check ran and did not pass, `2` the check could not run at all. Keep `2` distinct from `1` when you report — "the project was checked and failed" and "the check never happened" are different statements, and collapsing them turns an unrun check into an apparent pass.

## Reference files

This table is the complete list. Do not enumerate the skill directory.

| Task | File |
|---|---|
| Rule IDs, severities, exemption mechanism, self-scan false positives | `references/checks.md` |
| Rule-to-source mapping; the authoritative citation list | `references/standards.md` |
| What to ask, what to confirm, what to default, what to refuse | `references/interaction.md` |
| README / CHANGELOG / Release-note / audit-report templates | `references/templates.md` |
| Commit message convention | `references/commit-convention.md` (中文) · `references/commit-convention.en.md` (English) |

That directory's index — its three layers, the reading order, and why it is split this way — is `references/README.md`. Read it first when you need more than one of the files above.
