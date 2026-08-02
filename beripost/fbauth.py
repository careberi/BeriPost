"""Turn a short-lived Facebook token into a long-lived (roughly 60-day) Page
token, so the bot keeps posting without you re-doing the token each hour.

The Setup screen calls make_long_lived_page_token() for you. It needs your App
ID and App Secret (App Dashboard -> App settings -> Basic) plus a short-lived
USER token (in the Graph API Explorer, set "User or Page" to your own name).
"""
from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)

_GRAPH = "https://graph.facebook.com"


def _error_message(data: dict) -> str:
    return (data.get("error", {}) or {}).get("message", "Unknown Facebook error")


def make_long_lived_page_token(app_id: str, app_secret: str, token: str,
                               page_id: str, version: str = "v25.0") -> str:
    """Return a long-lived Page access token, or raise RuntimeError with a hint."""
    base = f"{_GRAPH}/{version}"

    # 1. Extend the short-lived token into a long-lived user token.
    resp = requests.get(
        f"{base}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": token,
        },
        timeout=30,
    )
    data = resp.json() if resp.content else {}
    if "error" in data:
        raise RuntimeError(
            _error_message(data)
            + "\n\nTip: paste a USER access token (in the Explorer set 'User or Page' "
            "to your own name), and double-check the App ID and App Secret."
        )
    long_token = data.get("access_token")
    if not long_token:
        raise RuntimeError("Facebook did not return an extended token. Check the App ID and App Secret.")

    # 2. Use the long-lived user token to read the Page's own (non-expiring) token.
    resp2 = requests.get(
        f"{base}/{page_id}",
        params={"fields": "access_token", "access_token": long_token},
        timeout=30,
    )
    d2 = resp2.json() if resp2.content else {}
    page_token = d2.get("access_token")
    if page_token:
        return page_token

    # Fallback: some inputs already resolve to a usable long-lived token.
    if "error" in d2:
        log.warning("Could not read page token via /%s: %s", page_id, _error_message(d2))
    return long_token
