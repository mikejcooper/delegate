#!/usr/bin/env python3
"""Whether the board's last builds worked, so the pages can say so instead of quietly showing old data.

Each build (build_workflows.py, build_board.py) calls report(<which>, ok, errors) when it finishes or crashes. The
pages read <live folder>/build-status.json (served as /build-status.json) and show a red banner while any build
is failing: what failed, the first error, and that the page shows the last version that built.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402


def report(which, ok, errors=()):
    try:
        try:
            with open(paths.BUILD_STATUS, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            data = {}
        prev = data.get(which) or {}
        if ok and prev.get("ok", True):
            if prev:   # nothing new to say: skip the write (build_board runs every second)
                return
        data[which] = {"ok": bool(ok), "t": time.time(), "errors": [str(e)[:300] for e in list(errors)[:5]]}
        os.makedirs(os.path.dirname(paths.BUILD_STATUS), exist_ok=True)
        tmp = paths.BUILD_STATUS + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.replace(tmp, paths.BUILD_STATUS)
    except Exception:   # reporting must never break a build
        pass
