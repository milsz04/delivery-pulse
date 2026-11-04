import os

SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY", "")
if len(SECRET_KEY) < 16:
    raise RuntimeError("Set SUPERSET_SECRET_KEY in .env (see .env.example for how to generate one).")

SQLALCHEMY_DATABASE_URI = "sqlite:////app/superset_home/superset.db"

TALISMAN_ENABLED = False
