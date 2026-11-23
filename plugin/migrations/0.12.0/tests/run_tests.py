"""0.12.0: notes the removed plugin workflows a folder ran (unless it has its own copy), and writes the areas its own
skills use that left the plugin's category list to its own list; twice = no change."""
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
with open(os.path.join(HERE, "..", "renames.json"), encoding="utf-8") as fh:
    renames = json.load(fh)

tmp = tempfile.mkdtemp(prefix="wm-0120-")
try:
    home = os.path.join(tmp, ".workflow-manager-data")
    done = os.path.join(home, "history", "done-list.jsonl")
    os.makedirs(os.path.dirname(done))
    lines = [{"wf": "wf-1", "skill": "workflow-news-bbc-article"}, {"wf": "wf-2", "skill": "workflow-security-alert"},
             {"wf": "wf-3", "skill": "workflow-mine-own"}, "not json"]
    with open(done, "w", encoding="utf-8") as fh:
        fh.write("\n".join(x if isinstance(x, str) else json.dumps(x) for x in lines) + "\n")
    before = open(done, encoding="utf-8").read()
    os.makedirs(os.path.join(tmp, ".claude", "skills", "workflow-security-alert"))   # this folder kept its own copy
    os.makedirs(os.path.join(tmp, ".claude", "skills", "workflow-property-flat-alert"))   # an area that left the plugin
    os.makedirs(os.path.join(tmp, ".claude", "skills", "workflow-news-mine"))           # an area the plugin still has
    config = os.path.join(home, "config")
    ctx = {"home": home, "done_list": done, "config": config}
    got = mod.migrate(ctx)
    cats = open(os.path.join(config, "categories.md"), encoding="utf-8").read()
    empty = mod.migrate({"home": os.path.join(tmp, "x", ".workflow-manager-data"), "done_list": os.path.join(tmp, "none")})
    ok = (len(got) == 2 and "workflow-news-bbc-article" in got[0] and "property" in got[1] and "security" in got[1]
          and "| `property` |" in cats and "| `security` |" in cats and "| `news` |" not in cats
          and "| `finance` |" not in cats and "workflow-security-alert" not in got[0]
          and "workflow-mine-own" not in got[0] and empty == [] and open(done, encoding="utf-8").read() == before
          and mod.migrate(ctx) == got[:1] and renames == {"shared-common-gmail": "connection-gmail"})
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("PASS" if ok else f"FAIL {got} {empty}")
sys.exit(0 if ok else 1)
