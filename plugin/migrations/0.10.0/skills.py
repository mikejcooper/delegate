"""0.10.0 user skills: a trigger's ## Trigger (or ## Entry) table becomes a ## Definition block.
convert(name, text) returns the new text, or the same text when there is nothing to do (safe to run twice)."""
import re

TABLE = re.compile(r"^## (Trigger|Entry)\n\|[^\n]*\|\n\|[-| ]+\|\n((?:\|[^\n]*\|\n?)+)", re.M)


def convert(name, text):
    if not name.startswith(("trigger-", "entry-")) or "## Definition" in text:
        return text
    m = TABLE.search(text)
    if not m:
        return text
    row = next((r for r in m.group(2).splitlines() if r.strip().startswith("| `")), None)
    if not row:
        return text
    cells = [c.strip() for c in row.strip().strip("|").split("|")]
    tid = cells[0].strip("`")
    phrases = [p.strip() for p in cells[1].split(",") if p.strip()]
    key = cells[-1] if len(cells) >= 3 else ""
    block = ["## Definition", "```yaml", f"id: {tid}", "starts on:            # what you type"]
    block += [f"  - {p}" for p in phrases]
    block += ["in run all: yes       # offered in the \"run workflow manager\" tick boxes", f"item key: {key}",
              "# each item has: the fields it hands on; the architect adds them the next time this skill changes",
              "```", ""]
    return text[:m.start()] + "\n".join(block) + "\n" + text[m.end():].lstrip("\n")
