#!/usr/bin/env python3
"""Rename workflows, connections and categories, one or many at once, so a name changes everywhere it is written
(core-renamer). Claude works out what the user wants; this script makes the list and then does every edit.

    rename.py workflow <name> [--name "New name"] [--category <cat>] [--skill workflow-<cat>-<desc>]
    rename.py connection <name> [--name "Label"] [--id <new-id>]
    rename.py category <cat> --to <cat2> [--label "Label"] [--meaning "what belongs there"]
    rename.py pattern <find> <replace> [--category <cat>]      every workflow name containing <find> (any case)
    rename.py list <file.json>                                  [{"workflow"|"connection": <name>, "name"?, "category"?,
                                                                  "skill"?, "id"?}, ...]  (names Claude suggested)
        Each writes the plan, <live>/rename-plan.json, and prints it: one line per item, old -> new, and any
        problem that stops it. Nothing is changed.

    rename.py apply
        Does the plan: for a workflow, its skill folder and name, its board file (name, category, colour table with
        the old name kept as an alias so earlier runs still show), its trigger's category, the README row and the
        category list; for a connection, its label, or its id: folder, status file and every `uses:` line that
        names it. Then the board build, and one version per renamed skill ("Renamed from …"). A skill with a draft
        not yet published is renamed but not saved: the rename goes live with that draft's publish.

A workflow keeps its board id, so its runs, done list, tests and links stay as they are. A workflow still in the
category `new` is named when it is published, never here. The plugin's own skills are never renamed from a folder
that only has it installed. Prints one JSON object; {"error": ...} with what to fix.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402
import board_store  # noqa: E402
import skill_history as sh  # noqa: E402

PLAN = os.path.join(paths.LIVE, "rename-plan.json")
SKILLS = paths.USER_SKILLS
H = os.path.join(HERE, "skill_history.py")


class Stop(Exception):
    pass


def out(obj, code=0):
    print(json.dumps(obj, indent=1, ensure_ascii=False))
    sys.exit(code)


def rd(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def wr(p, t):
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(t)


def jload(p):
    return json.loads(rd(p))


def jsave(p, obj):
    wr(p, json.dumps(obj, indent=2, ensure_ascii=False) + "\n")


def py(*args):
    r = subprocess.run([sys.executable, "-I", *args], capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def slug(s):
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")


def word(name):
    """a name as it is written in text: never part of a longer name"""
    return re.compile(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])")


def cat_label(cat, defs):
    return ((defs.get("categories") or {}).get(cat) or {}).get("name") or cat.capitalize()


def drafts():
    code, so, _ = py(H, "status")
    try:
        return set(json.loads(so).get("changed") or [])
    except ValueError:
        return set()


# ---------- finding things ----------

def workflows(defs):
    return [w for w in defs.get("workflows") or [] if (w.get("match") or {}).get("skill", "").startswith("workflow-")]


def find_workflow(name, defs):
    n = name.strip().lower()
    for w in workflows(defs):
        sk = w["match"]["skill"]
        if n in {str(w.get("id", "")).lower(), str(w.get("short", "")).lower(), sk, sk[len("workflow-"):]}:
            return w
    raise Stop(f"no workflow called {name!r} (its name on the board, its skill name or its id)")


def connections():
    out = {}
    for root in {paths.SKILLS, SKILLS}:
        if os.path.isdir(root):
            for d in os.listdir(root):
                f = os.path.join(root, d, "SKILL.md")
                if d.startswith("connection-") and os.path.isfile(f):
                    m = re.search(r"(?m)^system:\s*(.+)$", rd(f))
                    out[d[len("connection-"):]] = {"label": m.group(1).strip() if m else d[11:], "file": f,
                                                   "org": root == paths.SKILLS and root != SKILLS}
    return out


def users_of(conn):
    """the folder's own skills whose Definition lists this connection under uses:"""
    found = []
    if os.path.isdir(SKILLS):
        for d in sorted(os.listdir(SKILLS)):
            f = os.path.join(SKILLS, d, "SKILL.md")
            if os.path.isfile(f) and re.search(r"(?ms)^uses:\s*\n(?:  .*\n)*?  " + re.escape(conn) + r":", rd(f)):
                found.append(d)
    return found


# ---------- the plan ----------

def wf_item(w, defs, name=None, cat=None, skill=None):
    old_sk, old_cat = w["match"]["skill"], w.get("category")
    new_short = (name or w.get("short") or "").strip()
    new_cat = slug(cat).replace("-", "") if cat else old_cat
    desc = old_sk.split("-", 2)[2] if old_sk.count("-") >= 2 else slug(new_short)
    if (name or new_cat != old_cat) and not skill:   # renamed or moved: the description comes from its whole name
        desc = slug(new_short)
        if desc.startswith(new_cat + "-"):   # "Security watch" in security: workflow-security-watch
            desc = desc[len(new_cat) + 1:]
    new_sk = skill or f"workflow-{new_cat}-{desc}"
    probs = []
    if old_cat == "new" or old_sk.startswith("workflow-new-"):
        probs.append("still a new workflow: it is named when you publish it")
    if old_sk in board_store.org_skills() and not paths.SOURCE:
        probs.append("one of the plugin's own workflows: it can't be renamed from here")
    if new_cat == "new" and old_cat != "new":
        probs.append("`new` is kept for workflows not published yet")
    if not re.match(r"^workflow-[a-z0-9]+-[a-z0-9-]+$", new_sk) or len(new_sk) > 64:
        probs.append(f"{new_sk} doesn't read workflow-<category>-<description>, 64 characters at most")
    if new_sk != old_sk and os.path.exists(os.path.join(SKILLS, new_sk)):
        probs.append(f"{new_sk} already exists")
    cats = paths.categories()
    return {"kind": "workflow", "wid": w.get("id"), "old_skill": old_sk, "new_skill": new_sk,
            "old_name": w.get("short"), "new_name": new_short, "old_category": old_cat, "new_category": new_cat,
            "new_category_label": cat_label(new_cat, defs), "category_is_new": new_cat not in cats,
            "problems": probs}


def conn_item(name, label=None, new_id=None):
    cs = connections()
    key = name.lower().replace("connection-", "")
    if key not in cs:
        key = next((k for k, v in cs.items() if v["label"].lower() == name.lower()), None)
    if not key:
        raise Stop(f"no connection called {name!r}")
    c, nid = cs[key], slug(new_id).replace("-", "") if new_id else key
    probs = []
    if c["org"]:
        probs.append("one of the plugin's own connections: it can't be renamed from here")
    if nid != key and nid in cs:
        probs.append(f"connection-{nid} already exists")
    return {"kind": "connection", "old_id": key, "new_id": nid, "old_name": c["label"],
            "new_name": (label or c["label"]).strip(), "used_by": users_of(key), "problems": probs}


def plan(items, extra=None):
    items = [i for i in items if (i.get("old_skill"), i.get("old_name"), i.get("old_category"), i.get("old_id"))
             != (i.get("new_skill"), i.get("new_name"), i.get("new_category"), i.get("new_id"))] + list(extra or [])
    seen = {}
    for i in items:
        t = i.get("new_skill") or ("connection-" + i["new_id"] if i["kind"] == "connection" else None)
        if t and t in seen:
            i["problems"].append(f"two items would both be called {t}")
        seen[t] = 1
    before = drafts()
    for i in items:
        sk = i.get("old_skill") or ("connection-" + i["old_id"] if i["kind"] == "connection" else None)
        i["has_draft"] = bool(sk and sk in before)
    os.makedirs(paths.LIVE, exist_ok=True)
    jsave(PLAN, {"items": items})
    ok = [i for i in items if not i["problems"]]
    return {"plan": paths.rel(PLAN) if hasattr(paths, "rel") else PLAN, "count": len(items), "ready": len(ok),
            "items": [line(i) for i in items], "blocked": {line(i): i["problems"] for i in items if i["problems"]},
            "drafts": [line(i) for i in items if i.get("has_draft")],
            "next": "show the list to the user, then on their yes: rename.py apply" if items else "nothing to rename"}


def line(i):
    if i["kind"] == "workflow":
        cat = f" (now in {i['new_category_label']}{', a new category' if i['category_is_new'] else ''})" \
            if i["new_category"] != i["old_category"] else ""
        sk = f" [{i['new_skill']}]" if i["new_skill"] != i["old_skill"] else ""
        return f"{i['old_name']} -> {i['new_name']}{cat}{sk}"
    if i["kind"] == "connection":
        idp = f" (id {i['old_id']} -> {i['new_id']})" if i["new_id"] != i["old_id"] else ""
        return f"{i['old_name']} connection -> {i['new_name']}{idp}"
    return f"category {i['old']} -> {i['new']}"


# ---------- doing it ----------

def board_file(skill):
    f = board_store.user_files().get(skill)
    if not f:
        raise Stop(f"no board file for {skill} (an in-project setup can't be renamed yet)")
    return f


def do_workflow(i, defs):
    old, new = i["old_skill"], i["new_skill"]
    bf = board_file(old)
    if new != old:
        code, so, se = py(H, "rename", old, new)
        res = json.loads(so or "{}") if so.strip().startswith("{") else {}
        if code or res.get("renamed") is False:
            raise Stop(f"couldn't move {old}: " + (res.get("why") or se or so).strip()[-200:])
        for root, _d, files in os.walk(SKILLS):   # its own folder, and other skills' tests that hand work on to it
            for f in files:
                p = os.path.join(root, f)
                try:
                    t = rd(p)
                except (UnicodeDecodeError, OSError):
                    continue
                if word(old).search(t):
                    wr(p, word(old).sub(new, t))
        tests = paths.TESTS if os.path.isdir(paths.TESTS) else None   # the folder's own test sources name it too
        for root, _d, files in os.walk(tests) if tests else ():
            for f in files:
                p = os.path.join(root, f)
                try:
                    t = rd(p)
                except (UnicodeDecodeError, OSError):
                    continue
                if word(old).search(t):
                    wr(p, word(old).sub(new, t))
        nbf = os.path.join(os.path.dirname(bf), new + ".json")
        wr(nbf, word(old).sub(new, rd(bf)))
        os.remove(bf)
        bf = nbf
    edit_board(bf, i)
    fix_heading(i)
    readme = os.path.join(paths.PROJECT, "README.md")
    if new != old and os.path.isfile(readme):
        wr(readme, word(old).sub(new, rd(readme)))
    return [old, new]


def edit_board(bf, i):
    """the workflow's board file: its name, category, where it shows, and the old skill name kept as an alias"""
    old, new = i["old_skill"], i["new_skill"]
    b = jload(bf)
    label = i["new_category_label"]
    for w in b.get("workflows") or []:
        if w.get("id") != i["wid"]:
            continue
        if w.get("name") in (None, i["old_name"]) or str(w.get("name", "")).startswith(i["old_name"] + ":"):
            w["name"] = i["new_name"] + str(w.get("name") or "")[len(i["old_name"] or ""):]
        w["short"], w["category"] = i["new_name"], i["new_category"]
        w["from"] = label + " · " + str(w.get("from", "")).split(" · ", 1)[-1]
        for eid in w.get("entries") or []:
            if eid in (b.get("entries") or {}):
                b["entries"][eid]["category"] = label
    sk = b.setdefault("skills", {})
    if new != old:
        sk[new] = dict(sk.pop(new, None) or {}, **{k: v for k, v in (sk.get(old) or {}).items() if k != "alias_of"})
        sk[old] = {"alias_of": new}   # earlier runs under the old name still show
        for k, v in sk.items():
            if v.get("alias_of") == old:
                v["alias_of"] = new
    sk.setdefault(new, {})["short"] = i["new_name"]
    if i["category_is_new"]:
        b.setdefault("categories", {})[i["new_category"]] = {"name": label, "tone": "amber", "section": "workflows"}
        add_category(i["new_category"], f"{label.lower()} workflows")
    cats = b.get("categories") or {}
    if i["old_category"] in cats and not any(w.get("category") == i["old_category"] for w in b.get("workflows") or []):
        cats.pop(i["old_category"])   # nothing in this file is in the old category any more
    jsave(bf, b)


def fix_heading(i):
    md = os.path.join(SKILLS, i["new_skill"], "SKILL.md")
    t = rd(md)
    if i["old_name"] and re.search(r"(?m)^# " + re.escape(i["old_name"]) + r"\s*$", t, re.I):
        wr(md, re.sub(r"(?mi)^# " + re.escape(i["old_name"]) + r"\s*$", "# " + i["new_name"], t, count=1))


def fix_iterations(i):
    """The draft's change log keeps whole snapshots (Undo puts them back): give each the new name and category, so
    an Undo never brings back the old ones, and drop a snapshot that only recorded the rename itself"""
    old, new = i["old_skill"], i["new_skill"]
    log = sh.iter_log(new)
    if not log.get("items"):
        return
    log = json.loads(word(old).sub(new, json.dumps(log, ensure_ascii=False)))
    label = i["new_category_label"]
    for it in log["items"]:
        for w in (it.get("board") or {}).values():
            if isinstance(w, dict) and w.get("id") == i["wid"]:
                w["short"], w["category"] = i["new_name"], i["new_category"]
                if w.get("name") in (None, i["old_name"]):
                    w["name"] = i["new_name"]
                if "from" in w:
                    w["from"] = label + " · " + str(w["from"]).split(" · ", 1)[-1]
    items = log["items"]
    while len(items) > 1 and items[-1].get("note") == sh.SNAPSHOT_NOTE and \
            (items[-1].get("files"), items[-1].get("board")) == (items[-2].get("files"), items[-2].get("board")):
        items.pop()
    sh._iter_write(new, log)


def published_first(i, defs, now_at="old"):
    """A workflow with a draft: rename its published version and save that (so the new name has its history and
    the draft still has a version to be a draft of), then put the draft back on top under the new name.
    now_at "new": it was renamed already with its draft, and its published version is still under the old name
    (a repair). Returns the saved skills, or None when it was never published (a plain rename then)."""
    old, new = i["old_skill"], i["new_skill"]
    if not sh.has_head() or not sh.tree_of("HEAD", f"{sh.SKILLS_REL}/{old}"):
        return None
    here = new if now_at == "new" else old
    folder, bf = os.path.join(SKILLS, here), board_store.user_files().get(here)
    keep = [f for f in (sh._iter_path(here), os.path.join(sh.PENDING_DIR, here + ".json")) if os.path.isfile(f)]
    stash = tempfile.mkdtemp(prefix="rename-", dir=paths.LIVE)
    try:
        shutil.copytree(folder, os.path.join(stash, "skill"))
        if bf:
            shutil.copy(bf, os.path.join(stash, "board.json"))
        for f in keep:
            shutil.copy(f, os.path.join(stash, os.path.basename(os.path.dirname(f)) + "-" + os.path.basename(f)))
            os.remove(f)
        # the published version, back in place under its old name
        shutil.rmtree(folder)
        if bf:
            os.remove(bf)
        board_rel = f"{sh.BOARD_REL}/{old}.json"
        sh.git("checkout", "HEAD", "--", f"{sh.SKILLS_REL}/{old}", *([board_rel] if sh.tree_of("HEAD", board_rel) else []))
        hb = board_store.user_files().get(old)
        w = next((x for x in (jload(hb).get("workflows") if hb else []) if x.get("id") == i["wid"]), {})
        pub = dict(i, old_name=w.get("short") or i["old_name"], old_category=w.get("category") or i["old_category"])
        do_workflow(pub, defs)
        code, so, se = py(H, "save", "--via", "renamer", "--message", "Renamed: " + line(i), "--only", old,
                          "--only", new, "--note", f"{new}=Renamed: {line(i)}")
        if code:
            raise Stop("saving the renamed version failed: " + (se or so).strip()[-200:])
        # the draft, back on top under the new name
        shutil.rmtree(os.path.join(SKILLS, new))
        shutil.copytree(os.path.join(stash, "skill"), os.path.join(SKILLS, new))
        nbf = os.path.join(paths.BOARD_DEFS, new + ".json")
        if os.path.isfile(os.path.join(stash, "board.json")):   # a repair's board is already renamed: as it was
            t = rd(os.path.join(stash, "board.json"))
            wr(nbf, word(old).sub(new, t) if now_at == "old" else t)
        if now_at == "old":   # its own files still say the old name: the same edits the published copy had
            for root, _d, files in os.walk(os.path.join(SKILLS, new)):
                for f in files:
                    p = os.path.join(root, f)
                    try:
                        t = rd(p)
                    except (UnicodeDecodeError, OSError):
                        continue
                    if word(old).search(t):
                        wr(p, word(old).sub(new, t))
            edit_board(nbf, i)
            fix_heading(i)
        for f in keep:
            dst = sh._iter_path(new) if f == sh._iter_path(here) else os.path.join(sh.PENDING_DIR, new + ".json")
            src = os.path.join(stash, os.path.basename(os.path.dirname(f)) + "-" + os.path.basename(f))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            wr(dst, word(old).sub(new, rd(src)))
        fix_iterations(i)
        return [new]
    finally:
        shutil.rmtree(stash, ignore_errors=True)


def do_connection(i):
    old, new = i["old_id"], i["new_id"]
    folder = os.path.join(SKILLS, "connection-" + old)
    touched = ["connection-" + old]
    md = os.path.join(folder, "SKILL.md")
    t = rd(md)
    if i["new_name"] != i["old_name"]:
        t = re.sub(r"(?m)^system:\s*.+$", "system: " + i["new_name"], t, count=1)
        t = re.sub(r"(?m)^# " + re.escape(i["old_name"]) + r" connection\s*$", f"# {i['new_name']} connection", t, count=1)
    wr(md, t)
    if new != old:
        nf = os.path.join(SKILLS, "connection-" + new)
        os.rename(folder, nf)
        md = os.path.join(nf, "SKILL.md")
        wr(md, re.sub(r"(?m)^name:\s*connection-" + re.escape(old) + r"\s*$", "name: connection-" + new, rd(md), count=1))
        touched.append("connection-" + new)
        for sk in i["used_by"]:   # each `uses:` line that names it, and any step that names its skill
            f = os.path.join(SKILLS, sk, "SKILL.md")
            s = rd(f)
            s = re.sub(r"(?ms)(^uses:\s*\n(?:  .*\n)*?)  " + re.escape(old) + r":", r"\1  " + new + ":", s, count=1)
            wr(f, word("connection-" + old).sub("connection-" + new, s))
            touched.append(sk)
        for bf in board_store.user_files().values():
            s = rd(bf)
            if word("connection-" + old).search(s):
                wr(bf, word("connection-" + old).sub("connection-" + new, s))
        st = os.path.join(paths.CONNECTIONS, old + ".json")
        if os.path.isfile(st):
            d = jload(st)
            d["name"] = new
            jsave(os.path.join(paths.CONNECTIONS, new + ".json"), d)
            os.remove(st)
        it = os.path.join(paths.HISTORY, "iterations", f"connection-{old}.json")
        if os.path.isfile(it):
            os.rename(it, os.path.join(paths.HISTORY, "iterations", f"connection-{new}.json"))
    return touched


def add_category(cat, meaning):
    f = paths.USER_CATEGORIES or paths.ORG_CATEGORIES
    if cat in paths.categories():
        return
    t = rd(f) if os.path.isfile(f) else ("# Categories (this folder's own)\n\nThe areas of this folder's own workflows, "
                                         "read together with the plugin's list (rule 10).\n\n| Category | What belongs "
                                         "here |\n|---|---|\n")
    wr(f, t.rstrip("\n") + f"\n| `{cat}` | {meaning} |\n")


def do_category(i):
    """the category list's own row: renamed, or dropped once nothing is left in it"""
    f = paths.USER_CATEGORIES
    if not f or not os.path.isfile(f):
        return
    t = rd(f)
    row = re.compile(r"(?m)^\| `" + re.escape(i["old"]) + r"` \| (.*?) \|\s*\n?")
    m = row.search(t)
    if not m:
        return
    if i["new"] in paths.categories():
        t = row.sub("", t, count=1)
    else:
        t = row.sub(f"| `{i['new']}` | {i.get('meaning') or m.group(1)} |\n", t, count=1)
    wr(f, t)


def cmd_apply():
    if not os.path.isfile(PLAN):
        raise Stop("no rename plan: make one first (rename.py workflow|connection|category|pattern|list …)")
    p = jload(PLAN)
    # a category's own row first, so the workflows moved into it find it already named and described
    items = sorted((i for i in p["items"] if not i.get("problems")), key=lambda i: i["kind"] != "category")
    if not items:
        raise Stop("nothing in the plan can be renamed: " + "; ".join(sum((i["problems"] for i in p["items"]), [])))
    before = drafts()
    defs = board_store.load_all()
    done, save, saved_first = [], {}, []
    for i in items:
        if i["kind"] == "workflow" and i.get("has_draft"):
            first = published_first(i, defs)
            if first is not None:
                done.append(line(i))
                saved_first += first   # its published version renamed and saved; its draft stays a draft
                continue
            sks = do_workflow(i, defs)
            fix_iterations(i)
        elif i["kind"] == "workflow":
            sks = do_workflow(i, defs)
            fix_iterations(i)
        elif i["kind"] == "connection":
            sks = do_connection(i)
        else:
            do_category(i)
            done.append(line(i))
            continue
        done.append(line(i))
        for sk in sks:   # a skill with a draft not yet published is renamed, never saved: that would publish the draft
            if not i.get("has_draft") and sk not in before:
                save.setdefault(sk, line(i))
    code, so, se = py(os.path.join(HERE, "build_workflows.py"))
    errs = [ln[6:] for ln in (so + se).splitlines() if ln.startswith("ERROR ")]
    saved = []
    if save and not errs:
        args = [H, "save", "--via", "renamer", "--message", "Renamed: " + "; ".join(done)[:300]]
        for sk, note in save.items():
            args += ["--only", sk]
            if os.path.isdir(os.path.join(SKILLS, sk)):
                args += ["--note", f"{sk}=Renamed: {note}"]
        c, so2, se2 = py(*args)
        saved = sorted(s for s in save if os.path.isdir(os.path.join(SKILLS, s)))
        if c:
            errs.append("saving the version failed: " + (se2 or so2).strip()[-200:])
        py(os.path.join(HERE, "build_workflows.py"))
    os.remove(PLAN)
    return {"renamed": done, "saved_as_versions": sorted(set(saved) | set(saved_first)),
            "kept_as_drafts": sorted({i.get("new_skill") or "connection-" + i.get("new_id", "")
                                      for i in items if i.get("has_draft")}),
            "skipped": {line(i): i["problems"] for i in p["items"] if i.get("problems")},
            "schedules_to_update": schedules_naming([i for i in items if i["kind"] == "workflow"]),
            "build": "clean" if not errs else "errors", "errors": errs}


def cmd_repair(new):
    """A workflow renamed (before 0.13.5) while it had a draft: its published version is still saved only under the
    old name, so the board shows it as never published. Renames that version and saves it, keeping the draft."""
    old = next((o for o, n in sh.aliases().items() if n == new and sh.tree_of("HEAD", f"{sh.SKILLS_REL}/{o}")), None)
    if not old or sh.tree_of("HEAD", f"{sh.SKILLS_REL}/{new}"):
        return {"repaired": False, "why": f"{new} needs no repair"}
    defs = board_store.load_all()
    w = next((x for x in workflows(defs) if x["match"]["skill"] == new), None)
    if not w:
        raise Stop(f"no workflow {new} on the board")
    cat = w.get("category")
    i = {"kind": "workflow", "wid": w.get("id"), "old_skill": old, "new_skill": new, "old_name": w.get("short"),
         "new_name": w.get("short"), "old_category": cat, "new_category": cat,
         "new_category_label": cat_label(cat, defs), "category_is_new": False, "problems": []}
    first = published_first(i, defs, now_at="new")
    code, so, se = py(os.path.join(HERE, "build_workflows.py"))
    errs = [ln[6:] for ln in (so + se).splitlines() if ln.startswith("ERROR ")]
    return {"repaired": bool(first), "from": old, "saved": first or [], "build": "clean" if not errs else "errors",
            "errors": errs}


def schedules_naming(items):
    """scheduled runs whose prompt names an old workflow name: their task prompt has to be set again"""
    f = paths.SCHEDULES
    if not items or not os.path.isfile(f):
        return []
    t = rd(f)
    return [i["new_skill"] for i in items if i["old_skill"] in t or i["old_skill"][len("workflow-"):] in t]


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("workflow")
    w.add_argument("name"), w.add_argument("--name", dest="new"), w.add_argument("--category"), w.add_argument("--skill")
    c = sub.add_parser("connection")
    c.add_argument("name"), c.add_argument("--name", dest="new"), c.add_argument("--id")
    g = sub.add_parser("category")
    g.add_argument("cat"), g.add_argument("--to", required=True), g.add_argument("--label"), g.add_argument("--meaning")
    pt = sub.add_parser("pattern")
    pt.add_argument("find"), pt.add_argument("replace"), pt.add_argument("--category")
    ls = sub.add_parser("list")
    ls.add_argument("file")
    sub.add_parser("apply")
    fl = sub.add_parser("fix-log")
    fl.add_argument("skill"), fl.add_argument("--old", required=True), fl.add_argument("--old-name", required=True)
    fl.add_argument("--old-category", required=True)
    rp = sub.add_parser("repair")
    rp.add_argument("skill")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "apply":
            out(cmd_apply())
        if a.cmd == "fix-log":
            defs = board_store.load_all()
            w = next(x for x in workflows(defs) if x["match"]["skill"] == a.skill)
            fix_iterations({"old_skill": a.old, "new_skill": a.skill, "wid": w["id"], "old_name": a.old_name,
                            "new_name": w["short"], "new_category": w["category"],
                            "new_category_label": cat_label(w["category"], defs)})
            out({"fixed": a.skill, "iterations": len(sh.iter_log(a.skill).get("items") or [])})
        if a.cmd == "repair":
            out(cmd_repair(a.skill))
        defs = board_store.load_all()
        if a.cmd == "workflow":
            if not (a.new or a.category or a.skill):
                raise Stop("say what changes: --name, --category or both")
            out(plan([wf_item(find_workflow(a.name, defs), defs, a.new, a.category, a.skill)]))
        if a.cmd == "connection":
            if not (a.new or a.id):
                raise Stop("say what changes: --name, --id or both")
            out(plan([conn_item(a.name, a.new, a.id)]))
        if a.cmd == "category":
            to = slug(a.to).replace("-", "")
            if a.label:
                defs.setdefault("categories", {}).setdefault(to, {})["name"] = a.label
            its = [wf_item(w, defs, cat=to) for w in workflows(defs) if w.get("category") == a.cat]
            for i in its:
                i["new_category_label"] = a.label or i["new_category_label"]
            if not its:
                raise Stop(f"no workflows of yours in the category {a.cat!r}")
            own = set(re.findall(r"(?m)^\| `([a-z0-9]+)` \|", rd(paths.USER_CATEGORIES))) \
                if paths.USER_CATEGORIES and os.path.isfile(paths.USER_CATEGORIES) else set()
            # the folder's own category: its row is renamed (or dropped when merged); the plugin's stays as it is
            extra = [{"kind": "category", "old": a.cat, "new": to, "meaning": a.meaning, "problems": []}] \
                if a.cat in own else []
            out(plan(its, extra))
        if a.cmd == "pattern":
            rx = re.compile(re.escape(a.find), re.I)
            its = []
            for w in workflows(defs):
                if a.category and w.get("category") != a.category:
                    continue
                if rx.search(w.get("short") or ""):
                    new = re.sub(r"\s{2,}", " ", rx.sub(a.replace, w["short"])).strip()
                    its.append(wf_item(w, defs, name=new))
            if not its:
                raise Stop(f"no workflow name contains {a.find!r}")
            out(plan(its))
        if a.cmd == "list":
            its = []
            for x in jload(a.file):
                if x.get("connection"):
                    its.append(conn_item(x["connection"], x.get("name"), x.get("id")))
                else:
                    its.append(wf_item(find_workflow(x["workflow"], defs), defs, x.get("name"), x.get("category"), x.get("skill")))
            out(plan(its))
    except Stop as e:
        out({"error": str(e)}, 1)


if __name__ == "__main__":
    main(sys.argv[1:])
