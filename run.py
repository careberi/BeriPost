#!/usr/bin/env python3
"""BeriPost command line.

Examples:
    python run.py generate --pillar news        # build one post, route by mode
    python run.py generate --pillar dad_joke --dry-run   # build + print, post nothing
    python run.py dry-run                        # build today's scheduled pillar, print it
    python run.py publish-queue                  # publish everything marked 'approved'
    python run.py run-scheduler                  # run the daily scheduler (blocks)
    python run.py web                            # start the local web app
"""
from __future__ import annotations

import argparse
import logging
import sys

from beripost.config import ConfigError, get_config
from beripost.db import DB
from beripost import pipeline, scheduler


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )


def _print_post(result: dict) -> None:
    line = "=" * 70
    print(f"\n{line}")
    print(f"PILLAR : {result.get('pillar')}")
    if result.get("source_url"):
        print(f"SOURCE : {result['source_url']}")
    print(f"IMAGE  : {result.get('image_path')}")
    print(f"HEADLINE (on image): {result.get('headline')}")
    print(f"{line}\nCAPTION:\n")
    print(result.get("body", ""))
    print(line)


def cmd_generate(config, db, args) -> int:
    result = pipeline.generate(config, db, args.pillar, dry_run=args.dry_run)
    if not result.get("ok"):
        print(f"Could not build post: {result.get('error')}", file=sys.stderr)
        return 1
    _print_post(result)
    if args.dry_run:
        print("\n(dry run: nothing was saved or posted)")
    elif config.mode == "auto":
        print(f"\nMode=auto -> status: {result.get('status')}")
        if result.get("error"):
            print(f"Publish error: {result['error']}", file=sys.stderr)
    else:
        print(f"\nMode=review -> saved to the queue as pending (post id {result.get('post_id')}).")
        print("Open the web app to approve it:  python run.py web")
    return 0


def cmd_dry_run(config, db, args) -> int:
    import datetime as _dt

    pillar = scheduler._pillar_for_today(config, _dt.datetime.now().weekday())
    if not pillar:
        print("No pillar is scheduled for today in config.yaml.")
        return 0
    result = pipeline.generate(config, db, pillar, dry_run=True)
    if not result.get("ok"):
        print(f"Could not build post: {result.get('error')}", file=sys.stderr)
        return 1
    _print_post(result)
    print("\n(dry run: nothing was saved or posted)")
    return 0


def cmd_publish_queue(config, db, args) -> int:
    config.require_facebook()
    results = pipeline.publish_approved(config, db)
    if not results:
        print("Nothing approved to publish.")
        return 0
    ok = sum(1 for r in results if r.get("ok"))
    print(f"Published {ok}/{len(results)} approved posts.")
    for r in results:
        if not r.get("ok"):
            print(f"  post {r.get('post_id')} failed: {r.get('error')}", file=sys.stderr)
    return 0


def cmd_run_scheduler(config, db, args) -> int:
    scheduler.start(config, db)
    return 0


def cmd_web(config, db, args) -> int:
    from app import create_app

    app = create_app()
    print("Starting BeriPost web app at http://127.0.0.1:5000  (Ctrl+C to stop)")
    app.run(host="127.0.0.1", port=args.port, debug=False)
    return 0


def main() -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(prog="run.py", description="BeriPost control panel")
    sub = parser.add_subparsers(dest="command", required=True)

    g = sub.add_parser("generate", help="build one post for a pillar")
    g.add_argument("--pillar", required=True,
                   choices=["news", "education", "trivia", "dad_joke"])
    g.add_argument("--dry-run", action="store_true", help="build and print only, post nothing")
    g.set_defaults(func=cmd_generate)

    d = sub.add_parser("dry-run", help="build today's scheduled post and print it (no posting)")
    d.set_defaults(func=cmd_dry_run)

    p = sub.add_parser("publish-queue", help="publish all approved posts")
    p.set_defaults(func=cmd_publish_queue)

    s = sub.add_parser("run-scheduler", help="run the daily scheduler (blocks)")
    s.set_defaults(func=cmd_run_scheduler)

    w = sub.add_parser("web", help="start the local web app")
    w.add_argument("--port", type=int, default=5000)
    w.set_defaults(func=cmd_web)

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
