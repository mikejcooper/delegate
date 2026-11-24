#!/usr/bin/env python3
"""Whether the Workflow Viewer's data (workflows-data.js) is older than anything build_workflows.py reads.

Prints "stale" (and exits 0) when a skill, a board definition, a draft, a setting or the skill history changed after
the last build, or there is no build yet; prints "fresh" (and exits 1) otherwise. The Stop hook uses it so a turn
that changed nothing ends at once instead of rebuilding the whole board.

    python3 -I <workflow-ui>/scripts/board_stale.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402

SKIP_DIRS = {".git", "__pycache__", "node_modules"}


def inputs():
    """Every file or folder whose change the board's data can show."""
    hist = os.path.join(paths.HISTORY, "skill-history") if paths.PLUGIN else \
        os.path.join(paths.CODE, "dispatcher-data", "skill-history")
    base = os.path.dirname(hist)
    out = [paths.SKILLS, paths.USER_SKILLS, os.path.join(paths.CODE, "workflows.json"),
           *history_marks(hist), os.path.join(base, "pending-reviews"), os.path.join(base, "iterations")]
    if paths.PLUGIN:
        out.append(paths.CONFIG)
    else:
        out.append(paths.DRAFTS)
    return list(dict.fromkeys(out))


def history_marks(hist):
    """The skill history's files that change only when a version is saved (its refs and HEAD). Not the whole folder:
    it is a git repository, and any git command there (a status, a diff, which the hooks run on every message)
    creates and removes a lock file and refreshes the index, which made every turn look changed and rebuild."""
    if not os.path.isfile(os.path.join(hist, "HEAD")):   # not a git folder of its own: watch it whole
        return [hist]
    return [os.path.join(hist, x) for x in ("HEAD", "packed-refs", "refs", os.path.join("logs", "HEAD"))]


def newer(path, since):
    """True as soon as one file (or folder entry) under path changed after since."""
    try:
        if os.stat(path).st_mtime > since:
            return True
    except OSError:
        return False
    if not os.path.isdir(path):
        return False
    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in dirs + files:
            try:
                if os.stat(os.path.join(root, name)).st_mtime > since:
                    return True
            except OSError:
                pass
    return False


def stale():
    try:
        since = os.stat(paths.WORKFLOWS_JS).st_mtime
    except OSError:
        return True
    return any(newer(p, since) for p in inputs())


if __name__ == "__main__":
    s = stale()
    print("stale" if s else "fresh")
    sys.exit(0 if s else 1)
