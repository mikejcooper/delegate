#!/usr/bin/env python3
"""A workflow's past runs: count them, take them off the board (Inbox and Past runs), or put them back.

Deleting a workflow (core-architect, "Remove a skill") asks whether its past runs go too. "remove" moves them into
.workflow-manager-data/history/deleted/<time>-<skill>/, out of every folder the board reads, so they leave the Inbox
at once; "restore" puts them back. Nothing is erased: the deleted folder can be emptied by hand later.

What belongs to a workflow's runs:
  runs/        every run trace whose header names the skill (or its board workflow), and the item runs of its batches
  requests/    its trigger's request traces: those whose triggers are all this workflow's own
  done-list    its lines, so its items are new again if the workflow ever comes back
  suggestions  the run reviewer's warnings on those runs
  screenshots  the ones only those runs name
What a workflow made (pages/<workflow>/, work/<workflow>/, files it saved elsewhere) is the user's: never touched.

    past_runs.py count <skill> [--board-id ID]     what would go, as counts
    past_runs.py remove <skill> [--board-id ID]    move them out; prints the folder they went to
    past_runs.py restore <folder>                  put a removed set back
"""
import argparse
import json
import os
import re
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402


def out(obj, code=0):
    print(json.dumps(obj, indent=1, ensure_ascii=False))
    sys.exit(code)


def _lines(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().splitlines()
    except OSError:
        return []


def _header(path):
    for ln in _lines(path)[:1]:
        try:
            h = json.loads(ln)
            return h if isinstance(h, dict) and h.get("header") else {}
        except ValueError:
            return {}
    return {}


def _triggers(skill):
    try:
        import entries
        return {e["id"] for e in entries.load() if e.get("skill") == skill}
    except Exception:
        return set()


def _aliases(skill):
    """Its earlier names: a renamed workflow's runs still name the skill as it was (skill_history.aliases)."""
    try:
        import skill_history
        return {old for old, new in skill_history.aliases().items() if new == skill}
    except (Exception, SystemExit):
        return set()


def _board_id(skill):
    """Its board workflow's id ("wework-invoices"), which a loop's runs name as their flow."""
    try:
        with open(os.path.join(paths.BOARD_DEFS, skill + ".json"), encoding="utf-8") as fh:
            ws = json.load(fh).get("workflows") or []
        return ws[0].get("id") if ws else None
    except (OSError, ValueError, AttributeError):
        return None


def _deleted_root():
    return os.path.join(paths.HISTORY, "deleted")


def gather(skill, board_id=None):
    """{"runs": [files], "requests": [files], "done": [line numbers], "suggestions": [line numbers], "shots": [files]}"""
    names = {skill, re.sub(r"^workflow-", "", skill)} | ({board_id} if board_id else set()) | _aliases(skill)
    board_id = board_id or _board_id(skill)
    if board_id:
        names.add(board_id)
    runs, ids = [], set()
    rdir, qdir = paths.RUNS, paths.REQUESTS
    heads = {}
    for f in sorted(os.listdir(rdir)) if os.path.isdir(rdir) else []:
        if f.endswith(".jsonl"):
            heads[f] = _header(os.path.join(rdir, f))
    for f, h in heads.items():
        if h.get("skill") in names or h.get("flow") in names:
            runs.append(f)
            ids.add(h.get("run") or f[:-6])
    for f, h in heads.items():   # the item runs of its batches, whatever skill they name
        if f not in runs and h.get("batch") in ids:
            runs.append(f)
            ids.add(h.get("run") or f[:-6])
    trig = set().union(*(_triggers(n) for n in names)) | ({board_id} if board_id else set())
    groups = {heads[f].get("group") for f in runs if heads[f].get("group")}
    requests = []
    for f in sorted(os.listdir(qdir)) if os.path.isdir(qdir) else []:
        if not f.endswith(".jsonl"):
            continue
        p = os.path.join(qdir, f)
        h = _header(p)
        rid = h.get("run") or f[:-6]
        matched = set()
        for ln in _lines(p):
            m = re.search(r'"entry_match":\s*"([^"]+)"', ln)
            if m:
                matched.add(m.group(1))
        named = {h.get("trigger"), h.get("entry"), h.get("workflow")} - {None, ""}
        mine = (matched and matched <= trig) or (not matched and named and named <= (trig | names))
        if mine or (rid in groups and (not matched or matched <= trig)):
            requests.append(f)
            ids.add(rid)
    reqs = {(_header(os.path.join(qdir, f)).get("run") or f[:-6]) for f in requests}
    for f, h in heads.items():   # an older run names only the request that started it
        if f not in runs and h.get("group") in reqs and not h.get("skill"):
            runs.append(f)
            ids.add(h.get("run") or f[:-6])
    done = [i for i, ln in enumerate(_lines(paths.DONE_LIST)) if _json(ln).get("skill") in names]
    sugg_path = os.path.join(paths.HISTORY, "suggestions.jsonl")
    sugg = [i for i, ln in enumerate(_lines(sugg_path)) if _json(ln).get("run") in ids or _json(ln).get("skill") in names]
    shots = []
    if os.path.isdir(paths.SHOTS):
        mine_text = "".join("\n".join(_lines(os.path.join(rdir, f))) for f in runs) + \
                    "".join("\n".join(_lines(os.path.join(qdir, f))) for f in requests)
        others = None
        for s in sorted(os.listdir(paths.SHOTS)):
            if s in mine_text:
                if others is None:   # a screenshot another run also names stays
                    others = "".join("\n".join(_lines(os.path.join(rdir, f))) for f in heads if f not in runs)
                if s not in others:
                    shots.append(s)
    return {"runs": sorted(runs), "requests": requests, "done": done, "suggestions": sugg, "shots": shots}


def _json(ln):
    try:
        o = json.loads(ln)
        return o if isinstance(o, dict) else {}
    except ValueError:
        return {}


def counts(g):
    top = 0
    for f in g["runs"]:
        h = _header(os.path.join(paths.RUNS, f))
        if not h.get("batch"):
            top += 1
    return {"runs": top, "run_files": len(g["runs"]), "requests": len(g["requests"]), "done_list": len(g["done"]),
            "warnings": len(g["suggestions"]), "screenshots": len(g["shots"])}


def _split(path, drop):
    """Write the lines not in drop back; return the dropped ones."""
    lines = _lines(path)
    keep = [ln for i, ln in enumerate(lines) if i not in set(drop)]
    gone = [ln for i, ln in enumerate(lines) if i in set(drop)]
    if gone:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("\n".join(keep) + ("\n" if keep else ""))
        os.replace(tmp, path)
    return gone


def cmd_count(a):
    g = gather(a.skill, a.board_id)
    out(dict(counts(g), skill=a.skill))


def cmd_remove(a):
    g = gather(a.skill, a.board_id)
    c = counts(g)
    if not any(c.values()):
        out(dict(c, skill=a.skill, removed=False, note="no past runs"))
    dest = os.path.join(_deleted_root(), time.strftime("%Y%m%d-%H%M%S") + "-" + a.skill)
    for sub, src, files in (("runs", paths.RUNS, g["runs"]), ("requests", paths.REQUESTS, g["requests"]),
                            ("screenshots", paths.SHOTS, g["shots"])):
        if files:
            os.makedirs(os.path.join(dest, sub), exist_ok=True)
        for f in files:
            shutil.move(os.path.join(src, f), os.path.join(dest, sub, f))
    os.makedirs(dest, exist_ok=True)
    gone = _split(paths.DONE_LIST, g["done"])
    if gone:
        with open(os.path.join(dest, "done-list.jsonl"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(gone) + "\n")
    gone = _split(os.path.join(paths.HISTORY, "suggestions.jsonl"), g["suggestions"])
    if gone:
        with open(os.path.join(dest, "suggestions.jsonl"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(gone) + "\n")
    with open(os.path.join(dest, "removed.json"), "w", encoding="utf-8") as fh:
        json.dump(dict(c, skill=a.skill, t=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())), fh, indent=1)
    _rebuild()
    out(dict(c, skill=a.skill, removed=True, folder=dest))


def cmd_restore(a):
    src = a.folder if os.path.isabs(a.folder) else os.path.join(_deleted_root(), a.folder)
    if not os.path.isfile(os.path.join(src, "removed.json")):
        out({"error": f"no removed runs at {src}"}, 1)
    for sub, dst in (("runs", paths.RUNS), ("requests", paths.REQUESTS), ("screenshots", paths.SHOTS)):
        d = os.path.join(src, sub)
        if os.path.isdir(d):
            os.makedirs(dst, exist_ok=True)
            for f in os.listdir(d):
                if not os.path.exists(os.path.join(dst, f)):
                    shutil.move(os.path.join(d, f), os.path.join(dst, f))
    for name, dst in (("done-list.jsonl", paths.DONE_LIST), ("suggestions.jsonl", os.path.join(paths.HISTORY, "suggestions.jsonl"))):
        p = os.path.join(src, name)
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as fh, open(dst, "a", encoding="utf-8") as to:
                to.write(fh.read())
    shutil.rmtree(src)
    _rebuild()
    out({"restored": os.path.basename(src)})


def _rebuild():
    import subprocess
    try:
        subprocess.run([sys.executable, "-I", os.path.join(HERE, "build_board.py")], capture_output=True, timeout=60,
                       env=dict(os.environ, CLAUDE_PROJECT_DIR=paths.PROJECT))
    except subprocess.TimeoutExpired:
        pass


def main():
    if not paths.PLUGIN:
        out({"error": "past runs live in .workflow-manager-data, which needs the plugin installed in a folder"}, 1)
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    s = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (("count", cmd_count), ("remove", cmd_remove)):
        x = s.add_parser(name)
        x.add_argument("skill")
        x.add_argument("--board-id")
        x.set_defaults(fn=fn)
    r = s.add_parser("restore")
    r.add_argument("folder")
    r.set_defaults(fn=cmd_restore)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
