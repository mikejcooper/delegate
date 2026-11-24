#!/usr/bin/env python3
"""End-to-end test of migrate.py on throwaway copies. Nothing real is touched.

Builds, in a temp folder:
  plugin/.claude/   a copy of this plugin, version 0.6.0: the real migrations (0.4.0, 0.5.0) plus two
                    pretend releases: 0.5.5 (data only, can be told to fail) and 0.6.0 (data + user files)
  project/          a folder "made with 0.3.1" in the oldest layout: .dispatcher/ with traces + done list
                    directly inside, and one user skill with a board.json in its skill folder

Then checks, in order:
  1  a step that fails stops the walk, keeps the earlier steps, and leaves the version at the last good step
  2  the next run resumes from there and finishes, one backup and one log line per step, in order
  3  running again changes nothing
  4  the offer: shown once, a "no" changes nothing, not shown again the same day
  5  "yes" walks the user's file through every step, backed up first
  6  data newer than the plugin is left alone with a warning

    python3 -I test_walker.py            (optional: --keep to leave the temp folder for a look)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MIGRATIONS = os.path.dirname(HERE)
V = lambda x: tuple(int(p) for p in x.split("."))
REAL = sorted((d for d in os.listdir(MIGRATIONS) if d[0].isdigit()), key=V)   # the real releases, oldest first
FAILS, LAST = "90.5.0", "91.0.0"                                              # pretend releases, far ahead
ROOT = os.path.dirname(MIGRATIONS)               # the plugin's .claude/
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("  PASS " if ok else "  FAIL ") + name + (f"  ({detail})" if detail and not ok else ""))


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def build(tmp):
    plugin = os.path.join(tmp, "plugin", ".claude")
    shutil.copytree(os.path.join(ROOT, "workflow-ui", "scripts"), os.path.join(plugin, "workflow-ui", "scripts"),
                    ignore=shutil.ignore_patterns("__pycache__", ".watch.pid"))
    shutil.copytree(MIGRATIONS, os.path.join(plugin, "migrations"), ignore=shutil.ignore_patterns("__pycache__", "tests"))
    write(os.path.join(plugin, ".claude-plugin", "plugin.json"), json.dumps({"name": "workflow-manager", "version": LAST}))
    # pretend release FAILS: data only; fails when FAIL_PRETEND is set (after doing half its work)
    write(os.path.join(plugin, "migrations", FAILS, "data.py"), '''import os
def migrate(ctx):
    open(os.path.join(ctx["data"], "step-fails.txt"), "w").write("ran")
    if os.environ.get("FAIL_PRETEND"):
        raise RuntimeError("pretend failure")
    return ["wrote step-fails.txt"]
''')
    # pretend release LAST: data + user files
    write(os.path.join(plugin, "migrations", LAST, "data.py"), '''import os
def migrate(ctx):
    open(os.path.join(ctx["data"], "step-last.txt"), "w").write("ran")
    return ["wrote step-last.txt"]
''')
    write(os.path.join(plugin, "migrations", LAST, "user.py"), '''def upgrade(obj):
    obj = dict(obj)
    obj["tag"] = "last"
    return obj
''')
    project = os.path.join(tmp, "project")
    d = os.path.join(project, ".dispatcher")
    write(os.path.join(d, "traces", "dispatch-0001.jsonl"),
          json.dumps({"header": True, "run": "dispatch-0001", "kind": "trigger"}) + "\n"
          + json.dumps({"t": "2026-01-01T00:00:00Z", "end": True, "verdict": "ok"}) + "\n")
    write(os.path.join(d, "dispatcher-data", "ledger.jsonl"), json.dumps({"wf": "wf-00000000", "status": "done"}) + "\n")
    # a pretend board watcher from the old version, found only through its pid file in the old place
    watcher = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    write(os.path.join(d, ".watch.pid"), str(watcher.pid))
    write(os.path.join(project, ".claude", "skills", "workflow-sample", "SKILL.md"), "---\nname: workflow-sample\n---\n")
    write(os.path.join(project, ".claude", "skills", "workflow-sample", "board.json"),
          json.dumps({"workflows": [{"id": "sample"}]}, indent=2) + "\n")
    # a user skill on 0.6.0's rename list, whose board file points at itself and at a renamed org skill
    write(os.path.join(project, ".claude", "skills", "workflow-guardian-news", "SKILL.md"),
          "---\nname: workflow-guardian-news\ndescription: x. Not to be confused with workflow-guardian-newsletter.\n---\n"
          "Started by entry-guardian.\n")
    write(os.path.join(project, ".claude", "skills", "workflow-guardian-news", "board.json"),
          json.dumps({"workflows": [{"id": "g", "steps": [{"why": {"file": "workflow-guardian-news"}},
                                                         {"why": {"file": "workflow-security"}}]}]}, indent=2) + "\n")
    # a user trigger from before 0.6.0: renamed twice in a row, and its old Entry table updated
    write(os.path.join(project, ".claude", "skills", "entry-guardian", "SKILL.md"),
          "---\nname: entry-guardian\ndescription: Dispatcher entry point for The Guardian.\n---\n"
          "## Entry\n| Entry | Triggers | Item key |\n|---|---|---|\n| `guardian` | check the guardian | path |\n")
    return plugin, project, watcher


def run(plugin, project, *args, env_extra=None):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=project)
    env.pop("FAIL_PRETEND", None)
    env.update(env_extra or {})
    p = subprocess.run([sys.executable, "-I", os.path.join(plugin, "migrations", "migrate.py"), *args],
                       cwd=project, env=env, capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def main():
    keep = "--keep" in sys.argv
    tmp = tempfile.mkdtemp(prefix="migrate-test-")
    try:
        plugin, project, watcher = build(tmp)
        root = os.path.join(project, ".dispatcher")                  # the old folder
        home = os.path.join(project, ".workflow-manager-data")       # the new one (0.9.0)
        data = os.path.join(home, "system")                          # where steps from 0.8.0 on write
        vfile = os.path.join(data, "version.json")
        logf = os.path.join(data, "migrations.log")
        legacy_board = os.path.join(project, ".claude", "skills", "workflow-sample", "board.json")
        home_board = os.path.join(home, "config", "board", "workflow-sample.json")
        version = lambda: (read_json(vfile) or read_json(os.path.join(root, "data", "version.json"))
                           or read_json(os.path.join(root, "version.json")) or {}).get("data_version")
        backups = lambda: sorted(os.listdir(os.path.join(data, "backups"))) if os.path.isdir(os.path.join(data, "backups")) else []
        log_lines = lambda: open(logf).read().splitlines() if os.path.exists(logf) else []
        trace = os.path.join(home, "history", "requests", "dispatch-0001.jsonl")

        steps_all = REAL + [FAILS, LAST]
        froms = ["0.3.1"] + steps_all[:-1]
        print(f"Folder made with 0.3.1 (old layout, no version.json); plugin is {LAST};"
              f" steps: {', '.join(REAL)} (real), {FAILS}, {LAST} (pretend)\n")

        print(f"1. A step fails halfway ({FAILS})")
        rc, out, err = run(plugin, project, "--hook", env_extra={"FAIL_PRETEND": "1"})
        check("walk stops with an error (the hook itself swallows it)", rc != 0, f"rc={rc}")
        check(f"version left at the last good step ({REAL[-1]})", version() == REAL[-1], version())
        check("0.4.0 ran (trace header stamped)", os.path.exists(trace) and '"format": 2' in open(trace).readline())
        check("0.5.0 and 0.8.0 ran: the old folder is gone, data sorted into history/ and system/",
              not os.path.exists(root) and os.path.isfile(os.path.join(home, "history", "done-list.jsonl"))
              and os.path.isfile(vfile), sorted(os.listdir(project)))
        check(f"{LAST} did not run", not os.path.exists(os.path.join(data, "step-last.txt")))
        check("the failure is written in the log", any("FAILED" in l and FAILS in l for l in log_lines()),
              " | ".join(log_lines()))
        check("the user's board file was not touched", os.path.exists(legacy_board) and not os.path.exists(home_board))
        try:
            gone = watcher.wait(timeout=3) is not None
        except subprocess.TimeoutExpired:
            gone = False
            watcher.kill()
        check("the old board watcher was stopped (found via its old pid file)", gone)

        print("\n2. Next run resumes and finishes")
        rc, out, err = run(plugin, project, "--hook")
        check("runs cleanly", rc == 0, err.strip()[-200:])
        check(f"version is now {LAST}", version() == LAST, version())
        steps = [l.split(" data ")[1].split(":")[0] for l in log_lines() if " data " in l and "FAILED" not in l]
        check("one log line per finished step, in order",
              steps == [f"{a} -> {b}" for a, b in zip(froms, steps_all)], steps)
        check("a backup before each attempt, none reused",
              sorted((b.split("-")[0] for b in backups() if b[0].isdigit()), key=V) == sorted(froms + [REAL[-1]], key=V)
              and len(set(backups())) == len(froms) + 1, backups())
        first = next((b for b in backups() if b.startswith("0.3.1-")), "")   # by name, not sort order (0.10 sorts before 0.3)
        check("the first backup holds the old layout", os.path.isdir(os.path.join(data, "backups", first, ".dispatcher", "traces")), backups())
        check(f"{FAILS} re-ran cleanly and {LAST} ran", os.path.exists(os.path.join(data, "step-last.txt")))

        print("\n3. Running again")
        before = (backups(), len(log_lines()))
        run(plugin, project, "--hook")
        check("nothing new: no backup, no log line", (backups(), len(log_lines())) == before)

        print("\n4. The offer, and a \"no\"")
        offer_path = os.path.join(data, "offer.json")
        if os.path.exists(offer_path):
            os.remove(offer_path)   # step 2 already made the offer; start this check fresh
        rc, out, err = run(plugin, project, "--hook")
        check("offer shown for the user's out-of-date file", "workflow-sample/board.json" in out, out[:120])
        check("the offer says the file moves to .workflow-manager-data/config/board/", ".workflow-manager-data/config/board/" in out, out[-300:])
        check("the offer names every step's notes", all(v in out for v in [x for x in REAL if os.path.exists(os.path.join(MIGRATIONS, x, "user.py"))] + [LAST]))
        check("the offer says which skills get renamed", "workflow-guardian-news -> workflow-news-guardian-article" in out, out[-300:])
        check("the offer says which skills get the current format", "brought to the current format" in out, out[-300:])
        check("file unchanged and still in the skill folder after a no",
              read_json(legacy_board) == {"workflows": [{"id": "sample"}]} and not os.path.exists(home_board))
        rc, out2, err = run(plugin, project, "--hook")
        check("not offered again the same day", out2.strip() == "", out2[:120])

        print("\n5. A \"yes\"")
        rc, out, err = run(plugin, project, "--apply-user")
        b = read_json(home_board) or {}
        check("file now lives in .workflow-manager-data/config/board/, gone from the skill folder",
              os.path.exists(home_board) and not os.path.exists(legacy_board))
        check("walked through every step (0.4.0 format, last tag)", b.get("format") == 2 and b.get("tag") == "last", b)
        check(f"stamped {LAST}", b.get("data_version") == LAST, b.get("data_version"))
        skills = os.path.join(project, ".claude", "skills")
        gfile = os.path.join(skills, "workflow-news-guardian-article", "SKILL.md")
        check("user skill folder renamed", os.path.isfile(gfile) and not os.path.exists(os.path.join(skills, "workflow-guardian-news")),
              sorted(os.listdir(skills)))
        gtext = open(gfile).read() if os.path.isfile(gfile) else ""
        check("its name: line renamed, and its mention of a renamed skill", "name: workflow-news-guardian-article\n" in gtext
              and "Started by trigger-news-guardian-front-page." in gtext, gtext)
        check("a longer name that merely starts the same is left alone", "workflow-guardian-newsletter" in gtext, gtext)
        gb = read_json(os.path.join(home, "config", "board", "workflow-news-guardian-article.json")) or {}
        refs = [st["why"]["file"] for st in (gb.get("workflows") or [{}])[0].get("steps", [])]
        check("its board file follows the new name, with references renamed (its own and the org's)",
              refs == ["workflow-news-guardian-article", "workflow-security-alert"], refs)
        tg = os.path.join(skills, "trigger-news-guardian-front-page", "SKILL.md")
        ttext = open(tg).read() if os.path.isfile(tg) else ""
        check("an entry- skill renamed through both releases (entry-guardian -> trigger-news-guardian-front-page)",
              "name: trigger-news-guardian-front-page\n" in ttext and not os.path.exists(os.path.join(skills, "entry-guardian")),
              sorted(os.listdir(skills)))
        check("its description reworded for triggers (0.7.0)", "Dispatcher trigger for" in ttext, ttext)
        check("the user trigger's old table became a Definition block (0.10.0)",
              "## Definition" in ttext and "id: guardian" in ttext and "## Entry" not in ttext and "## Trigger\n" not in ttext, ttext)
        check("skill folder backed up before the rename", any(x.startswith("user-skills-") for x in backups()), backups())
        check("original backed up first", any(x.startswith("user-") for x in backups()), backups())
        check("one backup folder for the whole yes, not one per file",
              len([x for x in backups() if x.startswith("user-files-")]) == 1, backups())
        rc, out, err = run(plugin, project, "--check")
        check("nothing behind afterwards", "user_files_behind" not in out)

        print("\n6. Data newer than the plugin")
        with open(vfile, "w") as fh:
            json.dump({"data_version": "999.0.0"}, fh)
        before = (backups(), len(log_lines()))
        rc, out, err = run(plugin, project)
        check("warns", "newer than the plugin" in out, out[:120])
        check("leaves everything alone", version() == "999.0.0" and (backups(), len(log_lines())) == before)

        print("\n7. A brand-new folder (welcomed before its first check)")
        new = os.path.join(tmp, "new-project")
        write(os.path.join(new, ".workflow-manager-data", "system", "welcomed.json"), "{}")
        write(os.path.join(new, ".workflow-manager-data", "system", "board", "board-data.js"), "window.BOARD={};")
        os.makedirs(os.path.join(new, ".workflow-manager-data", "history", "runs"))
        write(os.path.join(new, ".workflow-manager-data", "history", "versions-cache.json"), "{}")   # the welcome's board build
        os.makedirs(os.path.join(new, ".claude"))
        rc, out, err = run(plugin, new)
        nsys = os.path.join(new, ".workflow-manager-data", "system")
        check("stamped with the plugin's version straight away", (read_json(os.path.join(nsys, "version.json")) or {}).get("data_version") == LAST,
              out.strip()[:120])
        check("no migration ran: no backups, no log", not os.path.exists(os.path.join(nsys, "backups"))
              and not os.path.exists(os.path.join(nsys, "migrations.log")), sorted(os.listdir(nsys)))
        check("no old .dispatcher/ folder made", not os.path.exists(os.path.join(new, ".dispatcher")))
        write(os.path.join(new, ".workflow-manager-data", "history", "runs", "x.jsonl"), "{}\n")
        os.remove(os.path.join(nsys, "version.json"))
        rc, out, err = run(plugin, new, "--check")
        check("a folder with history but no stamp still counts as old (0.3.1)", '"data_version": "0.3.1"' in out, out[:160])

        failed = [r for r in RESULTS if not r[1]]
        print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed" + (f"; temp folder kept: {tmp}" if keep else ""))
        return 1 if failed else 0
    finally:
        if not keep:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
