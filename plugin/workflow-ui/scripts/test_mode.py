#!/usr/bin/env python3
"""Test mode: while a test run is open, nothing outside the project is read or changed for real.

The dispatcher turns it on at the start of a test and off at the end (core-dispatcher, Test levels). While it is on,
the PreToolUse hook (on_test_guard.sh -> `test_mode.py guard`) refuses:
  writes   anything that changes the outside world: email drafts, sends, labels, deletes; clicks, typing and
           form filling in a browser; posting, uploading, pushing. The step is logged "Would have ..." instead.
  reads    anything that reads from outside: email, web pages, web search, Maps scans, network scripts.
           The case's canned answer is used instead. A case marked live: true allows reads (never writes).
Local work is always allowed: reading and writing files, the board on localhost, skills, the project's own scripts.
A test-mode file older than 3 hours is stale (a test that never finished) and is ignored and removed.

    test_mode.py on --run <run ID> [--case <skill>/<case>] [--live]
    test_mode.py off
    test_mode.py status
    test_mode.py guard            (the hook: reads the tool call as JSON on stdin)
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

STALE = 3 * 3600
LOCAL = re.compile(r"^(https?://)?(localhost|127\.0\.0\.1|\[::1\])(:\d+)?(/|$)", re.I)
ALWAYS = {"Read", "Write", "Edit", "MultiEdit", "NotebookEdit", "Glob", "Grep", "Skill", "Agent", "Task", "ToolSearch",
          "AskUserQuestion", "TodoWrite", "SendUserFile", "ReadNotifications", "ListAgents", "SendMessage"}
WRITE_WORDS = re.compile(r"(send|draft|delete|trash|forward|reply|label|spam|archive|post|publish|upload|create|update|"
                         r"move|write|set_|add_|remove|insert|submit|approve|merge|run_|call|start|stop|abort|enable)", re.I)
READ_WORDS = re.compile(r"(get|list|search|read|fetch|query|find|lookup|download|scrape|browse|details)", re.I)
NET_BASH = re.compile(r"\b(curl|wget|ssh|scp|rsync\s+\S+:|nc|telnet|ftp)\b|"
                      r"\bnode\b[^|;&]*\b(scan|resolve|velocity|enrich\w*)\.js|\bonpage\.py|"
                      r"\bgit\s+(push|fetch|pull|clone)\b|\bgh\s+|\b(npm|pip|pip3|brew)\s+install\b", re.I)
# a web address is only a network call when something in the command fetches it (a link written into a trace is data)
NET_CODE = re.compile(r"\b(requests\.(get|post|put|head)|urllib|urlopen|http\.client|httpx|aiohttp|fetch\(|"
                      r"webbrowser|socket\.)", re.I)
REMOTE_URL = re.compile(r"https?://(?!localhost|127\.0\.0\.1)", re.I)
WRITE_BASH = re.compile(r"\bgit\s+push\b|\bgh\s+(pr|issue|release|api)\b.*\b(create|merge|comment|edit|close|-X\s*(POST|PUT|PATCH|DELETE))", re.I)


def state():
    try:
        st = os.stat(paths.TEST_MODE)
    except OSError:
        return None
    if time.time() - st.st_mtime > STALE:
        try:
            os.remove(paths.TEST_MODE)
        except OSError:
            pass
        return None
    try:
        with open(paths.TEST_MODE, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"run": "?", "live": False}


def on(run, case, live):
    os.makedirs(os.path.dirname(paths.TEST_MODE), exist_ok=True)
    d = {"run": run, "case": case, "live": bool(live), "since": int(time.time())}
    with open(paths.TEST_MODE, "w", encoding="utf-8") as fh:
        json.dump(d, fh)
    return {"test_mode": "on", **d}


def off():
    try:
        os.remove(paths.TEST_MODE)
    except OSError:
        pass
    return {"test_mode": "off"}


def classify(tool, inp):
    """'ok', 'read' or 'write' for one tool call."""
    if tool in ALWAYS or tool.startswith(("mcp__ccd_", "mcp__visualize__")):
        return "ok"
    if tool == "Bash":
        cmd = str(inp.get("command", ""))
        if WRITE_BASH.search(cmd):
            return "write"
        return "read" if NET_BASH.search(cmd) or (NET_CODE.search(cmd) and REMOTE_URL.search(cmd)) else "ok"
    if tool in ("WebSearch", "WebFetch"):
        return "read"
    if "Browser" in tool or "chrome" in tool.lower():
        name = tool.split("__")[-1]
        if name in ("tabs_context", "tabs_select", "tabs_close", "tabs_create", "resize_window", "preview_list",
                    "preview_logs", "read_console_messages", "read_network_requests"):
            return "ok"
        if name in ("navigate", "navigate_page", "new_page", "preview_start"):
            url = str(inp.get("url") or "")
            return "ok" if (not url or LOCAL.match(url) or url in ("back", "forward")) else "read"
        if name in ("computer", "click", "fill", "fill_form", "type_text", "press_key", "drag", "upload_file",
                    "form_input", "handle_dialog"):
            act = str(inp.get("action", name))
            return "ok" if act in ("screenshot", "zoom", "wait", "scroll", "scroll_to", "hover") else "write"
        return "ok"   # reading the page already open (the board): it can only be local, since navigating out is refused
    if tool.startswith("mcp__"):
        name = tool.split("__")[-1]
        if READ_WORDS.match(name) or (READ_WORDS.search(name) and not WRITE_WORDS.search(name)):
            return "read"
        return "write"
    return "ok"


def guard():
    st = state()
    if not st:
        return
    try:
        call = json.load(sys.stdin)
    except ValueError:
        return
    tool, inp = call.get("tool_name", ""), call.get("tool_input") or {}
    kind = classify(tool, inp)
    if kind == "ok" or (kind == "read" and st.get("live")):
        return
    why = ("TEST MODE: this would change something outside the project, so it was not done. Don't retry it: log the "
           "step with \"type\":\"Mocked\" and say what would have happened (\"Would have drafted to … with subject …\")."
           if kind == "write" else
           "TEST MODE: reading from outside is off for this test. Use this case's canned answer for the step "
           "(\"type\":\"Fake Read\"); if the case has none, treat it as nothing found and say the answer wasn't canned.")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": why}}))


def main(argv):
    cmd = argv[0] if argv else "status"
    if cmd == "guard":
        return guard()
    if cmd == "on":
        a = dict(zip(argv[1::2], argv[2::2]))
        out = on(a.get("--run", "?"), a.get("--case", ""), "--live" in argv)
    elif cmd == "off":
        out = off()
    else:
        out = {"test_mode": "on", **state()} if state() else {"test_mode": "off"}
    print(json.dumps(out))


if __name__ == "__main__":
    main(sys.argv[1:])
