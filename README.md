# BeriPost

A hands-off Facebook content engine for **Careberi**. On a schedule it writes an
original, on-brand post, builds a branded card image, posts it to your Facebook
Page, emails you a copy, and updates a web gallery you can browse anytime. You
never have to approve anything. You can steer it with plain-English feedback,
which it remembers and applies to future posts.

> **New to all this?** Follow the steps top to bottom. Every command is
> copy-paste. You do not need to understand the code.

---

## Easiest way to use it: the desktop app

Double-click **`Start BeriPost.bat`** in the project folder. A window opens with buttons:

- **Preview (no posting)** - builds a post and shows the image + caption. Nothing is posted.
- **Post now** - publishes the chosen post to your Facebook Page (asks you to confirm first).
- **Give feedback** - type a note; future posts follow it.
- **Tidy feedback** - clean up your feedback notes.
- **Open web gallery** - see everything it has posted.

Pick the post type from the dropdown (or "Today's scheduled post"). No commands needed.

- **Put it on your desktop:** right-click `Start BeriPost.bat` -> Show more options -> Send to -> Desktop (create shortcut).
- **Using PyCharm:** open the project, set the interpreter to the project's `.venv`, then run `gui.py`.

The commands further below still work if you ever want them, but the app covers everyday use. The automatic daily posting (Windows Task Scheduler, section 8 wording below) runs on its own regardless.

## How it works

Every run, automatically:

1. Folds in any new **feedback** you have given.
2. Writes the day's post (rotating across the content pillars below).
3. Builds the **branded card image** (your logo, colors, and Poppins font).
4. **Posts it to your Facebook Page.**
5. **Emails you a copy.**
6. Adds it to your **web gallery** and pushes it to GitHub, so the gallery updates.

Content pillars (set the weekly plan in `config.yaml`):

- **News commentary** - original, family-focused take on a recent home care / senior care / disability news article, with a link.
- **Family education** - reassuring tips on what good care looks like, questions to ask, what to expect. No fear, no knocking competitors.
- **Trivia** - light care/health/wellness facts.
- **Dad jokes** - clean, warm, apolitical.

Where things live:

```
BeriPost/
├─ run.py                # the command line
├─ config.yaml           # all settings (schedule, brand, feeds, site) - no secrets
├─ brand_voice.md        # how the posts should sound (edit freely)
├─ feedback.md           # your feedback memory (auto-updated; you can edit too)
├─ .env                  # your secrets (you create this; never shared)
├─ beripost/             # the engine (news, writer, images, publisher, email, site, feedback)
├─ assets/               # your logo (assets/logo/logo.png) and Poppins fonts
├─ docs/                 # the web gallery that GitHub Pages serves
└─ data/                 # local database (created at runtime)
```

---

## 1. One-time setup

### 1a. Python and libraries
Python 3.11+ is required. It is likely already installed. To set up the project
workspace and libraries (once):

```bash
python -m venv .venv
```
Activate it, then install:
- Windows PowerShell: `.\.venv\Scripts\Activate.ps1`
- Mac/Linux: `source .venv/bin/activate`

```bash
pip install -r requirements.txt
```

> On Windows you can also skip activating and just run commands with
> `.\.venv\Scripts\python.exe run.py ...`

### 1b. Secrets
Copy `.env.example` to `.env` and fill in the values you have. Minimum to write
posts is the Anthropic key. Facebook and email are needed to post and notify.

```bash
Copy-Item .env.example .env    # Windows  (Mac/Linux: cp .env.example .env)
notepad .env
```

- `ANTHROPIC_API_KEY` - from <https://console.anthropic.com/> (Settings -> API Keys).
- `FB_PAGE_ID`, `FB_PAGE_ACCESS_TOKEN` - see section 4.
- `SMTP_*` and `NOTIFY_TO` - see section 5 (email copies).

### 1c. Your brand
- Logo is already generated at `assets/logo/logo.png` (from your brand vectors). Replace it with an official file anytime.
- Poppins fonts are installed in `assets/fonts/`.
- Set your real **phone** and **website** in `config.yaml` under `brand:`.

### 1d. Try it (nothing is posted)
```bash
python run.py dry-run
```
This writes today's post and prints it, and saves the image to `generated_images/`. It does not post, email, or push. Try a specific type: `python run.py dry-run --pillar education`.

---

## 2. Posting

Post today's scheduled pillar right now:
```bash
python run.py run-today
```
Or a specific one:
```bash
python run.py post --pillar news
```

Each of these does the full cycle: write -> image -> post to Facebook -> email you -> update the gallery -> push to GitHub.

---

## 3. Make it fully automatic (Windows Task Scheduler)

So it runs on its own whenever your PC is on:

1. Press Start, type **Task Scheduler**, open it.
2. Click **Create Basic Task**. Name it "BeriPost". Next.
3. Trigger: **Daily**, pick a start time (e.g. 9:30 AM). Next.
4. Action: **Start a program**.
   - Program/script:
     `C:\Users\neil\Desktop\BeriPost\.venv\Scripts\python.exe`
   - Add arguments: `run.py run-today`
   - Start in: `C:\Users\neil\Desktop\BeriPost`
5. Finish.

It will now build and post the scheduled pillar each day. Days with no pillar in
`config.yaml` are simply skipped. (It only runs while your PC is on.)

> Alternative: run `python run.py run-scheduler` in a window and leave it open.

---

## 4. Getting a Facebook Page access token (step by step)

Needed to post. About 15 minutes the first time.

1. Go to <https://developers.facebook.com/>, log in with the account that manages the Careberi Page, and finish developer registration if asked.
2. **My Apps -> Create App -> Business.** Name it (e.g. "Careberi Poster") and create it.
3. Open **Tools -> Graph API Explorer**. Select your app top-right. Click **Add a Permission** and add `pages_show_list`, `pages_read_engagement`, and `pages_manage_posts`. Click **Generate Access Token** and approve the Careberi Page.
4. In the Explorer, query `me/accounts`. Find the Careberi Page: its `id` is your **`FB_PAGE_ID`**, and the `access_token` beside it is a Page token.
5. Make it long-lived (about 60 days): under **App Settings -> Basic** get your App ID and App Secret, then visit
   `https://graph.facebook.com/v25.0/oauth/access_token?grant_type=fb_exchange_token&client_id=APP_ID&client_secret=APP_SECRET&fb_exchange_token=SHORT_LIVED_TOKEN`
   and query `me/accounts` again with the result to get a long-lived Page token.
6. Put `FB_PAGE_ID` and `FB_PAGE_ACCESS_TOKEN` into `.env`.

If posting later fails with an auth error, the token expired - redo steps 3-5. (A Meta "System User" token can be made non-expiring for a fully hands-off setup.)

---

## 5. Email copies (SMTP)

To get an email after each post, fill the `SMTP_*` and `NOTIFY_TO` values in `.env`.

Easiest with Gmail:
1. Turn on 2-Step Verification on the Google account.
2. Create an **App Password** (Google Account -> Security -> App passwords).
3. In `.env`: `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USER=you@gmail.com`, `SMTP_PASS=` the app password, `NOTIFY_TO=` where you want the copy sent.

If these are blank, posting still works, it just skips the email.

---

## 6. The web gallery (GitHub Pages)

Your posts show up on a web page at `https://careberi.github.io/BeriPost/`. To turn it on once:

1. On GitHub, open the `careberi/BeriPost` repo -> **Settings** -> **Pages**.
2. Under "Build and deployment", set **Source: Deploy from a branch**, **Branch: `main`**, **Folder: `/docs`**. Save.

After that, every post the engine pushes updates the page automatically. `config.yaml` already points `site.repo` at `careberi/BeriPost`.

---

## 7. Giving feedback (the bot remembers it)

Steer the writing anytime. Three ways, all remembered and applied to future posts:

- **Command:** `python run.py feedback "keep posts under 100 words and warmer"`
- **Edit:** open `feedback.md` and type notes.
- **Web:** click **Give feedback** on the gallery. It opens a pre-filled GitHub issue; the bot folds new issues in on its next run.

Tidy the notes into a clean list anytime: `python run.py tidy-feedback`.

The big-picture voice lives in `brand_voice.md`; day-to-day tweaks go through feedback.

---

## Command reference

| Command | What it does |
| --- | --- |
| `python run.py run-today` | Build + post today's scheduled pillar (the automatic one). |
| `python run.py post --pillar news` | Build + post one specific pillar now. |
| `python run.py dry-run` | Build a post and print it. Posts nothing. |
| `python run.py feedback "..."` | Add feedback the bot applies going forward. |
| `python run.py tidy-feedback` | Consolidate feedback notes. |
| `python run.py build-site` | Rebuild the web gallery from history. |
| `python run.py run-scheduler` | Keep running and post daily (alternative to Task Scheduler). |

---

## Customizing

- **Voice:** `brand_voice.md`. **Day-to-day tweaks:** feedback (section 7).
- **Schedule / posting time / timezone:** `posting:` in `config.yaml`.
- **RSS feeds:** `sources.feeds` in `config.yaml`, one URL per line.
- **Phone / website / colors / tagline:** `brand:` in `config.yaml`.
- **Turn images off:** `images.enabled: false` for text-only posts.
- **Models:** `claude-sonnet-5` writes, `claude-haiku-4-5` filters/tidies. Change in `config.yaml`.

## Troubleshooting

- **"ANTHROPIC_API_KEY is not set"** - create `.env` and add your key (1b).
- **"Facebook is not configured"** - add `FB_PAGE_ID` and `FB_PAGE_ACCESS_TOKEN` (section 4).
- **"Facebook rejected the post"** - usually an expired token; redo section 4 steps 3-5.
- **No email** - fill the `SMTP_*` values (section 5); check they are correct.
- **Gallery not updating** - make sure GitHub Pages is enabled (section 6) and that `git push` works from the project folder.
- **No news post** - the feeds had nothing new and on-brand; it will try next time, or add feeds.
