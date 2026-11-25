"""0.16.0: a user skill's .workflow-manager-data/ paths become .delegate-data/; twice = no change; other text untouched."""
import importlib.util
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("skills", os.path.join(HERE, "..", "skills.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

before = ("---\nname: workflow-news-x\n---\n# X\n\nSave the page to `.workflow-manager-data/history/pages/x/` and "
          "say \"workflow-manager\" once.\n")
after = mod.convert("workflow-news-x", before)
ok = ("`.delegate-data/history/pages/x/`" in after and ".workflow-manager-data" not in after
      and '"workflow-manager"' in after and mod.convert("workflow-news-x", after) == after
      and mod.convert("workflow-news-y", "nothing here\n") == "nothing here\n")
print("PASS" if ok else "FAIL\n" + after)
sys.exit(0 if ok else 1)
