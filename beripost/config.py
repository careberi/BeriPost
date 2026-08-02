"""Loads configuration from config.yaml and secrets from the .env file.

Nothing else in the project reads os.environ or config.yaml directly - they all
go through the Config object here, so there is one place to look.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Project root = the folder that contains this package's parent.
ROOT = Path(__file__).resolve().parent.parent

# Load .env once, on import. If it is missing we carry on with a warning later.
load_dotenv(ROOT / ".env")


class ConfigError(Exception):
    """Raised when required configuration or secrets are missing."""


class Config:
    def __init__(self, config_path: Path | None = None):
        self.root = ROOT
        self.config_path = config_path or (ROOT / "config.yaml")
        with open(self.config_path, "r", encoding="utf-8") as fh:
            self._data = yaml.safe_load(fh) or {}

        # Useful derived paths.
        self.data_dir = ROOT / "data"
        self.data_dir.mkdir(exist_ok=True)
        self.db_path = self.data_dir / "beripost.db"
        self.images_dir = ROOT / "generated_images"
        self.images_dir.mkdir(exist_ok=True)
        self.backgrounds_dir = ROOT / "assets" / "backgrounds"
        self.logo_path = ROOT / "assets" / "logo" / "logo.png"
        self.fonts_dir = ROOT / "assets" / "fonts"
        self.brand_voice_path = ROOT / "brand_voice.md"

    # --- config.yaml values (safe, no secrets) ------------------------------
    @property
    def mode(self) -> str:
        return str(self._data.get("mode", "review")).lower()

    @property
    def brand(self) -> dict:
        return self._data.get("brand", {})

    @property
    def models(self) -> dict:
        return self._data.get("models", {})

    @property
    def writer_model(self) -> str:
        return self.models.get("writer", "claude-sonnet-5")

    @property
    def cheap_model(self) -> str:
        return self.models.get("cheap", "claude-haiku-4-5")

    @property
    def posting(self) -> dict:
        return self._data.get("posting", {})

    @property
    def images(self) -> dict:
        return self._data.get("images", {})

    @property
    def images_enabled(self) -> bool:
        return bool(self.images.get("enabled", True))

    @property
    def sources(self) -> dict:
        return self._data.get("sources", {})

    @property
    def site(self) -> dict:
        return self._data.get("site", {})

    @property
    def seo(self) -> dict:
        return self._data.get("seo", {})

    def seo_guidance(self) -> str:
        """Local-SEO guidance for the writer, built from config.yaml `seo:`.

        Deliberately gentle: weave in the service area and search-friendly
        phrasing only where it reads naturally. Never keyword-stuff.
        """
        s = self.seo
        if not s or not s.get("enabled", True):
            return ""
        area = s.get("service_area", "")
        locations = ", ".join(s.get("locations", []))
        keywords = ", ".join(s.get("keywords", []))
        hashtags = " ".join(s.get("hashtags", []))
        lines = [
            "\n\n---\n\nLOCAL SEO (apply naturally, never keyword-stuff, keep the warm brand voice):"
        ]
        if area:
            lines.append(f"- Careberi serves {area}. Mention the service area naturally when it fits.")
        if locations:
            lines.append(f"- Areas served (reference one when relevant, never list them all): {locations}.")
        if keywords:
            lines.append(f"- Where it reads naturally, use plain search phrases families use, such as: {keywords}.")
        if hashtags:
            lines.append(f"- End the post with 3 to 5 relevant hashtags chosen from: {hashtags}.")
        lines.append("- Never sacrifice warmth or sound salesy for the sake of keywords.")
        return "\n".join(lines)

    @property
    def feeds(self) -> list[str]:
        return list(self.sources.get("feeds", []))

    def cta(self) -> str:
        """The default call-to-action text with {phone}/{website} filled in."""
        template = self.brand.get("cta_default", "")
        return template.format(
            phone=self.brand.get("phone", ""),
            website=self.brand.get("website", ""),
        )

    def brand_voice(self) -> str:
        try:
            return self.brand_voice_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""

    # --- secrets from .env --------------------------------------------------
    @property
    def anthropic_api_key(self) -> str | None:
        return os.environ.get("ANTHROPIC_API_KEY")

    @property
    def fb_page_id(self) -> str | None:
        return os.environ.get("FB_PAGE_ID")

    @property
    def fb_page_token(self) -> str | None:
        return os.environ.get("FB_PAGE_ACCESS_TOKEN")

    @property
    def graph_version(self) -> str:
        return os.environ.get("GRAPH_API_VERSION", "v25.0")

    # Email notification (SMTP) secrets from .env.
    @property
    def smtp_host(self) -> str | None:
        return os.environ.get("SMTP_HOST")

    @property
    def smtp_port(self) -> int:
        return int(os.environ.get("SMTP_PORT", "587"))

    @property
    def smtp_user(self) -> str | None:
        return os.environ.get("SMTP_USER")

    @property
    def smtp_pass(self) -> str | None:
        return os.environ.get("SMTP_PASS")

    @property
    def notify_to(self) -> str | None:
        return os.environ.get("NOTIFY_TO")

    @property
    def email_ready(self) -> bool:
        return bool(self.smtp_host and self.smtp_user and self.smtp_pass and self.notify_to)

    # Optional GitHub token (only needed to auto-close feedback issues, or for
    # a private repo). Reading public feedback issues needs no token.
    @property
    def github_token(self) -> str | None:
        return os.environ.get("GITHUB_TOKEN")

    def require_anthropic(self) -> None:
        if not self.anthropic_api_key:
            raise ConfigError(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
            )

    def require_facebook(self) -> None:
        missing = [
            name
            for name, val in (
                ("FB_PAGE_ID", self.fb_page_id),
                ("FB_PAGE_ACCESS_TOKEN", self.fb_page_token),
            )
            if not val
        ]
        if missing:
            raise ConfigError(
                "Facebook is not configured. Missing in .env: " + ", ".join(missing)
            )


# A single shared instance for convenience.
_config: Config | None = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = Config()
    return _config


def reload_config() -> Config:
    """Re-read .env and config.yaml (used after the Setup screen saves changes)."""
    global _config
    load_dotenv(ROOT / ".env", override=True)
    _config = Config()
    return _config
