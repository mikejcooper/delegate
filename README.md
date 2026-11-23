# Workflow manager

A Claude Code plugin that turns plain-words requests into workflows Claude runs for you, each step shown on a live
dashboard. Describe what you want ("every morning, email me the top BBC story"), and Claude drafts the workflow on
the dashboard, connects the accounts it needs, tries it once on your real data and publishes it. It comes with a
demo that needs no accounts.

## Install (one message)

Open the Claude app on the folder you want it in, start a session, and send:

```
Run <path to this repo>/install.sh
```

1. Claude checks the folder. An empty one gets "Install the workflow manager in <folder>?"; one with other things in
   it gets the choice of a new folder (you pick where) or installing there anyway.
2. It installs the plugin there.
3. Claude asks, on a card to click, to pin this chat and name it "🔗 Workflow Manager".
4. Send `open the dashboard`, in the same chat. The dashboard opens with a demo to run (`check the new york times`).

From then on it loads in every chat in that folder; `/workflow-manager:start` shows the welcome again.
In a terminal, `sh install.sh` asks the same questions, installs it and says how to start Claude there
(`claude "open the dashboard"`).

From GitHub, the one message is
`Run curl -fsSL https://raw.githubusercontent.com/mikejcooper/workflow-manager/main/install.sh | sh`.

On a Mac the dashboard stays on by itself: a small login item (one per folder, in `~/Library/LaunchAgents/`,
named `local.workflow-board.…`) keeps its server running through sleep and app restarts. To turn that off for a
folder, add `"board_always_on": false` to its `.workflow-manager-data/config/settings.json`.

## How it works

You ask for something. The front door finds the workflow whose trigger starts that kind of work; its trigger gets the
items and keeps the ones it takes, and each one goes through that workflow's steps. Every run is traced on the
dashboard, and nothing that reaches other people is sent without your yes.

```
        you
         |
         v
  core-dispatcher         the front door: one run per request
         |
         v
   workflow- skill        its trigger gets and keeps the items,
         |                its steps decide what to do with each
         v
   connection- skills     your accounts (Gmail, Slack, …)
         |
         v
     the dashboard        every step, every run, every version
```

| Skill | Role |
|---|---|
| `core-dispatcher` | Front door: runs a workflow's trigger, gives every item a repeatable ID so nothing is done twice, and runs each item through its workflow. |
| `core-architect` | Builds and changes workflows from your words: drafts them on the dashboard, wires them up, keeps the design rules, publishes versions. |
| `core-connections` | Sets up, checks and fixes your accounts: a connector, Claude's browser, your Chrome or an API. Never types a password. |
| `core-renamer` | Renames workflows, connections and categories, one or many at once, everywhere they are written. |
| `core-run-reviewer` | After each real run, checks it followed its workflow's path and notes anything off on the run. |
| `workflow-news-nyt-briefing` | The demo: "check the new york times" writes a one-page briefing of the newest NY Times stories. |

## Running it

| Say | Runs |
|---|---|
| a workflow's phrase ("check my email") | its trigger and the work it finds |
| "run workflow manager" | tick boxes of your triggers; the ticked ones run one after another |
| "run workflow <name> on <item>" | one workflow on one item |
| "test workflow <name>" | replays recorded real runs, with every outside read and write refused |
| "rerun workflow wf-…" | one earlier item again |
| "Add a workflow: <what you want>" | drafts a new workflow on the dashboard |
| "open the dashboard" | the dashboard |

## Your data

Everything it keeps goes in your folder's `.workflow-manager-data/`:

- `config/`: your settings and how your workflows show on the dashboard. The part to edit or commit.
- `history/`: requests, runs, screenshots, versions, and what workflows made (`pages/`) or worked with (`work/`).
  Private; don't commit.
- `system/`: generated files.

Suggested `.gitignore`: `.workflow-manager-data/history/` and `.workflow-manager-data/system/`.

## Repo layout

- `plugin/`: the plugin (engine skills, the demo, the dashboard in `workflow-ui/`, hooks, commands, migrations).
- `.claude-plugin/marketplace.json`: makes this repo a marketplace, so `claude plugin marketplace add mikejcooper/workflow-manager`
  works.
- `install.sh`: the one-message installer.

## Updates

- **Installed from a marketplace:** Claude Code updates the plugin (auto-update, or `/plugin`). A chat that was
  open keeps the old copy until `/reload-plugins`; the dashboard shows a banner saying so.
- **Running from a git clone** (a local folder marketplace, or `--plugin-dir`): the plugin keeps itself current. At
  most every 6 hours it fetches the clone's remote and fast-forwards to the newest release tag
  (`workflow-manager--v<version>`, made by `claude plugin tag`), or the tracked branch's tip when there are no tags.
  It waits while a run or test is open, and skips (saying why on the dashboard) when the clone has changes or commits
  of its own. Turn it off with `"auto_update": false` in `.workflow-manager-data/config/settings.json`.
  Keep the clone outside the folder you use it in: a plugin inside its own working folder counts as the plugin's
  source and never updates itself. One clone per machine: Claude Code knows a marketplace by its name
  (`workflow-manager`), so installing from a second clone points every folder at that one.
- **Releasing:** bump `version` in `plugin/.claude-plugin/plugin.json` and `WM_HOOKS_VERSION` in
  `plugin/hooks/hooks.json` to the same value (`plugin/workflow-ui/tests/test_reload_check.py` checks they match),
  add `plugin/migrations/<version>/` when stored data changes shape, then tag the release.
