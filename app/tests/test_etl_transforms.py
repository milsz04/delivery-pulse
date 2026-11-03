from pulse.etl import dedupe, transform_commit, transform_issue, transform_pr
from tests.factories import gh_commit, gh_issue, gh_pr


def test_transform_merged_pr():
    row = transform_pr("acme/app", gh_pr(42, created=3, merged=1))
    assert row["repo"] == "acme/app" and row["number"] == 42
    assert row["state"] == "closed"
    assert row["merged_at"] is not None and row["merged_at"] > row["created_at"]


def test_transform_pr_from_deleted_account():
    row = transform_pr("acme/app", gh_pr(1, login=None, draft=True))
    assert row["author"] is None and row["is_draft"] is True


def test_transform_issue_labels_and_assignee():
    row = transform_issue("acme/app", gh_issue(7, assignee="bob", labels=("bug", "ui")))
    assert row["assignee"] == "bob"
    assert row["labels"] == "bug,ui"
    assert row["state"] == "open"


def test_transform_issue_without_labels():
    row = transform_issue("acme/app", gh_issue(8, labels=()))
    assert row["labels"] is None


def test_transform_commit_keeps_first_line_and_handles_unlinked_author():
    row = transform_commit("acme/app", gh_commit("abc123", login=None))
    assert row["message"] == "Fix bug"
    assert row["author_login"] is None and row["author_name"] == "Alice"


def test_dedupe_keeps_last():
    rows = [{"repo": "a", "number": 1, "v": 1}, {"repo": "a", "number": 1, "v": 2}, {"repo": "a", "number": 2, "v": 3}]
    assert sorted(r["v"] for r in dedupe(rows, "repo", "number")) == [2, 3]
