"""0.8.0 machine data: .dispatcher/data/ -> .workflow-manager/{config,history,system}/.
Leaves .dispatcher/board/ (the user's own files) for the user step. Safe to run twice: whatever has
already moved is skipped. Trace files are sorted by their header: kind "trigger" (a request) goes to
history/requests/, everything else to history/runs/."""
import json
import os
import shutil

GENERATED = {"board-data.js", "workflows-data.js", ".watch.pid", "board-data.js.tmp", "workflows-data.js.tmp"}


def kind(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.loads(fh.readline() or "{}").get("kind")
    except (OSError, ValueError):
        return None


def put(src, dst, moved):
    """Move src to dst. Folders merge; an existing file is kept and the old one stored beside it."""
    if os.path.isdir(src) and os.path.isdir(dst):
        for n in sorted(os.listdir(src)):
            put(os.path.join(src, n), os.path.join(dst, n), moved)
        if not os.listdir(src):
            os.rmdir(src)
        return
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if os.path.exists(dst):
        dst = dst + ".pre-0.8.0"
    shutil.move(src, dst)
    moved.append(os.path.basename(dst))


def join_lines(src, dst):
    """Old lines first, then any already in the new file (logs, done list)."""
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(src, encoding="utf-8") as fh:
        old = fh.read()
    new = ""
    if os.path.exists(dst):
        with open(dst, encoding="utf-8") as fh:
            new = fh.read()
    if old and not old.endswith("\n"):
        old += "\n"
    with open(dst, "w", encoding="utf-8") as fh:
        fh.write(old + new)
    os.remove(src)


def migrate(ctx):
    legacy = ctx["legacy"]
    data = os.path.join(legacy, "data") if legacy else None
    if not data or not os.path.isdir(data):
        return ["nothing to move"]
    moved, out = [], []
    traces = os.path.join(data, "traces")
    if os.path.isdir(traces):
        req = runs = 0
        for n in sorted(os.listdir(traces)):
            p = os.path.join(traces, n)
            if n == ".live":
                shutil.rmtree(p, ignore_errors=True)          # stale "now doing" notes
            elif n == ".trash" and os.path.isdir(p):
                put(p, os.path.join(ctx["requests"], ".trash"), moved)
            elif n.endswith(".jsonl"):
                if kind(p) == "trigger":
                    put(p, os.path.join(ctx["requests"], n), moved); req += 1
                else:
                    put(p, os.path.join(ctx["runs"], n), moved); runs += 1
            else:
                put(p, os.path.join(ctx["runs"], n), moved)
        if os.path.isdir(traces) and not os.listdir(traces):
            os.rmdir(traces)
        out.append(f"traces: {req} requests, {runs} runs")
    if os.path.isdir(os.path.join(data, "shots")):
        put(os.path.join(data, "shots"), ctx["shots"], moved)
        out.append("screenshots moved")
    store = os.path.join(data, "dispatcher-data")
    if os.path.isfile(os.path.join(store, "ledger.jsonl")):
        join_lines(os.path.join(store, "ledger.jsonl"), ctx["done_list"])
        out.append("ledger.jsonl -> done-list.jsonl")
    if os.path.isfile(os.path.join(store, "settings.json")):
        put(os.path.join(store, "settings.json"), ctx["settings"], moved)
        out.append("settings -> config/settings.json")
    if os.path.isdir(store):
        for n in os.listdir(store):
            put(os.path.join(store, n), os.path.join(ctx["system"], "legacy", n), moved)
        os.rmdir(store)
    for n in sorted(os.listdir(data)):
        p = os.path.join(data, n)
        if n in GENERATED:
            os.remove(p)
        elif n == "migrations.log":
            join_lines(p, os.path.join(ctx["system"], "migrations.log"))
        elif n in ("backups", "version.json", "offer.json"):
            put(p, os.path.join(ctx["system"], n), moved)
        else:
            put(p, os.path.join(ctx["system"], "legacy", n), moved)
    if not os.listdir(data):
        os.rmdir(data)
    if os.path.isdir(legacy) and not os.listdir(legacy):
        os.rmdir(legacy)
    return out or ["nothing to move"]
