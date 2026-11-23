"""Check user.py turns board.before.json into board.after.json."""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("user", os.path.join(HERE, "..", "user.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
before = json.load(open(os.path.join(HERE, "board.before.json")))
after = json.load(open(os.path.join(HERE, "board.after.json")))
got = mod.upgrade(before)
print("PASS" if got == after else f"FAIL: {got}")
sys.exit(0 if got == after else 1)
