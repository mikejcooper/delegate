#!/usr/bin/env python3
"""Connections: the status of each external account a trigger or workflow reaches (core-architect rule 19).
The connections manager (core-connections) writes it while it sets a connection up and checks it; the board's
Connections tab and the dispatcher's early check read it. Never a dispatcher run, so nothing goes to the Inbox:
the log is kept here instead. Every change rebuilds the board, so the card on the right follows along.

    connections.py set <name> --status checking|ok|setup|broken --why "<what was found>" [--method <m>]
    connections.py setup <name> --method connector|chrome|browser|api --steps '[{"t": "<step>", "how": "<what to do>", "link": {"label": "<button>", "url": "https://…"}}, ...]'
                                         start a guided setup: its steps (plain strings work too), the first one "now";
                                         the card shows the current step's "how" under it
    connections.py step <name> <n> done|now|failed [--why "<what happened>"]
                                         tick a setup step (1-based); done moves "now" to the next one
    connections.py status [<name>...]    one connection, several, or all
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

STATUSES = ("ok", "setup", "broken", "checking")
METHODS = ("connector", "chrome", "browser", "api")
KEEP = 20


def _path(name):
    return os.path.join(paths.CONNECTIONS, name.replace("connection-", "") + ".json")


def get(name):
    try:
        with open(_path(name), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"name": name.replace("connection-", ""), "status": "unknown", "why": "never checked", "log": []}


def _save(name, cur):
    os.makedirs(paths.CONNECTIONS, exist_ok=True)
    with open(_path(name), "w", encoding="utf-8") as fh:
        json.dump(cur, fh, ensure_ascii=False, indent=1)
    _rebuild()
    return cur


def setup(name, method, steps):
    """A guided setup begins: the method chosen and its steps, shown live on the connection's card."""
    cur = get(name)
    cur["setup"] = {"method": method, "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "steps": [dict({"t": t} if isinstance(t, str) else t, s="now" if i == 0 else "todo")
                              for i, t in enumerate(steps)]}
    if cur.get("status") in (None, "unknown", "ok"):
        cur["status"] = "setup"
    return _save(name, cur)


def step(name, n, state, why=""):
    cur = get(name)
    st = (cur.get("setup") or {}).get("steps") or []
    if not 1 <= n <= len(st):
        return {"error": f"no step {n}"}
    st[n - 1]["s"] = state
    if why:
        st[n - 1]["why"] = why
    if state == "done" and n < len(st) and st[n]["s"] == "todo":
        st[n]["s"] = "now"
    return _save(name, cur)


def set_status(name, status, why, method=None):
    cur = get(name)
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    cur.update(name=name.replace("connection-", ""), status=status, why=why, checked=now)
    if method:
        cur["method"] = method
    if status == "ok" and cur.get("setup"):   # set up and checked: the guided steps are finished
        cur["method"] = cur.get("method") or cur["setup"].get("method")
        cur.pop("setup", None)
    cur["log"] = ([{"t": now, "status": status, "why": why, "method": cur.get("method")}] + (cur.get("log") or []))[:KEEP]
    return _save(name, cur)


def _rebuild():
    """The Connections tab reads the board's data: rebuild it so a check shows at once (quietly)."""
    import subprocess
    subprocess.run([sys.executable, "-I", os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_workflows.py")],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def all_status():
    out = {}
    if os.path.isdir(paths.CONNECTIONS):
        for f in sorted(os.listdir(paths.CONNECTIONS)):
            if f.endswith(".json"):
                out[f[:-5]] = get(f[:-5])
    return out


def main(argv):
    p = argparse.ArgumentParser(description="Status of each connection")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("set")
    s.add_argument("name")
    s.add_argument("--status", required=True, choices=STATUSES)
    s.add_argument("--why", default="")
    s.add_argument("--method", choices=METHODS)
    su = sub.add_parser("setup")
    su.add_argument("name")
    su.add_argument("--method", required=True, choices=METHODS)
    su.add_argument("--steps", required=True)
    sp = sub.add_parser("step")
    sp.add_argument("name")
    sp.add_argument("n", type=int)
    sp.add_argument("state", choices=("done", "now", "failed"))
    sp.add_argument("--why", default="")
    st = sub.add_parser("status")
    st.add_argument("names", nargs="*")
    a = p.parse_args(argv)
    if a.cmd == "set":
        out = set_status(a.name, a.status, a.why, a.method)
    elif a.cmd == "setup":
        out = setup(a.name, a.method, json.loads(a.steps))
    elif a.cmd == "step":
        out = step(a.name, a.n, a.state, a.why)
    elif a.names:
        out = {n: {k: v for k, v in get(n).items() if k != "log"} for n in a.names}
    else:
        out = {k: {kk: vv for kk, vv in v.items() if kk != "log"} for k, v in all_status().items()}
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
