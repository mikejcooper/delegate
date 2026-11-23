#!/usr/bin/env python3
"""The board's definitions as one picture, kept in two layers.

  org    the plugin's workflows.json: the engine (dispatcher, architect modes, sections) and the plugin's own skills
  user   .workflow-manager-data/config/board/<skill>.json: everything of one of this folder's own skills, in the
         same shape as workflows.json (workflows, entries, skills, categories, summaries, examples, results)

load_all() joins them into one workflows.json-shaped dict, so a script can read and change it as one file;
save_all(defs) splits it again by owner and writes each part back to its own file. A skill is the user's unless
it is in the plugin's own skills folder. The org part is written only where the plugin may be changed (its
source repo, or the old in-project setup); from an install a change to it is refused.

    python3 -I board_store.py split    print which file owns what (a dry run of save_all on the current board)
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402

ORG_FILE = os.path.join(paths.CODE, "workflows.json")
ORG_ONLY = ("_about", "sections", "dispatcher")          # always the engine's
PAGE_LINES = ("summaries", "examples", "results")        # keyed "workflow:<id>" / "trigger:<entry key>"


class Refused(Exception):
    pass


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def plugin_version():
    try:
        return _read(os.path.join(paths.ROOT, ".claude-plugin", "plugin.json"))["version"]
    except (OSError, ValueError, KeyError):
        return "0.0.0"


def org_skills():
    d = paths.SKILLS
    return {n for n in os.listdir(d) if os.path.isdir(os.path.join(d, n))} if os.path.isdir(d) else set()


def board_skill(w):
    """The skill a board workflow draws: its match skill, else the skill doing its first step (the architect's modes)."""
    sk = (w.get("match") or {}).get("skill")
    if sk:
        return sk
    return next((st.get("sk") for st in w.get("steps", [])
                 if (st.get("sk") or "").startswith(("workflow-", "shared-", "core-", "trigger-"))), None)


def layered():
    """True where the board is kept in two layers (a plugin install or the plugin's source repo)."""
    return bool(paths.BOARD_DEFS)


def org_writable():
    return not paths.PLUGIN or getattr(paths, "SOURCE", False)


def user_files():
    """{skill: path} of this folder's own board definitions."""
    d = paths.BOARD_DEFS
    if not d or not os.path.isdir(d):
        return {}
    return {f[:-5]: os.path.join(d, f) for f in sorted(os.listdir(d)) if f.endswith(".json")}


def load_all():
    """Org workflows.json with every user board file joined in (same shape as workflows.json)."""
    defs = _read(ORG_FILE)
    if not layered():
        return defs
    for sk, path in user_files().items():
        part = _read(path)
        for w in part.get("workflows") or []:
            if w.get("id") not in {x.get("id") for x in defs.setdefault("workflows", [])}:
                defs["workflows"].append(w)
        for key in ("entries", "skills", "categories", *PAGE_LINES):
            for k, v in (part.get(key) or {}).items():
                defs.setdefault(key, {}).setdefault(k, v)
    return defs


def split(defs):
    """{None: the org part, skill: that skill's part}: who owns each piece of a joined board."""
    org = org_skills()
    mine = lambda sk: bool(sk) and sk not in org and not sk.startswith("core-")
    parts = {None: {k: defs[k] for k in ORG_ONLY if k in defs}}
    part = lambda sk: parts.setdefault(sk if mine(sk) else None, {})
    wf_owner = {}
    for w in defs.get("workflows") or []:
        sk = board_skill(w)
        wf_owner[w.get("id")] = sk if mine(sk) else None
        part(sk).setdefault("workflows", []).append(w)
    en_owner = {}
    for k, e in (defs.get("entries") or {}).items():
        sk = next((wf_owner.get(f) for f in e.get("feeds") or [] if wf_owner.get(f)), None) or e.get("skill")
        en_owner[k] = sk if mine(sk) else None
        part(sk).setdefault("entries", {})[k] = e
    table = defs.get("skills") or {}
    for name, v in table.items():
        target, seen = name, set()
        while (table.get(target) or {}).get("alias_of") and target not in seen:   # an old name: its current skill
            seen.add(target)
            target = table[target]["alias_of"]
        part(target).setdefault("skills", {})[name] = v
    for key in PAGE_LINES:
        for k, v in (defs.get(key) or {}).items():
            kind, _, ref = k.partition(":")
            sk = wf_owner.get(ref) if kind == "workflow" else en_owner.get(ref) if kind == "trigger" else None
            part(sk).setdefault(key, {})[k] = v
    cats = defs.get("categories") or {}
    used = {}
    for sk, p in parts.items():
        for w in p.get("workflows") or []:
            used.setdefault(w.get("category"), set()).add(sk)
    for k, v in cats.items():
        owners = used.get(k, set())
        if None in owners or not owners:
            parts[None].setdefault("categories", {})[k] = v
        for sk in owners - {None}:
            parts[sk].setdefault("categories", {})[k] = v
    # a category the org has needn't be repeated in a user file
    for sk, p in parts.items():
        if sk and "categories" in p:
            p["categories"] = {k: v for k, v in p["categories"].items() if k not in parts[None].get("categories", {})}
            if not p["categories"]:
                del p["categories"]
    return parts


def save_all(defs):
    """Write a joined board back: the org part to workflows.json, each user skill's part to its own file.
    Returns the files written."""
    if not layered():
        _write(ORG_FILE, defs)
        return [ORG_FILE]
    parts = split(defs)
    org_part = parts.pop(None)
    written = []
    old_org = _read(ORG_FILE)
    order = list(old_org.keys()) + [k for k in org_part if k not in old_org]
    # a key the joined board doesn't carry (the demo, anything only the plugin's file has) keeps what the file had:
    # writing {} for it wiped the welcome's demo on every save
    new_org = {k: org_part[k] if k in org_part else old_org[k] for k in order if k in org_part or k in old_org}
    if json.dumps(new_org, sort_keys=True) != json.dumps(old_org, sort_keys=True):
        if not org_writable():
            raise Refused("this change touches the plugin's own board (workflows.json), which is read-only from an "
                          "install: change only this folder's own skills")
        _write(ORG_FILE, new_org)
        written.append(ORG_FILE)
    have = user_files()
    for sk, p in parts.items():
        path = have.get(sk) or os.path.join(paths.BOARD_DEFS, sk + ".json")
        old = _read(path) if os.path.isfile(path) else {}
        new = dict(old)
        for key in ("workflows", "entries", "skills", "categories", *PAGE_LINES):
            if p.get(key):
                new[key] = p[key]
            else:
                new.pop(key, None)
        if json.dumps(new, sort_keys=True) != json.dumps(old, sort_keys=True):
            new.setdefault("format", 2)
            new["data_version"] = plugin_version()   # written by this version: migrate.py must not upgrade it again
            _write(path, new)
            written.append(path)
    return written


if __name__ == "__main__":
    if sys.argv[1:] == ["split"]:
        ps = split(load_all())
        print(json.dumps({str(k): {kk: (len(vv) if isinstance(vv, (list, dict)) else vv) for kk, vv in v.items()}
                          for k, v in ps.items()}, indent=1))
    else:
        print(__doc__)
