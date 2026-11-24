#!/usr/bin/env python3
"""Whether a finished run needs the run reviewer (core-run-reviewer), or the script check is enough.

A clean run that only read things and made something on this computer (a page, a file) is checked by script alone:
path_check.py on the run and each of its items. The reviewer (a Claude session of its own) starts only when a run
needs judgment that a script can't give:

  drift       the path check found a step missing, out of order, off its path, or a connection used the wrong way
  trouble     a step failed, waited on the user or wasn't sure, or the run ended needing attention
  outside     the run sent, posted, replied, updated or drafted something in an account (not just a file here)
  again       an earlier try of the same item already wrote something outside (a possible second copy)

    review_gate.py <run id> [--dry]   prints {"review": true|false, "why": [...], "checked": [...]}, and with a review
                                      its "facts" (the path check's drift, the writes, earlier tries' writes), so the
                                      session that ran it reviews in one call; --dry records nothing

When no review is needed it records the script check as the run's review (suggestions.py: reviewed, no warnings),
so the run's card says "No warnings". It never changes the run. A test is never reviewed.
"""
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402
import path_check  # noqa: E402
import suggestions  # noqa: E402

OUTSIDE = re.compile(r"(Sent|Posted|Reply|Updated|Draft Created|Drafted)$", re.I)
LOCAL = re.compile(r"^(pages/|shots/|/|~|file:|http://127\.0\.0\.1|http://localhost)")


def lines(run):
    return path_check.trace_lines(run)


def items_of(run):
    out = []
    for p in sorted(glob.glob(os.path.join(paths.RUNS, "wf-*.jsonl"))):
        try:
            with open(p, encoding="utf-8") as fh:
                h = json.loads(fh.readline() or "{}")
        except (OSError, ValueError):
            continue
        if h.get("batch") == run:
            out.append(h.get("run") or os.path.basename(p)[:-6])
    return out


def outside_writes(tl):
    """Steps that changed something outside this computer (a page or file made here doesn't count)."""
    hits = []
    for s in tl:
        if not s.get("id") or s.get("status") != "done" or s.get("type") in ("Mocked", "Fake Read"):
            continue
        ty = str(s.get("type", ""))
        href = str((s.get("made") or {}).get("href", ""))
        if OUTSIDE.search(ty) and not (href and LOCAL.match(href)):
            hits.append(s.get("title") or s.get("step") or ty)
    return hits


def gate(run, dry=False):
    tl = lines(run)
    hdr = next((x for x in tl if x.get("header")), None)
    if not hdr:
        return {"review": False, "why": [f"no trace for {run}"], "checked": []}
    if hdr.get("test") or (hdr.get("try") and not hdr.get("try_real")):
        return {"review": False, "why": ["a test or a try as a test is never reviewed"], "checked": []}
    runs = [run] + (items_of(run) if hdr.get("kind") == "batch" else [])
    why, checked, facts = [], [], []
    for r in runs:
        t = lines(r)
        h = next((x for x in t if x.get("header")), {})
        end = next((x for x in t if x.get("end")), {})
        steps = [x for x in t if x.get("id") and not x.get("header") and not x.get("end")]
        pc = path_check.check(r, end.get("path"))
        checked.append(r)
        if pc.get("checked"):
            for d in pc.get("drift") or []:
                if not d.get("reported"):
                    why.append(f"{r}: {d.get('kind')} · {d.get('step') or d.get('what')}")
                    facts.append(dict({k: v for k, v in d.items() if k != "reported"}, run=r))
        bad = [s.get("title") or s.get("step") for s in steps if s.get("status") in ("failed", "uncertain", "needs_user")]
        if bad or end.get("attention") in ("review", "action"):
            why.append(f"{r}: needs a look ({', '.join(map(str, bad)) or end.get('attention')})")
        ow = outside_writes(t)
        if ow:
            why.append(f"{r}: changed something outside ({', '.join(map(str, ow[:3]))})")
            facts.append({"run": r, "writes": suggestions.writes(t)})
        if h.get("wf"):
            again = [e for e in suggestions.earlier_tries(r, h["wf"]) if outside_writes(
                [dict(w, id="x", status="done") for w in e.get("writes") or []])]
            if again:
                why.append(f"{r}: an earlier try of this item already wrote something outside")
                facts.append({"run": r, "earlier_tries": [{k: e.get(k) for k in ("started", "deleted_from_board",
                                                                                    "writes")} for e in again]})
    if not why and not dry:
        suggestions.write([{"type": "review", "run": run, "t": suggestions.now(), "count": 0, "by": "script check"}])
    out = {"review": bool(why), "why": why, "checked": checked}
    if why:
        out["facts"] = facts   # all the review needs beyond the run itself: the path check's drift, writes, earlier tries
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    print(json.dumps(gate(sys.argv[1], "--dry" in sys.argv), ensure_ascii=False, indent=1))
