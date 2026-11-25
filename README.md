# Delegate

A Claude Code plugin that turns plain-words requests into workflows Claude runs for you, each step shown on a live
dashboard. Describe what you want ("every morning, email me the top BBC story"), and Claude drafts the workflow on
the dashboard, connects the accounts it needs, tries it once on your real data and publishes it. It comes with a
demo that needs no accounts.

## Install (one message)

Open the Claude app on the folder you want it in, start a session, and send:

```
Run <path to this repo>/install.sh
```

1. Claude checks the folder. An empty one gets "Install Delegate in <folder>?"; one with other things in
   it gets the choice of a new folder (you pick where) or installing there anyway. For a new folder, Claude
   makes it and moves this chat into it (you approve the folder once), so you carry on in the same chat.
2. It installs the plugin there.
3. Send `delegate dashboard`, in the same chat. The dashboard opens on its welcome, in two steps: send `delegate pin`
   (Claude names this chat "🔀 Delegate Dashboard" and pins it), then run the demo (`check the new york times`).

From then on it loads in every chat in that folder; `/delegate:start` shows the welcome again.
In a terminal, `sh install.sh` asks the same questions, installs it and says how to start Claude there
(`claude "delegate dashboard"`).

From GitHub, the one message is
`Run curl -fsSL https://github.com/mikejcooper/delegate/raw/main/install.sh | sh`.

On a Mac the dashboard stays on by itself: a small login item (one per folder, in `~/Library/LaunchAgents/`,
named `local.workflow-board.…`) keeps its server running through sleep and app restarts. To turn that off for a
folder, add `"board_always_on": false` to its `.delegate-data/config/settings.json`.

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
| `core-sharer` | Shares a workflow as a zip (for someone new, an update, or an issue with the runs that went wrong) and brings one in: a draft, an update that keeps your changes, or a debugging copy. |
| `workflow-news-nyt-briefing` | The demo: "check the new york times" writes a one-page briefing of the newest NY Times stories. |

## Running it

Every command starts with `delegate`: `delegate <verb> <thing> <name>`, with any detail after a colon. A workflow's
own phrases ("check my email") work as they are, or with `delegate` in front. `delegate help` lists them all in the
chat, and the dashboard's buttons copy them for you. The older phrasings ("run workflow manager") still work.

| Group | Commands |
|---|---|
| Dashboard | `delegate dashboard` · `delegate start` · `delegate help` |
| Run | `delegate run` · `delegate run all` · `delegate run trigger <name>` · `delegate run workflow <name>: <item>` · `delegate run <workflow>: for real/as a test` · `delegate rerun <wf-…>: for real/as a test` · `delegate test workflow <name>: end to end` · `delegate test trigger <name>` |
| Inbox | `delegate answer <wf-…>: yes/no` · `delegate skip <wf-…>` · `delegate done <wf-…>` · `delegate mark <wf-…>: needs you/not run` · `delegate delete <wf-…>` · `delegate delete request <dispatch-…>` · `delegate turn on/off <setting>` · `delegate keep <wf-…>: test` |
| Build | `delegate add workflow: <what you want>` · `delegate create workflow <name>` · `delegate change workflow <name>: <what to change>` · `delegate undo workflow <name>` · `delegate discard workflow <name>` · `delegate add examples workflow <name>` · `delegate add tests workflow <name>` · `delegate import <path>` |
| Publish | `delegate validate workflow <name>` · `delegate publish workflow <name>: without validating` · `delegate restore workflow <name>: v2` · `delegate delete workflow <name>` |
| Names | `delegate rename workflow <name>: <new name>` · `delegate move workflow <name>: <category>` · `delegate tidy names` |
| Schedules | `delegate schedule workflow <name>: weekdays 08:00` · `delegate pause workflow <name>` · `delegate resume workflow <name>` · `delegate unschedule workflow <name>` |
| Connections | `delegate set up connection <name>` · `delegate check connection <name>` · `delegate fix connection <name>` · `delegate check connections` |
| Reviews | `delegate review <wf-…>` · `delegate dismiss <sg-…>` · `delegate fix <sg-…>` |
| Share | `delegate share workflow <name>` · `delegate share workflow <name>: update` · `delegate share workflow <name>: issue <wf-…> <wf-…>` · `delegate pick workflow <name>: c1 mine/theirs/merge` · `delegate replay debug <name>: <wf-…>` · `delegate share debug <name>: fix` · `delegate delete debug <name>` |
| Your workflows | their own phrases, e.g. `check my email` (or `delegate check my email`) |

## Your data

Everything it keeps goes in your folder's `.delegate-data/`:

- `config/`: your settings and how your workflows show on the dashboard. The part to edit or commit.
- `history/`: requests, runs, screenshots, versions, and what workflows made (`pages/`) or worked with (`work/`).
  Private; don't commit.
- `system/`: generated files.
- `debug/`: debugging copies brought in from someone's issue zip, with their runs. Private; don't commit.

Suggested `.gitignore`: `.delegate-data/history/`, `.delegate-data/system/` and
`.delegate-data/debug/`.

## Sharing

A workflow's **Share** tab (or **Share…** in its ⋯ menu) makes a zip in your Downloads folder, to pass on
yourself by Slack, email or a drive:

- **Share it**: the whole workflow, for someone new.
- **Share the update**: a newer version for people who have it. **How will this affect people who have it?** shows
  what changes for someone who never changed their copy, and for someone who did.
- **Share an issue**: the runs that went wrong and what they read, so someone can debug them.

Drop a zip into your chat and Claude says what it is. A new workflow comes in as a draft to check and publish. An
update keeps your own changes and asks only where you both changed the same thing. An issue comes in as a debugging
copy under **Debugging** in the Builder, with its runs, never run on its own and never in your Inbox; fix it there
and send the fixed version back. A share never carries a sign-in, key or token, and never says who made it.

## Repo layout

- `plugin/`: the plugin (engine skills, the demo, the dashboard in `workflow-ui/`, hooks, commands, migrations).
- `.claude-plugin/marketplace.json`: makes this repo a marketplace, so `claude plugin marketplace add mikejcooper/delegate`
  works.
- `install.sh`: the one-message installer.

## Updates

- **Installed with the install script from GitHub** (the usual way): the script clones this repo once per
  computer, to `~/.delegate/delegate` (set `WM_CLONE` to choose another folder; installs before 0.16.0 used
  `~/.workflow-manager/workflow-manager` and keep updating from there), and Claude Code
  runs the plugin from that clone. The plugin keeps it current itself: on a message and at the end of each turn, at most every 5 minutes, it
  checks this repo over HTTPS and fast-forwards to the newest release tag (`delegate--v<version>`, made by
  `claude plugin tag`; `workflow-manager--v<version>` before the rename), or the branch tip when there are no tags. The new release, its migrations included, runs
  from the next message, in every folder that uses the clone. It waits while a run or test is open, and skips
  (saying why on the dashboard) when the clone has changes or commits of its own. Turn it off with
  `"auto_update": false` in `.delegate-data/config/settings.json`.
- **A reload is rarely needed.** Claude Code reads a few things only when a chat starts: the hook list, the skills'
  names and descriptions, and the commands. Only a release that changes one of those shows a banner asking an open
  chat to type `/reload-plugins` (or start a new chat).
- **Installed from a marketplace's copy** (`claude plugin install`, or the install script without git): Claude Code
  updates it (turn on auto-update in `/plugin` → Marketplaces). Each version sits in its own folder, so an open
  chat keeps the old one until `/reload-plugins`; the dashboard says so.
- **One clone per computer:** Claude Code knows a marketplace by its name (`delegate`), so every folder on
  the computer uses the same one. If that name already points at another copy (a developer's checkout), the
  install script stops and says how to switch. Keep the clone outside the folders you use it in: a plugin inside its own working
  folder counts as the plugin's source and never updates itself.
- **Releasing:** bump `version` in `plugin/.claude-plugin/plugin.json` and `WM_HOOKS_VERSION` in
  `plugin/hooks/hooks.json` to the same value (`plugin/workflow-ui/tests/test_reload_check.py` checks they match),
  add `plugin/migrations/<version>/` when stored data changes shape, then tag the release.
