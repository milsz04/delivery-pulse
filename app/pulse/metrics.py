from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from statistics import median
from typing import Any, Iterable

Row = dict[str, Any]


def is_bot(login: str | None) -> bool:
    return bool(login) and login.endswith("[bot]")


def lead_time_hours(pr: Row) -> float | None:
    if pr.get("merged_at") is None:
        return None
    return (pr["merged_at"] - pr["created_at"]).total_seconds() / 3600


def _between(ts: datetime | None, start: datetime, end: datetime) -> bool:
    return ts is not None and start <= ts < end


def _pr_stats(prs: list[Row], start: datetime, end: datetime) -> dict[str, Any]:
    merged = [p for p in prs if _between(p.get("merged_at"), start, end)]
    lead_times = [lead_time_hours(p) for p in merged]
    return {
        "opened": sum(1 for p in prs if _between(p["created_at"], start, end)),
        "merged": len(merged),
        "median_lead_time_hours": round(median(lead_times), 1) if lead_times else None,
    }


def _issue_stats(issues: list[Row], start: datetime, end: datetime) -> dict[str, Any]:
    return {
        "opened": sum(1 for i in issues if _between(i["created_at"], start, end)),
        "closed": sum(1 for i in issues if _between(i.get("closed_at"), start, end)),
    }


def weekly_summary(
    prs: Iterable[Row],
    issues: Iterable[Row],
    commits: Iterable[Row],
    now: datetime,
    top_n: int = 5,
) -> dict[str, Any]:
    prs, issues, commits = list(prs), list(issues), list(commits)
    week_ago, two_weeks_ago = now - timedelta(days=7), now - timedelta(days=14)

    human_prs = [p for p in prs if not is_bot(p.get("author"))]
    open_prs = [p for p in human_prs if p["state"] == "open" and not p.get("is_draft")]
    open_issues = [i for i in issues if i["state"] == "open"]

    per_repo = {}
    for repo in sorted({p["repo"] for p in prs} | {i["repo"] for i in issues}):
        repo_prs = [p for p in human_prs if p["repo"] == repo]
        per_repo[repo] = {
            "pull_requests": _pr_stats(repo_prs, week_ago, now),
            "issues": _issue_stats([i for i in issues if i["repo"] == repo], week_ago, now),
            "open_prs": sum(1 for p in open_prs if p["repo"] == repo),
        }

    merged_by = Counter(
        p["author"] for p in human_prs if _between(p.get("merged_at"), week_ago, now) and p.get("author")
    )

    return {
        "period_start": week_ago.date().isoformat(),
        "period_end": now.date().isoformat(),
        "pull_requests": {
            "this_week": _pr_stats(human_prs, week_ago, now),
            "previous_week": _pr_stats(human_prs, two_weeks_ago, week_ago),
            "open_now": len(open_prs),
        },
        "issues": {
            "this_week": _issue_stats(issues, week_ago, now),
            "previous_week": _issue_stats(issues, two_weeks_ago, week_ago),
            "open_now": len(open_issues),
            "open_unassigned": sum(1 for i in open_issues if not i.get("assignee")),
        },
        "commits_this_week": sum(1 for c in commits if _between(c["committed_at"], week_ago, now)),
        "per_repo": per_repo,
        "top_contributors_this_week": [
            {"author": author, "merged_prs": count} for author, count in merged_by.most_common(top_n)
        ],
        "oldest_open_prs": [
            {
                "repo": p["repo"],
                "number": p["number"],
                "title": p["title"],
                "author": p.get("author"),
                "age_days": (now - p["created_at"]).days,
                "url": p.get("html_url"),
            }
            for p in sorted(open_prs, key=lambda p: p["created_at"])[:top_n]
        ],
    }
