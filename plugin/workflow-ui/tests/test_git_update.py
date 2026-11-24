#!/usr/bin/env python3
"""Test of git_update.py on throwaway git repos. Nothing real is touched; no network.

Builds, in a temp folder:
  remote.git   a bare "public repo" holding a copy of this plugin (the repo's layout: plugin/ inside), version 0.91.0
  dev/         the author's clone, which pushes releases
  install/     a user's clone the plugin runs from (in place), and project/, the user's folder
Then checks, in order:
  1  nothing newer: "current", nothing pulled
  2  a newer commit on the tracked branch: pulled, version on disk moves on, migrations run, logged
  3  checked a moment ago: not checked again until it is due (unless --now)
  4  a workflow run open: skipped, not shown on the board (it passes by itself), pulled once the run is over
  5  local changes in the clone: skipped, shown on the board with the reason
  6  commits of its own in the clone: skipped as diverged
  7  release tags: the newest tag wins over a newer untagged branch tip
  8  "auto_update": false in settings.json: never checks
  9  reload_check: a chat started on an older release is told to reload only when the release changed what a chat
     reads at its start (here a skill's description), not for one that only changes scripts

    python3 -I test_git_update.py      (optional: --keep to leave the temp folder for a look)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(os.path.dirname(HERE))          # workflow-manager/plugin
FAILS = []


def ok(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


def git(repo, *args):
    p = subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false",
                        "-c", "tag.gpgsign=false", *args], capture_output=True, text=True)
    assert p.returncode == 0, (args, p.stderr)
    return p.stdout.strip()


def set_version(clone, v, msg=None):
    f = os.path.join(clone, "plugin", ".claude-plugin", "plugin.json")
    with open(f) as fh:
        d = json.load(fh)
    d["version"] = v
    with open(f, "w") as fh:
        json.dump(d, fh, indent=2)
    git(clone, "commit", "-qam", msg or f"release {v}")


def disk_version(clone):
    with open(os.path.join(clone, "plugin", ".claude-plugin", "plugin.json")) as fh:
        return json.load(fh)["version"]


def main():
    tmp = tempfile.mkdtemp(prefix="git-update-")
    remote, dev, inst, project = (os.path.join(tmp, x) for x in ("remote.git", "dev", "install", "project"))
    os.makedirs(project)
    os.makedirs(dev)
    shutil.copytree(PLUGIN, os.path.join(dev, "plugin"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".watch.pid"))
    git(dev, "init", "-q", "-b", "main")
    git(dev, "add", "-A")
    git(dev, "commit", "-qm", "start")
    set_version(dev, "0.91.0")
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", remote], check=True)
    git(dev, "remote", "add", "origin", remote)
    git(dev, "push", "-q", "-u", "origin", "main")
    subprocess.run(["git", "clone", "-q", remote, inst], check=True)

    scripts = os.path.join(inst, "plugin", "workflow-ui", "scripts")
    live = os.path.join(project, ".workflow-manager-data", "system", "board", "live")
    env = dict(os.environ, CLAUDE_PROJECT_DIR=project)

    def run(*extra, hooks_version=None):
        e = dict(env, **({"WM_HOOKS_VERSION": hooks_version} if hooks_version else {}))
        subprocess.run([sys.executable, "-I", os.path.join(scripts, "git_update.py"), "run", *extra],
                       capture_output=True, text=True, env=e, timeout=120)
        try:
            with open(os.path.join(live, "update.json")) as fh:
                return json.load(fh)
        except OSError:
            return {}

    st = run("--now")
    ok(st.get("status") == "current" and disk_version(inst) == "0.91.0", "1 nothing newer: current")

    set_version(dev, "0.92.0")
    git(dev, "push", "-q")
    st = run("--now")
    ok(st.get("status") == "updated" and disk_version(inst) == "0.92.0", "2 newer commit: pulled to 0.92.0")
    ok(st.get("previous") == "0.91.0" and st.get("current") == "0.92.0", "2 state says from and to")
    with open(os.path.join(project, ".workflow-manager-data", "system", "version.json")) as fh:
        ok(json.load(fh).get("data_version") == "0.92.0", "2 the new release's migrations ran (folder stamped 0.92.0)")
    with open(os.path.join(project, ".workflow-manager-data", "system", "updates.log")) as fh:
        ok("updated 0.91.0 -> 0.92.0" in fh.read(), "2 logged")

    set_version(dev, "0.93.0")
    git(dev, "push", "-q")
    before = st["checked"]
    st = run()
    ok(st.get("checked") == before and disk_version(inst) == "0.92.0", "3 not due: not checked again")

    os.makedirs(live, exist_ok=True)
    with open(os.path.join(live, "current"), "w") as fh:
        json.dump({"run": "dispatch-test"}, fh)
    st = run("--now")
    ok(st.get("status") == "skipped" and st.get("reason") == "run_open" and not st.get("show")
       and disk_version(inst) == "0.92.0", "4 run open: skipped, not shown on the board")
    os.remove(os.path.join(live, "current"))
    st = run("--now")
    ok(st.get("status") == "updated" and disk_version(inst) == "0.93.0", "4 run over: pulled to 0.93.0")

    set_version(dev, "0.94.0")
    git(dev, "push", "-q")
    readme = os.path.join(inst, "plugin", "workflow-ui", "README.md")
    with open(readme, "a") as fh:
        fh.write("\nmy own change\n")
    st = run("--now")
    ok(st.get("status") == "skipped" and st.get("reason") == "local_changes" and st.get("show")
       and st.get("message") and disk_version(inst) == "0.93.0", "5 local changes: skipped, shown with the reason")
    git(inst, "checkout", "-q", "--", ".")

    git(inst, "commit", "-q", "--allow-empty", "-m", "mine")
    st = run("--now")
    ok(st.get("status") == "skipped" and st.get("reason") == "diverged", "6 own commits: skipped as diverged")
    git(inst, "reset", "-q", "--hard", "HEAD~1")

    git(dev, "tag", "workflow-manager--v0.94.0")
    set_version(dev, "0.95.0", "untagged work")
    git(dev, "push", "-q", "--tags", "origin", "main")
    st = run("--now")
    ok(st.get("status") == "updated" and disk_version(inst) == "0.94.0", "7 tags: the newest tag (0.94.0), not the tip")
    st = run("--now")
    ok(st.get("status") == "current", "7 then current, although the branch tip is 0.95.0")

    git(dev, "tag", "workflow-manager--v0.95.0")
    git(dev, "push", "-q", "--tags")
    os.makedirs(os.path.join(project, ".workflow-manager-data", "config"), exist_ok=True)
    with open(os.path.join(project, ".workflow-manager-data", "config", "settings.json"), "w") as fh:
        json.dump({"auto_update": False}, fh)
    before = run().get("checked")
    st = run("--now")
    ok(st.get("checked") == before and disk_version(inst) == "0.94.0", "8 auto_update off: never checks")

    # 9 the reload banner for a clone: only when a release changes what a chat reads at its start
    os.remove(os.path.join(project, ".workflow-manager-data", "config", "settings.json"))
    run("--now")

    def prompt(hooks_version):
        p = subprocess.run([sys.executable, "-I", os.path.join(scripts, "reload_check.py"), "prompt"],
                           input=json.dumps({"session_id": "s1"}), capture_output=True, text=True,
                           env=dict(env, WM_HOOKS_VERSION=hooks_version))
        with open(os.path.join(live, "reload.json")) as fh:
            return json.load(fh), p.stdout.strip()

    r, out = prompt("0.94.0")
    ok(disk_version(inst) == "0.95.0" and r.get("needed") is False and not out,
       "9 a release that only changes scripts: no banner, no note (it runs from the next message)")

    skill = os.path.join(dev, "plugin", "skills", "core-renamer", "SKILL.md")
    with open(skill) as fh:
        text = fh.read()
    with open(skill, "w") as fh:
        fh.write(text.replace("description: ", "description: (Changed.) ", 1))
    git(dev, "commit", "-qam", "a skill's description")
    set_version(dev, "0.96.0")
    git(dev, "tag", "delegate--v0.96.0")   # the new tag name after an old-named one
    git(dev, "push", "-q", "--tags", "origin", "main")
    run("--now")
    r, out = prompt("0.95.0")
    ok(disk_version(inst) == "0.96.0" and r.get("needed") and r.get("changed") == ["skills"]
       and r.get("running") == "0.95.0" and "/reload-plugins" in out,
       "9 a release that changes a skill's description: banner and note")
    r, out = prompt("0.96.0")
    ok(r.get("needed") is False and not out, "9 after /reload-plugins: cleared")

    if "--keep" not in sys.argv:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{'FAILED ' + str(len(FAILS)) if FAILS else 'all passed'}" + (f"  ({tmp})" if "--keep" in sys.argv else ""))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
