#!/usr/bin/env python3
"""Live feedback for dispatcher runs, driven by the hooks (never by Claude directly).

  live.py prompt   UserPromptSubmit hook (hook JSON on stdin). A dispatcher request ("run dispatcher",
                   "check my emails", "rerun workflow wf-...") gets its trigger trace + header straight away,
                   so the board shows it the moment you press enter; Claude is told the run ID to reuse.
                   Any other request closes the live marker, so later tool calls aren't pinned to an old run.
  live.py skill    PreToolUse hook for Skill: the dispatcher is starting. Reuses the open trigger, or creates
                   one if the request wasn't recognised at prompt time. Prints the run ID.
  live.py stop     Stop hook: Claude finished its turn; the activity line says it is waiting for you.
  live.py tool     PreToolUse hook for every tool. Always updates the activity line (<live folder>/activity.json,
                   served as /activity.json): what Claude is doing now, in plain words, which every board page
                   shows in its top bar, for any request. While a dispatcher run is open it also writes one plain-words
                   "now doing" note (e.g. "Opening Gmail") to the live folder (paths.LIVE)/<run>.json, which the board shows
                   under the running trigger. Writes nothing to the trace itself.

The open run is <live folder>/current ({"run": "<id>", "t": <epoch>}). It is cleared when the trace has an
end line, when a non-dispatcher request arrives, or after IDLE seconds without a tool call.
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402  where code and data live (in-project or plugin)
TRACES = paths.REQUESTS   # request traces (one per time the dispatcher is asked)
LIVE = paths.LIVE
CURRENT = os.path.join(LIVE, "current")
SETTINGS = paths.SETTINGS
IDLE = 1800

# The dispatcher's own requests. Every trigger's phrases come from its trigger- skill at run
# time (see dispatch_match), so a new trigger needs no change here.
DISPATCH = re.compile(
    r"\b(run|start)\s+(the\s+)?(dispatcher|workflow[\s-]manager)\b"   # run everything
    r"|\brun\s+all\s+(the\s+)?triggers\b"
    r"|\b(run|start)\s+(the\s+)?trigger\s+\S+"                      # one trigger by name
    r"|\b(run|test)\s+(the\s+)?workflow\s+(?!manager\b)\S+"           # one workflow / a test (and rerun wf-…)
    r"|\brerun\s+(the\s+)?workflow\s+wf-[0-9a-f]{8}\b"
    r"|\bskip\s+wf-[0-9a-f]{8}\b"                                    # change items by hand: skip,
    r"|\bmark\s+wf-[0-9a-f]{8}\b"                                    # mark done / needs you / not run,
    r"|\bdelete\s+wf-[0-9a-f]{8}\b"                                  # take off the board,
    r"|\bdelete\s+requests?\s+dispatch-[0-9a-z-]+"                      # or a request that ran nothing,
    r"|\bturn\s+run\s+each\s+item\s+once\s+(on|off)\b",              # or the Run each item once switch
    re.I)
MAX_WORDS = 15  # a work request is short; a longer message that merely mentions a trigger is not one
# The lines the board's Inbox page copies are longer, but always start the same way.
PAGE = re.compile(r"^\s*(run\s+workflow\s+manager\s+with\s+these\s+triggers\b|run\s+these\s+\d+\s+items\b"
                  r"|skip\s+these\s+items\b|skip\s+wf-[0-9a-f]{8}\b|(mark|delete)\s+these\s+items\b"
                  r"|(mark|delete)\s+wf-[0-9a-f]{8}\b|delete\s+(these\s+requests|requests?\s+dispatch-)|turn\s+run\s+each\s+item\s+once\s+(on|off)\b)", re.I)


def dispatch_match(prompt):
    try:   # "delegate run …", "delegate skip wf-…", "delegate <a workflow's phrase>" (commands.py)
        import commands
        c = commands.parse(prompt)
        if c:
            return c.get("skill") == "core-dispatcher" or bool(c.get("trigger"))
    except Exception:
        pass
    if PAGE.search(prompt):
        return True
    if len(prompt.split()) > MAX_WORDS:
        return False
    if DISPATCH.search(prompt):
        return True
    try:
        import entries
        pat = entries.trigger_pattern()
    except Exception:
        pat = None
    return bool(pat and pat.search(prompt))


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def write_json(path, obj):
    os.makedirs(LIVE, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)
    os.replace(tmp, path)


def trace_path(run):
    return os.path.join(TRACES, run + ".jsonl")


def ended(run):
    try:
        with open(trace_path(run), encoding="utf-8") as fh:
            return any('"end"' in line and json.loads(line).get("end") for line in fh if line.strip())
    except (OSError, ValueError):
        return True  # trace gone or unreadable: nothing to follow


def close():
    cur = read_json(CURRENT) or {}
    for p in (CURRENT, os.path.join(LIVE, str(cur.get("run", "")) + ".json")):
        try:
            os.remove(p)
        except OSError:
            pass


def open_run():
    """The open run's ID, or None (closing a finished or idle one on the way)."""
    cur = read_json(CURRENT)
    if not cur or not cur.get("run"):
        return None
    if ended(cur["run"]) or time.time() - cur.get("t", 0) > IDLE:
        close()
        return None
    return cur["run"]


def rebuild():
    subprocess.run([sys.executable, "-I", os.path.join(HERE, "build_board.py")],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


ADOPT = 600   # a request trace started this recently, with no end and no hook marker, is this request's own


def clean(request):
    """The request as the board shows it: notes in brackets ("(run ID …; a try of …)") are Claude's, not the user's."""
    return " ".join(re.sub(r"\([^)]*\)?", " ", request).split())[:60]


def trigger_of(request):
    """The trigger whose phrase this request uses (a workflow's own trigger or an older trigger skill), or None."""
    try:
        import entries
        for e in entries.load():
            if e.get("skill") == "core-dispatcher":
                continue
            for p in e.get("triggers") or []:
                if len(p.split()) >= 2 and re.search(r"\b" + re.escape(p) + r"\b", request, re.I):
                    return e
    except Exception:
        pass
    return None


def is_try(e):
    """A trigger of a workflow not published yet (category new): every run of it is a try."""
    return bool(e) and str(e.get("category", "")).lower() == "new"


def recent_open():
    """A request trace made moments ago that nothing has claimed yet (e.g. written by hand before the dispatcher was
    invoked): reused, so one request never shows twice on the Inbox."""
    try:
        names = [n for n in os.listdir(TRACES) if n.endswith(".jsonl")]
    except OSError:
        return None
    best = None
    for n in names:
        p = os.path.join(TRACES, n)
        if time.time() - os.path.getmtime(p) > ADOPT:
            continue
        try:
            with open(p, encoding="utf-8") as fh:
                lines = [x for x in fh if x.strip()]
            head = json.loads(lines[0]) if lines else {}
        except (OSError, ValueError):
            continue
        if len(lines) != 1 or not head.get("header") or head.get("kind") != "trigger":
            continue   # only a header: anything with steps or an end belongs to a run already under way or done
        if not best or os.path.getmtime(p) > best[0]:
            best = (os.path.getmtime(p), head.get("run") or n[:-6])
    return best[1] if best else None


NAMED = re.compile(r"\b(?:test|run|rerun|try)\s+workflow\s+([A-Za-z0-9][\w-]*)", re.I)


def board_workflows():
    """The Builder's workflows as last built (workflows-data.js): id, skill and the triggers that start each."""
    try:
        with open(paths.WORKFLOWS_JS, encoding="utf-8") as fh:
            txt = fh.read()
        return json.loads(txt[txt.index("=") + 1:].strip().rstrip(";")).get("workflows") or []
    except (OSError, ValueError):
        return []


def workflow_of(request):
    """The one workflow a request names ("test workflow …", "run workflow …", "rerun workflow wf-…"), as
    (board workflow id, its trigger id or ""), or None. Such a run is watched on the Builder, like a try."""
    m = NAMED.search(request or "")
    if not m:
        return None
    name, skill = m.group(1).lower(), ""
    if re.fullmatch(r"wf-[0-9a-f]{8}", name):   # a rerun: the workflow that item last ran through
        try:
            with open(paths.DONE_LIST, encoding="utf-8") as fh:
                for line in fh:
                    if f'"{name}"' in line:
                        skill = json.loads(line).get("skill") or skill
        except (OSError, ValueError):
            pass
    wfs = [w for w in board_workflows() if not w.get("parent")]
    hit = None
    for w in wfs:
        sk = str(w.get("skill") or (w.get("match") or {}).get("skill") or "")
        if (skill and sk == skill) or (not skill and name in (str(w.get("id", "")).lower(), sk.lower())):
            hit = w
            break
    if not hit and not skill:   # a word from its name ("briefing" finds workflow-news-nyt-briefing)
        found = [w for w in wfs if name in str(w.get("skill") or (w.get("match") or {}).get("skill") or "")]
        hit = found[0] if len(found) == 1 else None
    if not hit:
        return None
    return hit["id"], ((hit.get("entries") or [""])[0] or "")


LAUNCH = os.path.join(LIVE, "launch.json")


def _norm(t):
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(t or "").lower()).split())


def launch_of(request):
    """Where this request's line was copied on the board (serve_board.py /launch: the Builder, the Inbox, the
    welcome), when it was copied in the last 30 minutes and the request is that line; else None. Used once."""
    o = read_json(LAUNCH) or {}
    cmd = _norm(o.get("cmd"))
    if not cmd or time.time() - float(o.get("t") or 0) > 1800 or cmd not in _norm(request):
        return None
    try:
        os.remove(LAUNCH)
    except OSError:
        pass
    return o


def workflow_of_trigger(e):
    """The one workflow a trigger feeds, as its board id, or None (a trigger shared by several, or none)."""
    if not e:
        return None
    ws = [w.get("id") for w in board_workflows() if e["id"] in (w.get("entries") or [])]
    return ws[0] if len(ws) == 1 else None


def builder_url(run, e=None, wf=None):
    """Where a try or a run of one workflow is watched: the Builder on the workflow's own page, which shows its
    trigger's steps as they are logged and follows each item as it runs. There is no trigger page: a trigger is the
    first stage of its workflow."""
    base = paths.URL.rsplit("/", 1)[0]
    if e and not wf:
        wf = next((w.get("id") for w in board_workflows() if e["id"] in (w.get("entries") or [])), None)
        if not wf:   # a trigger that feeds no workflow on the board: its request on the Inbox (no dispatcher page)
            return f"{base}/workflows.html?pullin={run}"
    return f"{base}/workflow-viewer.html?w={wf}&run={run}"


def start(request):
    """Reuse the open trigger, or write a new trigger trace with its header line. Returns (run ID, created)."""
    run = open_run() or recent_open()
    if run:
        write_json(CURRENT, {"run": run, "t": time.time()})
        return run, False
    request = clean(request)
    base = "dispatch-" + time.strftime("%H%M")
    run, n = base, 2
    while os.path.exists(trace_path(run)):
        run, n = f"{base}-{n}", n + 1
    sets = read_json(SETTINGS) or {}
    skip, auto = sets.get("skip_done", True), sets.get("auto_approve", True)
    e = trigger_of(request)
    header = {"header": True, "run": run, "label": ("Try: " + (e.get("desc") or e["id"])) if is_try(e) else
              "Dispatcher run", "request": request, "started": now_iso(), "kind": "trigger", "skip_done": bool(skip),
              "auto_approve": bool(auto)}
    named = workflow_of(request)
    if named:   # "test workflow …", "run workflow …", "rerun workflow wf-…": watched on the Builder
        header["workflow"], header["watch"] = named[0], True
        if named[1] and not e:
            header["trigger"] = named[1]
    if e:
        header["trigger"] = e["id"]   # the trigger its phrase names, before the dispatcher's own match line
    # where it is watched (RUN-TRACE.md, Start): where its line was copied on the board; typed in the chat, one
    # workflow's trigger is watched on that workflow's page, several workflows on the Inbox
    lo = launch_of(request) or {}
    page = lo.get("page", "")
    one = workflow_of_trigger(e)
    if page in ("inbox", "welcome"):
        header.pop("watch", None)
        header["from"] = page
        if page == "welcome":
            header["first"] = True   # the first run, from the welcome: its Inbox row opens and points to the Builder
    elif page == "builder" or one:
        wf = lo.get("w") if page == "builder" and lo.get("w") else (named[0] if named else one)
        if wf:
            header["workflow"], header["watch"] = wf, True
        if page:
            header["from"] = page
    if is_try(e):
        header["try"], header["watch"] = True, True
    os.makedirs(TRACES, exist_ok=True)
    with open(trace_path(run), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(header) + "\n")
    write_json(CURRENT, {"run": run, "t": time.time()})
    note(run, "Starting")
    rebuild()
    return run, True


ACTIVITY = os.path.join(LIVE, "activity.json")


def activity(text, busy=True, request=None):
    """The top bar's live line: what Claude is doing now (any request, not only dispatcher runs)."""
    cur = read_json(ACTIVITY) or {}
    if request is not None:
        cur = {"request": request[:80], "started": time.time()}
    cur.update({"t": time.time(), "text": text[:90], "busy": busy})
    write_json(ACTIVITY, cur)


def note(run, text):
    write_json(os.path.join(LIVE, run + ".json"), {"t": now_iso(), "text": text[:90]})
    cur = read_json(CURRENT) or {}
    if cur.get("run") == run:
        cur["t"] = time.time()
        write_json(CURRENT, cur)


def context(run, created, request=""):
    how = "The hook just created" if created else "This run's trace is already open:"
    return (f"{how} the dispatcher trigger trace {paths.rel(trace_path(run))} with its header line "
            f"(kind trigger, skip_done as the switch reads now). Use run ID {run}: don't create another trace "
            f"or rewrite the header. " + try_note(run, request) + rules_note())


def try_note(run, request):
    """A try of a new workflow, or a run of one named workflow (a test, run or rerun), is watched on the Builder,
    not the Inbox (RUN-TRACE.md, Start)."""
    e = trigger_of(request)
    if is_try(e):
        return (f"This is a try of a new workflow: show the board tab at {builder_url(run, e)} (the Builder, which "
                f"follows the try and each item as it runs) instead of the Inbox, and keep it there. ")
    try:
        with open(trace_path(run), encoding="utf-8") as fh:
            hdr = json.loads(fh.readline() or "{}")
    except (OSError, ValueError):
        hdr = {}
    if hdr.get("first"):
        return ("This is the user's first run, started from the welcome: show the board tab at the Inbox "
                f"({paths.URL}) and keep it there; its row opens by itself and offers to watch it in the Builder. ")
    if not hdr.get("watch"):
        return ""
    named = (hdr.get("workflow"),) if hdr.get("workflow") else workflow_of(request)
    if not named:
        return ""
    url = builder_url(run, wf=named[0])
    return (f"This run is of one workflow{' and was started from its Builder page' if hdr.get('from') == 'builder' else ''}: "
            f"show the board tab at {url} (the Builder, which follows the run and its steps as they are logged) instead "
            f"of the Inbox, and keep it there until the run ends. ")


def rules_note():
    """Where this run's rules and paths are: the same wording for the prompt and skill hooks."""
    return (f"This dispatcher run gets a trace: read and follow the run-trace rules in {paths.RULES} "
            f"(read it now if you haven't this session), starting from Start (show the board, then the "
            f"dispatcher). This project's paths for those rules: requests folder {paths.rel(paths.REQUESTS)}/ "
            f"(the request trace), runs folder {paths.rel(paths.RUNS)}/ (one trace per item run), "
            f"screenshots folder {paths.rel(paths.SHOTS)}/, rebuild command "
            f"python3 -I {paths.rel(os.path.join(HERE, 'build_board.py'))}, board {paths.URL}.")


SKIP_TOOLS = ("ToolSearch", "mcp__ccd_turn__", "mcp__ccd_view__", "mcp__ccd_session", "mcp__Claude_Browser__tabs_",
              "mcp__Claude_Browser__resize_window", "mcp__visualize__")


def describe(name, inp):
    """One short plain-words line for a tool call, or None to leave the last note as it is."""
    if any(name.startswith(p) for p in SKIP_TOOLS):
        return None
    inp = inp if isinstance(inp, dict) else {}
    if name == "Skill":
        sk = str(inp.get("skill", "")).split(":")[-1]
        return {"core-architect": "Architect: working on your workflow", "core-dispatcher": "Starting Delegate",
                "core-connections": "Connections manager: checking accounts"}.get(sk, "Handing over to " + (sk or "a helper"))
    if name == "AskUserQuestion":
        return "Waiting for your answer"
    if name in ("Agent", "Task"):
        return "A helper is working on part of it"
    if name in ("Write", "Edit", "NotebookEdit"):
        f = str(inp.get("file_path", ""))
        base = os.path.basename(f)
        if base == "SKILL.md":
            return "Writing the skill " + os.path.basename(os.path.dirname(f))
        if base == "workflows.json" or "/board/" in f:
            return "Updating the board's definitions"
        if "/drafts/" in f:
            return "Writing the draft"
        return "Editing " + base
    if name == "WebSearch":
        return "Searching the web: " + str(inp.get("query", ""))
    if name in ("WebFetch",):
        return "Reading a web page"
    if name == "Bash":
        cmd = str(inp.get("command", ""))
        if inp.get("description"):   # Claude's own plain-words description of the command says it best
            return str(inp["description"])
        for key, text in (("new_workflow.py create", "Building the workflow from the draft"),
                          ("new_workflow.py publish", "Publishing it: names, checks, saving the version"),
                          ("run_item.py", "Writing down what happened"), ("recording.py", "Saving what it read, for its tests"),
                          ("test_mode.py", "Holding back every send (test mode)"), ("connections.py", "Checking the connections"),
                          ("skill_history.py save", "Saving the version"), ("skill_history.py", "Updating the draft's history"),
                          ("build_workflows", "Updating the Builder"), ("item_id.py", "Checking the done list"),
                          ("/traces/", "Writing down what happened"), ("build_board", "Writing down what happened")):
            if key in cmd:
                return text
        return str(inp.get("description") or "Running a command")
    if name in ("Read", "Grep", "Glob"):
        f = str(inp.get("file_path") or inp.get("path") or "")
        if f.endswith("rules.md"):
            return "Reading the rules"
        if f.endswith("SKILL.md"):
            return "Reading the skill " + os.path.basename(os.path.dirname(f))
        return "Reading the instructions"
    low = name.lower()
    if "outlook" in low:
        return "Sending in Outlook" if "send" in low or "forward" in low else "Reading Outlook"
    if "slack" in low:
        return "Sending you a Slack message" if "send" in low else "Reading Slack"
    if name.startswith("mcp__Claude_Browser__") or name.startswith("mcp__chrome-devtools__"):
        tool = name.split("__")[-1]
        if tool in ("navigate", "navigate_page", "new_page", "preview_start"):
            host = urlparse(str(inp.get("url", ""))).hostname or ""
            names = {"mail.google.com": "Gmail", "127.0.0.1": "the board", "localhost": "the board"}
            return "Opening " + names.get(host, host or "a page")
        if tool == "browser_batch":
            for a in inp.get("actions", []):
                if isinstance(a, dict):
                    text = describe("mcp__Claude_Browser__" + str(a.get("name", "")), a.get("input"))
                    if text:
                        return text
            return "Working in the browser"
        if tool == "computer":
            if inp.get("action") == "screenshot":
                return "Taking a screenshot"
            if inp.get("action") in ("wait", "zoom", "scroll", "scroll_to", "hover"):
                return None
            return str(inp.get("action_summary") or "Working in the browser")
        if tool in ("take_screenshot",):
            return "Taking a screenshot"
        return "Reading the page"
    if "gmail" in name.lower() or name.startswith("mcp__2339cc22"):
        return "Working in Gmail"
    return None


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        data = json.load(sys.stdin) if not sys.stdin.isatty() else {}
    except ValueError:
        data = {}
    if mode == "stop":
        cur = read_json(ACTIVITY) or {}
        activity("Done · waiting for you", busy=False)
        return
    if mode == "prompt":
        prompt = str(data.get("prompt", ""))
        activity("Reading your request", request=" ".join(prompt.split()))
        note = os.environ.get("MIGRATION_NOTE", "").strip()  # from migrations/migrate.py --hook, or empty
        if not dispatch_match(prompt):
            close()
            if note:
                print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                         "additionalContext": note}}))
            return
        request = " ".join(prompt.split())[:60]
        run, created = start(request)
        ctx = context(run, created, request) + (" " + note if note else "")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                 "additionalContext": ctx}}))
    elif mode == "skill":
        words = " ".join(" ".join(sys.argv[2:]).split())[:60]   # the dispatcher's call, e.g. "test workflow …"
        run, created = start(words or "dispatcher request")
        print(run)
        print("created" if created else "existing")
        print(try_note(run, words))
    elif mode == "note":
        print(rules_note())
    elif mode == "tool":
        tool, inp = str(data.get("tool_name", "")), data.get("tool_input")
        if tool in ("Write", "Edit", "NotebookEdit") and isinstance(inp, dict) and inp.get("file_path"):
            try:   # an edit to a skill: its page turns to "Claude is updating it" within seconds (skill_history.py)
                import skill_history
                skill_history.auto_updating(str(inp["file_path"]))
            except (Exception, SystemExit):
                pass
        text = describe(tool, inp)
        if text:
            activity(text)
        run = open_run()
        if run and text:
            note(run, text)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # a hook must never get in the way of the request
        pass
