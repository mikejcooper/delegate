#!/bin/sh
# PreToolUse hook: only while a test run is open (test-mode.json), refuse calls that would read or change the
# outside world (test_mode.py guard). Otherwise it exits at once.
SCRIPTS=$(cd "$(dirname "$0")" && pwd)
cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || exit 0
[ -f "$SCRIPTS/../traces/.live/test-mode.json" ] || [ -f .delegate-data/system/board/live/test-mode.json ] || exit 0
python3 -I "$SCRIPTS/test_mode.py" guard
exit 0
