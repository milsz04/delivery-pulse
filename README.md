# Delivery Pulse

Delivery analytics for engineering teams: GitHub API → PostgreSQL → dashboards and AI reports.

**Status** Wip
- Apache Superset dashboard kept as code (YAML in `superset/dashboards/`), imported
  automatically on start: throughput, lead time, work in progress by age, workload, oldest open work

![Dashboard](docs/dashboard.png)

docker compose up -d --build   # dashboard: http://localhost:8088 (admin / admin)
