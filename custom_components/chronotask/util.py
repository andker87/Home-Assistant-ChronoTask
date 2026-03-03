from __future__ import annotations

import re


def slugify(text: str) -> str:
    """Converte una stringa in uno slug valido per unique_id e path."""
    if not text:
        return "planner"
    t = str(text).strip().lower()
    t = re.sub(r"[^a-z0-9_\- ]+", "", t)
    t = t.replace(" ", "_")
    t = re.sub(r"_+", "_", t)
    return t.strip("_") or "planner"
