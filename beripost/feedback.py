"""Feedback memory.

Feedback you give is stored in feedback.md and loaded into the writer every
time, so future posts reflect it. You can add feedback three ways:
  1. CLI:      python run.py feedback "keep posts shorter and mention NJ"
  2. Edit:     open feedback.md and type notes yourself
  3. Web:      click "Give feedback" on the GitHub Pages gallery, which opens a
               pre-filled GitHub issue; the bot folds new issues in on its next run.
"""
from __future__ import annotations

import logging
import time

import requests

from .config import Config
from .db import DB
from . import llm

log = logging.getLogger(__name__)

_HEADER = (
    "# Feedback memory\n\n"
    "Guidance the bot applies to every post. Newest notes are at the bottom.\n"
    "Add with `python run.py feedback \"...\"`, by editing this file, or via the\n"
    "\"Give feedback\" button on the web gallery.\n\n"
)


def _path(config: Config):
    return config.root / "feedback.md"


def load(config: Config) -> str:
    """The full feedback text, or '' if none yet."""
    try:
        return _path(config).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def notes(config: Config) -> list[str]:
    """The actual feedback notes (bullet lines only), ignoring the header prose."""
    out = []
    for line in load(config).splitlines():
        s = line.strip()
        if s.startswith("- "):
            out.append(s[2:].strip())
    return [n for n in out if n]


def as_guidance(config: Config) -> str:
    """The feedback formatted for injection into the writer's system prompt."""
    items = notes(config)
    if not items:
        return ""
    body = "\n".join(f"- {n}" for n in items)
    return (
        "\n\n---\n\nFEEDBACK FROM THE PAGE OWNER (apply this to every post; it "
        "overrides earlier guidance where they conflict):\n" + body
    )


def add(config: Config, text: str) -> None:
    """Append a feedback note."""
    text = text.strip()
    if not text:
        return
    path = _path(config)
    existing = load(config)
    if not existing:
        existing = _HEADER
    stamp = time.strftime("%Y-%m-%d")
    path.write_text(existing.rstrip() + f"\n- ({stamp}) {text}\n", encoding="utf-8")
    log.info("Recorded feedback: %s", text)


def consolidate(config: Config) -> None:
    """Use the cheap model to merge notes into a concise, de-duplicated list."""
    items = notes(config)
    if not items:
        return  # nothing to tidy; never call the model with an empty list
    body = "\n".join(f"- {n}" for n in items)
    system = (
        "You tidy a list of feedback notes for a social media writer into a short, "
        "clear, de-duplicated set of standing instructions. Keep every distinct point, "
        "merge duplicates, drop dates, and output a plain bulleted list only."
    )
    try:
        tidy = llm.complete(config.cheap_model, system, body, max_tokens=600)
    except Exception:  # noqa: BLE001
        log.exception("Could not consolidate feedback; leaving it as-is.")
        return
    _path(config).write_text(_HEADER + tidy.strip() + "\n", encoding="utf-8")
    log.info("Consolidated feedback notes.")


def ingest_github(config: Config, db: DB) -> int:
    """Fold new 'Feedback' GitHub issues into feedback.md. Returns count added.

    Reads open issues from the configured repo (public repos need no token).
    Marks each issue as seen so it is only folded in once. If a GITHUB_TOKEN is
    set, closes the issue with a thank-you comment.
    """
    repo = config.site.get("repo")
    if not repo:
        return 0
    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {"Accept": "application/vnd.github+json"}
    if config.github_token:
        headers["Authorization"] = f"Bearer {config.github_token}"
    try:
        resp = requests.get(url, headers=headers, params={"state": "open", "per_page": 50}, timeout=30)
        resp.raise_for_status()
        issues = resp.json()
    except Exception:  # noqa: BLE001
        log.exception("Could not read GitHub feedback issues; skipping.")
        return 0

    added = 0
    for issue in issues:
        if "pull_request" in issue:  # skip PRs
            continue
        title = (issue.get("title") or "")
        labels = {l.get("name", "").lower() for l in issue.get("labels", [])}
        if not (title.lower().startswith("feedback") or "feedback" in labels):
            continue
        issue_id = issue.get("id")
        if issue_id is None or db.feedback_issue_seen(issue_id):
            continue
        note = (issue.get("body") or title).strip()
        if note:
            add(config, note)
            added += 1
        db.remember_feedback_issue(issue_id)
        _close_issue(config, repo, issue.get("number"))
    if added:
        log.info("Folded in %d new feedback note(s) from GitHub.", added)
    return added


def _close_issue(config: Config, repo: str, number) -> None:
    if not (config.github_token and number):
        return
    try:
        requests.patch(
            f"https://api.github.com/repos/{repo}/issues/{number}",
            headers={"Authorization": f"Bearer {config.github_token}",
                     "Accept": "application/vnd.github+json"},
            json={"state": "closed"},
            timeout=30,
        )
    except Exception:  # noqa: BLE001
        log.exception("Could not close feedback issue #%s.", number)
