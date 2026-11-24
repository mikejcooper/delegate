#!/usr/bin/env python3
"""Sharing: a workflow, an update or a problem run as one zip, and the zip brought in at the other end
(core-sharer). Nothing here reaches outside this folder: a zip is passed on by hand (Slack, email, a drive).

A share zip:
    manifest.json                      what it is: kind, workflow, version, skills, runs, note (never who made it)
    current/skills/<skill>/...         the skills as shared: the workflow, the shared processes it uses and the
    current/board/<skill>.json         connections it reaches (their setup steps only: never a sign-in or a key)
    versions/<skill>/<vN>/...          each published version, so the next update finds what both sides started from
    base/...                           a fix made on a debugging copy: what the sender had when they shared the issue
    runs/<run>.jsonl                   an issue: the runs picked, item runs of a batch with it
    recordings/<skill>/<id>.json       an issue: what those runs read (the short fields the recordings keep)

Kinds: full (the whole workflow, for someone new), update (a newer version for people who have it), issue (runs
that went wrong, so someone can debug them), fix (an update made on a debugging copy, sent back).

    share.py make <skill> --kind full|update|issue [--runs RUN ...] [--note TEXT] [--out DIR]
                                             the zip goes to ~/Downloads (--out: elsewhere)
    share.py make --debug <slug> [--note TEXT] [--out DIR]       a fix: the debugging copy, sent back
    share.py runs <skill> [--max N]          the workflow's recent runs, newest first, for picking an issue's runs
    share.py inspect <zip>                   what the zip is and what bringing it in would do (writes nothing)
    share.py import <zip>                    a workflow you don't have yet: added as a draft, marked imported
    share.py merge <zip> [--fresh] [--take ID=mine|theirs ...]
                                             an update of one you have: your changes kept, theirs added; where both
                                             changed the same thing yours stays until --take says otherwise;
                                             --fresh takes the update as it is (yours stays in Versions)
    share.py debug <zip>                     an issue: a debugging copy under Debugging, with its runs, apart from
                                             your own workflows and never run on its own
    share.py debugs                          the debugging copies
    share.py remove-debug <slug>             take a debugging copy off the board
    share.py impact <skill>                  what changed since you last shared it (or since its previous version)

Every command prints one JSON object; an "error" key means nothing was changed.
"""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402

FORMAT = "workflow-manager-share"
FORMAT_VERSION = 1
KINDS = ("full", "update", "issue", "fix")
MAX_BYTES = 50 * 1024 * 1024    # a zip bigger than this once unpacked is refused
MAX_FILES = 3000
SKIP_DIRS = {"tests", "__pycache__", "node_modules", ".git"}
SKIP_FILES = {".DS_Store"}
SECRET = re.compile(r"""(?i)(\b(api[_-]?key|secret|password|passwd|token|bearer)\b\s*[:=]\s*['"][^'"\s]{8,}['"]"""
                    r"""|\bsk-[A-Za-z0-9_-]{20,}|\bxox[bpas]-[A-Za-z0-9-]{10,}|\bAKIA[0-9A-Z]{16}\b"""
                    r"""|\bgh[pousr]_[A-Za-z0-9]{30,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)""")
TO_READER = re.compile(r"(?i)\b(ignore (all |any )?(previous|prior|above) instructions|you are now|disregard (the|your) "
                       r"(rules|instructions)|send (it|this|them) to [^\s]+@)")
SKILL_REF = re.compile(r"\b((?:shared|connection)-[a-z0-9][a-z0-9-]*[a-z0-9])\b")

if paths.PLUGIN:
    SHARES = os.path.join(paths.HISTORY, "shares")      # log.jsonl of what was shared; zips with no Downloads folder
    SHARED = os.path.join(paths.CONFIG, "shared")       # imported workflows: <skill>.json, <skill>/base/, <skill>/pending/
    DEBUG = os.path.join(paths.HOME, "debug")           # debugging copies: <slug>/
else:
    SHARES = SHARED = DEBUG = None


def out(obj, code=0):
    print(json.dumps(obj, indent=1, ensure_ascii=False))
    sys.exit(code)


def fail(msg, **more):
    out(dict({"error": msg}, **more), 1)


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def need_plugin():
    if not paths.PLUGIN:
        fail("sharing needs the plugin installed in a folder (its data lives in .workflow-manager-data)")


# ---------------------------------------------------------------- snapshots: {relpath: bytes}
# A snapshot holds one or more skills as "skills/<skill>/<file>" and "board/<skill>.json".

def _walk_skill(folder, skill):
    snap = {}
    for root, dirs, files in os.walk(folder):
        rel_root = os.path.relpath(root, folder)
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not (rel_root == "." and d == "tests"))
        for f in sorted(files):
            if f in SKIP_FILES or f.endswith(".pyc"):
                continue
            p = os.path.join(root, f)
            if os.path.islink(p):
                continue
            rel = os.path.normpath(os.path.join(rel_root, f)).replace(os.sep, "/")
            with open(p, "rb") as fh:
                snap[f"skills/{skill}/{rel}"] = fh.read()
    return snap


def local_snapshot(skill, skills_dir=None, board_dir=None):
    """The skill as it is on disk now (its tests are never part of it)."""
    skills_dir = skills_dir or paths.USER_SKILLS
    board_dir = board_dir or paths.BOARD_DEFS
    snap = {}
    folder = os.path.join(skills_dir, skill)
    if os.path.isdir(folder):
        snap.update(_walk_skill(folder, skill))
    b = os.path.join(board_dir, skill + ".json")
    if os.path.isfile(b):
        with open(b, "rb") as fh:
            snap[f"board/{skill}.json"] = fh.read()
    return snap


def only(snap, skill):
    return {k: v for k, v in snap.items() if k.startswith(f"skills/{skill}/") or k == f"board/{skill}.json"}


def digest(snap):
    h = hashlib.sha256()
    for k in sorted(snap):
        h.update(k.encode() + b"\0" + hashlib.sha256(snap[k]).digest())
    return h.hexdigest()[:16]


def write_snapshot(snap, skill, skills_dir=None, board_dir=None, exact=True):
    """Put a skill's files on disk. exact: files of the skill not in the snapshot are removed (tests always stay)."""
    skills_dir = skills_dir or paths.USER_SKILLS
    board_dir = board_dir or paths.BOARD_DEFS
    folder = os.path.join(skills_dir, skill)
    mine = only(snap, skill)
    if exact and os.path.isdir(folder):
        have = _walk_skill(folder, skill)
        for k in have:
            if k not in mine:
                os.remove(os.path.join(folder, k[len(f"skills/{skill}/"):]))
    for k, v in mine.items():
        if k.startswith("board/"):
            dest = os.path.join(board_dir, skill + ".json")
        else:
            dest = os.path.join(folder, k[len(f"skills/{skill}/"):])
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(v)
    b = os.path.join(board_dir, skill + ".json")
    if exact and f"board/{skill}.json" not in mine and os.path.isfile(b):
        os.remove(b)


def save_dir(snap, folder):
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    for k, v in snap.items():
        dest = os.path.join(folder, k)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fh:
            fh.write(v)


def load_dir(folder):
    snap = {}
    if not os.path.isdir(folder):
        return snap
    for root, _dirs, files in os.walk(folder):
        for f in files:
            if f in SKIP_FILES:
                continue
            p = os.path.join(root, f)
            with open(p, "rb") as fh:
                snap[os.path.relpath(p, folder).replace(os.sep, "/")] = fh.read()
    return snap


# ---------------------------------------------------------------- the skill history (skill_history.py's git)

def _hist():
    try:
        import skill_history
        return skill_history if skill_history.ready() else None
    except (Exception, SystemExit):
        return None


def version_list(skill):
    h = _hist()
    if not h:
        return []
    try:
        return h.versions(skill).get(skill) or []
    except (Exception, SystemExit):
        return []


def snapshot_at(commit, skill):
    """A skill's files at one commit of the skill history."""
    h = _hist()
    snap = {}
    if not h:
        return snap
    srel, brel = h.SKILLS_REL, h.BOARD_REL
    try:
        names = h.git("ls-tree", "-r", "--name-only", commit, "--", f"{srel}/{skill}", f"{brel}/{skill}.json").splitlines()
    except SystemExit:
        return snap
    for n in names:
        if n.startswith(f"{srel}/{skill}/"):
            rel = n[len(f"{srel}/{skill}/"):]
            parts = rel.split("/")
            if parts[0] == "tests" or any(p in SKIP_DIRS for p in parts[:-1]) or parts[-1] in SKIP_FILES or rel.endswith(".pyc"):
                continue
            key = f"skills/{skill}/{rel}"
        elif n == f"{brel}/{skill}.json":
            key = f"board/{skill}.json"
        else:
            continue
        env = dict(os.environ, GIT_DIR=h.GIT_DIR, GIT_WORK_TREE=paths.PROJECT)
        r = subprocess.run(["git", "show", f"{commit}:{n}"], cwd=paths.PROJECT, env=env, capture_output=True)
        if r.returncode == 0:
            snap[key] = r.stdout
    return snap


def published_versions(skill):
    """[(vN, snapshot, info)] oldest first."""
    outv = []
    for v in version_list(skill):
        snap = snapshot_at(v["commit"], skill)
        if snap:
            outv.append((v["v"], snap, {"v": v["v"], "t": v.get("t"), "text": v.get("text", "")}))
    return outv


def is_draft(skill):
    h = _hist()
    try:
        return bool(h and h.is_draft(skill))
    except (Exception, SystemExit):
        return False


# ---------------------------------------------------------------- what a workflow takes with it

def related(skill, snap):
    """The shared processes and connections a skill names that exist in this folder."""
    names = set()
    for k, v in snap.items():
        if k.endswith((".md", ".json")):
            names.update(SKILL_REF.findall(v.decode("utf-8", "replace")))
    # the Definition's uses: block names connections by system ("  slack: send you one message", "uses: gmail, slack")
    md = snap.get(f"skills/{skill}/SKILL.md", b"").decode("utf-8", "replace")
    m = re.search(r"^uses:[ \t]*(.*)$((?:\n[ \t]+\S.*)*)", md, re.M)
    if m:
        for part in re.split(r"[,\n]", m.group(1) + m.group(2)):
            name = part.strip().split(":")[0].strip().lower()
            if re.match(r"^[a-z0-9][a-z0-9-]*$", name):
                names.add("connection-" + name)
    names.discard(skill)
    return sorted(n for n in names if os.path.isdir(os.path.join(paths.USER_SKILLS, n)))


def board_workflow(snap, skill):
    raw = snap.get(f"board/{skill}.json")
    if not raw:
        return {}
    try:
        d = json.loads(raw)
    except ValueError:
        return {}
    ws = d.get("workflows") or []
    return ws[0] if ws else {}


def title_of(snap, skill):
    w = board_workflow(snap, skill)
    if w.get("short") or w.get("name"):
        return w.get("short") or w.get("name")
    md = snap.get(f"skills/{skill}/SKILL.md", b"").decode("utf-8", "replace")
    m = re.search(r"^#\s+(.+)$", md, re.M)
    return m.group(1).strip() if m else skill


def short_name(skill):
    return re.sub(r"^(workflow|shared|connection)-", "", skill)


def secrets_in(snap):
    hits = []
    for k, v in snap.items():
        try:
            text = v.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if SECRET.search(line):
                hits.append(f"{k}:{i}")
    return hits


def to_reader(snap):
    hits = []
    for k, v in snap.items():
        try:
            text = v.decode("utf-8")
        except UnicodeDecodeError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if TO_READER.search(line):
                hits.append(f"{k}:{i}")
    return hits


# ---------------------------------------------------------------- runs

def _header(path):
    try:
        with open(path, encoding="utf-8") as fh:
            first = fh.readline()
        h = json.loads(first)
        return h if isinstance(h, dict) and h.get("header") else None
    except (OSError, ValueError):
        return None


def _end(path):
    end = None
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if '"end"' in line:
                    try:
                        o = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(o, dict) and o.get("end"):
                        end = o
    except OSError:
        pass
    return end


def runs_of(skill, board_id=None):
    """Top-level runs of a workflow (a batch, or a run with no batch), newest first, with the files each one needs."""
    if not os.path.isdir(paths.RUNS):
        return []
    files = sorted(f for f in os.listdir(paths.RUNS) if f.endswith(".jsonl"))
    heads = {}
    for f in files:
        h = _header(os.path.join(paths.RUNS, f))
        if h:
            heads[f] = h
    mine = {f: h for f, h in heads.items() if h.get("skill") == skill or (board_id and h.get("flow") == board_id)}
    items = {}
    for f, h in heads.items():
        if h.get("batch"):
            items.setdefault(h["batch"], []).append(f)
    top = []
    for f, h in mine.items():
        if h.get("batch") and any(x.get("run") == h["batch"] for x in mine.values()):
            continue   # an item of a batch that is listed itself
        rid = h.get("run") or f[:-6]
        end = _end(os.path.join(paths.RUNS, f)) or {}
        top.append({"run": rid, "label": h.get("label") or rid, "started": h.get("started", ""),
                    "status": end.get("status") or ("done" if end else "unfinished"),
                    "attention": end.get("attention", ""), "summary": (end.get("summary") or "")[:200],
                    "try": bool(h.get("try")), "test": bool(h.get("test")),
                    "files": [f] + sorted(items.get(rid, []))})
    top.sort(key=lambda r: r["started"], reverse=True)
    return top


def recordings_for(skill, run_ids):
    """{zip path: bytes}: the skill's recordings made by these runs (or their items)."""
    found = {}
    folder = os.path.join(paths.USER_SKILLS, skill, "tests", "recordings")
    if not os.path.isdir(folder):
        return found
    for f in sorted(os.listdir(folder)):
        if not f.endswith(".json"):
            continue
        p = os.path.join(folder, f)
        try:
            with open(p, encoding="utf-8") as fh:
                rec = json.load(fh)
        except (OSError, ValueError):
            continue
        fr = str(rec.get("from_run", ""))
        if any(fr == r or fr.startswith(r + "-") or fr.rsplit("-a", 1)[0] == r for r in run_ids):
            with open(p, "rb") as fh:
                found[f"recordings/{skill}/{f}"] = fh.read()
    return found


# ---------------------------------------------------------------- make

def _zip(path, files):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for k in sorted(files):
            zi = zipfile.ZipInfo(k, date_time=(2020, 1, 1, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, files[k])
    os.replace(tmp, path)


def zip_name(title, kind, version, since="", runs=0):
    """delegate--<workflow>_<kind>_<version>[...].zip, so a share says what made it and what it is, in a Downloads list
    or a chat:
        delegate--wework-invoices_workflow_v3.zip                       the whole workflow, for someone new
        delegate--wework-invoices_update_v2-to-v3.zip                   an update, and the version it updates
        delegate--airtable-uptime-email_issue_v2_2-runs_2026-11-24.zip  runs that went wrong
        delegate--airtable-uptime-email_fix_v2_2026-11-24.zip           a fix made on a debugging copy, sent back
    The workflow's own short name, lower case with hyphens; a draft's version is "v2-draft"."""
    slug = re.sub(r"[^a-z0-9]+", "-", (title or "workflow").lower()).strip("-")[:50] or "workflow"
    ver = re.sub(r"[^A-Za-z0-9.-]+", "-", (version or "draft").replace("+", "-")).strip("-")
    day = time.strftime("%Y-%m-%d")
    if kind == "full":
        parts = [slug, "workflow", ver]
    elif kind == "update":
        parts = [slug, "update", f"{since}-to-{ver}" if since and since != ver else ver]
    elif kind == "issue":
        parts = [slug, "issue", ver, f"{runs}-run" + ("" if runs == 1 else "s"), day]
    else:
        parts = [slug, "fix", re.sub(r"-fix$", "", ver), day]
    return "delegate--" + "_".join(parts) + ".zip"


def default_out():
    """Where a share lands: the Downloads folder, where people look for a file to send; the shares folder without one."""
    dl = os.path.join(os.path.expanduser("~"), "Downloads")
    return dl if os.path.isdir(dl) else SHARES


def _unique(path):
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    n = 2
    while os.path.exists(f"{stem}-{n}{ext}"):
        n += 1
    return f"{stem}-{n}{ext}"


def _log(entry):
    os.makedirs(SHARES, exist_ok=True)
    with open(os.path.join(SHARES, "log.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def share_log(skill=None):
    outl = []
    try:
        with open(os.path.join(SHARES, "log.jsonl"), encoding="utf-8") as fh:
            for line in fh:
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if skill is None or e.get("skill") == skill:
                    outl.append(e)
    except (OSError, TypeError):
        pass
    return outl


def plugin_version():
    try:
        with open(os.path.join(paths.ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
            return json.load(fh).get("version", "")
    except (OSError, ValueError):
        return ""


def cmd_make(a):
    need_plugin()
    if a.debug:
        return make_fix(a)
    skill = a.skill
    if not skill:
        fail("say which workflow to share")
    if not os.path.isdir(os.path.join(paths.USER_SKILLS, skill)):
        fail(f"no workflow {skill} in this folder's skills")
    kind = a.kind or "full"
    if kind not in ("full", "update", "issue"):
        fail("kind is full, update or issue")
    skills = [skill] + related(skill, local_snapshot(skill))
    files, manifest_versions, left_out, version = {}, {}, [], ""
    for sk in skills:
        vs = published_versions(sk)
        manifest_versions[sk] = [dict(info, hash=digest(snap)) for _v, snap, info in vs]
        for v, snap, _info in vs:
            for k, b in snap.items():
                files[f"versions/{sk}/{v}/{k}"] = b
        draft = is_draft(sk)
        if kind == "issue" or not vs:
            cur = local_snapshot(sk)          # an issue shows what ran; a never-published skill has only its draft
            ver = (vs[-1][0] + "+draft") if (vs and draft) else (vs[-1][0] if vs else "draft")
        else:
            cur = vs[-1][1]                   # the last published version: a draft stays here
            ver = vs[-1][0]
            if draft:
                left_out.append(f"{sk}: its unpublished draft (shared as {ver})")
        for k, b in cur.items():
            files["current/" + k] = b
        if sk == skill:
            version = ver
    current = {k[len("current/"):]: v for k, v in files.items() if k.startswith("current/")}
    hits = secrets_in(current)
    if hits:
        fail("it looks like a password or key is written in it; take it out (connections keep their own sign-ins) "
             "and share again", at=hits)
    runs = []
    if kind == "issue":
        if not a.runs:
            fail("an issue needs at least one run: share.py runs " + skill + " lists them")
        board_id = board_workflow(current, skill).get("id")
        have = {r["run"]: r for r in runs_of(skill, board_id)}
        ids = list(a.runs)
        for rid in a.runs:
            r = have.get(rid)
            if not r:
                fail(f"no run {rid} of {skill}", runs=list(have)[:20])
            for f in r["files"]:
                with open(os.path.join(paths.RUNS, f), "rb") as fh:
                    files[f"runs/{f}"] = fh.read()
            runs.append({k: r[k] for k in ("run", "label", "started", "status", "summary")})
            ids.extend(f[:-len(".jsonl")] for f in r["files"])
        files.update(recordings_for(skill, ids))
    title = title_of(current, skill)
    manifest = {"format": FORMAT, "format_version": FORMAT_VERSION, "kind": kind, "workflow": skill, "title": title,
                "board_id": board_workflow(current, skill).get("id", ""), "version": version, "skills": skills,
                "versions": manifest_versions, "hash": {sk: digest(only(current, sk)) for sk in skills},
                "note": a.note or "", "runs": runs, "made": now_iso(), "plugin": plugin_version(),
                "connections": [s for s in skills if s.startswith("connection-")]}
    files["manifest.json"] = json.dumps(manifest, indent=1, ensure_ascii=False).encode()
    since = ""
    if kind == "update":   # what it updates from: the version shared before this one, else the one before it
        vs_ = [v["v"] for v in version_list(skill)]
        earlier = [e.get("version") for e in share_log(skill) if e.get("kind") in ("full", "update") and e.get("version") != version]
        since = earlier[-1] if earlier else (vs_[-2] if len(vs_) > 1 and vs_[-1] == version else "")
    name = zip_name(title, kind, version, since=since, runs=len(runs))
    dest = _unique(os.path.join(os.path.abspath(a.out) if a.out else default_out(), name))
    _zip(dest, files)
    _log({"t": now_iso(), "skill": skill, "kind": kind, "version": version, "file": dest,
          "runs": [r["run"] for r in runs]})
    out({"made": dest, "kind": kind, "workflow": skill, "title": title, "version": version, "skills": skills,
         "runs": [r["run"] for r in runs], "left_out": left_out, "bytes": os.path.getsize(dest)})


def make_fix(a):
    slug = a.debug
    root = os.path.join(DEBUG, slug)
    if not os.path.isfile(os.path.join(root, "manifest.json")):
        fail(f"no debugging copy {slug}")
    with open(os.path.join(root, "manifest.json"), encoding="utf-8") as fh:
        m = json.load(fh)
    current = load_dir(os.path.join(root, "current"))
    base = load_dir(os.path.join(root, "base"))
    hits = secrets_in(current)
    if hits:
        fail("it looks like a password or key is written in it; take it out and share again", at=hits)
    files = {"current/" + k: v for k, v in current.items()}
    files.update({"base/" + k: v for k, v in base.items()})
    files.update({"versions/" + k: v for k, v in load_dir(os.path.join(root, "versions")).items()})
    skill = m["workflow"]
    manifest = {"format": FORMAT, "format_version": FORMAT_VERSION, "kind": "fix", "workflow": skill,
                "title": m.get("title", skill), "board_id": m.get("board_id", ""), "version": m.get("version", "") + "+fix",
                "skills": m.get("skills", [skill]), "versions": m.get("versions", {}),
                "hash": {sk: digest(only(current, sk)) for sk in m.get("skills", [skill])},
                "base_hash": {sk: digest(only(base, sk)) for sk in m.get("skills", [skill])},
                "note": a.note or "", "runs": [], "made": now_iso(), "plugin": plugin_version(),
                "connections": m.get("connections", [])}
    files["manifest.json"] = json.dumps(manifest, indent=1, ensure_ascii=False).encode()
    dest = _unique(os.path.join(os.path.abspath(a.out) if a.out else default_out(),
                                zip_name(m.get("title") or short_name(skill), "fix", m.get("version", ""))))
    _zip(dest, files)
    _log({"t": now_iso(), "skill": skill, "kind": "fix", "debug": slug, "file": dest})
    changed = sorted(k for k in set(current) | set(base) if current.get(k) != base.get(k))
    out({"made": dest, "kind": "fix", "workflow": skill, "changed": changed, "bytes": os.path.getsize(dest)})


# ---------------------------------------------------------------- reading a zip safely

def read_zip(path):
    """{name: bytes} of a zip, refusing anything that could write outside where it is unpacked."""
    if not os.path.isfile(path):
        fail(f"no file {path}")
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        fail("that isn't a zip file")
    files, total = {}, 0
    with z:
        infos = z.infolist()
        if len(infos) > MAX_FILES:
            fail(f"it has {len(infos)} files; a share has at most {MAX_FILES}")
        for zi in infos:
            n = zi.filename
            if zi.is_dir():
                continue
            mode = (zi.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                fail(f"it holds a link ({n}); a share never does")
            norm = os.path.normpath(n).replace(os.sep, "/")
            if n.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", n) or norm.startswith("..") or "/../" in "/" + norm + "/":
                fail(f"it holds a file outside its own folder ({n})")
            total += zi.file_size
            if total > MAX_BYTES:
                fail("it is too big once unpacked (over 50 MB)")
            parts = norm.split("/")
            if parts[0] == "__MACOSX" or parts[-1] in SKIP_FILES:
                continue
            files[norm] = z.read(zi)
    # a zip of a folder: everything under one top folder
    tops = {k.split("/")[0] for k in files}
    if len(tops) == 1 and not any("/" not in k for k in files):
        top = tops.pop() + "/"
        if (top + "manifest.json") in files or not any(k.endswith("manifest.json") for k in files):
            files = {k[len(top):]: v for k, v in files.items()}
    return files


def manifest_of(files):
    raw = files.get("manifest.json")
    if not raw:
        return None
    try:
        m = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(m, dict) or m.get("format") != FORMAT:
        return None
    if m.get("kind") not in KINDS or not re.match(r"^[a-z0-9][a-z0-9-]*$", str(m.get("workflow", ""))):
        return None
    if any(not re.match(r"^[a-z0-9][a-z0-9-]*$", str(s)) for s in m.get("skills") or []):
        return None
    return m


def sub(files, prefix):
    return {k[len(prefix):]: v for k, v in files.items() if k.startswith(prefix)}


def zip_versions(files, skill):
    """[(vN, snapshot)] oldest first, from the zip's versions/ folder."""
    vs = {}
    pre = f"versions/{skill}/"
    for k, v in files.items():
        if k.startswith(pre):
            ver, rest = k[len(pre):].split("/", 1)
            vs.setdefault(ver, {})[rest] = v
    return sorted(vs.items(), key=lambda x: int(re.sub(r"\D", "", x[0]) or 0))


# ---------------------------------------------------------------- what both sides started from

def local_candidates(skill):
    """Snapshots this folder has had of the skill: what it last imported, then each published version."""
    cands = []
    s = only(load_dir(os.path.join(SHARED, skill, "base")), skill)
    if s:
        cands.append(("imported", s))
    for v, snap, _info in reversed(published_versions(skill)):
        cands.append((v, snap))
    return cands


def find_base(files, skill, local_now):
    """The newest snapshot both sides had: (label, snapshot) or (None, {})."""
    theirs = []
    if any(k.startswith("base/") for k in files):
        b = only(sub(files, "base/"), skill)
        if b:
            theirs.append(("what you shared", b))
    for v, snap in reversed(zip_versions(files, skill)):
        theirs.append((v, snap))
    mine = local_candidates(skill) + [("now", local_now)]
    mine_d = {digest(s): lab for lab, s in mine if s}
    for lab, s in theirs:
        if digest(s) in mine_d:
            return lab, s
    return None, {}


# ---------------------------------------------------------------- three-way merge

def _merge_text(base, mine, theirs, label):
    """(merged bytes, [conflict]) taking mine where both changed the same lines; each conflict has both sides."""
    with tempfile.TemporaryDirectory() as d:
        pm, pb, pt = (os.path.join(d, x) for x in ("mine", "base", "theirs"))
        for p, b in ((pm, mine), (pb, base), (pt, theirs)):
            with open(p, "wb") as fh:
                fh.write(b)
        r = subprocess.run(["git", "merge-file", "-p", "--diff3", "-L", "yours", "-L", "base", "-L", "theirs",
                            pm, pb, pt], capture_output=True)
        if r.returncode < 0 or r.returncode > 127:
            raise RuntimeError("git merge-file failed")
        text = r.stdout.decode("utf-8", "replace")
    if r.returncode == 0:
        return r.stdout, []
    outl, conflicts, i = [], [], 0
    lines = text.splitlines(keepends=True)
    while i < len(lines):
        ln = lines[i]
        if ln.startswith("<<<<<<< "):
            m_, b_, t_ = [], [], []
            i += 1
            while i < len(lines) and not lines[i].startswith(("||||||| ", "=======")):
                m_.append(lines[i]); i += 1
            if i < len(lines) and lines[i].startswith("||||||| "):
                i += 1
                while i < len(lines) and not lines[i].startswith("======="):
                    b_.append(lines[i]); i += 1
            i += 1
            while i < len(lines) and not lines[i].startswith(">>>>>>> "):
                t_.append(lines[i]); i += 1
            i += 1
            conflicts.append({"where": label, "yours": "".join(m_), "theirs": "".join(t_), "base": "".join(b_),
                              "at": len(outl)})
            outl.append(None)   # filled in by resolve
        else:
            outl.append(ln)
            i += 1
    return outl, conflicts


def _key_of(x):
    if isinstance(x, dict):
        for k in ("key", "id", "label"):
            if isinstance(x.get(k), str):
                return k + ":" + x[k]
    return None


def _merge_json(base, mine, theirs, where, conflicts):
    """Structural merge: objects key by key, lists of keyed objects item by item, anything else as one value."""
    if mine == theirs:
        return mine
    if mine == base:
        return theirs
    if theirs == base:
        return mine
    if isinstance(mine, dict) and isinstance(theirs, dict):
        b = base if isinstance(base, dict) else {}
        res = {}
        for k in list(theirs) + [k for k in mine if k not in theirs]:
            res_v = _merge_json(b.get(k, _MISSING), mine.get(k, _MISSING), theirs.get(k, _MISSING), where + [k], conflicts)
            if res_v is not _MISSING:
                res[k] = res_v
        return res
    if (isinstance(mine, list) and isinstance(theirs, list) and mine + theirs
            and all(_key_of(x) for x in mine + theirs)):
        b = base if isinstance(base, list) and all(_key_of(x) for x in base) else []
        bm, mm, tm = ({_key_of(x): x for x in L} for L in (b, mine, theirs))
        order = [_key_of(x) for x in theirs]
        for i, x in enumerate(mine):   # one only you added: after the item before it in yours
            k = _key_of(x)
            if k not in tm and k not in bm:
                prev = _key_of(mine[i - 1]) if i else None
                order.insert(order.index(prev) + 1 if prev in order else 0, k)
        res = []
        for k in order:
            v = _merge_json(bm.get(k, _MISSING), mm.get(k, _MISSING), tm.get(k, _MISSING), where + [k], conflicts)
            if v is not _MISSING:
                res.append(v)
        return res
    if mine is _MISSING and base is not _MISSING and theirs != base:
        conflicts.append({"where": where, "yours": None, "theirs": theirs, "base": base})
        return _Pick(mine, theirs, len(conflicts) - 1)
    if theirs is _MISSING and base is not _MISSING and mine != base:
        conflicts.append({"where": where, "yours": mine, "theirs": None, "base": base})
        return _Pick(mine, theirs, len(conflicts) - 1)
    conflicts.append({"where": where, "yours": mine, "theirs": theirs, "base": base})
    return _Pick(mine, theirs, len(conflicts) - 1)


class _Missing:
    def __repr__(self):
        return "MISSING"


_MISSING = _Missing()


class _Pick:
    def __init__(self, mine, theirs, idx):
        self.mine, self.theirs, self.idx = mine, theirs, idx


def _resolve_json(v, choice):
    if isinstance(v, _Pick):
        return _resolve_json(v.theirs if choice.get(v.idx) == "theirs" else v.mine, choice)
    if isinstance(v, dict):
        res = {}
        for k, x in v.items():
            r = _resolve_json(x, choice)
            if r is not _MISSING:
                res[k] = r
        return res
    if isinstance(v, list):
        return [r for r in (_resolve_json(x, choice) for x in v) if r is not _MISSING]
    return v


def _step_title(board, where):
    """A conflict's place in plain words: the step's title when it is inside one."""
    try:
        node = board
        for w in where:
            if isinstance(node, list):
                node = next(x for x in node if _key_of(x) == w)
            else:
                node = node[w]
            if isinstance(node, dict) and node.get("title") and node.get("key"):
                return f"the step \"{node['title']}\""
    except (StopIteration, KeyError, TypeError):
        pass
    return "the setting " + ".".join(str(w).split(":", 1)[-1] for w in where[-2:])


def merge_snapshots(base, mine, theirs, takes, start=0):
    """(merged snapshot, conflicts, summary) for one skill. takes: {conflict id: "mine"|"theirs"}; ids go on from start."""
    keys = sorted(set(base) | set(mine) | set(theirs))
    merged, conflicts, summary = {}, [], {"added": [], "changed": [], "removed": [], "kept_yours": []}
    for k in keys:
        b, m, t = base.get(k), mine.get(k), theirs.get(k)
        if m == t:
            if m is not None:
                merged[k] = m
            continue
        if m == b:            # only they changed it
            if t is not None:
                merged[k] = t
                summary["added" if b is None else "changed"].append(k)
            else:
                summary["removed"].append(k)
            continue
        if t == b:            # only you changed it
            if m is not None:
                merged[k] = m
                summary["kept_yours"].append(k)
            continue
        # both changed it
        if m is None or t is None:
            cid = f"c{start + len(conflicts) + 1}"
            kept = takes.get(cid, "mine")
            conflicts.append({"id": cid, "file": k, "what": f"{k}: " + ("you removed it, the update changed it" if m is None
                              else "you changed it, the update removed it"), "yours": _txt(m), "theirs": _txt(t),
                              "taking": kept})
            pick = t if kept == "theirs" else m
            if pick is not None:
                merged[k] = pick
            continue
        if k.endswith(".json"):
            try:
                jb = json.loads(b) if b else {}
                jm, jt = json.loads(m), json.loads(t)
            except ValueError:
                jb = jm = jt = None
            if jm is not None:
                local = []
                res = _merge_json(jb, jm, jt, [], local)
                choice = {}
                for i, c in enumerate(local):
                    cid = f"c{start + len(conflicts) + 1}"
                    choice[i] = takes.get(cid, "mine")
                    conflicts.append({"id": cid, "file": k, "what": _step_title(jm, c["where"]),
                                      "path": [str(w) for w in c["where"]], "yours": _short(c["yours"]),
                                      "theirs": _short(c["theirs"]), "taking": choice[i]})
                merged[k] = (json.dumps(_resolve_json(res, choice), indent=1, ensure_ascii=False) + "\n").encode()
                summary["changed"].append(k)
                continue
        try:
            res, local = _merge_text(b or b"", m, t, k)
        except RuntimeError:
            res, local = None, None
        if local is None:
            cid = f"c{start + len(conflicts) + 1}"
            kept = takes.get(cid, "mine")
            conflicts.append({"id": cid, "file": k, "what": k, "yours": "(a file)", "theirs": "(a file)", "taking": kept})
            merged[k] = t if kept == "theirs" else m
            continue
        if not local:
            merged[k] = res
            summary["changed"].append(k)
            continue
        for c in local:
            cid = f"c{start + len(conflicts) + 1}"
            kept = takes.get(cid, "mine")
            res[c["at"]] = c["theirs"] if kept == "theirs" else c["yours"]
            conflicts.append({"id": cid, "file": k, "what": _text_where(m, c["yours"], k), "yours": c["yours"],
                              "theirs": c["theirs"], "taking": kept})
        merged[k] = "".join(res).encode()
        summary["changed"].append(k)
    return merged, conflicts, summary


def _txt(b):
    if b is None:
        return None
    try:
        return b.decode("utf-8")[:600]
    except UnicodeDecodeError:
        return "(a file)"


def _short(v):
    if v is None or v is _MISSING:
        return None
    if isinstance(v, str):
        return v[:600]
    return json.dumps(v, ensure_ascii=False)[:600]


def _text_where(mine_bytes, chunk, k):
    """The heading a conflicting chunk sits under, e.g. 'Step 3: Write the reminder' in SKILL.md."""
    text = mine_bytes.decode("utf-8", "replace")
    pos = text.find(chunk) if chunk else -1
    if pos < 0:
        return k
    heads = re.findall(r"^(?:#+\s+|\*\*)(.+?)(?:\*\*)?\s*$", text[:pos], re.M)
    return f"\"{heads[-1].strip(' *.')}\"" if heads else k


# ---------------------------------------------------------------- inspect / import / merge

def plan_for(files, m):
    """What bringing the zip in would do, skill by skill. Writes nothing."""
    skills = m.get("skills") or [m["workflow"]]
    per, n_conf = [], 0
    for sk in skills:
        theirs = only(sub(files, "current/"), sk)
        mine = local_snapshot(sk)
        entry = {"skill": sk, "files": len(theirs)}
        if not mine:
            entry["plan"] = "new"
        elif digest(mine) == digest(theirs):
            entry["plan"] = "same"
        else:
            lab, base = find_base(files, sk, mine)
            entry["base"] = lab
            if lab is None:
                entry["plan"] = "merge"
                entry["no_common_version"] = True
            elif digest(base) == digest(mine):
                entry["plan"] = "update"          # you haven't changed it: it simply updates
            elif digest(base) == digest(theirs):
                entry["plan"] = "same"            # they have nothing new for you; yours has more
                entry["yours_is_newer"] = True
            else:
                entry["plan"] = "merge"
            if entry["plan"] in ("update", "merge"):
                _merged, conflicts, summary = merge_snapshots(base, mine, theirs, {}, n_conf)
                n_conf += len(conflicts)
                entry["conflicts"] = conflicts
                entry["changes"] = {k: len(v) for k, v in summary.items()}
            if sk.startswith("connection-") and entry["plan"] != "same":
                entry["plan"] = "keep"            # your own way in stays yours
                entry.pop("conflicts", None)
        per.append(entry)
    return per


def cmd_inspect(a):
    need_plugin()
    files = read_zip(a.zip)
    m = manifest_of(files)
    if not m:
        skills = sorted({k.rsplit("/", 1)[0] or "." for k in files if k.endswith("SKILL.md")})
        if skills:
            stem = re.sub(r"[^a-z0-9-]+", "-", os.path.splitext(os.path.basename(a.zip))[0].lower()).strip("-") or "skill"
            dest = os.path.join(SHARES, "incoming", stem)
            save_dir(files, dest)
            out({"what": "skill", "plan": "architect-import", "skills": skills, "unpacked": dest,
                 "say": "a skill made somewhere else: the architect imports it (Import mode) from the unpacked folder"})
        fail("not a Delegate share and no skill in it", files=sorted(files)[:20])
    current = sub(files, "current/")
    res = {"what": m["kind"], "workflow": m["workflow"], "title": m.get("title"), "version": m.get("version"),
           "note": m.get("note", ""), "made": m.get("made", ""), "skills": m.get("skills"),
           "connections": m.get("connections", []), "runs": m.get("runs", []),
           "credentials_at": secrets_in(current), "instructions_to_the_reader_at": to_reader(current)}
    if m["kind"] == "issue":
        res["plan"] = "debug"
    else:
        per = plan_for(files, m)
        main = next((p for p in per if p["skill"] == m["workflow"]), per[0])
        res["plan"] = {"new": "import", "same": "nothing", "update": "update", "merge": "merge", "keep": "import"}[main["plan"]]
        res["skills_plan"] = per
        res["conflicts"] = sum(len(p.get("conflicts", [])) for p in per)
        if main.get("yours_is_newer"):
            res["yours_is_newer"] = True
    out(res)


def _record(skill, m, zip_path, files, extra):
    os.makedirs(SHARED, exist_ok=True)
    rec = {"skill": skill, "workflow": m["workflow"], "kind": m["kind"], "from": os.path.basename(zip_path),
           "zip_path": os.path.abspath(zip_path),
           "their_version": m.get("version", ""), "note": m.get("note", ""), "made": m.get("made", ""),
           "imported": now_iso(), "their_versions": (m.get("versions") or {}).get(skill, [])}
    rec.update(extra)
    with open(os.path.join(SHARED, skill + ".json"), "w", encoding="utf-8") as fh:
        json.dump(rec, fh, indent=1, ensure_ascii=False)
    return rec


def _build():
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "build_workflows.py")], capture_output=True, text=True,
                       env=dict(os.environ, CLAUDE_PROJECT_DIR=paths.PROJECT))
    errs = [ln[6:] for ln in r.stdout.splitlines() if ln.startswith("ERROR ")]
    try:
        subprocess.run([sys.executable, "-I", os.path.join(HERE, "build_board.py")], capture_output=True, timeout=60,
                       env=dict(os.environ, CLAUDE_PROJECT_DIR=paths.PROJECT))
    except subprocess.TimeoutExpired:
        pass
    return errs


def cmd_import(a):
    need_plugin()
    files = read_zip(a.zip)
    m = manifest_of(files)
    if not m:
        fail("not a Delegate share: share.py inspect says what it is")
    if m["kind"] == "issue":
        fail("this is a debugging share: share.py debug brings it in as a debugging copy")
    current = sub(files, "current/")
    if secrets_in(current):
        fail("it has what looks like a password or key in it; ask for a copy without it", at=secrets_in(current))
    main = m["workflow"]
    if local_snapshot(main):
        fail(f"you already have {main}: share.py merge brings the update in and keeps your changes")
    added, kept = [], []
    for sk in m.get("skills") or [main]:
        theirs = only(current, sk)
        if local_snapshot(sk):
            kept.append(sk)   # a shared process or connection you already have stays as yours
            continue
        write_snapshot(theirs, sk)
        save_dir(theirs, os.path.join(SHARED, sk, "base"))
        _record(sk, m, a.zip, files, {"plan": "new", "conflicts": []})
        added.append(sk)
    errs = _build()
    out({"imported": main, "title": m.get("title"), "version": m.get("version"), "added": added, "kept_yours": kept,
         "draft": True, "connections": m.get("connections", []), "build_errors": errs})


def cmd_merge(a):
    need_plugin()
    files = read_zip(a.zip)
    m = manifest_of(files)
    if not m:
        fail("not a Delegate share")
    if m["kind"] == "issue":
        fail("this is a debugging share: share.py debug brings it in as a debugging copy")
    current = sub(files, "current/")
    if secrets_in(current):
        fail("it has what looks like a password or key in it; ask for a copy without it", at=secrets_in(current))
    takes = {}
    for t in a.take or []:
        if "=" not in t or t.split("=", 1)[1] not in ("mine", "theirs"):
            fail(f"--take {t}: write it as c1=mine or c1=theirs")
        cid, side = t.split("=", 1)
        takes[cid] = side
    zip_hash = hashlib.sha256(open(a.zip, "rb").read()).hexdigest()[:16]
    results, saved_first, n_conf = [], [], 0
    for sk in m.get("skills") or [m["workflow"]]:
        theirs = only(current, sk)
        pend = os.path.join(SHARED, sk, "pending")
        state = {}
        try:
            with open(os.path.join(pend, "state.json"), encoding="utf-8") as fh:
                state = json.load(fh)
        except (OSError, ValueError):
            state = {}
        again = state.get("zip") == zip_hash
        mine = only(load_dir(os.path.join(pend, "before")), sk) if again else local_snapshot(sk)
        if not mine:
            write_snapshot(theirs, sk)
            save_dir(theirs, os.path.join(SHARED, sk, "base"))
            _record(sk, m, a.zip, files, {"plan": "new", "conflicts": []})
            results.append({"skill": sk, "plan": "new"})
            continue
        if sk.startswith("connection-") and sk != m["workflow"]:
            results.append({"skill": sk, "plan": "kept yours"})
            continue
        if again:
            base, lab = only(load_dir(os.path.join(pend, "base")), sk), state.get("base")
        else:
            lab, base = find_base(files, sk, mine)
        if digest(mine) == digest(theirs):
            results.append({"skill": sk, "plan": "same"})
            continue
        if not again and is_draft(sk):
            h = _hist()   # your unsaved edits become a version first, so they are never lost
            if h:
                subprocess.run([sys.executable, "-I", os.path.join(HERE, "skill_history.py"), "save", "--via", "outside",
                                "--only", sk, "--quiet", "--message",
                                f"Your changes, kept before the update from {os.path.basename(a.zip)}"],
                               capture_output=True, env=dict(os.environ, CLAUDE_PROJECT_DIR=paths.PROJECT))
                saved_first.append(sk)
        if a.fresh:
            merged, conflicts, summary = theirs, [], {"took_the_update": True}
        else:
            merged, conflicts, summary = merge_snapshots(base, mine, theirs, takes, n_conf)
            n_conf += len(conflicts)
        if not again:
            save_dir(mine, os.path.join(pend, "before"))
            save_dir(base, os.path.join(pend, "base"))
            with open(os.path.join(pend, "state.json"), "w", encoding="utf-8") as fh:
                json.dump({"zip": zip_hash, "base": lab, "t": now_iso()}, fh)
        write_snapshot(merged, sk)
        save_dir(theirs, os.path.join(SHARED, sk, "base"))    # the next update starts from this one
        _record(sk, m, a.zip, files, {"plan": "fresh" if a.fresh else ("update" if digest(base) == digest(mine) else "merge"),
                                      "base": lab, "conflicts": conflicts, "summary": summary})
        results.append({"skill": sk, "plan": "fresh" if a.fresh else "merged", "base": lab,
                        "no_common_version": lab is None, "conflicts": conflicts, "summary": summary})
    errs = _build()
    out({"merged": m["workflow"], "version": m.get("version"), "skills": results, "saved_your_changes_first": saved_first,
         "draft": True, "build_errors": errs})


# ---------------------------------------------------------------- debugging copies

def _slug(m):
    base = re.sub(r"[^a-z0-9-]+", "-", short_name(m["workflow"])).strip("-")[:40] or "workflow"
    stamp = time.strftime("%Y%m%d")
    s, n = f"{base}-{stamp}", 2
    while os.path.exists(os.path.join(DEBUG, s)):
        s, n = f"{base}-{stamp}-{n}", n + 1
    return s


def cmd_debug(a):
    need_plugin()
    files = read_zip(a.zip)
    m = manifest_of(files)
    if not m:
        fail("not a Delegate share")
    if m["kind"] != "issue":
        fail(f"this is a {m['kind']} share, not a debugging one: share.py import or merge brings it in")
    slug = _slug(m)
    root = os.path.join(DEBUG, slug)
    current = sub(files, "current/")
    save_dir(current, os.path.join(root, "current"))
    save_dir(current, os.path.join(root, "base"))     # what the sender had: a fix sent back merges from here
    save_dir(sub(files, "versions/"), os.path.join(root, "versions"))
    save_dir(sub(files, "recordings/"), os.path.join(root, "recordings"))
    wid = "debug-" + slug
    runs = []
    os.makedirs(os.path.join(root, "runs"), exist_ok=True)
    for k, v in sorted(sub(files, "runs/").items()):
        if "/" in k or not k.endswith(".jsonl"):
            continue
        lines = v.decode("utf-8", "replace").splitlines()
        outl = []
        for ln in lines:
            try:
                o = json.loads(ln)
            except ValueError:
                continue
            if isinstance(o, dict) and o.get("header"):
                o["flow"], o["debug"], o["debug_slug"] = wid, True, slug
                o["watch"] = False
            outl.append(json.dumps(o, ensure_ascii=False))
        with open(os.path.join(root, "runs", k), "w", encoding="utf-8") as fh:
            fh.write("\n".join(outl) + "\n")
    m2 = dict(m, slug=slug, imported=now_iso(), from_zip=os.path.basename(a.zip), board_workflow=wid)
    with open(os.path.join(root, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(m2, fh, indent=1, ensure_ascii=False)
    for r in m.get("runs") or []:
        runs.append({"run": r.get("run"), "label": r.get("label"), "summary": r.get("summary", "")})
    errs = _build()
    out({"debug": slug, "page": wid, "workflow": m["workflow"], "title": m.get("title"), "version": m.get("version"),
         "note": m.get("note", ""), "runs": runs, "folder": root,
         "edit_here": os.path.join(root, "current"), "build_errors": errs})


def debug_copies():
    outl = []
    if not DEBUG or not os.path.isdir(DEBUG):
        return outl
    for s in sorted(os.listdir(DEBUG)):
        p = os.path.join(DEBUG, s, "manifest.json")
        try:
            with open(p, encoding="utf-8") as fh:
                m = json.load(fh)
        except (OSError, ValueError):
            continue
        root = os.path.join(DEBUG, s)
        cur = load_dir(os.path.join(root, "current"))
        base = load_dir(os.path.join(root, "base"))
        m["changed"] = sorted(k for k in set(cur) | set(base) if cur.get(k) != base.get(k))
        m["root"] = root
        outl.append(m)
    return outl


def cmd_debugs(_a):
    need_plugin()
    out({"debugging": [{"slug": m["slug"], "workflow": m["workflow"], "title": m.get("title"), "page": m.get("board_workflow"),
                        "runs": len(m.get("runs") or []), "changed": m["changed"]} for m in debug_copies()]})


def cmd_remove_debug(a):
    need_plugin()
    root = os.path.join(DEBUG, a.slug)
    if not os.path.isfile(os.path.join(root, "manifest.json")):
        fail(f"no debugging copy {a.slug}")
    shutil.rmtree(root)
    errs = _build()
    out({"removed": a.slug, "build_errors": errs})


# ---------------------------------------------------------------- what an update changes, for the Share tab

def _steps(snap, skill):
    w = board_workflow(snap, skill)
    return {s.get("key"): s for s in w.get("steps") or [] if isinstance(s, dict) and s.get("key")}


STEP_HEAD = re.compile(r"^\*\*Step \d+:\s*(.+?)\.?\*\*\s*$|^#{2,4}\s+Step \d+:\s*(.+?)\.?\s*$", re.M)


def _md_steps(snap, skill):
    """{step title (lower case): its text} from the skill's "**Step N: Title.**" sections."""
    md = snap.get(f"skills/{skill}/SKILL.md", b"").decode("utf-8", "replace")
    heads = list(STEP_HEAD.finditer(md))
    res = {}
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(md)
        nxt = re.search(r"^#{1,2} ", md[h.end():end], re.M)   # a section after the last step ends it
        body = md[h.end(): h.end() + nxt.start()] if nxt else md[h.end():end]
        res[(h.group(1) or h.group(2)).strip().lower()] = body.strip()
    return res


def step_changes(old, new, skill):
    """[{k: new|changed|removed, t: title}] between two snapshots: the board's steps, and each step's own text."""
    a, b = _steps(old, skill), _steps(new, skill)
    ma, mb = _md_steps(old, skill), _md_steps(new, skill)
    res = []
    for k, s in b.items():
        t = (s.get("title") or k).lower()
        if k not in a:
            res.append({"k": "new", "t": s.get("title") or k})
        elif (json.dumps(s, sort_keys=True) != json.dumps(a[k], sort_keys=True)
              or ma.get((a[k].get("title") or k).lower()) != mb.get(t)):
            res.append({"k": "changed", "t": s.get("title") or k})
    for k, s in a.items():
        if k not in b:
            res.append({"k": "removed", "t": s.get("title") or k})
    return res


def share_info(skill):
    """For the board: the published version, what was last shared, and what changed since then."""
    vs = version_list(skill)
    log = [e for e in share_log(skill) if e.get("kind") in ("full", "update")]
    last = log[-1] if log else None
    info = {"version": vs[-1]["v"] if vs else "", "last": last and {k: last.get(k) for k in ("kind", "version", "t")}}
    if vs:
        latest = vs[-1]["v"]
        # compared with the newest version shared before this one; never shared: the version before it
        earlier = next((e.get("version") for e in reversed(log) if e.get("version") != latest), None)
        since = next((v for v in vs if v["v"] == earlier), None) or (vs[-2] if len(vs) > 1 else None)
        info["update_since"] = since["v"] if since else ""
        info["is_new"] = bool(last and last.get("version") != latest)
        if since and since["v"] != vs[-1]["v"]:
            info["changes"] = step_changes(snapshot_at(since["commit"], skill), snapshot_at(vs[-1]["commit"], skill), skill)
    return info


def cmd_impact(a):
    need_plugin()
    out(dict(share_info(a.skill), skill=a.skill))


def cmd_runs(a):
    need_plugin()
    snap = local_snapshot(a.skill)
    rs = runs_of(a.skill, board_workflow(snap, a.skill).get("id"))[: a.max]
    out({"skill": a.skill, "runs": [{k: r[k] for k in ("run", "label", "started", "status", "attention", "summary", "try", "test")}
                                    for r in rs]})


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    s = p.add_subparsers(dest="cmd", required=True)
    mk = s.add_parser("make")
    mk.add_argument("skill", nargs="?")
    mk.add_argument("--kind", choices=("full", "update", "issue"))
    mk.add_argument("--runs", nargs="*")
    mk.add_argument("--note")
    mk.add_argument("--out")
    mk.add_argument("--debug")
    mk.set_defaults(fn=cmd_make)
    r = s.add_parser("runs")
    r.add_argument("skill")
    r.add_argument("--max", type=int, default=20)
    r.set_defaults(fn=cmd_runs)
    for name, fn in (("inspect", cmd_inspect), ("import", cmd_import), ("debug", cmd_debug)):
        x = s.add_parser(name)
        x.add_argument("zip")
        x.set_defaults(fn=fn)
    mg = s.add_parser("merge")
    mg.add_argument("zip")
    mg.add_argument("--fresh", action="store_true")
    mg.add_argument("--take", nargs="*")
    mg.set_defaults(fn=cmd_merge)
    d = s.add_parser("debugs")
    d.set_defaults(fn=cmd_debugs)
    rd = s.add_parser("remove-debug")
    rd.add_argument("slug")
    rd.set_defaults(fn=cmd_remove_debug)
    im = s.add_parser("impact")
    im.add_argument("skill")
    im.set_defaults(fn=cmd_impact)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
