"""Fetch industry news from RSS feeds, dedupe, and filter out anything
political or sensitive with a cheap Claude classifier.
"""
from __future__ import annotations

import calendar
import logging
import time
from urllib.parse import quote_plus

import feedparser

from .config import Config
from .db import DB
from . import llm

log = logging.getLogger(__name__)


def _topic_feeds(config: Config, days: int) -> list[str]:
    """Build dynamic Google News RSS search feeds from configured topics."""
    urls = []
    for topic in config.sources.get("topics", []):
        query = quote_plus(f"{topic} when:{days}d")
        urls.append(
            f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        )
    return urls


def _entry_epoch(entry) -> float | None:
    """The entry's publish time as a Unix timestamp, or None if unknown."""
    for key in ("published_parsed", "updated_parsed"):
        parsed = entry.get(key)
        if parsed:
            try:
                return calendar.timegm(parsed)  # feedparser dates are UTC
            except Exception:  # noqa: BLE001
                pass
    return None

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


def fetch_new_items(config: Config, db: DB, limit: int | None = None,
                    exclude: set | None = None) -> list[dict]:
    """Return a list of fresh, safe news items we have never used before.

    Each item: {guid, title, url, summary, source}. Items are remembered in the
    DB immediately so we never surface the same article twice, even across runs.
    """
    limit = limit or config.sources.get("max_articles_per_run", 15)
    exclude = exclude or set()
    max_age_days = int(config.sources.get("max_age_days", 60))
    cutoff = time.time() - max_age_days * 86400
    fresh: list[dict] = []

    # Explicit RSS feeds plus dynamic topic searches (Google News RSS).
    all_feeds = list(config.feeds) + _topic_feeds(config, max_age_days)

    for feed_url in all_feeds:
        log.info("Fetching feed: %s", feed_url)
        try:
            parsed = feedparser.parse(feed_url)
        except Exception:  # noqa: BLE001
            log.exception("Could not parse feed %s", feed_url)
            continue

        source_name = parsed.feed.get("title", feed_url)

        for entry in parsed.entries:
            guid = _guid(entry)
            if not guid or guid in exclude or db.article_seen(guid):
                continue

            # Only consider recent articles (default: last 60 days).
            published = _entry_epoch(entry)
            if published is not None and published < cutoff:
                continue

            title = entry.get("title", "").strip()
            url = entry.get("link", "")
            summary = entry.get("summary", "")

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
