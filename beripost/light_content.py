"""Light engagement content: care/health/wellness trivia and clean dad jokes.

Both check the DB history so we do not repeat ourselves. We try a few times to
get something new before giving up.
"""
from __future__ import annotations

import json
import logging

from .config import Config
from .db import DB
from . import llm

log = logging.getLogger(__name__)

_MAX_TRIES = 4


def _parse(raw: str) -> dict:
    text = raw.strip().strip("`")
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    try:
        data = json.loads(text)
        return {"headline": str(data.get("headline", "")).strip(),
                "body": str(data.get("body", "")).strip()}
    except json.JSONDecodeError:
        return {"headline": "", "body": raw.strip()}


def _generate(config: Config, db: DB, kind: str, system: str, prompt: str) -> dict:
    for attempt in range(_MAX_TRIES):
        raw = llm.complete(config.writer_model, system, prompt, max_tokens=400)
        post = _parse(raw)
        key = post["body"] or post["headline"]
        if key and not db.light_seen(key):
            db.remember_light(kind, key)
            return post
        log.info("%s repeat on attempt %d, retrying", kind, attempt + 1)
    # Give up on novelty but still return something.
    log.warning("Could not get a fresh %s after %d tries; using last one.", kind, _MAX_TRIES)
    return post


def make_trivia(config: Config, db: DB) -> dict:
    cta = config.cta()
    system = (
        config.brand_voice()
        + "\n\n---\n\nYou create light, positive TRIVIA for a home care agency's page. "
        "Themes: care, health, wellness, aging well, positivity. Warm and apolitical. "
        "No medical advice. Output valid JSON only: "
        '{"headline": "<short hook>", "body": "<the trivia question + a friendly answer + the CTA>"}'
    )
    prompt = (
        "Write one short, delightful piece of wellness/care trivia families will enjoy. "
        "Include the fun fact or a question-and-answer, kept short.\n"
        f"End the body with this exact call to action: {cta}\n"
        "No em dashes."
    )
    return _generate(config, db, "trivia", system, prompt)


def make_dad_joke(config: Config, db: DB) -> dict:
    cta = config.cta()
    system = (
        config.brand_voice()
        + "\n\n---\n\nYou write clean, warm, apolitical DAD JOKES for a home care agency's page. "
        "Gentle and wholesome, suitable for all ages. Output valid JSON only: "
        '{"headline": "<short setup or hook>", "body": "<the joke, then the CTA>"}'
    )
    prompt = (
        "Write one clean, warm dad joke. Keep it short and genuinely groan-worthy.\n"
        f"End the body with this exact call to action: {cta}\n"
        "No em dashes."
    )
    return _generate(config, db, "dad_joke", system, prompt)
