"""0.6.0: renames.json is well-formed and every new name follows the pattern; user.upgrade renames references."""
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("user", os.path.join(HERE, "..", "user.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
ok = True
pat = re.compile(r"^((entry|workflow|shared)-[a-z0-9]+-[a-z0-9-]+|core-[a-z0-9-]+)$")
for old, new in mod.RENAMES.items():
    if not pat.match(new) or old == new:
        ok = False
        print(f"FAIL bad rename {old} -> {new}")
before = {"workflows": [{"id": "g", "steps": [{"why": {"file": "workflow-guardian-news", "parts": []}},
                                               {"why": {"file": "workflow-security"}}]}],
          "note": "workflow-security is mentioned in a sentence, not renamed", "data_version": "0.5.0"}
got = mod.upgrade(before)
files = [s["why"]["file"] for s in got["workflows"][0]["steps"]]
if files != ["workflow-news-guardian-article", "workflow-security-alert"]:
    ok = False
    print("FAIL references not renamed:", files)
if got["note"] != before["note"]:
    ok = False
    print("FAIL text that only mentions a name was changed")
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
