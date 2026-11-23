#!/usr/bin/env python3
"""Repeatable item IDs and the processed-items ledger for the work dispatcher.

Every item gets the same workflow ID every time it is seen:
    item key    = <entry id>:<source ID>          e.g. email:1a1caf1595ab6954
    workflow ID = wf- + first 8 hex of sha256(key) e.g. wf-7c1e04ab

Data lives where paths.py says (created on first use): .claude/workflow-ui/dispatcher-data/ in-project, or the
project's .workflow-manager-data/ when installed as a plugin (history/done-list.jsonl, config/settings.json):
    ledger.jsonl   one line per attempt event (started, then its final status), plus "pulled" (pulled in, not
                   run yet), "skipped" (the user said not to run it), and the Inbox page's manual lines
                   ("marked_done", "marked_needs", "deleted"); none of these are attempts
    settings.json  {"skip_done": true, "auto_approve": true}  -- the board's "Run each item once" and
                   "Approve automatically" switches (both on when missing)

Commands (all print one JSON object):
    item_id.py check <entry> <source-id> [--fingerprint]
        -> wf, item, attempt (next number), last (latest ledger line or null),
           skip_done, action ("run" or "link") and why. A pulled item is "run" (it never ran); a
           skipped one is always "link"
    item_id.py record <wf> --status S --run R --entry E --item K [--attempt N] [--trace T]
                      [--label L] [--skill S] [--input JSON] [--rerun-of WF#N]
        status: started, done, review, action, needs_user, or pulled / queued / skipped (no trace, not an attempt;
                queued: kept by a run that is about to run it, so the Inbox shows it at once)
        -> appends a ledger line with the current UTC time
    item_id.py lookup <wf>     -> latest ledger line for that workflow (with its input), or null
    item_id.py latest <entry>  -> the newest real (not test) item a trigger found, with its saved input, or null
  record --test marks a test run: kept in the ledger for the board, never counted as handled.
  record --test --case <skill>/<case> --expect <path label>: a test case and the path it should take.
  record --status started also stores the skill's version (v1, v2, ...) from the hidden skill history.
    item_id.py setting [--skip-done on|off] [--auto-approve on|off]
        -> {"skip_done": true|false, "auto_approve": true|false}; with a flag, sets that switch first
    item_id.py mark <wf>... --to done|needs|notrun|skipped --run R
        -> a hand-made done-list line per item ("marked_done", "marked_needs", "pulled", "skipped"; "manual": true)
    item_id.py delete <wf>... --run R
        -> a "deleted" line per item, and its run traces moved to the traces folder's .trash/ (kept, not erased)
    item_id.py delete-request <request ID>... --run R
        -> a request that ran no item (a "Nothing new" row: its trigger kept nothing, or all was already handled)
           off the board: its trace moved to .trash/. A request that ran items is refused: delete those instead
  mark, delete and setting are what the Inbox page's status menu, Delete row and "Run each item once" switch
  copy as chat commands; the page never writes these itself.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "workflow-ui", "scripts")))
try:
    import paths  # where the data lives: in-project or plugin
    LEDGER, SETTINGS = paths.DONE_LIST, paths.SETTINGS
    DATA = os.path.dirname(LEDGER)
    OPEN_RUN = os.path.join(paths.LIVE, "current")  # the dispatcher run open now
except ImportError:  # no board installed: keep the data next to where it always was
    DATA = os.path.normpath(os.path.join(HERE, "..", "..", "workflow-ui", "dispatcher-data"))
    OPEN_RUN = os.path.normpath(os.path.join(DATA, "..", "traces", ".live", "current"))
    LEDGER = os.path.join(DATA, "ledger.jsonl")
    SETTINGS = os.path.join(DATA, "settings.json")
FINISHED = {"done", "review", "action", "needs_user"}  # an attempt that ended or is waiting on the user
NOT_ATTEMPTS = {"pulled", "queued", "skipped", "marked_done", "marked_needs", "deleted"}  # not a run of the item
# marked_done / marked_needs / deleted: set by hand, from the chat commands the Inbox page copies (mark, delete)
STILL_RUNNING_SECONDS = 3600                           # cap: a "started" attempt older than this is stalled
WF = re.compile(r"^wf-[0-9a-f]{8}$")
REQ = re.compile(r"^dispatch-[0-9a-z-]+$")   # a request: one time the dispatcher was fired


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def age_seconds(iso):
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - t).total_seconds()


def item_key(entry, source, fingerprint=False):
    entry = re.sub(r"\s+", "-", entry.strip().lower())
    source = re.sub(r"\s+", " ", source.strip())
    if fingerprint:
        source = "fp:" + source.lower()
    if not entry or not source or source == "fp:":
        raise SystemExit(json.dumps({"error": "entry and source ID are both needed"}))
    return f"{entry}:{source}"


def wf_id(key):
    return "wf-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]


def skip_done():
    try:
        with open(SETTINGS, encoding="utf-8") as fh:
            return bool(json.load(fh).get("skip_done", True))
    except (OSError, ValueError, AttributeError):
        return True  # default: on


def auto_approve():
    """The board's "Approve automatically" switch: a real run's "Send it?" steps are answered yes."""
    try:
        with open(SETTINGS, encoding="utf-8") as fh:
            return bool(json.load(fh).get("auto_approve", True))
    except (OSError, ValueError, AttributeError):
        return True  # default: on


def open_run():
    """The dispatcher run that is open right now (kept by the board's hooks), or None."""
    try:
        with open(OPEN_RUN, encoding="utf-8") as fh:
            return json.load(fh).get("run")
    except (OSError, ValueError, AttributeError):
        return None


def history(wf, with_tests=False):
    """The done-list lines for one item. Tests and tries never count as handled, so they are left out, except
    when numbering attempts (with_tests): a try and a later real run of the same item each get their own trace."""
    rows = []
    try:
        with open(LEDGER, encoding="utf-8") as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict) and obj.get("wf") == wf and (with_tests or not obj.get("test")):
                    rows.append(obj)   # test runs never count as handled
    except OSError:
        pass
    return rows


def decide(last, skip):
    if last is None:
        return "run", "new item"
    status = last.get("status")
    if status == "skipped":
        return "link", "skipped by the user"
    if status in ("marked_done", "marked_needs"):
        return "link", "marked " + ("done" if status == "marked_done" else "as needing you") + " by the user"
    if status == "deleted":
        return "run", "the user deleted its row, so it is new again"
    if status == "pulled":
        return "run", "pulled in earlier, not run yet"
    if status == "queued":
        return "run", "queued by a run that stopped before it got to it"
    age = age_seconds(last.get("t"))
    # "started" only counts as running while its own dispatcher run is still open;
    # an attempt left by an interrupted run is stalled, not running
    if (status == "started" and age is not None and age < STILL_RUNNING_SECONDS
            and last.get("run") and last.get("run") == open_run()):
        return "link", "an attempt is still running"
    if not skip:
        return "run", "Run each item once is off"
    if status in FINISHED:
        return "link", f"already handled ({status})"
    return "run", "earlier attempt never finished"


def cmd_check(a):
    key = item_key(a.entry, a.source, a.fingerprint)
    wf = wf_id(key)
    rows = history(wf)
    last = rows[-1] if rows else None
    skip = skip_done()
    action, why = decide(last, skip)
    attempt = max([r.get("attempt", 0) for r in history(wf, True) if r.get("status") not in NOT_ATTEMPTS] or [0]) + 1
    return {"wf": wf, "item": key, "key_kind": "fingerprint" if a.fingerprint else "source",
            "attempt": attempt, "last": last, "skip_done": skip, "action": action, "why": why}


def skill_version(skill):
    """The skill's current version from the hidden skill history (unsaved changes are saved first), or None."""
    try:
        import skill_history
        return skill_history.current(skill)
    except (Exception, SystemExit):  # no history installed, or git missing: the run is still recorded
        return None


def cmd_record(a):
    if not WF.match(a.wf):
        raise SystemExit(json.dumps({"error": "bad workflow ID"}))
    if a.status not in NOT_ATTEMPTS and (not a.trace or not a.attempt):
        raise SystemExit(json.dumps({"error": "an attempt needs --attempt and --trace"}))
    row = {"t": now_iso(), "wf": a.wf, "item": a.item, "entry": a.entry, "attempt": a.attempt,
           "status": a.status, "run": a.run, "trace": a.trace}
    for k in ("label", "skill", "rerun_of", "case", "expect", "result"):
        v = getattr(a, k)
        if v:
            row[k] = v
    if a.status == "started" and a.skill:   # tests too: a path passes "on v3"
        v = skill_version(a.skill)
        if v:
            row["version"] = v   # the skill's version this run used (skill_history.py)
            if v.endswith("+draft"):   # a run on a draft: which iteration of it, so the next run can be compared
                try:
                    import skill_history
                    n = skill_history.iteration(a.skill)
                    if n:
                        row["iteration"] = n
                except (Exception, SystemExit):
                    pass
    real = getattr(a, "try_", False) and getattr(a, "real", False)
    if a.test or (getattr(a, "try_", False) and not real):
        row["test"] = True   # never counts as handled: the real run still happens
    if getattr(a, "try_", False):
        row["try"] = True    # a new workflow's try on real data (reads real, sends nothing): shown with real work
    if real:
        row["try_real"] = True   # a try for real: every step ran, so it counts as handled like any real run
    if a.input:
        try:
            row["input"] = json.loads(a.input)
        except ValueError:
            row["input"] = a.input
    os.makedirs(DATA, exist_ok=True)
    with open(LEDGER, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row) + "\n")
    return {"ok": True, "recorded": row}


def cmd_lookup(a):
    rows = history(a.wf)
    if not rows:
        return None
    last = dict(rows[-1])
    for r in reversed(rows):  # the input is saved on the "started" line; carry it forward
        if "input" in r:
            last.setdefault("input", r["input"])
            last.setdefault("label", r.get("label"))
            last.setdefault("skill", r.get("skill"))
            break
    last["attempts"] = max([r.get("attempt", 0) for r in rows if r.get("status") not in NOT_ATTEMPTS] or [0])
    return last


def cmd_latest(a):
    """The newest real item a trigger found, with the input it was handed over with."""
    newest = None
    try:
        with open(LEDGER, encoding="utf-8") as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict) and obj.get("entry") == a.entry and "input" in obj and not obj.get("test"):
                    newest = obj
    except OSError:
        pass
    return cmd_lookup(argparse.Namespace(wf=newest["wf"])) if newest else None


MARK = {"done": "marked_done", "needs": "marked_needs", "notrun": "pulled", "skipped": "skipped"}


def manual_row(wf, status, run, with_tests=False):
    """A line set by hand: carries the item's own key, trigger, label and skill from its latest line.
    with_tests (delete only): an item that only ever ran as a try or a test is found too, and its line keeps
    the test / try flags, so it never counts as handled and a later real run still runs it."""
    rows = history(wf)
    tried = False
    if not rows and with_tests:
        rows = history(wf, with_tests=True)
        tried = bool(rows)
    last = rows[-1] if rows else {}
    row = {"t": now_iso(), "wf": wf, "item": last.get("item", ""), "entry": last.get("entry", ""),
           "status": status, "run": run, "trace": "", "manual": True}
    if tried:
        row["test"] = True
        if any(r.get("try") for r in rows):
            row["try"] = True
    for r in reversed(rows):
        for k in ("label", "skill"):
            if r.get(k) and k not in row:
                row[k] = r[k]
    return row, bool(rows)


def append(rows):
    os.makedirs(DATA, exist_ok=True)
    with open(LEDGER, "a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def cmd_mark(a):
    bad = [w for w in a.wf if not WF.match(w)]
    if bad:
        raise SystemExit(json.dumps({"error": "bad workflow ID", "ids": bad}))
    out, missing = [], []
    for w in a.wf:
        row, known = manual_row(w, MARK[a.to], a.run)
        (out if known else missing).append(row if known else w)
    append(out)
    return {"ok": True, "marked": [r["wf"] for r in out], "as": MARK[a.to], "not_found": missing}


def trace_dirs():
    try:
        return list(paths.TRACE_DIRS)   # every folder holding traces
    except NameError:                    # no board installed
        return [os.path.normpath(os.path.join(DATA, "..", "traces"))]


def to_trash(d, name):
    trash = os.path.join(d, ".trash")
    os.makedirs(trash, exist_ok=True)
    dest = os.path.join(trash, name)
    if os.path.exists(dest):
        dest = os.path.join(trash, f"{int(os.path.getmtime(os.path.join(d, name)))}-{name}")
    shutil.move(os.path.join(d, name), dest)


def ran_items(req):
    """The item runs a request started (their traces' header "group"), so it isn't deleted out from under them."""
    out = []
    for d in trace_dirs():
        if not os.path.isdir(d):
            continue
        for name in os.listdir(d):
            if not re.match(r"wf-[0-9a-f]{8}-a\d+\.jsonl$", name):
                continue
            try:
                with open(os.path.join(d, name), encoding="utf-8") as fh:
                    head = json.loads(fh.readline() or "{}")
            except (OSError, ValueError):
                continue
            if head.get("group") == req:
                out.append(name[:-6])
    return out


def cmd_delete_request(a):
    bad = [r for r in a.req if not REQ.match(r)]
    if bad:
        raise SystemExit(json.dumps({"error": "bad request ID (dispatch-…)", "ids": bad}))
    moved, refused, missing = [], {}, []
    for r in a.req:
        runs = ran_items(r)
        if runs:
            refused[r] = runs
            continue
        hit = [d for d in trace_dirs() if os.path.isfile(os.path.join(d, r + ".jsonl"))]
        for d in hit:
            to_trash(d, r + ".jsonl")
        (moved if hit else missing).append(r)
    return {"ok": True, "deleted_requests": moved, "refused_ran_items": refused, "not_found": missing}


def cmd_delete(a):
    bad = [w for w in a.wf if not WF.match(w)]
    if bad:
        raise SystemExit(json.dumps({"error": "bad workflow ID", "ids": bad}))
    try:
        traces = list(paths.TRACE_DIRS)   # every folder holding traces
    except NameError:                      # no board installed
        traces = [os.path.normpath(os.path.join(DATA, "..", "traces"))]
    out, moved, missing = [], [], []
    for w in a.wf:
        row, known = manual_row(w, "deleted", a.run, with_tests=True)
        if not known:
            missing.append(w)
            continue
        out.append(row)
        for d in traces:
            if not os.path.isdir(d):
                continue
            for name in sorted(os.listdir(d)):
                if re.match(re.escape(w) + r"-a\d+\.jsonl$", name):
                    trash = os.path.join(d, ".trash")
                    os.makedirs(trash, exist_ok=True)
                    dest = os.path.join(trash, name)
                    if os.path.exists(dest):
                        dest = os.path.join(trash, f"{int(os.path.getmtime(os.path.join(d, name)))}-{name}")
                    shutil.move(os.path.join(d, name), dest)
                    moved.append(name)
    append(out)
    return {"ok": True, "deleted": [r["wf"] for r in out], "traces_moved": moved, "not_found": missing}


def cmd_setting(a):
    if a.skip_done or a.auto_approve:
        current = {}
        try:
            with open(SETTINGS, encoding="utf-8") as fh:
                current = json.load(fh)
        except (OSError, ValueError):
            pass
        if not isinstance(current, dict):
            current = {}
        if a.skip_done:
            current["skip_done"] = a.skip_done == "on"
        if a.auto_approve:
            current["auto_approve"] = a.auto_approve == "on"
        os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
        tmp = SETTINGS + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(current, fh)
        os.replace(tmp, SETTINGS)
    return {"skip_done": skip_done(), "auto_approve": auto_approve()}


def main(argv):
    p = argparse.ArgumentParser(description="Repeatable item IDs and ledger for the work dispatcher")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("entry")
    c.add_argument("source")
    c.add_argument("--fingerprint", action="store_true")
    r = sub.add_parser("record")
    r.add_argument("wf")
    for k in ("status", "run", "entry", "item"):
        r.add_argument("--" + k, required=True)
    r.add_argument("--trace", default="")
    r.add_argument("--try", dest="try_", action="store_true", help="a new workflow's try on real data: reads real, every write held back")
    r.add_argument("--real", action="store_true", help="with --try: a try for real, every step ran (counts as handled)")
    r.add_argument("--attempt", type=int, default=0)
    for k in ("label", "skill", "input", "rerun-of", "case", "expect", "result"):
        r.add_argument("--" + k)
    r.add_argument("--test", action="store_true")
    lk = sub.add_parser("lookup")
    lk.add_argument("wf")
    lt = sub.add_parser("latest")
    lt.add_argument("entry")
    st = sub.add_parser("setting")
    st.add_argument("--skip-done", choices=["on", "off"])
    st.add_argument("--auto-approve", choices=["on", "off"])
    mk = sub.add_parser("mark")
    mk.add_argument("wf", nargs="+")
    mk.add_argument("--to", required=True, choices=sorted(MARK))
    mk.add_argument("--run", required=True)
    dl = sub.add_parser("delete")
    dl.add_argument("wf", nargs="+")
    dl.add_argument("--run", required=True)
    dq = sub.add_parser("delete-request")
    dq.add_argument("req", nargs="+")
    dq.add_argument("--run", required=True)
    a = p.parse_args(argv)
    out = {"check": cmd_check, "record": cmd_record, "lookup": cmd_lookup, "latest": cmd_latest,
           "setting": cmd_setting, "mark": cmd_mark, "delete": cmd_delete,
           "delete-request": cmd_delete_request}[a.cmd](a)
    print(json.dumps(out))


if __name__ == "__main__":
    main(sys.argv[1:])
