from datetime import datetime, timedelta, timezone

from pulse.metrics import is_bot, lead_time_hours, weekly_summary

NOW = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)


def ago(days):
    return NOW - timedelta(days=days) if days is not None else None


def pr(number, *, created, merged=None, repo="acme/app", author="alice", draft=False):
    return {"repo": repo, "number": number, "title": f"PR {number}", "author": author,
            "state": "closed" if merged is not None else "open", "is_draft": draft,
            "created_at": ago(created), "merged_at": ago(merged), "html_url": f"https://x/{number}"}


def issue(number, *, created, closed=None, assignee=None, repo="acme/app"):
    return {"repo": repo, "number": number, "title": f"I {number}", "assignee": assignee,
            "state": "closed" if closed is not None else "open",
            "created_at": ago(created), "closed_at": ago(closed)}


def test_helpers():
    assert is_bot("dependabot[bot]") and not is_bot("alice") and not is_bot(None)
    assert lead_time_hours(pr(1, created=3, merged=1)) == 48
    assert lead_time_hours(pr(2, created=3)) is None


def test_weekly_comparison_and_bots_excluded():
    prs = [
        pr(1, created=3, merged=1),
        pr(2, created=5, merged=1, author="bob"),
        pr(3, created=12, merged=10),
        pr(4, created=2, merged=1, author="renovate[bot]"),
    ]
    s = weekly_summary(prs, [], [], NOW)
    assert s["pull_requests"]["this_week"] == {"opened": 2, "merged": 2, "median_lead_time_hours": 72}
    assert s["pull_requests"]["previous_week"]["merged"] == 1
    assert {c["author"] for c in s["top_contributors_this_week"]} == {"alice", "bob"}


def test_issues_and_commits():
    issues = [issue(1, created=2), issue(2, created=20, closed=3, assignee="bob"), issue(3, created=9, closed=8)]
    commits = [{"repo": "acme/app", "committed_at": ago(d)} for d in (1, 2, 10)]
    s = weekly_summary([], issues, commits, NOW)
    assert s["issues"]["this_week"] == {"opened": 1, "closed": 1}
    assert s["issues"]["previous_week"] == {"opened": 1, "closed": 1}
    assert s["issues"]["open_now"] == 1 and s["issues"]["open_unassigned"] == 1
    assert s["commits_this_week"] == 2


def test_oldest_open_prs_sorted_without_drafts():
    prs = [pr(10, created=5), pr(11, created=40), pr(12, created=60, draft=True), pr(13, created=20, repo="acme/b")]
    s = weekly_summary(prs, [], [], NOW)
    assert [p["number"] for p in s["oldest_open_prs"]] == [11, 13, 10]
    assert s["per_repo"]["acme/b"]["open_prs"] == 1


def test_empty_week_has_no_median():
    s = weekly_summary([pr(1, created=30, merged=29)], [], [], NOW)
    assert s["pull_requests"]["this_week"]["median_lead_time_hours"] is None
