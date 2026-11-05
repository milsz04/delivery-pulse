from __future__ import annotations

import logging
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from pulse import config, etl, report

log = logging.getLogger("pulse.worker")


def etl_job() -> None:
    try:
        etl.run()
    except Exception:
        log.exception("ETL job failed")


def report_job() -> None:
    try:
        etl.run()
        report.generate(send=True)
    except Exception:
        log.exception("Report job failed")


def build_scheduler() -> BlockingScheduler:
    scheduler = BlockingScheduler(timezone=config.TIMEZONE)
    scheduler.add_job(
        etl_job,
        IntervalTrigger(minutes=config.ETL_INTERVAL_MINUTES),
        next_run_time=datetime.now(),
        id="etl", max_instances=1, coalesce=True,
    )
    scheduler.add_job(
        report_job,
        CronTrigger.from_crontab(config.REPORT_CRON, timezone=config.TIMEZONE),
        id="weekly_report", max_instances=1, coalesce=True,
    )
    return scheduler


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    scheduler = build_scheduler()
    log.info(
        "Worker started: ETL every %s min, report at '%s' (%s), repos: %s",
        config.ETL_INTERVAL_MINUTES, config.REPORT_CRON, config.TIMEZONE, config.REPOS,
    )
    scheduler.start()


if __name__ == "__main__":
    main()
