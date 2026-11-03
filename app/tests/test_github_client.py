from datetime import datetime, timedelta, timezone

import pytest
import responses

from pulse.github_client import API, GitHubClient, RateLimitError
from tests.factories import gh_issue, gh_issue_that_is_pr, gh_pr

PULLS = f"{API}/repos/acme/app/pulls"


@responses.activate
def test_paginate_follows_link_header():
    responses.get(PULLS, json=[gh_pr(1), gh_pr(2)], headers={"Link": f'<{PULLS}?page=2>; rel="next"'})
    responses.get(f"{PULLS}?page=2", json=[gh_pr(3)])
    numbers = [pr["number"] for pr in GitHubClient().pulls("acme/app", "all")]
    assert numbers == [1, 2, 3]


@responses.activate
def test_pulls_stop_at_updated_since():
    responses.get(PULLS, json=[gh_pr(1, updated=1), gh_pr(2, updated=5), gh_pr(3, updated=40)],
                  headers={"Link": f'<{PULLS}?page=2>; rel="next"'})
    since = datetime.now(timezone.utc) - timedelta(days=30)
    numbers = [pr["number"] for pr in GitHubClient().pulls("acme/app", "all", updated_since=since)]
    assert numbers == [1, 2]
    assert len(responses.calls) == 1


@responses.activate
def test_issues_skip_pull_requests_and_send_since():
    responses.get(f"{API}/repos/acme/app/issues", json=[gh_issue(10), gh_issue_that_is_pr(11)])
    since = datetime(2026, 10, 1, tzinfo=timezone.utc)
    items = list(GitHubClient().issues("acme/app", "all", since=since))
    assert [i["number"] for i in items] == [10]
    assert "since=2026-10-01T00%3A00%3A00Z" in responses.calls[0].request.url


@responses.activate
def test_rate_limit_raises_clear_error():
    responses.get(PULLS, status=403, headers={"X-RateLimit-Remaining": "0"}, json={"message": "rate limit"})
    with pytest.raises(RateLimitError, match="GITHUB_TOKEN"):
        list(GitHubClient().pulls("acme/app", "all"))


@responses.activate
def test_token_is_sent_as_bearer():
    responses.get(PULLS, json=[])
    list(GitHubClient(token="abc").pulls("acme/app", "all"))
    assert responses.calls[0].request.headers["Authorization"] == "Bearer abc"
