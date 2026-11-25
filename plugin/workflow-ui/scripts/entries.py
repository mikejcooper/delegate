#!/usr/bin/env python3
"""Triggers and skill folders across both layers, for the hooks and the board.

Layers (see paths.py):
  org    the plugin's own skills/ (or this project's .claude/skills/ in-project)
  user   the project's own .claude/skills/ when the plugin is installed in it

Since 0.12.0 a trigger lives inside the workflow it starts: the `trigger`, `starts on`, `in run all`, `reads`,
`item key` and `takes` lines of a workflow-'s Definition (architect rule 17). Before that, triggers were skills named
trigger-<category>-<description> (entry-… before 0.7.0), in either layer, still read here,
each with a "## Trigger" table ("## Entry" before 0.7.0; an older dispatcher's own "## Entry points"
table of the same shape is still read):
      | Trigger | Phrases | Item key |
      |---|---|---|
      | `guardian` | check the guardian, guardian headlines | Guardian link path |

    python3 -I entries.py        print every trigger found, as JSON
"""
import json
import os
import datetime
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402


def skill_roots():
    """[(layer, folder)], org first; the user layer only when it is a different folder."""
    roots = [("org", paths.SKILLS)]
    if os.path.realpath(paths.USER_SKILLS) != os.path.realpath(paths.SKILLS):
        roots.append(("user", paths.USER_SKILLS))
    return roots


def renames():
    """Old skill name -> new name, from every migrations/<version>/renames.json in the plugin, in order.
    Lets a board file written before a rename still find its skills until the user agrees to update it."""
    out, mig = {}, os.path.join(paths.ROOT, "migrations")
    try:
        steps = sorted((d for d in os.listdir(mig) if os.path.isfile(os.path.join(mig, d, "renames.json"))),
                       key=lambda v: tuple(int(x) for x in v.split(".")))
    except (OSError, ValueError):
        return out
    for step in steps:
        try:
            with open(os.path.join(mig, step, "renames.json"), encoding="utf-8") as fh:
                more = json.load(fh)
        except (OSError, ValueError):
            continue
        out = {k: more.get(v, v) for k, v in out.items()}
        out.update({k: v for k, v in more.items() if k not in out})
    return out


def skill_file(name):
    """(layer, path to SKILL.md) for a skill name, org first; an old name finds the renamed skill (if
    the user hasn't renamed theirs yet, the old folder is found first). (None, None) if absent."""
    for candidate in (name, renames().get(name)):
        if not candidate:
            continue
        for layer, root in skill_roots():
            p = os.path.join(root, candidate, "SKILL.md")
            if os.path.isfile(p):
                return layer, p
    return None, None


def skill_dirs():
    """[(layer, name, folder)] for every skill folder in both layers (org wins on a name clash)."""
    seen, out = set(), []
    for layer, root in skill_roots():
        try:
            names = sorted(os.listdir(root))
        except OSError:
            continue
        for n in names:
            d = os.path.join(root, n)
            if n in seen or not os.path.isfile(os.path.join(d, "SKILL.md")):
                continue
            seen.add(n)
            out.append((layer, n, d))
    return out


def parse_definition(text):
    """The ```yaml block under '## Definition' in a SKILL.md, as a dict, or None.

    Only the small shape the skills use: `key: value`; a key with nothing after it holds either a list
    (`  - item`) or fields (`  name: text`); ` # comments` are dropped; yes/no become True/False.
    Fields written `required · example` / `optional · example` (workflow needs) stay plain strings here:
    see needs()."""
    import re
    m = re.search(r"^## Definition\s*\n+```ya?ml\s*\n(.*?)\n```", text, re.M | re.S)
    if not m:
        return None
    out, key = {}, None
    for raw in m.group(1).split("\n"):
        line = re.sub(r"\s+#.*$", "", raw).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        body = line.strip()
        if indent == 0:
            k, _, v = body.partition(":")
            k, v = k.strip(), v.strip()
            key = k
            out[k] = {"yes": True, "no": False}.get(v.lower(), v) if v else None
        elif key is not None:
            if body.startswith("- "):
                out[key] = (out[key] if isinstance(out[key], list) else []) + [body[2:].strip()]
            else:
                k, _, v = body.partition(":")
                out[key] = (out[key] if isinstance(out[key], dict) else {})
                out[key][k.strip()] = v.strip()
    return out


def definition(name):
    """The Definition block of a skill by name (either layer, old names resolved), or None."""
    _, p = skill_file(name)
    if not p:
        return None
    try:
        with open(p, encoding="utf-8") as fh:
            return parse_definition(fh.read())
    except OSError:
        return None


def needs(defn):
    """{field: (required?, example)} from a workflow's or shared process's `needs:`."""
    out = {}
    for k, v in ((defn or {}).get("needs") or {}).items():
        head, _, example = str(v).partition("·")
        out[k] = (head.strip().lower() != "optional", example.strip().strip('"'))
    return out


def _table(path, section):
    """Rows (id, triggers, item key) of the backticked-id table under '## <section>'."""
    rows, cur = [], ""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return rows
    for line in lines:
        if line.startswith("## "):
            cur = line[3:].strip().lower()
        if cur != section:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 2 or not (cells[0].startswith("`") and cells[0].endswith("`")):
            continue
        key = cells[-1] if len(cells) >= 4 else (cells[2] if len(cells) >= 3 else "")
        rows.append((cells[0].strip("`"), [t.strip() for t in cells[1].split(",") if t.strip()], key))
    return rows


KINDS = ("trigger", "workflow", "shared", "connection", "core")
CAPS = {"bbc": "BBC", "kyc": "KYC", "cve": "CVE", "ceo": "CEO", "uk": "UK", "us": "US", "id": "ID", "ai": "AI"}


def _words(parts):
    w = [CAPS.get(x, x) for x in parts]
    return (w[0][:1].upper() + w[0][1:] + (" " if len(w) > 1 else "") + " ".join(w[1:])) if w else ""


def skill_label(name):
    """A skill's board name from its own name, <kind>-<category>-<description> (architect rule 10):
    {kind, category, desc, label}, e.g. trigger-security-gmail-inbox -> Security · Gmail inbox.
    core skills have no category. A name outside the pattern (from before 0.7.0): None."""
    name = renames().get(name, name)
    bits = name.split("-")
    if bits[0] not in KINDS or len(bits) < 2:
        return None
    if bits[0] == "connection":   # connection-<system>: one per external account, no category (rule 10)
        desc = _words(bits[1:])
        return {"kind": "connection", "category": "", "desc": desc, "label": desc + " connection"}
    if bits[0] == "core":
        desc = {"dispatcher": "Delegate"}.get("-".join(bits[1:]), _words(bits[1:]))
        return {"kind": "core", "category": "", "desc": desc, "label": desc}
    if len(bits) < 3:
        return None
    cat, desc = _words(bits[1:2]), _words(bits[2:])
    return {"kind": bits[0], "category": cat, "desc": desc, "label": cat + " \u00b7 " + desc}


def _workflow_trigger(layer, name, defn):
    """A workflow's own trigger (rule 17), in the same shape as a trigger skill's: it hands each run its needs."""
    starts = defn.get("starts on") or []
    sl = skill_label(name)
    gives = {k: ex for k, (req, ex) in needs(defn).items() if req}   # what it hands each run: the required needs
    return {"id": str(defn["trigger"]), "label": sl["label"] if sl else name, "triggers": starts if isinstance(starts, list) else [starts],
            "category": sl["category"] if sl else "", "desc": sl["desc"] if sl else "",
            "item_key": defn.get("item key") or "", "layer": layer, "skill": name, "workflow": name,
            "reads": defn.get("reads") or "", "takes": defn.get("takes") or "",
            "run_all": defn.get("in run all", True) is not False, "gives": gives, "defined": True, "inside": True,
            "schedule": parse_schedule(_saved_schedule(str(defn["trigger"])) or defn.get("schedule"))}


def _saved_schedule(tid):
    """The schedule set from the board (schedules.py), kept in the data folder; "paused · …" while paused."""
    try:
        with open(paths.SCHEDULES, encoding="utf-8") as fh:
            cur = (json.load(fh) or {}).get(tid)
    except (OSError, ValueError, AttributeError):
        return None
    if not cur or not cur.get("schedule"):
        return None
    return ("paused · " if cur.get("paused") else "") + cur["schedule"]


DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def parse_schedule(text):
    """A workflow's `schedule` line (`weekdays 08:00`, `every day 12:00 17:30`,
    `mon thu 08:00`, `every 2 hours 08:00-18:00`, `paused · weekdays 08:00`) as {text, days, times, every_h, from,
    to, paused}: days 0-6 from Monday. Every scheduled run runs its items (older words like "pull in only" are
    ignored). None when unset."""
    if not text:
        return None
    raw = str(text).strip()
    low = raw.lower()
    parts = [p.strip() for p in re.split(r"\s*[·|,;]\s*", low) if p.strip()]
    paused = any(p == "paused" for p in parts)
    when = " ".join(p for p in parts if p not in ("paused", "pull in only", "pull in", "run them", "run"))
    days = list(range(7))
    if "weekday" in when:
        days = [0, 1, 2, 3, 4]
    elif "weekend" in when:
        days = [5, 6]
    else:
        named = [i for i, d in enumerate(DAYS) if re.search(r"\b" + d, when)]
        if named:
            days = named
    times = sorted(set("%02d:%s" % (int(h), m) for h, m in re.findall(r"\b(\d{1,2}):(\d{2})\b", when)))
    every = re.search(r"every (\d+) ?h", when)
    rng = re.search(r"(\d{1,2}:\d{2})\s*(?:-|to)\s*(\d{1,2}:\d{2})", when)
    out = {"text": raw, "days": days, "times": times, "every_h": int(every.group(1)) if every else None,
           "from": rng.group(1).zfill(5) if rng else None, "to": rng.group(2).zfill(5) if rng else None,
           "paused": paused}
    if out["every_h"]:
        out["times"] = []
    once = re.search(r"\bonce (\d{4}-\d{2}-\d{2})\b", when)   # a one-off: "once 2026-11-19 18:07"
    if once and out["times"]:
        try:
            day = datetime.date.fromisoformat(once.group(1))
        except ValueError:
            day = None
        if day:
            out.update({"on": day.isoformat(), "days": [day.weekday()], "times": out["times"][:1], "every_h": None})
    return out


def load():
    """Every trigger: [{id, label, triggers, item_key, layer, skill}]. A workflow's own trigger (its Definition's
    `trigger` line) is listed with skill = that workflow and inside = True. An older dispatcher's table first."""
    out, ids = [], set()
    disp = os.path.join(paths.SKILLS, "core-dispatcher", "SKILL.md")
    for eid, trig, key in _table(disp, "entry points"):
        ids.add(eid)
        out.append({"id": eid, "label": eid.replace("-", " ").capitalize(), "triggers": trig,
                    "item_key": key, "layer": "org", "skill": "core-dispatcher"})
    for layer, name, d in skill_dirs():
        if name.startswith("workflow-"):
            defn = definition(name)
            if defn and defn.get("trigger") and str(defn["trigger"]) not in ids:
                ids.add(str(defn["trigger"]))
                out.append(_workflow_trigger(layer, name, defn))
            continue
        if not name.startswith(("trigger-", "entry-")):
            continue
        p = os.path.join(d, "SKILL.md")
        try:
            with open(p, encoding="utf-8") as fh:
                defn = parse_definition(fh.read())
        except OSError:
            defn = None
        if defn and defn.get("id"):
            starts = defn.get("starts on") or []
            rows = [(str(defn["id"]), starts if isinstance(starts, list) else [starts], defn.get("item key") or "")]
        else:   # before 0.10.0: a ## Trigger (or ## Entry) table
            rows = _table(p, "trigger") or _table(p, "entry")
            defn = None
        for eid, trig, key in rows:
            if eid in ids:
                continue  # an org trigger of the same id wins
            ids.add(eid)
            gives = (defn or {}).get("each item has") or {}
            sl = skill_label(name)
            out.append({"id": eid, "label": sl["label"] if sl else eid.replace("-", " ").capitalize(), "triggers": trig,
                        "category": sl["category"] if sl else "", "desc": sl["desc"] if sl else "",
                        "item_key": key, "layer": layer, "skill": name,
                        "run_all": (defn or {}).get("in run all", True) is not False,
                        "gives": gives if isinstance(gives, dict) else {}, "defined": bool(defn)})
    return out


def trigger_pattern():
    """A regex for the phrases of trigger skills (the dispatcher's own are built into live.py)."""
    phrases = sorted({t for e in load() if e["skill"] != "core-dispatcher" for t in e["triggers"]
                      if len(t.split()) >= 2}, key=len, reverse=True)
    if not phrases:
        return None
    return re.compile(r"\b(" + "|".join(re.escape(p) for p in phrases) + r")\b", re.I)


def board_files():
    """[(layer, skill name, path)] of the user's own board definitions for the Workflow Viewer.

    Home: .delegate-data/config/board/<skill name>.json. Older installs kept them in
    .workflow-manager/config/board/ (0.8), .dispatcher/board/ (0.5-0.7) or as board.json inside the skill
    folder (before 0.5); those are still read (the newest place wins) until the user agrees to move them.
    A definition whose skill no longer exists is listed by orphans()."""
    out, seen = [], set()
    old = [os.path.join(paths.LEGACY_08, "config", "board"), os.path.join(paths.LEGACY, "board")] if paths.LEGACY else []
    for folder in [paths.BOARD_DEFS] + old:
        if not folder or not os.path.isdir(folder):
            continue
        for f in sorted(os.listdir(folder)):
            if f.endswith(".json") and f[:-5] not in seen:
                seen.add(f[:-5])
                out.append(("user", f[:-5], os.path.join(folder, f)))
    for layer, n, d in skill_dirs():
        legacy = os.path.join(d, "board.json")
        if n not in seen and os.path.isfile(legacy):
            out.append((layer, n, legacy))
    return out


def orphans():
    """User board definitions whose skill no longer exists in either layer."""
    names = {n for _, n, _ in skill_dirs()}
    ren = renames()
    return [p for _, n, p in board_files() if n not in names and ren.get(n) not in names]


if __name__ == "__main__":
    print(json.dumps(load(), indent=1))
