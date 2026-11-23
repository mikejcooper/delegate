"""0.7.0 user files: replace every renamed skill name inside a board definition (renames.json next to
this file): "Why?" references to skills, and any other text that is exactly an old name."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "renames.json"), encoding="utf-8") as fh:
    RENAMES = json.load(fh)


def rename(value):
    if isinstance(value, dict):
        return {RENAMES.get(k, k): rename(v) for k, v in value.items()}
    if isinstance(value, list):
        return [rename(v) for v in value]
    if isinstance(value, str):
        return RENAMES.get(value, value)
    return value


def upgrade(obj):
    return rename(obj)
