"""0.5.0: user files keep their content; machine data moves into data/ (on a throwaway folder)."""
import importlib.util
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, "..", name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ok = True
board = {"workflows": [{"id": "x"}], "format": 2, "data_version": "0.4.0"}
if load("user").upgrade(board) != board:
    ok = False
    print("FAIL user.upgrade changed the content")

tmp = tempfile.mkdtemp()
try:
    root = os.path.join(tmp, ".dispatcher")
    for p, text in {"traces/a.jsonl": "{}\n", "dispatcher-data/ledger.jsonl": "{}\n", "version.json": "{}",
                    "migrations.log": "old\n", ".watch.pid": "1", "board/keep.json": "{}"}.items():
        os.makedirs(os.path.dirname(os.path.join(root, p)), exist_ok=True)
        open(os.path.join(root, p), "w").write(text)
    os.makedirs(os.path.join(root, "data"))
    open(os.path.join(root, "data", "migrations.log"), "w").write("new\n")
    data_mod = load("data")
    data_mod.migrate({"dispatcher": root, "data": os.path.join(root, "data")})
    left = sorted(os.listdir(root))
    want_left = ["board", "data"]
    inside = sorted(os.listdir(os.path.join(root, "data")))
    want_inside = ["dispatcher-data", "migrations.log", "traces", "version.json"]
    log = open(os.path.join(root, "data", "migrations.log")).read()
    for name, got, want in (("top level", left, want_left), ("data/", inside, want_inside), ("log order", log, "old\nnew\n")):
        if got != want:
            ok = False
            print(f"FAIL {name}: {got} != {want}")
    data_mod.migrate({"dispatcher": root, "data": os.path.join(root, "data")})   # twice: no change
    if sorted(os.listdir(root)) != want_left:
        ok = False
        print("FAIL second run changed something")
finally:
    shutil.rmtree(tmp)
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
