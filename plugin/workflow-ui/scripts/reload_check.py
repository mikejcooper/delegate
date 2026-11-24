#!/usr/bin/env python3
"""Whether this Claude session runs an older copy of the plugin than the one on disk, so the user can be told to
type /reload-plugins.

Two ways an update lands while a session is open:
  cached     installed from a marketplace: Claude Code puts each version in its own folder
             (<plugins>/cache/<marketplace>/workflow-manager/<version>/) and records it in
             <plugins>/installed_plugins.json. The session's hooks keep running from the old folder, so the
             release's new code and migrations don't run until /reload-plugins.
  in place   loaded from a git clone (a local folder marketplace, or --plugin-dir), kept current by git_update.py.
             Hook scripts are read from disk every time, so the new code and migrations run at once; but the hook
             list (hooks.json) and the skills' text were read when the session started. hooks.json passes its own
             version to the prompt hook (WM_HOOKS_VERSION=<version>), so a session whose hook list is older than
             plugin.json on disk hasn't reloaded. Each release sets both (tests/test_reload_check.py checks they match).
Claude can't reload plugins itself, so the user has to be told.

The prompt hook runs it:
  prompt    (every message, hook JSON on stdin) writes <live folder>/reload.json (served as /reload.json):
            {"needed", "running", "installed", "session", "t"}; every board page shows a banner while "needed" is
            true, and the first message after the reload clears it. Prints one sentence for Claude the first time
            a session is found behind a given version, or nothing.
Never in the plugin's source repo (paths.SOURCE): there the version on disk is the one being worked on.

    python3 -I reload_check.py           print what it finds, as JSON, and change nothing
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402

NAME = "workflow-manager"
STATE = paths.RELOAD
NOTED = os.path.join(paths.LIVE, "reload-noted.json")      # session -> the version Claude was already told of
KEEP = 50                                                    # sessions remembered


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


def _remember(path, key, value):
    d = _read(path)
    d = d if isinstance(d, dict) else {}
    d.pop(key, None)
    d[key] = value
    _write(path, dict(list(d.items())[-KEEP:]))


def _real(p):
    return os.path.realpath(p) if p else ""


def _session(raw):
    try:
        return str((json.loads(raw or "{}") or {}).get("session_id") or "")
    except (ValueError, AttributeError):
        return ""


def running_version(root=paths.ROOT):
    """The version in plugin.json on disk now."""
    return (_read(os.path.join(root, ".claude-plugin", "plugin.json")) or {}).get("version") or "0.0.0"


def where_cached(root=paths.ROOT):
    """(plugins folder, marketplace) when root is a cached copy (<plugins>/cache/<marketplace>/<name>/<version>),
    else (None, None)."""
    parts = _real(root).split(os.sep)
    if len(parts) >= 5 and parts[-4] == "cache" and parts[-2] == NAME:
        return os.sep.join(parts[:-4]), parts[-3]
    return None, None


def installed(project, root=paths.ROOT):
    """The install Claude Code has on record for this project and this marketplace: {"version", "installPath"},
    or None. A project (or local) install for this folder comes before a user-wide one."""
    plugins, market = where_cached(root)
    if not plugins:
        return None
    data = _read(os.path.join(plugins, "installed_plugins.json")) or {}
    entries = (data.get("plugins") if isinstance(data.get("plugins"), dict) else data).get(f"{NAME}@{market}") or []
    if isinstance(entries, dict):
        entries = [entries]
    mine = [e for e in entries if isinstance(e, dict) and e.get("projectPath")
            and _real(e["projectPath"]) == _real(project)]
    everyone = [e for e in entries if isinstance(e, dict) and e.get("scope") == "user"]
    for e in mine + everyone:
        if e.get("installPath") and e.get("version"):
            return {"version": str(e["version"]), "installPath": e["installPath"]}
    return None


def check(project=paths.PROJECT, root=paths.ROOT, started=None):
    """{"needed": bool, "running": version, "installed": version or None}.
    cached: needed when the install on record is another copy than the one running, and that copy is on disk.
    in place: needed when the session started on another version than plugin.json says now (started: the version
    the session started on, None when unknown)."""
    disk = running_version(root)
    if where_cached(root)[0]:
        inst = installed(project, root)
        needed = bool(inst and _real(inst["installPath"]) != _real(root)
                      and os.path.isfile(os.path.join(inst["installPath"], ".claude-plugin", "plugin.json")))
        return {"needed": needed, "running": disk, "installed": inst["version"] if inst else None}
    run = started or disk
    changed = startup_changed(root, run) if run != disk else []
    return {"needed": bool(changed), "running": run, "installed": disk, **({"changed": changed} if changed else {})}


TAG = "workflow-manager--v"


def _git(repo, *args):
    import subprocess
    try:
        p = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=10)
        return p.stdout if p.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _frontmatter(text):
    """A SKILL.md's frontmatter (name, description, …): what Claude Code reads when a chat starts."""
    if not text or not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    return text[:end] if end > 0 else ""


def startup_changed(root, since):
    """What a chat that started on version `since` would still have old, now that the clone at root is newer:
    the parts Claude Code reads only when a chat starts (or on /reload-plugins). [] when nothing such changed, or
    when it can't tell (not a git clone, no release tag for that version): then no banner, as everything else
    (hook scripts, migrations, the board) runs from disk on the next message anyway.
      "hooks"     hooks.json, apart from its WM_HOOKS_VERSION, which moves on every release
      "skills"    a skill added, removed, or its name or description changed
      "commands"  a slash command added, removed or changed"""
    import re
    top = (_git(root, "rev-parse", "--show-toplevel") or "").strip()
    if not top:
        return []
    ref = f"refs/tags/{TAG}{since}"
    if _git(top, "rev-parse", "--verify", "--quiet", ref) is None:
        return []
    rel = os.path.relpath(os.path.realpath(root), os.path.realpath(top))
    pre = "" if rel == "." else rel + "/"

    def old(path):
        return _git(top, "show", f"{ref}:{pre}{path}")

    def new(path):
        try:
            with open(os.path.join(root, path), encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            return None

    def files(folder, pattern):
        was = {f[len(pre):] for f in (_git(top, "ls-tree", "-r", "--name-only", ref, "--", pre + folder) or "").split()}
        now = set()
        for d, _, fs in os.walk(os.path.join(root, folder)):
            now |= {os.path.relpath(os.path.join(d, f), root) for f in fs}
        return {f for f in was | now if re.search(pattern, f)}

    out = []
    strip = lambda t: re.sub(r"WM_HOOKS_VERSION=\S+ ", "", t or "")
    if strip(old("hooks/hooks.json")) != strip(new("hooks/hooks.json")):
        out.append("hooks")
    if any(_frontmatter(old(f)) != _frontmatter(new(f)) for f in files("skills", r"(^|/)SKILL\.md$")):
        out.append("skills")
    if any(old(f) != new(f) for f in files("commands", r"\.md$")):
        out.append("commands")
    return out


def note(state):
    """One sentence for Claude, the same words the board shows."""
    return (f"The workflow manager plugin was updated to {state['installed']}, but this session still runs "
            f"{state['running']}, so the update isn't fully in use yet. Claude can't reload plugins. After answering "
            "the user's message, tell them in one short line to type /reload-plugins in this chat to switch (or "
            "start a new session). Say it once; the board shows it too.")


def active():
    return paths.PLUGIN and not paths.SOURCE


def hooks_version():
    """The version of the hook list this session read (hooks.json passes it as WM_HOOKS_VERSION), or None for a
    hook list from before 0.13.7. Claude Code reads hooks.json when a session starts and on /reload-plugins, so this
    is the version the session's hooks and skills were loaded at."""
    return os.environ.get("WM_HOOKS_VERSION") or None


def prompt(raw):
    if not active():
        return ""
    session = _session(raw)
    state = dict(check(started=hooks_version()), session=session, t=time.time())
    _write(STATE, state)
    if not state["needed"]:
        return ""
    noted = _read(NOTED) or {}
    key = session or "?"
    if isinstance(noted, dict) and noted.get(key) == state["installed"]:
        return ""
    _remember(NOTED, key, state["installed"])
    return note(state)


if __name__ == "__main__":
    arg = sys.argv[1:]
    if arg == ["prompt"]:
        out = prompt(sys.stdin.read())
        if out:
            print(out)
    else:
        print(json.dumps(dict(check(), plugin=paths.PLUGIN, source=paths.SOURCE, cached=bool(where_cached()[0]),
                              live=STATE), indent=1))
