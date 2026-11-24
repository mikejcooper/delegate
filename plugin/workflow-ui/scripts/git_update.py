#!/usr/bin/env python3
"""Keep a plugin that runs from a git clone up to date: check its remote, and pull a newer release by itself.

For a plugin loaded in place from a clone of its public repo (a local folder marketplace, or --plugin-dir). A plugin
installed from a marketplace's cache is Claude Code's to update (reload_check.py tells the user when it has), and
the plugin's own source repo (paths.SOURCE) is never pulled.

On a message, at most every CHECK_EVERY (the prompt hook starts it in the background, so it never slows a message):
  1. The check, over HTTPS: `git ls-remote` of the public repo (the clone's remote, as an https:// address even when
     the clone was made over SSH) lists its release tags and branch tips, a few hundred bytes, no sign-in. The
     newest release tag (workflow-manager--v<version>, as `claude plugin tag` makes them) is the version on offer;
     a repo with no tags offers the tracked branch's tip, whose plugin.json is read over HTTPS from
     raw.githubusercontent.com (other hosts: fetched first). Nothing newer: done, nothing fetched.
  2. Newer: git fetch that tag (or branch) over the same HTTPS address. No password prompt: a fetch that needs one
     fails and is tried again next time.
  3. Only when that version is newer, and it is safe: no workflow run open, no test running, no local changes in
     the clone, and the clone's history is part of the remote's (a fast-forward). Otherwise it is skipped, says why
     on the board, and is tried again later.
  4. git merge --ff-only, then the new release's migrations (migrations/migrate.py, the new code), and the board's
     background helpers restart on the new code. The hooks run the new scripts from the next message; the hook list
     and the skills' text need /reload-plugins, and reload_check.py shows the banner for that.
Off when the folder's settings.json says "auto_update": false.

    python3 -I git_update.py run         what the hook runs: check (when due) and pull
    python3 -I git_update.py run --now   check now, whenever it last did
    python3 -I git_update.py             print the last result, change nothing
The last result is <live folder>/update.json (served as /update.json); each pull and skip is logged in
<system>/updates.log.
"""
import datetime
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402
import reload_check  # noqa: E402

CHECK_EVERY = 6 * 3600
RETRY_SKIPPED = 15 * 60          # a skipped update (a run open, a test) is tried again this soon
TAG_PREFIX = "workflow-manager--v"
STATE = paths.UPDATE
LOG = os.path.join(paths.SYSTEM, "updates.log")
GIT_ENV = dict(os.environ, GIT_TERMINAL_PROMPT="0", GIT_ASKPASS="true",
               GIT_SSH_COMMAND="ssh -o BatchMode=yes -o ConnectTimeout=15")

REASONS = {   # why an update was skipped, in the board's words
    "run_open": "a workflow run is open; it updates after the run",
    "test_running": "a test is running; it updates after the test",
    "local_changes": "the plugin's folder has changes of its own",
    "diverged": "the plugin's folder has commits that aren't in the public repo",
    "fetch_failed": "the public repo couldn't be reached",
    "no_remote": "the plugin's folder doesn't track a remote branch",
    "merge_failed": "git couldn't apply the update",
}
SHOW = ("local_changes", "diverged", "merge_failed")


def ver(s):
    try:
        return tuple(int(x) for x in str(s).split("."))
    except ValueError:
        return None


def git(repo, *args, timeout=30):
    """(ok, stdout) of a git command in repo."""
    try:
        p = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, timeout=timeout, env=GIT_ENV)
        return p.returncode == 0, p.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False, ""


def clone_of(root=paths.ROOT):
    """The git clone the plugin runs from: (repo top, plugin folder relative to it), or (None, None)."""
    ok, top = git(root, "rev-parse", "--show-toplevel")
    if not ok or not top:
        return None, None
    return top, os.path.relpath(os.path.realpath(root), os.path.realpath(top))


def version_at(repo, ref, rel):
    path = ".claude-plugin/plugin.json" if rel in ("", ".") else f"{rel}/.claude-plugin/plugin.json"
    ok, out = git(repo, "show", f"{ref}:{path}")
    try:
        return json.loads(out).get("version") if ok else None
    except ValueError:
        return None


def https_url(url):
    """The remote's address over HTTPS: git@host:owner/repo(.git) and ssh://git@host/owner/repo become
    https://host/owner/repo.git. https:// stays; a local path or file:// stays (tests, a mirror on disk)."""
    import re
    url = (url or "").strip()
    m = re.match(r"^(?:ssh://)?(?:[^@/]+@)?([^:/]+)[:/](?!/)(.+?)(?:\.git)?/?$", url)
    if url.startswith(("https://", "http://", "file://", "/")) or not m:
        return url
    return f"https://{m.group(1)}/{m.group(2)}.git"


def remote_refs(url):
    """{ref: sha} of the public repo over HTTPS (git ls-remote), or None when it can't be reached."""
    ok, out = git(".", "ls-remote", "--tags", "--heads", url, timeout=30)
    if not ok:
        return None
    refs = {}
    for line in out.splitlines():
        sha, _, ref = line.partition("\t")
        if ref and not ref.endswith("^{}"):
            refs[ref] = sha
    return refs


def raw_version(url, sha, rel):
    """plugin.json's version at a commit, read over HTTPS from raw.githubusercontent.com (GitHub only), or None."""
    import re
    import urllib.request
    m = re.match(r"^https://github\.com/([^/]+)/(.+?)(?:\.git)?$", url)
    if not m:
        return None
    path = ".claude-plugin/plugin.json" if rel in ("", ".") else f"{rel}/.claude-plugin/plugin.json"
    try:
        with urllib.request.urlopen(f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}/{sha}/{path}",
                                    timeout=20) as r:
            return json.loads(r.read().decode()).get("version")
    except Exception:
        return None


def offered(refs, branch):
    """(ref, version or None, sha) on offer: the newest release tag, else the tracked branch's tip; or None."""
    tags = [(ver(r[len("refs/tags/" + TAG_PREFIX):]), r) for r in refs if r.startswith("refs/tags/" + TAG_PREFIX)]
    tags = [(v, r) for v, r in tags if v]
    if tags:
        v, r = max(tags)
        return r, ".".join(map(str, v)), refs[r]
    head = f"refs/heads/{branch}"
    return (head, None, refs[head]) if branch and head in refs else None


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


def log(line):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(f"{stamp} {line}\n")


def turned_off():
    s = _read(paths.SETTINGS)
    return isinstance(s, dict) and s.get("auto_update") is False


def run_open():
    cur = _read(os.path.join(paths.LIVE, "current"))
    return bool(isinstance(cur, dict) and cur.get("run"))


def due(now):
    st = _read(STATE) or {}
    wait = RETRY_SKIPPED if st.get("status") == "skipped" and st.get("reason") in ("run_open", "test_running") else CHECK_EVERY
    return now - float(st.get("checked") or 0) >= wait


def lock_path(repo):
    """The update lock lives in the clone, not in a project folder: one clone can serve every folder on the
    computer (install.sh clones once), and only one of them may pull at a time."""
    return os.path.join(repo, ".git", "workflow-manager-update.lock")


def lock(path):
    """One update at a time per clone (two messages close together, or two folders, start two). A lock older than
    10 min is stale."""
    try:
        if time.time() - os.path.getmtime(path) > 600:
            os.remove(path)
    except OSError:
        pass
    try:
        os.close(os.open(path, os.O_CREAT | os.O_EXCL))
        return True
    except OSError:
        return False


def restart_helpers():
    """The board's watcher and always-on server hold the old Python code: stop the watcher (the prompt hook starts a
    new one on the next message) and restart the always-on server. Pages are read from disk, so they are new already."""
    try:
        with open(paths.WATCH_PID) as fh:
            os.kill(int(fh.read().strip()), 15)
        os.remove(paths.WATCH_PID)
    except (OSError, ValueError):
        pass
    try:
        import serve_board
        if sys.platform == "darwin" and serve_board.agent_on():
            subprocess.run(["launchctl", "kickstart", "-k", f"gui/{os.getuid()}/{serve_board.AGENT}"],
                           capture_output=True, timeout=10)
    except Exception:
        pass


def update(now=None, force=False):
    """Check and, when it is newer and safe, pull. Returns the state written (or None when nothing was due)."""
    now = now or time.time()
    if not paths.PLUGIN or paths.SOURCE or reload_check.where_cached()[0] or turned_off():
        return None
    repo, rel = clone_of()
    if not repo:
        return None
    if not force and not due(now):
        return None
    held = lock_path(repo)
    if not lock(held):
        return None
    try:
        return _update(repo, rel, now)
    finally:
        try:
            os.remove(held)
        except OSError:
            pass


def _update(repo, rel, now):
    current = reload_check.running_version()
    st = {"checked": now, "current": current, "available": None, "status": "", "reason": None}

    def done(status, reason=None, **more):
        st.update(status=status, reason=reason, **more)
        # the board shows the reasons that need the user (not a run or a test, which pass by themselves, nor a
        # failed fetch, which is usually just no network)
        st["show"] = reason in SHOW and bool(st.get("available"))
        st["message"] = REASONS.get(reason)
        if status in ("skipped", "updated", "failed"):
            log(f"{status} {current} -> {st.get('available')}" + (f": {reason}" if reason else ""))
        _write(STATE, st)
        return st

    ok, up = git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if not ok or "/" not in up:
        return done("failed", "no_remote")
    remote, branch = up.split("/", 1)
    ok, url = git(repo, "remote", "get-url", remote)
    url = https_url(url) if ok else ""
    refs = remote_refs(url) if url else None                  # 1. the check: one small HTTPS request
    if refs is None:
        return done("failed", "fetch_failed")
    offer = offered(refs, branch)
    if not offer:
        return done("failed", "no_remote")
    ref, avail, sha = offer
    if avail is None:                                         # no release tags: the branch tip's plugin.json
        avail = raw_version(url, sha, rel)
    if avail and ver(avail) and ver(current) and ver(avail) <= ver(current):
        st["available"] = avail
        return done("current")
    # 2. newer (or unknown until fetched): fetch it over HTTPS into the clone's own refs
    spec = f"+{ref}:{ref}" if ref.startswith("refs/tags/") else f"+{ref}:refs/remotes/{remote}/{branch}"
    ok, _ = git(repo, "fetch", "--quiet", "--no-tags", url, spec, timeout=120)
    if not ok:
        return done("failed", "fetch_failed")
    ref = ref if ref.startswith("refs/tags/") else f"refs/remotes/{remote}/{branch}"
    avail = version_at(repo, ref, rel) or avail
    st["available"] = avail
    if not avail or not ver(avail) or not ver(current) or ver(avail) <= ver(current):
        return done("current")
    if os.path.exists(paths.TEST_MODE):
        return done("skipped", "test_running")
    if run_open():
        return done("skipped", "run_open")
    ok, dirty = git(repo, "status", "--porcelain", "--untracked-files=no")
    if not ok or dirty:
        return done("skipped", "local_changes")
    ok, _ = git(repo, "merge-base", "--is-ancestor", "HEAD", ref)
    if not ok:
        return done("skipped", "diverged")
    ok, _ = git(repo, "merge", "--ff-only", "--quiet", ref, timeout=60)
    if not ok:
        return done("failed", "merge_failed")
    mig = os.path.join(paths.ROOT, "migrations", "migrate.py")   # the new release's walker, from disk
    if os.path.isfile(mig):
        subprocess.run([sys.executable, "-I", mig], capture_output=True, timeout=300)
    restart_helpers()
    return done("updated", None, previous=current, current=reload_check.running_version(), updated=now)


if __name__ == "__main__":
    if sys.argv[1:2] == ["run"]:
        update(force="--now" in sys.argv)
    else:
        print(json.dumps(dict(_read(STATE) or {}, clone=clone_of()[0], source=paths.SOURCE,
                              cached=bool(reload_check.where_cached()[0])), indent=1))
