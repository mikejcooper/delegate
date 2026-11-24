#!/usr/bin/env python3
"""Publish board data for the trace board from .claude/workflow-ui/traces/*.jsonl and the table in .claude/skills/manager-work-dispatcher/SKILL.md.

Read-only: it never changes a trace. It writes board-data.js, which the static workflows.html
re-loads every second, so the page updates live without reloading.
    python3 .claude/workflow-ui/scripts/build_board.py           build once
    python3 .claude/workflow-ui/scripts/build_board.py --watch   rebuild every second
"""
import glob
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402  where code and data live (in-project or plugin)
TRACE_DIRS = paths.TRACE_DIRS
ENTRIES = os.path.join(paths.SKILLS, "core-dispatcher", "SKILL.md")
OUT = paths.BOARD_JS
STALL_SECONDS = 300


def parse_time(value):
    """Return epoch seconds, or None. Accepts 'Z' suffix; naive times are local."""
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.astimezone(timezone.utc).timestamp()


def load_entries():
    """Every trigger: trigger skills in both layers (see entries.py)."""
    try:
        import entries
        return [{"id": e["id"], "label": e["label"], "triggers": e["triggers"], "layer": e["layer"],
                 "workflow": e["skill"], "run_all": e.get("run_all", True)} for e in entries.load()]
    except Exception:
        return []


def load_settings():
    """The "Run each item once" and "Approve automatically" switches; on when missing or unreadable."""
    try:
        with open(paths.SETTINGS, encoding="utf-8") as fh:
            obj = json.load(fh)
        return {"skip_done": bool(obj.get("skip_done", True)),
                "auto_approve": bool(obj.get("auto_approve", True))}
    except (OSError, ValueError, AttributeError):
        return {"skip_done": True, "auto_approve": True}


def load_ledger():
    """Dispatcher done list, one dict per line. Saved inputs are kept, each value cut to 300 characters, for the
    Inbox page's "what it will be given" preview (they hold only the short details handed over)."""
    rows = []
    try:
        with open(paths.DONE_LIST, encoding="utf-8") as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    inp = obj.get("input")
                    if isinstance(inp, dict):
                        obj["input"] = {str(k): str(v)[:300] for k, v in list(inp.items())[:12]}
                    else:
                        obj.pop("input", None)
                    rows.append(obj)
    except OSError:
        pass
    return rows


def load_run(path, now, open_id=None):
    header, steps, end, match, bad = {}, [], None, None, 0
    matches = []  # every trigger line, in order: a request may use several triggers
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            if not isinstance(obj, dict):
                bad += 1
            elif obj.get("header"):
                header = obj
            elif obj.get("end"):
                end = obj
            elif "entry_match" in obj:
                matches.append(obj)
                match = match or obj
            else:
                steps.append(obj)
    run_id = header.get("run") or os.path.splitext(os.path.basename(path))[0]
    last = steps[-1] if steps else {}
    last_time = parse_time((end or last or match or {}).get("t")) or parse_time(header.get("started"))
    started = parse_time(header.get("started")) or last_time
    # stage: scanning (no entry decision yet) -> running / waiting / stalled -> done
    if end:
        state = "done"
    elif last.get("status") == "needs_user":
        state = "waiting"
    elif last_time and now - last_time > STALL_SECONDS and not (open_id and open_id in (run_id, header.get("group"))):
        # quiet for a while and not part of the dispatcher run that is open now: it stopped
        state = "stalled"
    elif match is None and "entry" not in header and header.get("kind") != "run":
        # A workflow ("kind":"run") never gets its own entry line: its trigger made that decision.
        state = "scanning"
    else:
        state = "running"
    counts = {"done": 0, "skipped": 0, "uncertain": 0, "failed": 0, "needs_user": 0}
    for s in steps:
        if s.get("status") in counts:
            counts[s["status"]] += 1
    # how long the run took: its end line minus its start (both written by the clock, so reliable), and how much of
    # that was spent waiting on the user (from a step marked needs_user to the next line after it)
    end_time = parse_time((end or {}).get("t"))
    took = round(end_time - started) if end_time and started and end_time >= started else None
    if took is not None and took < 2:
        took = None   # start and end written in the same second: the trace was logged after the fact, so not timed
    waited, lines = 0, steps + ([end] if end else [])
    for i, s in enumerate(lines[:-1]):
        if isinstance(s, dict) and s.get("status") == "needs_user":
            a, b = parse_time(s.get("t")), parse_time(lines[i + 1].get("t"))
            if a and b and b > a:
                waited += b - a
    live = None  # the hooks' "now doing" note (<live folder>/<run>.json), only while the run is open
    if not end:
        try:
            with open(os.path.join(paths.LIVE, run_id + ".json"), encoding="utf-8") as fh:
                live = json.load(fh)
        except (OSError, ValueError):
            live = None
    entry = None
    if match is not None:
        entry = match.get("entry_match")
    elif header.get("entry"):
        entry = header["entry"]
    sched = next((x for x in steps if x.get("type") == "Scheduled"), None) or {}   # schedules.py window's line
    return {
        "id": run_id,
        "group": header.get("group") or run_id,
        "kind": header.get("kind", ""),
        "file": os.path.basename(path),
        "label": header.get("label") or run_id,
        "try": bool(header.get("try")),
        "try_real": bool(header.get("try_real")),  # a try for real: every step ran, sends and saves included
        "sample": bool(header.get("sample")),      # a try on a sample from the workflow's own examples: nothing real read
        "named": header.get("trigger", ""),        # the trigger the request's phrase names (known before its match line)            # a try of a new workflow: real reads, every send held back
        "workflow": header.get("workflow", ""),    # the board workflow a request names ("test workflow …"): the Builder follows it
        "watch": bool(header.get("watch")),
        "from": header.get("from", ""),            # where its line was copied on the board: builder, inbox, welcome
        "first": bool(header.get("first")),        # the first run, from the welcome: its Inbox row opens by itself        # a run of one workflow (a try, a test, run or rerun): watched on the Builder
        "wf": header.get("wf", ""),                # repeatable workflow ID (wf-xxxxxxxx), when the dispatcher gave one
        "item": header.get("item", ""),
        "attempt": header.get("attempt"),
        "rerun_of": header.get("rerun_of", ""),
        "batch": header.get("batch", ""),          # an item of a loop: the run of its workflow as a whole (run-…)
        "loop": header.get("loop", ""),            # which loop of the workflow it went round (core-architect rule 33)
        "parent": header.get("parent", ""),        # an inner loop's item: the outer item's run
        "flow": header.get("flow", ""),            # a loop workflow's run: the board workflow it is a run of
        "skill": header.get("skill", ""),
        "skip_done": header.get("skip_done"),      # the switch as the run read it at its start
        "auto_approve": header.get("auto_approve"),  # "Approve automatically" as the run read it at its start
        "request": header.get("request", ""),
        "note": header.get("note", ""),
        "schedule": header.get("schedule") or sched.get("schedule", ""),   # a scheduled run: its schedule ("weekdays 08:00")
        "due": header.get("due") or sched.get("due", ""),        # when it was due, if it ran late (the app was closed)
        "since": header.get("since") or sched.get("since", ""),  # how far back a late run looked
        "entry": entry,
        "entry_why": (match or {}).get("why", ""),
        "candidates": (match or {}).get("candidates", []),
        "matches": [{"entry": m.get("entry_match"), "why": m.get("why", ""), "t": m.get("t")} for m in matches],
        "state": state,
        "now": live,
        "steps": steps,
        "end": end,
        "counts": counts,
        "started": started,
        "last": last_time,
        "took": took,                              # seconds from start to end line; None while running
        "waited": round(waited) if took is not None else 0,  # of which waiting on the user
        "bad": bad,
    }


def open_run():
    """The dispatcher run the hooks hold open (<live folder>/current), or None."""
    try:
        with open(os.path.join(paths.LIVE, "current"), encoding="utf-8") as fh:
            return json.load(fh).get("run")
    except (OSError, ValueError, AttributeError):
        return None


def build():
    import build_status
    try:
        n = _build()
    except Exception as e:
        build_status.report("board", False, [f"{type(e).__name__}: {e}"])
        if "--watch" in sys.argv:
            return 0   # keep watching: the next change may fix it
        raise
    build_status.report("board", True)
    return n


def load_suggestions():
    """The run reviewer's suggestions with their latest status, and which runs it has reviewed (suggestions.py)."""
    try:
        import suggestions
        items, reviews = suggestions.current()
        return {"items": items, "reviewed": {k: {"t": v.get("t"), "count": v.get("count")} for k, v in reviews.items()}}
    except Exception:
        return {"items": [], "reviewed": {}}


def load_demo():
    """The plugin's demo workflow (workflows.json "demo"): what the welcome card on the Inbox suggests first."""
    try:
        with open(os.path.join(paths.CODE, "workflows.json"), encoding="utf-8") as fh:
            return json.load(fh).get("demo") or None
    except (OSError, ValueError):
        return None


def load_pages():
    """Pages workflows made for the user (paths.PAGES, served at /pages/), newest first."""
    out = []
    try:
        names = os.listdir(paths.PAGES)
    except OSError:
        return out
    for n in names:
        f = os.path.join(paths.PAGES, n)
        if n.endswith(".html") and os.path.isfile(f):
            out.append({"name": n, "url": "/pages/" + n, "t": os.path.getmtime(f)})
    return sorted(out, key=lambda x: -x["t"])


def plugin_version():
    """The plugin's version on disk, shown small beside its name in the top bar."""
    try:
        with open(os.path.join(paths.ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
            return json.load(fh).get("version") or ""
    except (OSError, ValueError):
        return ""


def _build():
    now = time.time()
    open_id = open_run()
    runs = [load_run(p, now, open_id) for d in TRACE_DIRS for p in sorted(glob.glob(os.path.join(d, "*.jsonl")))]
    # a workflow run left without an end line by a trigger that has ended stopped there too
    ended = {r["group"] for r in runs if r.get("kind") != "run" and r.get("state") == "done"}
    for r in runs:
        if r.get("kind") == "run" and r.get("state") in ("running", "scanning") and r["group"] in ended:
            r["state"] = "stalled"
    # the skill each run was handed to, from its trigger's "forked → <run>" step, so a run whose own
    # steps never name its workflow skill is still shown under that workflow
    via = {}
    for r in runs:
        for st in r.get("steps") or []:
            m = re.match(r"forked\s*→\s*(\S+)", st.get("step") or "")
            if m and st.get("skill"):
                via[m.group(1)] = st["skill"]
    for r in runs:
        if r.get("kind") == "run" and r["id"] in via:
            r["via"] = via[r["id"]]
    runs.sort(key=lambda r: -(r["last"] or 0))
    data = {"built": now, "version": plugin_version(), "entries": load_entries(), "runs": runs,
            "settings": load_settings(), "ledger": load_ledger(), "views_file": paths.rel(paths.VIEWS),
            "suggestions": load_suggestions(), "demo": load_demo(), "pages": load_pages()}
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("window.BOARD=" + json.dumps(data) + ";")
    os.replace(tmp, OUT)  # atomic: the page never reads a half-written file
    return len(runs)


PIDFILE = paths.WATCH_PID


def watcher_running():
    try:
        with open(PIDFILE) as fh:
            pid = int(fh.read().strip())
        os.kill(pid, 0)
        return True
    except (OSError, ValueError):
        return False


if __name__ == "__main__":
    watching = "--watch" in sys.argv
    if watching and watcher_running():
        print("Watcher already running, nothing to start")
        sys.exit(0)
    for d in TRACE_DIRS:
        os.makedirs(d, exist_ok=True)
    os.makedirs(paths.GENERATED, exist_ok=True)
    n = build()
    print(f"Wrote {OUT} ({n} runs)")
    if watching:
        with open(PIDFILE, "w") as fh:
            fh.write(str(os.getpid()))
        here = os.path.dirname(os.path.abspath(__file__))

        def code_time():   # the newest change to the board's own scripts
            return max((os.path.getmtime(p) for p in glob.glob(os.path.join(here, "*.py"))), default=0)
        started_code = code_time()
        try:
            while True:
                time.sleep(1)
                if code_time() > started_code:   # its own code changed: start again on the new code, same process
                    try:
                        os.remove(PIDFILE)
                    except OSError:
                        pass
                    os.execv(sys.executable, [sys.executable, "-I", os.path.abspath(__file__), "--watch"])
                build()
        except KeyboardInterrupt:
            pass
        finally:
            try:
                os.remove(PIDFILE)
            except OSError:
                pass
