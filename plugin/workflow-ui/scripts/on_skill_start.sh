#!/bin/sh
# Runs when a skill is invoked. Only the dispatcher gets a trace; the other core skills (architect, connections,
# run reviewer) get the board forced open on their own page (board_section.py). Any other skill: nothing.
# For core-dispatcher (manager-work-dispatcher before 0.6.0): make sure the board watcher and server are live and the trigger trace exists,
# then tell Claude its run ID, the run-trace rules and this project's paths, and to show the board.
SCRIPTS=$(cd "$(dirname "$0")" && pwd)
cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || exit 0
INPUT=$(cat)
SKILL=$(printf '%s' "$INPUT" | python3 -I -c 'import json,sys
try: print(json.load(sys.stdin).get("tool_input",{}).get("skill",""))
except Exception: print("")' 2>/dev/null)
# the words the dispatcher was called with ("test workflow …"): the request text the board shows and sorts by
ARGS=$(printf '%s' "$INPUT" | python3 -I -c 'import json,sys
try: print(" ".join(str(json.load(sys.stdin).get("tool_input",{}).get("args","")).split())[:60])
except Exception: print("")' 2>/dev/null)
case "$SKILL" in
  core-dispatcher|*:core-dispatcher|manager-work-dispatcher|*:manager-work-dispatcher) KIND=dispatcher ;;
  core-architect|*:core-architect|core-connections|*:core-connections|core-run-reviewer|*:core-run-reviewer|core-renamer|*:core-renamer) KIND=core ;;
  *) exit 0 ;;
esac
python3 -I "$SCRIPTS/build_board.py" >/dev/null 2>&1   # rebuild now, so the board is current before it opens
nohup python3 -I "$SCRIPTS/build_board.py" --watch >/dev/null 2>&1 &
URL=$(python3 -I "$SCRIPTS/paths.py" url 2>/dev/null)
# In the Claude app the board is the app's preview (launch.json "workflow-ui", opened with preview_start), so the app
# keeps its tab; a copy left running in the background would hold the port, so stop it. Elsewhere, run it here.
if [ "$CLAUDE_CODE_ENTRYPOINT" = "claude-desktop" ]; then
  python3 -I "$SCRIPTS/serve_board.py" --release >/dev/null 2>&1
elif ! curl -s -o /dev/null --max-time 1 "$URL"; then
  nohup python3 -I "$SCRIPTS/serve_board.py" >/dev/null 2>&1 &
fi
python3 -I "$SCRIPTS/serve_board.py" --register >/dev/null 2>&1   # the board's entry in .claude/launch.json, so the app can reopen it
OPEN="in the built-in browser pane (never file://, which cannot update): if a board tab exists, front it with tabs_select, otherwise open it with preview_start name workflow-ui (in the Claude app the hooks leave the server to the app, so it keeps the tab and can reopen it), then navigate that tab to the address; if preview_start is unavailable, navigate to the URL. Then ALWAYS call mcp__ccd_view__show_pane with pane preview (load it via ToolSearch select:mcp__ccd_view__show_pane if deferred), even if you think the pane is visible: navigate and tabs_select leave a hidden pane hidden."
if [ "$KIND" = core ]; then
  # the whole args, not the 60-character cut, so a workflow named late in the request is still found
  WORDS=$(printf '%s' "$INPUT" | python3 -I -c 'import json,sys
try: print(" ".join(str(json.load(sys.stdin).get("tool_input",{}).get("args","")).split()))
except Exception: print("")' 2>/dev/null)
  PAGE=$(python3 -I "$SCRIPTS/board_section.py" "$SKILL" "$WORDS" 2>/dev/null)
  [ -n "$PAGE" ] || PAGE="$URL"
  CTX="Before this skill's work, open the workflow manager's board on its page for this request: $PAGE $OPEN If the skill later works on another workflow, draft or connection, navigate the same tab to that page (its own steps say which); never leave the board closed while it works."
  python3 -I -c 'import json,sys; print(json.dumps({"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":sys.argv[1]}}))' "$CTX"
  exit 0
fi
# The trigger trace normally exists already (on_prompt.sh made it); if the request wasn't recognised there, make it now.
OUT=$(python3 -I "$SCRIPTS/live.py" skill "$ARGS" </dev/null 2>/dev/null)
RUN=$(printf '%s\n' "$OUT" | sed -n 1p)
TRY=$(printf '%s\n' "$OUT" | sed -n 3p)   # a try, or a run of one workflow: where to watch it on the Builder
NOTE=$(python3 -I "$SCRIPTS/live.py" note </dev/null 2>/dev/null)
if [ -n "$RUN" ]; then
  TRACE="The hooks already created its trigger trace for run ID $RUN with the header line: use that ID, don't create another trace or rewrite the header."
else
  TRACE="If the run's trace file doesn't exist yet, create it now with its header line and rebuild the board."
fi
CTX="The dispatcher is about to start. $TRACE $TRY$NOTE Make sure $URL is open (for a try, a test, or a run or rerun of one workflow: the Builder address above instead, and stay on it for the whole run, never moving the tab to the Inbox) $OPEN Do this before the dispatcher's work."
python3 -I -c 'import json,sys; print(json.dumps({"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":sys.argv[1]}}))' "$CTX"
