#!/usr/bin/env python3
"""BeriPost command line (hands-off edition).

Everyday use is automatic (Windows Task Scheduler runs `run-today`). These
commands are here when you want them:

    python run.py run-today               # build + post today's scheduled post
    python run.py post --pillar news      # build + post one specific pillar now
    python run.py dry-run                  # build today's post and print it, post nothing
    python run.py feedback "keep it short" # teach the bot; applies to future posts
    python run.py tidy-feedback            # tidy the feedback notes into a clean list
    python run.py build-site               # rebuild the web gallery from history
    python run.py run-scheduler            # keep running and post daily (alternative)
"""
from __future__ import annotations

import argparse
import logging
import sys

from beripost import feedback, pipeline, scheduler, site
from beripost.config import ConfigError, get_config
from beripost.db import DB


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )


def _print_post(result: dict) -> None:
    line = "=" * 70
    print(f"\n{line}\nPILLAR : {result.get('pillar')}")
    if result.get("source_url"):
        print(f"SOURCE : {result['source_url']}")
    print(f"IMAGE  : {result.get('image_path')}")
    print(f"TITLE  : {result.get('title')}")
    print(f"{line}\nCAPTION:\n\n{result.get('body', '')}\n{line}")


def cmd_run_today(config, db, args) -> int:
    result = pipeline.run_once(config, db, dry_run=False)
    if result.get("skipped"):
        print("No pillar scheduled for today. Nothing posted.")
        return 0
    if not result.get("ok"):
        print(f"Could not build post: {result.get('error')}", file=sys.stderr)
        return 1
    _print_post(result)
    print(f"\nStatus: {result.get('status')}")
    if result.get("error"):
        print(f"Note: {result['error']}", file=sys.stderr)
    return 0


def cmd_post(config, db, args) -> int:
    result = pipeline.run_once(config, db, pillar=args.pillar, dry_run=False)
    if not result.get("ok"):
        print(f"Could not build post: {result.get('error')}", file=sys.stderr)
        return 1
    _print_post(result)
    print(f"\nStatus: {result.get('status')}")
    return 0 if result.get("status") != "failed" else 1


def cmd_dry_run(config, db, args) -> int:
    pillar = args.pillar or pipeline.pillar_for_today(config)
    if not pillar:
        print("No pillar scheduled for today in config.yaml.")
        return 0
    result = pipeline.run_once(config, db, pillar=pillar, dry_run=True)
    if not result.get("ok"):
        print(f"Could not build post: {result.get('error')}", file=sys.stderr)
        return 1
    _print_post(result)
    print("\n(dry run: nothing was posted, emailed, or pushed)")
    return 0


def cmd_feedback(config, db, args) -> int:
    note = " ".join(args.text).strip()
    if not note:
        print("Nothing to add. Example: python run.py feedback \"keep posts under 100 words\"")
        return 1
    feedback.add(config, note)
    print("Saved. Future posts will take this into account.")
    return 0


def cmd_tidy_feedback(config, db, args) -> int:
    feedback.consolidate(config)
    print("Feedback notes tidied. See feedback.md.")
    return 0


def cmd_build_site(config, db, args) -> int:
    out = site.build(config, db)
    print(f"Gallery written to {out}")
    return 0


def cmd_run_scheduler(config, db, args) -> int:
    scheduler.start(config, db)
    return 0


def main() -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(prog="run.py", description="BeriPost control")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run-today", help="build + post today's scheduled post").set_defaults(func=cmd_run_today)

    p = sub.add_parser("post", help="build + post one specific pillar now")
    p.add_argument("--pillar", required=True, choices=list(pipeline.PILLARS))
    p.set_defaults(func=cmd_post)

    d = sub.add_parser("dry-run", help="build a post and print it, post nothing")
    d.add_argument("--pillar", choices=list(pipeline.PILLARS), default=None)
    d.set_defaults(func=cmd_dry_run)

    f = sub.add_parser("feedback", help="teach the bot; applies to future posts")
    f.add_argument("text", nargs="+", help="your feedback, in quotes")
    f.set_defaults(func=cmd_feedback)

    sub.add_parser("tidy-feedback", help="tidy feedback notes into a clean list").set_defaults(func=cmd_tidy_feedback)
    sub.add_parser("build-site", help="rebuild the web gallery").set_defaults(func=cmd_build_site)
    sub.add_parser("run-scheduler", help="keep running and post daily").set_defaults(func=cmd_run_scheduler)

    args = parser.parse_args()
    try:
        config = get_config()
        config.require_anthropic()
    except ConfigError as exc:
        print(f"Configuration problem: {exc}", file=sys.stderr)
        return 1

    db = DB(config.db_path)
    return args.func(config, db, args)


if __name__ == "__main__":
    raise SystemExit(main())
