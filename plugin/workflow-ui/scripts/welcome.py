#!/usr/bin/env python3
"""The first-run experience, and opening the dashboard on request.

    welcome.py session   the SessionStart hook (and the prompt hook, for a plugin loaded mid-session): the first
                         session in a folder that has the plugin opens the board
                         (in the browser; in the Claude app, Claude opens it in the side pane with its first reply)
                         and tells Claude to suggest the demo. Once per folder; later sessions print nothing.
    welcome.py start     the welcome again, whether or not this folder had it (the start command)
    welcome.py installed install.sh's last step: gets the board ready; in the app, asks on a card to pin this chat
                         and name it "🔀 Delegate Dashboard", then says to send "delegate dashboard" (in a terminal:
                         `claude "delegate dashboard"`)
    welcome.py open      "/dashboard", "delegate dashboard" (the prompt hook): the board, up to date and open.
    welcome.py prompt    the prompt hook (JSON on stdin): "/delegate:start" gives the welcome again and opens
                         the board; "/dashboard", "delegate dashboard" open the board; anything else, nothing
    welcome.py is-dashboard   reads the prompt hook's JSON on stdin: exit 0 when the request is only to see the board

Whatever it prints is added to Claude's context. It never runs a workflow and never writes a trace.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402

IN_APP = os.environ.get("CLAUDE_CODE_ENTRYPOINT") == "claude-desktop"
DEMO = "check the new york times"
# The one formatted next step every welcome ends with: delegate dashboard (its first-look popover takes it from
# there). Plain words, not /dashboard: in the session that ran the install the plugin's commands aren't loaded yet.
OPEN = "delegate dashboard"
HOME = "🔀 Delegate Dashboard"   # the name the install chat gets when the user pins it
NEXT_STEP = ("---\n\n**Installed. Run this next to open your dashboard:**\n\n```\n" + OPEN + "\n```")


def run(*args, wait=True):
    cmd = [sys.executable, "-I", os.path.join(HERE, args[0]), *args[1:]]
    if wait:
        subprocess.run(cmd, capture_output=True, timeout=120)
    else:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def up():
    try:
        with urllib.request.urlopen(paths.URL, timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


def ready():
    """Build both pages, register the app's entry, and (outside the app) serve the board. True when it answers."""
    run("build_board.py")
    run("build_workflows.py")
    run("serve_board.py", "--ensure-agent")   # always on by default (macOS): survives sleep and app restarts
    run("serve_board.py", "--register")
    if IN_APP:   # the app serves it from launch.json, with its own tab (on_prompt.sh releases any other copy)
        return False
    if not up():
        run("serve_board.py", wait=False)
        for _ in range(30):
            if up():
                break
            time.sleep(0.2)
    return up()


def browser(url):
    try:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([opener, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        import webbrowser
        return webbrowser.open(url)


def has_runs():
    try:
        return os.path.getsize(paths.DONE_LIST) > 0
    except OSError:
        return False


def how_to_show():
    if IN_APP:
        return ("Open it in the side pane first thing in your reply, in two steps: preview_start with "
                "{\"name\": \"workflow-ui\"} (its address is " + paths.URL + "), then bring the pane into view with "
                "the show-pane tool (mcp__ccd_view__show_pane, pane \"preview\"). Opening alone can leave it hidden.")
    return f"It is open in their browser at {paths.URL}."


def session(again=False):
    """The first-run welcome: gets the board ready (it isn't opened yet) and tells Claude to end its reply with the one
    next step, "delegate dashboard", and how to open it when the user sends that."""
    if not paths.PLUGIN or (os.path.exists(paths.WELCOMED) and not again):
        return
    os.makedirs(paths.SYSTEM, exist_ok=True)
    ready()
    with open(paths.WELCOMED, "w", encoding="utf-8") as fh:
        json.dump({"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "in_app": IN_APP}, fh)
    print("Delegate, first session in this folder: the user has just installed the plugin. Don't open the "
          "dashboard yet. Whatever they ask first, answer it in a line or two, then end the reply with this block "
          "exactly as written (markdown), with nothing after it:\n\n" + NEXT_STEP + "\n\n"
          "When they then send \"" + OPEN + "\": " + how_to_show() + " Its first-look screen shows them the demo; "
          "say nothing more than that it's open.")


def installed():
    """The end of install.sh: the board is ready, and the next step is "delegate dashboard", in this same chat (in the
    Claude app the plugin's hooks and skills work in the chat that installed it). The welcome is marked as given, so
    that open goes straight to the board, whose first-look screen shows the demo."""
    if not paths.PLUGIN:
        return
    os.makedirs(paths.SYSTEM, exist_ok=True)
    ready()
    with open(paths.WELCOMED, "w", encoding="utf-8") as fh:
        json.dump({"t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "in_app": IN_APP, "by": "install"}, fh)
    if IN_APP:
        print("Installed in " + paths.PROJECT + ". Two steps now, in this order, with nothing else said:\n\n"
              "1. Ask with the AskUserQuestion tool (a card the user clicks, never a question in your text): question "
              "\"Pin this chat and name it " + HOME + "?\", header \"This chat\", options \"Pin and rename "
              "(Recommended)\" (\"Keeps it at the top of your sidebar, ready whenever you need it\") and \"Not now\" "
              "(\"Leave this chat as it is\"). On Pin and rename: get_session with \"self\" for this chat's sessionId "
              "(load mcp__ccd_session_mgmt__get_session with ToolSearch if it isn't loaded), then set_session_title to "
              "\"" + HOME + "\" and set_pinned to true for it (mcp__ccd_session_mgmt__set_session_title and "
              "mcp__ccd_sidebar__set_pinned). If either can't be done, say so in one line and go on.\n"
              "2. Then your reply is the block below, word for word (it is markdown), with nothing before or after "
              "it:\n\n" + NEXT_STEP)
    else:
        print("Installed in " + paths.PROJECT + ". Start Claude here and send \"" + OPEN + "\":\n\n    cd \""
              + paths.PROJECT + "\" && claude \"" + OPEN + "\"")


def open_board():
    served = ready()
    if not IN_APP and served:
        browser(paths.URL)
    print(f"Delegate: the user asked to see the dashboard. {how_to_show()} Say only that it's open, in one "
          "line (its own first-look screen shows anything new users need); run nothing, start no dispatcher run and "
          "write no trace.")


ASKS = __import__("re").compile(
    r"^\s*(/(delegate:|workflow-manager:)?dashboard|dashboard|board|delegate(\s+(open\s+)?(the\s+)?dashboard)?"
    r"|(open|show|see|view)( me)?( the| my)? (delegate |workflow manager |workflow )?(dashboard|board))\s*[.!?]*\s*$", 2)


START = __import__("re").compile(r"^\s*(/(delegate:|workflow-manager:)?start|start (delegate|the workflow manager)|delegate start\.?)\s*$", 2)


def on_prompt():
    """The prompt hook: "/delegate:start" gives the welcome again and opens the board; "/dashboard" and
    plain "delegate dashboard" open the board. Anything else: nothing."""
    try:
        prompt = (json.load(sys.stdin).get("prompt") or "").strip()
    except ValueError:
        return
    first = prompt.splitlines()[0] if prompt else ""
    if START.match(first):
        session(again=True)
    elif ASKS.match(first):
        open_board()


def is_dashboard():
    try:
        prompt = json.load(sys.stdin).get("prompt") or ""
    except ValueError:
        return False
    return bool(ASKS.match(prompt.strip().splitlines()[0] if prompt.strip() else ""))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "next-step":   # the same block, for install.sh to print for whoever reads its output
        print(NEXT_STEP)
        sys.exit(0)
    if cmd == "is-dashboard":
        sys.exit(0 if is_dashboard() else 1)
    if cmd == "prompt":
        try:
            on_prompt()
        except Exception as err:
            print(f"(Delegate: couldn't open the dashboard: {err})", file=sys.stderr)
        sys.exit(0)
    try:
        if cmd == "installed":
            installed()
        else:
            session(again=cmd == "start") if cmd in ("session", "start") else open_board() if cmd == "open" else print(__doc__)
    except Exception as err:   # a hook must never block the session
        print(f"(Delegate: couldn't open the dashboard: {err})", file=sys.stderr)
    sys.exit(0)
