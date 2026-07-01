"""HTML template loader for the local browser UI."""

from __future__ import annotations

from pathlib import Path


STATIC_DIR = Path(__file__).with_name("static")
INDEX_HTML = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
