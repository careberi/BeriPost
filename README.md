# BeriPost

An autonomous Facebook content engine for **Careberi**. It sources home care and
disability care news, writes original commentary in the Careberi brand voice,
mixes in light trivia and dad jokes, builds an on-brand image for each post, and
publishes to your Facebook Page a few times a week. You review everything from a
simple local web page before anything goes live.

> **New to all this?** That's fine. Follow the steps top to bottom. Every command
> is copy-paste. You do not need to understand the code.

---

## What it does

Four kinds of posts ("pillars"), rotated across the week:

1. **News commentary** — pulls recent articles from trusted RSS feeds and writes
   original, family-focused commentary (never copies the article), with a link.
2. **Family education** — evergreen, reassuring posts about what good home care
   looks like, questions to ask, what to expect. No fear, no knocking competitors.
3. **Trivia** — light care/health/wellness/positivity trivia.
4. **Dad jokes** — clean, warm, apolitical.

Two modes:

- **review** (default) — posts are generated into a local queue for you to
  approve or edit first. **Nothing goes to Facebook without your click.**
- **auto** — approved cadence posts publish automatically on schedule.

Start in **review** for a couple of weeks, then flip to **auto** when you trust it.

---

## 1. One-time setup

### 1a. Install Python
Install **Python 3.11 or newer** from <https://www.python.org/downloads/>.
On Windows, tick **"Add Python to PATH"** in the installer.

Check it worked (open PowerShell / Terminal):
```bash
python --version
```

### 1b. Get the project and install dependencies
In the `BeriPost` folder, create a private workspace and install the libraries:
```bash
python -m venv .venv
```
Activate it:
- Windows (PowerShell): `.\.venv\Scripts\Activate.ps1`
- Mac/Linux: `source .venv/bin/activate`

Then:
```bash
pip install -r requirements.txt
```

### 1c. Create your secrets file
Copy `.env.example` to a new file named `.env`, then open `.env` and fill in the
values. You need at minimum your Anthropic key to generate posts; Facebook keys
are only needed to actually publish.

```bash
# Windows PowerShell
Copy-Item .env.example .env
# Mac/Linux
cp .env.example .env
```

- `ANTHROPIC_API_KEY` — from <https://console.anthropic.com/> → Settings → API Keys.
- `FB_PAGE_ID`, `FB_PAGE_ACCESS_TOKEN` — see section 4 below.

### 1d. Add your brand assets
- Put background photos in `assets/backgrounds/` (see the README in that folder).
- Put your logo at `assets/logo/logo.png`.

Both are optional to start — BeriPost falls back to a plain brand-color image.

### 1e. Set your phone number and website
Open `config.yaml` and set your real **phone** and **website** under `brand:`.
These appear in the "call us" call-to-action at the end of posts.

---

## 2. Try it out (nothing gets posted)

Generate one post and just print it to the screen:
```bash
python run.py generate --pillar education --dry-run
```
Try the others too: `--pillar news`, `--pillar trivia`, `--pillar dad_joke`.
The composed image is saved in `generated_images/` so you can open and look at it.

---

## 3. Use the web app (the main way to run it)

```bash
python run.py web
```
Then open **http://127.0.0.1:5000** in your browser. From there you can:

- **Generate** a post for any pillar with one click.
- **Edit** the headline and caption inline.
- **Approve** or **Reject** each post.
- **Publish now** an approved post, or **Publish all approved** at once.

In **review** mode, generated posts wait under "Pending review" until you approve
them. Keep the terminal window open while you use the app; press **Ctrl+C** to stop.

---

## 4. Getting a Facebook Page access token (step by step)

You only need this to publish. It takes about 15 minutes the first time.

1. **Become a Meta developer.** Go to <https://developers.facebook.com/>, log in
   with the Facebook account that manages the Careberi Page, and complete the
   developer registration if prompted.
2. **Create an app.** Click **My Apps → Create App**. Choose the **Business**
   type. Give it a name (e.g. "Careberi Poster") and create it.
3. **Add the Pages permissions.** In your app, open **Tools → Graph API Explorer**
   (or add the "Facebook Login for Business" product). In the Graph API Explorer:
   - Select your app in the top-right dropdown.
   - Click **Add a Permission** and add: `pages_show_list`,
     `pages_read_engagement`, and `pages_manage_posts`.
   - Click **Generate Access Token** and approve the Careberi Page when asked.
     This gives you a short-lived **user** token.
4. **Find your Page ID.** With the token from step 3, in the Graph API Explorer
   query `me/accounts`. Find the Careberi Page in the results — its `id` is your
   **`FB_PAGE_ID`**, and the `access_token` next to it is a **Page** token
   (short-lived).
5. **Make the Page token long-lived (recommended).** Short-lived tokens expire in
   about an hour. To get a long-lived (about 60-day) Page token:
   - Exchange the user token for a long-lived user token:
     `https://graph.facebook.com/v25.0/oauth/access_token?grant_type=fb_exchange_token&client_id=YOUR_APP_ID&client_secret=YOUR_APP_SECRET&fb_exchange_token=SHORT_LIVED_USER_TOKEN`
     (App ID and App Secret are under **App Settings → Basic**.)
   - Then query `me/accounts` again with that long-lived user token — the Page
     `access_token` it returns is a **long-lived Page token**.
6. **Put them in `.env`:**
   ```
   FB_PAGE_ID=your_page_id_from_step_4
   FB_PAGE_ACCESS_TOKEN=your_long_lived_page_token_from_step_5
   ```

> Tokens still expire eventually. If publishing starts failing with an auth
> error, repeat steps 3–5 to get a fresh token. (A "System User" token in
> Meta Business Settings can be made non-expiring for a fully hands-off setup.)

Test publishing safely: generate a post in the web app, approve it, and click
**Publish now**.

---

## 5. Run it on a schedule

BeriPost can build the right pillar for each day automatically (see the weekly
plan under `posting.schedule` in `config.yaml`):
```bash
python run.py run-scheduler
```
Leave that running (or set it up as a scheduled task / cron job). In **review**
mode it drops each day's post into the queue for you; in **auto** mode it
publishes automatically.

Publish everything you approved, from the command line:
```bash
python run.py publish-queue
```

---

## 6. Customizing

- **Brand voice** — edit `brand_voice.md`. Plain English. The writer reads it
  every time. This is the single biggest lever on how posts sound.
- **Add / remove RSS feeds** — edit the `sources.feeds` list in `config.yaml`,
  one URL per line. Any standard RSS/Atom feed works.
- **Call to action, phone, website, colors** — the `brand:` section of `config.yaml`.
- **Weekly schedule & posting time** — the `posting:` section of `config.yaml`.
- **Switch review ↔ auto** — set `mode:` at the top of `config.yaml`.
- **Images** — drop new backgrounds in `assets/backgrounds/`. Sizes/colors are in
  the `images:` and `brand.colors:` sections. An AI-image hook is stubbed in
  `beripost/images.py` for later.

---

## Command reference

| Command | What it does |
| --- | --- |
| `python run.py web` | Start the local web app (main interface). |
| `python run.py generate --pillar news` | Build one post, route it by mode. |
| `python run.py generate --pillar trivia --dry-run` | Build + print, post nothing. |
| `python run.py dry-run` | Build today's scheduled post and print it. |
| `python run.py publish-queue` | Publish all approved posts. |
| `python run.py run-scheduler` | Run the daily scheduler (keeps running). |

---

## How it is built

```
BeriPost/
├─ run.py                # command line entry point
├─ app.py                # Flask web app (review/approve/publish)
├─ config.yaml           # all settings (no secrets)
├─ brand_voice.md        # editable voice the writer loads every time
├─ .env                  # your secrets (you create this; git-ignored)
├─ beripost/
│  ├─ config.py          # loads config.yaml + .env
│  ├─ db.py              # SQLite: dedup + the post queue
│  ├─ llm.py             # Claude API wrapper
│  ├─ sources.py         # RSS fetch + dedup + safety classifier
│  ├─ writer.py          # news & education posts
│  ├─ light_content.py   # trivia & dad jokes (with anti-repeat)
│  ├─ images.py          # Pillow image composition (+ AI hook)
│  ├─ publisher.py       # Facebook Graph API publishing
│  ├─ pipeline.py        # orchestrates build → route → publish
│  └─ scheduler.py       # daily cadence
├─ templates/ , static/  # web app UI
├─ assets/               # backgrounds, logo, fonts (you add these)
└─ data/                 # SQLite database (created at runtime)
```

- **Models:** `claude-sonnet-5` writes the posts; `claude-haiku-4-5` does cheap
  classification/dedup. Change these in `config.yaml`.
- **Error handling:** a failed post is logged and skipped; it never crashes a run.
- **Nothing is posted twice:** articles and light content are de-duplicated in SQLite.

---

## Troubleshooting

- **"ANTHROPIC_API_KEY is not set"** — you have not created `.env` or the key is
  blank. See step 1c.
- **"Facebook is not configured"** — add `FB_PAGE_ID` and `FB_PAGE_ACCESS_TOKEN`
  to `.env` (section 4).
- **"Facebook rejected the post"** — usually an expired token; redo section 4,
  steps 3–5.
- **No news posts generated** — the feeds had nothing new and on-brand, or the
  safety filter skipped them. Try again later or add more feeds.
- **Plain-color images** — add photos to `assets/backgrounds/` and a
  `logo.png` to `assets/logo/`.
