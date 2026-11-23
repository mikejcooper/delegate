#!/usr/bin/env python3
"""Where the board should open for a core skill's request, so the hooks can force it open on the right page.

    board_section.py <skill> [<the words it was called with>]

Prints one URL, or nothing for a skill that has no board page of its own (the dispatcher's page is on_skill_start.sh's).
  core-architect      the Builder on the workflow its words name (by skill name, id or short name); a new
                      workflow or an import: the new-workflow page; a connection: the Connections page; else Home
  core-connections    the Connections page
  core-run-reviewer   the Inbox on the run it reviews (wf-…)
  core-renamer        the Builder on the workflow its words name; a connection: the Connections page; else Home
Changes nothing.
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402


def norm(s):
    return re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")


def named_workflow(words):
    """The board id of the workflow the words name, the longest name that matches; None when none does."""
    try:
        import board_store
        defs = board_store.load_all()
    except Exception:
        return None
    text = "-" + norm(words) + "-"
    best, size = None, 0
    for w in defs.get("workflows") or []:
        skill = (w.get("match") or {}).get("skill")
        if not skill:
            continue   # the architect's own help pages
        names = {skill, skill.replace("workflow-", "", 1), w.get("id"), norm(w.get("short"))}
        for n in filter(None, names):
            n = norm(n)
            if len(n) > size and "-" + n + "-" in text:
                best, size = w["id"], len(n)
    return best


def section(skill, words):
    skill = skill.split(":")[-1]
    base = paths.as_dict().get("url", "")
    folder = base.rsplit("/", 1)[0]
    viewer = folder + "/workflow-viewer.html?w="
    low = (words or "").lower()
    if skill == "core-connections":
        return viewer + "connections"
    if skill == "core-run-reviewer":
        m = re.search(r"\bwf-[a-z0-9-]+", low)
        return base + ("?item=" + re.sub(r"-a\d+$", "", m.group(0)) if m else "")
    if skill in ("core-architect", "core-renamer"):
        wid = named_workflow(words)
        if wid:
            return viewer + wid
        if re.search(r"\bconnection\b", low):
            return viewer + "connections"
        if re.search(r"\b(add a workflow|new workflow|when:|trigger:|import)\b", low):
            return viewer + "new"
        return viewer + "home"
    return ""


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: board_section.py <skill> [<words>]")
    print(section(sys.argv[1], " ".join(sys.argv[2:])))
