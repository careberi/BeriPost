"""The orchestrator: build a finished post for a given content pillar, compose
its image, and route it (into the review queue, or straight to Facebook in auto
mode). Also the single place that turns a headline+body into a full caption.

A failure while building one post is logged and returned as an error result; it
never raises, so the scheduler can carry on.
"""
from __future__ import annotations

import logging

from .config import Config
from .db import DB
from . import images, light_content, publisher, sources, writer

log = logging.getLogger(__name__)

PILLARS = ("news", "education", "trivia", "dad_joke")


def _caption(post: dict) -> str:
    """The full Facebook caption is just the body. Headline lives on the image."""
    return post.get("body", "").strip()


def build_post(config: Config, db: DB, pillar: str) -> dict:
    """Generate one post for `pillar`. Returns a result dict with keys:
    ok, pillar, headline, body, source_url, image_path, error.
    Does not save or publish - that is done by generate() / caller.
    """
    result = {
        "ok": False,
        "pillar": pillar,
        "headline": "",
        "body": "",
        "source_url": None,
        "image_path": None,
        "error": None,
    }
    try:
        if pillar == "news":
            items = sources.fetch_new_items(config, db, limit=5)
            if not items:
                result["error"] = "No fresh, on-brand news articles found right now."
                return result
            item = items[0]
            post = writer.write_news_post(config, item)
            result["source_url"] = item["url"]
            db.mark_article_used(item["guid"])
        elif pillar == "education":
            post = writer.write_education_post(config)
        elif pillar == "trivia":
            post = light_content.make_trivia(config, db)
        elif pillar == "dad_joke":
            post = light_content.make_dad_joke(config, db)
        else:
            result["error"] = f"Unknown pillar: {pillar}"
            return result

        headline = post.get("headline") or config.brand.get("name", "Careberi")
        result["headline"] = headline
        result["body"] = post.get("body", "")

        # Compose the on-brand image from the headline.
        try:
            img_path = images.compose(config, headline)
            result["image_path"] = str(img_path)
        except Exception:  # noqa: BLE001 - image failure should not lose the text
            log.exception("Image composition failed for pillar %s", pillar)

        result["ok"] = True
        return result
    except Exception as exc:  # noqa: BLE001
        log.exception("Failed to build %s post", pillar)
        result["error"] = str(exc)
        return result


def generate(config: Config, db: DB, pillar: str, dry_run: bool = False) -> dict:
    """Build a post and route it according to mode.

    - dry_run: build and return it, save/publish nothing.
    - mode 'review': save to the queue as 'pending'.
    - mode 'auto': save and publish immediately.
    Returns the result dict, plus 'post_id' if it was saved.
    """
    result = build_post(config, db, pillar)
    if not result["ok"]:
        return result

    if dry_run:
        result["post_id"] = None
        return result

    status = "approved" if config.mode == "auto" else "pending"
    post_id = db.add_post(
        pillar=result["pillar"],
        headline=result["headline"],
        body=result["body"],
        source_url=result["source_url"],
        image_path=result["image_path"],
        status=status,
    )
    result["post_id"] = post_id

    if config.mode == "auto":
        publish_saved(config, db, post_id)
        # refresh status/error from DB
        saved = db.get_post(post_id)
        result["status"] = saved["status"]
        result["error"] = saved["error"]
    else:
        result["status"] = "pending"

    return result


def publish_saved(config: Config, db: DB, post_id: int) -> dict:
    """Publish one saved post by id. Logs and records errors, never raises."""
    post = db.get_post(post_id)
    if not post:
        return {"ok": False, "error": f"Post {post_id} not found"}
    try:
        fb_id = publisher.publish(config, _caption(post), post.get("image_path"))
        db.mark_published(post_id, fb_id)
        return {"ok": True, "post_id": post_id, "fb_post_id": fb_id}
    except Exception as exc:  # noqa: BLE001
        log.exception("Publishing post %s failed", post_id)
        db.mark_failed(post_id, str(exc))
        return {"ok": False, "post_id": post_id, "error": str(exc)}


def publish_approved(config: Config, db: DB) -> list[dict]:
    """Publish every post currently marked 'approved'. Used by the CLI and web app."""
    results = []
    for post in db.list_posts(status="approved"):
        results.append(publish_saved(config, db, post["id"]))
    return results
