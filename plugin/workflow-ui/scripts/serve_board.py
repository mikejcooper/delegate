#!/usr/bin/env python3
"""Serve the board on 127.0.0.1 (port from paths.py: 8765 in-project), read-only.

The pages only read: every change (run, skip, mark, delete, the "Run each item once" switch) is a command the page
copies for the Claude chat, carried out there by the dispatcher (core-dispatcher, item_id.py). So the server has no
write endpoints; any POST is refused.
    python3 -I .claude/workflow-ui/scripts/serve_board.py
    python3 -I .claude/workflow-ui/scripts/serve_board.py --release    (the hooks, in the Claude app) stop a copy of
        the board running on its own in the background (started by the hooks before), so the app's preview can have
        the port; a copy the app started is left alone
    python3 -I .claude/workflow-ui/scripts/serve_board.py --register   (the hooks) add or update the board's entry,
        "workflow-ui", in the project's .claude/launch.json, so the Claude app can start and reopen it as a preview
    python3 -I .claude/workflow-ui/scripts/serve_board.py --install-agent    keep the board always on: a macOS login
        item (a LaunchAgent) starts this server at login and again whenever it stops, apart from the Claude app, so
        quitting the app no longer stops the board. While it is installed, the app's entry only connects to it
        ("url", no command) and --release leaves it running
    python3 -I .claude/workflow-ui/scripts/serve_board.py --ensure-agent     (the hooks) the always-on board is the
        default on macOS: install it when missing or pointing at an older copy of the plugin; remove it when the
        folder's settings.json says "board_always_on": false
    python3 -I .claude/workflow-ui/scripts/serve_board.py --uninstall-agent  remove that login item and stop its
        server; the app starts the board itself again, as before

Started while another copy of the board already serves the port (the hooks start one in the background), it doesn't
fail: it waits, and takes over the port if that copy stops. So the app's preview (launch.json) and the hooks never
fight over the port, and the board stays up.
"""
import http.server
import json
import os
import sys
import time
import subprocess
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402  where code and data live (in-project or plugin)
BOARD = paths.CODE
for _d in paths.TRACE_DIRS:
    os.makedirs(_d, exist_ok=True)
PORT = paths.PORT


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=BOARD, **kw)

    def translate_path(self, path):
        """Pages come from the code folder; generated data and screenshots from the data folder."""
        clean = path.split("?", 1)[0].split("#", 1)[0]
        if clean in paths.SERVED:
            return paths.SERVED[clean]
        for prefix, folder in paths.SERVED_DIRS.items():
            if clean.startswith(prefix):
                target = os.path.realpath(os.path.join(folder, os.path.normpath(clean[len(prefix):])))
                if target.startswith(os.path.realpath(folder) + os.sep):
                    return target
        return super().translate_path(path)

    def reply(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        """The bare address (what the Claude app's side pane opens from launch.json) is the Inbox, never a file list."""
        if self.path.split("?", 1)[0].split("#", 1)[0] in ("", "/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/workflows.html")
            self.end_headers()
            return
        if self.path.split("?", 1)[0] == "/views.json" and not os.path.exists(paths.VIEWS):
            return self.reply(200, {"views": []})   # a new folder has no saved views yet: none, not a 404 a second
        for name, f in (("/reload.json", paths.RELOAD), ("/update.json", paths.UPDATE)):
            if self.path.split("?", 1)[0] == name and not os.path.exists(f):
                return self.reply(200, None)   # nothing to say (most folders, most of the time): no banner, no 404
        super().do_GET()

    def do_POST(self):
        """Read-only: changes are chat commands, never made through the server. The one exception is /launch: a copy
        button notes which page the line was copied on (Builder, Inbox, the welcome), so the run it starts opens
        there (live.py). It writes only that note, in the board's own live folder, and changes no data."""
        if self.path.split("?", 1)[0] == "/launch":
            try:
                n = min(int(self.headers.get("Content-Length") or 0), 4096)
                o = json.loads(self.rfile.read(n) or b"{}")
                note = {"cmd": str(o.get("cmd", ""))[:400], "page": str(o.get("page", ""))[:20],
                        "w": str(o.get("w", ""))[:80], "t": time.time()}
                os.makedirs(paths.LIVE, exist_ok=True)
                with open(os.path.join(paths.LIVE, "launch.json"), "w", encoding="utf-8") as fh:
                    json.dump(note, fh)
                return self.reply(200, {"ok": True})
            except (ValueError, OSError) as err:
                return self.reply(400, {"ok": False, "error": str(err)})
        self.reply(405, {"ok": False, "error": "the board is read-only: copy the command into the Claude chat"})

    def log_message(self, fmt, *args):
        pass


def board_up():
    """Another copy of the board answers on the port."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/workflows.html", timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


NAME = "workflow-ui"
AGENT = "local.workflow-board." + __import__("hashlib").sha256(paths.PROJECT.encode()).hexdigest()[:8]  # one per project
AGENT_PLIST = os.path.expanduser(f"~/Library/LaunchAgents/{AGENT}.plist")


def agent_on():
    return os.path.isfile(AGENT_PLIST)


def install_agent():
    """The always-on board: a LaunchAgent that runs this server at login and restarts it if it stops."""
    import plistlib
    py = "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else sys.executable
    log = os.path.expanduser("~/Library/Logs/workflow-board.log")
    plist = {"Label": AGENT, "ProgramArguments": [py, "-I", os.path.join(HERE, "serve_board.py")],
             "WorkingDirectory": paths.PROJECT, "RunAtLoad": True, "KeepAlive": True, "ThrottleInterval": 10,
             "ProcessType": "Background", "StandardOutPath": log, "StandardErrorPath": log}
    os.makedirs(os.path.dirname(AGENT_PLIST), exist_ok=True)
    with open(AGENT_PLIST, "wb") as f:
        plistlib.dump(plist, f)
    dom = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", f"{dom}/{AGENT}"], capture_output=True)   # a copy from before, if any
    r = subprocess.run(["launchctl", "bootstrap", dom, AGENT_PLIST], capture_output=True, text=True)
    register()
    return {"installed": r.returncode == 0, "label": AGENT, "plist": AGENT_PLIST, "log": log,
            "error": r.stderr.strip() or None}


def agent_loaded():
    return subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{AGENT}"], capture_output=True).returncode == 0


def ensure_agent():
    """The always-on board is the default on macOS (the hooks call this on every message and at the welcome): installed
    when missing, and again when it runs another copy of the plugin (each update has its own folder) or isn't loaded.
    Off, and removed, when the folder's settings.json says "board_always_on": false."""
    if sys.platform != "darwin":
        return {"skipped": "only on macOS"}
    try:
        with open(paths.SETTINGS, encoding="utf-8") as fh:
            sets = json.load(fh)
    except (OSError, ValueError):
        sets = {}
    if isinstance(sets, dict) and sets.get("board_always_on") is False:
        return uninstall_agent() if agent_on() else {"skipped": "turned off in settings"}
    if agent_on():
        import plistlib
        try:
            with open(AGENT_PLIST, "rb") as fh:
                args = plistlib.load(fh).get("ProgramArguments") or []
        except (OSError, ValueError):
            args = []
        if os.path.join(HERE, "serve_board.py") in args and agent_loaded():
            register()
            return {"ok": True, "label": AGENT}
    return install_agent()


def uninstall_agent():
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}/{AGENT}"], capture_output=True)
    gone = agent_on()
    if gone:
        os.remove(AGENT_PLIST)
    register()
    return {"uninstalled": gone, "label": AGENT}


def register():
    """The board's entry in <project>/.claude/launch.json: added when missing, its port and script kept current
    (the plugin's folder changes on every update). Other entries are never touched; a file that isn't valid JSON is
    left alone."""
    path = os.path.join(paths.PROJECT, ".claude", "launch.json")
    script = os.path.join(HERE, "serve_board.py")
    if not paths.PLUGIN:
        script = os.path.relpath(script, paths.PROJECT)
    want = {"name": NAME, "runtimeExecutable": "python3", "runtimeArgs": ["-I", script], "port": PORT, "autoPort": False}
    if agent_on():   # always on: the login item runs it, the app only connects (and so never stops it)
        want = {"name": NAME, "url": f"http://127.0.0.1:{PORT}", "port": PORT}
    data = {"version": "0.0.1", "configurations": []}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        if not isinstance(data, dict) or not isinstance(data.get("configurations", []), list):
            return
    confs = data.setdefault("configurations", [])
    cur = next((c for c in confs if isinstance(c, dict) and c.get("name") == NAME), None)
    if cur is not None and cur == want:
        return
    if cur is None:
        confs.append(want)
    else:
        cur.clear()
        cur.update(want)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(path + ".tmp", path)


def release():
    """Stop the board's server when it runs on its own (parent: launchd, the way the hooks used to start it), so
    the Claude app can start its own preview on the port and keep its tab. Only a serve_board.py on this port.
    Never the always-on board (--install-agent): the app connects to that one instead."""
    if agent_on():
        return
    try:
        pids = subprocess.run(["lsof", "-ti", f"tcp:{PORT}", "-sTCP:LISTEN"], capture_output=True, text=True, timeout=3).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return
    for pid in pids:
        try:
            out = subprocess.run(["ps", "-o", "ppid=,command=", "-p", pid], capture_output=True, text=True, timeout=3).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            continue
        ppid, _, cmd = out.partition(" ")
        if ppid.strip() == "1" and "serve_board.py" in cmd:
            try:
                os.kill(int(pid), 15)
            except OSError:
                pass


if __name__ == "__main__":
    if "--release" in sys.argv[1:]:
        release()
        sys.exit(0)
    if "--register" in sys.argv[1:]:
        register()
        sys.exit(0)
    if "--install-agent" in sys.argv[1:]:
        print(json.dumps(install_agent()))
        sys.exit(0)
    if "--ensure-agent" in sys.argv[1:]:
        print(json.dumps(ensure_agent()))
        sys.exit(0)
    if "--uninstall-agent" in sys.argv[1:]:
        print(json.dumps(uninstall_agent()))
        sys.exit(0)
    said = False
    while True:
        try:
            srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
            break
        except OSError as err:
            if not board_up():
                print(f"Cannot bind 127.0.0.1:{PORT}: {err}")
                sys.exit(1)
            if not said:   # the board is already up: stand by, and take over if that copy stops
                print(f"Trace board at http://127.0.0.1:{PORT}/workflows.html (already served; standing by)", flush=True)
                said = True
            time.sleep(5)
    print(f"Trace board at http://127.0.0.1:{PORT}/workflows.html", flush=True)
    srv.serve_forever()
