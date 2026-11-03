from datetime import datetime, timedelta, timezone


def iso(days_ago: float | None, now: datetime | None = None) -> str | None:
    if days_ago is None:
        return None
    now = now or datetime.now(timezone.utc)
    return (now - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def gh_pr(number, *, created=10, updated=1, merged=None, closed=None, state=None, draft=False, login="alice"):
    if merged is not None and closed is None:
        closed = merged
    return {
        "number": number,
        "title": f"PR {number}",
        "user": {"login": login} if login else None,
        "state": state or ("closed" if closed is not None else "open"),
        "draft": draft,
        "created_at": iso(created),
        "updated_at": iso(updated),
        "closed_at": iso(closed),
        "merged_at": iso(merged),
        "html_url": f"https://github.com/acme/app/pull/{number}",
    }


def gh_issue(number, *, created=20, updated=1, closed=None, assignee=None, reason=None, labels=("bug",)):
    return {
        "number": number,
        "title": f"Issue {number}",
        "user": {"login": "reporter"},
        "assignee": {"login": assignee} if assignee else None,
        "state": "closed" if closed is not None else "open",
        "state_reason": reason or ("completed" if closed is not None else None),
        "labels": [{"name": label} for label in labels],
        "comments": 3,
        "created_at": iso(created),
        "updated_at": iso(updated),
        "closed_at": iso(closed),
        "html_url": f"https://github.com/acme/app/issues/{number}",
    }


def gh_issue_that_is_pr(number):
    item = gh_issue(number)
    item["pull_request"] = {"url": "https://api.github.com/repos/acme/app/pulls/1"}
    return item


def gh_commit(sha, *, days_ago=2, login="alice", name="Alice", message="Fix bug\n\nLonger body"):
    return {
        "sha": sha,
        "html_url": f"https://github.com/acme/app/commit/{sha}",
        "commit": {"author": {"name": name, "date": iso(days_ago)}, "message": message},
        "author": {"login": login} if login else None,
    }
