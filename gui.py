"""BeriPost desktop app.

A simple window with buttons so you never have to type commands. Preview a post
(nothing is posted), post now, give feedback, tidy feedback, or open the web
gallery. Launch it by double-clicking "Start BeriPost.bat", or run this file
from PyCharm with the project's .venv interpreter.
"""
from __future__ import annotations

import logging
import queue
import threading
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import messagebox, scrolledtext, simpledialog, ttk

from beripost.config import ConfigError, get_config
from beripost.db import DB
from beripost import feedback, pipeline, site

try:
    from PIL import Image, ImageTk
except Exception:  # noqa: BLE001
    Image = ImageTk = None  # preview just won't show images

NAVY = "#16265C"
BERRY = "#D25680"
PAGE = "#EEF2F7"
CLOUD = "#F4F8FC"

# (label shown in the dropdown, pillar value passed to the engine)
PILLARS = [
    ("Today's scheduled post", None),
    ("News commentary", "news"),
    ("Family education", "education"),
    ("Trivia", "trivia"),
    ("Dad joke", "dad_joke"),
]


class _QueueHandler(logging.Handler):
    """Send log records to a thread-safe queue the UI drains on a timer."""

    def __init__(self, q: queue.Queue):
        super().__init__()
        self.q = q

    def emit(self, record):
        self.q.put(self.format(record))


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.config = get_config()
        self.db = DB(self.config.db_path)
        self.log_q: queue.Queue = queue.Queue()
        self._busy = False
        self._preview_img = None  # keep a reference so Tk does not garbage-collect it

        root.title("BeriPost - Careberi")
        root.geometry("1000x660")
        root.configure(bg=PAGE)

        handler = _QueueHandler(self.log_q)
        handler.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S"))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)

        self._build()
        self.root.after(150, self._drain)
        self._log("Ready. 'Preview' builds a post without posting. 'Post now' publishes it.")

    # --- layout -------------------------------------------------------------
    def _build(self):
        header = tk.Frame(self.root, bg=NAVY)
        header.pack(fill="x")
        tk.Label(header, text="BeriPost", bg=NAVY, fg="white",
                 font=("Segoe UI", 20, "bold")).pack(side="left", padx=18, pady=12)
        tk.Label(header, text="Careberi   Home Health & Home Care", bg=NAVY, fg="#9fb6d6",
                 font=("Segoe UI", 10)).pack(side="left", pady=12)

        controls = tk.Frame(self.root, bg=PAGE)
        controls.pack(fill="x", padx=16, pady=12)
        tk.Label(controls, text="Post type:", bg=PAGE).pack(side="left")
        self.pillar = ttk.Combobox(controls, values=[p[0] for p in PILLARS],
                                   state="readonly", width=22)
        self.pillar.current(0)
        self.pillar.pack(side="left", padx=(6, 14))

        self.btn_preview = tk.Button(controls, text="Preview (no posting)",
                                     command=self.on_preview)
        self.btn_preview.pack(side="left", padx=4)
        self.btn_post = tk.Button(controls, text="Post now", bg=BERRY, fg="white",
                                  activebackground="#b8446b", command=self.on_post)
        self.btn_post.pack(side="left", padx=4)
        tk.Button(controls, text="Give feedback", command=self.on_feedback).pack(side="left", padx=4)
        tk.Button(controls, text="Tidy feedback", command=self.on_tidy).pack(side="left", padx=4)
        tk.Button(controls, text="Open web gallery", command=self.on_gallery).pack(side="left", padx=4)

        body = tk.Frame(self.root, bg=PAGE)
        body.pack(fill="both", expand=True, padx=16, pady=(0, 12))

        left = tk.Frame(body, bg=PAGE)
        left.pack(side="left", fill="both", expand=True)
        tk.Label(left, text="Preview", bg=PAGE, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.img_label = tk.Label(left, bg=CLOUD, text="(the post image appears here)",
                                  width=46, height=15)
        self.img_label.pack(fill="x")
        tk.Label(left, text="Caption", bg=PAGE, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(8, 0))
        self.caption = tk.Text(left, height=8, wrap="word")
        self.caption.pack(fill="both", expand=True)

        right = tk.Frame(body, bg=PAGE)
        right.pack(side="right", fill="both", expand=True, padx=(14, 0))
        tk.Label(right, text="Activity", bg=PAGE, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.logbox = scrolledtext.ScrolledText(right, wrap="word", state="disabled")
        self.logbox.pack(fill="both", expand=True)

        self.status = tk.Label(self.root, text="Ready", bg="#dfe6ee", anchor="w", padx=10)
        self.status.pack(fill="x")

    # --- helpers ------------------------------------------------------------
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

    def _set_busy(self, busy: bool, msg: str = "Working..."):
        self._busy = busy
        state = "disabled" if busy else "normal"
        for b in (self.btn_preview, self.btn_post):
            b.config(state=state)
        self.status.config(text=(msg if busy else "Ready"))

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

    def _show_result(self, result: dict):
        if result.get("skipped"):
            self._log("No post type is scheduled for today. Pick a specific type from the dropdown.")
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
            img.thumbnail((440, 440))
            self._preview_img = ImageTk.PhotoImage(img)
            self.img_label.config(image=self._preview_img, text="")
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
        p = self._selected_pillar()
        self._log(f"Building a preview ({p or 'today'})...")
        self._run_bg(lambda: pipeline.run_once(self.config, self.db, pillar=p, dry_run=True),
                     self._show_result)

    def on_post(self):
        if not (self.config.fb_page_id and self.config.fb_page_token):
            messagebox.showwarning(
                "Facebook not connected",
                "Add FB_PAGE_ID and FB_PAGE_ACCESS_TOKEN to your .env first (see the README). "
                "You can still use Preview.")
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
        self._run_bg(lambda: (feedback.consolidate(self.config), {"ok": True, "status": "tidied"})[1],
                     lambda r: self._log("Feedback notes tidied. See feedback.md."))

    def on_gallery(self):
        try:
            out = site.build(self.config, self.db)
            webbrowser.open(Path(out).resolve().as_uri())
            self._log("Opened the local web gallery in your browser.")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("BeriPost", str(exc))


def main():
    try:
        get_config().require_anthropic()
    except ConfigError as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("BeriPost setup", str(exc))
        return
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
