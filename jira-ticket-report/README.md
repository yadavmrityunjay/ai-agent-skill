# Jira Ticket Report Skill

Fetch Jira issues through the Jira REST API and generate a detailed Markdown report plus a normalized JSON data file.

## What It Does

- Fetches exact Jira issue keys.
- Runs arbitrary JQL searches.
- Filters tickets by project and assignee.
- Filters unassigned tickets.
- Optionally fetches comments.
- Optionally fetches changelog/status history.
- Produces a concise Markdown report and machine-readable JSON data.

## Credentials

By default, the skill reads credentials from:

```bash
$HOME/jira.env
```

The env file should define:

```bash
JIRA_BASE_URL=https://example.atlassian.net
JIRA_EMAIL=user@example.com
JIRA_API_TOKEN=...
```

Or:

```bash
JIRA_BASE_URL=https://jira.example.com
JIRA_AUTH_HEADER='Bearer ...'
```

Secrets must never be printed or copied into generated reports.

## Usage

Use this skill by asking Codex to fetch or summarize Jira tickets. The agent reads `SKILL.md`, loads Jira credentials from `$HOME/jira.env`, runs the internal fetch script, reads the generated JSON, and returns the report paths plus a concise summary.

Example prompts:

- `[$jira-ticket-report] Fetch ABC-123 and ABC-456`
- `[$jira-ticket-report] Fetch all PROJECT tickets assigned to me`
- `[$jira-ticket-report] Fetch all PROJECT tickets assigned to me in the last year based on assignment or completion date`
- `[$jira-ticket-report] Run this JQL: project = ABC AND statusCategory != Done ORDER BY updated DESC`
- `[$jira-ticket-report] Fetch unassigned tickets in project ABC`
- `[$jira-ticket-report] Summarize ABC-123 with recent comments`
- `[$jira-ticket-report] Analyze why ABC-123 is stuck and include status history`

The generated files are written to `$HOME/jira-reports` by default unless you ask for a different output directory.

## Internal Script

The agent normally runs `scripts/fetch_jira_tickets.py` for you. Direct script execution is mainly for skill development, debugging, or compatibility testing.

## Optional Data

Comments are disabled by default. Ask for them explicitly when needed:

- `[$jira-ticket-report] Fetch ABC-123 with recent comments`
- `[$jira-ticket-report] Fetch ABC-123 with all comments`
- `[$jira-ticket-report] Summarize ABC-123 and include comment summary`

Changelog/status history is disabled by default. Ask for it explicitly when needed:

- `[$jira-ticket-report] Fetch ABC-123 with changelog`
- `[$jira-ticket-report] Analyze ABC-123 status transitions`
- `[$jira-ticket-report] Explain why ABC-123 is stuck using ticket history`

Use changelog when the user asks for history, status transitions, aging analysis, or why tickets are stuck.

## Output

Default output directory:

```bash
$HOME/jira-reports
```

Single-ticket output:

```text
$HOME/jira-reports/ABC-123-report.md
$HOME/jira-reports/ABC-123-data.json
```

Multi-ticket output:

```text
$HOME/jira-reports/jira-report-YYYY-MM-DD-HHMMSS.md
$HOME/jira-reports/jira-report-YYYY-MM-DD-HHMMSS-data.json
```

## Report Contents

Each report includes:

- Ticket count and source query.
- Comments/changelog fetch status.
- Rollups by status, issue type, priority, and assignee.
- Unassigned count.
- Oldest and least recently updated tickets.
- Per-ticket details including summary, URL, type, status, priority, dates, parent/epic, labels, components, fix versions, description summary, acceptance criteria, linked issues, subtasks, and attachment list.

## Date Filtering Examples

Tickets currently assigned to you and assigned or completed in the last year:

```jql
project = PROJECT
AND assignee = currentUser()
AND (
  assignee changed TO currentUser() AFTER "2025-05-15"
  OR resolutiondate >= "2025-05-15"
)
ORDER BY updated DESC
```

Tickets created in the last year:

```jql
project = PROJECT
AND assignee = currentUser()
AND created >= "2025-05-15"
ORDER BY updated DESC
```

Be clear in summaries about whether the filter uses created date, updated date, assignment date, or completion/resolution date.

## Files

- `SKILL.md`: Runtime instructions for Codex.
- `AGENTS.md`: Maintenance and behavior guidance for agents editing or using this skill.
- `scripts/fetch_jira_tickets.py`: Jira fetcher and report generator.
- `agents/openai.yaml`: Skill packaging metadata.
