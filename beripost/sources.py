"""Fetch industry news from RSS feeds, dedupe, and filter out anything
political or sensitive with a cheap Claude classifier.
"""
from __future__ import annotations

import logging

import feedparser

from .config import Config
from .db import DB
from . import llm

log = logging.getLogger(__name__)

CLASSIFIER_SYSTEM = (
    "You are a content safety filter for a home care agency's Facebook page. "
    "You decide if a news headline is SAFE to comment on. "
    "SAFE topics: home care, senior care, aging, caregiving, disability support, "
    "health and wellness for families, industry business news. "
    "NOT SAFE: politics, elections, partisan policy fights, crime, tragedy, lawsuits, "
    "abuse, anything graphic, or anything that would be sensitive or off-brand for a "
    "warm, apolitical family-focused page. "
    "Answer with exactly one word: SAFE or SKIP."
)


def _guid(entry) -> str:
    """A stable identifier for a feed entry."""
    return entry.get("id") or entry.get("link") or entry.get("title", "")


def _is_safe(cheap_model: str, title: str, summary: str) -> bool:
    prompt = f"Headline: {title}\n\nSummary: {summary[:500]}\n\nSAFE or SKIP?"
    try:
        answer = llm.complete(cheap_model, CLASSIFIER_SYSTEM, prompt, max_tokens=8)
        return answer.strip().upper().startswith("SAFE")
    except Exception:  # noqa: BLE001 - a failed classify should not crash the run
        log.exception("Classifier failed for %r; skipping to be safe", title)
        return False


def fetch_new_items(config: Config, db: DB, limit: int | None = None) -> list[dict]:
    """Return a list of fresh, safe news items we have never used before.

    Each item: {guid, title, url, summary, source}. Items are remembered in the
    DB immediately so we never surface the same article twice, even across runs.
    """
    limit = limit or config.sources.get("max_articles_per_run", 15)
    fresh: list[dict] = []

    for feed_url in config.feeds:
        log.info("Fetching feed: %s", feed_url)
        try:
            parsed = feedparser.parse(feed_url)
        except Exception:  # noqa: BLE001
            log.exception("Could not parse feed %s", feed_url)
            continue

        source_name = parsed.feed.get("title", feed_url)

        for entry in parsed.entries:
            guid = _guid(entry)
            if not guid or db.article_seen(guid):
                continue

            title = entry.get("title", "").strip()
            url = entry.get("link", "")
            summary = entry.get("summary", "")

            # Remember it now so we do not re-consider it next run.
            db.remember_article(guid, url, title, source_name)

            if not title or not url:
                continue

            if not _is_safe(config.cheap_model, title, summary):
                log.info("Filtered out (not safe/on-brand): %s", title)
                continue

            fresh.append(
                {
                    "guid": guid,
                    "title": title,
                    "url": url,
                    "summary": summary,
                    "source": source_name,
                }
            )
            if len(fresh) >= limit:
                return fresh

    return fresh
