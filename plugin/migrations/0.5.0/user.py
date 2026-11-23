"""0.5.0 user files: content unchanged; the walker writes each one to its new home,
.dispatcher/board/<skill name>.json, and removes the old board.json from the skill folder."""


def upgrade(obj):
    return dict(obj)
