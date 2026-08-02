"""BeriPost local web app.

A one-page control panel to review, edit, approve, and publish posts, and to
generate new ones on demand. Runs locally at http://127.0.0.1:5000.

Start it with:  python run.py web    (or:  python app.py)
"""
from __future__ import annotations

import datetime as _dt
import logging
from pathlib import Path

from flask import (
    Flask, abort, flash, redirect, render_template, request, send_file, url_for,
)

from beripost.config import get_config
from beripost.db import DB
from beripost import pipeline

log = logging.getLogger(__name__)


def create_app() -> Flask:
    config = get_config()
    db = DB(config.db_path)

    app = Flask(__name__)
    app.secret_key = config.flask_secret

    def _fmt(ts):
        if not ts:
            return ""
        return _dt.datetime.fromtimestamp(ts).strftime("%b %d, %I:%M %p")

    app.jinja_env.filters["fmt_time"] = _fmt

    @app.route("/")
    def index():
        return render_template(
            "queue.html",
            mode=config.mode,
            brand=config.brand,
            pending=db.list_posts("pending"),
            approved=db.list_posts("approved"),
            published=db.list_posts("published"),
            failed=db.list_posts("failed"),
            pillars=pipeline.PILLARS,
            fb_ready=bool(config.fb_page_id and config.fb_page_token),
        )

    @app.route("/generate", methods=["POST"])
    def generate():
        pillar = request.form.get("pillar", "education")
        result = pipeline.generate(config, db, pillar, dry_run=False)
        if result.get("ok"):
            if config.mode == "auto" and result.get("status") == "published":
                flash(f"Generated and published a {pillar} post.", "ok")
            elif result.get("status") == "failed":
                flash(f"Generated a {pillar} post but publishing failed: {result.get('error')}", "err")
            else:
                flash(f"Generated a {pillar} post. Review it below.", "ok")
        else:
            flash(f"Could not generate {pillar} post: {result.get('error')}", "err")
        return redirect(url_for("index"))

    @app.route("/post/<int:post_id>/edit", methods=["POST"])
    def edit(post_id: int):
        if not db.get_post(post_id):
            abort(404)
        db.update_post(
            post_id,
            headline=request.form.get("headline", "").strip(),
            body=request.form.get("body", "").strip(),
        )
        flash("Saved your edits.", "ok")
        return redirect(url_for("index"))

    @app.route("/post/<int:post_id>/approve", methods=["POST"])
    def approve(post_id: int):
        if not db.get_post(post_id):
            abort(404)
        db.update_post(post_id, status="approved")
        flash("Approved. Publish it now, or run 'publish-queue' later.", "ok")
        return redirect(url_for("index"))

    @app.route("/post/<int:post_id>/reject", methods=["POST"])
    def reject(post_id: int):
        if not db.get_post(post_id):
            abort(404)
        db.update_post(post_id, status="rejected")
        flash("Rejected. It will not be posted.", "ok")
        return redirect(url_for("index"))

    @app.route("/post/<int:post_id>/publish", methods=["POST"])
    def publish_one(post_id: int):
        if not db.get_post(post_id):
            abort(404)
        if not (config.fb_page_id and config.fb_page_token):
            flash("Facebook is not configured. Add FB_PAGE_ID and FB_PAGE_ACCESS_TOKEN to .env.", "err")
            return redirect(url_for("index"))
        res = pipeline.publish_saved(config, db, post_id)
        if res.get("ok"):
            flash("Published to Facebook.", "ok")
        else:
            flash(f"Publishing failed: {res.get('error')}", "err")
        return redirect(url_for("index"))

    @app.route("/publish-approved", methods=["POST"])
    def publish_approved():
        if not (config.fb_page_id and config.fb_page_token):
            flash("Facebook is not configured yet.", "err")
            return redirect(url_for("index"))
        results = pipeline.publish_approved(config, db)
        ok = sum(1 for r in results if r.get("ok"))
        flash(f"Published {ok}/{len(results)} approved posts.", "ok" if ok == len(results) else "err")
        return redirect(url_for("index"))

    @app.route("/image/<int:post_id>")
    def image(post_id: int):
        post = db.get_post(post_id)
        if not post or not post.get("image_path"):
            abort(404)
        path = Path(post["image_path"])
        if not path.exists():
            abort(404)
        return send_file(path)

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    create_app().run(host="127.0.0.1", port=5000, debug=False)
