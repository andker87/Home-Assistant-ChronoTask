import re


def slugify(text: str) -> str:
    if not text:
        return "planner"
    t = str(text).strip().lower()
    t = re.sub(r"[^a-z0-9_\- ]+", "", t)
    t = t.replace(" ", "_")
    t = re.sub(r"_+", "_", t)
    return t or "planner"
