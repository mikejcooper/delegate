"""0.9.0 machine data: .workflow-manager/{history,system,config/settings.json} -> .workflow-manager-data/.
Leaves .workflow-manager/config/board/ (the user's own files) for the user step. Safe to run twice.
Folders merge; a log or the done list is joined old lines first; any other clash keeps both."""
import os
import shutil

JOIN = {"migrations.log", "done-list.jsonl"}


def move(src, dst, moved):
    if os.path.isdir(src) and os.path.isdir(dst):
        for n in sorted(os.listdir(src)):
            move(os.path.join(src, n), os.path.join(dst, n), moved)
        if not os.listdir(src):
            os.rmdir(src)
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst) and os.path.basename(dst) in JOIN:
        with open(src, encoding="utf-8") as fh:
            old = fh.read()
        with open(dst, encoding="utf-8") as fh:
            new = fh.read()
        with open(dst, "w", encoding="utf-8") as fh:
            fh.write(old + ("" if not old or old.endswith("\n") else "\n") + new)
        os.remove(src)
        return
    if os.path.exists(dst):
        dst += ".pre-0.9.0"
    shutil.move(src, dst)
    moved.append(os.path.basename(dst))


def migrate(ctx):
    old, new = ctx.get("legacy_08"), ctx["home"]
    if not old or not os.path.isdir(old):
        return ["nothing to move"]
    moved = []
    for part in ("history", "system"):
        if os.path.isdir(os.path.join(old, part)):
            move(os.path.join(old, part), os.path.join(new, part), moved)
    if os.path.isfile(os.path.join(old, "config", "settings.json")):
        move(os.path.join(old, "config", "settings.json"), os.path.join(new, "config", "settings.json"), moved)
    for d in (os.path.join(old, "config"), old):   # remove what's left empty (board/ stays for the user step)
        if os.path.isdir(d) and not os.listdir(d):
            os.rmdir(d)
    return [f"moved .workflow-manager/ into .workflow-manager-data/ ({len(moved)} items)"]
