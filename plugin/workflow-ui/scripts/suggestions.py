#!/usr/bin/env python3
"""The run reviewer's findings: where a finished run went off its workflow's path, shown as warnings on the run's
outcome (its Warnings tab) in the Builder and as a small warning on the run's Inbox row. A suggestion never changes a run's
status or a skill.

    suggestions.py context <run id>
        Everything the reviewer needs about one run, as JSON: its trace, the path check's facts (path_check.py), the
        workflow's skill file, paths and steps, each connection's set method, the run's own writes (`writes`), and
        every other attempt of the same item with the writes it made (`earlier_tries`, deleted runs included).

    suggestions.py add <run id> --items '[{"title", "detail", "fix", "step", "kind", "severity"}, ...]'
        Saves the review of one run: one suggestion per item (an empty list records that it was reviewed and nothing
        looked strange). Each gets an id (sg-…). severity: info | warn. Prints the ids.

    suggestions.py list [--open] [--run <run id>]
    suggestions.py show <sg-…>
    suggestions.py dismiss <sg-…>... [--why "<reason>"]
    suggestions.py fixed <sg-…>...

The file is append-only JSON lines (paths.SUGGESTIONS): {"type":"suggestion",…}, {"type":"review",…} and
{"type":"status","id",…} lines; the latest status line for an id wins.
"""
import argparse
import glob
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402

def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fail(msg):
    print(json.dumps({"error": msg}))
    sys.exit(1)


def read_all():
    try:
        with open(paths.SUGGESTIONS, encoding="utf-8") as fh:
            return [json.loads(x) for x in fh if x.strip()]
    except (OSError, ValueError):
        return []


def write(objs):
    os.makedirs(os.path.dirname(paths.SUGGESTIONS), exist_ok=True)
    with open(paths.SUGGESTIONS, "a", encoding="utf-8") as fh:
        for o in objs:
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")
    subprocess.run([sys.executable, "-I", os.path.join(HERE, "build_board.py")], capture_output=True)


def current():
    """Every suggestion with its latest status (open, dismissed, fixed), plus the reviewed runs."""
    out, reviews = {}, {}
    for o in read_all():
        if o.get("type") == "suggestion":
            out[o["id"]] = dict(o, status=o.get("status", "open"))
        elif o.get("type") == "status" and o.get("id") in out:
            out[o["id"]].update(status=o["status"], status_t=o.get("t"), status_why=o.get("why", ""))
        elif o.get("type") == "review":
            reviews[o["run"]] = o
    return list(out.values()), reviews


def trace(run):
    p = os.path.join(paths.RUNS, run + ".jsonl")
    try:
        with open(p, encoding="utf-8") as fh:
            return [json.loads(x) for x in fh if x.strip()]
    except (OSError, ValueError):
        return []


def skill_file(skill):
    for d in (paths.USER_SKILLS, paths.SKILLS):
        f = os.path.join(d, skill, "SKILL.md")
        if os.path.isfile(f):
            return f
    return None


def brief(tl):
    """A run in a few lines: its steps and outcome, for comparing with this one."""
    hdr = next((x for x in tl if x.get("header")), {})
    end = next((x for x in tl if x.get("end")), {})
    return {"run": hdr.get("run"), "label": hdr.get("label"), "started": hdr.get("started"),
            "steps": [{k: s.get(k) for k in ("t", "type", "title", "step", "result", "status", "via") if s.get(k)}
                      for s in tl if s.get("id") and not s.get("header") and not s.get("end")],
            "verdict": end.get("verdict"), "attention": end.get("attention")}


WRITE_ENDS = ("Created", "Drafted", "Sent", "Posted", "Updated", "Reply")


def writes(tl):
    """The steps of a run that made or changed something outside: what, where, and its link when it has one."""
    out = []
    for s in tl:
        if not s.get("id") or s.get("header") or s.get("end") or s.get("status") != "done":
            continue
        ty = str(s.get("type", ""))
        if ty in ("Mocked", "Fake Read") or not ty.endswith(WRITE_ENDS):
            continue
        via = s.get("via") or {}
        link = ((s.get("io") or {}).get("out") or {}).get("link")
        out.append({k: v for k, v in {"step": s.get("step"), "type": ty, "t": s.get("t"),
                                       "connection": via.get("connection"), "result": s.get("result"),
                                       "confirmed": via.get("confirmed"), "link": link}.items() if v})
    return out


def earlier_tries(run, wf):
    """Every other attempt of the same item (wf), including runs deleted from the board (kept in .trash/), with
    the writes each one made, so the reviewer can see when this run made something a second time."""
    out = []
    for folder, deleted in ((paths.RUNS, False), (os.path.join(paths.RUNS, ".trash"), True)):
        for p in sorted(glob.glob(os.path.join(folder, wf + "-a*.jsonl"))):
            rid = os.path.basename(p)[:-6]
            if rid == run:
                continue
            try:
                with open(p, encoding="utf-8") as fh:
                    tl = [json.loads(x) for x in fh if x.strip()]
            except (OSError, ValueError):
                continue
            hdr = next((x for x in tl if x.get("header")), {})
            if hdr.get("test") or hdr.get("try") and not hdr.get("try_real"):
                continue   # a test or a held-back try never wrote anything for real (a try for real did)
            w = writes(tl)
            if w:
                out.append({"run": rid, "attempt": hdr.get("attempt"), "started": hdr.get("started"),
                            "deleted_from_board": deleted, "writes": w})
    return out


def cmd_context(a):
    tl = trace(a.run)
    hdr = next((x for x in tl if x.get("header")), None)
    if not hdr:
        fail(f"no trace for {a.run}")
    import path_check
    import connections
    pc = path_check.check(a.run, None, None)
    end = next((x for x in tl if x.get("end")), {})
    path = end.get("path")   # run_item.py end writes the path the run says it took; none: the check lists them
    W = path_check.load_defs() or {}
    defn = path_check.find_def(W, hdr.get("skill", "")) or {}
    if path:
        pc = path_check.check(a.run, path, end.get("deviations") or [])
    uses = sorted({s.get("sk") for s in defn.get("steps", []) if str(s.get("sk", "")).startswith("connection-")})
    print(json.dumps({
        "run": a.run, "header": hdr, "trace": tl, "path_check": pc,
        "workflow": {"id": defn.get("id"), "short": defn.get("short"), "skill_file": skill_file(hdr.get("skill", "")),
                     "paths": [{"label": p.get("label"), "steps": list((p.get("res") or {}).keys())}
                               for p in defn.get("simulated") or []],
                     "steps": [{k: s.get(k) for k in ("key", "title", "type", "sk", "from") if s.get(k)}
                               for s in defn.get("steps", [])]},
        "connections": {c: {k: connections.get(c).get(k) for k in ("status", "method", "checked")} for c in uses},
        "writes": writes(tl),
        "earlier_tries": [] if hdr.get("test") or hdr.get("try") and not hdr.get("try_real") else earlier_tries(a.run, hdr.get("wf", "")),
    }, ensure_ascii=False, indent=1))


def cmd_add(a):
    tl = trace(a.run)
    hdr = next((x for x in tl if x.get("header")), None)
    if not hdr:
        fail(f"no trace for {a.run}")
    try:
        items = json.loads(a.items)
    except ValueError as e:
        fail(f"--items is not valid JSON ({e})")
    if not isinstance(items, list):
        fail("--items must be a JSON list")
    import path_check
    defn = path_check.find_def(path_check.load_defs() or {}, hdr.get("skill", "")) or {}
    t = now()
    out, ids = [], []
    for i, it in enumerate(items):
        if not it.get("title") or not (it.get("detail") or it.get("why")):
            fail(f"each item needs a title and a detail: {json.dumps(it)[:120]}")
        sid = "sg-" + hashlib.sha1(f"{a.run}|{i}|{it['title']}|{t}".encode()).hexdigest()[:8]
        ids.append(sid)
        out.append({"type": "suggestion", "id": sid, "t": t, "run": a.run, "wf": hdr.get("wf"),
                    "label": hdr.get("label"), "skill": hdr.get("skill"), "workflow": defn.get("id"),
                    "workflow_short": defn.get("short"), "severity": it.get("severity") or "warn",
                    **{k: it.get(k, "") for k in ("title", "detail", "fix", "step", "kind")}})
    out.append({"type": "review", "run": a.run, "t": t, "count": len(items), "by": a.by})
    write(out)
    print(json.dumps({"run": a.run, "added": ids}))


def set_status(ids, status, why=""):
    have = {s["id"] for s in current()[0]}
    missing = [i for i in ids if i not in have]
    ok = [i for i in ids if i in have]
    write([{"type": "status", "id": i, "status": status, "t": now(), "why": why} for i in ok])
    print(json.dumps({status: ok, "not_found": missing}))


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("context")
    c.add_argument("run")
    ad = sub.add_parser("add")
    ad.add_argument("run")
    ad.add_argument("--items", required=True)
    ad.add_argument("--by", default="core-run-reviewer")
    ls = sub.add_parser("list")
    ls.add_argument("--open", action="store_true")
    ls.add_argument("--run")
    sh = sub.add_parser("show")
    sh.add_argument("id")
    di = sub.add_parser("dismiss")
    di.add_argument("ids", nargs="+")
    di.add_argument("--why", default="")
    fx = sub.add_parser("fixed")
    fx.add_argument("ids", nargs="+")
    a = ap.parse_args(argv)
    if a.cmd == "context":
        cmd_context(a)
    elif a.cmd == "add":
        cmd_add(a)
    elif a.cmd == "list":
        s = [x for x in current()[0] if (not a.open or x["status"] == "open") and (not a.run or x["run"] == a.run)]
        print(json.dumps(s, ensure_ascii=False, indent=1))
    elif a.cmd == "show":
        s = next((x for x in current()[0] if x["id"] == a.id), None)
        print(json.dumps(s or {"error": f"no suggestion {a.id}"}, ensure_ascii=False, indent=1))
    elif a.cmd == "dismiss":
        set_status(a.ids, "dismissed", a.why)
    else:
        set_status(a.ids, "fixed")


if __name__ == "__main__":
    main(sys.argv[1:])
