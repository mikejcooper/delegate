#!/usr/bin/env python3
"""Delegate's commands: every request a user can send, in one table.

Every command is `delegate <verb> <thing> <name>`, with any detail after a colon:
    delegate run workflow wework-invoices: the newest invoice
    delegate share workflow wework-invoices: issue wf-1a2b3c4d-a1 wf-5e6f7a8b-a1
A workflow's own phrases ("check my email") are the user's words and need no prefix; "delegate check my email"
works too. The older phrasings ("run workflow manager", "share the update of workflow X") keep working.

Each row says which part of Delegate does it (`skill`) and what it `means` in the older phrasing that part's
instructions are written in, so the prompt hook can tell Claude exactly what was asked (prompt), and the board and
the docs share one list (help).

    commands.py parse "<text>"     JSON: the command, its skill and its meaning ({} when it isn't one)
    commands.py help [--md]        the list, grouped, as a table
    commands.py prompt             the prompt hook (JSON on stdin): for a delegate command, one line for Claude
"""
import json
import re
import sys

N = r"(?P<name>[A-Za-z0-9][\w.-]*)"           # a workflow, trigger, connection, category or debugging copy
WF = r"(?P<id>wf-[0-9a-f]{8}(?:-a\d+)?)"       # an item's run
SG = r"(?P<id>sg-[0-9a-z-]+)"                  # a run reviewer's warning
KIND = r"(?P<kind>workflow|trigger|connection)"
D = r"(?:\s*:\s*(?P<detail>.+))?"              # ": anything after"

# (group, form shown to people, regex on the words after "delegate", skill, meaning in the older phrasing)
TABLE = [
    ("Dashboard", "delegate dashboard", r"(?:open\s+)?(?:the\s+)?dashboard", "", "open the dashboard"),
    ("Dashboard", "delegate start", r"start", "", "/workflow-manager:start"),
    ("Dashboard", "delegate help", r"help|commands", "", "list Delegate's commands"),

    ("Run", "delegate run", r"run", "core-dispatcher", "run workflow manager"),
    ("Run", "delegate run all", r"run\s+all(?:\s+triggers)?", "core-dispatcher", "run all triggers"),
    ("Run", "delegate run trigger <name>", r"run\s+trigger\s+" + N, "core-dispatcher", "run trigger {name}"),
    ("Run", "delegate run workflow <name>: <item>", r"run\s+workflow\s+" + N + D, "core-dispatcher",
     "run workflow {name}{ on detail}"),
    ("Run", "delegate run <workflow>: for real/as a test", r"run\s+(?!(?:all|trigger|workflow)(?:\s|$))" + N + D,
     "core-dispatcher", "{trigger}{ detail}"),
    ("Run", "delegate rerun <wf-…>: for real/as a test", r"rerun\s+(?:workflow\s+)?" + WF + D, "core-dispatcher",
     "rerun workflow {id}{ detail}"),
    ("Run", "delegate test workflow <name>: end to end", r"test\s+workflow\s+" + N + D, "core-dispatcher",
     "test workflow {name}{ detail}"),
    ("Run", "delegate test trigger <name>", r"test\s+trigger\s+" + N, "core-dispatcher", "test trigger {name}"),

    ("Inbox", "delegate answer <wf-…>: yes/no", r"answer\s+" + WF + r"\s*:\s*(?P<detail>.+)", "core-dispatcher",
     "answer {id}: {detail}"),
    ("Inbox", "delegate skip <wf-…>", r"skip\s+" + WF, "core-dispatcher", "skip {id}"),
    ("Inbox", "delegate done <wf-…>", r"(?:done|mark)\s+" + WF + r"(?:\s+done)?", "core-dispatcher", "mark {id} done"),
    ("Inbox", "delegate mark <wf-…>: needs you/not run", r"mark\s+" + WF + r"\s*:\s*(?P<detail>.+)",
     "core-dispatcher", "mark {id} {detail}"),
    ("Inbox", "delegate delete <wf-…>", r"delete\s+" + WF, "core-dispatcher", "delete {id}"),
    ("Inbox", "delegate delete request <dispatch-…>", r"delete\s+request\s+(?P<id>dispatch-[\w-]+)", "core-dispatcher",
     "delete request {id}"),
    ("Inbox", "delegate turn on/off <setting>", r"turn\s+(?P<detail>on|off)\s+(?P<name>.+)", "core-dispatcher",
     "turn {name} {detail}"),
    ("Inbox", "delegate keep <wf-…>: test", r"keep\s+" + WF + r"(?:\s*:\s*(?:as\s+a\s+)?test)?", "core-architect",
     "keep {id} as a test"),

    ("Build", "delegate add workflow: <what you want>", r"add\s+(?:a\s+)?workflow\s*:\s*(?P<detail>.+)",
     "core-architect", "Add a workflow: {detail}"),
    ("Build", "delegate create workflow <name>", r"create\s+(?:the\s+new\s+)?workflow\s+" + N, "core-architect",
     "create the new workflow {name}"),
    ("Build", "delegate change workflow <name>: <what to change>", r"change\s+" + KIND + r"\s+" + N + D,
     "core-architect", "change {kind} {name}: {detail}"),
    ("Build", "delegate undo workflow <name>", r"undo\s+" + KIND + r"\s+" + N, "core-architect",
     "undo the last change to {kind} {name}"),
    ("Build", "delegate discard workflow <name>", r"discard\s+" + KIND + r"\s+" + N, "core-architect",
     "discard the draft of {kind} {name}"),
    ("Build", "delegate add examples workflow <name>", r"add\s+examples\s+(?:to\s+)?workflow\s+" + N,
     "core-architect", "add examples to workflow {name}"),
    ("Build", "delegate add tests workflow <name>", r"add\s+tests\s+(?:for\s+)?workflow\s+" + N, "core-architect",
     "add tests for workflow {name}"),
    ("Build", "delegate import <path>", r"import\s+(?P<detail>.+)", "core-architect", "import {detail}"),

    ("Publish", "delegate validate workflow <name>", r"validate\s+" + KIND + r"\s+" + N, "core-architect",
     "validate {kind} {name}"),
    ("Publish", "delegate publish workflow <name>: without validating", r"publish\s+" + KIND + r"\s+" + N + D,
     "core-architect", "publish {kind} {name}{ detail}"),
    ("Publish", "delegate restore workflow <name>: v2", r"restore\s+" + KIND + r"\s+" + N + r"\s*:\s*(?P<detail>v\d+)",
     "core-architect", "restore {kind} {name} to {detail}"),
    ("Publish", "delegate delete workflow <name>", r"delete\s+" + KIND + r"\s+" + N, "core-architect",
     "delete {kind} {name}"),

    ("Names", "delegate rename workflow <name>: <new name>",
     r"rename\s+(?P<kind>workflow|connection|category)\s+" + N + r"\s*:\s*(?P<detail>.+)", "core-renamer",
     "rename {kind} {name} to {detail}"),
    ("Names", "delegate move workflow <name>: <category>", r"move\s+workflow\s+" + N + r"\s*:\s*(?P<detail>.+)",
     "core-renamer", "move workflow {name} to {detail}"),
    ("Names", "delegate tidy names", r"tidy(?:\s+up)?(?:\s+the)?\s+names", "core-renamer",
     "tidy up the names of my workflows"),

    ("Schedules", "delegate schedule workflow <name>: weekdays 08:00",
     r"schedule\s+workflow\s+" + N + r"\s*:\s*(?P<detail>.+)", "core-architect", "schedule workflow {name}: {detail}"),
    ("Schedules", "delegate pause workflow <name>", r"pause\s+(?:schedule\s+)?workflow\s+" + N, "core-architect",
     "pause schedule workflow {name}"),
    ("Schedules", "delegate resume workflow <name>", r"resume\s+(?:schedule\s+)?workflow\s+" + N, "core-architect",
     "resume schedule workflow {name}"),
    ("Schedules", "delegate unschedule workflow <name>", r"unschedule\s+workflow\s+" + N, "core-architect",
     "remove schedule workflow {name}"),

    ("Connections", "delegate set up connection <name>", r"(?:set\s*up|connect)\s+(?:connection\s+)?" + N,
     "core-connections", "set up connection {name}"),
    ("Connections", "delegate check connection <name>", r"check\s+connection\s+" + N, "core-connections",
     "check connection {name}"),
    ("Connections", "delegate fix connection <name>", r"fix\s+connection\s+" + N, "core-connections",
     "fix connection {name}"),
    ("Connections", "delegate check connections", r"check\s+connections", "core-connections",
     "what needs setting up?"),

    ("Reviews", "delegate review <wf-…>", r"review\s+(?:run\s+)?" + WF, "core-run-reviewer", "review run {id}"),
    ("Reviews", "delegate dismiss <sg-…>", r"dismiss\s+(?:warning\s+)?" + SG, "core-run-reviewer",
     "dismiss warning {id}"),
    ("Reviews", "delegate fix <sg-…>", r"fix\s+(?:warning\s+)?" + SG, "core-architect", "fix warning {id}"),

    ("Share", "delegate share workflow <name>", r"share\s+workflow\s+" + N + r"\s*$", "core-sharer",
     "share workflow {name}"),
    ("Share", "delegate share workflow <name>: update", r"share\s+workflow\s+" + N + r"\s*:\s*update\s*$",
     "core-sharer", "share the update of workflow {name}"),
    ("Share", "delegate share workflow <name>: issue <wf-…> <wf-…>",
     r"share\s+workflow\s+" + N + r"\s*:\s*issue\b\s*(?P<detail>.*)", "core-sharer",
     "share an issue with workflow {name}: {detail}"),
    ("Share", "delegate pick workflow <name>: c1 mine/theirs/merge",
     r"pick\s+workflow\s+" + N + r"\s*:\s*(?P<id>c\d+)\s+(?P<detail>mine|theirs|merge)", "core-sharer",
     "{pick} of {id} in workflow {name}"),
    ("Share", "delegate replay debug <name>: <wf-…>", r"replay\s+debug\s+" + N + D, "core-sharer",
     "replay a run of debug {name}{: detail}"),
    ("Share", "delegate share debug <name>: fix", r"share\s+debug\s+" + N + r"(?:\s*:\s*fix)?", "core-sharer",
     "share the fixed version of debug {name}"),
    ("Share", "delegate delete debug <name>", r"delete\s+debug\s+" + N, "core-sharer", "remove debug {name}"),
]
PICK = {"mine": "keep my side", "theirs": "take the update's side", "merge": "merge both sides"}
COMPILED = [(g, f, re.compile(r"^\s*" + rx + r"\s*[.!]?\s*$", re.I), sk, m) for g, f, rx, sk, m in TABLE]
BATCH = re.compile(r"^(run\s+workflow\s+manager\s+(with\s+these|no\s+question)|run\s+these\s+\d+\s+items\b"
                   r"|(skip|mark|delete)\s+these\s+(items|requests)\b)", re.I)
PREFIX = re.compile(r"^\s*delegate\b[\s,:]*", re.I)


def _means(template, gd):
    def opt(m):   # "{ on detail}" / "{: detail}" / "{ detail}": the words only when there is a detail
        return (m.group(1) + gd["detail"]) if gd.get("detail") else ""
    t = re.sub(r"\{([ :]+(?:on )?)detail\}", opt, template)
    if re.match(r"^(for real|as a test)$", (gd.get("detail") or "").strip(), re.I):
        t = t.replace(" on " + gd["detail"], " " + gd["detail"].strip())
    if "{trigger}" in t:   # "delegate run <workflow>": its own trigger, which reads what's new and runs each item
        t = t.replace("{trigger}", trigger_of(gd.get("name") or ""))
    if "{pick}" in t:
        t = t.replace("{pick}", PICK.get((gd.get("detail") or "").lower(), "pick"))
    for k, v in gd.items():
        t = t.replace("{" + k + "}", (v or "").strip())
    return t


def parse(text):
    """{"command", "skill", "means", "group", "form"} for a delegate command; {"trigger": phrase} for "delegate
    <a workflow's own phrase>"; {"unknown": words} for "delegate <something else>"; {} when it isn't one at all."""
    text = " ".join(str(text or "").split())
    m = PREFIX.match(text)
    if not m:
        return {}
    rest = text[m.end():].strip()
    if not rest:
        return {"command": "delegate dashboard", "skill": "", "means": "open the dashboard", "group": "Dashboard",
                "form": "delegate dashboard"}
    for g, f, rx, sk, mean in COMPILED:
        mm = rx.match(rest)
        if mm:
            return {"command": text, "skill": sk, "means": _means(mean, mm.groupdict()), "group": g, "form": f}
    if BATCH.match(rest):   # the Inbox's lines for several items or triggers at once
        return {"command": text, "skill": "core-dispatcher", "means": rest, "group": "Inbox", "form": "delegate " + rest[:40]}
    return {"trigger": rest} if _is_trigger(rest) else {"unknown": rest}


def trigger_of(name):
    """The request that runs a workflow now, by any of its names (its skill, the skill without "workflow-", or its
    trigger's id): its trigger's first phrase; with no trigger, "run workflow <name>"."""
    want = name.lower().strip()
    try:
        import os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import entries
        for e in entries.load():
            sk = str(e.get("skill") or "").lower()
            names = {sk, re.sub(r"^workflow-", "", sk), str(e.get("id") or "").lower()}
            parts = re.sub(r"^workflow-", "", sk).split("-", 1)
            if len(parts) == 2:
                names.add(parts[1])   # without its category: "wework-invoices"
            if want in names and e.get("triggers"):
                return e["triggers"][0]
    except Exception:
        pass
    return "run workflow " + name


def _is_trigger(words):
    try:
        import os
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import entries
        pat = entries.trigger_pattern()
        return bool(pat and pat.search(words))
    except Exception:
        return False


def help_rows():
    out = {}
    for g, f, _rx, _sk, _m in TABLE:
        out.setdefault(g, []).append(f)
    return out


def help_md():
    lines = ["| Group | Commands |", "|---|---|"]
    for g, fs in help_rows().items():
        lines.append(f"| {g} | " + " · ".join(f"`{f}`" for f in fs) + " |")
    lines.append("| Your workflows | their own phrases, e.g. `check my email` (or `delegate check my email`) |")
    return "\n".join(lines)


def prompt_note(text):
    """The line the prompt hook adds for Claude, or "" when the request isn't a delegate command."""
    p = parse(text)
    if not p:
        return ""
    if p.get("unknown") is not None:
        return ("Delegate: \"delegate " + p["unknown"] + "\" isn't one of Delegate's commands. Say so in one line, "
                "suggest the closest command from this list, and offer the list (\"delegate help\"):\n" + help_md())
    if p.get("trigger"):
        return (f"Delegate command: \"{p['trigger']}\" is a workflow's own phrase. Treat the request as exactly "
                f"\"{p['trigger']}\" (the dispatcher, core-dispatcher).")
    if p["form"] == "delegate help":
        return ("Delegate command: delegate help. Show the user this list as it is, under one line saying every "
                "command starts with \"delegate\", and that a workflow's own phrase works with or without it:\n" + help_md())
    if not p["skill"]:
        return ""   # the dashboard and start: welcome.py answers those
    return (f"Delegate command ({p['form']}). It means \"{p['means']}\": handle it exactly as that request, "
            f"with the {p['skill']} skill. The user typed: \"{p['command']}\".")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "parse":
        print(json.dumps(parse(" ".join(sys.argv[2:])), indent=1))
    elif cmd == "help":
        if "--md" in sys.argv:
            print(help_md())
        else:
            for g, fs in help_rows().items():
                print(g)
                for f in fs:
                    print("  " + f)
    elif cmd == "prompt":
        try:
            data = json.load(sys.stdin)
        except ValueError:
            return
        note = prompt_note(str(data.get("prompt", "")))
        if note:
            print(note)   # plain text: the prompt hook's other lines are added to Claude's context the same way
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
