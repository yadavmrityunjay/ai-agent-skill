---
name: pr-mr-review
description: Review GitHub pull requests and GitLab merge requests using a diff-led workflow with provider metadata, discussion deduplication, optional linked issue context, classified findings, and confirmed-only posting. Use when asked to review a PR/MR, inspect diffs or discussions, assess changed behavior with repository context, or post GitHub/GitLab review feedback.
metadata:
  author: "Mrityunjay Yadav <mrityu.yadav@yahoo.in>"
  version: 1.0.0
---

# PR/MR Review Workflow Skill

## Purpose

Use this workflow to review GitHub PRs and GitLab MRs. The review is diff-led, read-first, and non-invasive:

- Do not modify repository files.
- Start from the PR/MR diff, metadata, and existing discussions.
- Inspect surrounding repository context only when needed to confirm behavior, risk, call sites, tests, configuration, or target-branch interactions.
- Default to report-only. Post comments, approve, request changes, resolve threads, or update review state only after explicit user confirmation in the current turn.

The goal is actionable review feedback across correctness, security, compatibility, maintainability, operations, test coverage, and alignment with the PR/MR intent or linked issue.

## How to Use the Skill

Before starting, confirm the required setup and inputs are available. Treat this as the intake checklist for a review request.

### Setup Requirements

- For GitHub PRs, `gh` is installed and authenticated for the target GitHub host.
- For GitLab MRs, `glab` is installed and authenticated for the target GitLab host.
- The authenticated account can read the PR/MR metadata, diff, checks/statuses, and discussions.
- Posting, approval, request-changes, or discussion updates are available only if the authenticated account has the required provider permissions.
- The local workspace can create a temporary detached `git worktree` when repository context is needed.
- MCP/API tools are optional fallbacks and are not required for normal CLI-first review.
- Linked issue access is optional. If Jira REST context is requested or discoverable, credentials should be stored in `$HOME/jira.env`; never paste Jira tokens, auth headers, or email addresses into chat.

### Input Required From the User

- Review target: a GitHub PR URL, a GitLab MR URL, `--repo <owner/repo> --pr <number>`, `--repo <group/project> --mr <iid>`, or enough local branch context to infer the target.
- Provider or host when it cannot be inferred from the URL or repository remote.
- Linked issue key or URL when it is not reliably discoverable from the PR/MR title, branch, body, labels, or commits.
- Jira requirement if Jira story context is mandatory; otherwise Jira remains optional and the review can continue without it.
- Posting intent: review-only by default; provider writes happen only after the user confirms the exact action in the current turn.

### Usage Examples

```text
Review GitHub PR https://github.com/example/app/pull/123. Use linked issue context if available, but do not post anything until I confirm.
```

```text
Review GitLab MR https://gitlab.example.com/group/project/-/merge_requests/456 using Jira PROJ-789. Do not post comments yet.
```

```text
Review --repo example/app --pr 123. Jira is required for this review; stop if story context is unavailable.
```

## Inputs

Accept any of these:

- GitHub PR URL or `--repo <owner/repo> --pr <number>`.
- GitLab MR URL or `--repo <group/project> --mr <iid>`.
- Enough local branch/remote context to infer the current PR/MR.
- Optional linked issue key or URL when it is not reliably discoverable.

Detect the provider from the URL, explicit input, repository remote, or available CLI context. If multiple providers or review targets are plausible, ask which one is authoritative before reviewing.

## Tooling

Prefer CLI-first tooling because it is broadly portable:

- GitHub: `gh pr view`, `gh pr diff`, `gh pr checks`, `gh pr review`, and `gh` issue/comment commands when needed.
- GitLab: `glab mr view`, `glab mr diff`, `glab mr note list`, `glab mr note create`, and related `glab` commands.
- MCP/API tools may be used when available and useful, especially for precise inline comment positioning, but this skill must not depend on a specific MCP server.

Verify the needed read capabilities before review and posting capabilities before any write. If the preferred CLI is unavailable or unauthenticated, ask the user to authenticate it or approve an available fallback.

## Workflow

Follow these steps in order.

### Step 1 — Resolve Target and Capabilities

1. Identify provider, repository, PR/MR number, source branch, target branch, and head/base SHAs when available.
2. Verify read access to metadata, diff, existing discussions, and checks/statuses.
3. Verify write access only if the user later asks to post, approve, request changes, or update review state.
4. Do not require linked issue access. Continue without issue context when it is unavailable and clearly state that limitation.

Useful commands:

```bash
gh pr view <number> --repo <owner/repo> --json title,body,author,baseRefName,headRefName,commits,files,reviewThreads,comments,statusCheckRollup
gh pr diff <number> --repo <owner/repo> --patch
gh pr checks <number> --repo <owner/repo>

glab mr view <iid> -R <group/project>
glab mr diff <iid> --raw --color=never -R <group/project>
glab mr note list <iid> -F json -R <group/project>
```

Use provider-specific equivalents when command flags differ by installed CLI version.

### Step 2 — Gather Context

Collect, before forming findings:

- PR/MR metadata: title, description/body, author, labels, source/target branches, commits, and checks/statuses.
- Raw diff and complete changed-file list.
- Existing open and resolved discussions to avoid duplicate feedback and verify whether prior requested changes were addressed.
- Optional linked issue context from Jira, GitHub Issues, GitLab Issues, Linear, or another tracker if discoverable or provided.

Detect linked issue references from the PR/MR title, branch, body, commits, labels, and explicit user input. Jira-style keys can use `[A-Z][A-Z0-9]+-\d+`; also recognize issue URLs and provider-native references such as `#123`.

Linked issue context is optional and generic. Never require Jira by default. If tracker credentials are needed, use environment-based authentication only and never print tokens, auth headers, cookies, email addresses, or other secrets in chat, logs, comments, or reports.

#### Optional Jira REST Context

When a Jira key is discoverable or provided, use Jira REST context to review the PR/MR from the story's point of view when credentials are available. Fetch only review-relevant context: summary, status, type, priority, description, acceptance criteria if present, labels, components, fix versions, linked issues, and recent comments. Summarize this context; do not quote large Jira text into provider comments.

When using Jira REST, authentication must come from `$HOME/jira.env`; never ask the user to paste Jira tokens, auth headers, or email addresses into chat. The file should provide `JIRA_BASE_URL`, `JIRA_API_TOKEN`, and `JIRA_EMAIL` or `JIRA_USERNAME`; prefer `JIRA_EMAIL` when both are present. If the Jira instance requires bearer/PAT auth, use `JIRA_AUTH_HEADER` from the file. Treat these as secret everywhere: `JIRA_API_TOKEN`, `JIRA_AUTH_HEADER`, `JIRA_EMAIL`, and any `Authorization` header.

Smoke-test Jira before fetching the issue, without printing secrets:

```bash
set -a
. $HOME/jira.env
set +a
JIRA_BASE_URL="${JIRA_BASE_URL%/}"
curl -sS -o /tmp/jira-myself.json -w '%{http_code} %{content_type}\n' \
  -u "${JIRA_EMAIL:-$JIRA_USERNAME}:$JIRA_API_TOKEN" \
  "$JIRA_BASE_URL/rest/api/2/myself"
```

For bearer/PAT auth:

```bash
set -a
. $HOME/jira.env
set +a
JIRA_BASE_URL="${JIRA_BASE_URL%/}"
curl -sS -o /tmp/jira-myself.json -w '%{http_code} %{content_type}\n' \
  -H "Authorization: $JIRA_AUTH_HEADER" \
  "$JIRA_BASE_URL/rest/api/2/myself"
```

Fetch the issue using the same auth mode:

```bash
set -a
. $HOME/jira.env
set +a
JIRA_BASE_URL="${JIRA_BASE_URL%/}"
curl -sS -o /tmp/jira-issue.json -w '%{http_code} %{content_type}\n' \
  -u "${JIRA_EMAIL:-$JIRA_USERNAME}:$JIRA_API_TOKEN" \
  "$JIRA_BASE_URL/rest/api/2/issue/<KEY>?fields=summary,status,issuetype,priority,description,comment,issuelinks,labels,components,fixVersions"
```

If using bearer/PAT auth, replace the Basic auth option with `-H "Authorization: $JIRA_AUTH_HEADER"` and keep the header value redacted from all output.

Jira failure handling:

- `200 application/json`: use Jira story context in the review.
- `401`: credentials are missing, expired, or using the wrong auth scheme. Ask for corrected environment setup or continue without Jira if the user agrees.
- `403 text/html` or any HTML response: treat Jira context as unavailable. Common causes are SSO/proxy denial, wrong `JIRA_BASE_URL`, wrong auth mode, missing project permission, or CAPTCHA/account lockout. Do not parse HTML or infer acceptance criteria.
- `403 application/json`: authenticated but not authorized for the issue/project. Ask for access, a different Jira key, or permission to continue without Jira.
- `404`: the key may be wrong or hidden by permissions. Verify the key before relying on Jira context.

If Jira remains unavailable, state that Jira story context and acceptance criteria were not reviewed. Do not invent story requirements, and do not block GitHub/GitLab review unless the user explicitly says Jira context is required.

### Step 3 — Build File Coverage Ledger

Derive the complete changed-file list from the provider diff before reviewing. Every changed/new/deleted file must receive exactly one status:

- `deep-reviewed`: business logic, contracts, security-sensitive code, migrations, config, tests, or files relevant to a finding.
- `skimmed`: low-risk code where the diff was read but no deep surrounding context was needed.
- `skipped-generated`: generated, vendored, binary, build artifact, or mechanical lockfile output with no review signal.
- `skipped-unavailable`: file content or context could not be accessed; explain why and do not claim full coverage.

Review every meaningful changed file, but do not waste deep review time on generated, vendored, binary, or purely mechanical output unless it carries dependency, security, compatibility, or supply-chain risk.

For more than 50 changed files, pause before deep review and propose chunked review. Chunk by coherent area when possible; otherwise chunk by priority and path. Present each chunk's findings separately so the user can understand and verify the comments before continuing.

### Step 4 — Inspect Repository Context

Do not evaluate diffs in isolation when behavior depends on surrounding code. Inspect nearby code, imports, callers, tests, schemas, configs, migrations, feature flags, deployment behavior, and target-branch interactions as needed.

Create a temporary detached worktree only when local repository context is needed and not already available safely:

```bash
git worktree add --detach /tmp/pr-mr-review-<provider>-<repo>-<id>-<shortsha> <head-sha-or-branch>
```

Treat the worktree as read-only. Clean it up after review unless the user asks to keep it. Report cleanup failures without forcing unrelated repository changes.

### Step 5 — Analyze Findings

Report only findings with concrete evidence. Each finding must include changed file/path, line or affected area when available, behavior risk, diff/context evidence, suggested fix or question, confidence, and discussion classification.

Review through these lenses:

- Security and privacy: injection, auth/authz, secrets, data exposure, unsafe deserialization, dependency risk, OWASP-relevant issues.
- Correctness and compatibility: logic errors, edge cases, broken contracts, migrations, API behavior, backwards compatibility.
- Reliability and operations: error handling, logging, observability, performance, concurrency, resource use, rollout risk.
- Maintainability and consistency: local architecture, naming, duplication, test strategy, style, documentation, i18n when relevant.
- Scope alignment: PR/MR intent, linked issue acceptance criteria if available, and unresolved prior review feedback.

Severity:

- 🔴 `Blocker`: likely production incident, security exposure, data loss, broken public contract, or merge must not proceed.
- 🟠 `High`: serious correctness, reliability, security, or compatibility issue that should be fixed before merge.
- 🟡 `Medium`: meaningful bug, missing validation, test gap, operational risk, or maintainability issue with plausible impact.
- 🔵 `Low`: minor correctness, readability, test, or maintainability improvement worth noting but not merge-blocking.
- 🟣 `Question`: unclear requirement or context gap where the reviewer should ask instead of assert.

Discussion classification:

- `new`: not already discussed.
- `duplicate`: already covered by an unresolved discussion.
- `resolved-but-recurring`: similar to a resolved discussion but still present.
- `follow-up`: builds on an existing discussion.

Suppress duplicates by default. Include `new`, `resolved-but-recurring`, and useful `follow-up` findings in the proposed comment.

Verdict rules:

- `Request changes` for any 🔴/🟠 finding or multiple material 🟡 findings.
- `Needs clarification` for material 🟣 questions.
- `Approve with comments` when only 🔵/minor comments remain.

## Present Before Posting

Before any provider write, present the review and exact proposed comment:

```text
Review Verdict: Request changes | Needs clarification | Approve with comments

Provider: GitHub | GitLab
Target: PR/MR identifier and title

What I checked:
- Metadata, diff, existing discussions, checks/statuses
- Linked issue context: <source/key/url> | unavailable/not reviewed
- Worktree context: yes/no, path if used
- Tests run: none unless explicitly run

File coverage:
- deep-reviewed: path, path
- skimmed: path, path
- skipped-generated: path or pattern, reason
- skipped-unavailable: path, reason

Findings:
1. 🔴 [Blocker] Title
   File: path:line or path
   Classification: new | duplicate | resolved-but-recurring | follow-up
   Confidence: high | medium
   Evidence: concise diff/context evidence
   Risk: concrete behavior impact
   Suggested fix: concrete change

Suppressed duplicates:
- Existing discussion already covers ...

Proposed provider comment:
<exact comment body that would be posted>

Choose action: post summary | post targeted | post both | approve | request changes | do not post
```

## Confirmed Actions Only

Only after the user explicitly confirms the exact action in the current turn:

- `post summary`: one consolidated PR/MR comment.
- `post targeted`: eligible inline comments only when line mapping is confident.
- `post both`: summary plus targeted comments.
- `approve`: approve the PR/MR. If there are 🔴/🟠 findings, confirm the user explicitly wants to approve despite them.
- `request changes`: submit the provider's request-changes state when supported.
- `do not post`: no provider writes.

For GitHub, prefer:

```bash
gh pr review <number> --repo <owner/repo> --comment --body "$BODY"
gh pr review <number> --repo <owner/repo> --approve --body "$BODY"
gh pr review <number> --repo <owner/repo> --request-changes --body "$BODY"
```

Use GitHub inline review comments only when the target path and diff position/line are confidently mapped. Use `gh api` or MCP/API tooling only when CLI review commands cannot express the needed operation.

For GitLab, prefer:

```bash
glab mr note create <iid> -R <group/project> --message "$BODY"
glab mr note create <iid> -R <group/project> --file <path> --line <new-line> --message "$BODY"
glab mr note create <iid> -R <group/project> --file <path> --old-line <old-line> --message "$BODY"
```

Use GitLab API/MCP only when needed for precise inline positioning, approvals, or request-changes behavior that the installed `glab` cannot handle. If a provider does not support the requested state change or the instance version lacks it, report that clearly and do not approximate the action.

Append a generated-by marker to new provider comments:

```text
---
Generated by Codex pr-mr-review.
```

Use the marker and existing discussions to avoid duplicate reposts. Update, delete, resolve, or reopen comments only when explicitly asked.

## Comment Template

Keep comments simple, peer-to-peer, and actionable. Do not use rigid headers like "Observation:" or "Impact:" inside provider comments.

For each finding, include:

1. **Title**: short constructive topic.
2. **Observation and impact**: what changed and why it matters in 1-2 sentences.
3. **Context**: relevant file path and exact line reference when available.
4. **Suggested approach**: concrete fix, question, or code snippet in the changed file's language when useful.

In the chat report, prefix each item with `**Finding #N — <file-or-id>**`. Strip that prefix when posting to the provider unless the user asks to keep it.

## Guardrails

- Keep findings tied to changed files or changed behavior. Do not run a whole-repository audit by default.
- Do not run tests/static analysis by default. Infer likely commands and recommend them; run only if explicitly asked or needed for scoped verification.
- Do not quote large linked-issue text into provider comments. Summarize only review-relevant context.
- Do not post, approve, request changes, resolve, unresolve, edit, delete, or reopen provider discussions without explicit confirmation in the current turn.
- Prefer consolidated comments by default. Use targeted inline comments only for confident file/line positions.
- Never print or expose secrets from CLIs, environment files, auth headers, tokens, cookies, or tracker credentials.
- Clean up temporary worktrees created for review and report cleanup failures.

## Completion Checklist

- [ ] Provider and target resolved.
- [ ] CLI/API capabilities verified for read operations.
- [ ] Metadata, raw diff, checks/statuses, and existing discussions collected.
- [ ] Linked issue context reviewed when available, or limitation stated.
- [ ] Complete changed-file coverage ledger built.
- [ ] Large PR/MR chunking proposed when changed files are `>50`.
- [ ] Repository context inspected where needed to confirm behavior.
- [ ] Findings classified by severity, confidence, and discussion status.
- [ ] Exact proposed provider comment presented before any write.
- [ ] User-confirmed action executed, or no provider write performed.
- [ ] Temporary worktree cleaned up when one was created.
