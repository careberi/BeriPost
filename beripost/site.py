"""Build the static GitHub Pages gallery into docs/.

Reads published posts from the database, copies their images, and writes a
branded docs/index.html that GitHub Pages serves. Each post has a "Give
feedback" button that opens a pre-filled GitHub issue; the bot folds those in
on its next run.
"""
from __future__ import annotations

import html
import logging
import shutil
import time
from pathlib import Path
from urllib.parse import quote

from .config import Config
from .db import DB

log = logging.getLogger(__name__)

_PAGE = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root{{--navy:#16265C;--ocean:#2A5D9F;--azure:#2F80C2;--sky:#5AA9DE;--berry:#D25680;--page:#EEF2F7;--muted:#6B7280;--line:#E2E8F0;}}
*{{box-sizing:border-box}}body{{margin:0;font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;background:var(--page);color:#1F2733}}
.top{{background:var(--navy);color:#fff;padding:22px 24px;display:flex;align-items:center;gap:14px}}
.top img{{height:52px}}.top .nm{{font-size:26px;font-weight:700;letter-spacing:-.5px}}.top .nm span{{color:var(--sky)}}
.top .tg{{font-size:11px;letter-spacing:2px;text-transform:uppercase;color:#9fb6d6}}
main{{max-width:900px;margin:0 auto;padding:24px}}
.bar{{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:18px}}
.bar h1{{font-size:20px;margin:0;color:var(--navy)}}
.btn{{display:inline-block;background:var(--berry);color:#fff;text-decoration:none;padding:9px 16px;border-radius:9px;font-weight:600;font-size:14px}}
.btn.ghost{{background:#fff;color:var(--navy);border:1px solid var(--line)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:20px}}
.card{{background:#fff;border:1px solid var(--line);border-radius:14px;overflow:hidden;display:flex;flex-direction:column}}
.card img{{width:100%;display:block;aspect-ratio:1/1;object-fit:cover;background:var(--navy)}}
.cb{{padding:16px;display:flex;flex-direction:column;gap:10px}}
.meta{{display:flex;gap:8px;align-items:center;font-size:12px;color:var(--muted)}}
.pill{{padding:2px 9px;border-radius:20px;color:#fff;font-size:11px;text-transform:uppercase}}
.p-news{{background:var(--ocean)}}.p-education{{background:var(--navy)}}.p-trivia{{background:var(--azure)}}.p-dad_joke{{background:var(--sky);color:var(--navy)}}
.body{{white-space:pre-wrap;font-size:14px;line-height:1.55;margin:0}}
.actions{{display:flex;gap:10px;flex-wrap:wrap;margin-top:4px}}
.actions a{{font-size:13px;text-decoration:none;font-weight:600}}
.fb{{color:var(--azure)}}.fbk{{color:var(--berry)}}
.empty{{color:var(--muted);font-style:italic}}
footer{{text-align:center;color:var(--muted);font-size:12px;padding:30px}}
</style></head><body>
<div class="top">{logo}<div><div class="nm">care<span>beri</span></div><div class="tg">Home Health &amp; Home Care</div></div></div>
<main>
  <div class="bar"><h1>Posts by BeriPost</h1>{feedback_all}</div>
  {content}
</main>
<footer>Updated {updated}. Generated automatically by BeriPost.</footer>
</body></html>
"""


def _issue_url(repo: str, title: str, body: str) -> str:
    return f"https://github.com/{repo}/issues/new?title={quote(title)}&body={quote(body)}"


def _card(config: Config, repo: str | None, post: dict, img_rel: str | None) -> str:
    pillar = post.get("pillar", "")
    date = time.strftime("%b %d, %Y", time.localtime(post.get("created_at") or time.time()))
    body = html.escape(post.get("body", ""))
    img = f'<img src="{img_rel}" alt="post image">' if img_rel else ""
    actions = []
    if repo:
        url = _issue_url(
            repo,
            f"Feedback on post #{post['id']} ({pillar})",
            f"Post: {pillar} from {date}\n\nMy feedback (replace this line):\n",
        )
        actions.append(f'<a class="fbk" href="{url}" target="_blank">Give feedback</a>')
    if post.get("fb_post_id"):
        actions.append(f'<a class="fb" href="https://www.facebook.com/{post["fb_post_id"]}" target="_blank">View on Facebook</a>')
    actions_html = f'<div class="actions">{"".join(actions)}</div>' if actions else ""
    return (
        f'<article class="card">{img}<div class="cb">'
        f'<div class="meta"><span class="pill p-{pillar}">{pillar}</span><span>{date}</span></div>'
        f'<p class="body">{body}</p>{actions_html}</div></article>'
    )


def build(config: Config, db: DB) -> Path:
    docs = config.root / "docs"
    imgdir = docs / "images"
    imgdir.mkdir(parents=True, exist_ok=True)

    repo = config.site.get("repo")
    posts = db.list_posts("published")

    # Logo in the header.
    logo_html = ""
    if config.logo_path.exists():
        shutil.copyfile(config.logo_path, imgdir / "logo.png")
        logo_html = '<img src="images/logo.png" alt="careberi">'

    cards = []
    for post in posts:
        img_rel = None
        if post.get("image_path") and Path(post["image_path"]).exists():
            shutil.copyfile(post["image_path"], imgdir / f"{post['id']}.png")
            img_rel = f"images/{post['id']}.png"
        cards.append(_card(config, repo, post, img_rel))

    content = f'<div class="grid">{"".join(cards)}</div>' if cards else \
        '<p class="empty">No posts yet. They will appear here after BeriPost runs.</p>'

    feedback_all = ""
    if repo:
        url = _issue_url(repo, "Feedback for BeriPost",
                         "General feedback on how the posts should sound or look:\n")
        feedback_all = f'<a class="btn" href="{url}" target="_blank">Give feedback</a>'

    page = _PAGE.format(
        title=config.site.get("title", "Careberi posts"),
        logo=logo_html,
        feedback_all=feedback_all,
        content=content,
        updated=time.strftime("%b %d, %Y %I:%M %p"),
    )
    out = docs / "index.html"
    out.write_text(page, encoding="utf-8")
    log.info("Built gallery with %d post(s) at %s", len(posts), out)
    return out
