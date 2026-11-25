#!/usr/bin/env python3
"""0.16.0: a folder's .workflow-manager-data/ becomes .delegate-data/ the first time a script runs, the old name is
left as a link to it, and a folder already moved (or new) is left alone. Runs paths.py against temp folders."""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PATHS = os.path.join(os.path.dirname(HERE), "scripts", "paths.py")
fails = 0


def ok(cond, what):
    global fails
    print(("ok   " if cond else "FAIL ") + what)
    fails += 0 if cond else 1


def paths(project):
    out = subprocess.run([sys.executable, "-I", PATHS], capture_output=True, text=True,
                         env=dict(os.environ, CLAUDE_PROJECT_DIR=project), check=True).stdout
    return json.loads(out)


with tempfile.TemporaryDirectory() as t:
    p = os.path.realpath(t)
    old, new = os.path.join(p, ".workflow-manager-data"), os.path.join(p, ".delegate-data")
    os.makedirs(os.path.join(old, "system"))
    with open(os.path.join(old, "system", "version.json"), "w") as fh:
        json.dump({"data_version": "0.15.9"}, fh)
    with open(os.path.join(old, "config.txt"), "w") as fh:
        fh.write("mine")
    d = paths(p)
    ok(os.path.realpath(d.get("home", "")) == new or d.get("home") == new, "paths.py names .delegate-data as the home")
    ok(os.path.isfile(os.path.join(new, "system", "version.json")), "the old folder's files are in .delegate-data/")
    ok(os.path.islink(old) and os.path.realpath(old) == new, ".workflow-manager-data is now a link to it")
    with open(os.path.join(old, "config.txt")) as fh:
        ok(fh.read() == "mine", "the old path still reads the same files")
    paths(p)
    ok(os.path.isdir(new) and os.path.islink(old), "running again changes nothing")

with tempfile.TemporaryDirectory() as t:
    p = os.path.realpath(t)
    os.makedirs(os.path.join(p, ".delegate-data", "system"))
    os.makedirs(os.path.join(p, ".workflow-manager-data", "system"))   # both: never merged or overwritten
    paths(p)
    ok(os.path.isdir(os.path.join(p, ".workflow-manager-data")) and not os.path.islink(os.path.join(p, ".workflow-manager-data")),
       "with both folders present, the old one is left as it is")

with tempfile.TemporaryDirectory() as t:
    p = os.path.realpath(t)
    os.makedirs(os.path.join(p, ".claude"))
    paths(p)
    ok(not os.path.lexists(os.path.join(p, ".workflow-manager-data")), "a new folder gets no old-name link")

print("\nall passed" if not fails else f"\n{fails} failed")
sys.exit(1 if fails else 0)
