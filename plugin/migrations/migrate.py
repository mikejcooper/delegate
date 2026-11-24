#!/usr/bin/env python3
"""Bring a folder's dispatcher data up to the installed plugin's version.

  migrations/<version>/   one folder per release that changed a file shape
      README.md           what changed, in plain words
      data.py             machine data (traces, done list, settings): migrate(ctx), run automatically
      renames.json        old skill name -> new name: the user's own skills on the list are renamed (folder,
                          name: line, references) and their board files follow, on their yes; the board
                          reads the old names as the new ones until then
      skill_text.json     exact text -> replacement, applied to the user's own SKILL.md files with the renames
      skills.py           convert(name, text) -> text: bigger changes to the user's own SKILL.md files (e.g. a
                          table becoming a Definition block), on their yes; must be safe to run twice
      user.py             the user's own board definitions (.workflow-manager-data/config/board/<skill>.json): upgrade(obj) -> obj,
                          rewritten only with --apply-user (the user said yes)
      tests/              sample old file -> expected new file

The folder's version lives in .workflow-manager-data/system/version.json ({"data_version": "x.y.z"}); in
0.8.x it was .workflow-manager/system/version.json, before that .dispatcher/data/version.json, and before
0.5.0 .dispatcher/version.json; all are still read.
A .dispatcher/ with no version.json at all was made before migrations existed and counts as BASELINE. The walker runs
every version folder after the folder's version, up to the plugin's, in order, one step at a time:
back up, run that step, write the new version. Stopped halfway, it resumes from the last step done.
Never goes backwards: a folder newer than the plugin is reported and left alone.

    python3 -I migrate.py              check, then migrate machine data (what the hook runs)
    python3 -I migrate.py --check      only say what would happen
    python3 -I migrate.py --apply-user also update the user's own board definitions (backed up first)
    python3 -I migrate.py --hook       what the prompt hook runs: migrate machine data, then print one
                                       plain sentence for Claude when the user's own files are behind
                                       (at most once a day per plugin version), or nothing
"""
import datetime
import importlib.util
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "workflow-ui", "scripts"))
import paths  # noqa: E402

BASELINE = "0.3.1"
VERSION_FILE = os.path.join(paths.SYSTEM, "version.json")
LEGACY_VERSION_FILES = ([os.path.join(paths.LEGACY_08, "system", "version.json"),  # 0.8.x
                         os.path.join(paths.LEGACY, "data", "version.json"),      # 0.5.0 - 0.7.x
                         os.path.join(paths.LEGACY, "version.json")] if paths.LEGACY else [])   # before 0.5.0
LOG = os.path.join(paths.SYSTEM, "migrations.log")
BACKUPS = os.path.join(paths.SYSTEM, "backups")
OFFER = os.path.join(paths.SYSTEM, "offer.json")   # when the user was last asked about their own files
OFFER_EVERY = 24 * 3600


def layout(at):
    """Where the machine data sat at version `at`, so each step sees the folder as it was when it was
    written: before 0.5.0 directly in .dispatcher/; 0.5.0 - 0.7.x in .dispatcher/data/; 0.8.x in
    .workflow-manager-data/; from 0.9.0 in .workflow-manager-data/ (both with config/, history/, system/).
    Every step also gets the new folder's paths, and "legacy_08" for the 0.8 folder."""
    new = {"dispatcher": paths.LEGACY, "legacy": paths.LEGACY, "legacy_08": paths.LEGACY_08, "home": paths.HOME, "config": paths.CONFIG,
           "history": paths.HISTORY, "system": paths.SYSTEM, "settings": paths.SETTINGS,
           "requests": paths.REQUESTS, "runs": paths.RUNS, "shots": paths.SHOTS, "done_list": paths.DONE_LIST,
           "board_defs": paths.BOARD_DEFS}
    if paths.LEGACY and ver(at) < ver("0.8.0"):
        data = paths.LEGACY if ver(at) < ver("0.5.0") else os.path.join(paths.LEGACY, "data")
        return dict(new, data=data, traces=os.path.join(data, "traces"), store=os.path.join(data, "dispatcher-data"))
    if paths.LEGACY_08 and ver(at) < ver("0.9.0"):
        r = paths.LEGACY_08
        return dict(new, data=os.path.join(r, "system"), traces=os.path.join(r, "history", "requests"),
                    store=os.path.join(r, "history"))
    return dict(new, data=paths.SYSTEM, traces=paths.REQUESTS, store=paths.HISTORY)


def ver(s):
    return tuple(int(x) for x in str(s).split("."))


def plugin_version():
    with open(os.path.join(ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
        return json.load(fh)["version"]


def data_version():
    for f in [VERSION_FILE] + LEGACY_VERSION_FILES:
        try:
            with open(f, encoding="utf-8") as fh:
                return json.load(fh)["data_version"]
        except (OSError, ValueError, KeyError):
            continue
    has_data = any(_has_data(r) for r in (paths.LEGACY, paths.LEGACY_08, paths.HOME) if r)
    return BASELINE if has_data else None


# What a brand-new folder may already hold in system/ before its first check: the welcome (welcome.py, run at
# SessionStart and by install.sh, before the prompt hook's first check), the offer note and the board's generated
# files. A folder with only these is new, not one "made before migrations existed".
FRESH_SYSTEM = {"welcomed.json", "offer.json", "board"}


def _has_data(root):
    """Whether root holds data from before version stamps. The old folders: anything but board/ and config/.
    .workflow-manager-data/: run history (a request, a run or the done list, what the old steps work on), or
    anything in system/ beyond FRESH_SYSTEM. Caches the board writes in history/ before the first check
    (versions-cache.json) and config/ (the user's own) never count."""
    if not os.path.isdir(root):
        return False
    names = os.listdir(root)
    if os.path.realpath(root) != os.path.realpath(paths.HOME or ""):
        return any(n not in ("board", "config") for n in names)
    for n in names:
        p = os.path.join(root, n)
        if n == "config":
            continue
        if n == "system":
            if any(x not in FRESH_SYSTEM for x in os.listdir(p)):
                return True
        elif n == "history":
            if os.path.isfile(os.path.join(p, "done-list.jsonl")) or any(
                    files for d in ("requests", "runs") for _, _, files in os.walk(os.path.join(p, d))):
                return True
        elif not n.startswith("."):
            return True
    return False


def set_data_version(v):
    os.makedirs(paths.SYSTEM, exist_ok=True)
    tmp = VERSION_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"data_version": v}, fh)
    os.replace(tmp, VERSION_FILE)


def steps_between(old, new):
    """Version folders after old, up to and including new, in order."""
    found = []
    for name in os.listdir(HERE):
        try:
            v = ver(name)
        except ValueError:
            continue
        if ver(old) < v <= ver(new) and os.path.isdir(os.path.join(HERE, name)):
            found.append(name)
    return sorted(found, key=ver)


def load(step, name):
    path = os.path.join(HERE, step, name + ".py")
    if not os.path.isfile(path):
        return None
    spec = importlib.util.spec_from_file_location(f"mig_{step.replace('.', '_')}_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def log(line):
    os.makedirs(paths.SYSTEM, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(f"{stamp} {line}\n")


def fresh(base):
    """base, or base-2, base-3 ... : never reuse a backup folder (a retry can come within the same second)."""
    dest, n = base, 2
    while os.path.exists(dest):
        dest, n = f"{base}-{n}", n + 1
    return dest


def backup(step_from):
    """Copy the old folders (.dispatcher/, .workflow-manager-data/) and the new one (whichever exist), except backups and
    generated files, into system/backups/<from version>-<time>/ under their own names."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = fresh(os.path.join(BACKUPS, f"{step_from}-{stamp}"))
    ignore = shutil.ignore_patterns("backups", "*.js", "*.pid", "live", ".live")
    os.makedirs(dest)
    for root in (paths.LEGACY, paths.LEGACY_08, paths.HOME):
        if root and os.path.isdir(root):
            shutil.copytree(root, os.path.join(dest, os.path.basename(root)), ignore=ignore)
    return dest


def stop_helpers():
    """After a migration the board's background helpers may be running old code or old paths:
    stop them; the prompt hook starts fresh ones straight after."""
    import signal
    import subprocess
    stopped = []
    old = ([os.path.join(paths.LEGACY, x, ".watch.pid") for x in ("data", "")]
           + [os.path.join(paths.LEGACY_08, "system", "board", ".watch.pid")]) if paths.LEGACY else []
    for pidfile in {paths.WATCH_PID, *old}:
        try:
            with open(pidfile) as fh:
                pid = int(fh.read().strip())
            os.kill(pid, signal.SIGTERM)
            stopped.append(f"watcher {pid}")
        except (OSError, ValueError):
            pass
        try:
            os.remove(pidfile)
        except OSError:
            pass
    try:
        out = subprocess.run(["lsof", "-ti", f"tcp:{paths.PORT}", "-sTCP:LISTEN"], capture_output=True,
                             text=True, timeout=3).stdout.split()
        for pid in out:
            os.kill(int(pid), signal.SIGTERM)
            stopped.append(f"board server {pid}")
    except Exception:
        pass
    return stopped


def tidy_up(folder):
    """Remove folder and its parents while they are empty and inside an old folder (never the new one)."""
    olds = [os.path.realpath(r) for r in (paths.LEGACY, paths.LEGACY_08) if r]
    d = os.path.realpath(folder)
    while any(d == o or d.startswith(o + os.sep) for o in olds):
        try:
            if os.listdir(d):
                return
            os.rmdir(d)
        except OSError:
            return
        d = os.path.dirname(d)


def all_renames():
    """Every renames.json up to the plugin's version, applied in order (a -> b, then b -> c gives a -> c)."""
    out = {}
    for step in steps_between("0.0.0", plugin_version()):
        try:
            with open(os.path.join(HERE, step, "renames.json"), encoding="utf-8") as fh:
                more = json.load(fh)
        except (OSError, ValueError):
            continue
        out = {k: more.get(v, v) for k, v in out.items()}
        out.update({k: v for k, v in more.items() if k not in out})
    return out


def skill_converters():
    """Every skills.py up to the plugin's version, oldest first."""
    out = []
    for step in steps_between("0.0.0", plugin_version()):
        mod = load(step, "skills")
        if mod and callable(getattr(mod, "convert", None)):
            out.append((step, mod.convert))
    return out


def skills_to_update():
    """[(SKILL.md path, new text, steps)]: the user's own skills a converter would change."""
    out = []
    if not paths.BOARD_DEFS or not os.path.isdir(paths.USER_SKILLS):
        return out
    conv = skill_converters()
    for n in sorted(os.listdir(paths.USER_SKILLS)):
        f = os.path.join(paths.USER_SKILLS, n, "SKILL.md")
        if not os.path.isfile(f):
            continue
        with open(f, encoding="utf-8") as fh:
            text = new = fh.read()
        steps = []
        for step, fn in conv:
            changed = fn(n, new)
            if changed != new:
                steps.append(step)
                new = changed
        if steps:
            out.append((f, new, steps))
    return out


def update_user_skills(todo):
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = fresh(os.path.join(BACKUPS, f"user-skill-text-{stamp}"))
    done = []
    for f, new, steps in todo:
        name = os.path.basename(os.path.dirname(f))
        os.makedirs(os.path.join(dest, name), exist_ok=True)
        shutil.copy2(f, os.path.join(dest, name, "SKILL.md"))
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(new)
        done.append(name)
        log(f"user skill updated ({', '.join(steps)}): {name} (backup {os.path.relpath(dest, paths.SYSTEM)})")
    return done


def all_skill_text():
    """Every skill_text.json up to the plugin's version: exact text -> replacement, in order."""
    out = {}
    for step in steps_between("0.0.0", plugin_version()):
        try:
            with open(os.path.join(HERE, step, "skill_text.json"), encoding="utf-8") as fh:
                out.update(json.load(fh))
        except (OSError, ValueError):
            continue
    return out


NAME_TOKEN = r"(?<![a-z0-9-]){}(?![a-z0-9-])"


def skills_to_rename():
    """[(old folder, new name)]: the user's own skills whose name is on a rename list."""
    import re
    out, ren = [], all_renames()
    if not paths.BOARD_DEFS or not os.path.isdir(paths.USER_SKILLS):
        return out
    for n in sorted(os.listdir(paths.USER_SKILLS)):
        d = os.path.join(paths.USER_SKILLS, n)
        if n in ren and os.path.isfile(os.path.join(d, "SKILL.md")) and not os.path.exists(os.path.join(paths.USER_SKILLS, ren[n])):
            out.append((d, ren[n]))
    return out


def rename_user_skills(todo):
    """Rename each folder, its name: line, and every reference to a renamed skill in the user's SKILL.md files."""
    import re
    ren = all_renames()
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = fresh(os.path.join(BACKUPS, f"user-skills-{stamp}"))
    for d, _ in todo:
        shutil.copytree(d, os.path.join(dest, os.path.basename(d)))
    done = []
    for d, new in todo:
        target = os.path.join(paths.USER_SKILLS, new)
        os.rename(d, target)
        done.append(f"{os.path.basename(d)} -> {new}")
    for n in os.listdir(paths.USER_SKILLS):
        f = os.path.join(paths.USER_SKILLS, n, "SKILL.md")
        if not os.path.isfile(f):
            continue
        with open(f, encoding="utf-8") as fh:
            text = fh.read()
        new_text = text
        for old, new in ren.items():
            new_text = re.sub(NAME_TOKEN.format(re.escape(old)), new, new_text)
        for old, new in all_skill_text().items():
            new_text = new_text.replace(old, new)
        if new_text != text:
            with open(f, "w", encoding="utf-8") as fh:
                fh.write(new_text)
    for line in done:
        log(f"user skill renamed: {line} (backup {os.path.relpath(dest, paths.SYSTEM)})")
    return done


def user_files():
    """The user's own board definitions (user layer only): (path now, path it belongs at, obj, version).
    Home is .workflow-manager-data/config/board/<skill>.json; older ones sit in .workflow-manager-data/config/board/
    (0.8), .dispatcher/board/ (0.5 - 0.7) or as board.json in the skill folder (before 0.5)."""
    out = []
    if not paths.BOARD_DEFS:
        return out
    found = {}
    for folder in (paths.BOARD_DEFS, os.path.join(paths.LEGACY_08, "config", "board"), os.path.join(paths.LEGACY, "board")):
        if os.path.isdir(folder):
            for f in sorted(os.listdir(folder)):
                if f.endswith(".json") and f[:-5] not in found:
                    found[f[:-5]] = os.path.join(folder, f)
    try:
        names = sorted(os.listdir(paths.USER_SKILLS))
    except OSError:
        names = []
    for n in names:
        legacy = os.path.join(paths.USER_SKILLS, n, "board.json")
        if n not in found and os.path.isfile(legacy):
            found[n] = legacy
    for n, p in sorted(found.items()):
        try:
            with open(p, encoding="utf-8") as fh:
                obj = json.load(fh)
        except (OSError, ValueError):
            continue
        n_new = all_renames().get(n, n)   # a renamed skill's board file takes its new name
        out.append((p, os.path.join(paths.BOARD_DEFS, n_new + ".json"), obj, obj.get("data_version", BASELINE)))
    return out


def backup_user(paths_list, tag):
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = fresh(os.path.join(BACKUPS, f"user-{tag}-{stamp}"))
    for p in paths_list:
        rel = os.path.relpath(p, paths.PROJECT)
        os.makedirs(os.path.dirname(os.path.join(dest, rel)), exist_ok=True)
        shutil.copy2(p, os.path.join(dest, rel))
    return dest


def offer_note(report):
    """One sentence for Claude when the user's own files are behind, at most once a day per version."""
    behind = report.get("user_files_behind") or []
    renames = report.get("user_skills_to_rename") or []
    updates = report.get("user_skills_to_update") or []
    if not behind and not renames and not updates:
        return ""
    import time
    try:
        with open(OFFER, encoding="utf-8") as fh:
            last = json.load(fh)
    except (OSError, ValueError):
        last = {}
    if last.get("for") == report["plugin_version"] and time.time() - last.get("t", 0) < OFFER_EVERY:
        return ""
    with open(OFFER, "w", encoding="utf-8") as fh:
        json.dump({"for": report["plugin_version"], "t": time.time()}, fh)
    moving = any(b.get("moves_to") and not b["file"].startswith(".workflow-manager-data/") for b in behind)  # moves folder, not just renamed
    parts = []
    if behind:
        oldest = min((b["is"] for b in behind), key=ver)
        parts.append(f"{len(behind)} of the user's own board files ({', '.join(b['file'] for b in behind)}) were made with "
                     f"workflow manager {oldest} and can be updated"
                     + (" (this also moves them into .workflow-manager-data/config/board/<skill>.json)" if moving else ""))
    if renames:
        parts.append(f"{len(renames)} of their skills can be renamed to the naming pattern ({'; '.join(renames)})")
    if updates:
        parts.append(f"{len(updates)} of their skills can be brought to the current format ({', '.join(updates)}: e.g. a "
                     "trigger's table becomes a Definition block)")
    steps = {s for b in behind for s in b["steps"]}
    if updates:
        steps |= {s for s in steps_between("0.0.0", report["plugin_version"]) if os.path.isfile(os.path.join(HERE, s, "skills.py"))}
    steps = sorted(steps, key=ver)
    readmes = ", ".join(os.path.join(HERE, s, "README.md") for s in steps)
    return (f"Plugin update to {report['plugin_version']}: " + "; ".join(parts) + ". "
            + (f"What changes, in plain words, is in {readmes}. " if readmes else "")
            + "Their work keeps running either way. After answering their message (or at the end of a request), ask "
            "them once, in one short question, whether to update them; a backup is made first. "
            f"Only on a clear yes, run: python3 -I {os.path.abspath(__file__)} --apply-user  and tell them what changed. "
            "On no, leave them; they can ask the skill architect later.")


def main():
    check = "--check" in sys.argv
    apply_user = "--apply-user" in sys.argv
    hook = "--hook" in sys.argv
    if not paths.PLUGIN:
        if not hook:
            print("In-project (the source repo): nothing to migrate.")
        return 0
    have, want = data_version(), plugin_version()
    if have is None:  # brand new folder: nothing to upgrade, just stamp it
        if not check:
            set_data_version(want)
        if not hook:
            print(f"New folder: stamped {want}.")
        return 0
    if ver(have) > ver(want):
        if not hook:
            print(f"WARNING this folder's data is {have}, newer than the plugin ({want}). Left alone.")
        return 0
    steps = steps_between(have, want)
    report = {"folder": paths.PROJECT, "data_version": have, "plugin_version": want, "steps": steps}
    # 1. machine data: automatic, one step at a time. Stop the board helpers first: they may hold old
    #    paths, and a step may move or delete the pid files that find them. The hook restarts them after.
    if steps and not check:
        stopped = stop_helpers()
        if stopped:
            log("stopped the board helpers before migrating (the hook restarts them): " + ", ".join(stopped))
    for step in steps:
        mod = load(step, "data")
        if check:
            continue
        where = backup(have)
        try:
            changes = mod.migrate(layout(have)) if mod else []
        except Exception as err:  # stop here: the version stays at the last good step, so the next run retries this one
            log(f"FAILED data {have} -> {step}: {type(err).__name__}: {err}; version stays {have}; "
                f"backup from before this step: {os.path.relpath(where, paths.SYSTEM)}")
            if not hook:
                print(json.dumps(dict(report, failed={"step": step, "error": str(err),
                                                      "backup": os.path.relpath(where, paths.PROJECT)}), indent=1))
            return 1
        set_data_version(step)
        log(f"data {have} -> {step}: backup {os.path.relpath(where, paths.SYSTEM)}; " + "; ".join(changes or ["no data changes"]))
        report.setdefault("done", []).append({"step": step, "backup": os.path.relpath(where, paths.PROJECT),
                                               "changes": changes or []})
        have = step
    if not check and data_version() != want:
        set_data_version(want)  # releases with no migration folder just move the stamp on

    # 2. the user's own files: listed, rewritten only on --apply-user
    behind, todo_user = [], []
    for path, home, obj, fver in user_files():
        todo = steps_between(fver, want)
        mods = [(s, load(s, "user")) for s in todo]
        mods = [(s, m) for s, m in mods if m]
        if not mods:
            continue
        if apply_user and not check:
            todo_user.append((path, home, obj, fver, mods))
        else:
            behind.append({"file": paths.rel(path), "is": fver, "steps": [s for s, _ in mods],
                           **({"moves_to": paths.rel(home)} if path != home else {})})
    if todo_user:   # one backup of every file this yes changes, then each file walked through its steps
        where = backup_user([t[0] for t in todo_user], "files")
        for path, home, obj, fver, mods in todo_user:
            rel = paths.rel(path)
            for s, m in mods:
                obj = m.upgrade(obj)
                obj["data_version"] = s
            os.makedirs(os.path.dirname(home), exist_ok=True)
            with open(home, "w", encoding="utf-8") as fh:   # always written to its home, .workflow-manager-data/config/board/
                json.dump(obj, fh, indent=2)
                fh.write("\n")
            if os.path.realpath(path) != os.path.realpath(home):
                os.remove(path)
                tidy_up(os.path.dirname(path))
            moved = f", moved to {paths.rel(home)}" if path != home else ""
            log(f"user file {rel}: {fver} -> {obj['data_version']}{moved} (backup {os.path.relpath(where, paths.SYSTEM)})")
            report.setdefault("user_updated", []).append(rel + (f" -> {paths.rel(home)}" if path != home else ""))
    if behind:
        report["user_files_behind"] = behind
    todo = skills_to_rename()
    if todo and apply_user and not check:
        report["user_skills_renamed"] = rename_user_skills(todo)
    elif todo:
        report["user_skills_to_rename"] = [f"{os.path.basename(d)} -> {n}" for d, n in todo]
    upd = skills_to_update()     # after renames, so converters see the new names
    if upd and apply_user and not check:
        report["user_skills_updated"] = update_user_skills(upd)
    elif upd:
        report["user_skills_to_update"] = [os.path.basename(os.path.dirname(f)) for f, _, _ in upd]
    if hook:
        note = offer_note(report)
        if note:
            print(note)
        return 0
    print(json.dumps(report, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
