"""0.8.0: machine data lands in history/ and system/, traces sorted by kind, ledger joined, board left alone, twice = no change."""
import importlib.util
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("data", os.path.join(HERE, "..", "data.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
ok = True


def fail(msg):
    global ok
    ok = False
    print("FAIL", msg)


tmp = tempfile.mkdtemp()
try:
    P = lambda *a: os.path.join(tmp, *a)
    files = {
        ".dispatcher/data/traces/dispatch-0001.jsonl": json.dumps({"header": True, "kind": "trigger"}) + "\n",
        ".dispatcher/data/traces/wf-00000000-a1.jsonl": json.dumps({"header": True, "kind": "run"}) + "\n",
        ".dispatcher/data/traces/.live/current": "{}",
        ".dispatcher/data/shots/dispatch-0001-1.jpg": "jpg",
        ".dispatcher/data/dispatcher-data/ledger.jsonl": '{"wf": "old"}\n',
        ".dispatcher/data/dispatcher-data/settings.json": '{"skip_done": false}',
        ".dispatcher/data/version.json": '{"data_version": "0.7.1"}',
        ".dispatcher/data/migrations.log": "old line\n",
        ".dispatcher/data/backups/0.4.2-x/a.txt": "b",
        ".dispatcher/data/board-data.js": "gen",
        ".dispatcher/board/workflow-x.json": "{}",
        ".workflow-manager/history/done-list.jsonl": '{"wf": "new"}\n',
    }
    for p, t in files.items():
        os.makedirs(os.path.dirname(P(p)), exist_ok=True)
        open(P(p), "w").write(t)
    H = P(".workflow-manager")
    ctx = {"legacy": P(".dispatcher"), "home": H, "config": P(H, "config"), "history": P(H, "history"),
           "system": P(H, "system"), "settings": P(H, "config", "settings.json"), "requests": P(H, "history", "requests"),
           "runs": P(H, "history", "runs"), "shots": P(H, "history", "screenshots"), "done_list": P(H, "history", "done-list.jsonl")}
    mod.migrate(ctx)
    expect = ["history/requests/dispatch-0001.jsonl", "history/runs/wf-00000000-a1.jsonl", "history/screenshots/dispatch-0001-1.jpg",
              "config/settings.json", "system/version.json", "system/migrations.log", "system/backups/0.4.2-x/a.txt"]
    for e in expect:
        if not os.path.isfile(P(H, e)):
            fail("missing " + e)
    if open(P(H, "history", "done-list.jsonl")).read() != '{"wf": "old"}\n{"wf": "new"}\n':
        fail("done list not joined old-first")
    if sorted(os.listdir(P(".dispatcher"))) != ["board"]:
        fail(f".dispatcher should hold only board/: {os.listdir(P('.dispatcher'))}")
    if os.path.exists(P(H, "system", "board-data.js")) or os.path.exists(P(H, "history", "requests", ".live")):
        fail("generated or stale files were carried over")
    before = sorted(os.walk(tmp))
    mod.migrate(ctx)
    if sorted(os.walk(tmp)) != before:
        fail("second run changed something")
finally:
    shutil.rmtree(tmp)
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
