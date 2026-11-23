#!/bin/sh
# Stop hook: no longer saves versions. A version is one finished change, saved by the architect after its impact
# review (skill_history.py). Edits made this turn stay a draft; this only refreshes the Workflow Viewer data so its
# History panel shows "draft" for a workflow with unsaved edits. Silent, and never blocks the turn.
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || true
python3 -I "$HERE/live.py" stop </dev/null >/dev/null 2>&1   # the top bar: Claude is done, waiting for you
SETTLED="$(python3 -I "$HERE/new_workflow.py" settle 2>/dev/null)"   # a new draft left "drafting": Claude is done
# a skill still marked "Claude is updating it" (an edit with no checkpoint after it): Claude is done, stop pulsing
UPD="$(python3 -I "$HERE/skill_history.py" settle-updating 2>/dev/null)"
case "$UPD" in *'"settled": []'*|'') UPD="" ;; esac
OUT="$(python3 -I "$HERE/skill_history.py" status 2>/dev/null)"
case "$OUT$SETTLED" in
  *'"changed": []'*'"settled": []'*) [ -n "$UPD" ] && python3 -I "$HERE/build_workflows.py" >/dev/null 2>&1 ;;
  *) python3 -I "$HERE/build_workflows.py" >/dev/null 2>&1 ;;
esac
exit 0
