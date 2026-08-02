"""Daily scheduling. Reads the weekly plan from config.yaml and, once a day at
the configured time, builds that day's post via the pipeline.

In 'review' mode the post lands in the queue for you to approve. In 'auto' mode
it publishes itself. Run it with:  python run.py run-scheduler
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import Config
from .db import DB
from . import pipeline

log = logging.getLogger(__name__)

_DAY_INDEX = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def _pillar_for_today(config: Config, weekday: int) -> str | None:
    schedule = config.posting.get("schedule", {})
    for name, idx in _DAY_INDEX.items():
        if idx == weekday:
            return schedule.get(name)
    return None


def run_daily_job(config: Config, db: DB) -> None:
    """Called once per day by the scheduler."""
    import datetime as _dt

    weekday = _dt.datetime.now().weekday()
    pillar = _pillar_for_today(config, weekday)
    if not pillar:
        log.info("No pillar scheduled for today. Nothing to do.")
        return

    log.info("Scheduled run: building a '%s' post (mode=%s)", pillar, config.mode)
    result = pipeline.generate(config, db, pillar)
    if result.get("ok"):
        where = "published" if config.mode == "auto" else "added to the review queue"
        log.info("Done: %s post %s.", pillar, where)
    else:
        log.warning("Could not build %s post: %s", pillar, result.get("error"))


def start(config: Config, db: DB) -> None:
    """Start the blocking scheduler. Ctrl+C to stop."""
    tz = config.posting.get("timezone", "America/New_York")
    time_of_day = str(config.posting.get("time_of_day", "09:30"))
    hour, minute = (int(x) for x in time_of_day.split(":"))

    scheduler = BlockingScheduler(timezone=tz)
    scheduler.add_job(
        run_daily_job,
        CronTrigger(hour=hour, minute=minute, timezone=tz),
        args=[config, db],
        id="daily_post",
        misfire_grace_time=3600,
    )
    log.info(
        "Scheduler started. A post will be built every day at %s (%s), mode=%s. "
        "Press Ctrl+C to stop.",
        time_of_day, tz, config.mode,
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped.")
