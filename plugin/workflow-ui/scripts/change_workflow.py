#!/usr/bin/env python3
"""Change a published workflow through one editable file, so Claude edits the design and the script writes the
plumbing (core-architect Change mode). The same idea as new_workflow.py create, run both ways.

    change_workflow.py open <skill>
        Reads the skill's SKILL.md and its board definition and writes them as one change file,
        <live>/change-<workflow id>.json (shape below). Marks the page "Claude is updating it". Prints the file's path.

    change_workflow.py apply <skill> --note TEXT --summary TEXT [--details FILE] [--check]
        Writes the change file back: SKILL.md (sections in their order, unknown sections kept word for word), the
        board workflow with its derived fields (lane, why, from, sk) worked out again, its summary, examples and
        results, the README row from the description, and test cases on a renamed path. Then one draft iteration
        (skill_history.py checkpoint, with --note, --summary and --details) and the board build. The change file is
        deleted once it is applied. --check writes nothing and prints the diff it would make.

Prints one JSON object: what it did, or {"error": ...} with what to fix. Changes nothing outside the project.

Only workflows laid out with one "## Steps" section of "**Step N: <title>.**" paragraphs, each a board step of the
same title, and no code steps (flow.py). Anything else is edited by hand, as before; `open` says so.

The change file:
    {"skill", "workflow",
     "description", "title", "plain",                      SKILL.md front matter, heading, In plain words
     "definition": "<the yaml>", "definition_after": "...", the Definition block and the lines under it
     "picture": "<the ASCII picture>",                     kept as written; "auto" draws it again from the steps
     "steps_intro": "...", "steps": [{<board step without lane/why/from/sk>, "text": "<the step's prose>"}],
     "sections": {"<name>": "<body>"}, "order": [...],     every other section (Trigger, Report, …), word for word
     "board": {<the board workflow's other fields: short, name, desc, simulated, stages, …>},
     "summary", "trigger_summary", "examples", "results",  the page's lines (workflows.json summaries, examples, results)
     "noun": "<what one item is>",                         read only: the trigger's, for an "auto" picture
     "renamed_paths": {"<old label>": "<new label>"}}       optional: a path renamed, so its test cases follow
"""
import argparse
import difflib
import glob
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402
from new_workflow import DEFS, SKILLS, Stop, build, load, out, picture, run, save_json, why  # noqa: E402
import board_store  # noqa: E402

DERIVED = ("lane", "why")   # worked out from the step's place and title; "from" and "sk" stay as each step has them
OWN = ("In plain words", "Definition", "How it works", "Steps")
HEAD = re.compile(r"^\*\*Step (\d+): (.+?)\*\*[ \t]*", re.M)


def change_path(wid):
    return os.path.join(paths.LIVE, f"change-{wid}.json")


def read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()


def sections(md):
    """(front matter dict, title, [(section name, body)]) of a SKILL.md."""
    m = re.match(r"^---\n(.*?)\n---\n", md, re.S)
    if not m:
        raise Stop("SKILL.md has no front matter")
    fm = dict(re.findall(r"^(\w+):\s*(.*)$", m.group(1), re.M))
    rest = md[m.end():]
    t = re.search(r"^# (.+)$", rest, re.M)
    if not t:
        raise Stop("SKILL.md has no # title")
    parts = re.split(r"^## (.+)$", rest[t.end():], flags=re.M)
    return fm, t.group(1).strip(), [(parts[i].strip(), parts[i + 1].strip("\n")) for i in range(1, len(parts), 2)]


def heading_title(t):
    return t.rstrip()[:-1] if t.rstrip().endswith(".") else t.rstrip()


def find_workflow(defs, skill):
    w = next((x for x in defs["workflows"] if (x.get("match") or {}).get("skill") == skill), None)
    if not w:
        raise Stop(f"no board workflow for {skill}: edit it by hand (Change mode)")
    return w


def cmd_open(skill):
    folder = os.path.join(SKILLS, skill)
    md = read(os.path.join(folder, "SKILL.md"))
    if os.path.exists(os.path.join(folder, "flow.py")) or glob.glob(os.path.join(folder, "**", "*.py"), recursive=True):
        raise Stop(f"{skill} has code steps: edit it by hand (Change mode)")
    fm, title, secs = sections(md)
    names = [n for n, _ in secs]
    if "Steps" not in names or any(n.startswith("Step ") for n in names):
        raise Stop(f"{skill} isn't laid out as one \"## Steps\" section: edit it by hand (Change mode)")
    body = dict(secs)
    dm = re.match(r"^\s*```yaml\n(.*?)\n```\n?(.*)$", body.get("Definition", ""), re.S)
    pm = re.match(r"^\s*```\n(.*?)\n```\s*$", body.get("How it works", ""), re.S)
    if not dm or not pm:
        raise Stop(f"{skill}: its Definition or How it works isn't one fenced block: edit it by hand")
    st_body = body["Steps"]
    heads = list(HEAD.finditer(st_body))
    if not heads:
        raise Stop(f"{skill}: no \"**Step N: …**\" paragraphs under Steps: edit it by hand")
    texts = []
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(st_body)
        texts.append((heading_title(h.group(2)), st_body[h.end():end].strip()))
    defs = board_store.load_all()
    w = find_workflow(defs, skill)
    bsteps = w.get("steps") or []
    if [s.get("title") for s in bsteps] != [t for t, _ in texts]:
        raise Stop(f"{skill}: its board steps and its \"Step N\" headings differ ("
                   f"{[s.get('title') for s in bsteps]} vs {[t for t, _ in texts]}); fix that by hand first")
    if any(s.get("sub") or s.get("code") for s in bsteps):
        raise Stop(f"{skill} has code steps on the board: edit it by hand (Change mode)")
    steps = [dict({k: v for k, v in s.items() if k not in DERIVED}, text=t) for s, (_, t) in zip(bsteps, texts)]
    wid = w["id"]
    tid = (w.get("entries") or [None])[0]
    ch = {"skill": skill, "workflow": wid,
          "description": fm.get("description", ""), "title": title, "plain": body.get("In plain words", "").strip(),
          "definition": dm.group(1), "definition_after": dm.group(2).strip(),
          "picture": pm.group(1),
          "steps_intro": st_body[:heads[0].start()].strip(), "steps": steps,
          "sections": {n: b for n, b in secs if n not in OWN}, "order": names,
          "board": {k: v for k, v in w.items() if k not in ("id", "match", "entries", "steps")},
          "summary": (defs.get("summaries") or {}).get("workflow:" + wid),
          "trigger_summary": (defs.get("summaries") or {}).get("trigger:" + tid) if tid else None,
          "examples": (defs.get("examples") or {}).get("workflow:" + wid),
          "results": (defs.get("results") or {}).get("workflow:" + wid),
          "noun": ((defs.get("entries") or {}).get(tid) or {}).get("noun") if tid else None,
          "renamed_paths": {}}
    os.makedirs(paths.LIVE, exist_ok=True)
    p = change_path(wid)
    save_json(p, ch)
    # the "before" view, so apply can tell whether the steps changed under an unchanged picture
    save_json(p + ".orig", {"picture": ch["picture"], "shape": shape(steps)})
    run(os.path.join(HERE, "skill_history.py"), "updating", skill, "changing it")
    return {"opened": p, "workflow": wid, "steps": [s["title"] for s in steps],
            "paths": [x.get("label") for x in ch["board"].get("simulated") or []],
            "next": "edit that file, then: change_workflow.py apply " + skill + " --note … --summary … --details …"}


def shape(steps):
    # lists only, so it compares equal to its own copy read back from JSON
    return json.loads(json.dumps([[s.get("title"), s.get("type"),
                                   [[a.get("when"), bool(a.get("ends"))] for a in s.get("alts") or []], s.get("on")]
                                  for s in steps]))


def render(ch, steps):
    pic = ch["picture"]
    if str(pic).strip() == "auto":
        tr = None   # the picture's trigger lines come from the Definition
        y = ch["definition"]
        sm = re.search(r"^starts on:\n\s+- (.+)$", y, re.M)
        rd = re.search(r"^reads:\s*(.+)$", y, re.M)
        if sm and rd:
            tr = {"starts_on": [sm.group(1).strip()], "reads": rd.group(1),
                  "noun": ch.get("noun") or "item"}
        pic = picture(tr, steps, (ch.get("board") or {}).get("loops") or [])   # a loop workflow draws its loops
    long = [ln for ln in pic.splitlines() if len(ln) > 75]
    if long:
        raise Stop(f"the picture has lines over 75 characters (rule 12): {long[0]!r}")
    own = {"In plain words": ch["plain"],
           "Definition": "```yaml\n" + ch["definition"].strip("\n") + "\n```" + ("\n" + ch["definition_after"] if ch["definition_after"] else ""),
           "How it works": "```\n" + pic.strip("\n") + "\n```",
           "Steps": "\n\n".join(([ch["steps_intro"]] if ch["steps_intro"] else []) + [
               f"**Step {i}: {s['title'].rstrip()}{'' if s['title'].rstrip()[-1:] in '?.!' else '.'}** {s['text'].strip()}"
               for i, s in enumerate(steps, 1)])}
    order = list(ch["order"]) + [n for n in ch["sections"] if n not in ch["order"]]
    body = []
    for n in order:
        if n in own:
            body.append(f"## {n}\n{own[n].strip()}\n")
        elif n in ch["sections"]:
            body.append(f"## {n}\n{ch['sections'][n].strip()}\n")
    desc = " ".join(str(ch["description"]).split())
    return f"---\nname: {ch['skill']}\ndescription: {desc}\n---\n\n# {ch['title']}\n\n" + "\n".join(body)


def validate(ch, steps):
    titles = [s.get("title") for s in steps]
    dup = sorted({t for t in titles if titles.count(t) > 1})
    if dup:
        raise Stop(f"two steps share a title (rule 32): {dup[0]!r}")
    keys = [s.get("key") for s in steps]
    if None in keys or len(set(keys)) != len(keys):
        raise Stop("every step needs its own \"key\"")
    for i, s in enumerate(steps, 1):
        if not str(s.get("text") or "").strip():
            raise Stop(f"step {i} ({s.get('title')!r}) needs its prose in \"text\"")
        for k in ("what", "tip"):
            if not s.get(k):
                raise Stop(f"step {i} ({s.get('title')!r}) needs \"{k}\" (rule 23)")
        on = s.get("on") or {}
        if on and on.get("step") not in keys:
            raise Stop(f"step {i} ({s.get('title')!r}) runs \"on\" a step that is gone: {on.get('step')!r}")
    labels = {p.get("label") for p in ch["board"].get("simulated") or []}
    if not labels:
        raise Stop("board.simulated needs at least one path")
    for p in ch["board"]["simulated"]:
        bad = [k for k in list(p.get("res") or {}) + list(p.get("taken") or {}) if k not in keys]
        if bad:
            raise Stop(f"path {p.get('label')!r} names a step that is gone: {bad[0]!r}")
    for x in ch.get("examples") or []:
        if x.get("path") not in labels:
            raise Stop(f"example {x.get('title')!r} names path {x.get('path')!r}, which is not one of board.simulated")
    missing = sorted(l for l in labels if l not in (ch.get("results") or {}))
    if missing:
        raise Stop("results needs every path's outcome; missing: " + ", ".join(missing))
    extra = sorted(l for l in (ch.get("results") or {}) if l not in labels)
    if extra:
        raise Stop("results names a path that is gone: " + ", ".join(extra))


def cmd_apply(a):
    defs = board_store.load_all()
    w = find_workflow(defs, a.skill)
    wid = w["id"]
    p = change_path(wid)
    try:
        ch = load(p)
    except (OSError, ValueError) as e:
        raise Stop(f"no change file to apply ({e}): run change_workflow.py open {a.skill} first")
    steps = ch["steps"]
    validate(ch, steps)
    try:
        orig = load(p + ".orig")
    except (OSError, ValueError):
        orig = {}
    if orig and shape(steps) != orig.get("shape") and ch["picture"] == orig.get("picture"):
        raise Stop("the steps or their options changed but the picture didn't (rule 12): edit \"picture\", "
                   "or set it to \"auto\" to draw it again from the steps")
    folder = os.path.join(SKILLS, a.skill)
    md_path = os.path.join(folder, "SKILL.md")
    new_md = render(ch, steps)

    # the board workflow, its derived fields worked out again
    old = {x.get("key"): x for x in w.get("steps") or []}
    bsteps = []
    for i, s in enumerate(steps, 1):
        was = old.get(s["key"]) or {}
        b = {k: None for k in was}            # an existing step keeps its key order
        b.update({k: v for k, v in s.items() if k not in ("text",) + DERIVED})
        if b.get("sk") is None:
            b["sk"] = a.skill
        # its lane: a hand-named one ("Write: dm") stays; a numbered one follows the step's place
        b["lane"] = was["lane"] if was.get("lane") and not re.match(r"^Step \d+$", was["lane"]) else f"Step {i}"
        label = f"Step {i}: {s['title']}"
        wy = json.loads(json.dumps(was.get("why") or {}))
        # its Why? summary: kept while its "what" is unchanged (older ones were written by hand), else the new "what"
        summ = wy.get("sum") if wy.get("sum") and was.get("what") == s.get("what") else s.get("what", "")
        if wy.get("parts"):
            # the quoted parts stay (a table under the step, say); only its own "Step N: <title>" line follows it
            old_label = wy.get("label")
            for part in wy["parts"]:
                part["pick"] = [label if (x == old_label or re.match(r"^Step \d+: ", str(x))) else x
                                for x in part.get("pick") or []]
            wy.update(file=a.skill, label=label, sum=summ)
            b["why"] = wy
        else:
            b["why"] = why(a.skill, label, summ)
        b.setdefault("from", {"key": s["key"]})   # a new step is matched by its key (rule 32)
        if b.get("from") is None:
            b["from"] = {"key": s["key"]}
        bsteps.append({k: v for k, v in b.items() if v is not None or k in s})
    nw = {"id": wid}
    for k, v in w.items():          # keep the board's key order: replace in place, add new keys at the end
        if k == "id":
            continue
        nw[k] = bsteps if k == "steps" else w[k] if k in ("match", "entries") else ch["board"].get(k, v)
    for k, v in ch["board"].items():
        nw.setdefault(k, v)
    for k in [k for k in nw if k not in ch["board"] and k not in ("id", "match", "entries", "steps")]:
        nw.pop(k)                   # a field taken out of board is taken off the board
    new_defs = json.loads(json.dumps(defs))
    new_defs["workflows"] = [nw if x is w else x for x in defs["workflows"]]
    for key, val in (("summaries", ch.get("summary")), ("examples", ch.get("examples")), ("results", ch.get("results"))):
        if val is not None:
            new_defs.setdefault(key, {})["workflow:" + wid] = val
    tid = (w.get("entries") or [None])[0]
    if tid and ch.get("trigger_summary"):
        new_defs.setdefault("summaries", {})["trigger:" + tid] = ch["trigger_summary"]

    # the README row, from the description
    readme = os.path.join(paths.PROJECT, "README.md")
    rd = read(readme) if os.path.exists(readme) else ""
    desc = " ".join(str(ch["description"]).split())
    new_rd = re.sub(rf"^(\| `{re.escape(a.skill)}` \| [^|]+ \| ).*?( \|)$", lambda m: m.group(1) + desc + m.group(2), rd, flags=re.M)

    # test cases on a renamed path follow it
    ren = ch.get("renamed_paths") or {}
    tests = {}
    for f in glob.glob(os.path.join(folder, "tests", "*.json")):
        try:
            t = load(f)
        except (OSError, ValueError):
            continue
        if t.get("path") in ren:
            t["path"] = ren[t["path"]]
            tests[f] = t
    labels = {x.get("label") for x in nw.get("simulated") or []}
    stale = []
    for f in glob.glob(os.path.join(folder, "tests", "*.json")):
        t = tests.get(f) or (load(f) if f not in tests else {})
        if t.get("path") and t["path"] not in labels:
            stale.append(os.path.basename(f))

    if a.check:
        old_md = read(md_path)
        d = list(difflib.unified_diff(old_md.splitlines(), new_md.splitlines(), "SKILL.md", "SKILL.md (new)", lineterm="", n=1))
        bd = list(difflib.unified_diff(json.dumps(w, indent=2, ensure_ascii=False).splitlines(),
                                       json.dumps(nw, indent=2, ensure_ascii=False).splitlines(),
                                       "board", "board (new)", lineterm="", n=0))
        return {"check": True, "skill_diff": d, "board_diff": bd, "readme_changes": rd != new_rd,
                "tests_moved": [os.path.basename(f) for f in tests], "tests_on_a_gone_path": stale}

    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(new_md)
    board_store.save_all(new_defs)
    if rd != new_rd:
        with open(readme, "w", encoding="utf-8") as fh:
            fh.write(new_rd)
    for f, t in tests.items():
        save_json(f, t)
    cp = [os.path.join(HERE, "skill_history.py"), "checkpoint", a.skill, "--note", a.note, "--summary", a.summary]
    if a.details:
        cp += ["--details", a.details]
    code, so, se = run(*cp)
    ok, errs = build()
    for f in (p, p + ".orig"):
        try:
            os.remove(f)
        except OSError:
            pass
    return {"applied": a.skill, "workflow": wid, "steps": [s["title"] for s in steps],
            "iteration": (json.loads(so).get("iteration") if code == 0 and so.strip().startswith("{") else None),
            "checkpoint": "ok" if code == 0 else (se or so).strip()[-300:],
            "build": "clean" if ok else "errors", "errors": errs,
            "tests_moved": [os.path.basename(f) for f in tests], "tests_on_a_gone_path": stale,
            "page": f"workflow-viewer.html?w={wid}"}


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("open")
    o.add_argument("skill")
    p = sub.add_parser("apply")
    p.add_argument("skill")
    p.add_argument("--note")
    p.add_argument("--summary")
    p.add_argument("--details")
    p.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "open":
            out(cmd_open(a.skill))
        if not a.check and not (a.note and a.summary):
            raise Stop("apply needs --note (this change, in the user's words) and --summary (how the whole draft "
                       "now differs from the published version)")
        out(cmd_apply(a))
    except (Stop, board_store.Refused) as e:
        out({"error": str(e)}, 1)


if __name__ == "__main__":
    main(sys.argv[1:])
