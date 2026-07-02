"""Frontend asset loader for the local browser server."""

from __future__ import annotations

from pathlib import Path


UI_DIR = Path(__file__).resolve().parent.parent / "ui"
INDEX_HTML = (UI_DIR / "index.html").read_text(encoding="utf-8")
