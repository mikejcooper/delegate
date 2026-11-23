"""0.9.0 user files: content unchanged; the walker writes each board definition to its new home,
.workflow-manager-data/config/board/<skill>.json, and removes it from .workflow-manager/config/board/."""


def upgrade(obj):
    return dict(obj)
