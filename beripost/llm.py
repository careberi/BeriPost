"""Thin wrapper around the Anthropic (Claude) API.

Every call to Claude in this project goes through complete() here. That keeps
model handling and response parsing in one place.
"""
from __future__ import annotations

import logging

import anthropic

log = logging.getLogger(__name__)

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        # Reads ANTHROPIC_API_KEY from the environment (loaded from .env).
        _client = anthropic.Anthropic()
    return _client


def complete(
    model: str,
    system: str,
    prompt: str,
    max_tokens: int = 1024,
    temperature: float | None = None,
) -> str:
    """Send one prompt to Claude and return the plain text answer.

    We deliberately keep this simple: one system prompt, one user message,
    text back. Thinking blocks (if any) are skipped when reading the response.
    """
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }
    # Newer models (sonnet-5, etc.) reject temperature, so only pass it when
    # explicitly requested for an older model.
    if temperature is not None:
        kwargs["temperature"] = temperature

    resp = _get_client().messages.create(**kwargs)
    text_parts = [block.text for block in resp.content if block.type == "text"]
    return "".join(text_parts).strip()
