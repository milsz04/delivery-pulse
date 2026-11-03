import os
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest

from pulse import config

TABLES = "pull_requests, issues, commits, etl_runs, reports"


def _with_credentials(url: str, user: str) -> str:
    parts = urlsplit(url)
    host = parts.netloc.split("@")[-1]
    return urlunsplit(parts._replace(netloc=f"{user}:{user}@{host}"))


@pytest.fixture
def db(monkeypatch):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set - skipping integration test")
    monkeypatch.setattr(config, "DATABASE_URL", url)
    monkeypatch.setattr(config, "ANALYTICS_DATABASE_URL", _with_credentials(url, "analytics_ro"))
    monkeypatch.setattr(config, "AI_DATABASE_URL", _with_credentials(url, "ai_ro"))
    with psycopg.connect(url) as conn:
        conn.execute(f"TRUNCATE {TABLES} RESTART IDENTITY")
    return url
