from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Iterator

import requests

log = logging.getLogger(__name__)

API = "https://api.github.com"
PAGE_SIZE = 100


class RateLimitError(RuntimeError):
    pass


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class GitHubClient:
    def __init__(self, token: str | None = None, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "delivery-pulse",
            }
        )
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"
        self.requests_made = 0

    def _get(self, url: str, params: dict[str, Any] | None = None) -> requests.Response:
        for attempt in range(3):
            resp = self.session.get(url, params=params, timeout=30)
            self.requests_made += 1
            if resp.status_code in (403, 429):
                if resp.headers.get("X-RateLimit-Remaining") == "0":
                    raise RateLimitError(
                        "GitHub API rate limit reached. Set GITHUB_TOKEN in .env "
                        "(5000 requests/hour instead of 60) or wait for the reset."
                    )
                retry_after = int(resp.headers.get("Retry-After", "0") or 0)
                if retry_after and attempt < 2:
                    log.warning("Secondary rate limit, sleeping %ss", retry_after)
                    time.sleep(min(retry_after, 60))
                    continue
            resp.raise_for_status()
            return resp
        resp.raise_for_status()
        return resp

    def paginate(self, path: str, params: dict[str, Any]) -> Iterator[dict[str, Any]]:
        url: str | None = f"{API}{path}"
        query: dict[str, Any] | None = {**params, "per_page": PAGE_SIZE}
        while url:
            resp = self._get(url, query)
            yield from resp.json()
            url = resp.links.get("next", {}).get("url")
            query = None

    def pulls(self, repo: str, state: str, updated_since: datetime | None = None) -> Iterator[dict]:
        params = {"state": state, "sort": "updated", "direction": "desc"}
        for pr in self.paginate(f"/repos/{repo}/pulls", params):
            if updated_since and parse_ts(pr["updated_at"]) < updated_since:
                return
            yield pr

    def issues(self, repo: str, state: str, since: datetime | None = None) -> Iterator[dict]:
        params: dict[str, Any] = {"state": state, "sort": "updated", "direction": "desc"}
        if since:
            params["since"] = since.strftime("%Y-%m-%dT%H:%M:%SZ")
        for item in self.paginate(f"/repos/{repo}/issues", params):
            if "pull_request" not in item:
                yield item

    def commits(self, repo: str, since: datetime) -> Iterator[dict]:
        params = {"since": since.strftime("%Y-%m-%dT%H:%M:%SZ")}
        yield from self.paginate(f"/repos/{repo}/commits", params)
