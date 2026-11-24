#!/usr/bin/env python3
"""A short brief for a plain run: one workflow started by its own trigger's phrase ("check the new york times").

Instead of reading the whole dispatcher skill and run rules to work out what to do, Claude gets, in about a thousand
tokens, everything this one run needs: the workflow's skill to read and follow (its markdown is still the source of
every step and decision), its trigger, the connections it uses, its steps' titles and paths, and the exact bookkeeping
commands with this run's ID and names filled in. Anything that isn't a plain run (tests, tries of a new workflow,
reruns, several triggers, changes by hand) still goes through core-dispatcher.

    run_brief.py "<request>" <request run ID>     prints the brief, or nothing when the request isn't a plain run

Read only.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402


TAG_TYPE = {"read": "Online Search/Check", "get": "Online Search/Check", "check": "Online Search/Check",
            "decide": "Sorted", "sort": "Sorted", "keep": "Sorted", "combine": "Combined", "write": "Written",
            "summarise": "Summarised", "draft": "Email Draft Created", "save": "File Changed", "make": "File Changed",
            "build": "File Changed", "download": "File Changed", "send": "Message Sent", "post": "Posted",
            "reply": "Reply Sent", "update": "Updated"}
TYPE_TYPE = {"read": "Online Search/Check", "check": "Online Search/Check", "dec": "Sorted", "send": "Message Sent"}


def step_type(st):
    """The trace type the board expects for a workflow step, from its tag ("Save" -> File Changed)."""
    return (TAG_TYPE.get(str(st.get("tag") or "").lower()) or TYPE_TYPE.get(str(st.get("type") or "").lower())
            or "Step Done")


def _uses(skill_md):
    try:
        txt = open(skill_md, encoding="utf-8").read()
    except OSError:
        return []
    m = re.search(r"^uses:[ \t]*(.*)$((?:\n[ \t]+\S.*)*)", txt, re.M)
    if not m:
        return []
    out = []
    for part in re.split(r"[,\n]", m.group(1) + m.group(2)):
        name = part.strip().split(":")[0].strip().lower()
        if re.match(r"^[a-z0-9][a-z0-9-]*$", name):
            out.append(name)
    return out


# The run reviewer's checks (core-run-reviewer, "Review a run", Steps 2-4), short, so a run reviews itself in one call.
# The reviewer skill stays the source: change them there first.
REVIEW = (
    "check only (a) the path: each step of the path it took done, in order, none from another path, each connection "
    "reached the way it is set up, each write confirmed, the path named as the workflow names it (confirm each drift "
    "fact against what you did; drop one that is only a matter of record, or a page left for the chat to open); and "
    "(b) made twice: a write an earlier try already made for this item (same step, title, recipient or text; a "
    "deleted try counts; an update of it doesn't). At most 5 warnings, most important first, each "
    "{\"title\": up to 6 words, \"detail\": one sentence of up to 20 words, no IDs or file names, \"fix\": up to 12 "
    "words or \"Nothing to change.\", \"step\", \"kind\": missing-step|order|off-path|method|unconfirmed|path-name|"
    "made-twice, \"severity\": warn (something to do) | info (fix is Nothing to change)}. Save them in one call: "
    "`python3 -I {S}/suggestions.py add <the run> --items '<the list as JSON>'` (an empty list when nothing is "
    "wrong), then `python3 -I {S}/run_card.py <the run> --check` gives the review's one line."
)

def approval(R):
    """A step that asks for the user's yes is never asked in the chat (core-dispatcher, Approvals): the Approve
    automatically switch says yes for them, or parks the run on the Inbox."""
    try:
        sys.path.insert(0, os.path.join(paths.SKILLS, "core-dispatcher"))
        import item_id
        on = item_id.auto_approve()
    except Exception:
        on = True
    if on:
        return ("A step that asks for the user's yes is never asked: Approve automatically is on, so log it "
                f"`{R} line <run> '{{\"type\":\"Approved Automatically\",\"step\":\"<its title>\",\"status\":"
                "\"done\",\"result\":\"Approved automatically: <what it does>\",\"ask\":{\"q\":\"<the question>\","
                "\"show\":{<to, a one-line gist>}},\"because\":\"Approve automatically is on\"}'` and carry on as if "
                "the user said yes.")
    return ("A step that asks for the user's yes is never asked: Approve automatically is off, so log it "
            f"`{R} line <run> '{{\"type\":\"Asked You\",\"step\":\"<its title>\",\"status\":\"needs_user\","
            "\"result\":\"Waiting for your yes on the Inbox\",\"ask\":{\"q\":\"<the question>\",\"show\":{<to, a "
            "one-line gist>},\"yes\":\"<2-4 words>\",\"no\":\"<2-4 words>\"},\"io\":{\"out\":{<everything the next "
            "step needs: recipient, the finished message>}}}'`, end that item `--status needs_user` with "
            "`\"attention\":\"action\"`, `\"waiting\":\"You: yes or no to <the action>\"`, `\"next\":\"answer it on "
            "the Inbox\"` and `--path` the path a yes takes, then go on with the next item.")


def brief(request, run):
    import entries
    import path_check
    try:
        import commands
        c = commands.parse(request)
        request = c.get("means") or c.get("trigger") or request
    except Exception:
        pass
    low = request.lower()
    if re.search(r"\b(test|try|rerun|run workflow|run trigger|answer|skip|mark|delete|turn|context:|scheduled:|as a test|for real)\b", low):
        return ""
    e = None
    for x in entries.load():
        if x.get("skill") == "core-dispatcher":
            continue
        if any(len(p.split()) >= 2 and re.search(r"\b" + re.escape(p) + r"\b", low) for p in x.get("triggers") or []):
            e = x
            break
    if not e or str(e.get("category", "")).lower() == "new":
        return ""
    W = path_check.load_defs() or {}
    d = path_check.find_def(W, e["skill"]) or {}
    if not d:
        return ""
    md = entries.skill_file(e["skill"])[1] or ""
    uses = [u for u in _uses(md) if u not in ("web", "browser")]
    ent = (W.get("entries") or {}).get(e["id"]) or {}
    tsteps = [s.get("title") for s in ent.get("steps") or [] if s.get("title")]
    loops = d.get("loops") or []
    inside = {k for lp in loops for k in (lp.get("steps") or [])}
    steps = d.get("steps") or []
    tt = lambda st: f'{st.get("title")} ({step_type(st)})'
    loop_t = [tt(s) for s in steps if s.get("key") in inside]
    once_t = [tt(s) for s in steps if s.get("key") not in inside and not s.get("on")]
    pths = [p.get("label") for p in d.get("simulated") or [] if p.get("label")]
    asks = bool(re.search(r"(?i)send it\?|asks first: yes|your yes|wait for the answer", open(md, encoding="utf-8").read()))
    S, I = paths.rel(HERE), paths.rel(os.path.join(paths.SKILLS, "core-dispatcher", "item_id.py"))
    R = f"python3 -I {S}/run_item.py"
    q = lambda t: json.dumps(t, ensure_ascii=False)
    lines = [
        f"Plain run of the workflow {d.get('short') or e['skill']} (trigger `{e['id']}`, request {run}). This brief "
        f"replaces reading the dispatcher skill and the run rules for this run: follow it. Something here doesn't fit "
        f"(a connection isn't set up, the trigger can't read its source): stop there and say why.",
        f"1. Read and follow its skill, `{paths.rel(md)}`: its `## Trigger` gets and keeps the items, its steps do the "
        f"work, exactly as written; every decision in it is yours to make.",
        (f"2. Connections first: `python3 -I {S}/connections.py status {' '.join(uses)}`; any not `ok`: stop and say "
         f"which." if uses else "2. It reads only the public web: no connection to check."),
        f"3. Log the trigger's read and keep on the request, each the moment it's done: `{R} line {run} "
        f"'{{\"entry_match\":\"{e['id']}\",\"why\":\"<one line>\",\"wstep\":null}}'`, then one line per step "
        f"{q(tsteps)}: `{R} line {run} '{{\"type\":\"Online Search/Check\",\"step\":\"<its title>\",\"result\":"
        f"\"<what it found>\",\"status\":\"done\",\"io\":{{\"out\":{{\"seen\":[\"<each item: title · time · "
        f"kept|stopped: why>\"]}}}}}}'`.",
        f"4. Each kept item: `python3 -I {I} check {e['id']} <item key>`. `link`: `{R} line {run} '{{\"type\":\"Already "
        f"Done\",\"step\":\"seen → <wf>\",\"label\":\"<name>\",\"link_wf\":\"<wf>\",\"link_run\":\"<its run>\","
        f"\"result\":\"Already handled in an earlier run\",\"status\":\"skipped\",\"wstep\":null}}'`. `run`: carries on.",
    ]
    stepline = (f"`{R} line <run> '{{\"type\":\"<its type>\",\"step\":\"<the title, word for word>\",\"result\":"
                f"\"<what it found>\",\"because\":\"<why>\",\"status\":\"done\"}}'`")
    if loops:
        lines += [
            f"5. One run for all of them: `{R} batch {run} --entry {e['id']} --skill {e['skill']} --label \"<what it "
            f"covers>\"` (prints run-…), then `{R} queue {run} --entry {e['id']} --skill {e['skill']} --items "
            f"'[{{\"wf\",\"item\",\"label\",\"input\"}}]'` for every item to run.",
            f"6. Each item, one at a time: `{R} start {run} --wf <wf> --attempt <n> --entry {e['id']} --item <item> "
            f"--label \"<its own name>\" --skill {e['skill']} --input '<its fields>' --found \"<what it is, one line>\" "
            f"--batch <run-…>`, then its steps {q(loop_t)} (title, then its type) each logged as it finishes: "
            f"{stepline}, then `{R} end <wf>-a<n> --status done '{{\"summary\":\"<one line>\",\"verdict\":\"<the "
            f"answer>\",\"attention\":\"none\"}}' --path \"<one of {q(pths)}>\"`.",
            f"7. The steps that run once, {q(once_t)}, logged on run-… the same way (a step that made something adds "
            f"`\"made\":{{\"name\",\"kind\",\"href\"}}`), then `{R} end run-… --status done '{{\"summary\":\"<what "
            f"the run did>\",\"verdict\":\"<12 words>\",\"flow\":[\"<2-4 words>\",…],\"attention\":\"none\"}}'`.",
        ]
    else:
        lines += [
            f"5. Each item, one at a time: `{R} start {run} --wf <wf> --attempt <n> --entry {e['id']} --item <item> "
            f"--label \"<its own name>\" --skill {e['skill']} --input '<its fields>' --found \"<what it is>\"`, its "
            f"steps {q([tt(s) for s in steps])} (title, then its type) each logged as it finishes ({stepline}), then "
            f"`{R} end <wf>-a<n> --status done '{{\"summary\",\"verdict\",\"attention\":\"none\"}}' --path \"<one of "
            f"{q(pths)}>\"`.",
        ]
    lines += [
        f"{sum(1 for x in lines if re.match(r'^[0-9]+[.]', x)) + 1}. End the request: `{R} end {run} --status done "
        f"'{{\"summary\":\"<what the request did>\",\"verdict\":\"<12 words>\",\"attention\":\"none\"}}'`. Then "
        f"`python3 -I {S}/review_gate.py <the run>`: `\"review\": false` → it's reviewed; `true` → review it yourself "
        f"now, from the run you just did and the gate's `facts` (core-run-reviewer's \"Review a run\", in short): "
        f"{REVIEW.replace('{S}', S)}",
        "Plain words in every result; log each step only once it has finished; no passwords, tokens or full email "
        "bodies." + (" " + approval(R) if asks else ""),
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    print(brief(sys.argv[1], sys.argv[2]))
