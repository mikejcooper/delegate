"""0.4.0 user files: a skill's board.json gets "format": 2 (nothing else changes)."""


def upgrade(obj):
    obj = dict(obj)
    obj["format"] = 2
    return obj
