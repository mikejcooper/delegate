#!/usr/bin/env python3
"""Test of wake_check.py on a throwaway wake-seen file. Nothing real is touched.

Checks check(session, wake, path):
  1  a session's first message only records the wake time: not a wake
  2  the same wake time again: not a wake
  3  a newer wake time: a wake, told once
  4  the next message after it: not a wake
  5  another session's first message, after the wake: not a wake (no tab of its own lost yet)
  6  no session, or no wake time (not macOS, unreadable): never a wake, nothing recorded

    python3 -I test_wake_check.py
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
sys.path.insert(0, SCRIPTS)
import wake_check as wc  # noqa: E402

FAILS = []


def ok(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


def main():
    tmp = tempfile.mkdtemp(prefix="wake-check-")
    seen = os.path.join(tmp, "live", "wake-seen.json")

    ok(wc.check("s1", 1000, seen) is False, "1 first message of a session: not a wake")
    with open(seen) as fh:
        ok(json.load(fh) == {"s1": 1000}, "1 its wake time recorded")
    ok(wc.check("s1", 1000, seen) is False, "2 same wake time: not a wake")
    ok(wc.check("s1", 2000, seen) is True, "3 newer wake time: a wake")
    ok(wc.check("s1", 2000, seen) is False, "4 next message: not a wake again")
    ok(wc.check("s2", 3000, seen) is False, "5 another session's first message: not a wake")
    ok(wc.check("s1", 3000, seen) is True, "5 the first session still sees that wake")

    ok(wc.check("", 4000, seen) is False, "6 empty session: not a wake")
    ok(wc.check("s1", None, seen) is False, "6 no wake time: not a wake")
    with open(seen) as fh:
        d = json.load(fh)
    ok("" not in d and d.get("s1") == 3000, "6 neither recorded anything")

    ok(wc._session('{"session_id": "x"}') == "x" and wc._session("not json") == "",
       "hook input: session id read, bad input ignored")

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'FAILED ' + str(len(FAILS)) if FAILS else 'all passed'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
