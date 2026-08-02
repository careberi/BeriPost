"""Turns a news item or an education topic into a finished Careberi post.

Returns a dict: {"headline": str, "body": str}. The headline is a short line
used on the composed image; the body is the full Facebook caption.
"""
from __future__ import annotations

import json
import logging

from .config import Config
from . import llm

log = logging.getLogger(__name__)


def _base_system(config: Config) -> str:
    return (
        config.brand_voice()
        + "\n\n---\n\n"
        + "You write Facebook posts for the Careberi page. Follow the brand voice above "
        "exactly. Output MUST be valid JSON only, no other text, in this shape:\n"
        '{"headline": "<short scroll-stopping line, max 12 words>", '
        '"body": "<the full Facebook caption>"}\n'
        "Do not use em dashes anywhere. Do not add markdown code fences."
    )


def _parse(raw: str) -> dict:
    """Parse the model's JSON. Fall back gracefully if it added stray text."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[-1] if "\n" in text else text
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
        return {"headline": str(data.get("headline", "")).strip(),
                "body": str(data.get("body", "")).strip()}
    except json.JSONDecodeError:
        log.warning("Writer returned non-JSON; using raw text as body.")
        return {"headline": "", "body": raw.strip()}


def write_news_post(config: Config, item: dict) -> dict:
    """Original 80-150 word commentary on a news item, plus the source link."""
    cta = config.cta()
    system = _base_system(config)
    prompt = (
        "Write an ORIGINAL news-commentary post for the pillar 'news'.\n"
        "Do NOT copy or closely paraphrase the article text. Summarize the gist in your "
        "own words in one sentence, then add Careberi's own helpful angle for families: "
        "what this means for them, or a reassuring, practical takeaway.\n"
        "80 to 150 words of commentary. Then, on its own line, add: "
        f'Read more: {item["url"]}\n'
        f"End with this exact call to action: {cta}\n\n"
        f"Article title: {item['title']}\n"
        f"Article summary: {item.get('summary', '')[:800]}\n"
        f"Source: {item.get('source', '')}"
    )
    raw = llm.complete(config.writer_model, system, prompt, max_tokens=900)
    return _parse(raw)


def write_education_post(config: Config, topic: str | None = None) -> dict:
    """Evergreen, reassuring 'what good home care looks like' education post."""
    cta = config.cta()
    system = _base_system(config)
    topic_line = f"Focus topic: {topic}\n" if topic else (
        "Pick a helpful evergreen topic families care about (what good home care looks "
        "like, questions to ask when arranging care, standards to expect, how to prepare "
        "for a first caregiver visit, supporting a loved one's independence, etc.).\n"
    )
    prompt = (
        "Write a purely informative, reassuring EDUCATION post for families arranging "
        "care for an aging or disabled loved one.\n"
        + topic_line
        + "90 to 150 words. Never frame it as 'if your provider does X, switch to us'. "
        "No fear. Just genuinely helpful information a caring friend would share.\n"
        f"End with this exact call to action: {cta}"
    )
    raw = llm.complete(config.writer_model, system, prompt, max_tokens=900)
    return _parse(raw)
