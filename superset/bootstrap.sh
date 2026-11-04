#!/bin/bash
set -e

superset db upgrade

superset fab create-admin \
  --username admin --firstname Admin --lastname User --email admin@example.com \
  --password "${SUPERSET_ADMIN_PASSWORD:-admin}" || true

superset init

if [ -f /app/dashboards/metadata.yaml ]; then
  echo "Importing dashboards from /app/dashboards"
  python - <<'EOF'
import os, pathlib, re, shutil

src, dst = pathlib.Path("/app/dashboards"), pathlib.Path("/tmp/import/dashboards")
shutil.rmtree(dst.parent, ignore_errors=True)
shutil.copytree(src, dst)
uri = os.environ["ANALYTICS_DATABASE_URI"]
for f in (dst / "databases").glob("*.yaml"):
    f.write_text(re.sub(r"^sqlalchemy_uri:.*$", f"sqlalchemy_uri: {uri}", f.read_text(), flags=re.M))
shutil.make_archive("/tmp/dashboards", "zip", root_dir=dst.parent, base_dir="dashboards")
EOF
  superset import-dashboards -p /tmp/dashboards.zip -u admin
fi

superset set-database-uri -d "Delivery Pulse" -u "${ANALYTICS_DATABASE_URI}"

exec /app/docker/entrypoints/run-server.sh
