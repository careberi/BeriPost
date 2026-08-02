"""BeriPost desktop app.

Two tabs:
  - Create posts: Preview / Post now / Give feedback / Tidy feedback / Open gallery,
    with a live image + caption preview.
  - Setup: enter your Claude key, Facebook details, email, and business info into
    boxes; it saves them to .env and config.yaml for you.

Launch by double-clicking "Start BeriPost.bat", or run this file from PyCharm
with the project's .venv interpreter.
"""
from __future__ import annotations

import logging
import queue
import threading
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog, ttk

from beripost import config as config_module
from beripost import fbauth, feedback, llm, pipeline, settings_io, site
from beripost.config import get_config
from beripost.db import DB

try:
    from PIL import Image, ImageTk
except Exception:  # noqa: BLE001
    Image = ImageTk = None

NAVY = "#16265C"
BERRY = "#D25680"
PAGE = "#EEF2F7"
CLOUD = "#F4F8FC"

PILLARS = [
    ("Today's scheduled post", None),
    ("News commentary", "news"),
    ("Family education", "education"),
    ("Trivia", "trivia"),
    ("Dad joke", "dad_joke"),
]

# (env key, label, is_secret)
ENV_FIELDS_CLAUDE = [("ANTHROPIC_API_KEY", "Claude API key", True)]
ENV_FIELDS_FB = [
    ("FB_PAGE_ID", "Facebook Page ID", False),
    ("FB_PAGE_ACCESS_TOKEN", "Facebook Page token", True),
    ("FB_APP_ID", "Facebook App ID", False),
    ("FB_APP_SECRET", "Facebook App Secret", True),
    ("GRAPH_API_VERSION", "Graph API version", False),
]
ENV_FIELDS_EMAIL = [
    ("SMTP_HOST", "SMTP host", False),
    ("SMTP_PORT", "SMTP port", False),
    ("SMTP_USER", "SMTP user (email)", False),
    ("SMTP_PASS", "SMTP password", True),
    ("NOTIFY_TO", "Send copies to", False),
]
ENV_FIELDS_GITHUB = [("GITHUB_TOKEN", "GitHub token (optional)", True)]
ALL_ENV_FIELDS = ENV_FIELDS_CLAUDE + ENV_FIELDS_FB + ENV_FIELDS_EMAIL + ENV_FIELDS_GITHUB

# (config.yaml scalar key, label, how-to-read-current-value)
CFG_FIELDS = [
    ("phone", "Phone number"),
    ("website", "Website"),
    ("tagline", "Tagline"),
    ("service_area", "Service area (SEO)"),
]


class _QueueHandler(logging.Handler):
    def __init__(self, q: queue.Queue):
        super().__init__()
        self.q = q

    def emit(self, record):
        self.q.put(self.format(record))


class ScrollFrame(tk.Frame):
    """A vertically scrollable frame (for the Setup form)."""

    def __init__(self, parent, bg=PAGE):
        super().__init__(parent, bg=bg)
        canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        vsb = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner = tk.Frame(canvas, bg=bg)
        self.inner.bind("<Configure>",
                        lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.inner, anchor="nw")
        canvas.configure(yscrollcommand=vsb.set)
        canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        def _wheel(event):
            canvas.yview_scroll(int(-event.delta / 120), "units")
        canvas.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _wheel))
        canvas.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.config = get_config()
        self.db = DB(self.config.db_path)
        self.log_q: queue.Queue = queue.Queue()
        self._busy = False
        self._preview_img = None
        self.vars: dict[str, tk.StringVar] = {}
        self._secret_entries: list[tk.Entry] = []

        root.title("BeriPost - Careberi")
        root.geometry("1040x740")
        root.configure(bg=PAGE)

        handler = _QueueHandler(self.log_q)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

        self._build()
        self.root.after(150, self._drain)
        self._refresh_status()
        self._log("Ready. If a button says a key is missing, open the Setup tab.")

    # --- layout -------------------------------------------------------------
    def _build(self):
        header = tk.Frame(self.root, bg=NAVY)
        header.pack(fill="x")
        tk.Label(header, text="BeriPost", bg=NAVY, fg="white",
                 font=("Segoe UI", 20, "bold")).pack(side="left", padx=18, pady=12)
        tk.Label(header, text="Careberi   Home Health & Home Care", bg=NAVY, fg="#9fb6d6",
                 font=("Segoe UI", 10)).pack(side="left", pady=12)

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True)
        self.tab_posts = tk.Frame(self.nb, bg=PAGE)
        self.tab_setup = ScrollFrame(self.nb, bg=PAGE)
        self.nb.add(self.tab_posts, text="  Create posts  ")
        self.nb.add(self.tab_setup, text="  Setup  ")

        self._build_posts(self.tab_posts)
        self._build_setup(self.tab_setup.inner)

        self.status = tk.Label(self.root, text="", bg="#dfe6ee", anchor="w", padx=10)
        self.status.pack(fill="x")

    def _build_posts(self, parent):
        controls = tk.Frame(parent, bg=PAGE)
        controls.pack(fill="x", padx=16, pady=12)
        tk.Label(controls, text="Post type:", bg=PAGE).pack(side="left")
        self.pillar = ttk.Combobox(controls, values=[p[0] for p in PILLARS],
                                   state="readonly", width=22)
        self.pillar.current(0)
        self.pillar.pack(side="left", padx=(6, 14))
        self.btn_preview = tk.Button(controls, text="Preview (no posting)", command=self.on_preview)
        self.btn_preview.pack(side="left", padx=4)
        self.btn_post = tk.Button(controls, text="Post now", bg=BERRY, fg="white",
                                  activebackground="#b8446b", command=self.on_post)
        self.btn_post.pack(side="left", padx=4)
        tk.Button(controls, text="Give feedback", command=self.on_feedback).pack(side="left", padx=4)
        tk.Button(controls, text="Tidy feedback", command=self.on_tidy).pack(side="left", padx=4)
        tk.Button(controls, text="Open web gallery", command=self.on_gallery).pack(side="left", padx=4)

        body = tk.Frame(parent, bg=PAGE)
        body.pack(fill="both", expand=True, padx=16, pady=(0, 12))
        left = tk.Frame(body, bg=PAGE)
        left.pack(side="left", fill="both", expand=True)
        tk.Label(left, text="Preview", bg=PAGE, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.img_label = tk.Label(left, bg=CLOUD, text="(the post image appears here)")
        self.img_label.pack(anchor="w", pady=(2, 6))
        tk.Label(left, text="Caption", bg=PAGE, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.caption = tk.Text(left, height=8, wrap="word")
        self.caption.pack(fill="both", expand=True)

        right = tk.Frame(body, bg=PAGE)
        right.pack(side="right", fill="both", expand=True, padx=(14, 0))
        tk.Label(right, text="Activity", bg=PAGE, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.logbox = scrolledtext.ScrolledText(right, wrap="word", state="disabled", width=48)
        self.logbox.pack(fill="both", expand=True)

    def _build_setup(self, parent):
        pad = {"padx": 18}
        tk.Label(parent, text="Set up BeriPost", bg=PAGE, fg=NAVY,
                 font=("Segoe UI", 15, "bold")).pack(anchor="w", pady=(14, 2), **pad)
        tk.Label(parent, text="Fill in the boxes and click Save. Your entries are stored on this "
                              "PC only (never uploaded).", bg=PAGE, fg="#4B5563",
                 wraplength=900, justify="left").pack(anchor="w", **pad)

        self.setup_status = tk.Label(parent, text="", bg="#e8eef6", fg=NAVY, anchor="w",
                                     font=("Segoe UI", 10, "bold"))
        self.setup_status.pack(fill="x", padx=18, pady=10)

        self._section(parent, "1. Claude (Anthropic) - required to write posts")
        self._help(parent, "Get a free key at console.anthropic.com (Settings -> API Keys)",
                   "https://console.anthropic.com/settings/keys")
        self._fields(parent, ENV_FIELDS_CLAUDE)

        self._section(parent, "2. Facebook - required to post")
        self._help(parent, "How to get a Page ID and token: see README section 5 "
                           "(opens developers.facebook.com)", "https://developers.facebook.com/tools/explorer/")
        self._fields(parent, ENV_FIELDS_FB)
        tk.Label(parent, text="The Explorer token expires in ~1 hour. To make it permanent: paste a "
                              "USER token above (in the Explorer set 'User or Page' to your own name), "
                              "add your App ID + App Secret, then click:", bg=PAGE, fg="#4B5563",
                 wraplength=900, justify="left").pack(anchor="w", padx=18, pady=(4, 2))
        tk.Button(parent, text="Make token long-lived", command=self.on_make_long_lived
                  ).pack(anchor="w", padx=18)

        self._section(parent, "3. Email copies (optional)")
        self._help(parent, "Gmail: turn on 2-Step Verification, then create an App Password.",
                   "https://myaccount.google.com/apppasswords")
        self._fields(parent, ENV_FIELDS_EMAIL)

        self._section(parent, "4. GitHub token (optional - only for private repos / auto-closing feedback)")
        self._fields(parent, ENV_FIELDS_GITHUB)

        self._section(parent, "5. Your business details")
        self._cfg_fields(parent)

        show_row = tk.Frame(parent, bg=PAGE)
        show_row.pack(anchor="w", padx=18, pady=(12, 2))
        self.show_secrets = tk.IntVar(value=0)
        tk.Checkbutton(show_row, text="Show hidden values", bg=PAGE, variable=self.show_secrets,
                       command=self._toggle_secrets).pack(side="left")

        btns = tk.Frame(parent, bg=PAGE)
        btns.pack(anchor="w", padx=18, pady=(4, 24))
        tk.Button(btns, text="Save all settings", bg=BERRY, fg="white",
                  activebackground="#b8446b", font=("Segoe UI", 10, "bold"),
                  command=self.on_save_settings).pack(side="left")
        tk.Button(btns, text="Open full setup guide (README)",
                  command=self.on_open_readme).pack(side="left", padx=10)

        self._load_settings_into_form()

    # --- setup helpers ------------------------------------------------------
    def _section(self, parent, text):
        tk.Label(parent, text=text, bg=PAGE, fg=NAVY, font=("Segoe UI", 11, "bold")
                 ).pack(anchor="w", padx=18, pady=(16, 2))

    def _help(self, parent, text, url):
        lbl = tk.Label(parent, text=text, bg=PAGE, fg="#2F80C2", cursor="hand2",
                       wraplength=900, justify="left")
        lbl.pack(anchor="w", padx=18)
        lbl.bind("<Button-1>", lambda e: webbrowser.open(url))

    def _fields(self, parent, fields):
        for key, label, secret in fields:
            row = tk.Frame(parent, bg=PAGE)
            row.pack(fill="x", padx=18, pady=3)
            tk.Label(row, text=label, bg=PAGE, width=22, anchor="w").pack(side="left")
            var = tk.StringVar()
            entry = tk.Entry(row, textvariable=var, show=("*" if secret else ""))
            entry.pack(side="left", fill="x", expand=True)
            self.vars[key] = var
            if secret:
                self._secret_entries.append(entry)

    def _cfg_fields(self, parent):
        for key, label in CFG_FIELDS:
            row = tk.Frame(parent, bg=PAGE)
            row.pack(fill="x", padx=18, pady=3)
            tk.Label(row, text=label, bg=PAGE, width=22, anchor="w").pack(side="left")
            var = tk.StringVar()
            tk.Entry(row, textvariable=var).pack(side="left", fill="x", expand=True)
            self.vars["cfg_" + key] = var

    def _toggle_secrets(self):
        show = "" if self.show_secrets.get() else "*"
        for e in self._secret_entries:
            e.config(show=show)

    def _load_settings_into_form(self):
        env = settings_io.read_env(self.config.root / ".env")
        for key, _, _ in ALL_ENV_FIELDS:
            self.vars[key].set(env.get(key, "v25.0" if key == "GRAPH_API_VERSION" else ""))
        brand = self.config.brand
        self.vars["cfg_phone"].set(brand.get("phone", ""))
        self.vars["cfg_website"].set(brand.get("website", ""))
        self.vars["cfg_tagline"].set(brand.get("tagline", ""))
        self.vars["cfg_service_area"].set(self.config.seo.get("service_area", ""))

    def on_save_settings(self):
        env_updates = {key: self.vars[key].get().strip() for key, _, _ in ALL_ENV_FIELDS}
        settings_io.update_env(self.config.root / ".env", env_updates,
                               template=self.config.root / ".env.example")
        for key, _ in CFG_FIELDS:
            settings_io.set_yaml_scalar(self.config.config_path, key,
                                        self.vars["cfg_" + key].get().strip())
        llm.reset_client()
        self.config = config_module.reload_config()
        self.db = DB(self.config.db_path)
        self._refresh_status()
        self._log("Settings saved.")
        messagebox.showinfo("BeriPost", "Settings saved. You're ready to Preview and Post.")

    def on_open_readme(self):
        readme = self.config.root / "README.md"
        try:
            webbrowser.open(readme.resolve().as_uri())
        except Exception:  # noqa: BLE001
            messagebox.showinfo("BeriPost", f"Open this file for full instructions:\n{readme}")

    def on_make_long_lived(self):
        app_id = self.vars["FB_APP_ID"].get().strip()
        app_secret = self.vars["FB_APP_SECRET"].get().strip()
        page_id = self.vars["FB_PAGE_ID"].get().strip()
        token = self.vars["FB_PAGE_ACCESS_TOKEN"].get().strip()
        missing = [n for n, v in (("App ID", app_id), ("App Secret", app_secret),
                                  ("Page ID", page_id), ("token", token)) if not v]
        if missing:
            messagebox.showwarning("BeriPost", "First fill in: " + ", ".join(missing))
            return
        version = self.vars["GRAPH_API_VERSION"].get().strip() or "v25.0"
        self._log("Converting to a long-lived Facebook token...")

        def work():
            return fbauth.make_long_lived_page_token(app_id, app_secret, token, page_id, version)

        def done(result):
            if isinstance(result, dict):  # _run_bg wrapped an error
                messagebox.showerror("BeriPost", f"Could not convert the token:\n\n{result.get('error')}")
                return
            self.vars["FB_PAGE_ACCESS_TOKEN"].set(result)
            self.on_save_settings()
            messagebox.showinfo(
                "BeriPost",
                "Done. Your Facebook token is now long-lived (about 60 days, and Page tokens "
                "from it typically keep working as long as you stay a Page admin). It's saved.")

        self._run_bg(work, done)

    # --- shared helpers -----------------------------------------------------
    def _selected_pillar(self):
        return PILLARS[self.pillar.current()][1]

    def _log(self, msg: str):
        self.log_q.put(msg)

    def _drain(self):
        try:
            while True:
                line = self.log_q.get_nowait()
                self.logbox.config(state="normal")
                self.logbox.insert("end", line + "\n")
                self.logbox.see("end")
                self.logbox.config(state="disabled")
        except queue.Empty:
            pass
        self.root.after(150, self._drain)

    def _refresh_status(self):
        c = self.config

        def mark(ok):
            return "READY" if ok else "not set"
        claude = bool(c.anthropic_api_key)
        fb = bool(c.fb_page_id and c.fb_page_token)
        email = c.email_ready
        txt = f"Claude: {mark(claude)}    |    Facebook: {mark(fb)}    |    Email: {mark(email)}"
        self.status.config(text=txt)
        if hasattr(self, "setup_status"):
            hint = "" if claude else "   <- add your Claude key to start"
            self.setup_status.config(text="Status:  " + txt + hint)

    def _set_busy(self, busy: bool, msg: str = "Working..."):
        self._busy = busy
        state = "disabled" if busy else "normal"
        for b in (self.btn_preview, self.btn_post):
            b.config(state=state)

    def _run_bg(self, fn, on_done):
        if self._busy:
            return
        self._set_busy(True)

        def worker():
            try:
                result = fn()
            except Exception as exc:  # noqa: BLE001
                logging.getLogger().exception("Something went wrong")
                result = {"ok": False, "error": str(exc)}
            self.root.after(0, lambda: (self._set_busy(False), on_done(result)))

        threading.Thread(target=worker, daemon=True).start()

    def _needs_key(self) -> bool:
        if not self.config.anthropic_api_key:
            messagebox.showwarning(
                "Add your Claude key first",
                "Open the Setup tab and paste your Claude (Anthropic) API key, then Save.")
            self.nb.select(self.tab_setup)
            return True
        return False

    def _show_result(self, result: dict):
        if result.get("skipped"):
            messagebox.showinfo("BeriPost", "Nothing scheduled today. Choose a post type from the dropdown.")
            return
        if not result.get("ok"):
            messagebox.showerror("BeriPost", f"Could not build the post:\n\n{result.get('error')}")
            return
        self.caption.delete("1.0", "end")
        self.caption.insert("1.0", result.get("body", ""))
        path = result.get("image_path")
        if path and Image and Path(path).exists():
            img = Image.open(path)
            img.thumbnail((360, 360))
            self._preview_img = ImageTk.PhotoImage(img)
            # width/height must be pixels once an image is set, else it clips.
            self.img_label.config(image=self._preview_img, text="",
                                  width=self._preview_img.width(),
                                  height=self._preview_img.height())
        status = result.get("status")
        if status == "published":
            note = "Posted to your Facebook Page." + (
                " A copy was emailed to you." if self.config.email_ready else "")
            messagebox.showinfo("BeriPost", note)
        elif status == "failed":
            messagebox.showerror("BeriPost", f"Publishing failed:\n\n{result.get('error')}")
        else:
            self._log("Preview built. Nothing was posted.")

    # --- button actions -----------------------------------------------------
    def on_preview(self):
        if self._needs_key():
            return
        p = self._selected_pillar()
        self._log(f"Building a preview ({p or 'today'})...")
        self._run_bg(lambda: pipeline.run_once(self.config, self.db, pillar=p, dry_run=True),
                     self._show_result)

    def on_post(self):
        if self._needs_key():
            return
        if not (self.config.fb_page_id and self.config.fb_page_token):
            messagebox.showwarning("Facebook not connected",
                                   "Add your Facebook Page ID and token in the Setup tab first. "
                                   "You can still use Preview.")
            self.nb.select(self.tab_setup)
            return
        if not messagebox.askyesno("Post now", "This will publish to your Careberi Facebook Page. Continue?"):
            return
        p = self._selected_pillar()
        self._log(f"Posting ({p or 'today'})...")
        self._run_bg(lambda: pipeline.run_once(self.config, self.db, pillar=p, dry_run=False),
                     self._show_result)

    def on_feedback(self):
        note = simpledialog.askstring("Give feedback",
                                      "What should future posts do differently?", parent=self.root)
        if note and note.strip():
            feedback.add(self.config, note.strip())
            self._log(f"Feedback saved: {note.strip()}")
            messagebox.showinfo("BeriPost", "Saved. Future posts will take this into account.")

    def on_tidy(self):
        self._log("Tidying feedback notes...")
        self._run_bg(lambda: (feedback.consolidate(self.config), {"ok": True})[1],
                     lambda r: self._log("Feedback notes tidied (if there were any)."))

    def on_gallery(self):
        try:
            out = site.build(self.config, self.db)
            webbrowser.open(Path(out).resolve().as_uri())
            self._log("Opened the local web gallery in your browser.")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("BeriPost", str(exc))


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
