#!/usr/bin/env python3
"""Fetch Jira issues and write normalized JSON plus a Markdown report."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")
ACCOUNT_ID_RE = re.compile(r"^[a-f0-9]{24,}(:[a-f0-9-]+)?$")
DEFAULT_ENV_FILE = "$HOME/jira.env"


def expand_path(value: str) -> Path:
    return Path(os.path.expandvars(value)).expanduser()


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def auth_header() -> str:
    explicit = os.environ.get("JIRA_AUTH_HEADER", "").strip()
    if explicit:
        return explicit if explicit.lower().startswith("basic ") else f"Basic {explicit}"

    email = env("JIRA_EMAIL")
    token = env("JIRA_API_TOKEN")
    raw = f"{email}:{token}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


class JiraClient:
    def __init__(self, base_url: str, authorization: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.authorization = authorization

    def request(self, method: str, path: str, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> Any:
        url = self.base_url + path
        if params:
            query = urllib.parse.urlencode(params, doseq=True)
            url = f"{url}?{query}"

        data = None
        headers = {
            "Accept": "application/json",
            "Authorization": self.authorization,
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = response.read()
        except urllib.error.HTTPError as exc:
            message = exc.read().decode("utf-8", errors="replace")
            raise SystemExit(f"Jira API error {exc.code} for {path}: {redact(message)}") from exc
        except urllib.error.URLError as exc:
            raise SystemExit(f"Jira API connection error for {path}: {exc.reason}") from exc

        if not payload:
            return None
        return json.loads(payload.decode("utf-8"))

    def get_issue(self, key: str, expand: str | None = None) -> dict[str, Any]:
        params = {"expand": expand} if expand else None
        return self.request("GET", f"/rest/api/3/issue/{urllib.parse.quote(key)}", params=params)

    def search(self, jql: str, max_results: int) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        next_page_token = None
        while True:
            body = {
                "jql": jql,
                "maxResults": min(100, max_results - len(issues)),
                "fields": ["*all"],
            }
            if next_page_token:
                body["nextPageToken"] = next_page_token
            result = self.request("POST", "/rest/api/3/search/jql", body=body)
            batch = result.get("issues", [])
            issues.extend(batch)
            next_page_token = result.get("nextPageToken")
            if len(issues) >= max_results or result.get("isLast") or not next_page_token or not batch:
                return issues

    def find_user(self, query: str) -> dict[str, Any]:
        users = self.request("GET", "/rest/api/3/user/search", params={"query": query, "maxResults": 10})
        if not users:
            raise SystemExit(f"No Jira user matched assignee query: {query}")

        query_lower = query.lower()
        exact = [
            user
            for user in users
            if query_lower
            in {
                str(user.get("emailAddress", "")).lower(),
                str(user.get("displayName", "")).lower(),
                str(user.get("accountId", "")).lower(),
            }
        ]
        if len(exact) == 1:
            return exact[0]
        if len(users) == 1:
            return users[0]

        choices = ", ".join(f"{u.get('displayName')} ({u.get('accountId')})" for u in users[:5])
        raise SystemExit(f"Assignee query is ambiguous: {query}. Matches: {choices}")

    def comments(self, key: str, mode: str, recent_count: int) -> list[dict[str, Any]]:
        if mode == "none":
            return []

        comments: list[dict[str, Any]] = []
        start_at = 0
        while True:
            result = self.request(
                "GET",
                f"/rest/api/3/issue/{urllib.parse.quote(key)}/comment",
                params={"startAt": start_at, "maxResults": 100, "orderBy": "created"},
            )
            batch = result.get("comments", [])
            comments.extend(batch)
            if start_at + len(batch) >= result.get("total", 0) or not batch:
                break
            start_at += len(batch)

        if mode == "recent":
            return comments[-recent_count:]
        return comments

    def field_names(self) -> dict[str, str]:
        fields = self.request("GET", "/rest/api/3/field")
        return {field.get("id"): field.get("name", "") for field in fields if field.get("id")}


def redact(value: str) -> str:
    for secret_name in ("JIRA_API_TOKEN", "JIRA_AUTH_HEADER", "JIRA_EMAIL"):
        secret = os.environ.get(secret_name, "")
        if secret:
            value = value.replace(secret, "[REDACTED]")
    return value


def adf_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(filter(None, (adf_to_text(item) for item in value)))
    if not isinstance(value, dict):
        return str(value)

    parts: list[str] = []
    text = value.get("text")
    if text:
        parts.append(str(text))
    for child in value.get("content", []) or []:
        child_text = adf_to_text(child)
        if child_text:
            parts.append(child_text)
    return " ".join(parts).strip()


def user_name(value: dict[str, Any] | None) -> str:
    if not value:
        return "Unassigned"
    return value.get("displayName") or value.get("emailAddress") or value.get("accountId") or "Unknown"


def names(values: list[dict[str, Any]] | None) -> list[str]:
    return [str(item.get("name") or item.get("value") or item.get("key")) for item in values or []]


def first_custom_field(fields: dict[str, Any], field_names: dict[str, str], labels: tuple[str, ...]) -> Any:
    lowered = {label.lower() for label in labels}
    for key, value in fields.items():
        field_name = field_names.get(key, key)
        if key.lower() in lowered or field_name.lower() in lowered:
            return value
    return None


def normalize_issue(
    issue: dict[str, Any],
    base_url: str,
    field_names: dict[str, str],
    comments: list[dict[str, Any]],
    comments_mode: str,
) -> dict[str, Any]:
    fields = issue.get("fields", {})
    parent = fields.get("parent") or {}
    rendered_comments = [
        {
            "id": comment.get("id"),
            "author": user_name(comment.get("author")),
            "created": comment.get("created"),
            "updated": comment.get("updated"),
            "body": adf_to_text(comment.get("body")),
        }
        for comment in comments
    ]

    return {
        "key": issue.get("key"),
        "url": f"{base_url.rstrip('/')}/browse/{issue.get('key')}",
        "summary": fields.get("summary"),
        "issue_type": (fields.get("issuetype") or {}).get("name"),
        "status": (fields.get("status") or {}).get("name"),
        "status_category": ((fields.get("status") or {}).get("statusCategory") or {}).get("name"),
        "priority": (fields.get("priority") or {}).get("name"),
        "assignee": user_name(fields.get("assignee")),
        "assignee_account_id": (fields.get("assignee") or {}).get("accountId") if fields.get("assignee") else None,
        "reporter": user_name(fields.get("reporter")),
        "creator": user_name(fields.get("creator")),
        "project": (fields.get("project") or {}).get("key"),
        "project_name": (fields.get("project") or {}).get("name"),
        "parent_key": parent.get("key"),
        "parent_summary": (parent.get("fields") or {}).get("summary"),
        "created": fields.get("created"),
        "updated": fields.get("updated"),
        "due_date": fields.get("duedate"),
        "resolution_date": fields.get("resolutiondate"),
        "labels": fields.get("labels") or [],
        "components": names(fields.get("components")),
        "fix_versions": names(fields.get("fixVersions")),
        "description": adf_to_text(fields.get("description")),
        "acceptance_criteria": adf_to_text(first_custom_field(fields, field_names, ("acceptance criteria", "acceptance criteria/scope"))),
        "linked_issues": normalize_links(fields.get("issuelinks") or []),
        "subtasks": [
            {
                "key": subtask.get("key"),
                "summary": (subtask.get("fields") or {}).get("summary"),
                "status": ((subtask.get("fields") or {}).get("status") or {}).get("name"),
            }
            for subtask in fields.get("subtasks") or []
        ],
        "attachments": [
            {
                "filename": attachment.get("filename"),
                "author": user_name(attachment.get("author")),
                "created": attachment.get("created"),
                "size": attachment.get("size"),
                "mime_type": attachment.get("mimeType"),
            }
            for attachment in fields.get("attachment") or []
        ],
        "comments_mode": comments_mode,
        "comments": rendered_comments,
        "changelog": normalize_changelog(issue.get("changelog", {})),
    }


def normalize_links(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    links: list[dict[str, Any]] = []
    for link in values:
        linked = link.get("outwardIssue") or link.get("inwardIssue")
        if not linked:
            continue
        fields = linked.get("fields") or {}
        links.append(
            {
                "key": linked.get("key"),
                "summary": fields.get("summary"),
                "status": (fields.get("status") or {}).get("name"),
                "type": (link.get("type") or {}).get("name"),
                "direction": "outward" if link.get("outwardIssue") else "inward",
            }
        )
    return links


def normalize_changelog(changelog: dict[str, Any]) -> list[dict[str, Any]]:
    histories = changelog.get("histories") or []
    rows: list[dict[str, Any]] = []
    for history in histories:
        items = []
        for item in history.get("items") or []:
            if item.get("field") in {"status", "assignee", "priority", "resolution"}:
                items.append(
                    {
                        "field": item.get("field"),
                        "from": item.get("fromString"),
                        "to": item.get("toString"),
                    }
                )
        if items:
            rows.append(
                {
                    "created": history.get("created"),
                    "author": user_name(history.get("author")),
                    "items": items,
                }
            )
    return rows


def build_jql(args: argparse.Namespace, client: JiraClient) -> str:
    clauses: list[str] = []
    order_by = "ORDER BY updated DESC"
    if args.jql:
        jql_body, existing_order_by = split_order_by(args.jql)
        clauses.append(f"({jql_body})")
        if existing_order_by:
            order_by = existing_order_by
    if args.project:
        clauses.append(f"project = {quote_jql_value(args.project)}")
    if args.assignee:
        assignee = args.assignee
        if not ACCOUNT_ID_RE.match(assignee):
            assignee = client.find_user(assignee)["accountId"]
        clauses.append(f"assignee = {quote_jql_value(assignee)}")
    if args.unassigned:
        clauses.append("assignee is EMPTY")
    if not clauses:
        raise SystemExit("Provide --keys, --jql, --project, --assignee, or --unassigned.")
    return " AND ".join(clauses) + f" {order_by}"


def split_order_by(jql: str) -> tuple[str, str | None]:
    match = re.search(r"\border\s+by\b", jql, flags=re.IGNORECASE)
    if not match:
        return jql.strip(), None
    return jql[: match.start()].strip(), jql[match.start() :].strip()


def quote_jql_value(value: str) -> str:
    if re.match(r"^[A-Za-z0-9_.:-]+$", value):
        return value
    return '"' + value.replace('"', '\\"') + '"'


def markdown_report(data: dict[str, Any]) -> str:
    issues = data["issues"]
    lines = [
        f"# Jira Ticket Report",
        "",
        f"- Generated: {data['generated_at']}",
        f"- Source: {data['source']}",
        f"- Ticket count: {len(issues)}",
        f"- Comments: {data['options']['comments'] if data['options']['comments'] != 'none' else 'not fetched'}",
        f"- Changelog: {'fetched' if data['options']['changelog'] else 'not fetched'}",
        "",
    ]
    if issues:
        lines.extend(summary_rollup(issues))
        lines.extend(risks_and_next_actions(issues))
    for issue in issues:
        lines.extend(issue_markdown(issue))
    return "\n".join(lines).rstrip() + "\n"


def summary_rollup(issues: list[dict[str, Any]]) -> list[str]:
    status = Counter(issue.get("status") or "Unknown" for issue in issues)
    types = Counter(issue.get("issue_type") or "Unknown" for issue in issues)
    priorities = Counter(issue.get("priority") or "Unknown" for issue in issues)
    assignees = Counter(issue.get("assignee") or "Unassigned" for issue in issues)
    oldest = sorted(issues, key=lambda issue: issue.get("created") or "")[:5]
    stale = sorted(issues, key=lambda issue: issue.get("updated") or "")[:5]

    return [
        "## Rollup",
        "",
        f"- By status: {format_counter(status)}",
        f"- By issue type: {format_counter(types)}",
        f"- By priority: {format_counter(priorities)}",
        f"- By assignee: {format_counter(assignees)}",
        f"- Unassigned: {assignees.get('Unassigned', 0)}",
        f"- Oldest tickets: {', '.join(issue['key'] for issue in oldest)}",
        f"- Least recently updated: {', '.join(issue['key'] for issue in stale)}",
        "",
    ]


def risks_and_next_actions(issues: list[dict[str, Any]]) -> list[str]:
    risk_lines = issue_risks(issues)
    action_lines = next_actions(issues)
    return [
        "## Risks and Blockers",
        "",
        *(risk_lines or ["- No obvious risks inferred from fetched fields."]),
        "",
        "## Recommended Next Actions",
        "",
        *action_lines,
        "",
    ]


def issue_risks(issues: list[dict[str, Any]]) -> list[str]:
    today = datetime.now(timezone.utc).date()
    risks: list[str] = []
    stale = []
    overdue = []
    high_priority = []
    blocked = []
    unassigned = []

    for issue in issues:
        key = issue.get("key") or "Unknown"
        status = str(issue.get("status") or "")
        status_category = str(issue.get("status_category") or "")
        priority = str(issue.get("priority") or "")
        labels = {str(label).lower() for label in issue.get("labels") or []}

        if issue.get("assignee") == "Unassigned":
            unassigned.append(key)
        if priority.lower() in {"highest", "high", "critical", "blocker"}:
            high_priority.append(f"{key} ({priority})")
        if "blocked" in status.lower() or "blocker" in labels or "blocked" in labels:
            blocked.append(key)

        due_date = parse_date(issue.get("due_date"))
        if due_date and due_date < today and status_category.lower() != "done":
            overdue.append(f"{key} (due {issue.get('due_date')})")

        updated = parse_date(issue.get("updated"))
        if updated and (today - updated).days >= 14 and status_category.lower() != "done":
            stale.append(f"{key} ({(today - updated).days} days since update)")

    if blocked:
        risks.append(f"- Explicitly blocked: {', '.join(blocked[:10])}{truncated_count(blocked, 10)}")
    if overdue:
        risks.append(f"- Past due and not done: {', '.join(overdue[:10])}{truncated_count(overdue, 10)}")
    if stale:
        risks.append(f"- Stale active tickets: {', '.join(stale[:10])}{truncated_count(stale, 10)}")
    if high_priority:
        risks.append(f"- High-priority work in scope: {', '.join(high_priority[:10])}{truncated_count(high_priority, 10)}")
    if unassigned:
        risks.append(f"- Unassigned tickets: {', '.join(unassigned[:10])}{truncated_count(unassigned, 10)}")
    return risks


def next_actions(issues: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    has_unassigned = any(issue.get("assignee") == "Unassigned" for issue in issues)
    has_blocked = any("blocked" in str(issue.get("status") or "").lower() for issue in issues)
    has_open_due = any(parse_date(issue.get("due_date")) and str(issue.get("status_category") or "").lower() != "done" for issue in issues)
    has_comments = any(issue.get("comments") for issue in issues)
    has_changelog = any(issue.get("changelog") for issue in issues)

    if has_blocked:
        actions.append("- Review blocked tickets first and confirm the external dependency or owner.")
    if has_unassigned:
        actions.append("- Assign owners for unassigned tickets before using this report for delivery planning.")
    if has_open_due:
        actions.append("- Check due dates against current delivery commitments and update dates that are no longer realistic.")
    if not has_comments:
        actions.append("- Re-run with `--comments recent` when discussion context is needed for prioritization.")
    if not has_changelog:
        actions.append("- Re-run with `--changelog` when status aging or transition history matters.")
    actions.append("- Use the JSON data file for deeper slicing by assignee, status, component, or priority.")
    return actions


def parse_date(value: Any) -> Any:
    if not value:
        return None
    text = str(value)
    try:
        if len(text) == 10:
            return datetime.fromisoformat(text).date()
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def truncated_count(values: list[str], limit: int) -> str:
    extra = len(values) - limit
    return f" and {extra} more" if extra > 0 else ""


def format_counter(counter: Counter[str]) -> str:
    return ", ".join(f"{name}={count}" for name, count in counter.most_common()) or "None"


def issue_markdown(issue: dict[str, Any]) -> list[str]:
    description = summarize_text(issue.get("description") or "", 700)
    comments_line = "not fetched"
    if issue.get("comments_mode") != "none":
        comments_line = f"{len(issue.get('comments') or [])} fetched"

    lines = [
        f"## {issue['key']}: {issue.get('summary') or ''}",
        "",
        f"- URL: {issue.get('url')}",
        f"- Type: {issue.get('issue_type') or 'Unknown'}",
        f"- Status: {issue.get('status') or 'Unknown'}",
        f"- Priority: {issue.get('priority') or 'Unknown'}",
        f"- Assignee: {issue.get('assignee') or 'Unassigned'}",
        f"- Reporter: {issue.get('reporter') or 'Unknown'}",
        f"- Creator: {issue.get('creator') or 'Unknown'}",
        f"- Project: {project_label(issue)}",
        f"- Parent/Epic: {parent_label(issue)}",
        f"- Created: {issue.get('created') or 'Unknown'}",
        f"- Updated: {issue.get('updated') or 'Unknown'}",
        f"- Due: {issue.get('due_date') or 'None'}",
        f"- Resolution date: {issue.get('resolution_date') or 'None'}",
        f"- Labels: {', '.join(issue.get('labels') or []) or 'None'}",
        f"- Components: {', '.join(issue.get('components') or []) or 'None'}",
        f"- Fix versions: {', '.join(issue.get('fix_versions') or []) or 'None'}",
        f"- Comments: {comments_line}",
        f"- Attachments: {attachment_summary(issue.get('attachments') or [])}",
        "",
        "### Description Summary",
        "",
        description or "No description.",
        "",
    ]

    if issue.get("acceptance_criteria"):
        lines.extend(["### Acceptance Criteria", "", summarize_text(issue["acceptance_criteria"], 700), ""])
    if issue.get("subtasks"):
        lines.extend(["### Subtasks", ""])
        lines.extend(f"- {item['key']}: {item.get('summary') or ''} [{item.get('status') or 'Unknown'}]" for item in issue["subtasks"])
        lines.append("")
    if issue.get("linked_issues"):
        lines.extend(["### Linked Issues", ""])
        lines.extend(f"- {item['key']}: {item.get('summary') or ''} [{item.get('type') or 'link'}]" for item in issue["linked_issues"])
        lines.append("")
    if issue.get("attachments"):
        lines.extend(["### Attachments", ""])
        lines.extend(attachment_line(item) for item in issue["attachments"])
        lines.append("")
    if issue.get("comments"):
        lines.extend(["### Comments", ""])
        for comment in issue["comments"]:
            body = summarize_text(comment.get("body") or "", 300)
            lines.append(f"- {comment.get('created')}: {comment.get('author')} - {body}")
        lines.append("")
    if issue.get("changelog"):
        lines.extend(["### Changelog", ""])
        for event in issue["changelog"][:30]:
            changes = "; ".join(f"{item['field']}: {item.get('from') or 'None'} -> {item.get('to') or 'None'}" for item in event["items"])
            lines.append(f"- {event.get('created')}: {event.get('author')} - {changes}")
        if len(issue["changelog"]) > 30:
            lines.append(f"- Additional changelog events in JSON: {len(issue['changelog']) - 30}")
        lines.append("")
    return lines


def project_label(issue: dict[str, Any]) -> str:
    key = issue.get("project") or "Unknown"
    name = issue.get("project_name")
    return f"{key} ({name})" if name and name != key else key


def parent_label(issue: dict[str, Any]) -> str:
    key = issue.get("parent_key")
    if not key:
        return "None"
    summary = issue.get("parent_summary")
    return f"{key}: {summary}" if summary else key


def attachment_summary(attachments: list[dict[str, Any]]) -> str:
    count = len(attachments)
    if count == 0:
        return "0"
    total_size = sum(int(item.get("size") or 0) for item in attachments)
    return f"{count} ({format_bytes(total_size)})"


def attachment_line(item: dict[str, Any]) -> str:
    details = [
        item.get("filename") or "unnamed file",
        format_bytes(int(item.get("size") or 0)),
        item.get("mime_type") or "unknown type",
        f"created {item.get('created')}" if item.get("created") else "",
        f"by {item.get('author')}" if item.get("author") else "",
    ]
    return "- " + " | ".join(part for part in details if part)


def format_bytes(size: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024


def summarize_text(value: str, width: int) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= width:
        return value
    return textwrap.shorten(value, width=width, placeholder="...")


def output_paths(args: argparse.Namespace, issues: list[dict[str, Any]]) -> tuple[Path, Path]:
    output = Path(args.output).expanduser() if args.output else None
    output_dir = Path(args.output_dir).expanduser() if args.output_dir else Path.home() / "jira-reports"

    if output:
        if output.suffix.lower() == ".md":
            md_path = output
            json_path = output.with_name(output.stem + "-data.json")
        elif output.suffix.lower() == ".json":
            json_path = output
            md_path = output.with_name(output.stem.removesuffix("-data") + ".md")
        else:
            output_dir = output
            md_path, json_path = default_paths(output_dir, issues)
    else:
        md_path, json_path = default_paths(output_dir, issues)
    return md_path, json_path


def default_paths(output_dir: Path, issues: list[dict[str, Any]]) -> tuple[Path, Path]:
    if len(issues) == 1:
        stem = f"{issues[0]['key']}-report"
    else:
        stem = "jira-report-" + datetime.now().strftime("%Y-%m-%d-%H%M%S")
    return output_dir / f"{stem}.md", output_dir / f"{stem.removesuffix('-report')}-data.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=os.environ.get("JIRA_ENV_FILE", DEFAULT_ENV_FILE))
    parser.add_argument("--keys", nargs="+", help="Exact Jira issue keys to fetch.")
    parser.add_argument("--jql", help="Jira JQL to search.")
    parser.add_argument("--project", help="Project key used with assignee or unassigned filters.")
    parser.add_argument("--assignee", help="Jira account ID, email, or display name.")
    parser.add_argument("--unassigned", action="store_true", help="Filter to unassigned tickets.")
    parser.add_argument("--comments", choices=["none", "recent", "all", "summarize"], default="none")
    parser.add_argument("--recent-comment-count", type=int, default=10)
    parser.add_argument("--changelog", action="store_true")
    parser.add_argument("--max-results", type=int, default=100)
    parser.add_argument("--output-dir")
    parser.add_argument("--output", help="Markdown path, JSON path, or output directory.")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    search_filters = [args.jql, args.project, args.assignee, args.unassigned]
    if args.keys and any(search_filters):
        raise SystemExit("Use either --keys or search filters/JQL, not both.")
    if args.assignee and args.unassigned:
        raise SystemExit("Use either --assignee or --unassigned, not both.")
    if args.recent_comment_count < 1:
        raise SystemExit("--recent-comment-count must be at least 1.")
    if args.max_results < 1:
        raise SystemExit("--max-results must be at least 1.")


def main() -> int:
    args = parse_args()
    validate_args(args)
    load_env_file(expand_path(args.env_file))
    base_url = env("JIRA_BASE_URL")
    client = JiraClient(base_url, auth_header())

    expand = "changelog" if args.changelog else None
    source: str
    raw_issues: list[dict[str, Any]]
    if args.keys:
        invalid = [key for key in args.keys if not ISSUE_KEY_RE.match(key)]
        if invalid:
            raise SystemExit(f"Invalid Jira issue key(s): {', '.join(invalid)}")
        source = "keys: " + ", ".join(args.keys)
        raw_issues = [client.get_issue(key, expand=expand) for key in args.keys]
    else:
        jql = build_jql(args, client)
        source = f"jql: {jql}"
        raw_issues = client.search(jql, args.max_results)
        if args.changelog:
            raw_issues = [client.get_issue(issue["key"], expand="changelog") for issue in raw_issues]

    normalized = []
    field_names = client.field_names()
    for issue in raw_issues:
        comments = client.comments(issue["key"], args.comments, args.recent_comment_count)
        normalized.append(normalize_issue(issue, base_url, field_names, comments, args.comments))

    data = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": source,
        "options": {
            "comments": args.comments,
            "recent_comment_count": args.recent_comment_count,
            "changelog": args.changelog,
            "max_results": args.max_results,
        },
        "issues": normalized,
    }

    md_path, json_path = output_paths(args, normalized)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(markdown_report(data), encoding="utf-8")

    print(f"Markdown report: {md_path}")
    print(f"JSON data: {json_path}")
    print(f"Fetched issues: {len(normalized)}")
    print(f"Comments: {args.comments if args.comments != 'none' else 'not fetched'}")
    print(f"Changelog: {'fetched' if args.changelog else 'not fetched'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
