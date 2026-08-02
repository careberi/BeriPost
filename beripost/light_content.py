"""Light engagement content: care/health/wellness trivia and clean dad jokes.

Structured like the writer output (title, subtitle, bullets, body) so it flows
into the same card image. Dedupes against DB history and applies feedback.
"""
from __future__ import annotations

import json
import logging

from .config import Config
from .db import DB
from . import feedback, llm

log = logging.getLogger(__name__)

_MAX_TRIES = 4

_JSON_RULES = (
    ' Output valid JSON only (no code fences): '
    '{"title": "<short hook>", "subtitle": "<one line>", "bullets": [], "body": "<caption>"}. '
    "Never use em dashes."
)


def _system(config: Config, role: str) -> str:
    return config.brand_voice() + feedback.as_guidance(config) + "\n\n---\n\n" + role + _JSON_RULES


def _parse(raw: str) -> dict:
    text = raw.strip().strip("`")
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {"title": "", "subtitle": "", "bullets": [], "body": raw.strip()}
    return {
        "title": str(data.get("title", "")).strip(),
        "subtitle": str(data.get("subtitle", "")).strip(),
        "bullets": [],
        "body": str(data.get("body", "")).strip(),
    }


def _generate(config: Config, db: DB, kind: str, system: str, prompt: str) -> dict:
    post = {"title": "", "subtitle": "", "bullets": [], "body": ""}
    for attempt in range(_MAX_TRIES):
        post = _parse(llm.complete(config.writer_model, system, prompt, max_tokens=500))
        key = post["body"] or post["subtitle"] or post["title"]
        if key and not db.light_seen(key):
            db.remember_light(kind, key)
            return post
        log.info("%s repeat on attempt %d, retrying", kind, attempt + 1)
    log.warning("Could not get a fresh %s after %d tries; using the last one.", kind, _MAX_TRIES)
    return post


def make_trivia(config: Config, db: DB) -> dict:
    cta = config.cta()
    system = _system(
        config,
        "You create light, positive wellness/care TRIVIA for a home care page. Warm and "
        "apolitical, no medical advice.",
    )
    prompt = (
        "Write one short, delightful piece of wellness or care trivia families will enjoy.\n"
        "title: a hook such as 'Did you know?'. subtitle: the fun fact or a question-and-answer, "
        "kept to one or two sentences. bullets: empty. body: a friendly caption of the fact, "
        f"ending with this exact call to action: {cta}"
    )
    return _generate(config, db, "trivia", system, prompt)


def make_dad_joke(config: Config, db: DB) -> dict:
    cta = config.cta()
    system = _system(
        config,
        "You write clean, warm, apolitical DAD JOKES for a home care page. Gentle and "
        "wholesome, suitable for all ages.",
    )
    prompt = (
        "Write one clean, warm, genuinely groan-worthy dad joke.\n"
        "title: the setup (a short question or line). subtitle: the punchline. bullets: empty. "
        f"body: the full joke as a caption, ending with this exact call to action: {cta}"
    )
    return _generate(config, db, "dad_joke", system, prompt)
