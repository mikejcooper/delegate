"""0.7.0: every rename is entry-* -> trigger-* with the rest unchanged; the text swaps turn an old Entry table into a Trigger table."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ok = True
ren = json.load(open(os.path.join(HERE, "..", "renames.json")))
for old, new in ren.items():
    if not (old.startswith("entry-") and new == "trigger-" + old[len("entry-"):]):
        ok = False
        print(f"FAIL {old} -> {new} is not entry-x -> trigger-x")
swaps = json.load(open(os.path.join(HERE, "..", "skill_text.json")))
before = "---\nname: entry-x\ndescription: Dispatcher entry point for X.\n---\n## Entry\n| Entry | Triggers | Item key |\n|---|---|---|\n"
after = before
for a, b in swaps.items():
    after = after.replace(a, b)
want = "---\nname: entry-x\ndescription: Dispatcher trigger for X.\n---\n## Trigger\n| Trigger | Phrases | Item key |\n|---|---|---|\n"
if after != want:
    ok = False
    print("FAIL text swaps:", repr(after))
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
