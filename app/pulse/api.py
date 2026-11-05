from __future__ import annotations

import html
import logging
import re
from pathlib import Path

import markdown
import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from pulse import ask as ask_module
from pulse import config, llm
from pulse import report as report_module

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

STATIC = Path(__file__).parent / "static"

app = FastAPI(title="Delivery Pulse AI", version="1.0.0")


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class ReportRequest(BaseModel):
    notify: bool = False


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict:
    try:
        with psycopg.connect(config.ANALYTICS_DATABASE_URL, connect_timeout=3) as conn:
            last_etl = conn.execute(
                "SELECT max(finished_at) FROM etl_runs WHERE status = 'success'"
            ).fetchone()[0]
        db = "ok"
    except psycopg.Error:
        db, last_etl = "unavailable", None
    return {
        "status": "ok",
        "database": db,
        "last_successful_etl": last_etl,
        "llm": f"{config.LLM_PROVIDER}/{config.LLM_MODEL or llm.DEFAULT_MODELS.get(config.LLM_PROVIDER, '?')}",
        "dashboard_url": config.SUPERSET_PUBLIC_URL,
    }


@app.post("/api/ask")
def ask(req: AskRequest) -> dict:
    try:
        return ask_module.ask(req.question)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except llm.LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/reports/latest")
def latest_report() -> dict:
    with psycopg.connect(config.ANALYTICS_DATABASE_URL) as conn:
        row = conn.execute(
            "SELECT period_start, period_end, content, model, created_at FROM reports "
            "ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No report generated yet.")
    keys = ["period_start", "period_end", "content", "model", "created_at"]
    result = dict(zip(keys, row))
    rendered = markdown.markdown(html.escape(result["content"], quote=False))
    result["html"] = re.sub(r'href="(?!https?://)[^"]*"', 'href="#"', rendered)
    return result


@app.post("/api/reports")
def create_report(req: ReportRequest) -> dict:
    try:
        return report_module.generate(send=req.notify)
    except (RuntimeError, llm.LLMError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
