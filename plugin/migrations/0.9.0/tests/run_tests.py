"""0.9.0: history/system/settings move, logs and done list joined old-first, board left for the user step, twice = no change."""
import importlib.util
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("data", os.path.join(HERE, "..", "data.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
ok, tmp = True, tempfile.mkdtemp()
try:
    P = lambda *a: os.path.join(tmp, *a)
    for p, t in {".workflow-manager/history/requests/r.jsonl": "r", ".workflow-manager/history/done-list.jsonl": "old\n",
                 ".workflow-manager/system/migrations.log": "old\n", ".workflow-manager/system/version.json": "{}",
                 ".workflow-manager/config/settings.json": "{}", ".workflow-manager/config/board/x.json": "{}",
                 ".workflow-manager-data/history/done-list.jsonl": "new\n", ".workflow-manager-data/system/migrations.log": "new\n"}.items():
        os.makedirs(os.path.dirname(P(p)), exist_ok=True)
        open(P(p), "w").write(t)
    ctx = {"legacy_08": P(".workflow-manager"), "home": P(".workflow-manager-data")}
    mod.migrate(ctx)
    N = lambda *a: P(".workflow-manager-data", *a)
    checks = [os.path.isfile(N("history", "requests", "r.jsonl")), os.path.isfile(N("system", "version.json")),
              os.path.isfile(N("config", "settings.json")),
              open(N("history", "done-list.jsonl")).read() == "old\nnew\n", open(N("system", "migrations.log")).read() == "old\nnew\n",
              sorted(os.listdir(P(".workflow-manager"))) == ["config"] and os.listdir(P(".workflow-manager", "config")) == ["board"]]
    if not all(checks):
        ok = False
        print("FAIL", checks)
    before = sorted(os.walk(tmp))
    mod.migrate(ctx)
    if sorted(os.walk(tmp)) != before:
        ok = False
        print("FAIL second run changed something")
finally:
    shutil.rmtree(tmp)
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
