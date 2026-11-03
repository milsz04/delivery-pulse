CREATE TABLE pull_requests (
    repo        TEXT        NOT NULL,
    number      INTEGER     NOT NULL,
    title       TEXT        NOT NULL,
    author      TEXT,
    state       TEXT        NOT NULL,
    is_draft    BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL,
    closed_at   TIMESTAMPTZ,
    merged_at   TIMESTAMPTZ,
    html_url    TEXT,
    fetched_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (repo, number)
);

CREATE TABLE issues (
    repo          TEXT        NOT NULL,
    number        INTEGER     NOT NULL,
    title         TEXT        NOT NULL,
    author        TEXT,
    assignee      TEXT,
    state         TEXT        NOT NULL,
    state_reason  TEXT,
    labels        TEXT,
    comments      INTEGER     NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL,
    closed_at     TIMESTAMPTZ,
    html_url      TEXT,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (repo, number)
);

CREATE TABLE commits (
    repo          TEXT        NOT NULL,
    sha           TEXT        NOT NULL,
    author_login  TEXT,
    author_name   TEXT,
    committed_at  TIMESTAMPTZ NOT NULL,
    message       TEXT,
    html_url      TEXT,
    fetched_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (repo, sha)
);

CREATE INDEX ON pull_requests (merged_at);
CREATE INDEX ON issues (state);
CREATE INDEX ON commits (committed_at);

CREATE TABLE etl_runs (
    id           BIGSERIAL PRIMARY KEY,
    mode         TEXT        NOT NULL,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ,
    status       TEXT        NOT NULL DEFAULT 'running',
    pull_requests INTEGER,
    issues       INTEGER,
    commits      INTEGER,
    error        TEXT
);

CREATE TABLE reports (
    id            BIGSERIAL PRIMARY KEY,
    period_start  DATE        NOT NULL,
    period_end    DATE        NOT NULL,
    content       TEXT        NOT NULL,
    model         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE VIEW pr_metrics AS
SELECT
    repo, number, title, author,
    (author LIKE '%[bot]') AS is_bot,
    state, is_draft, created_at, updated_at, closed_at, merged_at, html_url,
    CASE
        WHEN merged_at IS NOT NULL THEN 'merged'
        WHEN state = 'closed'      THEN 'closed_unmerged'
        ELSE 'open'
    END AS status,
    EXTRACT(EPOCH FROM (merged_at - created_at)) / 3600.0 AS lead_time_hours,
    CASE WHEN state = 'open'
         THEN EXTRACT(EPOCH FROM (now() - created_at)) / 86400.0 END AS open_age_days
FROM pull_requests;

CREATE VIEW issue_metrics AS
SELECT
    repo, number, title, author, assignee, labels, comments,
    state, state_reason, created_at, updated_at, closed_at, html_url,
    CASE
        WHEN state = 'open'                THEN 'open'
        WHEN state_reason = 'not_planned'  THEN 'not_planned'
        ELSE 'completed'
    END AS status,
    EXTRACT(EPOCH FROM (closed_at - created_at)) / 3600.0 AS resolution_time_hours,
    CASE WHEN state = 'open'
         THEN EXTRACT(EPOCH FROM (now() - created_at)) / 86400.0 END AS open_age_days
FROM issues;

CREATE VIEW open_work AS
WITH items AS (
    SELECT 'pull_request' AS item_type, repo, number, title,
           author AS owner, created_at, html_url
    FROM pull_requests
    WHERE state = 'open' AND NOT is_draft AND author NOT LIKE '%[bot]'
    UNION ALL
    SELECT 'issue', repo, number, title,
           COALESCE(assignee, 'unassigned'), created_at, html_url
    FROM issues
    WHERE state = 'open'
)
SELECT
    item_type, repo, number, title, owner, created_at, html_url,
    ROUND((EXTRACT(EPOCH FROM (now() - created_at)) / 86400.0)::numeric, 1) AS age_days,
    CASE
        WHEN now() - created_at < INTERVAL '3 days'  THEN '1) 0-2 days'
        WHEN now() - created_at < INTERVAL '8 days'  THEN '2) 3-7 days'
        WHEN now() - created_at < INTERVAL '31 days' THEN '3) 8-30 days'
        WHEN now() - created_at < INTERVAL '91 days' THEN '4) 31-90 days'
        ELSE '5) 90+ days'
    END AS age_bucket
FROM items;

CREATE VIEW workload AS
WITH open_counts AS (
    SELECT owner AS person,
           COUNT(*) FILTER (WHERE item_type = 'pull_request') AS open_prs,
           COUNT(*) FILTER (WHERE item_type = 'issue')        AS open_issues_assigned
    FROM open_work
    WHERE owner <> 'unassigned'
    GROUP BY owner
),
merged AS (
    SELECT author AS person, COUNT(*) AS merged_prs_30d
    FROM pull_requests
    WHERE merged_at > now() - INTERVAL '30 days'
    GROUP BY author
),
recent_commits AS (
    SELECT author_login AS person, COUNT(*) AS commits_30d
    FROM commits
    WHERE committed_at > now() - INTERVAL '30 days' AND author_login IS NOT NULL
    GROUP BY author_login
)
SELECT
    person,
    COALESCE(o.open_prs, 0)              AS open_prs,
    COALESCE(o.open_issues_assigned, 0)  AS open_issues_assigned,
    COALESCE(o.open_prs, 0) + COALESCE(o.open_issues_assigned, 0) AS open_items_total,
    COALESCE(m.merged_prs_30d, 0)        AS merged_prs_30d,
    COALESCE(c.commits_30d, 0)           AS commits_30d
FROM open_counts o
FULL OUTER JOIN merged m USING (person)
FULL OUTER JOIN recent_commits c USING (person)
WHERE person IS NOT NULL AND person NOT LIKE '%[bot]';

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'analytics_ro') THEN
        CREATE ROLE analytics_ro LOGIN PASSWORD 'analytics_ro';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'ai_ro') THEN
        CREATE ROLE ai_ro LOGIN PASSWORD 'ai_ro';
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO analytics_ro, ai_ro', current_database());
END $$;

GRANT USAGE ON SCHEMA public TO analytics_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analytics_ro;

GRANT USAGE ON SCHEMA public TO ai_ro;
GRANT SELECT ON pr_metrics, issue_metrics, open_work, workload, commits TO ai_ro;
ALTER ROLE ai_ro SET default_transaction_read_only = on;
ALTER ROLE ai_ro SET statement_timeout = '5s';
