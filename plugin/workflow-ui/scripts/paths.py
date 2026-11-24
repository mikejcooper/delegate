#!/usr/bin/env python3
"""Where the board's code and data live, in one place for every script.

Two setups:
  in-project   the files sit in a project's own .claude/ folder (the setup before 0.12.0).
               Code and data share .claude/workflow-ui/, port 8765, as before.
  source       the plugin's source repo: the plugin sits in a folder of the project (skills-test/plugin/) and the
               project uses it like any install (its own skills in .claude/skills/, its data in
               .workflow-manager-data/), except that the plugin's own files may be changed here. Port 8765.
  plugin       installed as the delegate plugin (workflow-manager before 0.15.0) (code in the plugin cache or a marketplace folder,
               replaced on every update). The project's own .workflow-manager-data/ folder holds:
                 config/    YOURS: settings.json (your switches) and board/<skill>.json (how your skills
                            show on the board). The only part to edit, review or commit.
                 history/   WHAT HAPPENED: requests/ (one file per time you asked), runs/ (one per item),
                            screenshots/, done-list.jsonl, pages/<workflow>/ (what a workflow made for you to
                            look at) and work/<workflow>/ (its scratch files). Keep it; private; don't commit.
                 system/    PLUMBING: version.json, migrations.log, backups/, offer.json, and board/
                            (generated page data, helper pids, the live "now doing" notes).
               It was .workflow-manager/ in 0.8.x and .dispatcher/ before (board/ + data/); migrations move it.
               Each project gets its own board port, so two projects never share a board.

The project is $CLAUDE_PROJECT_DIR when the hooks set it, otherwise the nearest folder at or
above the current one that has .workflow-manager-data/ (or an older name) or .claude/ (never the home folder).

    python3 -I paths.py           print every path as JSON
    python3 -I paths.py port|url  print just that value
    python3 -I paths.py fake <source>   the fake source's file (this folder's own first, then the plugin's)
"""
import hashlib
import json
import os
import sys

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.dirname(SCRIPTS)              # workflow-ui: pages, workflows.json, scripts
ROOT = os.path.dirname(CODE)                 # .claude/ in-project, the plugin root when installed
SKILLS = os.path.join(ROOT, "skills")       # org layer: the plugin's own skills
RULES = os.path.join(CODE, "RUN-TRACE.md")
def _project():
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and os.path.isdir(env):
        return os.path.realpath(env)
    home = os.path.realpath(os.path.expanduser("~"))
    here = os.path.realpath(os.getcwd())
    d = here
    while d != os.path.dirname(d) and d != home:
        if any(os.path.isdir(os.path.join(d, x)) for x in (".workflow-manager-data", ".workflow-manager", ".dispatcher", ".claude")):
            return d
        d = os.path.dirname(d)
    return here


# Plugin mode: the code is a plugin (it has a manifest) and is NOT the project's own .claude/ folder.
# Claude Code may run a plugin from its cache or straight from a folder marketplace, so the location
# alone doesn't tell; comparing with the project does. In skills-test, ROOT is the project's .claude/.
_HERE_PROJECT = _project()
PLUGIN = (os.path.isfile(os.path.join(ROOT, ".claude-plugin", "plugin.json"))
          and os.path.realpath(ROOT) != os.path.join(_HERE_PROJECT, ".claude"))
PROJECT = _HERE_PROJECT if PLUGIN else os.path.dirname(ROOT)
# Source mode: the plugin is a folder inside the project (its source repo), not a copy in a cache or a marketplace
# folder elsewhere. Data is kept as in any install; only the plugin's own files become editable (guard.py).
SOURCE = PLUGIN and os.path.realpath(ROOT).startswith(os.path.realpath(PROJECT) + os.sep)
USER_SKILLS = os.path.join(PROJECT, ".claude", "skills")   # user layer: this folder's own skills (= SKILLS in-project)
LEGACY = os.path.join(PROJECT, ".dispatcher") if PLUGIN else None            # the folder before 0.8.0
LEGACY_08 = os.path.join(PROJECT, ".workflow-manager") if PLUGIN else None    # the folder in 0.8.x
if PLUGIN:
    HOME = os.path.join(PROJECT, ".workflow-manager-data")
    CONFIG, HISTORY, SYSTEM = (os.path.join(HOME, x) for x in ("config", "history", "system"))
    SETTINGS = os.path.join(CONFIG, "settings.json")
    BOARD_DEFS = os.path.join(CONFIG, "board")
    REQUESTS = os.path.join(HISTORY, "requests")      # request traces: one per time the dispatcher was asked
    RUNS = os.path.join(HISTORY, "runs")              # run traces: <wf>-a<n>.jsonl, one per item
    SHOTS = os.path.join(HISTORY, "screenshots")
    DONE_LIST = os.path.join(HISTORY, "done-list.jsonl")
    GENERATED = os.path.join(SYSTEM, "board")
    LIVE = os.path.join(GENERATED, "live")
    WATCH_PID = os.path.join(GENERATED, ".watch.pid")
else:
    HOME = CONFIG = HISTORY = BOARD_DEFS = None
    SYSTEM = GENERATED = CODE
    SETTINGS = os.path.join(CODE, "dispatcher-data", "settings.json")
    REQUESTS = RUNS = os.path.join(CODE, "traces")
    SHOTS = os.path.join(CODE, "shots")
    DONE_LIST = os.path.join(CODE, "dispatcher-data", "ledger.jsonl")
    LIVE = os.path.join(REQUESTS, ".live")
    WATCH_PID = os.path.join(SCRIPTS, ".watch.pid")
TESTS = os.path.join(CONFIG, "tests") if PLUGIN else os.path.join(ROOT, "tests")   # fakes/ for test runs (core-architect rule 28)
# Fake sources, in layers like the skills: this folder's own first (it may override one), then the plugin's, which
# ship with it and update with it. Never copied into the user's folder, so a plugin update needs no migration.
FAKES = [os.path.join(TESTS, "fakes")] + ([os.path.join(ROOT, "tests", "fakes")] if PLUGIN else [])


# Categories (core-architect rule 10), in layers like the fakes: this folder's own list first, then the plugin's.
# The folder's own areas never go in the plugin's list, so they never ship. In-project there is only the one list.
ORG_CATEGORIES = os.path.join(SKILLS, "core-architect", "categories.md")
USER_CATEGORIES = os.path.join(CONFIG, "categories.md") if PLUGIN else None
CATEGORIES = [p for p in (USER_CATEGORIES, ORG_CATEGORIES) if p]


def categories():
    """{category: what belongs there}: every list, the folder's own line winning over the plugin's."""
    import re
    out = {}
    for p in reversed(CATEGORIES):
        try:
            with open(p, encoding="utf-8") as fh:
                out.update(re.findall(r"^\| `([a-z0-9]+)` \| (.*?) \|\s*$", fh.read(), re.M))
        except OSError:
            pass
    return out


def fake(source):
    """The file for fake source `source`: the first layer that has it; none has it: where a new one goes."""
    for d in FAKES:
        f = os.path.join(d, f"{source}.json")
        if os.path.isfile(f):
            return f
    return os.path.join(FAKES[0], f"{source}.json")


SCHEDULES = os.path.join(os.path.dirname(SETTINGS), "schedules.json")   # each workflow trigger's schedule (schedules.py)
CONNECTIONS = os.path.join(os.path.dirname(SETTINGS), "connections")   # each connection's status and check log (connections.py)
SUGGESTIONS = os.path.join(HISTORY, "suggestions.jsonl") if PLUGIN else os.path.join(CODE, "dispatcher-data", "suggestions.jsonl")   # the run reviewer's findings (suggestions.py)
TEST_MODE = os.path.join(LIVE, "test-mode.json")   # present while a test run is open: test_guard.py blocks outside calls
DRAFTS = os.path.join(CONFIG, "drafts") if PLUGIN else os.path.join(CODE, "drafts")   # imports waiting for a yes (core-architect Import mode)
VIEWS = os.path.join(CONFIG, "views.json") if PLUGIN else os.path.join(CODE, "dispatcher-data", "views.json")  # Inbox page views, written by Claude
TRACE_DIRS = sorted({REQUESTS, RUNS})                 # every folder holding traces (one in-project)
BOARD_JS = os.path.join(GENERATED, "board-data.js")
WORKFLOWS_JS = os.path.join(GENERATED, "workflows-data.js")
# Port: from the project's path, by the formula used since 0.3 (it hashed the old folder's path), so
# a project's board keeps its address through every rename.
PORT = 8766 + int(hashlib.sha256(LEGACY.encode()).hexdigest()[:6], 16) % 200 if PLUGIN and not SOURCE else 8765
URL = f"http://127.0.0.1:{PORT}/workflows.html"
ACTIVITY = os.path.join(LIVE, "activity.json")      # what Claude is doing right now, for every request (live.py)
BUILD_STATUS = os.path.join(LIVE, "build-status.json")   # whether the last board builds worked (build_status.py)
RELOAD = os.path.join(LIVE, "reload.json")          # whether this session runs an older copy than installed (reload_check.py)
UPDATE = os.path.join(LIVE, "update.json")          # a git clone's last update check and pull (git_update.py)
SERVED = {"/board-data.js": BOARD_JS, "/workflows-data.js": WORKFLOWS_JS, "/views.json": VIEWS,
          "/activity.json": ACTIVITY, "/build-status.json": BUILD_STATUS,
          "/reload.json": RELOAD, "/update.json": UPDATE}   # generated files, served by name
# Pages a workflow makes for the user to look at (the demo's briefing): served by the board at /pages/<file>, so
# the board can link to them and the Claude app can show them in its side pane.
PAGES = os.path.join(HISTORY, "pages") if PLUGIN else os.path.join(CODE, "pages")
# a workflow's own scratch files (copied scripts, browser profiles, intermediate JSON): <WORK>/<workflow>/, never the
# project's root (core-architect rule 34); what the user is meant to look at goes in PAGES/<workflow>/ instead
WORK = os.path.join(HISTORY, "work") if PLUGIN else os.path.join(CODE, "work")
PAGES_URL = f"http://127.0.0.1:{PORT}/pages/"
WELCOMED = os.path.join(SYSTEM, "welcomed.json")   # the folder's first session has opened the board (welcome.py)
SERVED_DIRS = {"/shots/": SHOTS, "/pages/": PAGES}                         # trace lines say "shots/<file>"


def rel(path):
    """A path as Claude should write it: relative to the project when inside it."""
    try:
        r = os.path.relpath(path, PROJECT)
    except ValueError:
        return path
    return path if r.startswith("..") else r


def as_dict():
    return {"mode": "source" if SOURCE else "plugin" if PLUGIN else "in-project", "project": PROJECT, "code": CODE, "home": HOME,
            "config": CONFIG, "history": HISTORY, "system": SYSTEM, "settings": SETTINGS, "schedules": SCHEDULES, "board_defs": BOARD_DEFS,
            "requests": REQUESTS, "runs": RUNS, "shots": SHOTS, "done_list": DONE_LIST, "user_skills": USER_SKILLS,
            "org_skills": SKILLS, "rules": RULES, "build_board": os.path.join(SCRIPTS, "build_board.py"),
            "views": VIEWS, "drafts": DRAFTS, "tests": TESTS, "fakes": FAKES, "test_mode": TEST_MODE, "connections": CONNECTIONS, "categories": CATEGORIES, "pages": PAGES, "pages_url": PAGES_URL, "work": WORK, "port": PORT, "url": URL}


if __name__ == "__main__":
    want = sys.argv[1] if len(sys.argv) > 1 else ""
    if want == "fake" and len(sys.argv) > 2:
        print(fake(sys.argv[2]))
        sys.exit(0)
    d = as_dict()
    print(d[want] if want in d else json.dumps(d, indent=1))
