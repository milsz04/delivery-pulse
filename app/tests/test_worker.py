from pulse import worker


def test_scheduler_has_etl_and_weekly_report_jobs():
    scheduler = worker.build_scheduler()
    jobs = {job.id: job for job in scheduler.get_jobs()}
    assert set(jobs) == {"etl", "weekly_report"}
    assert "mon" in str(jobs["weekly_report"].trigger)


def test_jobs_never_crash_the_scheduler(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("GitHub down")

    monkeypatch.setattr(worker.etl, "run", boom)
    worker.etl_job()
    worker.report_job()
