#!/usr/bin/env python3
"""Test of past_runs.py on a throwaway folder: a workflow's runs leave the board and come back. Nothing real is touched.

  1  count finds its runs (by skill, an earlier name, its board id and a batch's items), its trigger's requests,
     its done-list lines, warnings and the screenshots only it names; another workflow's are left out
  2  remove moves them out of what the board reads: the Inbox data no longer has them; the other workflow's stay
  3  restore puts every file and line back as it was

    python3 -I test_past_runs.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
FAILS = []
SK = "workflow-test-chaser"


def ok(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


def write(p, text):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(text)


def jl(*objs):
    return "\n".join(json.dumps(o) for o in objs) + "\n"


def run(proj, *args):
    r = subprocess.run([sys.executable, "-I", os.path.join(SCRIPTS, "past_runs.py"), *args], cwd=proj,
                       env=dict(os.environ, CLAUDE_PROJECT_DIR=proj), capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except ValueError:
        return {"raw": r.stdout, "err": r.stderr}


def snapshot(home):
    out = {}
    for root, _d, files in os.walk(os.path.join(home, "history")):
        if "/deleted" in root:
            continue
        for f in files:
            p = os.path.join(root, f)
            with open(p, encoding="utf-8") as fh:
                out[os.path.relpath(p, home)] = sorted(fh.read().splitlines())
    return out


def board_runs(proj):
    subprocess.run([sys.executable, "-I", os.path.join(SCRIPTS, "build_board.py")], cwd=proj, capture_output=True,
                   env=dict(os.environ, CLAUDE_PROJECT_DIR=proj))
    t = open(os.path.join(proj, ".workflow-manager-data", "system", "board", "board-data.js"), encoding="utf-8").read()
    return {r["id"] for r in json.loads(t[len("window.BOARD="):].rstrip().rstrip(";"))["runs"]}


def main():
    proj = tempfile.mkdtemp(prefix="wm-runs-")
    home = os.path.join(proj, ".workflow-manager-data")
    h = os.path.join(home, "history")
    write(os.path.join(proj, ".claude", "skills", SK, "SKILL.md"), "---\nname: " + SK + "\ndescription: x\n---\n# x\n")
    write(os.path.join(home, "config", "board", SK + ".json"), json.dumps({
        "workflows": [{"id": "test-chaser", "category": "test", "short": "Chaser", "steps": []}],
        "skills": {"workflow-new-chaser": {"short": "Chaser", "alias_of": SK}}}))
    # its runs: a batch (flow = board id) with an item, a run under its earlier name, and another workflow's run
    write(os.path.join(h, "runs", "run-1-chaser.jsonl"), jl(
        {"header": True, "run": "run-1-chaser", "kind": "batch", "flow": "test-chaser", "group": "dispatch-1",
         "started": "2026-11-20T09:00:00Z"}, {"step": "x", "result": "shot chaser-1.png", "status": "done"},
        {"end": True, "status": "done"}))
    write(os.path.join(h, "runs", "wf-aaaaaaaa-a1.jsonl"), jl(
        {"header": True, "run": "wf-aaaaaaaa-a1", "kind": "run", "batch": "run-1-chaser", "group": "dispatch-1"},
        {"end": True}))
    write(os.path.join(h, "runs", "wf-bbbbbbbb-a1.jsonl"), jl(
        {"header": True, "run": "wf-bbbbbbbb-a1", "kind": "run", "skill": "workflow-new-chaser", "group": "dispatch-2"},
        {"step": "y", "result": "shared.png", "status": "done"}, {"end": True}))
    write(os.path.join(h, "runs", "wf-cccccccc-a1.jsonl"), jl(
        {"header": True, "run": "wf-cccccccc-a1", "kind": "run", "skill": "workflow-other", "group": "dispatch-3"},
        {"step": "z", "result": "shared.png", "status": "done"}, {"end": True}))
    write(os.path.join(h, "requests", "dispatch-1.jsonl"), jl({"header": True, "run": "dispatch-1", "kind": "trigger"},
                                                           {"entry_match": "test-chaser"}, {"end": True}))
    write(os.path.join(h, "requests", "dispatch-3.jsonl"), jl({"header": True, "run": "dispatch-3", "kind": "trigger"},
                                                           {"entry_match": "other"}, {"end": True}))
    write(os.path.join(h, "done-list.jsonl"), jl({"wf": "wf-aaaaaaaa", "skill": SK}, {"wf": "wf-cccccccc", "skill": "workflow-other"},
                                                {"wf": "wf-bbbbbbbb", "skill": "workflow-new-chaser"}))
    write(os.path.join(h, "suggestions.jsonl"), jl({"id": "sg-1", "run": "wf-bbbbbbbb-a1"}, {"id": "sg-2", "run": "wf-cccccccc-a1"}))
    for s in ("chaser-1.png", "shared.png"):
        write(os.path.join(h, "screenshots", s), "png")
    before = snapshot(home)

    # 1
    c = run(proj, "count", SK)
    ok(c.get("runs") == 2 and c.get("run_files") == 3, f"1 its runs: the batch with its item, and the one under its earlier name ({c})")
    ok(c.get("requests") == 1 and c.get("done_list") == 2 and c.get("warnings") == 1, "1 its request, done-list lines and warning")
    ok(c.get("screenshots") == 1, "1 only the screenshot no other run names")

    # 2
    have = board_runs(proj)
    ok({"run-1-chaser", "wf-bbbbbbbb-a1", "wf-cccccccc-a1"} <= have, "2 before: the board has them")
    r = run(proj, "remove", SK)
    ok(r.get("removed") and os.path.isdir(r.get("folder", "")), "2 remove moves them to the deleted folder")
    have = board_runs(proj)
    ok(not ({"run-1-chaser", "wf-aaaaaaaa-a1", "wf-bbbbbbbb-a1", "dispatch-1"} & have), "2 they're off the board")
    ok({"wf-cccccccc-a1", "dispatch-3"} <= have, "2 the other workflow's runs stay")
    done = open(os.path.join(h, "done-list.jsonl")).read()
    ok("wf-cccccccc" in done and "wf-aaaaaaaa" not in done and "wf-bbbbbbbb" not in done, "2 its done-list lines go, the other's stay")
    ok(os.path.isfile(os.path.join(h, "screenshots", "shared.png")) and not os.path.isfile(os.path.join(h, "screenshots", "chaser-1.png")),
       "2 a screenshot another run names stays")

    # 3
    r = run(proj, "restore", os.path.basename(r.get("folder", "x")))
    ok(r.get("restored"), "3 restore")
    ok(snapshot(home) == before, "3 every file and line is back as it was")

    print()
    print("FAILED: " + str(len(FAILS)) if FAILS else "all passed")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
