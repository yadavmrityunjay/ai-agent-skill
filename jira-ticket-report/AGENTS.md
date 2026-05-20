# Agent Instructions

This directory contains the `jira-ticket-report` Codex skill. Use it when the user asks to fetch Jira tickets, summarize Jira issues, run Jira JQL, report by assignee, or analyze Jira ticket data.

## Operating Rules

- Read `SKILL.md` first and follow its workflow.
- Use `scripts/fetch_jira_tickets.py` for Jira collection whenever possible.
- Load credentials from `$HOME/jira.env` by default, or from the user-provided env file.
- Never print, log, quote, summarize, or include Jira secrets in chat or generated files.
- Treat these as secrets: `JIRA_API_TOKEN`, `JIRA_AUTH_HEADER`, `JIRA_EMAIL`, and any `Authorization` header.
- Default output directory is `$HOME/jira-reports` unless the user requests another path.
- Always return both generated paths: the Markdown report and the JSON data file.
- Comments and changelog are opt-in. Do not fetch them unless the user asks for comments, history, timeline, stuck analysis, or status transitions.

## Expected Flow

1. Determine whether the request is for exact keys, JQL, assignee filtering, unassigned tickets, or another search filter.
2. Run the fetch script with the narrowest matching mode.
3. Read the generated JSON before finalizing the response.
4. Give a concise chat summary with counts, rollups, notable risks, and next actions when useful.
5. Mention limitations explicitly, especially when comments or changelog were not fetched.

## JQL Guidance

- For "assigned to me", prefer `assignee = currentUser()` when current assignment matters.
- For "assigned in the last year", use assignment history such as `assignee changed TO currentUser() AFTER "YYYY-MM-DD"` when Jira supports it.
- For "completed in the last year", use `resolutiondate >= "YYYY-MM-DD"` or the project’s completion field if the user specifies one.
- Be explicit in the final answer about which date field was used: created, updated, assigned, or completion/resolution.

## API Compatibility Notes

The bundled script targets Jira REST API v3. Some Jira Server/Data Center instances may require REST API v2 endpoints or may use a Bearer `JIRA_AUTH_HEADER`. If v3 calls fail with server-side errors, verify the auth scheme and Jira API version without exposing secrets, then use a local compatibility helper or patch the script conservatively.

## Generated Artifacts

Generated reports should include:

- Rollups by status, issue type, priority, and assignee.
- Unassigned count.
- Oldest and least recently updated tickets.
- Per-ticket bounded profile: key, summary, URL, type, status, priority, assignee, reporter, creator, project, parent/epic, dates, labels, components, fix versions, description summary, acceptance criteria, linked issues, subtasks, and attachment list.

Do not download Jira attachments.
