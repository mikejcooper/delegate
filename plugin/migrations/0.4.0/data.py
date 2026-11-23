"""0.4.0 machine data: stamp trace headers with format 2; add show_seen_before to settings.
Safe to run twice: a header already at format 2 and a key already set are left as they are."""
import glob
import json
import os


def migrate(ctx):
    changes = []
    stamped = 0
    for path in sorted(glob.glob(os.path.join(ctx["traces"], "*.jsonl"))):
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
        if not lines:
            continue
        try:
            head = json.loads(lines[0])
        except ValueError:
            continue
        if not head.get("header") or head.get("format") == 2:
            continue
        head["format"] = 2
        lines[0] = json.dumps(head)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        os.replace(tmp, path)
        stamped += 1
    changes.append(f"stamped {stamped} trace headers with format 2")
    settings = os.path.join(ctx["store"], "settings.json")
    try:
        with open(settings, encoding="utf-8") as fh:
            obj = json.load(fh)
    except (OSError, ValueError):
        obj = {"skip_done": True}
    if "show_seen_before" not in obj:
        obj["show_seen_before"] = True
        os.makedirs(ctx["store"], exist_ok=True)
        with open(settings, "w", encoding="utf-8") as fh:
            json.dump(obj, fh)
        changes.append("settings.json: added show_seen_before")
    return changes
