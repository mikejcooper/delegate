"""0.5.0 machine data: move everything directly in .dispatcher/ into .dispatcher/data/.
Leaves .dispatcher/board/ alone. Safe to run twice: anything already moved is skipped.
Where both places have a folder, their contents are merged; where both have the log, the old
lines are put first; any other clash keeps both (the old one gets a .pre-0.5.0 name)."""
import os
import shutil

KEEP = {"data", "board"}
SKIP = {".watch.pid"}            # a helper's pid: stale after the move, the helper is restarted


def move(s, d, name, moved, clashes):
    """Move one item s to d: plain move, merge folders, join logs (old lines first), else keep both."""
    if not os.path.exists(d):
        shutil.move(s, d)
        moved.append(name)
    elif os.path.isdir(s) and os.path.isdir(d):
        for child in sorted(os.listdir(s)):
            move(os.path.join(s, child), os.path.join(d, child), child, moved, clashes)
        if not os.listdir(s):
            os.rmdir(s)
    elif name == "migrations.log":
        with open(s, encoding="utf-8") as fh:
            old = fh.read()
        with open(d, encoding="utf-8") as fh:
            new = fh.read()
        with open(d, "w", encoding="utf-8") as fh:
            fh.write(old + new)
        os.remove(s)
    else:
        shutil.move(s, d + ".pre-0.5.0")
        clashes.append(name)


def migrate(ctx):
    root = ctx["dispatcher"]
    data = os.path.join(root, "data") if root else None   # the layout this step creates
    if not root or not os.path.isdir(root):
        return ["nothing to move"]
    os.makedirs(data, exist_ok=True)
    moved, clashes = [], []
    for name in sorted(os.listdir(root)):
        if name in KEEP:
            continue
        src = os.path.join(root, name)
        if name in SKIP:
            os.remove(src)
            continue
        move(src, os.path.join(data, name), name, moved, clashes)
    out = [f"moved into .dispatcher/data/: {', '.join(moved) or 'nothing'}"]
    if clashes:
        out.append(f"kept both copies (old one renamed .pre-0.5.0): {', '.join(clashes)}")
    return out
