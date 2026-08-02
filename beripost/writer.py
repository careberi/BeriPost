"""Turns a news item or an education topic into a finished Careberi post.

Returns a dict with keys used by the rest of the pipeline:
  title    - short hook, shown large on the card image
  subtitle - a supporting line (news takeaway, or the tips-card heading)
  bullets  - list of short tips (education only; [] otherwise)
  body     - the full Facebook caption

The writer always loads brand_voice.md AND the feedback memory, so your notes
shape every post.
"""
from __future__ import annotations

import json
import logging

from .config import Config
from . import feedback, llm

log = logging.getLogger(__name__)

_JSON_RULES = (
    "\n\n---\n\n"
    "You write Facebook posts for the Careberi page. Follow the brand voice and any "
    "feedback above exactly. Output MUST be valid JSON only (no code fences, no extra "
    "text), in this exact shape:\n"
    '{"title": "<short scroll-stopping hook, max 10 words>", '
    '"subtitle": "<one supporting line>", '
    '"bullets": ["<short tip>", "..."], '
    '"body": "<the full Facebook caption>"}\n'
    "Use an empty list for bullets when the post is not a tips list. "
    "Never use em dashes anywhere."
)


def _system(config: Config) -> str:
    return (config.brand_voice() + feedback.as_guidance(config)
            + config.seo_guidance() + _JSON_RULES)


def _parse(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[-1] if "\n" in text else text
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.warning("Writer returned non-JSON; using raw text as the caption.")
        return {"title": "", "subtitle": "", "bullets": [], "body": raw.strip()}
    bullets = data.get("bullets") or []
    if not isinstance(bullets, list):
        bullets = []
    return {
        "title": str(data.get("title", "")).strip(),
        "subtitle": str(data.get("subtitle", "")).strip(),
        "bullets": [str(b).strip() for b in bullets if str(b).strip()],
        "body": str(data.get("body", "")).strip(),
    }


def write_news_post(config: Config, item: dict, include_link: bool = True) -> dict:
    """Original 80-150 word commentary on a news item.

    If include_link is False (a paywalled source), the post comments on the
    topic but contains no link, so families never hit a paywall.
    """
    cta = config.cta()
    if include_link:
        body_rule = (
            "body: 80 to 150 words of commentary, then on its own line "
            f'"Read more: {item["url"]}", then this exact call to action: {cta}'
        )
    else:
        body_rule = (
            "body: 80 to 150 words of commentary. Do NOT include any link or a 'Read more' "
            "line, because the source is subscription-only. Refer to it generally (for example "
            "'a recent industry report'), do not name a website to visit, then end with this "
            f"exact call to action: {cta}"
        )
    prompt = (
        "Write an ORIGINAL news-commentary post (pillar 'news').\n"
        "Do NOT copy or closely paraphrase the article. Summarize the gist in your own "
        "words in one sentence, then add Careberi's helpful angle for families.\n"
        "title: a short hook. subtitle: a one-line takeaway families can hold onto. "
        "bullets: leave empty. "
        + body_rule + "\n\n"
        f"Article title: {item['title']}\n"
        f"Article summary: {item.get('summary', '')[:800]}\n"
        f"Source: {item.get('source', '')}"
    )
    return _parse(llm.complete(config.writer_model, _system(config), prompt, max_tokens=1000))


def write_education_post(config: Config, topic: str | None = None) -> dict:
    """Evergreen, reassuring tips post for families arranging care."""
    cta = config.cta()
    topic_line = f"Focus topic: {topic}\n" if topic else (
        "Pick a helpful evergreen topic (what good home care looks like, questions to ask "
        "when arranging care, standards to expect, preparing for a first caregiver visit, "
        "supporting a loved one's independence, etc.).\n"
    )
    prompt = (
        "Write a purely informative, reassuring EDUCATION tips post for families arranging "
        "care for an aging or disabled loved one. No fear, never 'switch to us' framing.\n"
        + topic_line
        + "title: a short, warm hook. subtitle: a short heading for the tips (for example "
        "'Questions worth asking' or 'Simple things that help'). bullets: 3 to 5 short, "
        "concrete tips (each under 9 words). body: a warm 90 to 150 word caption that stands "
        f"on its own, ending with this exact call to action: {cta}"
    )
    return _parse(llm.complete(config.writer_model, _system(config), prompt, max_tokens=1000))
