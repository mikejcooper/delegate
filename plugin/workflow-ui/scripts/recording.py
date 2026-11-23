#!/usr/bin/env python3
"""Recordings: what really came back from the outside, kept so tests replay real data instead of made-up data
(core-architect rule 28). Every real run (core-dispatcher, Recordings) saves what it read; a new workflow's runs
read for real with every write refused. Only the newest few per path are kept, never one a test replays:

  workflow  <skill>/tests/recordings/<id>.json  one item's run: the fields it was handed, what each step really
            read or worked out, what each write would have done, the path it took and which systems it reached.
            The first recording of a path also becomes that path's test case: <skill>/tests/<id>.json
            {"path": ..., "recording": <id>}. --sample: the run was on a sample item (its steps ran for real where
            they could); its recording and case are marked "sample", and the first real recording of that
            path replaces the sample's case.
  trigger   <skill>/tests/recordings/<id>.json (a workflow's own trigger: <workflow>/tests/trigger/recordings/)  one get-and-sort: the items that carried on (only the fields the
            trigger hands on) and how many stopped (a count, never their content).

Kept small and private: only the fields a trigger hands on and the steps' short results. Never full email bodies,
passwords, tokens or personal ID numbers; the dispatcher passes only those short fields in.

    recording.py workflow <skill> --run <wf>-a<n> --path "<path label>" [--systems '{"Outlook": "ok"}'] [--sample]
    recording.py trigger <skill> --run <request run ID> --items '<json list>' --others <n> [--systems '{...}']
    recording.py list <skill>
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
import entries  # noqa: E402

KEEP = ("title", "type", "as", "result", "sub", "status")


def _dir(skill, write=True):
    f = entries.skill_file(skill)[1]
    if not f:
        sys.exit(f"no skill {skill}")
    root = os.path.realpath(paths.ROOT)
    if write and paths.PLUGIN and not paths.SOURCE and os.path.realpath(f).startswith(root + os.sep):
        # one of the plugin's own workflows, run from an install: the plugin is read-only here (and replaced on
        # every update), and it ships with its own tests from real runs. Nothing to save.
        print(json.dumps({"saved": False, "why": f"{skill} is the plugin's own workflow: its tests ship with the "
                          "plugin, so runs of it here aren't recorded"}, indent=1))
        sys.exit(0)
    return os.path.join(os.path.dirname(f), "tests")


def _trace(run):
    out = []
    try:
        with open(os.path.join(paths.RUNS, run + ".jsonl"), encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        out.append(json.loads(line))
                    except ValueError:
                        pass
    except OSError:
        pass
    return out


def _input(wf):
    item = None
    try:
        with open(paths.DONE_LIST, encoding="utf-8") as fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("wf") == wf and row.get("input"):
                    item = row["input"]
    except OSError:
        pass
    return item


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:48] or "recording"


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
        fh.write("\n")


def systems_of(text):
    """--systems as {"Outlook": "ok"}; a list (["outlook", "slack"]) or "outlook,slack" means each was reached."""
    text = (text or "").strip()
    try:
        val = json.loads(text) if text else {}
    except ValueError:
        val = [x for x in text.split(",") if x.strip()]
    if isinstance(val, list):
        val = {str(x).strip().capitalize(): "ok" for x in val}
    return val if isinstance(val, dict) else {}


def board_paths(skill):
    """The path names the board knows for a workflow skill (its `simulated` labels, from the last build), or None when
    the board can't be read. A recording's path must be one of them to become a test (the build refuses others)."""
    try:
        txt = open(paths.WORKFLOWS_JS, encoding="utf-8").read()
        defs = json.loads(txt[txt.index("=") + 1:].rstrip().rstrip(";"))
    except (OSError, ValueError):
        return None
    for w in defs.get("workflows", []):
        if ((w.get("match") or {}).get("skill") or "") == skill:
            return [p.get("label") for p in w.get("simulated", []) if p.get("label")]
    return None


def workflow(skill, run, path, systems, sample=False):
    known = board_paths(skill)
    if known and path not in known:
        return {"saved": False, "path": path, "why": f"{path!r} is not one of this workflow's paths on the board, so it "
                "was not saved: save it again with --path set to the one of these it took", "paths": known}
    lines = _trace(run)
    head = next((x for x in lines if x.get("header")), {})
    wf = head.get("wf") or run.rsplit("-a", 1)[0]
    item = _input(wf)
    if not lines or item is None:
        return {"saved": False, "why": f"no trace or no handed-over input for {run}"}
    steps = [x for x in lines if not x.get("header") and not x.get("end") and "entry_match" not in x]
    reads = [{k: s[k] for k in KEEP if k in s} for s in steps if s.get("type") != "Mocked"]
    writes = [{k: s[k] for k in KEEP if k in s} for s in steps if s.get("type") == "Mocked"]
    rid = time.strftime("%Y%m%d") + "-" + _slug(path.replace("If:", ""))
    d = _dir(skill)
    n, base = 1, rid
    while os.path.exists(os.path.join(d, "recordings", rid + ".json")):
        n += 1
        rid = f"{base}-{n}"
    _write(os.path.join(d, "recordings", rid + ".json"),
           {"kind": "workflow", "from_run": run, "recorded": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "path": path, "item": item, "reads": reads, "writes": writes, "systems": systems or {},
            **({"sample": True} if sample else {})})
    case = None
    cases = {}
    for f in (os.listdir(d) if os.path.isdir(d) else []):
        if f.endswith(".json"):
            c = json.load(open(os.path.join(d, f), encoding="utf-8"))
            if c.get("path"):
                cases.setdefault(c["path"], []).append((f, c))
    have = cases.get(path, [])
    if not have:   # the first example of a path becomes its test (a sample's is marked)
        case = rid
        _write(os.path.join(d, rid + ".json"), {"path": path, "recording": rid, **({"sample": True} if sample else {})})
    elif not sample and all(c.get("sample") for _f, c in have):   # real data takes over from a sample
        for f, _c in have:
            os.remove(os.path.join(d, f))
        case = rid
        _write(os.path.join(d, rid + ".json"), {"path": path, "recording": rid})
    _prune(d, "path", path)
    return {"saved": True, "recording": rid, "test_case": case, "path": path}


KEEP_PER = 3


def _prune(d, key, value):
    """Keep only the newest few recordings per path (or per trigger); never one a test case replays."""
    used = set()
    for f in os.listdir(d):
        if f.endswith(".json"):
            try:
                used.add(json.load(open(os.path.join(d, f), encoding="utf-8")).get("recording"))
            except ValueError:
                pass
    rd = os.path.join(d, "recordings")
    same = []
    for f in os.listdir(rd):
        if f.endswith(".json"):
            r = json.load(open(os.path.join(rd, f), encoding="utf-8"))
            if r.get(key) == value:
                same.append((r.get("recorded", ""), f[:-5]))
    for _t, rid in sorted(same, reverse=True)[KEEP_PER:]:
        if rid not in used:
            os.remove(os.path.join(rd, rid + ".json"))


def trigger(skill, run, items, others, systems):
    rid = time.strftime("%Y%m%d-%H%M") + "-" + _slug(run)
    d = _dir(skill)
    if skill.startswith("workflow-"):   # a workflow's own trigger (rule 17): its cases sit apart, in tests/trigger/
        d = os.path.join(d, "trigger")
    os.makedirs(os.path.join(d, "recordings"), exist_ok=True)
    _write(os.path.join(d, "recordings", rid + ".json"),
           {"kind": "trigger", "from_run": run, "recorded": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "carried_on": items, "stopped": int(others), "systems": systems or {}})
    if not any(f.endswith(".json") and json.load(open(os.path.join(d, f), encoding="utf-8")).get("recording")
               for f in os.listdir(d)):
        _write(os.path.join(d, "replays-a-recording.json"), {"recording": rid})
    _prune(d, "kind", "trigger")
    return {"saved": True, "recording": rid}


def listing(skill):
    d = os.path.join(_dir(skill, write=False), "recordings")
    out = []
    for f in sorted(os.listdir(d)) if os.path.isdir(d) else []:
        if f.endswith(".json"):
            r = json.load(open(os.path.join(d, f), encoding="utf-8"))
            out.append({"id": f[:-5], "path": r.get("path"), "from_run": r.get("from_run"), "recorded": r.get("recorded")})
    return out


def main(argv):
    p = argparse.ArgumentParser(description="Recordings of real runs, replayed by tests")
    sub = p.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("workflow")
    w.add_argument("skill")
    w.add_argument("--run", required=True)
    w.add_argument("--path", required=True)
    w.add_argument("--systems", default="{}")
    w.add_argument("--sample", action="store_true")
    t = sub.add_parser("trigger")
    t.add_argument("skill")
    t.add_argument("--run", required=True)
    t.add_argument("--items", default="[]")
    t.add_argument("--others", default="0")
    t.add_argument("--systems", default="{}")
    ls = sub.add_parser("list")
    ls.add_argument("skill")
    a = p.parse_args(argv)
    if a.cmd == "workflow":
        out = workflow(a.skill, a.run, a.path, systems_of(a.systems), a.sample)
    elif a.cmd == "trigger":
        out = trigger(a.skill, a.run, json.loads(a.items), a.others, systems_of(a.systems))
    else:
        out = listing(a.skill)
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
