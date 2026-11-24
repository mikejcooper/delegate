#!/bin/sh
# Runs the moment the user sends a request: quietly make sure the board watcher and the board server are live.
# A dispatcher request ("run dispatcher", "check my emails", "rerun workflow wf-…") also gets its trigger trace
# right now (live.py prompt), so the board shows it at once; Claude is told the run ID, the rules and the paths.
# Any other request closes the live "now doing" marker and adds nothing to Claude's context, except the
# migration offer below when the user's own files are behind.
# Works in-project (.claude/workflow-ui/) and as a plugin: paths.py says where code and data live.
INPUT=$(cat)
SCRIPTS=$(cd "$(dirname "$0")" && pwd)
cd "$CLAUDE_PROJECT_DIR" 2>/dev/null || exit 0
# Plugin installs only: bring this folder's data up to the plugin's version first (see migrations/migrate.py).
# If the user's own files are behind, it prints one sentence for Claude to offer an update (passed on below).
MIG="$SCRIPTS/../../migrations/migrate.py"
MIGRATION_NOTE=""
[ -f "$MIG" ] && MIGRATION_NOTE=$(python3 -I "$MIG" --hook 2>/dev/null)
# An update installed while this session was open runs only after /reload-plugins: the board shows a banner, and
# Claude is told once per session to ask for it (reload_check.py). Passed on with the migration note.
RELOAD_NOTE=$(printf '%s' "$INPUT" | python3 -I "$SCRIPTS/reload_check.py" prompt 2>/dev/null)
[ -n "$RELOAD_NOTE" ] && MIGRATION_NOTE="${MIGRATION_NOTE:+$MIGRATION_NOTE }$RELOAD_NOTE"
# A plugin running from a git clone keeps itself current: fetch, and pull a newer release when it's safe (at most
# every 5 minutes, in the background so the message never waits; git_update.py). The banner above follows.
nohup python3 -I "$SCRIPTS/git_update.py" run >/dev/null 2>&1 &
export MIGRATION_NOTE
# Start the hidden skill history from the skills as they are, before anything can edit them (does nothing once
# started), so a folder's first edit is a draft the board can show and compare.
python3 -I "$SCRIPTS/skill_history.py" start --quiet >/dev/null 2>&1
python3 -I "$SCRIPTS/build_board.py" >/dev/null 2>&1      # rebuild now, so the board is current before it opens
# refresh the Builder (rule text quoted live from each SKILL.md) in the background: it reads the skill history with
# hundreds of git calls (~25s), and the app cancels this hook at 30s, which used to kill live.py below before it could
# start the run's trace and brief. The page picks the new data up when it lands.
nohup python3 -I "$SCRIPTS/build_workflows.py" >/dev/null 2>&1 &
nohup python3 -I "$SCRIPTS/build_board.py" --watch >/dev/null 2>&1 &
URL=$(python3 -I "$SCRIPTS/paths.py" url 2>/dev/null)
# In the Claude app the board is the app's preview (launch.json "workflow-ui", opened with preview_start), so the app
# keeps its tab; a copy left running in the background would hold the port, so stop it. Elsewhere, run it here.
# The always-on board (a macOS login item) is the default: it keeps running through sleep and app restarts
python3 -I "$SCRIPTS/serve_board.py" --ensure-agent >/dev/null 2>&1
if [ "$CLAUDE_CODE_ENTRYPOINT" = "claude-desktop" ]; then
  python3 -I "$SCRIPTS/serve_board.py" --release >/dev/null 2>&1
  # the app closes its preview tab when the computer sleeps and doesn't open it again on wake: when the board doesn't
  # answer, Claude reopens it first (only Claude can start the app's preview). The always-on board keeps answering
  # through sleep, so a wake since this session's last message counts too (wake_check.py).
  WOKE=$(printf '%s' "$INPUT" | python3 -I "$SCRIPTS/wake_check.py" prompt 2>/dev/null)
  if ! curl -s -o /dev/null --max-time 1 "$URL"; then
    echo "The workflow board isn't running (the computer slept, or the app stopped its preview). Before anything else, reopen it: preview_start with name workflow-ui, then show_pane with pane preview. Say nothing about it unless it fails."
  elif [ -n "$WOKE" ]; then
    echo "The computer woke from sleep since the last message, and the Claude app closes its preview tabs on sleep. Before anything else, call tabs_context: if no tab is on the workflow board ($URL), reopen it with preview_start with name workflow-ui, then show_pane with pane preview. Say nothing about it unless it fails."
  fi
elif ! curl -s -o /dev/null --max-time 1 "$URL"; then
  nohup python3 -I "$SCRIPTS/serve_board.py" >/dev/null 2>&1 &
fi
python3 -I "$SCRIPTS/serve_board.py" --register >/dev/null 2>&1   # the board's entry in .claude/launch.json, so the app can reopen it
# A folder never welcomed (the plugin was installed or reloaded mid-session, so SessionStart didn't run for it):
# the first message gets the first-run welcome instead. Does nothing once welcomed.
python3 -I "$SCRIPTS/welcome.py" session 2>/dev/null
# "/delegate:start" (the welcome again), "/dashboard", "delegate dashboard": the board, open (no run, no trace)
printf '%s' "$INPUT" | python3 -I "$SCRIPTS/welcome.py" prompt 2>/dev/null
# "delegate <verb> <thing> <name>": one line for Claude naming the command, what it means and the skill that does it
printf '%s' "$INPUT" | python3 -I "$SCRIPTS/commands.py" prompt 2>/dev/null
printf '%s' "$INPUT" | python3 -I "$SCRIPTS/live.py" prompt 2>/dev/null
exit 0
