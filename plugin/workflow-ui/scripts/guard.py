#!/usr/bin/env python3
"""PreToolUse guard, plugin installs only: never let a session change the org layer.

When the plugin runs in someone's folder, the org layer (the plugin's own files, and the git repo
it came from) is read-only for that session. New skills, entry points and board files belong in the
folder's own .claude/skills/. In-project (the source repo itself) this does nothing.

Checks Edit / Write / MultiEdit / NotebookEdit by their file path, and Bash commands that name a
protected folder together with a writing command. A shell command can always hide a write, so the
architect's layer rule is the main defence; this is the backstop. Never blocks on its own errors.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402

SEGMENT = re.compile(r"\|\||&&|[;|\n]")
REDIRECT = re.compile(r"(?<![0-9&])>{1,2}\s*([^\s;|&<>]+)|[0-9]>{1,2}\s*([^\s;|&<>&]+)")
ANY_ARG = {"rm", "rmdir", "touch", "mkdir", "tee", "truncate", "chmod", "ln", "unzip", "tar"}


def _git_top(folder):
    try:
        out = subprocess.run(["git", "-C", folder, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=2)
        return out.stdout.strip() or None
    except Exception:
        return None


def _git_origin(folder):
    try:
        out = subprocess.run(["git", "-C", folder, "remote", "get-url", "origin"],
                             capture_output=True, text=True, timeout=2)
        url = out.stdout.strip()
    except Exception:
        return None
    if url.startswith("file://"):
        url = url[7:]
    return url if url and os.path.isdir(url) else None


def protected():
    """Folders this session must not change: the plugin root, its git repo, and that repo's local origin."""
    out = {os.path.realpath(paths.ROOT)}
    top = _git_top(paths.ROOT)
    if top:
        out.add(os.path.realpath(top))
        origin = _git_origin(top)
        if origin:
            out.add(os.path.realpath(origin))
    project = os.path.realpath(paths.PROJECT)
    return {p for p in out if p != project and not project.startswith(p + os.sep)}


def inside(path, folders):
    p = os.path.realpath(os.path.join(paths.PROJECT, os.path.expanduser(path)))
    return next((f for f in folders if p == f or p.startswith(f + os.sep)), None)


def deny(folder):
    reason = (f"Blocked: {folder} is the org dispatcher plugin (or its source), which is read-only from this folder. "
              f"Put new or changed skills in this folder's own {paths.rel(paths.USER_SKILLS)}/ instead "
              f"(a workflow is a workflow-<category>-<description> skill there, with its trigger inside it; a skill's "
              f"board definition is .workflow-manager-data/config/board/<skill name>.json). Org changes are made in the plugin's source repo, not from an install.")
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": reason}}))


def main():
    if not paths.PLUGIN or paths.SOURCE:   # in-project, or the plugin's own source repo: its files are yours to change
        return
    data = json.load(sys.stdin)
    tool, inp = str(data.get("tool_name", "")), data.get("tool_input") or {}
    folders = protected()
    if not folders:
        return
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        target = inp.get("file_path") or inp.get("notebook_path") or ""
        hit = inside(target, folders) if target else None
        if hit:
            deny(hit)
    elif tool == "Bash":
        hit = bash_write(str(inp.get("command", "")), folders)
        if hit:
            deny(hit)


def bash_write(cmd, folders):
    """The protected folder a shell command would write into, or None. Reading from it is fine."""
    import shlex
    if not any(f in cmd for f in folders):
        return None
    for seg in SEGMENT.split(cmd):
        for a, b in REDIRECT.findall(seg):
            target = a or b
            if target and target != "/dev/null" and not target.startswith("&"):
                hit = inside(target, folders)
                if hit:
                    return hit
        try:
            words = shlex.split(seg)
        except ValueError:
            words = seg.split()
        if not words:
            continue
        prog, args = os.path.basename(words[0]), [w for w in words[1:] if not w.startswith("-")]
        if prog in ANY_ARG or (prog in ("sed", "perl") and any(w.startswith("-i") or w == "-pi" for w in words[1:])):
            targets = args
        elif prog in ("cp", "mv", "rsync", "install") and args:
            targets = args[-1:]                       # only the destination is written
        elif prog == "git" and any(w in ("commit", "stash", "checkout", "reset", "apply", "push", "add", "rm", "mv", "restore", "clean")
                                   for w in words[1:]):
            targets = [w for w in words[1:] if w.startswith("/")] or [os.getcwd()]
        elif prog.startswith("python") and "open(" in seg and re.search(r"[\"']\s*[wa]\+?\s*[\"']", seg):
            targets = [f for f in folders if f in seg]
        else:
            continue
        for t in targets:
            hit = inside(t, folders)
            if hit:
                return hit
    return None


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # a broken guard must never stop the session
