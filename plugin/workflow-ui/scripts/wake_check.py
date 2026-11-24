#!/usr/bin/env python3
"""Whether the Mac has woken from sleep since this Claude session's last message, so the board's tab can be reopened.

The Claude app closes its preview tabs when the computer sleeps and doesn't open them again on wake. The always-on
board (serve_board.py --install-agent) keeps the server running through sleep, so "is the board answering?" stays
yes and can't tell that the tab is gone. The wake time can: macOS keeps it in `sysctl kern.waketime`.

The prompt hook runs it (desktop app only):
  prompt    (every message, hook JSON on stdin) remembers the wake time each session last saw in
            <live folder>/wake-seen.json. Prints "woke" when the Mac has woken since that session's last message,
            else nothing. A session's first message only records it: there's no tab of its to have lost yet.
Elsewhere than macOS it never prints anything.

    python3 -I wake_check.py           print the current wake time, and change nothing
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402

SEEN = os.path.join(paths.LIVE, "wake-seen.json")   # session -> the wake time (seconds) seen at its last message
KEEP = 50                                            # sessions remembered


def _read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(obj, fh)
    os.replace(path + ".tmp", path)


def _session(raw):
    try:
        return str((json.loads(raw or "{}") or {}).get("session_id") or "")
    except (ValueError, AttributeError):
        return ""


def waketime():
    """Seconds since the epoch of the Mac's last wake, or None (not macOS, never slept, or unreadable)."""
    if sys.platform != "darwin":
        return None
    try:
        out = subprocess.run(["sysctl", "-n", "kern.waketime"], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"sec\s*=\s*(\d+)", out)
    return int(m.group(1)) if m and int(m.group(1)) > 0 else None


def check(session, now_wake, path=SEEN):
    """True when this session has been seen before and the Mac woke since. Records now_wake for the session."""
    if not session or now_wake is None:
        return False
    d = _read(path)
    d = d if isinstance(d, dict) else {}
    before = d.pop(session, None)
    d[session] = now_wake
    _write(path, dict(list(d.items())[-KEEP:]))
    return isinstance(before, int) and now_wake > before


if __name__ == "__main__":
    if sys.argv[1:2] == ["prompt"]:
        if check(_session(sys.stdin.read()), waketime()):
            print("woke")
    else:
        print(json.dumps({"waketime": waketime(), "seen": _read(SEEN)}))
