#!/usr/bin/env python3
"""Test of share.py: two throwaway folders, a sender and a receiver, each with its own skill history. Nothing real
is touched (every call runs with CLAUDE_PROJECT_DIR set to a temp folder).

  1  share a workflow for the first time: a zip with its skill, board, versions and the connection it uses
  2  a share refuses a skill with a key written in it
  3  the receiver inspects it (a new workflow) and imports it: a draft, marked imported, their connection kept
  4  an update the receiver hasn't changed: it simply updates
  5  an update the receiver has changed elsewhere: both changes kept, no questions
  6  both changed the same step: one conflict, yours kept; --take theirs takes theirs; their unpublished edits saved
     as a version first
  7  --fresh: the update as it is
  8  an issue with a run: the receiver brings it in as a debugging copy, its runs marked debug and kept out of
     the Inbox, the copy on the board under Debugging
  9  the receiver fixes the copy and sends it back; the sender merges the fix onto what they had
 10  a zip that writes outside its folder, a zip that isn't a share, a plain skill zip

    python3 -I test_share.py          (WM_SHARE_KEEP=1 keeps both folders, to look at their boards)
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
SHARE = os.path.join(SCRIPTS, "share.py")
HIST = os.path.join(SCRIPTS, "skill_history.py")
FAILS = []
SK = "workflow-test-invoice-chaser"
CONN = "connection-testmail"


def ok(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        FAILS.append(what)


def run(proj, script, *args, expect_error=False):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=proj)
    r = subprocess.run([sys.executable, "-I", script, *args], cwd=proj, env=env, capture_output=True, text=True)
    try:
        obj = json.loads(r.stdout) if r.stdout.strip().startswith("{") else {"raw": r.stdout, "err": r.stderr}
    except ValueError:
        obj = {"raw": r.stdout, "err": r.stderr}
    if not expect_error and (r.returncode != 0 or "error" in obj) and script == SHARE:
        print("   (unexpected)", r.stdout[:400], r.stderr[-800:])
    return obj


SKILL_MD = """---
name: workflow-test-invoice-chaser
description: Chases overdue invoices. Use when the user says "chase invoices".
---

# Invoice chaser

## Definition
uses: testmail

## Steps
**Step 1: Find the overdue invoices.**
Read the inbox and keep invoices past their due date.

**Step 2: Write the reminder.**
Write a polite reminder for each invoice, addressed to the client.

**Step 3: Save it as a draft.**
Save each reminder as an email draft through connection-testmail.
"""


def board(steps):
    return {"workflows": [{"id": "test-invoice-chaser", "category": "test", "short": "Invoice chaser",
                           "match": {"skill": SK, "default": True},
                           "steps": [{"key": k, "sk": SK, "title": t, "type": "act", "what": t} for k, t in steps]}],
            "categories": {"test": {"name": "Test", "tone": "teal", "section": "workflows"}}}


STEPS = [("find", "Find the overdue invoices"), ("write", "Write the reminder"), ("save", "Save it as a draft")]


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def project(root, name, with_skill=True):
    proj = os.path.join(root, name)
    os.makedirs(os.path.join(proj, ".delegate-data", "config", "board"))
    os.makedirs(os.path.join(proj, ".claude", "skills"))
    if with_skill:
        write(os.path.join(proj, ".claude", "skills", SK, "SKILL.md"), SKILL_MD)
        write(os.path.join(proj, ".claude", "skills", CONN, "SKILL.md"),
              "---\nname: connection-testmail\ndescription: Test mail.\n---\n\n# Test mail\nmethods: browser\n")
        write(os.path.join(proj, ".delegate-data", "config", "board", SK + ".json"), json.dumps(board(STEPS), indent=1))
    run(proj, HIST, "start", "--quiet")
    return proj


def publish(proj, msg):
    r = run(proj, HIST, "save", "--via", "architect", "--message", msg, "--quiet")
    return r


def skill_md(proj):
    return read(os.path.join(proj, ".claude", "skills", SK, "SKILL.md"))


def board_json(proj):
    return json.loads(read(os.path.join(proj, ".delegate-data", "config", "board", SK + ".json")))


def edit(proj, old, new):
    p = os.path.join(proj, ".claude", "skills", SK, "SKILL.md")
    t = read(p)
    assert old in t, old
    write(p, t.replace(old, new))


def main():
    root = tempfile.mkdtemp(prefix="wm-share-")
    out = os.path.join(root, "zips")
    sender = project(root, "sender")
    receiver = project(root, "receiver", with_skill=False)
    # the receiver already has its own way into the test mail, which must stay theirs
    write(os.path.join(receiver, ".claude", "skills", CONN, "SKILL.md"),
          "---\nname: connection-testmail\ndescription: Test mail, the receiver's own.\n---\n\n# Test mail\nmethods: chrome\n")

    # 1 first share
    r = run(sender, SHARE, "make", SK, "--kind", "full", "--out", out)
    z1 = r.get("made")
    ok(bool(z1) and os.path.isfile(z1), "1 a full share makes a zip")
    ok(os.path.basename(z1 or "") == "delegate--invoice-chaser_workflow_v1.zip", "1 named delegate--<workflow>_workflow_<version>.zip")
    names = zipfile.ZipFile(z1).namelist() if z1 else []
    ok("manifest.json" in names and f"current/skills/{SK}/SKILL.md" in names and f"current/board/{SK}.json" in names,
       "1 it holds the manifest, the skill and its board")
    ok(f"current/skills/{CONN}/SKILL.md" in names, "1 it takes the connection it uses with it")
    ok(any(n.startswith(f"versions/{SK}/v1/") for n in names), "1 it carries the published version v1")
    m = json.loads(zipfile.ZipFile(z1).read("manifest.json"))
    ok(m["kind"] == "full" and m["version"] == "v1" and "made_by" not in m and "user" not in json.dumps(m).lower(),
       "1 the manifest says what it is, never who made it")
    ok(os.path.isfile(os.path.join(sender, ".delegate-data", "history", "shares", "log.jsonl")),
       "1 the share is logged for the Share tab")

    # 2 a key in a skill is refused
    edit(sender, "Read the inbox", 'api_key = "abcd1234efgh5678" Read the inbox')
    r = run(sender, SHARE, "make", SK, "--kind", "issue", "--runs", "x", "--out", out, expect_error=True)
    ok("error" in r and r.get("at"), "2 a share with a key in it is refused, with where it is")
    edit(sender, 'api_key = "abcd1234efgh5678" Read the inbox', "Read the inbox")

    # 3 receiver: inspect, import
    r = run(receiver, SHARE, "inspect", z1)
    ok(r.get("what") == "full" and r.get("plan") == "import", "3 inspect: a new workflow to import")
    r = run(receiver, SHARE, "import", z1)
    ok(r.get("imported") == SK and SK in r.get("added", []), "3 import adds the workflow")
    ok(CONN in r.get("kept_yours", []) and "chrome" in read(os.path.join(receiver, ".claude", "skills", CONN, "SKILL.md")),
       "3 the receiver's own connection stays theirs")
    ok(skill_md(receiver) == SKILL_MD, "3 the skill arrives as it was shared")
    rec = json.loads(read(os.path.join(receiver, ".delegate-data", "config", "shared", SK + ".json")))
    ok(rec.get("plan") == "new" and rec.get("their_version") == "v1", "3 it is recorded as imported, their v1")
    st = run(receiver, HIST, "status")
    ok(SK in json.dumps(st), "3 it is a draft until published")
    publish(receiver, "Imported invoice chaser")
    r = run(receiver, SHARE, "inspect", z1)
    ok(r.get("plan") == "nothing", "3 the same zip again: nothing to do")

    # 4 an update the receiver hasn't changed
    edit(sender, "Write a polite reminder for each invoice, addressed to the client.",
         "Write a polite reminder for each invoice, addressed to the client, with the invoice attached.")
    publish(sender, "Attach the invoice")
    r = run(sender, SHARE, "make", SK, "--kind", "update", "--out", out)
    z2 = r.get("made")
    ok(r.get("version") == "v2", "4 the update shares v2")
    ok(os.path.basename(z2 or "") == "delegate--invoice-chaser_update_v1-to-v2.zip", "4 named with the version it updates from")
    r = run(receiver, SHARE, "inspect", z2)
    ok(r.get("plan") == "update" and r.get("conflicts") == 0, "4 inspect: it simply updates")
    r = run(receiver, SHARE, "merge", z2)
    ok("with the invoice attached" in skill_md(receiver), "4 merge: the update is in")
    publish(receiver, "Took v2")

    # 5 both changed, different places
    edit(receiver, "Read the inbox and keep invoices past their due date.",
         "Read the inbox and keep invoices more than 7 days past their due date.")
    publish(receiver, "Only 7 days overdue")
    edit(sender, "Save each reminder as an email draft through connection-testmail.",
         "Save each reminder as an email draft through connection-testmail, labelled Chased.")
    b = board_json(sender)
    b["workflows"][0]["steps"].insert(1, {"key": "group", "sk": SK, "title": "Group them by client", "type": "act",
                                          "what": "Group them by client"})
    write(os.path.join(sender, ".delegate-data", "config", "board", SK + ".json"), json.dumps(b, indent=1))
    publish(sender, "Label and group")
    z3 = run(sender, SHARE, "make", SK, "--kind", "update", "--out", out).get("made")
    imp = run(sender, SHARE, "impact", SK)
    ok(any(c["k"] == "new" and c["t"] == "Group them by client" for c in imp.get("changes", [])),
       "5 impact: the Share tab can say what the update adds")
    ok(any(c["k"] == "changed" and c["t"] == "Save it as a draft" for c in imp.get("changes", [])),
       "5 impact: and which steps' own text changed")
    r = run(receiver, SHARE, "inspect", z3)
    ok(r.get("plan") == "merge" and r.get("conflicts") == 0, "5 inspect: a merge with nothing to pick")
    r = run(receiver, SHARE, "merge", z3)
    t = skill_md(receiver)
    ok("more than 7 days" in t and "labelled Chased" in t, "5 merge: your change and theirs are both in")
    ok([s["key"] for s in board_json(receiver)["workflows"][0]["steps"]] == ["find", "group", "write", "save"],
       "5 merge: their new step is in the board, in its place")
    publish(receiver, "Took v3")

    # 6 both changed the same line
    edit(receiver, "Write a polite reminder for each invoice, addressed to the client, with the invoice attached.",
         "Write a firm reminder for each invoice, addressed to the client, with the invoice attached.")
    # left unpublished on purpose: the merge saves it as a version first
    edit(sender, "Write a polite reminder for each invoice, addressed to the client, with the invoice attached.",
         "Write a polite reminder for each invoice, addressed to the accounts payable team, with the invoice attached.")
    publish(sender, "Address accounts payable")
    z4 = run(sender, SHARE, "make", SK, "--kind", "update", "--out", out).get("made")
    r = run(receiver, SHARE, "inspect", z4)
    ok(r.get("plan") == "merge" and r.get("conflicts") == 1, "6 inspect: one thing to pick")
    r = run(receiver, SHARE, "merge", z4)
    sk = next(x for x in r.get("skills", []) if x["skill"] == SK)
    c = (sk.get("conflicts") or [{}])[0]
    ok(c.get("id") == "c1" and "firm" in (c.get("yours") or "") and "accounts payable" in (c.get("theirs") or ""),
       "6 the conflict shows both sides")
    ok("Write the reminder" in (c.get("what") or "") and "SKILL.md" not in (c.get("what") or ""), "6 it says where: the step, not the file")
    ok("firm reminder" in skill_md(receiver), "6 yours is kept until you pick")
    ok(SK in r.get("saved_your_changes_first", []), "6 your unpublished edit was saved as a version first")
    r = run(receiver, SHARE, "merge", z4, "--take", "c1=theirs")
    t = skill_md(receiver)
    ok("accounts payable" in t and "firm" not in t and "more than 7 days" in t, "6 --take c1=theirs: theirs, the rest kept")
    rec = json.loads(read(os.path.join(receiver, ".delegate-data", "config", "shared", SK + ".json")))
    ok(rec["conflicts"][0]["taking"] == "theirs", "6 the record shows the pick for the page")
    r = run(receiver, SHARE, "merge", z4, "--take", "c1=mine")
    ok("firm reminder" in skill_md(receiver), "6 picking again starts from your copy, not the last pick")

    # 7 start fresh
    r = run(receiver, SHARE, "merge", z4, "--fresh")
    ok("more than 7 days" not in skill_md(receiver) and "accounts payable" in skill_md(receiver),
       "7 --fresh: the update exactly as shared")
    publish(receiver, "Fresh from v4")

    # 8 an issue with a run, debugged at the receiver
    runs = os.path.join(sender, ".delegate-data", "history", "runs")
    os.makedirs(runs, exist_ok=True)
    hdr = {"header": True, "run": "run-0001-chase", "kind": "batch", "skill": SK, "flow": "test-invoice-chaser",
           "label": "3 invoices", "started": "2026-11-20T09:12:00Z"}
    item = {"header": True, "run": "wf-abc-a1", "kind": "run", "skill": SK, "batch": "run-0001-chase",
            "label": "INV-2041", "started": "2026-11-20T09:12:05Z"}
    write(os.path.join(runs, "run-0001-chase.jsonl"), "\n".join(json.dumps(x) for x in (
        hdr, {"type": "Sorted", "step": "Write the reminder", "result": "Drafted to accounts", "status": "done",
              "t": "2026-11-20T09:12:30Z"},
        {"end": True, "status": "done", "attention": "warn", "summary": "Reminder went to the accounts team",
         "t": "2026-11-20T09:12:40Z"})) + "\n")
    write(os.path.join(runs, "wf-abc-a1.jsonl"), json.dumps(item) + "\n" + json.dumps({"end": True, "status": "done"}) + "\n")
    write(os.path.join(sender, ".claude", "skills", SK, "tests", "recordings", "r1.json"),
          json.dumps({"kind": "workflow", "from_run": "wf-abc-a1", "item": {"invoice": "INV-2041"}}))
    rl = run(sender, SHARE, "runs", SK)
    ok([x["run"] for x in rl.get("runs", [])] == ["run-0001-chase"], "8 runs: the batch, not its item, is listed")
    r = run(sender, SHARE, "make", SK, "--kind", "issue", "--runs", "run-0001-chase", "--note", "Goes to accounts",
            "--out", out)
    z5 = r.get("made")
    ok(re.match(r"^delegate--invoice-chaser_issue_v\d+_1-run_\d{4}-\d\d-\d\d\.zip$", os.path.basename(z5 or "")) is not None,
       "8 named <workflow>_issue_<version>_<n>-run(s)_<date>.zip")
    names = zipfile.ZipFile(z5).namelist()
    ok("runs/run-0001-chase.jsonl" in names and "runs/wf-abc-a1.jsonl" in names, "8 the issue holds the run and its item")
    ok(f"recordings/{SK}/r1.json" in names, "8 and what the run read")
    r = run(receiver, SHARE, "inspect", z5)
    ok(r.get("what") == "issue" and r.get("plan") == "debug", "8 inspect: a debugging share")
    r = run(receiver, SHARE, "debug", z5)
    slug = r.get("debug")
    ok(bool(slug) and r.get("page") == "debug-" + slug, "8 debug: a debugging copy with its own page")
    droot = os.path.join(receiver, ".delegate-data", "debug", slug or "x")
    h = json.loads(read(os.path.join(droot, "runs", "run-0001-chase.jsonl")).splitlines()[0])
    ok(h.get("debug") is True and h.get("flow") == "debug-" + slug, "8 its runs are marked debug and point at the copy")
    ok(not os.path.isdir(os.path.join(receiver, ".claude", "skills", SK + "-debug")) and
       "firm" not in read(os.path.join(droot, "current", "skills", SK, "SKILL.md")),
       "8 the copy is the sender's, apart from the receiver's own skills")
    wf = read(os.path.join(receiver, ".delegate-data", "system", "board", "workflows-data.js"))
    W = json.loads(wf[len("window.WFDEF="):].rstrip().rstrip(";"))
    dw = [w for w in W["workflows"] if w.get("debug")]
    ok(len(dw) == 1 and dw[0]["id"] == "debug-" + slug and dw[0]["debug"]["note"] == "Goes to accounts",
       "8 the board has the copy, under its own id, with their note")
    bd = read(os.path.join(receiver, ".delegate-data", "system", "board", "board-data.js"))
    B = json.loads(bd[len("window.BOARD="):].rstrip().rstrip(";"))
    ok(any(x.get("debug") and x["id"] == "run-0001-chase" for x in B["runs"]), "8 its runs are on the board, marked debug")
    mine = [w for w in W["workflows"] if w["id"] == "test-invoice-chaser"]
    ok(mine and mine[0].get("share", {}).get("version") and "shared" in mine[0], "8 the receiver's own copy has Share data and its import record")

    # 9 fix and send back; the sender merges it onto what they had, while they changed something else
    p = os.path.join(droot, "current", "skills", SK, "SKILL.md")
    write(p, read(p).replace("addressed to the accounts payable team", "addressed to the client's accounts payable team"))
    r = run(receiver, SHARE, "make", "--debug", slug, "--out", out)
    z6 = r.get("made")
    ok(r.get("kind") == "fix" and r.get("changed") == [f"skills/{SK}/SKILL.md"], "9 the fix zip says what changed")
    edit(sender, "Save each reminder", "Save every reminder")   # the sender moves on meanwhile (a draft)
    r = run(sender, SHARE, "inspect", z6)
    ok(r.get("plan") == "merge" and r.get("conflicts") == 0, "9 at the sender: merges onto what they shared")
    run(sender, SHARE, "merge", z6)
    t = skill_md(sender)
    ok("client's accounts payable team" in t and "Save every reminder" in t, "9 the fix is in and their new edit stayed")

    # 10 bad zips
    bad = os.path.join(root, "bad.zip")
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("../../evil.txt", "x")
    r = run(receiver, SHARE, "inspect", bad, expect_error=True)
    ok("error" in r and "outside" in r["error"], "10 a zip that writes outside its folder is refused")
    plain = os.path.join(root, "plain.zip")
    with zipfile.ZipFile(plain, "w") as zf:
        zf.writestr("notes.txt", "hello")
    r = run(receiver, SHARE, "inspect", plain, expect_error=True)
    ok("error" in r, "10 a zip that isn't a share and holds no skill: said so")
    sk_zip = os.path.join(root, "my-skill.zip")
    with zipfile.ZipFile(sk_zip, "w") as zf:
        zf.writestr("my-skill/SKILL.md", "---\nname: my-skill\ndescription: x\n---\n# My skill\n")
    r = run(receiver, SHARE, "inspect", sk_zip)
    ok(r.get("plan") == "architect-import" and os.path.isfile(os.path.join(r.get("unpacked", ""), "SKILL.md")),
       "10 a plain skill zip goes to the architect's import, unpacked")
    if os.environ.get("WM_SHARE_KEEP"):   # leave both folders as they are, to look at the board
        print("kept: " + root)
    else:
        r = run(receiver, SHARE, "remove-debug", slug)
        ok(r.get("removed") == slug and not os.path.isdir(droot), "10 a debugging copy can be removed")

    print()
    print("FAILED: " + str(len(FAILS)) if FAILS else "all passed")
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
