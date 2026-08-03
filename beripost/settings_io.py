"""Read and write .env and simple config.yaml values, preserving comments.

Used by the desktop app's Setup screen so the user never edits files by hand.
"""
from __future__ import annotations

import re
from pathlib import Path


def read_env(path: Path) -> dict:
    """Parse a .env file into {KEY: value}. Missing file -> {}."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, val = s.split("=", 1)
        values[key.strip()] = val.strip()
    return values


def update_env(path: Path, updates: dict, template: Path | None = None) -> None:
    """Update KEY=value lines in .env, preserving comments and other lines.

    Keys not already present are appended. If .env is missing, it is seeded from
    `template` (usually .env.example) first so the helpful comments come along.
    """
    if not path.exists() and template and template.exists():
        path.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")

    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen = set()
    out = []
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            key = s.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        out.append(line)
    for key, val in updates.items():
        if key not in seen:
            out.append(f"{key}={val}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def set_yaml_raw(path: Path, key: str, raw_value: str) -> bool:
    """Set a `key:` value WITHOUT adding quotes (for YAML words/null, e.g.
    schedule days like `monday: news` or `sunday: null`)."""
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^(\s*){re.escape(key)}:[ \t]*.*$", re.M)
    new_text, n = pattern.subn(rf"\g<1>{key}: {raw_value}", text, count=1)
    if n:
        path.write_text(new_text, encoding="utf-8")
    return n > 0


def set_yaml_scalar(path: Path, key: str, value: str) -> bool:
    """Replace the value of a single `key:` line in a YAML file, keeping comments.

    Only touches the first match. Good for unique scalar keys (phone, website,
    tagline, time_of_day, service_area). Returns True if a line was changed.
    """
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^(\s*){re.escape(key)}:[ \t]*.*$", re.M)
    safe = value.replace('"', '\\"')
    new_text, n = pattern.subn(rf'\g<1>{key}: "{safe}"', text, count=1)
    if n:
        path.write_text(new_text, encoding="utf-8")
    return n > 0
