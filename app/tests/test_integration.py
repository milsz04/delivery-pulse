import psycopg
import pytest
import responses
from responses import matchers
from fastapi.testclient import TestClient

from pulse import api, ask, config, etl, report
from pulse.github_client import API
from tests.factories import gh_commit, gh_issue, gh_issue_that_is_pr, gh_pr

pytestmark = pytest.mark.integration

REPO = "acme/app"
PULLS, ISSUES, COMMITS = (f"{API}/repos/{REPO}/{p}" for p in ("pulls", "issues", "commits"))


OPEN_QUERY = matchers.query_param_matcher({"state": "open"}, strict_match=False)


def mock_github(rsps, prs, issues, commits, open_prs=(), open_issues=()):
    rsps.get(PULLS, match=[OPEN_QUERY], json=list(open_prs))
    rsps.get(PULLS, json=prs)
    rsps.get(ISSUES, match=[OPEN_QUERY], json=list(open_issues))
    rsps.get(ISSUES, json=issues)
    rsps.get(COMMITS, json=commits)


@pytest.fixture
def loaded(db, monkeypatch):
    monkeypatch.setattr(config, "REPOS", [REPO])
    monkeypatch.setattr(config, "GITHUB_TOKEN", "test")
    with responses.RequestsMock() as rsps:
        mock_github(
            rsps,
            prs=[
                gh_pr(1, created=3, updated=1, merged=1),
                gh_pr(2, created=10, updated=2, login="bob"),
                gh_pr(3, created=5, updated=2, merged=4, login="dependabot[bot]"),
            ],
            issues=[gh_issue(10, assignee="bob"), gh_issue(11, closed=1), gh_issue_that_is_pr(2)],
            commits=[gh_commit("a1"), gh_commit("b2", login="bob")],
            open_prs=[gh_pr(4, created=120, updated=100, login="carol")],
            open_issues=[gh_issue(12, created=200, updated=150)],
        )
        etl.run()
    return db


def test_full_load_and_views(loaded):
    with psycopg.connect(loaded) as conn:
        assert conn.execute("SELECT count(*) FROM pull_requests").fetchone()[0] == 4
        assert conn.execute("SELECT count(*) FROM issues").fetchone()[0] == 3
        assert conn.execute("SELECT count(*) FROM commits").fetchone()[0] == 2
        run = conn.execute("SELECT mode, status, pull_requests FROM etl_runs").fetchone()
        assert run == ("full", "success", 4)

        lead = conn.execute("SELECT lead_time_hours FROM pr_metrics WHERE number = 1").fetchone()[0]
        assert 47 < float(lead) < 49

        open_work = dict(conn.execute("SELECT number, age_bucket FROM open_work").fetchall())
        assert open_work[4] == "5) 90+ days" and open_work[12] == "5) 90+ days"
        assert 3 not in open_work

        workload = {r[0]: r[1:] for r in conn.execute(
            "SELECT person, open_prs, open_issues_assigned, merged_prs_30d, commits_30d FROM workload")}
        assert workload["bob"] == (1, 1, 0, 1)
        assert workload["alice"] == (0, 0, 1, 1)
        assert "dependabot[bot]" not in workload


def test_second_run_is_incremental_and_idempotent(loaded):
    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        mock_github(rsps, prs=[gh_pr(2, created=10, updated=0, merged=0, login="bob")], issues=[], commits=[gh_commit("a1")])
        etl.run()
        assert not any("state=open" in c.request.url for c in rsps.calls)
    with psycopg.connect(loaded) as conn:
        assert conn.execute("SELECT mode FROM etl_runs ORDER BY id DESC LIMIT 1").fetchone()[0] == "incremental"
        assert conn.execute("SELECT count(*) FROM pull_requests").fetchone()[0] == 4
        assert conn.execute("SELECT state FROM pull_requests WHERE number = 2").fetchone()[0] == "closed"


def test_ai_role_is_locked_down_even_without_the_validator(loaded):
    with psycopg.connect(config.AI_DATABASE_URL) as conn:
        assert conn.execute("SELECT count(*) FROM pr_metrics").fetchone()[0] == 4
    for sql in ("SELECT * FROM pull_requests", "DELETE FROM commits", "SELECT * FROM etl_runs"):
        with psycopg.connect(config.AI_DATABASE_URL) as conn, pytest.raises(psycopg.Error):
            conn.execute(sql)
    with psycopg.connect(config.AI_DATABASE_URL) as conn:
        assert conn.execute("SHOW statement_timeout").fetchone()[0] == "5s"


def test_ask_end_to_end_with_fake_llm(loaded, monkeypatch):
    answers = iter([
        "```sql\nSELECT person, open_items_total FROM workload ORDER BY open_items_total DESC, person\n```",
        "Bob has the most open items (2).",
    ])
    monkeypatch.setattr(ask.llm, "complete", lambda *a, **k: next(answers))
    result = ask.ask("Who is the busiest?")
    assert result["rows"][0] == ["bob", 2]
    assert result["answer"].startswith("Bob")


def test_report_is_generated_saved_and_served(loaded, monkeypatch, tmp_path):
    monkeypatch.setattr(report, "REPORTS_DIR", tmp_path)
    monkeypatch.setattr(report.llm, "complete", lambda *a, **k: "**Summary**: 1 PR merged <script>x</script>.")
    monkeypatch.setattr(report.llm, "model_name", lambda: "fake")
    result = report.generate(send=False)

    assert (tmp_path / result["file"].split("/")[-1]).exists()
    latest = TestClient(api.app).get("/api/reports/latest").json()
    assert "1 PR merged" in latest["content"]
    assert "<script>" not in latest["html"] and "<strong>Summary</strong>" in latest["html"]
