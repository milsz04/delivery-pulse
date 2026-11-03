from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _int(name: str, default: int) -> int:
    value = _get(name)
    return int(value) if value else default


GITHUB_TOKEN = _get("GITHUB_TOKEN") or None
REPOS = [r.strip() for r in _get("REPOS", "apache/superset,fastapi/fastapi").split(",") if r.strip()]
DAYS_BACK = _int("DAYS_BACK", 90)
ETL_INTERVAL_MINUTES = _int("ETL_INTERVAL_MINUTES", 60)

DATABASE_URL = _get("DATABASE_URL", "postgresql://pulse:pulse@localhost:5433/pulse")
ANALYTICS_DATABASE_URL = _get(
    "ANALYTICS_DATABASE_URL", "postgresql://analytics_ro:analytics_ro@localhost:5433/pulse"
)
AI_DATABASE_URL = _get("AI_DATABASE_URL", "postgresql://ai_ro:ai_ro@localhost:5433/pulse")

LLM_PROVIDER = _get("LLM_PROVIDER", "anthropic").lower()
LLM_MODEL = _get("LLM_MODEL")
ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY") or None
OLLAMA_URL = _get("OLLAMA_URL", "http://localhost:11434")
REPORT_LANGUAGE = _get("REPORT_LANGUAGE", "English")

TIMEZONE = _get("TZ", "Europe/Warsaw")
REPORT_CRON = _get("REPORT_CRON", "0 8 * * mon")

DISCORD_WEBHOOK_URL = _get("DISCORD_WEBHOOK_URL") or None
SLACK_WEBHOOK_URL = _get("SLACK_WEBHOOK_URL") or None
SMTP_HOST = _get("SMTP_HOST") or None
SMTP_PORT = _int("SMTP_PORT", 587)
SMTP_USER = _get("SMTP_USER") or None
SMTP_PASSWORD = _get("SMTP_PASSWORD") or None
EMAIL_FROM = _get("EMAIL_FROM") or SMTP_USER
EMAIL_TO = [a.strip() for a in _get("EMAIL_TO").split(",") if a.strip()]

REPORTS_DIR = _get("REPORTS_DIR", str(Path(__file__).resolve().parents[2] / "reports"))

SUPERSET_PUBLIC_URL = _get("SUPERSET_PUBLIC_URL", "http://localhost:8088/superset/dashboard/delivery-pulse/")
