"""Publish a post (image + caption) to the Careberi Facebook Page.

Uses the Graph API "photo" upload so the image and caption post together.
Requires FB_PAGE_ID and FB_PAGE_ACCESS_TOKEN in .env.
"""
from __future__ import annotations

import logging
from pathlib import Path

import requests

from .config import Config

log = logging.getLogger(__name__)


class PublishError(Exception):
    pass


def publish(config: Config, caption: str, image_path: str | Path | None) -> str:
    """Publish to the page. Returns the new post id.

    If image_path is given, publishes a photo with the caption. Otherwise
    publishes a plain text status update.
    """
    config.require_facebook()
    base = f"https://graph.facebook.com/{config.graph_version}"
    token = config.fb_page_token
    page_id = config.fb_page_id

    if image_path and Path(image_path).exists():
        url = f"{base}/{page_id}/photos"
        with open(image_path, "rb") as fh:
            files = {"source": fh}
            data = {"caption": caption, "access_token": token}
            resp = requests.post(url, files=files, data=data, timeout=60)
        id_field = "post_id"
    else:
        if image_path:
            log.warning("Image %s not found; posting text only.", image_path)
        url = f"{base}/{page_id}/feed"
        data = {"message": caption, "access_token": token}
        resp = requests.post(url, data=data, timeout=60)
        id_field = "id"

    try:
        payload = resp.json()
    except ValueError:
        payload = {}

    if resp.status_code != 200 or "error" in payload:
        error = payload.get("error", {}) or {}
        err = error.get("message", resp.text)
        hint = ""
        if error.get("code") == 200 or "publish_actions" in str(err):
            hint = (
                "\n\nThis almost always means the saved token is a USER token, not a "
                "PAGE token. Fix it in the Setup screen: fill in App ID + App Secret and a "
                "fresh User token, then click 'Make token long-lived' (that produces a Page "
                "token). Or in the Graph API Explorer, under 'User or Page' pick the token "
                "listed beneath 'Page Access Tokens'."
            )
        raise PublishError(f"Facebook rejected the post: {err}{hint}")

    post_id = payload.get(id_field) or payload.get("id") or ""
    log.info("Published to Facebook, post id=%s", post_id)
    return post_id
