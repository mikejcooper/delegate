#!/usr/bin/env python3
"""Build workflows-data.js for the Workflow Viewer (workflow-viewer.html).

Reads the hand-written definitions in workflows.json and fills each step's "Why?" with the rule text
quoted from the skill file it points at (.claude/skills/<file>/SKILL.md). A part names a section by
its "## " heading and, optionally, "pick": substrings of the lines (in a list or table) or paragraphs
to quote. A section or pick that can't be found marks the step "missing", so the page can say the
skill changed instead of showing stale text. Real examples come from board-data.js on the page itself.

It also checks the definitions (see check() and README.md next to workflows.json). The page data is
still written so the board stays live, but any problem is printed as an ERROR and the exit code is 1.

    python3 -I .claude/workflow-ui/scripts/build_workflows.py
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402  where code and data live (in-project or plugin)
import entries  # noqa: E402  triggers and skill folders in both layers
import codeflow  # noqa: E402  workflows written as code: drawn from their @step / @decision markers
BOARD = paths.CODE
SKILLS = paths.SKILLS
DEFS = os.path.join(BOARD, "workflows.json")
OUT = paths.WORKFLOWS_JS


def sections(path):
    """{heading: [lines]} for every '## ' section of a SKILL.md."""
    out, cur = {}, None
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith("## "):
            cur = line[3:].strip()
            out[cur] = []
        elif cur is not None:
            out[cur].append(line)
    return out


def plain(text):
    return text.replace("**", "").replace("`", "")


def blocks(lines):
    """Split a section into blocks separated by blank lines."""
    out, cur = [], []
    for line in lines:
        if line.strip():
            cur.append(line)
        elif cur:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return out


ITEM = re.compile(r"(\||- |\d+\. )")


def units(block):
    """Pickable pieces of a block: each list item or table row on its own (with its indented continuation
    lines); a run of plain lines is one paragraph, which carries the list straight after it ("intro + list")."""
    out = []
    for line in block:
        if ITEM.match(line):
            out.append({"lines": [line], "item": True})
        elif line.startswith((" ", "\t")) and out and out[-1]["item"]:
            out[-1]["lines"].append(line)
        elif out and not out[-1]["item"]:
            out[-1]["lines"].append(line)
        else:
            out.append({"lines": [line], "item": False})
    return out


def quote(secs, part):
    """Return (text, found) for one part."""
    lines = secs.get(part["section"])
    if lines is None:
        return "", False
    picks = part.get("pick")
    if not picks:
        return "\n".join(plain(l) for l in lines).strip(), True
    got, hit = [], set()
    for block in blocks(lines):
        us = units(block)
        take = set()
        for i, u in enumerate(us):
            text = "\n".join(u["lines"])
            found = [p for p in picks if p in plain(text) or p in text]
            if not found:
                continue
            hit.update(found)
            take.add(i)
            if not u["item"]:  # a picked paragraph brings the list that follows it
                j = i + 1
                while j < len(us) and us[j]["item"]:
                    take.add(j)
                    j += 1
        for i in sorted(take):
            got.extend(us[i]["lines"])
    # a pick that only matches table plumbing (header / rule rows) is not a real hit
    real = [p for p in picks if not p.startswith("|")]
    ok = bool(got) and all(p in hit for p in real)
    return "\n".join(plain(l) for l in got).strip(), ok


def fill(step, cache):
    why = step.get("why")
    if not why or why.get("code") or why.get("draft"):   # code and draft steps carry their own rule text
        return
    path = entries.skill_file(why["file"])[1] or os.path.join(SKILLS, why["file"], "SKILL.md")
    if why.get("ref"):   # a section kept in one of the skill's reference files ("references/one-item.md")
        path = os.path.join(os.path.dirname(path), why["ref"])
    if path not in cache:
        cache[path] = sections(path)
    secs = cache[path]
    texts, ok = [], secs is not None
    for part in why.get("parts", []):
        if secs is None:
            break
        text, found = quote(secs, part)
        ok = ok and found
        if text:
            texts.append("## " + part["section"] + "\n" + text)
    why["rule"] = "\n\n".join(texts)
    why["missing"] = not ok


SHORT_MAX = 32   # characters that fit one sidebar line


def layout(defs):
    """Rule 24 (the architect's rules.md): one row per workflow skill, its branches as paths. Returns ERROR strings;
    prints WARN lines for what doesn't block the build."""
    errs, cats, by_skill = [], defs.get("categories", {}), {}
    def skill_of(w):
        return (w.get("match") or {}).get("skill") or cats.get(w.get("category"), {}).get("skill") or w.get("skill") or ""
    for w in defs["workflows"]:
        if w.get("parent") or w.get("draft"):
            continue   # a workflow's own code (drawn under it) and drafts aren't rows of their own
        by_skill.setdefault(skill_of(w), []).append(w)
        if len(w.get("short") or "") > SHORT_MAX:
            print(f"WARN {w['id']}: short name \"{w['short']}\" is over {SHORT_MAX} characters, so the sidebar cuts it (rule 24)")
    for sk, ws in by_skill.items():
        if sk.startswith("workflow-") and len(ws) > 1:
            errs.append(f"layout {sk}: {len(ws)} board entries ({', '.join(w['id'] for w in ws)}); a workflow skill is one row "
                        "with its branches as decision options and paths (rule 24)")
    for k, c in cats.items():
        if not c.get("parent"):
            continue
        sk = c.get("skill") or ""
        if sk.startswith("workflow-"):
            errs.append(f"layout category {k}: a sub-folder for the workflow skill {sk}; workflow skills sit straight under their area (rule 24)")
        elif sk and len(by_skill.get(sk, [])) < 2:
            print(f"WARN category {k}: a mode heading for {sk}, which has {len(by_skill.get(sk, []))} row(s) on the board (rule 24: headings are for skills with several modes)")
    return errs


def check(defs):
    """Structural rules the page relies on. Returns a list of 'workflow:step: problem' strings."""
    errs = []
    cats = defs.get("categories", {})
    secs = [x["key"] for x in defs.get("sections", [])]
    # sidebar: every category sits in a section, directly or through its parent; parents exist, no loops
    for k, c in cats.items():
        seen, cur = [], k
        while cur in cats and cur not in seen:
            seen.append(cur)
            cur = cats[cur].get("parent")
        if cur in seen:
            errs.append(f"category {k}: its parents loop ({' > '.join(seen)})")
        elif cur is not None:
            errs.append(f"category {k}: parent {cur!r} is not a category")
        elif cats[seen[-1]].get("section") not in secs:
            errs.append(f"category {seen[-1]}: needs a 'section', one of {', '.join(secs)}")
    def section_of(k):
        seen = []
        while k in cats and cats[k].get("parent") and k not in seen:
            seen.append(k)
            k = cats[k]["parent"]
        return cats.get(k, {}).get("section")
    # entry tags: workflows the dispatcher starts name their triggers; each one is a row of its table
    real = {e["id"] for e in entries.load()}
    for k in defs.get("entries", {}):
        if k not in real:
            errs.append(f"entries.{k}: not a trigger id (no workflow's Definition has `trigger: {k}`, and no trigger skill has it)")
    for w in defs["workflows"]:
        ents = w.get("entries", [])
        if section_of(w.get("category")) == "workflows" and not ents and not w.get("direct"):
            errs.append(f"{w['id']}: list the triggers that start it in \"entries\"")
        for k in ents:
            if k not in defs.get("entries", {}):
                errs.append(f"{w['id']}: entry {k!r} is not in the top-level \"entries\" (name and icon)")
    flows = [dict(defs["dispatcher"], id="dispatcher")] + defs["workflows"]
    for w in flows:
        wid, steps = w["id"], w["steps"]
        if wid != "dispatcher" and (w.get("category") not in cats or not w.get("short")):
            errs.append(f"{wid}: needs a 'category' (a key of categories) and a 'short' name")
        keys = [st["key"] for st in steps]
        forks = {st["key"]: st for st in steps if len(st.get("alts", [])) >= 2}   # steps with options
        # 1. a step with options, followed by more steps, must say which steps belong to which option:
        #    "on" on the later steps, "ends": true on options that stop the flow, or "continues": "all"
        for i, st in enumerate(steps):
            if st["key"] in forks and i < len(steps) - 1 and st.get("continues") != "all":
                open_alts = [a for a in st["alts"] if not a.get("ends")]
                if len(open_alts) > 1 and not any((x.get("on") or {}).get("step") == st["key"] for x in steps[i + 1:]):
                    errs.append(f"{wid}:{st['key']}: {len(open_alts)} options carry on, but no later step says which "
                                f"option it belongs to. Add \"on\": {{\"step\": \"{st['key']}\", \"alt\": n}} to them, "
                                "\"ends\": true to options that stop, or \"continues\": \"all\" if every option runs the same steps")
        # 2. 'on' must point back to an earlier step with options, and one of its options
        for i, st in enumerate(steps):
            on = st.get("on")
            if not on:
                continue
            d = forks.get(on.get("step"))
            if not d or keys.index(on["step"]) >= i:
                errs.append(f"{wid}:{st['key']}: \"on\" names {on.get('step')!r}, which is not an earlier step with options")
            elif not all(0 <= a < len(d.get("alts", [])) for a in (on.get("alt") if isinstance(on.get("alt"), list) else [on.get("alt", -1)])):
                errs.append(f"{wid}:{st['key']}: \"on\" option {on.get('alt')} doesn't exist on {on['step']}")
        # 3. every path says which option it took at each decision it reaches (same hiding as the page)
        for ex in w.get("simulated", []):
            taken, ended = ex.get("taken") or {}, False
            for st in steps:
                on = st.get("on")
                alts = on.get("alt") if on and isinstance(on.get("alt"), list) else [on.get("alt")] if on else []
                if ended or (on and on.get("step") in taken and not any(a in taken[on["step"]] for a in alts)):
                    continue
                if st.get("type") == "dec" and st["key"] not in taken:
                    errs.append(f"{wid}: path {ex.get('label')!r} doesn't say which option it took at {st['key']} (taken.{st['key']})")
                tk = taken.get(st["key"]) or []
                if tk and all(0 <= j < len(st.get("alts", [])) and st["alts"][j].get("ends") for j in tk):
                    ended = True
        # 4. steps matched to real runs by the same step type must be told apart with step_any
        seen = {}
        for st in steps:
            f = st.get("from")
            if isinstance(f, dict):
                for t in f.get("type_any", []):
                    seen.setdefault(t, []).append(st)
        for t, sts in seen.items():
            if len(sts) > 1:
                lists = [tuple(x["from"].get("step_any") or ()) for x in sts]
                if not all(lists) or len(set(lists)) < len(lists):
                    errs.append(f"{wid}: steps {', '.join(x['key'] for x in sts)} all match {t!r}: "
                                "give each a different \"step_any\"")
    # 5b. every step has a short title for the compact view
    for wid, st in [("dispatcher", x) for x in defs["dispatcher"]["steps"]] + \
                   [(w["id"], x) for w in defs["workflows"] for x in w["steps"]]:
        t = st.get("title", "")
        if not t:
            errs.append(f"{wid}:{st['key']}: needs a short \"title\" (up to 6 words) for the compact view")
        elif len(t.split()) > 6 and st.get("mark") != "ask":   # an open question in a new draft is the question itself
            errs.append(f"{wid}:{st['key']}: title {t!r} is over 6 words; put the detail in \"what\"")
        if len(st.get("tag", "")) > 10:
            errs.append(f"{wid}:{st['key']}: tag {st['tag']!r} should be one short word")
    # 5c. stages (rule 23): a workflow over 7 steps groups them into 3-7 stages, plain titles, in order
    for w in defs["workflows"]:
        wid, steps, stages = w["id"], w["steps"], w.get("stages") or []
        if not stages:
            if len(steps) > MAX_FLAT and not w.get("parent"):
                errs.append(f"{wid}: {len(steps)} steps and no \"stages\"; over {MAX_FLAT} steps, group them into "
                            f"3-7 stages (README, \"Stages\")")
            continue
        skeys = [s.get("key") for s in stages]
        if len(set(skeys)) != len(skeys) or not all(skeys):
            errs.append(f"{wid}: every stage needs its own \"key\"")
        if not 3 <= len(stages) <= 7:
            errs.append(f"{wid}: {len(stages)} stages; use 3 to 7")
        for s in stages:
            t = s.get("title", "")
            if not t or len(t.split()) > 6:
                errs.append(f"{wid}: stage {s.get('key')!r} needs a title of up to 6 words")
            elif JARGON.search(t):
                errs.append(f"{wid}: stage title {t!r} has a file name, code word or abbreviation; "
                            "write it for someone who doesn't know the system")
        seen, last = [], None
        for st in steps:
            k = st.get("stage")
            if k not in skeys:
                errs.append(f"{wid}:{st['key']}: \"stage\" {k!r} is not one of {', '.join(map(str, skeys))}")
                continue
            if k != last:
                if k in seen:
                    errs.append(f"{wid}:{st['key']}: stage {k!r} is split; its steps must be next to each other")
                seen.append(k)
                last = k
        for k in skeys:
            if k not in seen:
                errs.append(f"{wid}: stage {k!r} has no steps")
        if seen and [k for k in skeys if k in seen] != seen:
            errs.append(f"{wid}: stages are listed in a different order from their steps")
    # 5d. loops (rule 33): a loop is a run of next-to-each-other steps that repeat for each item; a stage is wholly
    # inside a loop or wholly outside it; one loop may sit inside another, no deeper; a loop with steps after it is
    # closed by a combine step ("combines": its key) straight after its last step
    for w in defs["workflows"]:
        wid, steps, loops = w["id"], w["steps"], w.get("loops") or []
        if not loops:
            if any(st.get("combines") for st in steps):
                errs.append(f"{wid}: a step \"combines\" a loop, but the workflow has no \"loops\"")
            continue
        order = [st["key"] for st in steps]
        lkeys = [lp.get("key") for lp in loops]
        if len(set(lkeys)) != len(lkeys) or not all(lkeys):
            errs.append(f"{wid}: every loop needs its own \"key\"")
            continue
        by = {lp["key"]: lp for lp in loops}
        for lp in loops:
            k, ks = lp["key"], lp.get("steps") or []
            if not lp.get("each") or not lp.get("title"):
                errs.append(f"{wid}: loop {k!r} needs \"each\" (what one item is) and a \"title\" (\"For each <item>\")")
            if not ks or any(x not in order for x in ks):
                errs.append(f"{wid}: loop {k!r} lists steps that aren't the workflow's: {[x for x in ks if x not in order]}")
                continue
            ix = sorted(order.index(x) for x in ks)
            if ix != list(range(ix[0], ix[0] + len(ix))):
                errs.append(f"{wid}: loop {k!r}: its steps must be next to each other")
            inn = lp.get("in")
            if inn:
                if inn not in by:
                    errs.append(f"{wid}: loop {k!r} is \"in\" {inn!r}, which is not a loop")
                elif by[inn].get("in"):
                    errs.append(f"{wid}: loop {k!r} is a loop inside a loop inside a loop; one level is the most "
                                "(make the inner part its own workflow or a shared process)")
                elif not set(ks) <= set(by[inn].get("steps") or []):
                    errs.append(f"{wid}: loop {k!r} is \"in\" {inn!r} but has steps outside it")
            if lp.get("over") not in (None, "", "trigger") and lp["over"] not in order:
                errs.append(f"{wid}: loop {k!r} goes over {lp['over']!r}: \"trigger\" or the key of the step that makes the list")
            last = ix[-1] if ix else -1
            after = steps[last + 1] if 0 <= last < len(steps) - 1 else None
            outer_last = None
            if inn and inn in by and by[inn].get("steps"):
                outer_last = max(order.index(x) for x in by[inn]["steps"] if x in order)
            if after is not None and last != outer_last and after.get("combines") != k:
                errs.append(f"{wid}: loop {k!r} has steps after it, so the step straight after it must combine it "
                            f"(\"combines\": {k!r}); {after['key']!r} doesn't")
        for st in steps:
            c = st.get("combines")
            if c and c not in by:
                errs.append(f"{wid}:{st['key']}: \"combines\" {c!r}, which is not a loop")
        for sg in w.get("stages") or []:
            mine = [st["key"] for st in steps if st.get("stage") == sg.get("key")]
            chains = {tuple(lp["key"] for lp in loops if x in (lp.get("steps") or [])) for x in mine}
            if len(chains) > 1:
                errs.append(f"{wid}: stage {sg.get('key')!r} is partly inside a loop; a stage is wholly inside a loop or "
                            "wholly outside it (rule 33)")
    # 5. every quoted rule must still be in its skill
    for wid, st in [("dispatcher", x) for x in defs["dispatcher"]["steps"]] + \
                   [(w["id"], x) for w in defs["workflows"] for x in w["steps"]]:
        if st.get("why", {}).get("missing"):
            errs.append(f"{wid}:{st['key']}: quoted rule not found in {st['why']['file']} (the skill changed)")
    return errs



STEP_HEAD = re.compile(r"\*\*Step [0-9a-z]+[:.]\s*([^*]+?)\*\*")


def step_titles(defs, errs):
    """Run steps line up with their workflow by title (run_item.py stamps each logged step with the step whose title
    it carries), so the titles must be one and the same: unique in a workflow, and each one, word for word, a
    "**Step N: <title>.**" heading of its skill. A skill without such headings (an older format, or code) is skipped:
    its runs fall back to the step finders."""
    norm = lambda x: " ".join(str(x or "").lower().rstrip(".?:").split())
    for w in defs["workflows"]:
        sk = (w.get("match") or {}).get("skill")
        if not sk or w.get("code_file") or any(st.get("code_file") for st in w.get("steps", [])):
            continue
        titles = [st.get("title", "") for st in w.get("steps", [])]
        for t in sorted({t for t in titles if t and titles.count(t) > 1}):
            errs.append(f"{w['id']}: two steps are titled {t!r}; a run's steps are placed by title, so make each one different")
        path = entries.skill_file(sk)[1]
        if not path:
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                heads = [h.strip() for h in STEP_HEAD.findall(fh.read())]
        except OSError:
            continue
        if not heads:
            continue
        hs = {norm(h) for h in heads}
        for st in w.get("steps", []):
            if st.get("title") and norm(st["title"]) not in hs:
                errs.append(f"{w['id']}:{st['key']}: title {st['title']!r} is no \"Step N\" heading in {sk} "
                            f"(it has: {'; '.join(heads)}); runs log the skill's heading, so make them the same")


def calm_lines(steps, ws):
    """How many lines a stage shows open in the Builder's calm layout (rule 23): each decision and each code step
    one line, each run of plain steps one line, each branch one more for its "if …" (a whole stage on one answer has
    none); a code step's own steps hide behind it."""
    rows = [s for s in steps if not s.get("nest")]
    whole = bool(rows) and rows[0].get("on") and all(s.get("on") == rows[0].get("on") for s in rows)
    # each decision or code step is one line; a run of plain steps is one line when it folds (4 or more in a row, or 2 or
    # more once the stage is long; never a whole stage), else one line per step
    n, runs, branch = 0, [], None
    for s in rows:
        b = None if whole else json.dumps(s.get("on"), sort_keys=True) if s.get("on") else None
        if b != branch:
            branch = b
            n += 1 if b else 0
            runs.append(0)
        own = s.get("type") == "dec" or s.get("code_file") or any(x.get("nest") for x in ws if x.get("parent_key") == s.get("key"))
        if own:
            n += 1
            runs.append(0)
        else:
            if not runs:
                runs.append(0)
            runs[-1] += 1
    plain_total = sum(runs)
    unfolded = n + plain_total
    for r in runs:
        if r == 0:
            continue
        if r == len(rows):
            n += r
        elif r >= 4 or (r >= 2 and unfolded > 7):
            n += 1
        else:
            n += r
    return n


def calm_check(defs):
    """Rule 23's limits and plain words for the calm Builder: WARN only, so a draft is never stopped. A stage that
    shows more than 7 lines open, a branch of 5 steps or more, a stage with no outcome ("makes"), and a step,
    decision or stage with no tooltip ("tip") or one longer than a sentence."""
    for w in defs["workflows"]:
        if w.get("parent") or (w.get("draft") or {}).get("kind") == "new" and not w.get("steps"):
            continue
        wid, steps, stages = w["id"], w["steps"], w.get("stages") or []
        for st in stages:
            mine = [x for x in steps if x.get("stage") == st.get("key")]
            n = calm_lines(mine, steps)
            if n > 7:
                print(f"WARN {wid}: stage \"{st.get('title')}\" shows {n} lines open; over 7 it's probably two "
                      "milestones, so split it where the result changes (rule 23)")
            if not st.get("makes"):
                print(f"WARN {wid}: stage \"{st.get('title')}\" has no \"makes\": what it produces, a few words for "
                      "the right of its line (rule 23)")
        by_on = {}
        for x in steps:
            if x.get("on") and not x.get("nest"):
                by_on.setdefault(json.dumps(x["on"], sort_keys=True), []).append(x)
        for on, xs in by_on.items():
            stg = {x.get("stage") for x in xs}
            whole = len(stg) == 1 and all(y.get("on") for y in steps if y.get("stage") in stg and not y.get("nest"))
            if len(xs) >= 5 and not whole:
                print(f"WARN {wid}: {len(xs)} steps run on one answer of \"{on}\" inside a stage; at 5 or more make "
                      "them their own stage, or a follow-up workflow if they end in their own result (rule 23)")
        no_tip = [x["key"] for x in steps if not x.get("nest") and not x.get("tip")]
        no_tip += ["stage " + st.get("key", "") for st in stages if not st.get("tip")]
        if no_tip:
            print(f"WARN {wid}: {len(no_tip)} line(s) with no \"tip\" (the hover ⓘ, rule 23): {', '.join(no_tip[:8])}"
                  + (" …" if len(no_tip) > 8 else ""))
        for x in [*steps, *stages]:
            t = x.get("tip") or ""
            if t and (len(t.split()) > 13 or ". " in t.strip()[:-1]):
                print(f"WARN {wid}: tip on {x.get('key')!r} should be one sentence of up to 13 words: {t!r}")


def merge_user(defs, errs):
    """Add the user's own board definitions, .workflow-manager-data/config/board/<skill>.json (entries, categories, workflows). A skill never replaces what is
    already there: a clashing key or workflow id is reported and skipped."""
    for path in entries.orphans():
        errs.append(f"{paths.rel(path)}: no skill of that name any more (renamed or deleted?): rename or remove this file")
    for layer, name, path in entries.board_files():
        try:
            with open(path, encoding="utf-8") as fh:
                extra = json.load(fh)
        except (OSError, ValueError) as err:
            errs.append(f"{paths.rel(path)}: can't read it ({err})")
            continue
        for part in ("entries", "categories", "skills"):
            for k, v in (extra.get(part) or {}).items():
                have_v = defs.setdefault(part, {}).get(k)
                if have_v is None:
                    defs[part][k] = v
                elif part == "categories" or json.dumps(have_v, sort_keys=True) == json.dumps(v, sort_keys=True):
                    continue   # a category several skills share, or one the plugin already has: the first one stands
                else:
                    errs.append(f"{paths.rel(path)}: {part}.{k} already exists; pick another name")
        for part in ("summaries", "examples", "results"):   # the page's lines, keyed workflow:<id> / trigger:<key>
            for k, v in (extra.get(part) or {}).items():
                defs.setdefault(part, {}).setdefault(k, v)
        have = {w["id"] for w in defs["workflows"]}
        for w in extra.get("workflows") or []:
            if w.get("id") in have:
                errs.append(f"{paths.rel(path)}: workflow id {w.get('id')!r} already exists; pick another")
                continue
            w["layer"] = layer
            defs["workflows"].append(w)
            have.add(w["id"])


def attach_share(defs):
    """The Share tab's data (share.py): each user workflow's published version, what was last shared and what an
    update would change; and "shared" on one brought in from a zip (where from, their version, what to pick)."""
    try:
        import share
    except Exception:
        return
    if not share.SHARED:
        return
    for w in defs["workflows"]:
        sk = (w.get("match") or {}).get("skill") or w.get("history_skill")
        if not sk or w.get("layer") != "user":
            continue
        try:
            w["share"] = share.share_info(sk)
            w["share"]["skill"] = sk
            w["share"]["runs"] = [{k: r[k] for k in ("run", "label", "started", "status", "attention", "summary")}
                                  for r in share.runs_of(sk, w.get("id"))[:12]]
        except (Exception, SystemExit):
            pass
        try:
            with open(os.path.join(share.SHARED, sk + ".json"), encoding="utf-8") as fh:
                w["shared"] = json.load(fh)
        except (OSError, ValueError):
            pass


def merge_debug(defs):
    """Debugging copies (share.py debug): each one's workflow, under its own id and the Debugging section, apart
    from the user's own workflows. Added after the checks: a copy is someone else's and is never run on its own."""
    try:
        import share
        copies = share.debug_copies()
    except Exception:
        return
    have = {w["id"] for w in defs["workflows"]}
    for m in copies:
        wid = m.get("board_workflow") or ("debug-" + m["slug"])
        if wid in have:
            continue
        sk = m["workflow"]
        board = {}
        try:
            with open(os.path.join(m["root"], "current", "board", sk + ".json"), encoding="utf-8") as fh:
                board = json.load(fh)
        except (OSError, ValueError):
            pass
        src = (board.get("workflows") or [{}])[0]
        w = json.loads(json.dumps(src))
        old = w.get("id")
        w.update({"id": wid, "category": "debugging", "layer": "debug", "entries": [], "match": {},
                  "short": src.get("short") or m.get("title") or sk})
        w["debug"] = {"slug": m["slug"], "skill": sk, "from": m.get("from_zip", ""), "version": m.get("version", ""),
                      "note": m.get("note", ""), "runs": m.get("runs") or [], "changed": m.get("changed") or [],
                      "folder": paths.rel(m["root"]), "imported": m.get("imported", "")}
        for part in ("summaries", "examples", "results"):
            v = (board.get(part) or {}).get("workflow:" + str(old))
            if v is not None:
                defs.setdefault(part, {})["workflow:" + wid] = v
        for k, v in (board.get("skills") or {}).items():
            defs.setdefault("skills", {}).setdefault(k, v)
        defs["workflows"].append(w)
        have.add(wid)
    if copies:
        defs.setdefault("categories", {}).setdefault("debugging", {"name": "Debugging", "tone": "amber",
                                                                   "section": "workflows"})


def iteration_info(w, sk):
    """A draft's iterations (skill_history.py): which one it is, what the last change did (its marks: JUST ADDED,
    JUST CHANGED, JUST REMOVED) and whether Claude is changing it right now."""
    try:
        import skill_history
        log = skill_history.iter_log(sk)
    except (Exception, SystemExit):
        return
    items = log.get("items") or []
    if items:
        w["iteration"], w["iter_note"], w["iter_t"] = items[-1]["n"], items[-1].get("note", ""), items[-1].get("t", "")
        if items[-1].get("summary"):
            w["draft_summary"] = items[-1]["summary"]
        if items[-1].get("details"):
            w["draft_details"] = items[-1]["details"]
        m = skill_history.iter_marks(sk).get(w["id"])
        if m:
            w["just_marks"], w["just_removed"] = m["marks"], m["removed"]
    if log.get("updating"):
        w["updating"] = log["updating"]


def merge_drafts(defs, errs):
    """Imports waiting for the user's yes (core-architect Import mode): drafts/<name>.json, each one workflow in
    the same shape as workflows.json plus a "draft" block (source, proposed needs, what it changes, overlaps).
    Shown under Drafts on the Workflow Viewer; not a skill yet, so it has no runs and no trigger."""
    if not os.path.isdir(paths.DRAFTS):
        return
    files = sorted(f for f in os.listdir(paths.DRAFTS) if f.endswith(".json"))
    if not files:
        return
    defs.setdefault("sections", []).append({"key": "drafts", "name": "Drafts",
                                            "desc": "New workflows being drafted, and imports waiting for your yes: not skills yet"})
    defs.setdefault("categories", {})["drafts"] = {"name": "Imports", "tone": "purple", "section": "drafts"}
    have = {w["id"] for w in defs["workflows"]}
    for f in files:
        path = os.path.join(paths.DRAFTS, f)
        try:
            with open(path, encoding="utf-8") as fh:
                w = json.load(fh)
        except (OSError, ValueError) as err:
            errs.append(f"{paths.rel(path)}: can't read it ({err})")
            continue
        stem = f[:-5]
        w.setdefault("draft", {})
        new = w["draft"].get("kind") == "new"   # a workflow being created in the chat (core-architect Create mode)
        w.update({"id": "draft-" + stem, "category": "new" if new else "drafts", "direct": True, "entries": []})
        w.pop("match", None)
        if w["id"] in have:
            continue
        sk = "draft:" + stem
        defs.setdefault("skills", {})[sk] = {"short": w.get("short") or stem, "code": "w", "cat": w["category"]}
        for st in w.get("steps", []):
            st.setdefault("sk", sk)
            why = st.setdefault("why", {"label": "", "sum": ""})
            why.update({"draft": True, "file": why.get("file") or w["draft"].get("source", stem), "missing": False})
        if isinstance(w["draft"].get("needs"), dict):
            w["needs"] = {k: [bool(v.get("required")), v.get("example", "")] if isinstance(v, dict) else v
                          for k, v in w["draft"]["needs"].items()}
        defs["workflows"].append(w)
        have.add(w["id"])


def new_category(defs):
    """The reserved category `new` (core-architect Create mode): a new workflow and its trigger, from the first draft
    until they are named. Listed first, so the sidebar's New group is a design area above the real categories."""
    cats = defs.setdefault("categories", {})
    cats.pop("new", None)
    defs["categories"] = {"new": {"name": "New", "tone": "purple", "section": "workflows",
                                  "desc": "Being designed: not named or published yet"}, **cats}


WAY_IN = {"connector": "MCP", "chrome": "external browser", "browser": "built-in browser", "api": "API"}
BUILT_IN = {"web": "the public web: search and public pages", "browser": "public pages in the browser"}


def uses_of(skill):
    """[(name, what)] from a skill's Definition `uses:` (a map, or a list of "name: what")."""
    u = ((entries.definition(skill) or {}).get("uses")) if skill else None
    if isinstance(u, dict):
        return [(k.strip().lower(), str(v).strip()) for k, v in u.items()]
    if isinstance(u, list):
        return [(x.partition(":")[0].strip().lower(), x.partition(":")[2].strip()) for x in u]
    return []


def connections_info(defs, errs):
    """Connections (rule 19): every connection-<system> skill, its Definition and its status (connections.py), and
    which triggers and workflows use it. Each workflow and trigger gets "uses" for its Connections tab; a name that
    is neither a connection nor built in is an ERROR."""
    import connections as cn
    conns = {}
    for _layer, name, _d in entries.skill_dirs():
        if not name.startswith("connection-"):
            continue
        key, defn = name[len("connection-"):], entries.definition(name) or {}
        st = cn.get(key)
        meths = defn.get("methods") if isinstance(defn.get("methods"), dict) else {}
        conns[key] = {"skill": name, "system": defn.get("system") or key.capitalize(), "methods": meths,
                      "method": st.get("method", ""), "setup_now": st.get("setup"),
                      "via": meths.get(st.get("method", "")) or defn.get("via", ""),
                      "setup": defn.get("setup", ""), "check": defn.get("check", ""),
                      "reads": defn.get("reads") or {}, "writes": defn.get("writes") or {},
                      "status": st.get("status", "unknown"), "why": st.get("why", ""), "checked": st.get("checked", ""),
                      "log": (st.get("log") or [])[:5], "used_by": []}
        # its name on the board says the way in: "Slack (MCP)", "Rightmove (external browser)". The chosen method,
        # else the only one it lists; several and none chosen yet: the system alone
        how = st.get("method") or (next(iter(meths)) if len(meths) == 1 else "")
        conns[key]["label"] = conns[key]["system"] + (f" ({WAY_IN[how]})" if how in WAY_IN else "")
    def attach(owner, label, view, skill):
        out = []
        for name, what in uses_of(skill):
            if name in BUILT_IN:
                out.append({"name": name, "what": what or BUILT_IN[name], "builtin": True})
            elif name in conns:
                out.append({"name": name, "what": what})
                conns[name]["used_by"].append({"view": view, "label": label})
            else:
                errs.append(f"{skill}: uses {name!r}, but there is no connection-{name} skill (rule 19)")
        owner["uses"] = out
    for w in defs["workflows"]:
        sk = (w.get("match") or {}).get("skill")
        if sk:
            attach(w, w.get("short") or w["id"], w["id"], sk)
    for k, e in (defs.get("entries") or {}).items():
        if e.get("skill"):
            attach(e, e.get("name") or k, "disp:" + k, e["skill"])
    defs["connections"] = conns


def engine_steps(k, e):
    """The engine's two steps after every trigger's own (core-dispatcher, Run a trigger steps 3 and 4): the same for
    every trigger, so no trigger writes them."""
    noun = e.get("noun") or "item"
    key = e.get("item_key") or next((x.get("item_key") for x in entries.load() if x.get("id") == k), "") or "own ID in the source"
    ids = {"key": f"{k}-ids", "sk": "core-dispatcher", "lane": "Delegate", "type": "check", "tag": "Check",
           "title": f"Give each {noun} an ID", "what": f"Gives each {noun} a workflow ID from its {key} and checks the done list",
           "from": "ids", "continues": "all",
           "why": {"file": "core-dispatcher", "label": "Item IDs + Run a trigger · Step 3",
                   "parts": [{"section": "Run a trigger", "pick": ["Step 3: Give each item"]},
                             {"section": "Item IDs", "pick": ["| `action`", "|---", "| `run`", "| `link`"]}],
                   "sum": f"The same {noun} always maps to the same workflow ID. Done before and Run each item once on: link, don't run."},
           "alts": [{"when": "New", "then": "Run it", "k": "next"}, {"when": "Done before", "then": "Link to the earlier run", "k": "info"}]}
    send = {"key": f"{k}-send", "sk": "core-dispatcher", "lane": "Delegate", "type": "act", "tag": "Hand off",
            "title": f"Send each new {noun} on", "what": f"Sends each new {noun} to its workflow, one at a time",
            "from": "dispatched", "links": list(e.get("feeds") or []),
            "why": {"file": "core-dispatcher", "label": "Run a trigger · Step 4: Dispatch the work",
                    "parts": [{"section": "Run a trigger", "pick": ["Step 4: Dispatch"]}],
                    "sum": f"Records the start, hands over only that {noun}'s details, then records how it ended."}}
    return [ids, send]


def compose_dispatcher(defs):
    """The dispatcher's board definition, put together from the triggers (rule 17): its own steps (Pick the trigger,
    Rerun) stay in workflows.json; each trigger's own steps and paths live in its entry (steps, simulated, when);
    the engine's steps after them are the same for every trigger. So adding a trigger never edits the dispatcher.
    Options and steps that point at a fixed option by "alt_id" get its number here."""
    D = defs["dispatcher"]
    d1 = D["steps"][0]
    fixed = [a for a in d1["alts"] if not a.get("entry") or a.get("id")]
    ents = [(k, e) for k, e in (defs.get("entries") or {}).items() if e.get("steps") or e.get("when")]
    alts = [{"when": e.get("when") or f"Mentions {e.get('name', k)}", "then": e.get("name", k), "k": "next", "entry": k}
            for k, e in ents]
    d1["alts"] = alts + fixed
    pos = {a.get("id"): i for i, a in enumerate(d1["alts"]) if a.get("id")}
    for st in D["steps"][1:]:
        on = st.get("on") or {}
        if "alt_id" in on:
            st["on"] = {"step": "d1", "alt": pos[on["alt_id"]]}
    for m in D.get("simulated", []):
        t = m.get("taken", {}).get("d1")
        if t:
            m["taken"]["d1"] = [pos.get(x, x) if isinstance(x, str) else x for x in t]
    for i, (k, e) in enumerate(ents):
        for st in [dict(x) for x in e.get("steps") or []] + engine_steps(k, e):
            st.update(entry=k, on={"step": "d1", "alt": i})
            D["steps"].append(st)
        for m in e.get("simulated") or []:
            m = json.loads(json.dumps(m))
            m.update(entry=k)
            m["taken"] = {"d1": [i], **(m.get("taken") or {})}
            m["res"] = {"d1": f"Matches the {e.get('name', k)} trigger", **(m.get("res") or {})}
            D.setdefault("simulated", []).append(m)


def section_of_cat(defs, k):
    cats, seen = defs.get("categories", {}), []
    while k in cats and cats[k].get("parent") and k not in seen:
        seen.append(k)
        k = cats[k]["parent"]
    return cats.get(k, {}).get("section")


def contracts(defs):
    """Fill in each workflow's needs and each trigger's fields from their Definition blocks, and check that
    every trigger gives the required fields of every workflow it starts (rule 21)."""
    errs = []
    gives = {e["id"]: e for e in entries.load()}
    for k, e in (defs.get("entries") or {}).items():
        if k in gives and gives[k].get("gives"):
            e["gives"] = gives[k]["gives"]
        if k in gives:
            e.update(starts_on=gives[k].get("triggers") or [], item_key=gives[k].get("item_key") or "",
                     run_all=gives[k].get("run_all", True), reads=gives[k].get("reads") or "",
                     takes=gives[k].get("takes") or "")   # the page's four trigger slots (rule 30)
            if gives[k].get("schedule"):
                e["schedule"] = gives[k]["schedule"]
            else:
                e.pop("schedule", None)
    for w in defs["workflows"]:
        skills = sorted({(st.get("why") or {}).get("file") for st in w["steps"]} - {None})
        kind = "shared-" if (defs.get("sections") and section_of_cat(defs, w.get("category")) == "shared") else "workflow-"
        skills = [n for n in skills if n.startswith(kind) or entries.renames().get(n, "").startswith(kind)]
        if kind == "shared-" and w.get("skill"):
            skills = [w["skill"]]
            g = (entries.definition(w["skill"]) or {}).get("gives")
            if isinstance(g, dict) and g:
                w["gives"] = g
        need = {}
        for n in skills:
            for field, (req, ex) in entries.needs(entries.definition(n)).items():
                need[field] = [req or need.get(field, [False])[0], ex]
        if need:
            w["needs"] = need
        for t in w.get("entries", []):
            have = (gives.get(t) or {}).get("gives") or {}
            if not have or not need:
                continue   # a skill from before 0.10.0 without a Definition block: nothing to compare yet
            missing = [f for f, (req, _) in need.items() if req and f not in have]
            if missing:
                errs.append(f"{w['id']}: trigger {t!r} doesn't give the required field(s) {', '.join(missing)} "
                            f"that {', '.join(skills)} needs (rule 21)")
    return errs


def viewer_has_colour(code):
    """steps.css (the step component both pages use) has this skill code's rail, label and band colours
    (.fl-bar-<code>, .fl-k-<code>, .fl-bd-<code>) and its tokens in light and both dark blocks."""
    try:
        css = open(os.path.join(paths.CODE, "steps.css"), encoding="utf-8").read()
    except OSError:
        return True
    return all(f".fl-{k}-{code}{{" in css for k in ("bar", "k", "bd")) and css.count(f"--k-{code}:") >= 3


def followups(defs, errs):
    """Follow-up items (one workflow hands back work the dispatcher runs next as its own item): the step that hands
    it back has "starts": <workflow id>, and the target page lists who starts it ("followup_from"). A skill whose
    text has a **Follow-up item** with no such step on the board is an ERROR, so the two never drift apart."""
    ids = {w["id"]: w for w in defs["workflows"]}
    for w in defs["workflows"]:
        w.pop("followup_from", None)
    for w in defs["workflows"]:
        starts = [st for st in w["steps"] if st.get("starts")]
        for st in starts:
            t = ids.get(st["starts"])
            if not t:
                errs.append(f"{w['id']}.{st['key']}: starts {st['starts']!r}, which is not a workflow id")
                continue
            tsk = (t.get("match") or {}).get("skill")
            if tsk and tsk not in defs.get("skills", {}):
                errs.append(f"{w['id']}.{st['key']}: the workflow it starts ({tsk}) has no colour on the board: add it to "
                            f"\"skills\" with a short name and its own \"code\" (rule 25)")
            code = (defs.get("skills", {}).get(tsk) or {}).get("code")
            if tsk and code and not viewer_has_colour(code):
                errs.append(f"{w['id']}.{st['key']}: colour code {code!r} for {tsk} has no colours in steps.css "
                            f"(.fl-bar-{code}, .fl-k-{code}, .fl-bd-{code}, and --k-{code} light and dark; rule 25)")
            t.setdefault("followup_from", [])
            if w["id"] not in t["followup_from"]:
                t["followup_from"].append(w["id"])
        sk = (w.get("match") or {}).get("skill")
        path = entries.skill_file(sk)[1] if sk else None
        text = open(path).read() if path and os.path.exists(path) else ""
        if "**Follow-up item" in text and not starts:
            errs.append(f"{w['id']}: {sk} hands back a follow-up item, but no step on the board has \"starts\" "
                        f"(the workflow it runs next)")


def attach_history(defs):
    """Each workflow's versions from the hidden skill history (skill_history.py), newest last, for its History
    panel. No history yet, or git missing: no panel data, never an error."""
    try:
        import skill_history
        allv = skill_history.versions()
    except (Exception, SystemExit):
        return
    for w in defs["workflows"]:
        sk = skill_history.board_skill(w)
        if not sk:
            continue
        if not allv.get(sk):
            # no version yet (the history couldn't start): still show a draft, so an edit is never invisible
            try:
                if os.path.isdir(os.path.join(paths.USER_SKILLS if paths.PLUGIN else paths.SKILLS, sk)) and skill_history.is_draft(sk):
                    w["history"], w["history_skill"], w["edited"] = [], sk, True
                    w["draft_changes"] = ["Not published yet: no version of this workflow has been saved"]
                    w["step_marks"] = {st["key"]: "new" for st in w.get("steps", []) if st.get("key")}
                    iteration_info(w, sk)
            except (Exception, SystemExit):
                pass
            continue
        if allv.get(sk):
            w["history"] = allv[sk]
            w["history_skill"] = sk   # runs and restore requests use this name
            try:
                # edits since its last version, not published yet ("draft" is taken: an import waiting for a yes)
                w["edited"] = skill_history.is_draft(sk)
                if w["edited"]:   # what the draft changes, and its impact review once Publish has written one
                    ci = skill_history.draft_change_items(sk)
                    w["draft_changes"] = [x["t"] for x in ci]
                    w["draft_change_keys"] = {x["t"]: x["keys"] for x in ci if x["keys"]}   # a chip shows its steps
                    w["uses_new"] = skill_history.new_uses(sk)   # a connection the change adds: its Connect step
                    # the change marks on its steps (NEW / CHANGED, and the steps it removes), against the last version
                    dm = skill_history.draft_marks(sk)
                    m = dm.get(w["id"]) or (next(iter(dm.values())) if len(dm) == 1 else None)
                    if m:
                        w["step_marks"], w["removed_steps"] = m["marks"], m["removed"]
                    iteration_info(w, sk)
                    pr = skill_history.pending(sk)
                    if pr and pr.get("review"):
                        w["pending_review"] = dict(pr["review"], current=pr["current"])
                else:   # not a draft yet: Claude may be starting its first change
                    up = skill_history.iter_log(sk).get("updating")
                    if up:
                        w["updating"] = up
            except (Exception, SystemExit):
                pass


def skill_versions(obj, sk, allv=None):
    """A trigger's or connection's versions and draft (the same history as a workflow's, without step marks):
    history, edited, draft_changes, its iteration and any pending impact review. Never an error."""
    try:
        import skill_history
        allv = allv if allv is not None else skill_history.versions()
        obj["history"], obj["history_skill"] = allv.get(sk) or [], sk
        obj["edited"] = skill_history.is_draft(sk)
        if obj["edited"]:
            ci = skill_history.draft_change_items(sk)
            obj["draft_changes"] = [x["t"] for x in ci] if obj["history"] else ["Not published yet: no version has been saved"]
            iteration_info(obj, sk)
            pr = skill_history.pending(sk)
            if pr and pr.get("review"):
                obj["pending_review"] = dict(pr["review"], current=pr["current"])
    except (Exception, SystemExit):
        pass


def attach_side_versions(defs):
    """Triggers and connections are skills too: each gets its versions and draft, and a workflow's draft also
    says when its trigger or a connection it uses has a draft of its own (they change how it runs)."""
    try:
        import skill_history
        allv = skill_history.versions()
    except (Exception, SystemExit):
        return
    for k, e in (defs.get("entries") or {}).items():
        if e.get("skill") and not e.get("inside"):   # a workflow's own trigger shares the workflow's versions
            e.setdefault("id", "disp:" + k)
            skill_versions(e, e["skill"], allv)
    for k, c in (defs.get("connections") or {}).items():
        c.setdefault("id", "conn:" + k)
        skill_versions(c, c["skill"], allv)
    for w in defs["workflows"]:
        side = []
        for k in w.get("entries") or []:
            e = (defs.get("entries") or {}).get(k) or {}
            if e.get("edited"):
                side.append({"t": f"Its {e.get('name') or k} trigger has a draft too", "view": "disp:" + k})
        for u in w.get("uses") or []:
            c = (defs.get("connections") or {}).get(u.get("name")) or {}
            if c.get("edited"):
                side.append({"t": f"The {c.get('system') or u['name']} connection has a draft too", "view": "connections", "conn": u["name"]})
        if side:
            w["side_drafts"] = side


def recordings_of(skill, sub=""):
    """{id: recording} from the skill's tests/recordings/ (recording.py): real runs, replayed by its tests.
    sub="trigger": a workflow's own trigger's, in tests/trigger/recordings/."""
    f = entries.skill_file(skill)[1] if skill else None
    d = os.path.join(os.path.dirname(f), "tests", *([sub] if sub else []), "recordings") if f else None
    out = {}
    if d and os.path.isdir(d):
        for n in sorted(os.listdir(d)):
            if n.endswith(".json"):
                try:
                    out[n[:-5]] = json.load(open(os.path.join(d, n), encoding="utf-8"))
                except ValueError:
                    pass
    return out


def tests_check(defs, errs):
    """Test cases (core-architect rule 28): every path of a workflow has a case in the skill's tests/ folder and
    every case names a path that exists; a case's seed item has the workflow's required fields and its canned
    answers name real steps; every trigger has a case on a fake source whose records carry the fields the trigger
    hands on. Each workflow gets "tests" (its cases) for the Workflow Viewer."""
    def cases_of(skill, sub=""):
        f = entries.skill_file(skill)[1] if skill else None
        d = os.path.join(os.path.dirname(f), "tests", *([sub] if sub else [])) if f else None
        out = {}
        if d and os.path.isdir(d):
            for n in sorted(os.listdir(d)):
                if n.endswith(".json"):
                    try:
                        out[n[:-5]] = json.load(open(os.path.join(d, n), encoding="utf-8"))
                    except ValueError:
                        errs.append(f"{skill}/tests/{n}: not valid JSON")
        return out
    known = {}
    for w in defs["workflows"]:
        sk = (w.get("match") or {}).get("skill") or ""
        if sk.startswith("workflow-"):
            known[sk] = cases_of(sk)
    for w in defs["workflows"]:
        sk = (w.get("match") or {}).get("skill") or ""
        if sk not in known:
            continue
        cases, labels = known[sk], [p.get("label") for p in w.get("simulated", [])]
        keys = {st["key"] for st in w["steps"]}
        need = entries.needs(entries.definition(sk))
        recs = recordings_of(sk)
        w["tests"] = [{"id": k, "path": c.get("path"), "live": bool(c.get("live")), "recorded": bool(c.get("recording")),
                       "sample": bool(c.get("sample")),   # a sample from the draft's own examples, not real data
                       "from_run": (recs.get(c.get("recording")) or {}).get("from_run", "")} for k, c in cases.items()]
        w["recordings"] = len(recs)
        # a path with no real example yet is a gap, shown on the page; nothing is made up to fill it (rule 28)
        w["test_gaps"] = [lab for lab in labels if not any(c.get("path") == lab and c.get("recording") for c in cases.values())]
        made_up = [k for k, c in cases.items() if not c.get("recording")]
        if made_up:
            print(f"WARN {sk}: {len(made_up)} test case(s) on made-up data, to replace with recordings of real runs (rule 28): {', '.join(made_up)}")
        latest = sorted(recs.values(), key=lambda r: r.get("recorded", ""))
        sysok = {}
        for r in latest:
            s = r.get("systems") or {}
            sysok.update(s if isinstance(s, dict) else {str(x).capitalize(): "ok" for x in s})
        for k, c in cases.items():
            if c.get("path") not in labels:
                errs.append(f"{sk}/tests/{k}.json: its path {c.get('path')!r} is not a path on the board (rule 28)")
            if c.get("recording"):
                if c["recording"] not in recs:
                    errs.append(f"{sk}/tests/{k}.json: recording {c['recording']!r} not in its tests/recordings/")
                continue
            miss = [f for f, (req, _e) in need.items() if req and f not in (c.get("item") or {})]
            if miss:
                errs.append(f"{sk}/tests/{k}.json: the seed item is missing required fields {miss} (rule 28)")
            bad = [x for x in (c.get("canned") or {}) if x not in keys]
            if bad:
                errs.append(f"{sk}/tests/{k}.json: canned answers for steps the board doesn't have: {bad}")
            for tsk, tcase in (c.get("followup_case") or {}).items():
                if tcase not in known.get(tsk, {}):
                    errs.append(f"{sk}/tests/{k}.json: followup_case {tsk}/{tcase} doesn't exist")
    seen_src = set()
    for e in entries.load():
        sk = e.get("skill")
        if not sk or not (sk.startswith("trigger-") or e.get("inside")):
            continue
        sub = "trigger" if e.get("inside") else ""   # a workflow's own trigger keeps its cases in tests/trigger/
        cases = cases_of(sk, sub)
        trecs = recordings_of(sk, sub)
        gives = list((e.get("gives") or {}).keys()) if e.get("inside") else \
            list(((entries.definition(sk) or {}).get("each item has") or {}).keys())
        for k, c in cases.items():
            if c.get("recording"):
                if c["recording"] not in trecs:
                    errs.append(f"{sk}/tests/{k}.json: recording {c['recording']!r} not in its tests/recordings/")
                continue
            print(f"WARN {sk}/tests/{k}.json: a made-up fake source, to replace with a recording of a real run (rule 28)")
            src = paths.fake(c.get("source"))
            if not os.path.exists(src):
                errs.append(f"{sk}/tests/{k}.json: fake source {c.get('source')!r} not in tests/fakes/")
                continue
            if (sk, src) in seen_src:
                continue
            seen_src.add((sk, src))
            for r in json.load(open(src, encoding="utf-8")).get("records", []):
                miss = [f for f in gives if f not in r]
                if "id" not in r or miss:
                    errs.append(f"tests/fakes/{c.get('source')}.json {r.get('id', '?')}: missing {(['id'] if 'id' not in r else []) + miss} (what {sk} hands on)")
                ref = r.get("_case")
                if ref:
                    wsk, _, wcase = ref.partition("/")
                    if wcase not in known.get(wsk, {}):
                        errs.append(f"tests/fakes/{c.get('source')}.json {r.get('id')}: _case {ref} doesn't exist")


def settings_drawn(defs, errs):
    """An optional setting in a workflow's `needs` that its steps act on (named in backticks after the Definition
    block) changes what the workflow does, so the board shows it as a choice: some decision or guard step must
    name it (title, what, options, Why? summary or quote). Otherwise the setting is invisible on the page (rule 26)."""
    for w in defs["workflows"]:
        sk = (w.get("match") or {}).get("skill") or ""
        if not sk.startswith("workflow-"):
            continue
        path = entries.skill_file(sk)[1]
        if not path or not os.path.exists(path):
            continue
        text = open(path, encoding="utf-8").read()
        body = re.sub(r"## Definition\n.*?(?=\n## )", "", text, count=1, flags=re.S)
        board = " ".join(json.dumps({k: st.get(k) for k in ("title", "what", "alts", "why")}, ensure_ascii=False)
                         for st in w["steps"] if st.get("type") in ("dec", "guard", "route"))
        for field, (required, _ex) in entries.needs(entries.definition(sk)).items():
            if not required and f"`{field}`" in body and field not in board:
                errs.append(f"{w['id']}: the steps act on the optional setting {field!r}, but no decision on the board "
                            f"names it (add a decision for it, rule 26)")


TRIGGER_LOGIC = re.compile(r"\b(if|unless|whether|under|over|above|below|more than|less than|only when|only if|except when|as long as)\b", re.I)


def trigger_logic(defs):
    """Rule 30: a trigger only finds items (source, window, item, kind); any condition, threshold or judgement is a
    workflow step. Prints a WARN for each trigger whose `takes` or keep text names one, or whose keep step has more
    options than kept / not kept. Drafts' triggers too, so the architect sees it while drafting."""
    seen = []
    for e in entries.load():
        seen.append((e["id"], "takes", e.get("takes") or ""))
    for k, e in (defs.get("entries") or {}).items():
        for st in e.get("steps") or []:
            if st.get("tag") == "Keep" and len(st.get("alts") or []) > 2:
                print(f"WARN trigger {k}: its keep step has {len(st['alts'])} options; a trigger keeps or drops, the "
                      f"choices are the workflow's (rule 30)")
    for w in defs["workflows"]:
        t = (w.get("draft") or {}).get("trigger") or {}
        if t:
            seen += [(w["id"], "takes", t.get("takes") or ""), (w["id"], "keep", t.get("keep") or "")]
    for who, part, text in seen:
        # "the fields under `needs`" is how every keep says what it hands on, not a condition
        m = TRIGGER_LOGIC.search(re.sub(r"under\s+`?needs`?", "", text))
        if m:
            print(f"WARN trigger {who}: its {part} names a condition (\"{m.group(0)}\" in \"{text[:80]}\"); move it "
                  f"into the workflow as a decision, so the board shows when an item stops (rule 30)")


def names(defs):
    """Board names from the skill names (<kind>-<category>-<description>): each trigger's name and category,
    and each workflow's skill. A skill renamed by the architect shows its new name with no edit here."""
    trig = {e["id"]: e["skill"] for e in entries.load()}
    for k, e in (defs.get("entries") or {}).items():
        sl = entries.skill_label(trig.get(k, ""))
        if sl and sl["kind"] == "workflow":   # a workflow's own trigger (rule 17): keeps its board name, takes its category
            e.update(skill=entries.renames().get(trig[k], trig[k]), category=sl["category"], inside=True)
        elif sl:
            e.update(skill=entries.renames().get(trig[k], trig[k]), name=sl["desc"], category=sl["category"])
    for w in defs["workflows"]:
        sk = (w.get("match") or {}).get("skill") or (defs.get("categories", {}).get(w.get("category")) or {}).get("skill")
        if not sk:
            files = [(st.get("why") or {}).get("file") or "" for st in w["steps"]]
            sk = next((f for f in files if f.startswith(("workflow-", "shared-"))), None) or next((f for f in files if f), None)
        sl = entries.skill_label(sk or "")
        if sl:
            w["skill"], w["skill_label"] = entries.renames().get(sk, sk), sl["label"]


def merge_code(defs):
    """Workflows and shared processes written as code (a @flow function in a workflow- or shared- skill's .py
    files): drawn from the code itself, so they need no hand-written entry. A hand-written one with the same id wins.
    A shared process goes in its own folder under its area in Shared, like the hand-written ones."""
    have = {w["id"] for w in defs["workflows"]}
    cats = defs.setdefault("categories", {})
    for layer, name, d in entries.skill_dirs():
        if not name.startswith(("workflow-", "shared-")):
            continue
        w = codeflow.read(d)
        if not w or w["id"] in have:
            continue
        area = w["category"]
        owner = next((x for x in defs["workflows"] if (x.get("match") or {}).get("skill") == name and not x.get("parent")), None)
        if owner:   # code inside a hand-written workflow's folder: one of its steps, drawn as a child under it (rule 22)
            slug = re.sub(r"[^a-z0-9]+", "-", w["short"].lower()).strip("-")
            w.update({"id": f"{owner['id']}-{slug}", "category": owner["category"], "parent": owner["id"],
                      "entries": [], "from": f"part of {owner.get('short') or owner['name']}"})
            w.pop("match", None)   # its trace lines belong to the owner's runs: never matched as a run of its own
            for st in owner["steps"]:
                if st.get("sub") == w["id"]:
                    st["sub_label"] = w["short"]
            w["layer"] = layer
            defs["workflows"].append(w)
            have.add(w["id"])
            continue
        if name.startswith("shared-"):
            key = f"{area}-{w['id']}"
            cats.setdefault(key, {"name": w["short"], "tone": (cats.get(area) or {}).get("tone", "teal"),
                                  "parent": area, "skill": name})
            w["category"] = key
            w["from"] = "a workflow that needs it, or you"
        elif (cats.get(area) or {}).get("section") != "workflows":   # e.g. "common" lives under Shared: give it a Workflows folder
            key = area + "-workflows"
            if key not in cats:
                cats[key] = {"name": area.capitalize(), "tone": (cats.get(area) or {}).get("tone", "teal"), "section": "workflows"}
            w["category"] = key
        w["layer"] = layer
        defs["workflows"].append(w)
        have.add(w["id"])
        defs.setdefault("skills", {}).setdefault(name, {"short": w["short"], "code": "w"})


MAX_FLAT = 7   # rule 23: more steps than this need stages
# a stage title is for someone who doesn't know the system: no file names, code_words, `code`, ABBREVIATIONS or JoinedNames
JARGON = re.compile(r"`|\b\w+\.(py|js|json|md)\b|\b\w+_\w+\b|\b[A-Z]{2,}\b(?<!\bUK)(?<!\bGB)|\b[A-Za-z]*[a-z][A-Z]\w*")
NOTE_KINDS = {"stop": "can stop", "ask": "asks you"}


def stage_notes(w):
    """Give each stage its step count and notes, from the options in it that stop or ask (never hand-written)."""
    for s in w.get("stages") or []:
        mine = [st for st in w["steps"] if st.get("stage") == s.get("key")]
        s["n"] = len(mine)
        notes = []
        for st in mine:
            for a in st.get("alts", []):
                if a.get("k") in NOTE_KINDS:
                    then = a.get("then", "")
                    notes.append(f"{a.get('when', '')}: {then[:1].lower() + then[1:]}")
        s["notes"] = notes


def summaries(defs):
    """The one line the Workflow Viewer's header leads with: what the skill does, in plain words.
    A skill's Definition block `summary:` wins; until it has one, the line in the top-level `summaries`
    ("workflow:<id>" / "trigger:<key>") is used. Kept apart from each workflow, so a new line never makes it a draft."""
    lines = defs.pop("summaries", {}) or {}
    def from_skill(name):
        s = (entries.definition(name) or {}).get("summary") if name else None
        return str(s).strip().strip('"') if s else ""
    for w in defs["workflows"]:
        own = str(w.get("summary") or "").strip()  # a draft's own line, until it is created
        w["summary"] = from_skill(w.get("skill")) if len([x for x in defs["workflows"] if x.get("skill") == w.get("skill")]) == 1 else ""
        w["summary"] = w["summary"] or lines.get("workflow:" + w["id"], "") or own
    for k, e in (defs.get("entries") or {}).items():
        e["summary"] = from_skill(e.get("skill")) or lines.get("trigger:" + k, "")
        if not e["summary"]:
            print(f"WARN trigger {k}: no summary; its step line falls back to its description. Add \"trigger:{k}\" to "
                  "summaries: one sentence naming the source, the window and what it keeps (rule 31)")
    for w in defs["workflows"]:
        sk = w.get("skill") or (w.get("match") or {}).get("skill") or ""
        if sk.startswith("core-") or w.get("category") == "new" and not w.get("steps"):
            continue
        if not w["summary"]:
            print(f"WARN {w['id']}: no summary; the Overview falls back to its description's first sentence. Add "
                  f"\"workflow:{w['id']}\" to summaries (rule 31)")
        if not w.get("stages") and len(w.get("steps") or []) <= 7:
            miss = [x.get("title") or x.get("key") for x in w.get("steps") or [] if x.get("type") != "dec" and not x.get("makes")]
            if miss:
                print(f"WARN {w['id']}: steps with no makes (2 to 5 words on their line, rule 23): {', '.join(miss)}")


def page_lines(defs):
    """Examples and each path's results live apart from the workflows (top-level "examples" and "results", like
    "summaries"), so writing or editing them never turns a workflow into a draft. Copied in here for the page."""
    exs, rss = defs.pop("examples", {}) or {}, defs.pop("results", {}) or {}
    D = defs.get("dispatcher") or {}
    for w in defs["workflows"]:
        key = "workflow:" + w["id"]
        if key in exs:
            w["examples"] = exs[key]
        for p in w.get("simulated", []):
            if p.get("label") in (rss.get(key) or {}):
                p["results"] = rss[key][p["label"]]
    for k, e in (defs.get("entries") or {}).items():
        if "trigger:" + k in exs:
            e["examples"] = exs["trigger:" + k]
    for p in D.get("simulated", []):
        r = rss.get("trigger:" + (p.get("entry") or "all")) or {}
        if p.get("label") in r:
            p["results"] = r[p["label"]]
    known = {"workflow:" + w["id"] for w in defs["workflows"]} | {"trigger:" + k for k in (defs.get("entries") or {})} | {"trigger:all"}
    return [f"examples/results: {k!r} is not a workflow or trigger on the board" for k in set(exs) | set(rss) if k not in known]


RESULT_KINDS = ("shown", "mail", "next", "file", "inbox", "untouched", "ask", "stop")


def examples_check(defs, errs):
    """Examples (the Examples tab) each name a saved path; a path's results (the outcome box) use known kinds."""
    def paths_of(sims):
        return {p.get("label") for p in sims}
    D = defs.get("dispatcher") or {}
    groups = [(w["id"], w.get("examples") or [], w.get("simulated") or []) for w in defs["workflows"]]
    groups += [("trigger:" + k, e.get("examples") or [], [p for p in D.get("simulated", []) if p.get("entry") == k]) for k, e in (defs.get("entries") or {}).items()]
    for gid, exs, sims in groups:
        labels = paths_of(sims)
        for i, x in enumerate(exs):
            if not x.get("title"):
                errs.append(f"{gid}: example {i + 1} has no title")
            if x.get("path") not in labels:
                errs.append(f"{gid}: example {x.get('title')!r} names path {x.get('path')!r}, which is not one of its paths")
            # rule 31: a title is a chip beside the others, and "ok" is the route's outcome summary
            if x.get("title") and len(str(x["title"]).split()) > 4:
                print(f"WARN {gid}: example {x['title']!r} is over 4 words; it is a chip on the page (rule 29)")
            if not x.get("ok"):
                print(f"WARN {gid}: example {x.get('title')!r} has no ok; it is the route's outcome summary (rule 31)")
        for p in sims:
            for r in p.get("results") or []:
                if r.get("k") not in RESULT_KINDS or not r.get("t"):
                    errs.append(f"{gid}: path {p.get('label')!r} has a result with kind {r.get('k')!r}; use one of {', '.join(RESULT_KINDS)} and a line of text")


BUILD_ERRORS = []   # this build's ERROR lines, for build_status


def main():
    with open(DEFS, encoding="utf-8") as fh:
        defs = json.load(fh)
    merge_errs = []
    merge_user(defs, merge_errs)
    merge_code(defs)
    merge_drafts(defs, merge_errs)
    new_category(defs)
    compose_dispatcher(defs)
    users = {}
    for w in defs["workflows"]:
        own = (w.get("match") or {}).get("skill")
        for st in w["steps"]:
            if (st.get("sk") or "").startswith("shared-") and st["sk"] != own:
                users.setdefault(st["sk"], set()).add(own or w["id"])
    for st in defs["dispatcher"]["steps"]:   # a trigger's get step uses a shared process for that trigger
        if (st.get("sk") or "").startswith("shared-"):
            users.setdefault(st["sk"], set()).add("trigger:" + str((st.get("on") or {}).get("alt", st["key"])))
    for layer, name, _d in entries.skill_dirs():
        if name.startswith("shared-") and len(users.get(name, ())) < 2:
            print(f"WARN {name}: used by {len(users.get(name, ()))} skill(s) on the board; rule 22 puts a process with one user inside that workflow")
    cache = {}
    for step in defs["dispatcher"]["steps"]:
        fill(step, cache)
    for wf in defs["workflows"]:
        for step in wf["steps"]:
            fill(step, cache)
        stage_notes(wf)
    defs.pop("_about", None)
    names(defs)
    attach_history(defs)
    tests_check(defs, merge_errs)
    merge_errs += page_lines(defs)
    examples_check(defs, merge_errs)
    calm_check(defs)
    settings_drawn(defs, merge_errs)
    trigger_logic(defs)
    connections_info(defs, merge_errs)
    attach_side_versions(defs)   # after connections_info: the connections exist and each workflow knows its uses
    step_titles(defs, merge_errs)
    followups(defs, merge_errs)   # before writing: the page links each follow-up both ways
    contract_errs = contracts(defs)   # before writing: fills in needs / gives for the page
    summaries(defs)
    attach_share(defs)
    merge_debug(defs)   # after every check: a debugging copy is someone else's, shown as it came
    defs["built"] = int(time.time())
    cats = defs.get("categories", {})
    unnamed = [w["id"] for w in defs["workflows"] if w.get("category") not in cats or not w.get("short")]
    for w in defs["workflows"]:
        w["unnamed"] = w["id"] in unnamed  # the page flags these instead of guessing a name
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("window.WFDEF=" + json.dumps(defs, ensure_ascii=False) + ";\n")
    errs = merge_errs + contract_errs + check(defs) + layout(defs)
    print(f"Wrote {OUT}")
    for e in errs:
        print("ERROR " + e)
    BUILD_ERRORS[:] = errs
    if errs:
        sys.exit(1)


if __name__ == "__main__":
    import traceback
    import build_status
    try:
        main()
    except SystemExit as e:
        build_status.report("workflows", not e.code, BUILD_ERRORS or ["the build stopped"])
        raise
    except Exception as e:
        tb = traceback.extract_tb(e.__traceback__)[-1]
        build_status.report("workflows", False, [f"{type(e).__name__}: {e} (build_workflows.py line {tb.lineno})"])
        raise
    build_status.report("workflows", True)
