#!/usr/bin/env python3
"""Skill history: a hidden git history of the skills and their board definitions, kept in the data folder.

It is separate from the project's own git (its own --git-dir, never the project's .git) and tracks only:
  in-project   .claude/skills/  and  .claude/workflow-ui/workflows.json
  plugin       .claude/skills/ (the user's own skills)  and  .workflow-manager-data/config/board/
It lives in .claude/workflow-ui/dispatcher-data/skill-history/ in-project, or
.workflow-manager-data/history/skill-history/ where the plugin is installed.

A version is one finished change: the architect saves one at the end of a change the user asked for (or when
the user says "save a version"), after an impact review of the change against earlier runs. Edits in between are
a draft: nothing saves them on its own, and a run on a draft is stamped "vN+draft" (current()).

    skill_history.py save [--via architect|outside|restore|start] [--message M] [--note SKILL=TEXT ...] [--only SKILL ...]
                          [--review FILE] [--quiet]
        save every change since the last save as one version per changed skill; --review is the impact review
        ({skill: review}, JSON) stored with it; "nothing to save" when there is none
    skill_history.py start [--quiet]    start the history from the skills as they are, if it hasn't started (the prompt
                                        hook runs it before every request; does nothing once started)
    skill_history.py status             skills with a draft (changed since their last version)
    skill_history.py versions [SKILL]   every skill's versions (or one skill's), newest last, as JSON
    skill_history.py current SKILL      the version a run uses now: "vN", or "vN+draft" when it has unsaved edits
    skill_history.py diff SKILL         what changed since its last version: its files and its board definition
    skill_history.py runs SKILL [--max N]  earlier runs to review a change against: the latest test per case,
                                        every unusual run, then recent ordinary ones with different outcomes
    skill_history.py restore SKILL vN   put back that version's folder and board definition, saved as a new version
    skill_history.py updating SKILL "what"   Claude has started changing the draft (the Builder pulses until the next checkpoint)
    skill_history.py checkpoint SKILL --note "what changed"   after one change: the draft's next iteration
    skill_history.py iterations SKILL   the draft's iterations since its last version
    skill_history.py undo SKILL         put back the iteration before the last one (files and board definition)

Publishing a draft (core-architect, Publish):
    skill_history.py prepare SKILL [--max N]
        one call for the heavy part: builds the board (its ERROR / WARN lines), the diff since the last version, the
        draft's changes in plain words, and the earlier runs to check it against
    skill_history.py pending SKILL --review FILE [--confirm]
        keep the impact review ({skill: review}) with the draft, so the draft's History entry on the board shows it
        before anything is saved; --confirm marks the user's yes. It goes stale when the draft is edited again
    skill_history.py pending SKILL       show the draft's pending review (and whether it is still current)
    save picks up a current pending review on its own when --review isn't given, and drops it once saved.
"""
import argparse
import difflib
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402

PROJECT = paths.PROJECT
if paths.PLUGIN:
    GIT_DIR = os.path.join(paths.HISTORY, "skill-history")
    SKILLS_REL = os.path.relpath(paths.USER_SKILLS, PROJECT)
    BOARD_REL = os.path.relpath(paths.BOARD_DEFS, PROJECT)       # a folder: board/<skill>.json
else:
    GIT_DIR = os.path.join(paths.CODE, "dispatcher-data", "skill-history")
    SKILLS_REL = os.path.relpath(paths.SKILLS, PROJECT)
    BOARD_REL = os.path.relpath(os.path.join(paths.CODE, "workflows.json"), PROJECT)   # one file for every skill
PENDING_DIR = os.path.join(os.path.dirname(GIT_DIR), "pending-reviews")   # a draft's review, before it is saved
TRACKED = [SKILLS_REL, BOARD_REL, os.path.relpath(paths.TESTS, PROJECT)]   # skills, board, fake sources
VIA = {"architect": "via the architect", "outside": "edited outside the architect",
       "restore": "restored", "start": "history started", "renamer": "renamed"}


def git(*args, check=True, text=True):
    env = dict(os.environ, GIT_DIR=GIT_DIR, GIT_WORK_TREE=PROJECT, GIT_TERMINAL_PROMPT="0")
    r = subprocess.run(["git", *args], cwd=PROJECT, env=env, capture_output=True, text=text)
    if check and r.returncode != 0:
        raise SystemExit(json.dumps({"error": f"git {args[0]}: {(r.stderr or '').strip()[:300]}"}))
    return r.stdout


def ready():
    return os.path.isfile(os.path.join(GIT_DIR, "HEAD"))


def init():
    if ready():
        return
    os.makedirs(GIT_DIR, exist_ok=True)
    subprocess.run(["git", "init", "-q", "--bare", GIT_DIR], check=True, capture_output=True)
    git("config", "core.bare", "false")
    git("config", "user.name", "workflow-manager")
    git("config", "user.email", "skill-history@workflow-manager.local")
    git("config", "commit.gpgsign", "false")
    with open(os.path.join(GIT_DIR, "info", "exclude"), "a", encoding="utf-8") as fh:
        fh.write("__pycache__/\n*.pyc\n.DS_Store\nnode_modules/\n")


def has_head():
    return git("rev-parse", "-q", "--verify", "HEAD", check=False).strip() != ""


def stage():
    present = [p for p in TRACKED if os.path.exists(os.path.join(PROJECT, p))]
    if present:
        git("add", "-A", "--", *present)
    # a tracked path that was deleted entirely
    gone = [p for p in TRACKED if p not in present]
    if gone and has_head():
        git("rm", "-r", "-q", "--cached", "--ignore-unmatch", "--", *gone)


def changed_paths():
    stage()
    if not has_head():
        return git("ls-files").splitlines()
    return git("diff", "--cached", "--name-only", "HEAD").splitlines()


def skill_of(path):
    """The skill a tracked file belongs to (None for the shared workflows.json)."""
    if path.startswith(SKILLS_REL + "/"):
        return path[len(SKILLS_REL) + 1:].split("/")[0]
    if paths.PLUGIN and path.startswith(BOARD_REL + "/") and path.endswith(".json"):
        return os.path.basename(path)[:-5]
    return None


def _board_partial(only):
    """The shared workflows.json (org layer) as it was at the last version, with only these skills' parts taken from
    the working folder: their workflows, triggers, skill keys (and aliases to them), examples, results and summaries,
    and any category they use. Every other skill's board edits stay a draft."""
    raw = git("show", f"HEAD:{BOARD_REL}", check=False)
    head = json.loads(raw) if raw else {}
    with open(os.path.join(PROJECT, BOARD_REL), encoding="utf-8") as fh:
        cur = json.load(fh)
    out = dict(head)
    hw = {w.get("id"): w for w in head.get("workflows", [])}
    cw = {w.get("id"): w for w in cur.get("workflows", [])}
    mine = lambda w: board_skill(w) in only
    wfs, mine_ids = [], set()
    for w in head.get("workflows", []):   # the last version's order; these skills' workflows replaced in place
        i, c = w.get("id"), cw.get(w.get("id"))
        if mine(w) or (c and mine(c)):
            mine_ids.add(i)
            if c:
                wfs.append(c)
        else:
            wfs.append(w)
    for w in cur.get("workflows", []):    # these skills' new workflows go at the end
        if w.get("id") not in hw and mine(w):
            mine_ids.add(w.get("id"))
            wfs.append(w)
    out["workflows"] = wfs
    he, ce = head.get("entries") or {}, cur.get("entries") or {}
    ents, mine_ent = {}, set()
    for k in list(ce) + [k for k in he if k not in ce]:
        sk = (ce.get(k) or he.get(k) or {}).get("skill") or _entry_skill(k)
        if sk in only:
            mine_ent.add(k)
            if k in ce:
                ents[k] = ce[k]
        elif k in he:
            ents[k] = he[k]
    out["entries"] = ents
    hs, cs = head.get("skills") or {}, cur.get("skills") or {}
    sks = {}
    for k in list(cs) + [k for k in hs if k not in cs]:
        v = cs.get(k) if k in cs else hs.get(k)
        if k in only or (isinstance(v, dict) and v.get("alias_of") in only):
            if k in cs:
                sks[k] = cs[k]
        elif k in hs:
            sks[k] = hs[k]
    out["skills"] = sks
    keys = {f"workflow:{i}" for i in mine_ids} | {f"trigger:{k}" for k in mine_ent}
    for sec in ("summaries", "examples", "results"):
        if sec in cur or sec in head:
            d = {k: v for k, v in (head.get(sec) or {}).items() if k not in keys}
            d.update({k: v for k, v in (cur.get(sec) or {}).items() if k in keys})
            out[sec] = d
    cats = dict(head.get("categories") or {})
    for w in wfs:
        if w.get("id") in mine_ids and w.get("category") in (cur.get("categories") or {}):
            cats.setdefault(w["category"], cur["categories"][w["category"]])
    if cats:
        out["categories"] = cats
    return json.dumps(out, indent=2, ensure_ascii=False) + "\n"


def _entry_skill(trigger_id):
    """A trigger's skill from its Definition id, for a board entry that doesn't name it."""
    try:
        import entries
        return next((e["skill"] for e in entries.load() if e.get("id") == trigger_id), None)
    except Exception:
        return None


def _stage_only(only):
    """Put back the index to the last version, then stage only these skills: their folders and their board part."""
    git("reset", "-q", "HEAD", "--", *[p for p in TRACKED if os.path.exists(os.path.join(PROJECT, p))] or ["."], check=False)
    for sk in only:
        rel = f"{SKILLS_REL}/{sk}"
        if os.path.exists(os.path.join(PROJECT, rel)):
            git("add", "-A", "--", rel)
        else:
            git("rm", "-r", "-q", "--cached", "--ignore-unmatch", "--", rel)
        if paths.PLUGIN:
            b = f"{BOARD_REL}/{sk}.json"
            if os.path.exists(os.path.join(PROJECT, b)):
                git("add", "--", b)
            else:
                git("rm", "-q", "--cached", "--ignore-unmatch", "--", b)
    if not paths.PLUGIN and os.path.exists(os.path.join(PROJECT, BOARD_REL)):
        env = dict(os.environ, GIT_DIR=GIT_DIR, GIT_WORK_TREE=PROJECT, GIT_TERMINAL_PROMPT="0")
        r = subprocess.run(["git", "hash-object", "-w", "--stdin"], input=_board_partial(set(only)), cwd=PROJECT,
                           env=env, capture_output=True, text=True, check=True)
        git("update-index", "--add", "--cacheinfo", f"100644,{r.stdout.strip()},{BOARD_REL}")
    return git("diff", "--cached", "--name-only", "HEAD").splitlines()


def save(via="outside", message="", notes=None, quiet=False, review=None, only=None):
    """One version. With `only` (skill names): just those skills are saved, and every other draft stays a draft;
    a publish and a restore always pass it. Without: every change is saved (the history's start and its
    automatic saves)."""
    init()
    files = changed_paths()
    # read each pending review first: checking that one is current re-stages the working folder (fingerprint), which
    # would undo _stage_only below and save every other draft along with these skills
    pre = {}
    if review is None:
        for sk in (list(only) if only else sorted({s for s in map(skill_of, files) if s})):
            pr = pending(sk)
            if pr and pr.get("current"):
                pre[sk] = pr["review"]
    if only and has_head():
        files = _stage_only(list(only))
    held = sorted({s for s in map(skill_of, files) if s and unnamed(s)})
    files = [f for f in files if not unnamed(skill_of(f) or "")]   # a new workflow is named before it is published
    if not files:
        return {"saved": False, "why": "name it first: " + ", ".join(held) + " is still in the category new"
                if held else "nothing to save"}
    skills = sorted({s for s in map(skill_of, files) if s})
    if review is None:
        review = {sk: pre[sk] for sk in skills if sk in pre} or None
    if not message:
        if via == "start":
            message = "History started"
        else:
            what = ", ".join(skills) if skills else "the board definitions"
            message = ("Saved automatically: " if via == "outside" else "Changed ") + what
    body = [f"Via: {via}"]
    if notes:
        body.append("Notes: " + json.dumps(notes, ensure_ascii=False))
    if review:
        body.append("Review: " + json.dumps(review, ensure_ascii=False))
    git("commit", "-q", "--no-verify", "-m", message, "-m", "\n".join(body))
    out = {"saved": True, "commit": git("rev-parse", "--short", "HEAD").strip(), "skills": skills, "message": message}
    for sk in skills:   # saved: its pending review, and its iterations, now live in the version
        for f in (os.path.join(PENDING_DIR, sk + ".json"), _iter_path(sk)):
            try:
                os.remove(f)
            except OSError:
                pass
    return out


def status():
    init()
    files = changed_paths()
    # recordings and test cases describe a skill, they never change what it does (core-architect rules 28, 29): a
    # real run saving one must not turn a published workflow back into a draft. They are saved with its next version.
    edits = [f for f in files if "/tests/" not in f and not _board_same(f)]
    return {"changed": sorted({s for s in map(skill_of, edits) if s}), "files": files}


def _board_same(path):
    """A board file whose only edits are its page lines, colours or format stamp (what _plain leaves out): like
    examples, those never make a draft."""
    if not (paths.PLUGIN and path.startswith(BOARD_REL + "/") and path.endswith(".json")):
        return False
    try:
        with open(os.path.join(PROJECT, path), encoding="utf-8") as fh:
            now = _plain(json.load(fh))
        raw = git("show", f"HEAD:{path}", check=False)
        return bool(raw) and json.dumps(now, sort_keys=True) == json.dumps(_plain(json.loads(raw)), sort_keys=True)
    except (OSError, ValueError):
        return False


# ---------- versions ----------
def commits():
    if not ready() or not has_head():
        return []
    raw = git("log", "--reverse", "--format=%H%x1f%ct%x1f%s%x1f%b%x1e")
    out = []
    for rec in raw.split("\x1e"):
        rec = rec.strip("\n")
        if not rec:
            continue
        h, t, subj, body = (rec.split("\x1f") + ["", "", "", ""])[:4]
        via, notes, review = "outside", {}, {}
        for line in body.splitlines():
            if line.startswith("Via: "):
                via = line[5:].strip()
            elif line.startswith("Notes: ") or line.startswith("Review: "):
                try:
                    val = json.loads(line.split(": ", 1)[1])
                except ValueError:
                    continue
                if line.startswith("Notes: "):
                    notes = val
                else:
                    review = val
        out.append({"commit": h, "t": int(t), "subject": subj, "via": via, "notes": notes, "review": review})
    return out


def tree_of(commit, rel):
    return git("rev-parse", "-q", "--verify", f"{commit}:{rel}", check=False).strip() or None


WORDS = ("tip", "makes")   # rule 23: a line's hover sentence and a stage's outcome describe the skill, never change it
PAGE_ONLY = ("summaries", "examples", "results", "skills", "categories", "format", "data_version")   # page lines, colours, labels


def _plain(entry):
    """A board definition without its tips and stage outcomes: like examples, writing them never makes a draft, so
    every comparison (draft or not, what changed, the impact review) leaves them out."""
    if not isinstance(entry, dict):
        return entry
    e = json.loads(json.dumps(entry))
    for k in PAGE_ONLY:   # a board file's page lines (rule 29, 31) and its format stamp: never a draft either
        e.pop(k, None)
    for w in e.get("workflows") or ([e] if "steps" in e else []):
        for x in (w.get("steps") or []) + (w.get("stages") or []):
            for k in WORDS:
                x.pop(k, None)
    return e


def board_entries(commit):
    """{skill: its board definition} at a commit."""
    out = {}
    if paths.PLUGIN:
        for name in git("ls-tree", "--name-only", f"{commit}:{BOARD_REL}", check=False).split():
            if name.endswith(".json"):
                try:
                    out[name[:-5]] = _plain(json.loads(git("show", f"{commit}:{BOARD_REL}/{name}")))
                except ValueError:
                    pass
        return out
    raw = git("show", f"{commit}:{BOARD_REL}", check=False)
    try:
        defs = json.loads(raw) if raw else {}
    except ValueError:
        return out
    for w in defs.get("workflows", []):
        sk = board_skill(w)
        if sk:
            out.setdefault(sk, {"workflows": []})["workflows"].append(w)
    return {k: _plain(v) for k, v in out.items()}


def board_skill(w):
    """The skill a board workflow draws: its match skill, else the skill doing its first step (the architect's modes)."""
    sk = (w.get("match") or {}).get("skill")
    if sk:
        return sk
    return next((st.get("sk") for st in w.get("steps", []) if (st.get("sk") or "").startswith(("workflow-", "shared-", "core-", "trigger-"))), None)


def _wfs(entry):
    """{workflow id: workflow} inside a board definition (one or more workflows for a skill)."""
    if isinstance(entry, dict) and "workflows" in entry:
        return {w.get("id", str(i)): w for i, w in enumerate(entry.get("workflows") or [])}
    return {"": entry} if entry else {}


def board_changes(old, new):
    """What changed on the board, in plain words, for every workflow the skill draws."""
    return [x["t"] for x in board_change_items(old, new)]


def board_change_items(old, new):
    """board_changes with the steps each line is about: [{"t": line, "keys": [step key, ...]}]."""
    o, n = _wfs(old), _wfs(new)
    out = []
    for k in list(n) + [k for k in o if k not in n]:
        items = wf_change_items(o.get(k), n.get(k))
        if len(n) > 1 and items:
            label = (n.get(k) or o.get(k) or {}).get("short") or k
            items = [dict(x, t=f"{x['t']} ({label})") for x in items]
        out += items
    return out


def sk_words(sk):
    """A skill a step uses, in plain words: a connection by its system's name, anything else by its name."""
    if not sk:
        return "no skill"
    if sk.startswith("connection-"):
        return f"the {sk[len('connection-'):].replace('-', ' ').title()} connection"
    m = re.match(r"^(shared|workflow|trigger)-[a-z0-9]+-(.+)$", sk)
    if m:
        what = m.group(2).replace("-", " ")
        return {"shared": f"the shared {what.title()} process", "workflow": f"the {what} workflow",
                "trigger": f"the {what} trigger"}[m.group(1)]
    return sk


def wf_changes(o, n):
    """What changed in one board workflow, in plain words."""
    return [x["t"] for x in wf_change_items(o, n)]


def wf_change_items(o, n):
    """wf_changes with the steps each line is about."""
    o, n = o or {}, n or {}
    if not o and n:
        return [{"t": "Added to the board", "keys": []}]
    if o and not n:
        return [{"t": "Removed from the board", "keys": []}]
    lines, keys = [], []
    add = lambda t, ks=(): (lines.append(t), keys.append(list(ks)))
    os_, ns = {s["key"]: s for s in o.get("steps", [])}, {s["key"]: s for s in n.get("steps", [])}
    name = lambda s: s.get("title") or s.get("what") or s["key"]
    for k in ns:
        if k not in os_:
            add(f'+ Added step "{name(ns[k])}"', [k])
    for k in os_:
        if k not in ns:
            add(f'- Removed step "{name(os_[k])}"')
    moved = {}
    for k in ns:
        if k in os_:
            a, b = os_[k], ns[k]
            if name(a) != name(b):
                add(f'~ Renamed step "{name(a)}" to "{name(b)}"', [k])
            if [(x.get("when"), x.get("then")) for x in a.get("alts", [])] != [(x.get("when"), x.get("then")) for x in b.get("alts", [])]:
                add(f'~ Changed the options of "{name(b)}"', [k])
            elif a.get("what") != b.get("what") or (a.get("why") or {}).get("sum") != (b.get("why") or {}).get("sum"):
                add(f'~ Reworded "{name(b)}"', [k])
            if (a.get("sk") or "") != (b.get("sk") or ""):
                moved.setdefault((a.get("sk") or "", b.get("sk") or ""), []).append(k)
    for (was, now), ks in moved.items():
        who = f'"{name(ns[ks[0]])}" now uses' if len(ks) == 1 else f"{len(ks)} steps now use"
        add(f"~ {who} {sk_words(now)} instead of {sk_words(was)}", ks)
    op, np_ = [p.get("label") for p in o.get("simulated", [])], [p.get("label") for p in n.get("simulated", [])]
    for l in np_:
        if l not in op:
            add(f'+ Added example "{l}"')
    for l in op:
        if l not in np_:
            add(f'- Removed example "{l}"')
    if [s.get("title") for s in o.get("stages", [])] != [s.get("title") for s in n.get("stages", [])]:
        add("~ Regrouped the stages")
    if o.get("desc") != n.get("desc"):
        add("~ Changed the description")
    return [{"t": t, "keys": k} for t, k in zip(lines, keys)]


# ---------- iterations: every change to a draft is a numbered checkpoint between versions ----------
# <data>/iterations/<skill>.json = {"items": [{"n", "t", "note", "board": {wf id: workflow}, "files": {path: text}}],
#                                  "updating": {"what", "t"}}   ("updating" only while Claude is changing it)
# A checkpoint keeps the skill's own files and its board definition after one change, so the Builder can mark what
# that change did and Undo can put the one before back. Publishing (save) clears them: the version holds the result.
ITER_DIR = os.path.join(os.path.dirname(GIT_DIR), "iterations")


def unnamed(skill):
    """A new workflow or trigger not named yet (core-architect Create mode): its category is the reserved `new`."""
    return bool(re.match(r"^(workflow|trigger|shared)-new-", skill or ""))


def rename(old, new):
    """Name a new skill (core-architect Create mode, Name): move its folder, its frontmatter `name:` and its iteration
    log to the new name. Everything else that names it (other skills, tests, the board) is the architect's edit."""
    root = os.path.join(PROJECT, SKILLS_REL)
    src, dst = os.path.join(root, old), os.path.join(root, new)
    if not os.path.isdir(src):
        return {"renamed": False, "why": f"no skill folder {old}"}
    if os.path.exists(dst):
        return {"renamed": False, "why": f"{new} already exists"}
    if not re.match(r"^(workflow|trigger|shared)-[a-z0-9]+-[a-z0-9-]+$", new) or len(new) > 64:
        return {"renamed": False, "why": f"{new} doesn't follow <kind>-<category>-<description> (rule 10)"}
    os.rename(src, dst)
    md = os.path.join(dst, "SKILL.md")
    if os.path.isfile(md):
        with open(md, encoding="utf-8") as fh:
            text = fh.read()
        with open(md, "w", encoding="utf-8") as fh:
            fh.write(re.sub(r"(?m)^name:\s*" + re.escape(old) + r"\s*$", "name: " + new, text, count=1))
    moved = False
    if os.path.isfile(_iter_path(old)):
        with open(_iter_path(old), encoding="utf-8") as fh:
            text = fh.read()
        with open(_iter_path(new), "w", encoding="utf-8") as fh:
            fh.write(text.replace(old, new))
        os.remove(_iter_path(old))
        moved = True
    return {"renamed": True, "from": old, "to": new, "iterations": moved}


def _iter_path(skill):
    return os.path.join(ITER_DIR, skill + ".json")


def iter_log(skill):
    try:
        with open(_iter_path(skill), encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {"items": []}


def _iter_write(skill, log):
    os.makedirs(ITER_DIR, exist_ok=True)
    with open(_iter_path(skill), "w", encoding="utf-8") as fh:
        json.dump(log, fh, ensure_ascii=False, indent=1)


def _skill_files(skill):
    root = os.path.join(PROJECT, SKILLS_REL, skill)
    out = {}
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x != "__pycache__" and not x.startswith(".")]
        for f in files:
            p = os.path.join(d, f)
            try:
                with open(p, encoding="utf-8") as fh:
                    out[os.path.relpath(p, root)] = fh.read()
            except (OSError, UnicodeDecodeError):
                pass
    return out


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _build_soon():
    """Rebuild the Workflow Viewer's data in the background (about 3 seconds), so the page, which polls every few
    seconds, shows the change within moments while the caller carries straight on."""
    try:
        subprocess.Popen([sys.executable, "-I", os.path.join(HERE, "build_workflows.py")], cwd=PROJECT,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        pass


PAGE_LINES = ("summaries", "examples", "results")   # keyed "workflow:<id>" / "trigger:<entry key>" (board_store)


def _page_keys(wfs):
    return {"workflow:" + w.get("id", "") for w in wfs} | {"trigger:" + e for w in wfs for e in (w.get("entries") or [])}


def _page(skill):
    """The skill's page lines (its summaries, examples and results) and its README row: kept with each iteration, so
    Undo puts them back with the steps they describe (they never make a draft, so the plain board leaves them out)."""
    keys = _page_keys(_raw_board(skill))
    try:
        if paths.PLUGIN:
            with open(os.path.join(PROJECT, BOARD_REL, skill + ".json"), encoding="utf-8") as fh:
                whole = json.load(fh)
        else:
            with open(os.path.join(PROJECT, BOARD_REL), encoding="utf-8") as fh:
                whole = json.load(fh)
    except (OSError, ValueError):
        whole = {}
    out = {k: {x: v for x, v in (whole.get(k) or {}).items() if x in keys} for k in PAGE_LINES}
    try:
        with open(os.path.join(PROJECT, "README.md"), encoding="utf-8") as fh:
            row = next((ln for ln in fh.read().splitlines() if ln.startswith(f"| `{skill}` |")), None)
    except OSError:
        row = None
    if row:
        out["readme_row"] = row
    return out


def _put_page(defs, page, keys):
    """Put an iteration's page lines back into a board definition: this skill's keys only, the rest left as they are."""
    for k in PAGE_LINES:
        cur = {x: v for x, v in (defs.get(k) or {}).items() if x not in keys}
        cur.update((page.get(k) or {}))
        if cur or k in defs:
            defs[k] = cur


def _put_readme_row(skill, row):
    p = os.path.join(PROJECT, "README.md")
    if not row or not os.path.exists(p):
        return
    with open(p, encoding="utf-8") as fh:
        text = fh.read()
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        if ln.startswith(f"| `{skill}` |"):
            lines[i] = row
    new = "\n".join(lines)
    if new != text:
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(new)


def _raw_board(skill):
    """The skill's board workflows as written, tips and stage outcomes included (board_entries_now leaves them out)."""
    try:
        if paths.PLUGIN:
            with open(os.path.join(PROJECT, BOARD_REL, skill + ".json"), encoding="utf-8") as fh:
                return json.load(fh).get("workflows") or []
        with open(os.path.join(PROJECT, BOARD_REL), encoding="utf-8") as fh:
            return [w for w in json.load(fh).get("workflows", []) if board_skill(w) == skill]
    except (OSError, ValueError):
        return []


def _words(wfs):
    """{workflow id: {step or stage key: {tip, makes}}}: the words a snapshot's plain board leaves out."""
    out = {}
    for w in wfs:
        for x in (w.get("steps") or []) + (w.get("stages") or []):
            got = {k: x[k] for k in WORDS if k in x}
            if got:
                got["_order"] = list(x)   # where they sat among its fields, so Undo puts them back in place
            if got and x.get("key"):
                out.setdefault(w.get("id", ""), {})[x["key"]] = got
    return out


def _with_words(wfs, *maps):
    """The workflows with each step's and stage's words put back, from the first map that has them."""
    wfs = json.loads(json.dumps(wfs))
    for w in wfs:
        for x in (w.get("steps") or []) + (w.get("stages") or []):
            for m in maps:
                got = (m.get(w.get("id", "")) or {}).get(x.get("key"))
                if got:
                    order = got.get("_order") or []
                    add = {k: v for k, v in got.items() if k != "_order" and k not in x}
                    at = next((a for a in ("what", "title") if a in x), None)   # no order kept: after `what`
                    if add and at:
                        items = list(x.items())
                        i = [k for k, _ in items].index(at) + 1
                        x.clear()
                        x.update(items[:i] + list(add.items()) + items[i:])
                    else:
                        x.update(add)
                    if order:   # back to the order it was written in; fields it didn't have then stay at the end
                        items = dict(x)
                        x.clear()
                        x.update({k: items[k] for k in order if k in items})
                        x.update({k: v for k, v in items.items() if k not in x})
                    break
    return wfs


SNAPSHOT_NOTE = "as it was before this change"   # the iteration a change starts from, kept by updating()


def updating(skill, what, build=True):
    """Claude has started changing the draft: the Builder shows it, pulsing, until the next checkpoint. The board is
    rebuilt at once (in the background), so the page turns to the draft within seconds, not at the checkpoint.
    A change starting on files that differ from the last iteration (edited without a checkpoint) first keeps them as
    an iteration of their own, so Undo after this change goes back to how they were, not to an older iteration."""
    log = iter_log(skill)
    if not log.get("updating") and os.path.isdir(os.path.join(PROJECT, SKILLS_REL, skill)):
        board, files = _wfs(board_entries_now().get(skill)), _skill_files(skill)
        items = log.setdefault("items", [])
        prev = items[-1] if items else {}
        same = prev.get("board") == board and prev.get("files") == files
        if files and same and "page" not in prev:   # an iteration from before page lines were kept: fill them in
            prev["words"], prev["page"] = _words(_raw_board(skill)), _page(skill)
        elif files and not same:
            items.append({"n": prev.get("n", 0) + 1, "t": _now(), "note": SNAPSHOT_NOTE,
                          "board": board, "files": files, "words": _words(_raw_board(skill)), "page": _page(skill),
                          "summary": prev.get("summary", ""), "details": prev.get("details", [])})
    log["updating"] = {"what": what, "t": _now()}
    _iter_write(skill, log)
    if build:
        _build_soon()
    return {"skill": skill, "updating": what}


def auto_updating(path, what=""):
    """The hooks call this before Claude edits a file: an edit inside an existing skill's folder marks that skill as
    being updated straight away (once per change: nothing if it is already marked). Returns the skill, or None."""
    try:
        rel = os.path.relpath(os.path.abspath(path), PROJECT)
    except ValueError:
        return None
    sk = skill_of(rel)
    if not sk or not os.path.isdir(os.path.join(PROJECT, SKILLS_REL, sk)) or iter_log(sk).get("updating"):
        return None
    updating(sk, what or "Editing " + os.path.basename(path))
    return sk


def settle_updating():
    """End of Claude's turn: no skill is still being changed. Drops every "updating" mark a checkpoint didn't (an
    edit made without one stays a draft, shown by its files, but stops pulsing). Returns the skills settled."""
    out = []
    if os.path.isdir(ITER_DIR):
        for n in sorted(os.listdir(ITER_DIR)):
            if n.endswith(".json"):
                log = iter_log(n[:-5])
                if log.pop("updating", None):
                    _iter_write(n[:-5], log)
                    out.append(n[:-5])
    return out


DETAIL_KINDS = ("changed", "new", "gone")


def read_details(path):
    """A --details file: [{"kind": "changed"|"new"|"gone", "s": a short headline, "t": what, "why": the reason,
    "keys": [step key, ...]}].
    "gone" is what the draft will no longer do: the list the user approves when publishing."""
    if not path:
        return None
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    out = []
    for x in data if isinstance(data, list) else []:
        if isinstance(x, dict) and x.get("t") and x.get("kind") in DETAIL_KINDS:
            d = {"kind": x["kind"], "t": str(x["t"]), "why": str(x.get("why") or ""),
                 "keys": [str(k) for k in (x.get("keys") or [])]}
            if x.get("s"):   # the short headline the approval cards show; "t" and "why" open under it
                d["s"] = str(x["s"])
            out.append(d)
    return out


def checkpoint(skill, note="", summary="", details=None):
    """After one change: keep the skill's files and board definition as the next iteration (none if nothing changed).
    summary: one line on how the whole draft differs from the published version (rewritten every change, so the bar
    always says it in one line); details: its reasoned list (read_details). Both are kept with the iteration, so
    Undo brings back the ones before. A change that gives none keeps the last ones."""
    log = iter_log(skill)
    log.pop("updating", None)
    board = _wfs(board_entries_now().get(skill))
    files = _skill_files(skill)
    items = log.setdefault("items", [])
    if items and items[-1].get("board") == board and items[-1].get("files") == files:
        if summary or details is not None:   # the words only: no new iteration
            if summary:
                items[-1]["summary"] = summary
            if details is not None:
                items[-1]["details"] = details
        _iter_write(skill, log)
        return {"skill": skill, "iteration": items[-1]["n"], "new": False}
    prev = items[-1] if items else {}
    items.append({"n": (prev["n"] + 1) if items else 1, "t": _now(), "note": note, "board": board, "files": files,
                  "words": _words(_raw_board(skill)), "page": _page(skill),
                  "summary": summary or prev.get("summary", ""),
                  "details": details if details is not None else prev.get("details", [])})
    _iter_write(skill, log)
    return {"skill": skill, "iteration": items[-1]["n"], "new": True, "note": note, "summary": items[-1]["summary"]}


def iteration(skill):
    items = iter_log(skill).get("items") or []
    return items[-1]["n"] if items else None


def undo(skill):
    """Put back the iteration before the last one: its files and its board definition. The last iteration is dropped."""
    log = iter_log(skill)
    items = log.get("items") or []
    if len(items) < 2:
        return {"skill": skill, "undone": False, "why": "nothing to undo: this is the first iteration"}
    if items[-1].get("note") == SNAPSHOT_NOTE:   # nothing changed since the change began: an older one isn't "the last"
        return {"skill": skill, "undone": False, "why": "nothing to undo: no change was made since it was opened"}
    last, prev = items.pop(), items[-1]
    now_words = _words(_raw_board(skill))   # an older iteration without its words keeps today's tips
    page_keys = _page_keys(_raw_board(skill)) | _page_keys(list(prev["board"].values()))
    root = os.path.join(PROJECT, SKILLS_REL, skill)
    for rel in set(_skill_files(skill)) - set(prev["files"]):
        os.remove(os.path.join(root, rel))
    for rel, text in prev["files"].items():
        os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
        with open(os.path.join(root, rel), "w", encoding="utf-8") as fh:
            fh.write(text)
    if paths.PLUGIN:
        bf = os.path.join(PROJECT, BOARD_REL, skill + ".json")
        try:
            with open(bf, encoding="utf-8") as fh:
                whole = json.load(fh)   # keep its triggers, colours and page lines: only its workflows go back
        except (OSError, ValueError):
            whole = {}
        whole["workflows"] = _with_words(list(prev["board"].values()), prev.get("words") or {}, now_words)
        if "page" in prev:   # an older iteration without its page lines keeps today's
            _put_page(whole, prev["page"], page_keys)
        with open(bf, "w", encoding="utf-8") as fh:
            json.dump(whole, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    else:
        bp = os.path.join(PROJECT, BOARD_REL)
        with open(bp, encoding="utf-8") as fh:
            defs = json.load(fh)
        olds = set(last["board"]) | set(prev["board"])
        wfs = [w for w in defs.get("workflows", []) if w.get("id") not in olds]
        at = next((i for i, w in enumerate(defs.get("workflows", [])) if w.get("id") in olds), len(wfs))
        defs["workflows"] = wfs[:at] + _with_words(list(prev["board"].values()), prev.get("words") or {}, now_words) + wfs[at:]
        if "page" in prev:
            _put_page(defs, prev["page"], page_keys)
        with open(bp, "w", encoding="utf-8") as fh:
            json.dump(defs, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    _put_readme_row(skill, (prev.get("page") or {}).get("readme_row"))
    log.pop("updating", None)
    _iter_write(skill, log)
    return {"skill": skill, "undone": True, "iteration": prev["n"], "undid": last.get("note", "")}


def iter_marks(skill):
    """{workflow id: step_marks(...)} for the last change: the latest iteration against the one before it.
    With one iteration (or none) there is nothing to compare: {}."""
    items = iter_log(skill).get("items") or []
    if len(items) < 2:
        return {}
    a, b = items[-2]["board"], items[-1]["board"]
    return {k: step_marks(a.get(k), w) for k, w in b.items() if a.get(k)}


def step_marks(o, n):
    """The Builder's change marks for one board workflow, against its last version (the same tests as wf_changes):
    {"marks": {step key: "new" | "chg"}, "removed": [the old step, plus "after": the key of the step before it]}.
    No last version: every step is new."""
    n = n or {}
    if not o:
        return {"marks": {s["key"]: "new" for s in n.get("steps", []) if s.get("key")}, "removed": []}
    os_ = {s["key"]: s for s in o.get("steps", []) if s.get("key")}
    ns = {s["key"]: s for s in n.get("steps", []) if s.get("key")}
    name = lambda s: s.get("title") or s.get("what") or s["key"]
    alts = lambda s: [(x.get("when"), x.get("then")) for x in s.get("alts", [])]
    marks = {}
    for k, b in ns.items():
        a = os_.get(k)
        if a is None:
            marks[k] = "new"
        elif name(a) != name(b) or alts(a) != alts(b) or a.get("what") != b.get("what") or \
                (a.get("why") or {}).get("sum") != (b.get("why") or {}).get("sum") or (a.get("sk") or "") != (b.get("sk") or ""):
            marks[k] = "chg"
    removed, prev = [], None
    for s in o.get("steps", []):
        if s.get("key") and s["key"] not in ns:
            removed.append(dict(s, after=prev))
        else:
            prev = s.get("key")
    return {"marks": marks, "removed": removed}


def draft_marks(skill):
    """{board workflow id: step_marks(...)} for a skill's draft, against its last version (HEAD)."""
    init()
    try:
        old = _wfs(board_entries("HEAD").get(skill) if has_head() else None)
        new = _wfs(board_entries_now().get(skill))
    except (OSError, ValueError):
        return {}
    return {k: step_marks(old.get(k), w) for k, w in new.items()}


VERSIONS_CACHE = os.path.join(os.path.dirname(GIT_DIR), "versions-cache.json")


def versions(only=None):
    """{skill: [{v, commit, t, via, text, changes, files}, ...]} oldest first. Saved versions never change, so the
    answer is cached against the newest commit: a board build reads it once instead of walking the history again
    (that walk was hundreds of git calls, most of every build's time)."""
    head = git("rev-parse", "-q", "--verify", "HEAD", check=False).strip() if has_head() else ""
    try:
        with open(VERSIONS_CACHE, encoding="utf-8") as fh:
            cache = json.load(fh)
    except (OSError, ValueError):
        cache = {}
    if not head or cache.get("head") != head:
        cache = {"head": head, "out": _versions()}
        try:
            tmp = VERSIONS_CACHE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(cache, fh)
            os.replace(tmp, VERSIONS_CACHE)
        except OSError:
            pass
    out = _with_renames(cache["out"])
    return {only: out[only]} if only and only in out else ({} if only else out)


def aliases():
    """{old skill name: its current name}, from the board's colour tables, where a rename (core-renamer, or a new
    workflow's publish) leaves the old name as an alias so earlier runs still show"""
    table = {}
    try:
        if paths.PLUGIN:
            for f in glob.glob(os.path.join(PROJECT, BOARD_REL, "*.json")):
                with open(f, encoding="utf-8") as fh:
                    table.update((json.load(fh).get("skills") or {}))
        else:
            with open(os.path.join(PROJECT, BOARD_REL), encoding="utf-8") as fh:
                table.update(json.load(fh).get("skills") or {})
    except (OSError, ValueError):
        pass
    out = {}
    for old, v in table.items():
        new, seen = (v or {}).get("alias_of"), {old}
        while new and (table.get(new) or {}).get("alias_of") and new not in seen:
            seen.add(new)
            new = table[new]["alias_of"]
        if new and new != old:
            out[old] = new
    return out


def _with_renames(out):
    """A renamed skill's versions start with those it had under each earlier name, numbered on from them; each
    such version says the name it had ("as"), so a restore can find it"""
    al = aliases()
    if not al:
        return out
    out = dict(out)
    for new in set(al.values()):
        olds = [o for o, n in al.items() if n == new and o in out]
        if not olds:
            continue
        merged = sorted([dict(x, **{"as": x.get("as") or o}) for o in olds for x in out[o]] + list(out.get(new) or []),
                        key=lambda x: x["t"])
        seen, vs = set(), []
        for x in merged:
            if x["commit"] in seen:   # the rename itself is one commit for both names: keep it once, as the new name's
                vs = [y for y in vs if y["commit"] != x["commit"]]
            seen.add(x["commit"])
            vs.append(x)
        out[new] = [dict(x, v=f"v{n}") for n, x in enumerate(vs, 1)]
    return out


def _versions(only=None):
    out, last_tree, last_board = {}, {}, {}
    prev = None
    for c in commits():
        h = c["commit"]
        names = set(git("ls-tree", "--name-only", f"{h}:{SKILLS_REL}", check=False).split())
        boards = board_entries(h)
        for sk in sorted(names | set(boards) | set(last_tree)):
            if only and sk != only:
                continue
            tree = tree_of(h, f"{SKILLS_REL}/{sk}") if sk in names else None
            board = boards.get(sk)
            bkey = json.dumps(board, sort_keys=True) if board is not None else None
            if sk in last_tree and tree == last_tree[sk] and bkey == last_board.get(sk):
                continue
            if sk not in last_tree and tree is None and board is None:
                continue
            old_board = json.loads(last_board[sk]) if last_board.get(sk) else None
            files = []
            if prev and sk in last_tree:
                files = [f[len(SKILLS_REL) + len(sk) + 2:] for f in
                         git("diff", "--name-only", prev, h, "--", f"{SKILLS_REL}/{sk}").splitlines()]
            vs = out.setdefault(sk, [])
            changes = board_changes(old_board, board) if (sk in last_tree or board is not None) and bkey != last_board.get(sk) else []
            if tree is None and sk in last_tree and last_tree[sk] is not None:
                changes = ["Skill removed"] + changes
            vs.append({"v": f"v{len(vs) + 1}", "commit": h[:12], "t": c["t"], "via": c["via"],
                       "via_text": VIA.get(c["via"], c["via"]),
                       "text": c["notes"].get(sk) or c["subject"], "changes": changes if vs else [],
                       "files": files, "review": (c.get("review") or {}).get(sk)})
            last_tree[sk], last_board[sk] = tree, bkey
        prev = h
    return out


def is_draft(skill):
    """The skill has edits since its last version: its folder, or its board definition."""
    if not has_head():
        return True
    if skill in status()["changed"]:
        return True
    try:
        now = board_entries_now().get(skill)
    except (OSError, ValueError):
        return False
    return json.dumps(now, sort_keys=True) != json.dumps(board_entries("HEAD").get(skill), sort_keys=True)


def board_entries_now():
    """{skill: its board definition} in the working folder (what board_entries reads from a commit)."""
    out = {}
    if paths.PLUGIN:
        for f in glob.glob(os.path.join(PROJECT, BOARD_REL, "*.json")):
            with open(f, encoding="utf-8") as fh:
                out[os.path.basename(f)[:-5]] = _plain(json.load(fh))
        return out
    with open(os.path.join(PROJECT, BOARD_REL), encoding="utf-8") as fh:
        defs = json.load(fh)
    for w in defs.get("workflows", []):
        sk = board_skill(w)
        if sk:
            out.setdefault(sk, {"workflows": []})["workflows"].append(w)
    return {k: _plain(v) for k, v in out.items()}


def start():
    """Start the history the first time it is needed, from the skills as they are now, so the first edit is a draft
    with something to compare against. The prompt hook calls this before every request; once there is a history it
    does nothing. A folder that had skills before the plugin kept a history (an install, or an update from a version
    without one) gets "History started" as each skill's v1, before Claude can edit anything."""
    if ready() and has_head():
        return {"started": False, "why": "history already started"}
    return dict(save(via="start"), started=True)


def current(skill):
    """The version a run uses now: "vN", or "vN+draft" when the skill has edits that aren't a version yet.
    Nothing is saved: a version is one finished change, made by the architect (or "save a version")."""
    start()
    vs = versions(skill).get(skill) or []
    v = vs[-1]["v"] if vs else "v0"
    return v + "+draft" if is_draft(skill) else v


# ---------- the impact review: what changed, and which earlier runs to check it against ----------
def diff(skill):
    """What changed since the skill's last version: a unified diff of its folder and of its board definition."""
    init()
    stage()
    files = git("diff", "--cached", "HEAD", "--", f"{SKILLS_REL}/{skill}", check=False) if has_head() else ""
    try:
        old = json.dumps(board_entries("HEAD").get(skill), indent=1, sort_keys=True, ensure_ascii=False).splitlines()
        new = json.dumps(board_entries_now().get(skill), indent=1, sort_keys=True, ensure_ascii=False).splitlines()
        board = "\n".join(difflib.unified_diff(old, new, "board (last version)", "board (now)", lineterm="", n=2))
    except (OSError, ValueError):
        board = ""
    vs = versions(skill).get(skill) or []
    return {"skill": skill, "since": vs[-1]["v"] if vs else None, "draft": is_draft(skill),
            "files": files, "board": board}


def _ledger():
    rows = []
    try:
        with open(paths.DONE_LIST, encoding="utf-8") as fh:
            for line in fh:
                try:
                    obj = json.loads(line)
                except ValueError:
                    continue
                if isinstance(obj, dict):
                    rows.append(obj)
    except OSError:
        pass
    return rows


def _trace(name):
    for d in paths.TRACE_DIRS:
        f = os.path.join(d, name)
        if os.path.isfile(f):
            lines = []
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    try:
                        lines.append(json.loads(line))
                    except ValueError:
                        pass
            return lines
    return None


def runs(skill, limit=20):
    """Earlier runs to review a change against, each summed up: its input, steps, outcome and why it was picked.
    Picked in this order, up to `limit`: the latest test run of each test case (one per path), every unusual real
    run (failed or waiting step, needs-you or check-this outcome, a rerun), then the newest ordinary real runs
    whose outcome differs from those already picked. A run saved under an old name of the skill counts too."""
    names = {skill}
    existing = set(os.listdir(os.path.join(PROJECT, SKILLS_REL))) if os.path.isdir(os.path.join(PROJECT, SKILLS_REL)) else set()
    for row in _ledger():   # renamed skills: an old name that no longer exists and is the start of this one
        old = row.get("skill") or ""
        if old and old not in existing and skill.startswith(old + "-"):
            names.add(old)
    started = {}
    for row in _ledger():
        if row.get("status") == "started" and row.get("skill") in names and row.get("trace"):
            started[row["trace"]] = row
    found = []
    for trace, row in started.items():
        lines = _trace(trace)
        if not lines:
            continue
        steps = [x for x in lines if not x.get("header") and not x.get("end") and "entry_match" not in x]
        end = next((x for x in lines if x.get("end")), None)
        if not end:
            continue   # unfinished: nothing to compare against
        status = {x.get("status") for x in steps}
        unusual = [w for w, ok in [("a step failed", "failed" in status), ("waited on the user", "needs_user" in status),
                                   ("needed a look", end.get("attention") in ("review", "action")),
                                   ("a rerun", bool(row.get("rerun_of")) or (row.get("attempt") or 0) > 1)] if ok]
        found.append({"run": trace[:-6], "t": row.get("t"), "version": row.get("version"), "test": bool(row.get("test")),
                      "try": bool(row.get("try")),   # a new workflow's try (as a test or for real), before its v1
                      "case": row.get("case"), "expected_path": row.get("expect"), "input": row.get("input"),
                      "steps": [{k: x.get(k) for k in ("title", "step", "type", "status", "result") if x.get(k)} for x in steps],
                      "outcome": {k: end.get(k) for k in ("verdict", "attention", "next") if end.get(k)}, "_unusual": unusual})
    found.sort(key=lambda x: x["t"] or "", reverse=True)
    latest, seen_items = [], set()                   # one attempt per item: its newest
    for x in found:
        item = x["run"].rsplit("-a", 1)[0]
        if x["test"] or item not in seen_items:
            seen_items.add(item)
            latest.append(x)
    found = latest
    picked, seen_cases, outcomes = [], set(), set()
    for x in found:                                   # 1. the latest test of each case: one per path
        if x["test"] and x["case"] and x["case"] not in seen_cases:
            seen_cases.add(x["case"])
            picked.append(dict(x, why="latest test of " + x["case"].split("/")[-1]))
    for x in found:                                   # 2. every unusual real run
        if not x["test"] and x["_unusual"]:
            picked.append(dict(x, why="unusual: " + ", ".join(x["_unusual"])))
    for x in found:                                   # 3. ordinary real runs with an outcome not seen yet
        key = " ".join(str(x["outcome"].get("verdict", "")).lower().split()[:5])
        if not x["test"] and not x["_unusual"] and key not in outcomes:
            outcomes.add(key)
            picked.append(dict(x, why="a different outcome"))
    for x in picked:
        x.pop("_unusual", None)
    return {"skill": skill, "names": sorted(names), "found": len(found), "picked": len(picked[:limit]), "runs": picked[:limit]}


# ---------- publishing a draft: one call for the heavy part, and the review kept with the draft ----------
def fingerprint(skill):
    """What the draft is now: its folder's diff and its board definition. A pending review is current only while
    this stays the same, so an edit after the review shows it as out of date."""
    stage()
    files = git("diff", "--cached", "HEAD", "--", f"{SKILLS_REL}/{skill}", check=False) if has_head() else ""
    try:
        board = json.dumps(board_entries_now().get(skill), sort_keys=True)
    except (OSError, ValueError):
        board = ""
    return hashlib.sha1((files + "\x00" + board).encode()).hexdigest()[:16]


def draft_changes(skill):
    """The draft's changes since its last version, in plain words: the board's changes and the files changed."""
    return [x["t"] for x in draft_change_items(skill)]


def uses_words(name):
    return "the public web" if name in ("web", "browser") else name.replace("-", " ").title()


def draft_change_items(skill):
    """draft_changes with the steps each line is about: [{"t", "keys"}]. The board's changes, the connections its
    Definition's `uses:` gained or lost, and only when nothing else says what changed, the files changed."""
    init()
    stage()
    items = []
    try:
        items = board_change_items(board_entries("HEAD").get(skill) if has_head() else None, board_entries_now().get(skill))
    except (OSError, ValueError):
        pass
    try:
        import entries
        rel = f"{SKILLS_REL}/{skill}/SKILL.md"
        old = entries.parse_definition(git("show", f"HEAD:{rel}", check=False)) if has_head() else None
        new = entries.definition(skill)
        if old is not None and (old.get("trigger") or "") != ((new or {}).get("trigger") or ""):
            t = (new or {}).get("trigger")
            items.append({"t": f"+ Its trigger now lives inside it (starts on “{((new or {}).get('starts on') or [''])[0]}”)" if t
                          else "- It no longer has a trigger of its own: it is run directly", "keys": []})
        ou, nu = list(((old or {}).get("uses") or {})), list(((new or {}).get("uses") or {}))
        if old is not None and ou != nu:
            got, lost = [u for u in nu if u not in ou], [u for u in ou if u not in nu]
            if got:
                items.append({"t": "+ Now uses " + " and ".join(uses_words(u) for u in got), "keys": []})
            if lost:
                items.append({"t": "- No longer uses " + " and ".join(uses_words(u) for u in lost), "keys": []})
    except Exception:
        pass
    pre = f"{SKILLS_REL}/{skill}/"
    files = [f[len(pre):] for f in changed_paths() if f.startswith(pre)]
    if files and not items:
        items.append({"t": ("Edited its instructions" if files == ["SKILL.md"] else (files[0] if len(files) == 1 else f"{len(files)} files") + " changed"), "keys": []})
    return items


def new_uses(skill):
    """The connections the draft's Definition `uses` that its last version didn't: the draft bar's Connect step.
    [] when it has no version yet or nothing new."""
    try:
        import entries
        if not has_head():
            return []
        old = entries.parse_definition(git("show", f"HEAD:{SKILLS_REL}/{skill}/SKILL.md", check=False))
        if old is None:
            return []
        def names(u):
            return [str(x).partition(":")[0].strip().lower() for x in (u or [])]
        ou, nu = names(old.get("uses")), names((entries.definition(skill) or {}).get("uses"))
        return [u for u in nu if u not in ou]
    except Exception:
        return []


def pending(skill, review_file=None, confirm=False):
    """The draft's impact review, kept before it is saved. With review_file: store it (a confirm keeps the user's
    yes). Without: read it back, with "current" false when the draft changed after it was written."""
    f = os.path.join(PENDING_DIR, skill + ".json")
    if review_file:
        with open(review_file, encoding="utf-8") as fh:
            data = json.load(fh)
        rv = data.get(skill, data)
        if confirm:
            rv["confirmed"] = True
        os.makedirs(PENDING_DIR, exist_ok=True)
        with open(f, "w", encoding="utf-8") as fh:
            json.dump({"skill": skill, "fingerprint": fingerprint(skill), "review": rv}, fh, ensure_ascii=False, indent=1)
    elif confirm and os.path.isfile(f):
        with open(f, encoding="utf-8") as fh:
            data = json.load(fh)
        data["review"]["confirmed"] = True
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
    try:
        with open(f, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return {"skill": skill, "review": data.get("review"), "current": data.get("fingerprint") == fingerprint(skill)}


def prepare(skill, limit=20):
    """Everything Publish needs, in one call: the board build's problems, the diff, the draft's changes in plain
    words, and the earlier runs to check the change against."""
    r = subprocess.run([sys.executable, "-I", os.path.join(os.path.dirname(os.path.abspath(__file__)), "build_workflows.py")],
                       capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    lines = [l for l in out.splitlines() if l.startswith(("ERROR", "WARN"))]
    d = diff(skill)
    return {"skill": skill, "draft": d["draft"], "since": d["since"],
            "build": {"ok": r.returncode == 0, "errors": [l for l in lines if l.startswith("ERROR")],
                      "warnings": [l for l in lines if l.startswith("WARN")]},
            "changes": draft_changes(skill), "diff": {"files": d["files"], "board": d["board"]},
            "runs": runs(skill, limit)}


def _readme_row(skill):
    """The project README's row for this skill, from its SKILL.md description (when both exist)."""
    readme = os.path.join(PROJECT, "README.md")
    try:
        with open(os.path.join(PROJECT, SKILLS_REL, skill, "SKILL.md"), encoding="utf-8") as fh:
            m = re.search(r"^description:\s*(.+)$", fh.read(), re.M)
        with open(readme, encoding="utf-8") as fh:
            t = fh.read()
    except OSError:
        return
    if not m:
        return
    desc = m.group(1).strip()
    new = re.sub(rf"^(\| `{re.escape(skill)}` \| [^|]+ \| ).*?( \|)$", lambda x: x.group(1) + desc + x.group(2), t, flags=re.M)
    if new != t:
        with open(readme, "w", encoding="utf-8") as fh:
            fh.write(new)


def restore(skill, v):
    vs = versions(skill).get(skill) or []
    hit = next((x for x in vs if x["v"] == v), None)
    if not hit:
        raise SystemExit(json.dumps({"error": f"{skill} has no {v}", "versions": [x["v"] for x in vs]}))
    if vs and vs[-1]["v"] == v:
        return {"restored": False, "why": f"{v} is already the current version"}
    if status()["files"]:
        save(via="outside", message="Saved automatically before a restore", only=[skill])
    full = git("rev-parse", hit["commit"]).strip()
    folder = os.path.join(PROJECT, SKILLS_REL, skill)
    was = hit.get("as")
    if was and was != skill:
        return _restore_renamed(skill, was, full, v, hit)
    if tree_of(full, f"{SKILLS_REL}/{skill}"):
        if os.path.isdir(folder):
            shutil.rmtree(folder)
        git("checkout", full, "--", f"{SKILLS_REL}/{skill}")
    old = board_entries(full).get(skill)
    if paths.PLUGIN:
        f = os.path.join(PROJECT, BOARD_REL, skill + ".json")
        if old is None:
            if os.path.exists(f):
                os.remove(f)
        else:
            git("checkout", full, "--", f"{BOARD_REL}/{skill}.json")
    else:
        p = os.path.join(PROJECT, BOARD_REL)
        with open(p, encoding="utf-8") as fh:
            defs = json.load(fh)
        ws = defs.get("workflows", [])
        # board_entries gives {"workflows": [...]} per skill: put back those workflows, in place of the skill's
        # current ones (at the first one's place)
        olds = (old or {}).get("workflows") or []
        ids = {w.get("id") for w in olds}
        mine = [i for i, w in enumerate(ws) if board_skill(w) == skill or w.get("id") in ids]
        at = mine[0] if mine else len(ws)
        rest = [w for i, w in enumerate(ws) if i not in mine]
        at -= sum(1 for i in mine if i < at)
        defs["workflows"] = rest[:at] + olds + rest[at:]
        # the page's lines for them (rule 29, rule 31) sit apart from the workflows: put back the version's own
        try:
            then = json.loads(git("show", f"{full}:{BOARD_REL}", check=False) or "{}")
        except ValueError:
            then = {}
        keys = set()
        for w in olds + [w for i, w in enumerate(ws) if i in mine]:
            keys.add("workflow:" + str(w.get("id")))
            keys |= {"trigger:" + str(e) for e in w.get("entries") or []}
        for part in ("examples", "results", "summaries"):
            cur, was = defs.setdefault(part, {}), then.get(part) or {}
            for k in keys:
                if k in was:
                    cur[k] = was[k]
                else:
                    cur.pop(k, None)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(defs, indent=2, ensure_ascii=False) + "\n")
    _readme_row(skill)
    r = save(via="restore", message=f"Restored {v} ({hit['text']})", notes={skill: f"Restored {v}: {hit['text']}"}, only=[skill])
    return {"restored": True, "skill": skill, "from": v, "saved": r}


def _restore_renamed(skill, was, full, v, hit):
    """Restore a version saved before the skill was renamed: its files and board part as they were then, written under
    today's name, keeping today's name and category on the board (a restore puts back what it did, not what it was
    called)."""
    word = re.compile(r"(?<![\w-])" + re.escape(was) + r"(?![\w-])")
    folder = os.path.join(PROJECT, SKILLS_REL, skill)
    files = git("ls-tree", "-r", "--name-only", full, "--", f"{SKILLS_REL}/{was}").splitlines()
    if not files:
        raise SystemExit(json.dumps({"error": f"{v} of {skill} (then {was}) has no files to restore"}))
    if os.path.isdir(folder):
        shutil.rmtree(folder)
    for f in files:
        data = git("show", f"{full}:{f}", text=False)
        dst = os.path.join(folder, f[len(SKILLS_REL) + len(was) + 2:])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            data = word.sub(skill, data.decode("utf-8")).encode("utf-8")
        except UnicodeDecodeError:
            pass
        with open(dst, "wb") as fh:
            fh.write(data)
    if paths.PLUGIN:
        bf = os.path.join(PROJECT, BOARD_REL, skill + ".json")
        then = git("show", f"{full}:{BOARD_REL}/{was}.json", check=False)
        if then:
            try:
                with open(bf, encoding="utf-8") as fh:
                    now = json.load(fh)
            except (OSError, ValueError):
                now = {}
            old = json.loads(word.sub(skill, then))
            keep = {w.get("id"): w for w in now.get("workflows") or []}
            for w in old.get("workflows") or []:   # today's name, category and where it shows stay as they are
                k = keep.get(w.get("id")) or {}
                for f in ("short", "name", "category", "from"):
                    if f in k:
                        w[f] = k[f]
            for eid, e in (old.get("entries") or {}).items():
                if "category" in ((now.get("entries") or {}).get(eid) or {}):
                    e["category"] = now["entries"][eid]["category"]
            old["skills"] = dict(old.get("skills") or {}, **(now.get("skills") or {}))
            if now.get("categories"):
                old["categories"] = now["categories"]
            with open(bf, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(old, indent=2, ensure_ascii=False) + "\n")
    _readme_row(skill)
    r = save(via="restore", message=f"Restored {v} ({hit['text']})", notes={skill: f"Restored {v}: {hit['text']}"}, only=[skill])
    return {"restored": True, "skill": skill, "from": v, "then_called": was, "saved": r}


def main(argv):
    p = argparse.ArgumentParser(description="Hidden history of the skills and their board definitions")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("save")
    s.add_argument("--via", default="outside", choices=sorted(VIA))
    s.add_argument("--message", default="")
    s.add_argument("--note", action="append", default=[], help="SKILL=what changed for that skill, in plain words")
    s.add_argument("--review", help="a JSON file: {skill: the impact review of this change}")
    s.add_argument("--quiet", action="store_true")
    s.add_argument("--only", action="append", default=[], help="save only this skill (repeat for each); every other draft stays a draft. "
                   "A save --via architect with --note and no --only saves just the noted skills")
    sub.add_parser("status")
    st = sub.add_parser("start")
    st.add_argument("--quiet", action="store_true")
    d = sub.add_parser("diff")
    d.add_argument("skill")
    rn = sub.add_parser("runs")
    rn.add_argument("skill")
    rn.add_argument("--max", type=int, default=20)
    v = sub.add_parser("versions")
    v.add_argument("skill", nargs="?")
    c = sub.add_parser("current")
    c.add_argument("skill")
    pp = sub.add_parser("prepare")
    pp.add_argument("skill")
    pp.add_argument("--max", type=int, default=20)
    pe = sub.add_parser("pending")
    pe.add_argument("skill")
    pe.add_argument("--review", help="a JSON file: {skill: the impact review}")
    pe.add_argument("--confirm", action="store_true", help="the user said yes to what may change")
    r = sub.add_parser("restore")
    r.add_argument("skill")
    r.add_argument("v")
    up = sub.add_parser("updating", help="Claude has started changing the draft (the Builder shows it)")
    up.add_argument("skill")
    up.add_argument("what")
    sub.add_parser("settle-updating", help="end of the turn: drop every \"updating\" mark left")
    cp = sub.add_parser("checkpoint", help="after one change: keep it as the draft's next iteration")
    cp.add_argument("skill")
    cp.add_argument("--note", default="", help="what this change did, in plain words")
    cp.add_argument("--summary", default="", help="one line: how the whole draft differs from the published version")
    cp.add_argument("--details", help="a JSON file: [{kind: changed|new|gone, t, why, keys}], the draft's changes with reasons")
    it = sub.add_parser("iterations")
    it.add_argument("skill")
    ud = sub.add_parser("undo", help="put back the iteration before the last one")
    ud.add_argument("skill")
    rm = sub.add_parser("rename", help="name a new skill: move its folder, name and iteration log")
    rm.add_argument("old")
    rm.add_argument("new")
    a = p.parse_args(argv)
    if a.cmd == "save":
        notes = dict(n.split("=", 1) for n in a.note if "=" in n)
        review = None
        if a.review:
            with open(a.review, encoding="utf-8") as fh:
                review = json.load(fh)
        only = a.only or (sorted(notes) if a.via == "architect" and notes else None)
        out = save(a.via, a.message, notes, a.quiet, review, only=only)
        if a.quiet:
            return
    elif a.cmd == "start":
        out = start()
        if a.quiet:
            return
    elif a.cmd == "status":
        out = status()
    elif a.cmd == "versions":
        out = versions(a.skill)
    elif a.cmd == "diff":
        out = diff(a.skill)
    elif a.cmd == "runs":
        out = runs(a.skill, a.max)
    elif a.cmd == "prepare":
        out = prepare(a.skill, a.max)
    elif a.cmd == "pending":
        out = pending(a.skill, a.review, a.confirm) or {"skill": a.skill, "review": None}
    elif a.cmd == "current":
        out = {"skill": a.skill, "version": current(a.skill)}
    elif a.cmd == "updating":
        out = updating(a.skill, a.what)
    elif a.cmd == "settle-updating":
        out = {"settled": settle_updating()}
    elif a.cmd == "checkpoint":
        out = checkpoint(a.skill, a.note, a.summary, read_details(a.details))
    elif a.cmd == "iterations":
        out = [{k: x.get(k) for k in ("n", "t", "note", "summary")} for x in iter_log(a.skill).get("items", [])]
    elif a.cmd == "undo":
        out = undo(a.skill)
    elif a.cmd == "rename":
        out = rename(a.old, a.new)
    else:
        out = restore(a.skill, a.v)
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main(sys.argv[1:])
