#!/bin/bash
set -e

superset export-dashboards -f /tmp/export.zip

python - <<'EOF'
import pathlib, shutil, zipfile

target = pathlib.Path("/app/dashboards")
for child in target.iterdir():
    shutil.rmtree(child) if child.is_dir() else child.unlink()

with zipfile.ZipFile("/tmp/export.zip") as zf:
    for name in zf.namelist():
        if name.endswith("/"):
            continue
        relative = pathlib.Path(*pathlib.Path(name).parts[1:])
        out = target / relative
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(zf.read(name))
print(f"Exported to {target}")
EOF
