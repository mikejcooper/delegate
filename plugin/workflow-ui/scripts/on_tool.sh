#!/bin/sh
# Runs before every tool call: updates the board's live "what Claude is doing" line (every request), and while a
# dispatcher run is open also the "now doing" note under the running trigger.
SCRIPTS=$(cd "$(dirname "$0")" && pwd)
cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || exit 0
python3 -I "$SCRIPTS/live.py" tool >/dev/null 2>&1   # stdin: the hook JSON
exit 0
