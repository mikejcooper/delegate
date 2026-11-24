#!/usr/bin/env python3
"""Test of Delegate's commands (commands.py) and the board's translation of its buttons (topbar.js cmd()).

  1  every "delegate …" form parses to its skill and means the older request that skill knows
  2  a workflow's own phrase, with "delegate" in front, is a trigger; an unknown one says so; plain words are not commands
  3  the prompt hook: one line for Claude naming the skill; the help list; nothing for other requests
  4  the dispatcher's run trace starts for delegate run commands and not for others; the dashboard phrases open it
  5  every command a board button copies, in its older phrasing, turns into a delegate command that parses (node)

    python3 -I test_commands.py
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
UI = os.path.dirname(HERE)
SCRIPTS = os.path.join(UI, "scripts")
sys.path.insert(0, SCRIPTS)
import commands  # noqa: E402

FAILS = []


def ok(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


CASES = [
    ("delegate run", "core-dispatcher", "run workflow manager"),
    ("delegate run all", "core-dispatcher", "run all triggers"),
    ("delegate run triggers email, news", "core-dispatcher", "run workflow manager with these triggers, no question: email, news."),
    ("delegate run triggers email: Context: only today's", "core-dispatcher",
     "run workflow manager with these triggers, no question: email. Context: only today's"),
    ("delegate run triggers news: (scheduled: weekdays 08:00)", "core-dispatcher",
     "run workflow manager with these triggers, no question: news. (scheduled: weekdays 08:00)"),
    ("delegate run workflow wework-invoices: the newest invoice", "core-dispatcher",
     "run workflow wework-invoices on the newest invoice"),
    ("delegate run workflow wework-invoices: as a test", "core-dispatcher", "run workflow wework-invoices as a test"),
    ("delegate rerun wf-1a2b3c4d: for real", "core-dispatcher", "rerun workflow wf-1a2b3c4d for real"),
    ("delegate test workflow bbc-article: end to end", "core-dispatcher", "test workflow bbc-article end to end"),
    ("delegate answer wf-1a2b3c4d: yes", "core-dispatcher", "answer wf-1a2b3c4d: yes"),
    ("delegate done wf-1a2b3c4d", "core-dispatcher", "mark wf-1a2b3c4d done"),
    ("delegate turn off Run each item once", "core-dispatcher", "turn Run each item once off"),
    ("delegate add workflow: file each invoice", "core-architect", "Add a workflow: file each invoice"),
    ("delegate undo workflow wework-invoices", "core-architect", "undo the last change to workflow wework-invoices"),
    ("delegate publish workflow wework-invoices: without validating", "core-architect",
     "publish workflow wework-invoices without validating"),
    ("delegate restore connection gmail: v2", "core-architect", "restore connection gmail to v2"),
    ("delegate rename category finance: Money", "core-renamer", "rename category finance to Money"),
    ("delegate unschedule workflow wework-invoices", "core-architect", "remove schedule workflow wework-invoices"),
    ("delegate connect slack", "core-connections", "set up connection slack"),
    ("delegate check connections", "core-connections", "what needs setting up?"),
    ("delegate review wf-1a2b3c4d-a1", "core-run-reviewer", "review run wf-1a2b3c4d-a1"),
    ("delegate share workflow wework-invoices: update", "core-sharer", "share the update of workflow wework-invoices"),
    ("delegate share workflow x: issue wf-1a2b3c4d-a1 wf-5e6f7a8b-a1", "core-sharer",
     "share an issue with workflow x: wf-1a2b3c4d-a1 wf-5e6f7a8b-a1"),
    ("delegate pick workflow x: c2 merge", "core-sharer", "merge both sides of c2 in workflow x"),
    ("delegate delete debug x-20261124", "core-sharer", "remove debug x-20261124"),
    ("Delegate, run", "core-dispatcher", "run workflow manager"),
]


def main():
    # 1
    for text, skill, means in CASES:
        p = commands.parse(text)
        ok(p.get("skill") == skill and p.get("means") == means, f"1 {text!r} → {skill}: {means!r} (got {p.get('skill')!r}: {p.get('means')!r})")
    forms = [f for _g, f, *_ in commands.TABLE]
    ok(len(forms) == len(set(forms)), "1 every form is listed once")
    ok(all(f.startswith("delegate ") for f in forms), "1 every form starts with delegate")

    # 1b: delegate run <workflow> runs its own trigger, by any of its names
    import entries
    wf = next((e for e in entries.load() if e.get("triggers") and str(e.get("skill", "")).startswith("workflow-")), None)
    if wf:
        sk = wf["skill"]
        for name in (sk, sk[len("workflow-"):]):
            p = commands.parse("delegate run " + name)
            ok(p.get("skill") == "core-dispatcher" and p.get("means") == wf["triggers"][0],
               f"1b \"delegate run {name}\" runs its trigger: {wf['triggers'][0]!r} (got {p.get('means')!r})")
        p = commands.parse("delegate run " + sk + ": as a test")
        ok(p.get("means") == wf["triggers"][0] + " as a test", "1b and \": as a test\" tries it as a test")
    ok(commands.parse("delegate run no-such-workflow").get("means") == "run workflow no-such-workflow",
       "1b an unknown name falls back to running the workflow by name")
    ok(commands.parse("delegate run all").get("means") == "run all triggers", "1b \"run all\" is still every trigger")

    # 2
    real = entries.trigger_pattern()
    if real:
        phrase = next(iter(e["triggers"][0] for e in entries.load() if e.get("triggers")), None)
        if phrase:
            p = commands.parse("delegate " + phrase)
            ok(p.get("trigger") == phrase, f"2 \"delegate {phrase}\" is that workflow's own phrase")
    ok("unknown" in commands.parse("delegate frobnicate the widgets"), "2 an unknown delegate command says so")
    ok(commands.parse("check my email") == {} and commands.parse("please delegate this to Sam") == {},
       "2 words without the prefix are not commands")
    ok(commands.parse("delegate").get("form") == "delegate dashboard", "2 \"delegate\" alone opens the dashboard")

    # 3
    note = commands.prompt_note("delegate share workflow x: update")
    ok("core-sharer" in note and "share the update of workflow x" in note, "3 the hook names the skill and the meaning")
    h = commands.prompt_note("delegate help")
    ok("| Share |" in h and "delegate run" in h, "3 delegate help gives the list")
    ok(commands.prompt_note("what's the weather") == "", "3 nothing for other requests")
    ok(all("|" not in f for f in forms), "3 no form has a | that would break the help table")

    # 4
    import live
    import welcome
    ok(live.dispatch_match("delegate run") and live.dispatch_match("delegate skip wf-1a2b3c4d"),
       "4 delegate run commands start a run trace")
    ok(not live.dispatch_match("delegate share workflow x") and not live.dispatch_match("delegate help"),
       "4 other delegate commands don't")
    ok(live.dispatch_match("run workflow manager"), "4 the older phrasing still does")
    ok(all(welcome.ASKS.match(t) for t in ("delegate", "delegate dashboard", "open delegate dashboard", "/dashboard",
                                           "open the dashboard")), "4 the dashboard phrases, old and new, open it")
    ok(bool(welcome.START.match("delegate start")), "4 delegate start gives the welcome")

    # 5
    node = shutil.which("node")
    if not node:
        print("skip 5 (no node)")
    else:
        olds = ["run workflow manager", "run all triggers", "run workflow wework-invoices on the newest invoice",
                "rerun workflow wf-1a2b3c4d-a1", "rerun workflow wf-1a2b3c4d for real", "test workflow bbc-article end to end",
                "test trigger wework", "discard the draft of workflow x", "undo the last change to trigger y",
                "validate workflow x", "publish workflow x without validating", "publish connection gmail",
                "restore workflow x to v2", "delete workflow x", "tidy up the names of my workflows",
                "change schedule workflow x: weekdays 08:00", "pause schedule workflow x", "remove schedule workflow x",
                "set up connection gmail", "carry on setting up connection gmail", "check connection gmail",
                "fix connection gmail", "create the new workflow invoice-filer", "add examples to workflow x",
                "add tests for workflow x", "answer wf-1a2b3c4d: no", "skip wf-1a2b3c4d  (INV-2041)",
                "mark wf-1a2b3c4d done  (INV-2041)", "mark wf-1a2b3c4d needs you  (INV-2041)",
                "delete wf-1a2b3c4d  (INV-2041) from the board", "delete request dispatch-1432-1",
                "turn Run each item once off", "keep wf-1a2b3c4d-a1 as a test", "review run wf-1a2b3c4d-a1",
                "dismiss warning sg-1a2b", "fix warning sg-1a2b", "share workflow x", "share the update of workflow x",
                "share an issue with workflow x: wf-1a2b3c4d-a1", "keep my side of c1 in workflow x",
                "take the update's side of c1 in workflow x", "merge both sides of c1 in workflow x",
                "replay a run of debug x-1", "share the fixed version of debug x-1", "remove debug x-1",
                "run these 3 items:\n- wf-1a2b3c4d  INV-1", "skip these items:\n- wf-1a2b3c4d  INV-1"]
        js = ("const fs=require('fs');const src=fs.readFileSync(process.argv[1],'utf8');"
              "eval(src.slice(src.indexOf('var KD='),src.indexOf('function fixCmds'))+';global.cmd=cmd;');"
              "const L=JSON.parse(fs.readFileSync(0,'utf8'));console.log(JSON.stringify(L.map(cmd)));")
        r = subprocess.run([node, "-e", js, os.path.join(UI, "topbar.js")], input=json.dumps(olds), capture_output=True, text=True)
        news = json.loads(r.stdout) if r.returncode == 0 else []
        ok(len(news) == len(olds), "5 the board's translation runs")
        for o, n in zip(olds, news):
            p = commands.parse(n)
            ok(n.startswith("delegate ") and bool(p.get("skill")), f"5 {o.splitlines()[0]!r} → {n.splitlines()[0]!r}")
        r = subprocess.run([node, "-e", js, os.path.join(UI, "topbar.js")],
                           input=json.dumps(["check wework invoices for real", "import it", "change the import: x"]),
                           capture_output=True, text=True)
        ok(json.loads(r.stdout) == ["check wework invoices for real", "import it", "change the import: x"],
           "5 a workflow's phrase and replies to Claude are left as they are")

    print()
    print("FAILED: " + str(len(FAILS)) if FAILS else "all passed")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
