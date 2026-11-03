from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg

from pulse import config
from pulse.github_client import GitHubClient, RateLimitError, parse_ts

log = logging.getLogger(__name__)

INCREMENTAL_OVERLAP = timedelta(hours=1)


def transform_pr(repo: str, raw: dict[str, Any]) -> dict[str, Any]:
    user = raw.get("user") or {}
    return {
        "repo": repo,
        "number": raw["number"],
        "title": raw.get("title") or "",
        "author": user.get("login"),
        "state": raw["state"],
        "is_draft": bool(raw.get("draft", False)),
        "created_at": parse_ts(raw["created_at"]),
        "updated_at": parse_ts(raw["updated_at"]),
        "closed_at": parse_ts(raw.get("closed_at")),
        "merged_at": parse_ts(raw.get("merged_at")),
        "html_url": raw.get("html_url"),
    }


def transform_issue(repo: str, raw: dict[str, Any]) -> dict[str, Any]:
    user = raw.get("user") or {}
    assignee = raw.get("assignee") or {}
    labels = [label["name"] for label in raw.get("labels") or [] if isinstance(label, dict)]
    return {
        "repo": repo,
        "number": raw["number"],
        "title": raw.get("title") or "",
        "author": user.get("login"),
        "assignee": assignee.get("login"),
        "state": raw["state"],
        "state_reason": raw.get("state_reason"),
        "labels": ",".join(labels) or None,
        "comments": raw.get("comments") or 0,
        "created_at": parse_ts(raw["created_at"]),
        "updated_at": parse_ts(raw["updated_at"]),
        "closed_at": parse_ts(raw.get("closed_at")),
        "html_url": raw.get("html_url"),
    }


def transform_commit(repo: str, raw: dict[str, Any]) -> dict[str, Any]:
    commit = raw.get("commit") or {}
    git_author = commit.get("author") or {}
    gh_author = raw.get("author") or {}
    message = (commit.get("message") or "").splitlines()
    return {
        "repo": repo,
        "sha": raw["sha"],
        "author_login": gh_author.get("login"),
        "author_name": git_author.get("name"),
        "committed_at": parse_ts(git_author.get("date")),
        "message": message[0][:500] if message else "",
        "html_url": raw.get("html_url"),
    }


def dedupe(rows: list[dict[str, Any]], *key: str) -> list[dict[str, Any]]:
    return list({tuple(r[k] for k in key): r for r in rows}.values())


UPSERT_PR = """
INSERT INTO pull_requests (repo, number, title, author, state, is_draft, created_at, updated_at,
                           closed_at, merged_at, html_url, fetched_at)
VALUES (%(repo)s, %(number)s, %(title)s, %(author)s, %(state)s, %(is_draft)s, %(created_at)s,
        %(updated_at)s, %(closed_at)s, %(merged_at)s, %(html_url)s, now())
ON CONFLICT (repo, number) DO UPDATE SET
    title = EXCLUDED.title, author = EXCLUDED.author, state = EXCLUDED.state,
    is_draft = EXCLUDED.is_draft, updated_at = EXCLUDED.updated_at, closed_at = EXCLUDED.closed_at,
    merged_at = EXCLUDED.merged_at, html_url = EXCLUDED.html_url, fetched_at = now()
"""

UPSERT_ISSUE = """
INSERT INTO issues (repo, number, title, author, assignee, state, state_reason, labels, comments,
                    created_at, updated_at, closed_at, html_url, fetched_at)
VALUES (%(repo)s, %(number)s, %(title)s, %(author)s, %(assignee)s, %(state)s, %(state_reason)s,
        %(labels)s, %(comments)s, %(created_at)s, %(updated_at)s, %(closed_at)s, %(html_url)s, now())
ON CONFLICT (repo, number) DO UPDATE SET
    title = EXCLUDED.title, assignee = EXCLUDED.assignee, state = EXCLUDED.state,
    state_reason = EXCLUDED.state_reason, labels = EXCLUDED.labels, comments = EXCLUDED.comments,
    updated_at = EXCLUDED.updated_at, closed_at = EXCLUDED.closed_at, fetched_at = now()
"""

UPSERT_COMMIT = """
INSERT INTO commits (repo, sha, author_login, author_name, committed_at, message, html_url, fetched_at)
VALUES (%(repo)s, %(sha)s, %(author_login)s, %(author_name)s, %(committed_at)s, %(message)s,
        %(html_url)s, now())
ON CONFLICT (repo, sha) DO NOTHING
"""


def upsert(conn: psycopg.Connection, sql: str, rows: list[dict[str, Any]]) -> None:
    if rows:
        with conn.cursor() as cur:
            cur.executemany(sql, rows)


def last_successful_run(conn: psycopg.Connection) -> datetime | None:
    row = conn.execute("SELECT max(started_at) FROM etl_runs WHERE status = 'success'").fetchone()
    return row[0] if row else None


def load_repo(gh: GitHubClient, repo: str, since: datetime, full: bool) -> dict[str, list[dict]]:
    prs = [transform_pr(repo, r) for r in gh.pulls(repo, "all", updated_since=since)]
    issues = [transform_issue(repo, r) for r in gh.issues(repo, "all", since=since)]
    if full:
        prs += [transform_pr(repo, r) for r in gh.pulls(repo, "open")]
        issues += [transform_issue(repo, r) for r in gh.issues(repo, "open")]
    commits = [transform_commit(repo, r) for r in gh.commits(repo, since)]
    return {
        "pull_requests": dedupe(prs, "repo", "number"),
        "issues": dedupe(issues, "repo", "number"),
        "commits": dedupe(commits, "repo", "sha"),
    }


def run(full: bool = False, days: int | None = None) -> dict[str, int]:
    now = datetime.now(timezone.utc)
    gh = GitHubClient(config.GITHUB_TOKEN)
    if not config.GITHUB_TOKEN:
        log.warning("No GITHUB_TOKEN set - anonymous limit is 60 requests/hour, a full load may fail.")

    with psycopg.connect(config.DATABASE_URL) as conn:
        last = last_successful_run(conn)
        if full or last is None:
            mode, since = "full", now - timedelta(days=days or config.DAYS_BACK)
        else:
            mode, since = "incremental", last - INCREMENTAL_OVERLAP

        run_id = conn.execute(
            "INSERT INTO etl_runs (mode) VALUES (%s) RETURNING id", (mode,)
        ).fetchone()[0]
        conn.commit()
        log.info("ETL run %s (%s) since %s for %s", run_id, mode, since.isoformat(), config.REPOS)

        totals = {"pull_requests": 0, "issues": 0, "commits": 0}
        try:
            for repo in config.REPOS:
                data = load_repo(gh, repo, since, full=(mode == "full"))
                upsert(conn, UPSERT_PR, data["pull_requests"])
                upsert(conn, UPSERT_ISSUE, data["issues"])
                upsert(conn, UPSERT_COMMIT, data["commits"])
                conn.commit()
                for key in totals:
                    totals[key] += len(data[key])
                log.info(
                    "  %s: %d PRs, %d issues, %d commits",
                    repo, len(data["pull_requests"]), len(data["issues"]), len(data["commits"]),
                )
        except Exception as exc:
            conn.rollback()
            conn.execute(
                "UPDATE etl_runs SET status = 'failed', finished_at = now(), error = %s WHERE id = %s",
                (str(exc)[:2000], run_id),
            )
            conn.commit()
            raise

        conn.execute(
            """UPDATE etl_runs SET status = 'success', finished_at = now(),
                   pull_requests = %s, issues = %s, commits = %s WHERE id = %s""",
            (totals["pull_requests"], totals["issues"], totals["commits"], run_id),
        )
        conn.commit()

    log.info("ETL done: %s (%d GitHub API requests)", totals, gh.requests_made)
    return totals


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--full", action="store_true", help="force a full load")
    parser.add_argument("--days", type=int, help="override DAYS_BACK for a full load")
    args = parser.parse_args()
    try:
        run(full=args.full, days=args.days)
    except RateLimitError as exc:
        log.error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
