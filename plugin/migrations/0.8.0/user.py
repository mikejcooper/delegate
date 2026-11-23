"""0.8.0 user files: content unchanged; the walker writes each board definition to its new home,
.workflow-manager/config/board/<skill>.json, and removes it from .dispatcher/board/."""


def upgrade(obj):
    return dict(obj)
