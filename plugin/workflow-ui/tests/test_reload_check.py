#!/usr/bin/env python3
"""Test of reload_check.py on a throwaway plugins folder. Nothing real is touched.

Builds, in a temp folder, <plugins>/cache/mkt/workflow-manager/<version>/ copies and an installed_plugins.json, then
checks, for a project:
  1  the running copy is the one installed: no reload needed
  2  a newer copy installed for this project: reload needed, with both versions
  3  the record names a copy that isn't on disk: not needed (nothing to switch to)
  4  another project's install is ignored; a user-wide install is used when this project has none
  5  a copy loaded in place (a git clone): needed only when its hooks were read at an older version
  7  this release: hooks.json's WM_HOOKS_VERSION is plugin.json's version
  6  the hook: banner state written every message, the note for Claude printed once per session and version

    python3 -I test_reload_check.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
sys.path.insert(0, SCRIPTS)
import reload_check as rc  # noqa: E402

FAILS = []


def ok(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


def copy_at(plugins, version, market="mkt"):
    d = os.path.join(plugins, "cache", market, "workflow-manager", version)
    os.makedirs(os.path.join(d, ".claude-plugin"), exist_ok=True)
    with open(os.path.join(d, ".claude-plugin", "plugin.json"), "w") as fh:
        json.dump({"name": "workflow-manager", "version": version}, fh)
    return d


def record(plugins, entries, market="mkt"):
    with open(os.path.join(plugins, "installed_plugins.json"), "w") as fh:
        json.dump({"version": 2, "plugins": {f"workflow-manager@{market}": entries}}, fh)


def main():
    tmp = tempfile.mkdtemp(prefix="reload-check-")
    plugins = os.path.join(tmp, "plugins")
    project = os.path.join(tmp, "project")
    other = os.path.join(tmp, "other")
    os.makedirs(project)
    os.makedirs(other)
    old, new = copy_at(plugins, "0.13.6"), copy_at(plugins, "0.14.0")

    record(plugins, [{"scope": "project", "projectPath": project, "installPath": old, "version": "0.13.6"}])
    r = rc.check(project, old)
    ok(r == {"needed": False, "running": "0.13.6", "installed": "0.13.6"}, "1 same copy: no reload")

    record(plugins, [{"scope": "project", "projectPath": project, "installPath": new, "version": "0.14.0"}])
    r = rc.check(project, old)
    ok(r == {"needed": True, "running": "0.13.6", "installed": "0.14.0"}, "2 newer copy installed: reload needed")
    ok(rc.check(project, new)["needed"] is False, "2 the new copy itself: no reload")

    gone = os.path.join(plugins, "cache", "mkt", "workflow-manager", "0.15.0")
    record(plugins, [{"scope": "project", "projectPath": project, "installPath": gone, "version": "0.15.0"}])
    ok(rc.check(project, old)["needed"] is False, "3 recorded copy not on disk: not needed")

    record(plugins, [{"scope": "project", "projectPath": other, "installPath": new, "version": "0.14.0"}])
    ok(rc.check(project, old)["installed"] is None, "4 another project's install is ignored")
    record(plugins, [{"scope": "project", "projectPath": other, "installPath": old, "version": "0.13.6"},
                     {"scope": "user", "installPath": new, "version": "0.14.0"}])
    ok(rc.check(project, old)["needed"] is True, "4 a user-wide install counts when the project has none")

    inplace = os.path.join(tmp, "repo", "plugin")
    os.makedirs(os.path.join(inplace, ".claude-plugin"))
    with open(os.path.join(inplace, ".claude-plugin", "plugin.json"), "w") as fh:
        json.dump({"version": "0.13.6"}, fh)
    ok(rc.check(project, inplace)["needed"] is False, "5 in place, session on the version on disk: not needed")
    r = rc.check(project, inplace, started="0.13.5")
    ok(r == {"needed": True, "running": "0.13.5", "installed": "0.13.6"}, "5 in place, hooks read at an older version: needed")

    # 7 the release itself: hooks.json's WM_HOOKS_VERSION must be plugin.json's version, or the banner never clears
    plugin = os.path.dirname(os.path.dirname(HERE))
    with open(os.path.join(plugin, "hooks", "hooks.json")) as fh:
        hooks = fh.read()
    want = rc.running_version(plugin)
    ok(f"WM_HOOKS_VERSION={want} " in hooks, f"7 hooks.json passes WM_HOOKS_VERSION={want}, the same as plugin.json")

    # 6 the hook, run from the old copy: a real copy of the scripts inside the cached folder, as an install has them
    record(plugins, [{"scope": "project", "projectPath": project, "installPath": new, "version": "0.14.0"}])
    scripts = os.path.join(old, "workflow-ui", "scripts")
    os.makedirs(scripts)
    for f in ("reload_check.py", "paths.py"):
        with open(os.path.join(SCRIPTS, f)) as src, open(os.path.join(scripts, f), "w") as dst:
            dst.write(src.read())
    env = dict(os.environ, CLAUDE_PROJECT_DIR=project)

    def hook(session):
        p = subprocess.run([sys.executable, "-I", os.path.join(scripts, "reload_check.py"), "prompt"],
                           input=json.dumps({"session_id": session, "prompt": "hi"}), capture_output=True,
                           text=True, env=env)
        return p.stdout.strip()

    live = os.path.join(project, ".workflow-manager-data", "system", "board", "live", "reload.json")
    first = hook("s1")
    ok("0.14.0" in first and "/reload-plugins" in first, "6 first message: Claude told to ask for /reload-plugins")
    with open(live) as fh:
        st = json.load(fh)
    ok(st["needed"] and st["running"] == "0.13.6" and st["installed"] == "0.14.0" and st["session"] == "s1",
       "6 banner state written for the board")
    ok(hook("s1") == "", "6 same session again: told only once")
    ok(hook("s2") != "", "6 another session behind: told too")
    record(plugins, [{"scope": "project", "projectPath": project, "installPath": old, "version": "0.13.6"}])
    ok(hook("s1") == "", "6 nothing to switch to: no note")
    with open(live) as fh:
        ok(json.load(fh)["needed"] is False, "6 banner cleared")

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'FAILED ' + str(len(FAILS)) if FAILS else 'all passed'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
