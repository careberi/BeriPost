"""The autonomous orchestrator.

A run does, hands-off and in order:
  1. fold in any new feedback (from GitHub issues)
  2. build the day's post (news / education / trivia / dad joke)
  3. compose the branded card image
  4. publish to the Facebook Page
  5. email Neil a copy
  6. record it and rebuild the GitHub Pages gallery
  7. commit and push, so the web gallery updates

Nothing needs approval. Failures are logged and recorded, never fatal.
"""
from __future__ import annotations

import datetime as _dt
import logging
import subprocess

from .config import Config
from .db import DB
from . import feedback, images, light_content, notifier, publisher, site, sources, writer

log = logging.getLogger(__name__)

PILLARS = ("news", "education", "trivia", "dad_joke")

_DAY_INDEX = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def pillar_for_today(config: Config, weekday: int | None = None) -> str | None:
    if weekday is None:
        weekday = _dt.datetime.now().weekday()
    schedule = config.posting.get("schedule", {})
    for name, idx in _DAY_INDEX.items():
        if idx == weekday:
            return schedule.get(name)
    return None


def build_post(config: Config, db: DB, pillar: str) -> dict:
    """Generate content + image for one pillar. Never raises."""
    result = {"ok": False, "pillar": pillar, "title": "", "body": "",
              "source_url": None, "image_path": None, "error": None, "article": None}
    try:
        if pillar == "news":
            items = sources.fetch_new_items(config, db, limit=5)
            if not items:
                result["error"] = "No fresh, on-brand news articles found right now."
                return result
            item = items[0]
            include_link = config.should_link(item["url"])
            post = writer.write_news_post(config, item, include_link=include_link)
            result["source_url"] = item["url"] if include_link else None
            # Remember the article, but only mark it "used" after it actually
            # posts (done in run_once). Previews must not consume articles.
            result["article"] = item
        elif pillar == "education":
            post = writer.write_education_post(config)
        elif pillar == "trivia":
            post = light_content.make_trivia(config, db)
        elif pillar == "dad_joke":
            post = light_content.make_dad_joke(config, db)
        else:
            result["error"] = f"Unknown pillar: {pillar}"
            return result

        title = post.get("title") or config.brand.get("name", "Careberi")
        result["title"] = title
        result["body"] = post.get("body", "")

        if config.images_enabled:
            try:
                img = images.compose(config, title, subtitle=post.get("subtitle"),
                                     bullets=post.get("bullets"))
                result["image_path"] = str(img)
            except Exception:  # noqa: BLE001
                log.exception("Image composition failed for pillar %s", pillar)

        result["ok"] = True
        return result
    except Exception as exc:  # noqa: BLE001
        log.exception("Failed to build %s post", pillar)
        result["error"] = str(exc)
        return result


def _publish_and_record(config: Config, db: DB, result: dict) -> dict:
    post_id = db.add_post(
        pillar=result["pillar"], headline=result["title"], body=result["body"],
        source_url=result["source_url"], image_path=result["image_path"], status="pending",
    )
    result["post_id"] = post_id
    try:
        fb_id = publisher.publish(config, result["body"], result["image_path"])
        db.mark_published(post_id, fb_id)
        result["status"] = "published"
        result["fb_post_id"] = fb_id
        notifier.notify_post(config, result["pillar"], result["body"], result["image_path"], fb_id)
    except Exception as exc:  # noqa: BLE001
        log.exception("Publishing failed for post %s", post_id)
        db.mark_failed(post_id, str(exc))
        result["status"] = "failed"
        result["error"] = str(exc)
    return result


def run_once(config: Config, db: DB, pillar: str | None = None, dry_run: bool = False) -> dict:
    """One full autonomous cycle. If pillar is None, uses today's scheduled pillar."""
    if not dry_run:
        feedback.ingest_github(config, db)

    pillar = pillar or pillar_for_today(config)
    if not pillar:
        log.info("No pillar scheduled for today; nothing to do.")
        return {"ok": True, "skipped": True, "pillar": None}

    log.info("Building a '%s' post (dry_run=%s)", pillar, dry_run)
    result = build_post(config, db, pillar)
    if not result["ok"] or dry_run:
        return result

    _publish_and_record(config, db, result)

    # Only now, after a real publish, mark the news article as used so it is
    # never posted again. (Previews never reach this point.)
    if result.get("status") == "published" and result.get("article"):
        a = result["article"]
        db.mark_article_used(a["guid"], a.get("url", ""), a.get("title", ""), a.get("source", ""))

    # Update the web gallery and push it, regardless of publish success.
    try:
        site.build(config, db)
        _git_publish(config, result["pillar"])
    except Exception:  # noqa: BLE001
        log.exception("Could not update/push the web gallery.")
    return result


def _git_publish(config: Config, pillar: str) -> None:
    """Commit the gallery + feedback and push. Best-effort."""
    if not config.site.get("auto_push", True):
        return
    root = str(config.root)
    try:
        subprocess.run(["git", "add", "docs", "feedback.md"], cwd=root, check=False,
                       capture_output=True)
        committed = subprocess.run(
            ["git", "commit", "-m", f"Publish {pillar} post to the gallery"],
            cwd=root, check=False, capture_output=True, text=True,
        )
        if committed.returncode == 0:
            push = subprocess.run(["git", "push"], cwd=root, check=False,
                                  capture_output=True, text=True)
            if push.returncode == 0:
                log.info("Pushed the updated gallery to GitHub.")
            else:
                log.warning("git push failed: %s", push.stderr.strip())
        else:
            log.info("No gallery changes to commit.")
    except Exception:  # noqa: BLE001
        log.exception("git publish step failed.")
