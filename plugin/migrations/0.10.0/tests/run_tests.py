"""0.10.0: a Trigger table becomes a Definition block the reader understands; twice = no change; workflows untouched."""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("skills", os.path.join(HERE, "..", "skills.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "..", "workflow-ui", "scripts")))
import entries  # noqa: E402

before = ("---\nname: trigger-news-guardian-front-page\n---\n# G\n\n## Trigger\n| Trigger | Phrases | Item key |\n|---|---|---|\n"
          "| `guardian` | check the guardian, guardian headlines | Guardian article path |\n\n## Steps\nStep 1.\n")
after = mod.convert("trigger-news-guardian-front-page", before)
d = entries.parse_definition(after) or {}
ok = (d.get("id") == "guardian" and d.get("starts on") == ["check the guardian", "guardian headlines"]
      and d.get("in run all") is True and d.get("item key") == "Guardian article path"
      and "## Trigger" not in after and "## Steps\nStep 1." in after
      and mod.convert("trigger-news-guardian-front-page", after) == after
      and mod.convert("workflow-x", before) == before)
print("PASS" if ok else "FAIL\n" + after)
sys.exit(0 if ok else 1)
