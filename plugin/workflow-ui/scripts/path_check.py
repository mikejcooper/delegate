#!/usr/bin/env python3
"""How closely one finished run followed its workflow's path. It never blocks anything: it only reports the drift.

    path_check.py <wf>-a<n> [--path "<path label>"] [--deviations '<json list>']

Compares the run's trace with the workflow's board definition (workflows-data.js), the same way the board reads a run
(runpath.js `matches` / `mapSteps`), and with each connection's chosen method (connections.py):
  unknown_path   the path given is not one of the workflow's paths (or none was given)
  missing_step   a step on that path has no matching line in the trace
  out_of_order   steps on the path were logged in a different order
  off_path       a step that belongs to another path was logged
  no_via         a step that uses a connection did not log how it went in ("via")
  wrong_method   it went in by another method than the connection is set to
  not_confirmed  a connection's write did not log that it confirmed the result (e.g. "in Sent")
Each drift is marked "reported" when the run's own end line lists it under "deviations" (a step's title or key named).
Prints {"checked": true, "drift": [...], "followed": n, "of": n} or {"checked": false, "why": "..."}.
The run reviewer (core-run-reviewer) gets these facts through suggestions.py context and judges what they mean;
this script judges nothing and changes nothing. A test replay has its own pass / fail and is not checked.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402
import connections  # noqa: E402


def load_defs():
    p = paths.WORKFLOWS_JS
    try:
        with open(p, encoding="utf-8") as fh:
            txt = fh.read()
    except OSError:
        return None
    s, e = txt.find("{"), txt.rstrip().rstrip(";").rfind("}")
    try:
        return json.loads(txt[s:e + 1])
    except ValueError:
        return None


def trace_lines(run):
    try:
        with open(os.path.join(paths.RUNS, run + ".jsonl"), encoding="utf-8") as fh:
            return [json.loads(x) for x in fh if x.strip()]
    except (OSError, ValueError):
        return []


def norm(x):
    return " ".join(str(x or "").replace("If:", "").lower().split()).rstrip(".?:! ")


def matches(f, s):
    """runpath.js matches(): the type (or a test's "as") and, when given, one of the step_any words."""
    t, w = f.get("type_any") or [], f.get("step_any") or []
    ok_t = not t or s.get("type") in t or (s.get("as") and s.get("as") in t)
    text = (str(s.get("step", "")) + " " + str(s.get("result", ""))).lower()
    ok_w = not w or any(str(x).lower() in text for x in w)
    return ok_t and ok_w


def same_title(st, s):
    t = norm(st.get("title"))
    return bool(t) and t in (norm(s.get("title")), norm(s.get("step")))


def map_steps(defn, steps):
    """{definition step key: trace index}, as the board does (runpath.js mapSteps): the line stamped with the step's
    key ("wstep", written by run_item.py) first, then its "from", then the same title."""
    m, used = {}, set()
    for st in defn.get("steps", []):
        i = next((i for i, s in enumerate(steps) if i not in used and s.get("wstep") == st.get("key")), None)
        if i is not None:
            m[st["key"]] = i
            used.add(i)
    for st in defn.get("steps", []):
        if st["key"] in m:
            continue
        f = st.get("from")
        for i, s in enumerate(steps):
            if i in used or s.get("wstep"):
                continue
            hit = (isinstance(f, dict) and (s.get("key") == f["key"] if f.get("key") else matches(f, s))) \
                or same_title(st, s)
            if hit:
                m[st["key"]] = i
                used.add(i)
                break
    return m


def find_def(W, skill):
    alias = (W.get("skills", {}).get(skill) or {}).get("alias_of") or skill
    for w in W.get("workflows", []):
        if (w.get("match") or {}).get("skill") in (skill, alias):
            return w
    return None


def check(run, path=None, deviations=None):
    tl = trace_lines(run)
    hdr = next((x for x in tl if x.get("header")), None)
    if not hdr:
        return {"checked": False, "why": f"no trace for {run}"}
    if hdr.get("test"):
        return {"checked": False, "why": "a test replay has its own pass / fail"}
    W = load_defs()
    defn = find_def(W, hdr.get("skill", "")) if W else None
    if not defn:
        return {"checked": False, "why": f"no board definition for {hdr.get('skill')}"}
    steps = [x for x in tl if x.get("id") and not x.get("header") and not x.get("end")
             and x.get("type") != "Path Check"]
    end = next((x for x in tl if x.get("end")), {})
    devs = deviations if deviations is not None else (end.get("deviations") or [])
    byk = {s["key"]: s for s in defn.get("steps", []) if s.get("key")}
    drift = []

    def add(kind, st, what):
        drift.append({"kind": kind, "step": (st or {}).get("title", ""), "key": (st or {}).get("key", ""),
                      "what": what})

    paths_ = defn.get("simulated") or []
    p = next((x for x in paths_ if norm(x.get("label")) == norm(path)), None) if path else None
    m = map_steps(defn, steps)
    if paths_ and not p:
        names = ", ".join('"' + x.get("label", "") + '"' for x in paths_)
        add("unknown_path", None, (f'"{path}" is not one of its paths ({names})' if path
                                   else f"no path was given ({names})"))
    expect = [s["key"] for s in defn.get("steps", []) if p and s.get("key") in (p.get("res") or {})]
    # a loop workflow (core-architect rule 33): an item's trace holds only its loop's steps; the run's own holds the rest
    loops = defn.get("loops") or []
    if loops and hdr.get("batch"):
        mine = next((lp for lp in loops if lp.get("key") == (hdr.get("loop") or loops[0].get("key"))), loops[0])
        expect = [k for k in expect if k in (mine.get("steps") or [])]
    elif loops and hdr.get("kind") == "batch":
        inside = {k for lp in loops for k in (lp.get("steps") or [])}
        once = [s["key"] for s in defn.get("steps", []) if s.get("key") not in inside]
        drift = [d for d in drift if d["kind"] != "unknown_path"]   # paths are named on each item, not the run
        m_once = map_steps(defn, steps)
        for k in once:
            if k not in m_once:
                add("missing_step", byk[k], "this once step has no line on the run's own trace")
        expect = []
    for k in expect:
        if k not in m:
            add("missing_step", byk[k], "no line in the trace matches this step (by its type or title)")
    seen = [k for k in expect if k in m]
    order = sorted(seen, key=lambda k: m[k])
    if order != seen:
        add("out_of_order", None, "logged as " + " → ".join(byk[k].get("title", k) for k in order))
    if p:
        for k, i in m.items():
            if k not in expect and k in byk and byk[k].get("type") != "dec":
                add("off_path", byk[k], f'logged, but it is not on "{p.get("label")}"')
    # connections: every mapped step that runs through one says how it went in, and that it confirmed a write
    for k, i in m.items():
        st, s = byk.get(k) or {}, steps[i]
        sk = str(st.get("sk", ""))
        if not sk.startswith("connection-"):
            continue
        via = s.get("via") if isinstance(s.get("via"), dict) else None
        want = (connections.get(sk).get("method") or "")
        if not via:
            add("no_via", st, f"didn't log how it reached {sk.replace('connection-', '')}"
                + (f" (set to {want})" if want else ""))
            continue
        got = str(via.get("method", ""))
        if want and got and got != want:
            add("wrong_method", st, f"went in by {got}; the connection is set to {want}")
        if st.get("type") == "send" or st.get("hand", "").endswith("write"):
            if not via.get("confirmed"):
                add("not_confirmed", st, "didn't log that the connection confirmed the result")
    for d in drift:
        names = [norm(d["step"]), norm(d["key"])]
        d["reported"] = any(any(n and n in norm(json.dumps(x)) for n in names) for x in devs) if d["step"] \
            else bool(devs) and d["kind"] == "unknown_path" and any("path" in norm(json.dumps(x)) for x in devs)
    return {"checked": True, "path": p.get("label") if p else (path or ""), "followed": len(seen),
            "of": len(expect), "drift": drift}


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("--path")
    ap.add_argument("--deviations")
    a = ap.parse_args(argv)
    devs = json.loads(a.deviations) if a.deviations else None
    print(json.dumps(check(a.run, a.path, devs), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1:])
