"""Optional built-in scheduler. Runs a full autonomous cycle once a day at the
configured time, using the weekly plan in config.yaml.

On Windows, the simplest hands-off setup is Windows Task Scheduler running
`python run.py run-today` daily (see the README). This blocking scheduler is an
alternative you can leave running in a window.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import Config
from .db import DB
from . import pipeline

log = logging.getLogger(__name__)


def start(config: Config, db: DB) -> None:
    tz = config.posting.get("timezone", "America/New_York")
    time_of_day = str(config.posting.get("time_of_day", "09:30"))
    hour, minute = (int(x) for x in time_of_day.split(":"))

    scheduler = BlockingScheduler(timezone=tz)
    scheduler.add_job(
        pipeline.run_once,
        CronTrigger(hour=hour, minute=minute, timezone=tz),
        args=[config, db],
        id="daily_post",
        misfire_grace_time=3600,
    )
    log.info(
        "Scheduler running. It will post automatically every day at %s (%s). "
        "Keep this window open. Press Ctrl+C to stop.",
        time_of_day, tz,
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped.")
