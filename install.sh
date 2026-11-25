#!/bin/sh
# Install the Delegate plugin into the current folder.
#
# In the Claude app, open a session on the folder you want it in and send:
#     Run <path to this repo>/install.sh
# From GitHub, the same from anywhere:
#     Run curl -fsSL https://github.com/mikejcooper/delegate/raw/main/install.sh | sh
#
# The steps:
#   1. Without --yes it installs nothing: it says which folder it would install into, so Claude can ask the user
#      first ("Install Delegate in <folder>?"). On their yes Claude runs it again with --yes. In a
#      terminal it asks the question itself.
#      A folder with other things in it gets the choice of a new folder instead: the script makes it, and in the
#      Claude app Claude moves this same chat into it and installs there, so there is no second chat to start.
#   2. It installs the plugin into that folder (project scope). From GitHub it first clones the repo, once per
#      computer, to ~/.delegate/delegate (WM_CLONE to change it; ~/.workflow-manager/workflow-manager before 0.16.0); the plugin runs from that clone
#      and keeps it up to date itself.
#   3. It says to send "delegate dashboard", in the same chat. The board's welcome then has two steps: in the Claude
#      app, "delegate pin" (Claude names and pins this chat); then run the first workflow.
#
# Where the plugin comes from, first that applies: an argument (a folder or owner/repo), $WM_SOURCE, the repo this
# script sits in, else GITHUB. Safe to run again: what is already installed is kept.
set -e
GITHUB="mikejcooper/delegate"   # the public repo
MARKETPLACE="delegate"         # the "name" in .claude-plugin/marketplace.json

YES=""
NEWFOLDER=""
WHERE=""                  # --in=<folder>: where --new-folder makes it
SOURCE=""
GIVEN=""                  # the source as it was given, to say again in the --yes command
for a in "$@"; do
  case "$a" in
    --yes|-y) YES=1 ;;
    --new-folder) NEWFOLDER=1 ;;
    --in=*) WHERE=${a#--in=} ;;
    *) SOURCE=$a; GIVEN=" \"$a\"" ;;
  esac
done
here=$(cd "$(dirname "$0")" 2>/dev/null && pwd || true)
SOURCE=${SOURCE:-${WM_SOURCE:-}}
if [ -z "$SOURCE" ] && [ -f "$here/.claude-plugin/marketplace.json" ]; then SOURCE=$here; fi
SOURCE=${SOURCE:-$GITHUB}
if [ -z "$SOURCE" ]; then
  echo "Where is the plugin? Give a folder or owner/repo: sh install.sh <folder or owner/repo>" >&2
  exit 1
fi
PLUGIN="delegate@$MARKETPLACE"
FOLDER=$(pwd)

# The install message the user sends, as they'd type it (~ for the home folder)
if [ -f "$here/install.sh" ]; then MSG="Run $(printf '%s' "$here/install.sh" | sed "s|^$HOME|~|")"
else MSG="the same install message"; fi
DOCS="https://code.claude.com/docs/en/desktop#start-a-session"

# 0. What it needs, checked before anything is asked or installed, so a missing piece is named up front instead of
#    failing halfway: a Mac, Claude Code's `claude` command, and git and Python 3 (both in Apple's Command Line
#    Tools). Without the Tools, macOS has only stand-ins at /usr/bin/git and /usr/bin/python3 that open an "install
#    the developer tools?" window and fail, so those don't count; a git or Python from elsewhere (Homebrew) does.
MISSING=""
need() { MISSING="$MISSING
- $1"; }
OS=$(uname -s)
if [ "$OS" != "Darwin" ]; then
  need "A Mac. Delegate runs on macOS only for now (this computer runs $OS)."
fi
if ! command -v claude >/dev/null 2>&1; then
  need "Claude Code's \`claude\` command (the Claude app has Claude Code built in, but this command is a separate
  install). Install it with: curl -fsSL https://claude.ai/install.sh | bash
  then open a new terminal, or restart the Claude app (https://code.claude.com/docs/en/setup)."
fi
TOOLS=1
if [ "$OS" = "Darwin" ] && ! xcode-select -p >/dev/null 2>&1; then TOOLS=""; fi
usable() {   # $1 is a real command here, not one of macOS's stand-ins
  p=$(command -v "$1" 2>/dev/null) || return 1
  case "$p" in /usr/bin/*) [ -n "$TOOLS" ] ;; *) return 0 ;; esac
}
if [ "$OS" = "Darwin" ] && { ! usable git || ! usable python3; }; then
  need "Apple's Command Line Tools (they include git and Python 3). Install them with: xcode-select --install
  (a window opens; it takes a few minutes)."
elif usable python3 && ! python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
  need "Python 3.8 or newer (this computer has $(python3 --version 2>&1)). Update Apple's Command Line Tools in
  System Settings > General > Software Update."
fi
if [ -n "$MISSING" ]; then
  echo "Nothing installed. Delegate needs:$MISSING"
  echo
  echo "Once that's done, run the same install again."
  exit 1
fi

# --new-folder [--in=<folder>]: the user chose a folder of its own, made inside the folder they picked (their home
# folder when none is given): "Delegate", or "… 2", "… 3" when that is taken and not empty. Nothing is installed
# here. In the Claude app, Claude moves this same chat into the new folder (the app's change_directory tool; the
# user approves that one folder) and installs there in the same turn, so there is no second chat to start. Without
# that tool, or when the user declines the move, it falls back to how to start a chat in the folder by hand.
if [ -n "$NEWFOLDER" ]; then
  WHERE=${WHERE:-$HOME}
  case "$WHERE" in "~") WHERE=$HOME ;; "~/"*) WHERE="$HOME/${WHERE#\~/}" ;; esac
  if [ ! -d "$WHERE" ]; then
    echo "There's no folder $WHERE. Ask the user where to make it again (the same card), and run this again with"
    echo "--in=<that folder>."
    exit 1
  fi
  WHERE=$(cd "$WHERE" && pwd)
  NEW="$WHERE/Delegate"; n=2
  while [ -e "$NEW" ] && [ -n "$(ls -A "$NEW" 2>/dev/null | grep -v -x .DS_Store)" ]; do NEW="$WHERE/Delegate $n"; n=$((n + 1)); done
  mkdir -p "$NEW"
  NAME=$(basename "$NEW")
  IN=$(printf '%s' "$WHERE" | sed "s|^$HOME\$|your home folder|; s|^$HOME/|~/|")
  if [ -f "$here/install.sh" ]; then THERE="cd \"$NEW\" && sh \"$here/install.sh\" --yes$GIVEN"
  else THERE="cd \"$NEW\" && curl -fsSL https://github.com/$GITHUB/raw/main/install.sh | sh -s -- --yes$GIVEN"; fi
  echo "Made the folder $NEW (empty). Nothing installed yet. Say nothing to the user until the end of these steps."
  echo
  echo "1. If you have the tool mcp__ccd_directory__change_directory (load it with ToolSearch if it is listed as"
  echo "   deferred), call it with path \"$NEW\". It moves this chat into the new folder; the user approves it."
  echo "2. If that worked, run: $THERE"
  echo "   and do what it says. The chat is in $NAME from the next message on, so the user stays in this chat."
  echo "3. If you don't have that tool, or the move was declined or failed, install nothing: your whole reply to the"
  echo "   user is the block below, word for word (it is markdown), with nothing before or after it:"
  echo
  echo "## Your new folder is ready: **$NAME**"
  echo
  echo "Start a chat in it, and install there:"
  echo
  echo "1. Press **⌘N** (or click **+ New** at the top of the sidebar)."
  echo "2. Under the message box, click the **folder** button and choose **$NAME** (in $IN)."
  echo "3. In that new chat, send:"
  echo
  echo '```'
  echo "$MSG"
  echo '```'
  echo
  echo "[How to pick a folder for a chat]($DOCS)"
  exit 0
fi

# 1. The folder, confirmed before anything is installed. It works best in a folder of its own: it keeps its
#    settings, runs and history there, and a folder with other work in it mixes the two.
if [ -f "$FOLDER/.delegate-data/system/version.json" ] || [ -f "$FOLDER/.workflow-manager-data/system/version.json" ] || grep -qsE "(delegate|workflow-manager)@" "$FOLDER/.claude/settings.json"; then
  INSTALLED=1
else
  INSTALLED=""
fi
# what else is here: everything but macOS's .DS_Store, and a .claude folder holding only the app's own files
OTHER=$(cd "$FOLDER" && for f in * .[!.]* ..?*; do
  [ -e "$f" ] || continue
  [ "$f" = ".DS_Store" ] && continue
  if [ "$f" = ".claude" ] && [ -z "$(cd .claude && ls -A | grep -v -x -e launch.json -e settings.local.json -e .DS_Store)" ]; then continue; fi
  echo "$f"
done)
COUNT=$(printf '%s' "$OTHER" | grep -c . || true)
SOME=$(printf '%s\n' "$OTHER" | head -3 | paste -sd ',' - | sed 's/,/, /g')
[ "$COUNT" -gt 3 ] && SOME="$SOME, …"
if [ -f "$here/install.sh" ]; then AGAIN="sh \"$here/install.sh\" --yes$GIVEN"
else AGAIN="the same command with --yes added (piped from curl: ... | sh -s -- --yes$GIVEN)"; fi

if [ -n "$INSTALLED" ] && [ -z "$YES" ]; then
  if [ -t 0 ]; then
    echo "Delegate is already installed in $FOLDER. To use it, start Claude here and send: delegate dashboard"
  else
    echo "Nothing to do: Delegate is already installed in $FOLDER."
    echo "Tell the user in one line: send \"delegate dashboard\" to open it."
  fi
  exit 0
fi

if [ -z "$YES" ]; then
  if [ -t 0 ]; then   # a terminal: ask here
    if [ "$COUNT" -gt 0 ]; then
      echo "This folder isn't empty: $COUNT other item(s) ($SOME)."
      echo "Delegate works best in a folder of its own. To use a new one: mkdir ~/\"Delegate\" && cd ~/\"Delegate\", then run this again."
      printf 'Install it in %s anyway? [y/N] ' "$FOLDER"
    else
      printf 'Install Delegate in %s (an empty folder, good)? [y/N] ' "$FOLDER"
    fi
    read -r answer
    case "$answer" in y|Y|yes|Yes) ;; *) echo "Nothing installed."; exit 0 ;; esac
  elif [ "$COUNT" -gt 0 ]; then   # Claude ran it, in a folder with other things in it
    if [ -f "$here/install.sh" ]; then MAKE="sh \"$here/install.sh\" --new-folder$GIVEN"
    else MAKE="the same command with --new-folder added"; fi
    echo "Nothing installed. This folder isn't empty: $COUNT other item(s) ($SOME). Delegate works best in"
    echo "a folder of its own: it keeps its settings, runs and history there."
    echo
    PARENT=$(dirname "$FOLDER" | sed "s|^$HOME\$|your home folder|; s|^$HOME/|~/|")
    echo "Say nothing else; ask with the AskUserQuestion tool (cards the user clicks, never a question in your text)."
    echo "Card 1: question \"This folder already has other things in it ($SOME). Delegate works best in"
    echo "a folder of its own. Make a new one?\", header \"Folder\", options \"Make a new folder (Recommended)\""
    echo "(\"Pick where, and it makes an empty Delegate folder there and moves this chat into it\") and \"Install here anyway\" (\"Puts it"
    echo "in this folder, alongside what's already here\")."
    echo "On Install here anyway, run: $AGAIN."
    echo "On Make a new folder, card 2: question \"Where should the Delegate folder go?\", header \"Where\","
    echo "options \"Your home folder (Recommended)\" (\"~/Delegate\"), \"Documents\" (\"~/Documents/Delegate\") and \"Next to this folder\" (\"In $PARENT\"); the card's own Other box takes any other folder."
    echo "Then run: $MAKE --in=<the folder they picked: $HOME, $HOME/Documents, $(dirname "$FOLDER"), or the one they"
    echo "typed> and do what it says."
    exit 0
  else                            # Claude ran it, in an empty folder
    echo "Nothing installed yet (this folder is empty, which is right for it)."
    echo
    echo "Your whole reply to the user is this one line, word for word, with nothing before or after it:"
    echo
    echo "Install Delegate in $FOLDER?"
    echo
    echo "On their yes, run: $AGAIN. On a no, install nothing."
    exit 0
  fi
fi

# 2. Install
echo "Installing Delegate into $FOLDER"
# From GitHub: a git clone, one per computer, outside every project folder, which Claude Code reads in place. The
# plugin keeps it current itself (workflow-ui/scripts/git_update.py: it checks the repo over HTTPS and pulls each
# new release), and a pulled release runs from the next message. Without git, Claude Code's own copy instead.
if [ ! -d "$SOURCE" ] && command -v git >/dev/null 2>&1; then
  case "$SOURCE" in http://*|https://*) URL=$SOURCE ;; *) URL="https://github.com/$SOURCE.git" ;; esac
  CLONE=${WM_CLONE:-$HOME/.delegate/delegate}
  # a computer installed before 0.16.0 keeps its clone where it is: one clone per computer, never two
  if [ -z "${WM_CLONE:-}" ] && [ ! -d "$CLONE/.git" ] && [ -d "$HOME/.workflow-manager/workflow-manager/.git" ]; then
    CLONE=$HOME/.workflow-manager/workflow-manager
  fi
  if [ -d "$CLONE/.git" ]; then
    HAVE=$(git -C "$CLONE" remote get-url origin 2>/dev/null || true)
    if [ "${HAVE%.git}" != "${URL%.git}" ]; then
      echo "$CLONE is a clone of $HAVE, not $URL. Move it away, or set WM_CLONE to another folder, and run this again." >&2
      exit 1
    fi
    # an older install's clone may be several releases behind: bring it up to date now, not on the plugin's first run
    if GIT_TERMINAL_PROMPT=0 git -C "$CLONE" pull --ff-only --quiet 2>/dev/null; then
      echo "Using the clone already at $CLONE, brought up to date"
    else
      echo "Using the clone already at $CLONE (couldn't update it now; the plugin updates it itself)"
    fi
  else
    mkdir -p "$(dirname "$CLONE")"
    if ! GIT_TERMINAL_PROMPT=0 git clone --quiet "$URL" "$CLONE"; then
      echo "Couldn't download the plugin from $URL." >&2
      exit 1
    fi
  fi
  SOURCE=$CLONE
fi
# A marketplace name is one per computer. If "$MARKETPLACE" already points at another folder (another copy of
# Delegate, such as a developer's checkout), adding this one fails quietly and the install would turn on that other
# copy: stop and say so instead.
if [ -d "$SOURCE" ]; then
  TAKEN=$(claude plugin marketplace list --json 2>/dev/null | WM_NAME="$MARKETPLACE" WM_SOURCE="$SOURCE" python3 -I -c '
import json, os, sys
try:
    items = json.load(sys.stdin)
except ValueError:
    items = []
for m in items:
    if isinstance(m, dict) and m.get("name") == os.environ["WM_NAME"]:
        where = m.get("path") or m.get("repo") or m.get("url") or ""
        if not m.get("path") or os.path.realpath(where) != os.path.realpath(os.environ["WM_SOURCE"]):
            print(where)
')
  if [ -n "$TAKEN" ]; then
    echo "Nothing installed. On this computer the name \"$MARKETPLACE\" already belongs to another copy of Delegate:" >&2
    echo "  $TAKEN" >&2
    echo "Installing now would turn on that copy, not $SOURCE." >&2
    echo "To use $SOURCE instead, run: claude plugin marketplace remove $MARKETPLACE" >&2
    echo "then run this install again. Other folders that used that copy will then use this one." >&2
    exit 1
  fi
fi
claude plugin marketplace add "$SOURCE" --scope project >/dev/null 2>&1 || true
claude plugin install "$PLUGIN" --scope project >/dev/null 2>&1 || true

# Where Claude Code reads the installed plugin from (a local folder in place; a GitHub one from its plugin cache).
# The list holds every folder's installs on this computer: take this folder's (a user-wide one if it has none).
ROOT=$(claude plugin list --json 2>/dev/null | WM_PLUGIN="$PLUGIN" WM_FOLDER="$FOLDER" python3 -I -c '
import json, os, sys
try:
    items = json.load(sys.stdin)
except ValueError:
    items = []
here = os.path.realpath(os.environ["WM_FOLDER"])
mine = [p for p in items if isinstance(p, dict) and p.get("id") == os.environ["WM_PLUGIN"]]
mine.sort(key=lambda p: 0 if os.path.realpath(p.get("projectPath") or "/nowhere") == here else 1 if p.get("scope") == "user" else 2)
for p in mine[:1]:
    if os.path.realpath(p.get("projectPath") or "/nowhere") == here or p.get("scope") == "user":
        print(p.get("readFromFolder") or p.get("installPath") or "")
')
if [ ! -f "$ROOT/workflow-ui/scripts/welcome.py" ]; then
  echo "The plugin didn't install. Check: claude plugin marketplace add $SOURCE --scope project" >&2
  exit 1
fi

# 3. What to do next: delegate dashboard
CLAUDE_PROJECT_DIR="$FOLDER" python3 -I "$ROOT/workflow-ui/scripts/welcome.py" installed
