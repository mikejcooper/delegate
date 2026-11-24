#!/usr/bin/env python3
"""Schedules: when a workflow's trigger runs on its own. The board shows them (the Overview's Schedule row, the
sidebar clock, the Inbox's next run); the app's scheduled tasks run them while the Claude app is open. A schedule is
a run setting, like the "Run each item once" switch: it is kept in the data folder (paths.SCHEDULES), never in the
skill, so setting one makes no draft and no version. The architect turns the board's lines ("schedule workflow …",
"change schedule workflow …", "pause / resume / remove schedule workflow …") into these commands and the matching
scheduled-task calls; the dispatcher asks `window` at the start of a scheduled run.

    schedules.py set <workflow> "<when>"
                         save it; prints the plan: the trigger, each scheduled task (id, cron, title) and its prompt
    schedules.py pause|resume|remove <workflow>
                         prints the task ids to pause, resume or delete
    schedules.py list    every schedule, with its next run
    schedules.py window <trigger> [--now ISO]
                         for a scheduled run: when it was due, whether it is late, and how far back to look
                         (the last finished run of that trigger; none: 24 hours)

<workflow> is its name as the board copies it (property-broker-alert), its skill name, or its trigger id.
<when>: "weekdays 08:00", "every day 12:00 17:30", "mon thu 08:00", "every 2 hours 08:00-18:00", or once:
"today 18:07", "tomorrow 09:00", "2026-11-20 09:00" (kept as "once 2026-11-20 09:00"; its task fires once). Prints JSON;
{"error": …} with what to fix. Every change rebuilds the board.
"""
import argparse
import datetime as dt
import glob
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
import entries  # noqa: E402

LATE_MIN = 20          # a run starting this long after it was due is "late" (the app was closed or the Mac asleep)
CRON_DOW = [1, 2, 3, 4, 5, 6, 0]   # Monday-first day numbers -> cron's Sunday-first


def out(obj, code=0):
    print(json.dumps(obj, indent=1, ensure_ascii=False))
    sys.exit(code)


def load():
    try:
        with open(paths.SCHEDULES, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save(data):
    os.makedirs(os.path.dirname(paths.SCHEDULES), exist_ok=True)
    tmp = paths.SCHEDULES + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, paths.SCHEDULES)
    subprocess.run([sys.executable, "-I", os.path.join(paths.SCRIPTS, "build_workflows.py")],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def trigger_of(name):
    """(trigger entry, workflow skill) for a workflow name, skill name or trigger id."""
    n = name.strip()
    for e in entries.load():
        wf = e.get("workflow") or ""
        if not e.get("inside"):
            continue
        if n in (e["id"], wf, wf.replace("workflow-", "", 1)) or wf.endswith("-" + n) and n.count("-") >= 2:
            return e, wf
    out({"error": f"no workflow with its own trigger is called {name!r}: use the name the board copies, e.g. "
                  "property-broker-alert"}, 1)


def once_text(when, now=None):
    """'today 18:07', 'tomorrow 09:00', '2026-11-20 09:00' or 'once …' -> 'once YYYY-MM-DD HH:MM'; None when it
    isn't a one-off."""
    import re
    low = when.strip().lower()
    m = re.fullmatch(r"(?:once\s+)?(?:on\s+)?(today|tomorrow|\d{4}-\d{2}-\d{2})(?:\s+at)?\s+(\d{1,2}):(\d{2})", low)
    if not m:
        return None
    now = now or dt.datetime.now().astimezone()
    day = {"today": now.date(), "tomorrow": now.date() + dt.timedelta(days=1)}.get(m.group(1))
    if day is None:
        try:
            day = dt.date.fromisoformat(m.group(1))
        except ValueError:
            return None
    return f"once {day.isoformat()} {int(m.group(2)):02d}:{m.group(3)}"


def fire_at(sc):
    """A one-off's moment (local, aware), or None for a repeating schedule."""
    if not sc or not sc.get("on") or not sc.get("times"):
        return None
    h, m = sc["times"][0].split(":")
    return dt.datetime.combine(dt.date.fromisoformat(sc["on"]), dt.time(int(h), int(m))).astimezone()


def crons(sc):
    """The cron lines for a schedule: one per distinct minute (a task has one cron). A one-off has none."""
    if sc.get("on"):
        return []
    dow = ",".join(str(CRON_DOW[d]) for d in sorted(sc["days"]))
    dow = "*" if len(sc["days"]) == 7 else ("1-5" if sorted(sc["days"]) == [0, 1, 2, 3, 4] else dow)
    if sc.get("every_h"):
        fh, fm = (sc.get("from") or "00:00").split(":")
        th = (sc.get("to") or "23:59").split(":")[0]
        return [f"{int(fm)} {int(fh)}-{int(th)}/{sc['every_h']} * * {dow}"]
    by_min = {}
    for t in sc["times"]:
        h, m = t.split(":")
        by_min.setdefault(int(m), []).append(int(h))
    return [f"{m} {','.join(str(h) for h in sorted(hs))} * * {dow}" for m, hs in sorted(by_min.items())]


def plan(trig, wf, sc):
    short = wf.replace("workflow-", "", 1)
    when = entries_text(sc)
    req = f"delegate run triggers {trig['id']}: (scheduled: {when})"
    prompt = (f"Scheduled run of Delegate, set up from the board's schedule for the workflow {short}.\n\n"
              f"Work in the project folder {paths.PROJECT}. Take this request exactly as if the user had typed it, and "
              f"follow that folder's CLAUDE.md for it (it is a dispatcher run):\n\n{req}\n\n"
              "Nobody is watching this run: never wait for an answer. A step that would ask the user is left "
              "waiting on the Inbox as Needs you instead.")
    at = fire_at(sc)
    if at:
        tasks = [{"task_id": f"workflow-{short}-once-{at.strftime('%Y%m%d-%H%M')}", "fire_at": at.isoformat(timespec="seconds"),
                  "title": f"Workflow schedule: {short} (once, {at.strftime('%d %b %H:%M')})"}]
        note = "Create the task with fireAt (not a cron) and this prompt; it runs once while the Claude app is open."
    else:
        tasks = [{"task_id": f"workflow-{short}" + (f"-{i + 1}" if i else ""), "cron": c,
                  "title": f"Workflow schedule: {short}" + (f" ({i + 1})" if i else "")} for i, c in enumerate(crons(sc))]
        note = "Create each task with its cron (local time) and this prompt; they run while the Claude app is open."
    return {"trigger": trig["id"], "workflow": wf, "schedule": when, "request": req,
            "prompt": prompt, "tasks": tasks, "note": note}


def entries_text(sc):
    import re
    parts = [p for p in re.split(r"[·|,;]", sc["text"]) if p.strip()]
    keep = [p.strip() for p in parts if p.strip().lower() not in ("paused", "pull in only", "pull in", "run them", "run")]
    return " ".join(keep).strip()


def cmd_set(a):
    trig, wf = trigger_of(a.workflow)
    one = once_text(a.when)
    sc = entries.parse_schedule(one or a.when)
    if not sc or not (sc["times"] or sc["every_h"]):
        out({"error": "say at least one time (08:00) or 'every N hours', e.g. 'weekdays 08:00', or one run: 'today 18:07'"}, 1)
    if one and not sc.get("on"):
        out({"error": f"{a.when!r} is not a real date"}, 1)
    if sc.get("on") and fire_at(sc) <= dt.datetime.now().astimezone():
        out({"error": f"{a.when!r} has already passed: give a time later than now"}, 1)
    data = load()
    old = data.get(trig["id"]) or {}
    oldsc = entries.parse_schedule(old.get("schedule"))
    if sc.get("on") and oldsc and not oldsc.get("on"):
        out({"error": f"{wf} already runs on a repeating schedule ({old['schedule']}); a workflow has one schedule, so "
                      "remove that first, or change it"}, 1)
    p = plan(trig, wf, sc)
    canon = entries_text(sc)
    data[trig["id"]] = {"workflow": wf, "schedule": canon, "paused": False, "tasks": [t["task_id"] for t in p["tasks"]],
                        "set_at": dt.datetime.now().astimezone().isoformat(timespec="seconds")}
    save(data)
    p["replaces_tasks"] = [t for t in old.get("tasks", []) if t not in data[trig["id"]]["tasks"]]
    out(p)


def cmd_state(a, what):
    trig, wf = trigger_of(a.workflow)
    data = load()
    cur = data.get(trig["id"])
    if not cur:
        out({"error": f"{wf} has no schedule"}, 1)
    if what == "remove":
        data.pop(trig["id"])
    else:
        cur["paused"] = what == "pause"
    save(data)
    out({"trigger": trig["id"], "workflow": wf, what: True, "tasks": cur.get("tasks", []),
         "next": {"pause": "update each task with enabled: false", "resume": "update each task with enabled: true",
                  "remove": "delete each task"}[what]})


def cmd_list(_a):
    rows = []
    for k, v in load().items():
        sc = entries.parse_schedule(v.get("schedule"))
        rows.append({"trigger": k, "workflow": v.get("workflow"), "schedule": v.get("schedule"),
                     "paused": v.get("paused", False), "tasks": v.get("tasks", [])})
        if sc and sc.get("on"):
            rows[-1]["fire_at"] = fire_at(sc).isoformat(timespec="seconds")
        elif sc:
            rows[-1]["crons"] = crons(sc)
    out({"schedules": rows})


def last_due(sc, now):
    """The latest scheduled time at or before now (local), or None."""
    if sc.get("on"):
        at = fire_at(sc)
        return at if at and at <= now else None
    for back in range(0, 8):
        day = (now - dt.timedelta(days=back)).date()
        if day.weekday() not in sc["days"]:
            continue
        if sc.get("every_h"):
            fh, fm = map(int, (sc.get("from") or "00:00").split(":"))
            th, tm = map(int, (sc.get("to") or "23:59").split(":"))
            slots, m = [], fh * 60 + fm
            while m <= th * 60 + tm:
                slots.append(m)
                m += sc["every_h"] * 60
        else:
            slots = [int(t[:2]) * 60 + int(t[3:]) for t in sc["times"]]
        for m in sorted(slots, reverse=True):
            t = dt.datetime.combine(day, dt.time(m // 60, m % 60)).astimezone()
            if t <= now:
                return t
    return None


def last_finished(trigger, before):
    """The end time of the newest finished request that ran this trigger (its trace's end line), before `before`."""
    best = None
    for d in paths.TRACE_DIRS:
        for f in glob.glob(os.path.join(d, "*.jsonl")):
            try:
                lines = [json.loads(x) for x in open(f, encoding="utf-8") if x.strip()]
            except (OSError, ValueError):
                continue
            if not lines or lines[0].get("kind") != "trigger":
                continue
            if not any(x.get("entry_match") == trigger for x in lines[1:]):
                continue
            end = next((x for x in reversed(lines) if x.get("end")), None)
            if not end or not end.get("t"):
                continue
            t = dt.datetime.fromisoformat(end["t"].replace("Z", "+00:00"))
            if t < before and (best is None or t > best):
                best = t
    return best


def cmd_window(a):
    now = dt.datetime.fromisoformat(a.now).astimezone() if a.now else dt.datetime.now().astimezone()
    cur = load().get(a.trigger)
    sc = entries.parse_schedule((cur or {}).get("schedule"))
    due = last_due(sc, now) if sc else None
    late = bool(due and (now - due).total_seconds() > LATE_MIN * 60)
    prev = last_finished(a.trigger, now - dt.timedelta(minutes=1))
    since = prev if prev and now - prev < dt.timedelta(days=14) else now - dt.timedelta(hours=24)
    if not prev or since > now - dt.timedelta(hours=24):
        since = min(since, now - dt.timedelta(hours=24))   # never less than the trigger's usual day
    fmt = lambda t: t.astimezone().strftime("%a %H:%M") if t else ""
    out({"trigger": a.trigger, "schedule": entries_text(sc) if sc else "", "due": due.isoformat(timespec="minutes") if due else "",
         "late": late, "since": since.astimezone().isoformat(timespec="minutes"),
         "line": {"type": "Scheduled", "step": "Scheduled run", "title": "Started by its schedule",
                  "result": ("Due " + fmt(due) + ", started late: the app was closed" if late else "Started on time") +
                            "; looking back to " + fmt(since),
                  "status": "done", "schedule": entries_text(sc) if sc else "", "due": fmt(due) if late else "",
                  "since": fmt(since) if late else "",
                  "because": "The app runs it on its schedule; a late run looks back to the last finished run so nothing is missed"}})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set"); s.add_argument("workflow"); s.add_argument("when")
    for c in ("pause", "resume", "remove"):
        sub.add_parser(c).add_argument("workflow")
    sub.add_parser("list")
    w = sub.add_parser("window"); w.add_argument("trigger"); w.add_argument("--now")
    a = ap.parse_args()
    if a.cmd == "set":
        cmd_set(a)
    elif a.cmd in ("pause", "resume", "remove"):
        cmd_state(a, a.cmd)
    elif a.cmd == "list":
        cmd_list(a)
    else:
        cmd_window(a)


if __name__ == "__main__":
    main()
