#!/usr/bin/env python3
"""The dispatcher's bookkeeping in one call per moment, so a run never waits on hand-written trace lines
(RUN-TRACE.md says what each line means; this writes them with real timestamps and rebuilds the board each time).

    run_item.py line <run id> '<json>'
        Append one line to a trace: the request's (dispatch-…) or an item's (<wf>-a<n>). "t" is added from the clock;
        a step with no "id" gets the next one (s1, s2, …). Use it for the trigger line, each step and the request's end.
        In an item's run, a step is stamped with the workflow step it is ("wstep": that step's key), found by its
        "step" (or "title") being that workflow step's title, word for word. The board and the run reviewer match on
        the stamp, so a run's steps line up with its workflow whatever "type" they carry. A step whose name is no
        step of the workflow is written unstamped, with "unmatched": true, and the output's "warning" lists the
        titles it can use: rename the step and log it again. "wstep": null says on purpose that a line is not a
        workflow step (a connection check, your context). A code step (its "key" written by flow.py) needs no stamp.

    run_item.py queue <request id> --entry <trigger id> --skill <workflow skill> [--try [--real] | --test]
                      --items '[{"wf": "wf-…", "item": "<item key>", "label": "<short name>", "input": {…}}, …]'
        Right after the trigger keeps its items, before running any: every item gets its row on the Inbox at once,
        marked Queued, so you see what was found while the first one runs. One call for all of them.

    run_item.py start <request id> --wf <wf> --attempt <n> --entry <trigger id|direct|followup> --item <item key>
                      --label "<short name>" --skill <workflow skill> --input '<json>' [--found "<one plain line>"]
                      [--try [--sample | --real] | --test --case <skill>/<case> --expect "<path>"] [--rerun-of <wf>#<n>]
                      [--from <step id>] [--batch <run id> --loop <loop key> [--parent <item run id>]]
        Records the attempt as started in the done list (item_id.py), writes the item's run trace header and the
        request's "forked →" step. Prints {"run": "<wf>-a<n>"}.
        --found: what the trigger found, for this item, in one plain line ("Found a Savills email about a Stratford
        bid deadline"): who sent it or where it is from, and what it is about. The run page shows it as the first row
        of the steps ("How it started"); without it, the item's label.
        --try: a new workflow's try on real data (reads real, every send held back): never counts as handled, shown
        on the Inbox with real work, tagged as a try.
        --real (with --try): a try for real, the user's choice when the try starts: every step runs, saves, writes,
        creates and sends included (test mode stays off). It counts as handled, so the first run after publishing
        doesn't do the same items again; still tagged as a try, and its recordings still become the tests.
        --sample (with --try): the item is a sample (from the workflow's own examples, or a real public one that fits
        a path); its steps still run for real where they can, with every send held back (test mode --live). Recorded
        like a try, marked as a sample, so a real recording of the same
        path later takes over its test.

    run_item.py batch <request id> --entry <trigger id> --skill <workflow skill> --label "<what the run covers>"
                      [--try [--real] | --test]
        A run of a workflow that has a loop (its Definition's `loop:` line; core-architect rule 33): before its items,
        opens the run's own trace, which holds the steps that run once (the combine and everything after it) and the
        run's outcome. Prints {"run": "run-<request>-<trigger>"}. Each item of the loop is then started with
        `start … --batch <that run> --loop <loop key>` (an inner loop's item adds --parent <the outer item's run>),
        and the once steps are logged with `line <that run>`. End it last, after every item and the once steps.

    run_item.py end <wf>-a<n> --status done|review|action|needs_user '<end json>' [--path "<path label>"]
                    [--systems '["outlook","slack"]'] [--result pass|fail]
        Writes the run's end line, records how it ended, and (a real run or a try, with --path) saves what it read as
        a recording for the workflow's tests (recording.py). A test replay is never recorded; a sample is, marked.
        It also writes --path on the end line ("path"), so the run reviewer (core-run-reviewer) knows which path the
        run says it took. The end JSON's "deviations" ([{"step", "planned", "did", "why"}]) are the changes the run
        knowingly made. Nothing here judges the run: the reviewer does that afterwards, on its own.

Every command prints JSON; an error says what to fix.
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402
import path_check  # noqa: E402

ITEM_ID = None
for cand in (os.path.join(paths.SKILLS, "core-dispatcher", "item_id.py"),
             os.path.join(paths.USER_SKILLS, "core-dispatcher", "item_id.py")):
    if os.path.isfile(cand):
        ITEM_ID = cand
        break


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fail(msg):
    print(json.dumps({"error": msg}))
    sys.exit(1)


def is_batch(run):
    """A run of a loop workflow as a whole (run_item.py batch): its trace sits with the item runs."""
    return run.startswith("run-")


def trace(run):
    folder = paths.RUNS if run.startswith("wf-") or is_batch(run) else paths.REQUESTS
    return os.path.join(folder, run + ".jsonl")


def lines(run):
    try:
        with open(trace(run), encoding="utf-8") as fh:
            return [json.loads(x) for x in fh if x.strip()]
    except (OSError, ValueError):
        return []


_DEFS = {}
obj_warn = {}


def workflow_of(run):
    """The board definition of an item run's workflow (by its header's skill), or None."""
    if not (run.startswith("wf-") or is_batch(run)):
        return None
    hdr = next((x for x in lines(run) if x.get("header")), None)
    skill = (hdr or {}).get("skill")
    if not skill:
        return None
    if "W" not in _DEFS:
        _DEFS["W"] = path_check.load_defs()
    return path_check.find_def(_DEFS["W"], skill) if _DEFS["W"] else None


def stamp(run, obj):
    """Adds "wstep" (the workflow step's key) to a step line of an item run; returns a warning or None."""
    if obj.get("header") or obj.get("end") or "entry_match" in obj or obj.get("key"):
        return None
    if "wstep" in obj and obj["wstep"] is None:
        return None
    defn = workflow_of(run)
    if not defn:
        return None
    steps = defn.get("steps", [])
    keys = {st.get("key") for st in steps}
    if obj.get("wstep"):
        if obj["wstep"] in keys:
            obj.pop("unmatched", None)
            return None
        bad = obj.pop("wstep")
        obj["unmatched"] = True
        return f"{bad!r} is no step key of workflow {defn.get('id')!r}; use one of {sorted(k for k in keys if k)}"
    hit = next((st for st in steps if path_check.same_title(st, obj)), None)
    if hit:
        obj["wstep"] = hit["key"]
        obj.pop("unmatched", None)
        return None
    obj["unmatched"] = True
    titles = [st.get("title") for st in steps if st.get("title")]
    return (f"step {obj.get('step') or obj.get('title')!r} is no step of workflow {defn.get('id')!r}, so the board "
            f"can't place it: name it as one of {titles}, or add \"wstep\": null if it is not a workflow step")


def unmatched(run):
    """The step lines of a run that matched no workflow step."""
    return [x.get("step") or x.get("title") for x in lines(run) if x.get("unmatched")]


def append(run, obj, rebuild=True):
    path = trace(run)
    if not os.path.exists(path) and not obj.get("header"):
        fail(f"no trace {paths.rel(path)}: start it first")
    if not obj.get("header"):
        obj = dict(obj)
        obj.setdefault("t", now())
        if not obj.get("end") and "entry_match" not in obj and not obj.get("id"):
            n = sum(1 for x in lines(run) if x.get("id"))
            obj["id"] = f"s{n + 1}"
        warn = stamp(run, obj)
        if warn:
            obj_warn[run] = warn
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
    if rebuild:
        subprocess.run([sys.executable, "-I", os.path.join(HERE, "build_board.py")], capture_output=True)
    return obj


def parse(text):
    try:
        v = json.loads(text)
    except ValueError as e:
        fail(f"not valid JSON ({e}): {text[:120]}")
    if not isinstance(v, dict):
        fail("expected a JSON object")
    return v


def item_id(*args):
    if not ITEM_ID:
        fail("item_id.py not found next to core-dispatcher")
    r = subprocess.run([sys.executable, "-I", ITEM_ID, *args], capture_output=True, text=True)
    if r.returncode:
        fail("item_id.py: " + (r.stderr or r.stdout).strip()[-300:])


def loop_key(skill, given):
    """The loop an item goes round, as its key: given as the key, its title ("For each story") or what one item is
    ("story"); left out when the workflow has one loop. None when the workflow has no such loop."""
    if "W" not in _DEFS:
        _DEFS["W"] = path_check.load_defs()
    d = path_check.find_def(_DEFS["W"], skill) if _DEFS["W"] else None
    loops = (d or {}).get("loops") or []
    norm = lambda t: " ".join(str(t or "").lower().replace("for each", " ").split())
    if not given:
        return loops[0]["key"] if len(loops) == 1 else None
    for lp in loops:
        if norm(given) in (norm(lp.get("key")), norm(lp.get("title")), norm(lp.get("each"))):
            return lp["key"]
    return None


def tryflags(try_, real, test):
    """item_id.py's flags for a try (held back: never handled; --real: every step ran, so it counts) or a test"""
    return (["--try", "--real"] if real else ["--try"]) if try_ else (["--test"] if test else [])


def cmd_start(a):
    run = f"{a.wf}-a{a.attempt}"
    if a.batch:   # an item of a loop: its loop by key, whatever words it was given in (the board matches on the key)
        k = loop_key(a.skill, a.loop)
        if not k:
            fail(f"--loop {a.loop!r} is no loop of {a.skill}: give the loop's key, or leave it out when there is one loop")
        a.loop = k
    if os.path.exists(trace(run)):
        fail(f"{run} already has a trace: run item_id.py check again for the next attempt number")
    flags = tryflags(a.try_, a.real, a.test)
    for k in ("case", "expect", "rerun_of"):
        if getattr(a, k):
            flags += ["--" + k.replace("_", "-"), getattr(a, k)]
    item_id("record", a.wf, "--status", "started", "--attempt", str(a.attempt), "--run", a.request, "--trace",
            run + ".jsonl", "--entry", a.entry, "--item", a.item, "--label", a.label, "--skill", a.skill,
            "--input", a.input or "{}", *flags)
    req = lines(a.request)
    hdr = next((x for x in req if x.get("header")), {})
    append(run, {"header": True, "run": run, "kind": "run", "group": a.request, "wf": a.wf, "item": a.item,
                 "attempt": a.attempt, "label": a.label, "request": hdr.get("request", ""), "started": now(),
                 "entry": a.entry, "skill": a.skill, "try": bool(a.try_), "test": bool(a.test),
                 **({"try_real": True} if a.try_ and a.real else {}),
                 **({"sample": True} if a.sample else {}),
                 **({"rerun_of": a.rerun_of} if a.rerun_of else {}),
                 **({"batch": a.batch, "loop": a.loop or ""} if a.batch else {}),
                 **({"parent": a.parent} if a.parent else {})}, rebuild=False)
    last = [x.get("id") for x in req if x.get("id")]
    append(a.request, {"from": a.from_ or (last[-1] if last else None), "entry": a.entry if a.entry not in ("direct",) else None,
                       "type": "Handed Off", "step": f"forked → {run}", "label": a.label, "skill": a.skill,
                       "result": f"Sent {a.label} to {a.skill}", "status": "done",
                       "because": ("A sample item: its steps run for real where they can; nothing is sent" if a.sample
                                   else "A try for real: every step runs, sends and saves included" if a.try_ and a.real
                                   else "A try as a test: real data, nothing sent" if a.try_ else "Its own run"),
                       "trigger": "new item", "why": "item_id check: run",
                       **({"found": a.found} if a.found else {})})
    print(json.dumps({"run": run}))


def cmd_queue(a):
    try:
        items = json.loads(a.items)
    except ValueError as e:
        fail(f"--items is not valid JSON ({e})")
    flags = tryflags(a.try_, a.real, a.test)
    for it in items:
        for k in ("wf", "item", "label"):
            if not it.get(k):
                fail(f"each item needs {k!r}: {json.dumps(it)[:120]}")
        item_id("record", it["wf"], "--status", "queued", "--run", a.request, "--entry", a.entry, "--item", it["item"],
                "--label", it["label"], "--skill", a.skill, "--input", json.dumps(it.get("input") or {}), *flags)
    subprocess.run([sys.executable, "-I", os.path.join(HERE, "build_board.py")], capture_output=True)
    print(json.dumps({"queued": len(items)}))


def cmd_batch(a):
    req = lines(a.request)
    hdr = next((x for x in req if x.get("header")), None)
    if not hdr:
        fail(f"no request trace {a.request}: the hooks open it when the request is sent")
    run = "run-" + a.request.replace("dispatch-", "") + "-" + "".join(c if c.isalnum() else "-" for c in a.entry)
    if os.path.exists(trace(run)):
        print(json.dumps({"run": run, "note": "already open"}))
        return
    if "W" not in _DEFS:
        _DEFS["W"] = path_check.load_defs()
    d = path_check.find_def(_DEFS["W"], a.skill) if _DEFS["W"] else None
    if d is not None and not d.get("loops"):
        fail(f"workflow {a.skill} has no loop: run its items with start alone")
    append(run, {"header": True, "run": run, "kind": "batch", "group": a.request, "entry": a.entry, "skill": a.skill,
                 "flow": (d or {}).get("id", ""), "label": a.label, "request": hdr.get("request", ""), "started": now(),
                 "try": bool(a.try_), "test": bool(a.test), **({"try_real": True} if a.try_ and a.real else {})})
    print(json.dumps({"run": run}))


def cmd_end(a):
    tl = lines(a.run)
    hdr = next((x for x in tl if x.get("header")), None)
    if not hdr:
        fail(f"no trace for {a.run}: start it first")
    if hdr.get("kind") == "batch":   # a loop workflow's run as a whole: its items record themselves
        end = parse(a.end)
        end["end"] = True
        end["status"] = a.status
        append(a.run, end)
        out = {"ended": a.run, "status": a.status}
        um = unmatched(a.run)
        if um:
            out["unmatched"] = um
            out["warning"] = f"{len(um)} step(s) matched no workflow step: " + "; ".join(map(str, um))
        print(json.dumps(out, ensure_ascii=False))
        return
    end = parse(a.end)
    end["end"] = True
    if a.path:
        end["path"] = a.path
    append(a.run, end, rebuild=False)
    if not hdr.get("wf"):   # a request (its trigger ran nothing, or only linked): no item to record
        subprocess.run([sys.executable, "-I", os.path.join(HERE, "build_board.py")], capture_output=True)
        print(json.dumps({"ended": a.run, "status": a.status}, ensure_ascii=False))
        return
    flags = tryflags(hdr.get("try"), hdr.get("try_real"), hdr.get("test"))
    if a.result:
        flags += ["--result", a.result]
    item_id("record", hdr["wf"], "--status", a.status, "--attempt", str(hdr["attempt"]), "--run", hdr["group"],
            "--trace", a.run + ".jsonl", "--entry", hdr.get("entry", ""), "--item", hdr["item"], "--label",
            hdr.get("label", ""), "--skill", hdr.get("skill", ""), *flags)
    rec = None
    if a.path and not hdr.get("test"):
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "recording.py"), "workflow", hdr.get("skill", ""),
                            "--run", a.run, "--path", a.path, "--systems", a.systems or "{}",
                            *(["--sample"] if hdr.get("sample") else [])], capture_output=True, text=True)
        try:
            rec = json.loads(r.stdout)
        except ValueError:
            rec = {"error": (r.stderr or r.stdout).strip()[-200:]}
    subprocess.run([sys.executable, "-I", os.path.join(HERE, "build_board.py")], capture_output=True)
    out = {"ended": a.run, "status": a.status, "recording": rec}
    um = unmatched(a.run)
    if um:
        out["unmatched"] = um
        out["warning"] = (f"{len(um)} step(s) matched no workflow step, so the board shows them as skipped: "
                          + "; ".join(map(str, um)))
    print(json.dumps(out, ensure_ascii=False))


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    ln = sub.add_parser("line")
    ln.add_argument("run")
    ln.add_argument("json")
    s = sub.add_parser("start")
    s.add_argument("request")
    for k in ("--wf", "--entry", "--item", "--label", "--skill"):
        s.add_argument(k, required=True)
    s.add_argument("--attempt", type=int, required=True)
    s.add_argument("--input", default="{}")
    s.add_argument("--try", dest="try_", action="store_true")
    s.add_argument("--real", action="store_true")
    s.add_argument("--sample", action="store_true")
    s.add_argument("--test", action="store_true")
    s.add_argument("--case")
    s.add_argument("--expect")
    s.add_argument("--rerun-of", dest="rerun_of")
    s.add_argument("--from", dest="from_")
    s.add_argument("--found", default="")
    s.add_argument("--batch", default="")
    s.add_argument("--loop", default="")
    s.add_argument("--parent", default="")
    b = sub.add_parser("batch")
    b.add_argument("request")
    for k in ("--entry", "--skill", "--label"):
        b.add_argument(k, required=True)
    b.add_argument("--try", dest="try_", action="store_true")
    b.add_argument("--real", action="store_true")
    b.add_argument("--test", action="store_true")
    q = sub.add_parser("queue")
    q.add_argument("request")
    q.add_argument("--entry", required=True)
    q.add_argument("--skill", required=True)
    q.add_argument("--items", required=True)
    q.add_argument("--try", dest="try_", action="store_true")
    q.add_argument("--real", action="store_true")
    q.add_argument("--test", action="store_true")
    e = sub.add_parser("end")
    e.add_argument("run")
    e.add_argument("--status", required=True, choices=["done", "review", "action", "needs_user"])
    e.add_argument("end")
    e.add_argument("--path")
    e.add_argument("--systems")
    e.add_argument("--result", choices=["pass", "fail"])
    a = ap.parse_args(argv)
    if a.cmd == "line":
        out = {"wrote": append(a.run, parse(a.json))}
        if obj_warn.get(a.run):
            out["warning"] = obj_warn[a.run]
        print(json.dumps(out, ensure_ascii=False))
    elif a.cmd == "start":
        cmd_start(a)
    elif a.cmd == "queue":
        cmd_queue(a)
    elif a.cmd == "batch":
        cmd_batch(a)
    else:
        cmd_end(a)


if __name__ == "__main__":
    main(sys.argv[1:])
