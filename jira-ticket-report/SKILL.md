---
name: jira-ticket-report
description: Fetch Jira tickets using $HOME/jira.env by default and create detailed Markdown reports plus JSON data. Use when asked to collect Jira tickets, summarize Jira issues, report on Jira tickets, filter tickets by assignee or unassigned status, run Jira JQL, or analyze ticket status/history/comments.
metadata:
  author: "Mrityunjay Yadav <mrityu.yadav@yahoo.in>"
  version: 1.0.0
---

# Jira Ticket Report

Use this skill to fetch Jira issue data through Jira REST API and produce:

- A concise chat summary.
- A detailed Markdown report.
- A separate JSON data file next to the Markdown report.

Default output directory: `$HOME/jira-reports`. Use a user-provided output directory or file path when specified.

## Credentials

Use `$HOME/jira.env`. The fetch script loads this file by default, but you can also source it in a shell before running scripts:

```bash
set -a
. "$HOME/jira.env"
set +a
```

Never print or include Jira secrets in chat, reports, logs, command output summaries, or errors. Treat these as secret: `JIRA_API_TOKEN`, `JIRA_AUTH_HEADER`, `JIRA_EMAIL`, and any Authorization header.

The env file should provide:

- `JIRA_BASE_URL`, such as `https://example.atlassian.net`.
- Either `JIRA_EMAIL` plus `JIRA_API_TOKEN`, or `JIRA_AUTH_HEADER`.

Use `--env-file /path/to/jira.env` or set `JIRA_ENV_FILE=/path/to/jira.env` when credentials live somewhere else. Paths may use `$HOME` or `~`.

## Workflow

1. Determine the collection mode:
   - Exact ticket keys such as `ABC-123`.
   - JQL/search.
   - Assignee filter.
   - Unassigned filter.
2. Run `scripts/fetch_jira_tickets.py` to fetch and normalize Jira data.
3. Read the generated JSON.
4. Produce a concise chat summary.
5. Ensure the Markdown report is detailed and useful. If needed, edit the generated Markdown report after reading the JSON.

The script validates collection modes. Use exact keys or search filters/JQL in a single run, and use either `--assignee` or `--unassigned`, not both.

## Fetching

Run from the skill directory or pass the absolute script path.

Fetch exact keys:

```bash
python3 scripts/fetch_jira_tickets.py --keys ABC-123 DEF-456
```

Run JQL:

```bash
python3 scripts/fetch_jira_tickets.py --jql 'project = ABC AND statusCategory != Done ORDER BY updated DESC'
```

Filter by assigned user. Account IDs are used directly; email/display name values are resolved through Jira user search:

```bash
python3 scripts/fetch_jira_tickets.py --project ABC --assignee user@example.com
```

Fetch unassigned tickets:

```bash
python3 scripts/fetch_jira_tickets.py --project ABC --unassigned
```

Use a custom output directory:

```bash
python3 scripts/fetch_jira_tickets.py --keys ABC-123 --output-dir /path/to/reports
```

## Optional Data

Comments are opt-in:

- `--comments recent` fetches recent comments.
- `--comments all` fetches all comments.
- `--comments summarize` fetches comments so Codex can summarize them in the Markdown report.
- Default: comments are not fetched and the report should say `Comments: not fetched`.

Changelog/status history is opt-in:

- Use `--changelog` when the user asks for history, timeline, status transitions, aging analysis, or why tickets are stuck.

## Report Expectations

For each issue, include the bounded profile available from Jira:

- Key, summary, URL, issue type, status, priority.
- Assignee, reporter, creator.
- Project, parent/epic when available.
- Created, updated, due date, resolution date.
- Labels, components, fix versions.
- Description summary.
- Acceptance criteria if present.
- Linked issues.
- Subtasks.
- Attachments list only; do not download attachments.
- Comments only when requested.
- Changelog/status history only when requested.

For multi-ticket reports, include rollups:

- Ticket count by status, issue type, priority, and assignee.
- Unassigned count.
- Oldest and most recently updated tickets.
- Risks/blockers inferred from status, priority, stale updates, due dates, and comments when fetched.
- Clear next-action recommendations.

The generated Markdown includes lightweight inferred risks and next actions. When the user asks for deeper interpretation, read the JSON and refine those sections manually.

## Output

The fetch script prints the generated paths. Use those paths in the final answer.

Default names:

- Single ticket Markdown: `$HOME/jira-reports/ABC-123-report.md`
- Single ticket JSON: `$HOME/jira-reports/ABC-123-data.json`
- Multi-ticket Markdown: `$HOME/jira-reports/jira-report-YYYY-MM-DD-HHMMSS.md`
- Multi-ticket JSON: `$HOME/jira-reports/jira-report-YYYY-MM-DD-HHMMSS-data.json`

Final response should include:

- A concise summary of what was fetched.
- The Markdown report path.
- The JSON data path.
- Any limitations, such as comments or changelog not fetched.
