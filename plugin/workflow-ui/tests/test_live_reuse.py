#!/usr/bin/env python3
"""Test of live.py start() (the skill hook's path) on throwaway trace and live folders. Nothing real is touched.

When the prompt hook didn't run (it was cancelled, or didn't recognise the request), the skill hook makes the trace.
It may take over a trace made moments ago only when it is for the same request:
  1  an unclaimed BBC trace from another session is not taken by an NYT request: a new trace
  2  the same words as that trace's request: taken over
  3  the trigger's phrase for the same trigger ("check the news"): taken over
  4  the open run (the marker) of another request is not reused either
  5  the open run of this request, called with its trigger's phrase: reused

    python3 -I test_live_reuse.py
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
sys.path.insert(0, SCRIPTS)
import live  # noqa: E402

FAILS = []


def ok(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


def header(run, request, trigger):
    with open(live.trace_path(run), "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"header": True, "run": run, "request": request, "kind": "trigger",
                             "trigger": trigger, "workflow": trigger}) + "\n")


def reset(tmp):
    shutil.rmtree(live.TRACES, ignore_errors=True)
    shutil.rmtree(live.LIVE, ignore_errors=True)
    os.makedirs(live.TRACES)
    os.makedirs(live.LIVE)


def main():
    tmp = tempfile.mkdtemp(prefix="live-reuse-")
    live.TRACES = os.path.join(tmp, "requests")
    live.LIVE = os.path.join(tmp, "live")
    live.CURRENT = os.path.join(live.LIVE, "current")
    live.LAUNCH = os.path.join(live.LIVE, "launch.json")
    live.rebuild = lambda: None
    try:
        reset(tmp)
        header("dispatch-0001", "delegate run news-bbc-article", "news")
        run, created = live.start("delegate run news-nyt-briefing")
        ok(created and run != "dispatch-0001", "1 another request's unclaimed trace: a new trace")

        reset(tmp)
        header("dispatch-0001", "delegate run news-bbc-article", "news")
        ok(live.start("delegate run news-bbc-article") == ("dispatch-0001", False), "2 same words: taken over")

        reset(tmp)
        header("dispatch-0001", "delegate run news-bbc-article", "news")
        ok(live.start("check the news") == ("dispatch-0001", False), "3 same trigger's phrase: taken over")

        reset(tmp)
        header("dispatch-0001", "delegate run news-bbc-article", "news")
        live.write_json(live.CURRENT, {"run": "dispatch-0001", "t": __import__("time").time()})
        run, created = live.start("check the new york times")
        ok(created and run != "dispatch-0001", "4 another request's open run: not reused")

        reset(tmp)
        header("dispatch-0001", "delegate run news-nyt-briefing", "nyt")
        live.write_json(live.CURRENT, {"run": "dispatch-0001", "t": __import__("time").time()})
        ok(live.start("check the new york times") == ("dispatch-0001", False), "5 this request's open run: reused")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{len(FAILS)} failed" if FAILS else "\nall passed")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
