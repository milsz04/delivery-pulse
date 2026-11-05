import pytest

from pulse.sql_guard import UnsafeSQLError, validate_sql

ALLOWED = [
    "SELECT repo, count(*) FROM pr_metrics GROUP BY repo",
    "select * from open_work order by age_days desc;",
    "WITH x AS (SELECT * FROM workload) SELECT person FROM x",
    "SELECT repo, percentile_cont(0.5) WITHIN GROUP (ORDER BY lead_time_hours) FROM pr_metrics GROUP BY 1",
    "SELECT person FROM workload UNION SELECT author FROM pr_metrics",
    "SELECT * FROM public.issue_metrics WHERE status = 'open'",
]

BLOCKED = [
    ("DELETE FROM pull_requests", "Only SELECT"),
    ("UPDATE pr_metrics SET title = 'x'", "Only SELECT"),
    ("DROP TABLE issues", "Only SELECT"),
    ("SELECT 1; DROP TABLE issues", "one statement"),
    ("SELECT * FROM pull_requests", "not allowed"),
    ("SELECT * FROM etl_runs", "not allowed"),
    ("SELECT * FROM pg_catalog.pg_user", "Schema"),
    ("SELECT * FROM information_schema.tables", "Schema"),
    ("SELECT pg_sleep(10)", "pg_sleep"),
    ("SELECT pg_read_file('/etc/passwd')", "pg_read_file"),
    ("SELECT set_config('statement_timeout', '0', false)", "set_config"),
    ("SELECT * INTO stolen FROM pr_metrics", "INTO"),
    ("SELECT * FROM pr_metrics FOR UPDATE", "LOCK"),
    ("WITH d AS (DELETE FROM issues RETURNING *) SELECT * FROM d", "DELETE"),
    ("COPY pr_metrics TO '/tmp/x'", "Only SELECT"),
    ("", "Empty"),
]


@pytest.mark.parametrize("sql", ALLOWED)
def test_allowed_queries_are_wrapped_with_limit(sql):
    safe = validate_sql(sql, max_rows=50)
    assert safe.startswith("SELECT * FROM (") and safe.endswith("LIMIT 50")


@pytest.mark.parametrize("sql,message", BLOCKED)
def test_dangerous_queries_are_blocked(sql, message):
    with pytest.raises(UnsafeSQLError, match=message):
        validate_sql(sql)
