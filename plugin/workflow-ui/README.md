# Trace board

Two pages, served on `http://127.0.0.1:8765` by `scripts/serve_board.py` (installed as a plugin: the project's own port and data folder, see `scripts/paths.py`). The hooks
(`scripts/on_prompt.sh`, `scripts/on_skill_start.sh`) rebuild the data and keep the board's `workflow-ui` entry in
the project's `.claude/launch.json` (`serve_board.py --register`). In the Claude app the board is the app's preview
(`preview_start` with that name), so the app owns its tab and can reopen it; the hooks stop any copy left running on
its own in the background (`--release`), which would hold the port. Anywhere else the hooks start the server
themselves. A copy started while another already serves the board stands by instead of failing, and takes over if
the first stops.

**Live feedback** (`scripts/live.py`, run only by the hooks):
- `on_prompt.sh` → `live.py prompt`: a dispatcher request ("run dispatcher", "check my emails", "what came in",
  "rerun workflow wf-…") gets its trigger trace and header (`dispatch-HHMM`, `kind` trigger, `skip_done`) at once,
  so the board shows it the moment the request is sent. Claude is told the run ID to reuse. Any other request
  closes the live marker.
- `on_skill_start.sh` → `live.py skill`: when the dispatcher starts, reuses that trigger, or creates it if the
  request wasn't recognised at prompt time.
- `on_tool.sh` (PreToolUse, every tool) → `live.py tool`: while a run is open (`traces/.live/current`), writes
  one plain-words "now doing" note (e.g. "Opening Gmail") to `traces/.live/<run>.json`. The Inbox page shows it as
  **Now:** on the running pull-in and its Pulling in tab. It exits at once when no run is open, and never writes to a trace.
- The marker closes when the trace gets its end line, when a non-dispatcher request arrives, or after 30 idle minutes.
- Until the trigger line lands, the request's Triggers table shows one **Choosing…** row (**No trigger**
  if the run ended without one), never a made-up trigger.

| Page | Shows | Reads | Built by |
|---|---|---|---|
| **Inbox** `workflows.html` (the board's home) | What happened: every item, run or not, grouped by the request that pulled it in, with each run's steps and path; views; Run triggers | `board-data.js` + `workflows-data.js` + `views.json` | `scripts/build_board.py` (from `traces/*.jsonl`; `--watch` keeps it live) |
| **Builder** `workflow-viewer.html` (was the Workflow Viewer; old `workflows.html?w=…` links land here) | What can happen: each workflow, with real runs and "If…" examples | `workflows-data.js` + `board-data.js` | `scripts/build_workflows.py` (from `workflows.json` + each skill's SKILL.md) |

**The top bar** (`topbar.js`) is the same on all three pages: **Delegate** on the left, the
**Inbox · Builder** switch in the middle, then a live dot (its tooltip says when the board last updated) and one
split button. Its face follows the page: **Run** (run your triggers) on the Inbox, **Build** (add a workflow) on the
Builder; ▾ opens both. While a trigger run is pulling
items in, the face reads **Running 2/5** (the trigger it's on, of the ones it chose to run) and opens the Run
triggers panel. From the Builder or Add a workflow, Run triggers opens the Inbox with `?panel=1`, which opens the
panel. Under 480px wide the face shows only its icon. A page that doesn't load `board-data.js` itself adds
`data-poll` to `<header id="topbar">`.

The Builder opens on **Overview** (no `?w=`): a fixed, high-level picture of how the board
works (something comes in → the agent picks skills and their order → watch it on the Inbox page →
feedback fixes the skill for next time), led by one moving picture: **Run triggers** → several triggers →
several workflows, with items flowing through (hidden dots under reduced motion). It deliberately uses no real skill or workflow names, so it
needs no update when skills change. The dispatcher's own view is `?w=disp`.

How traces are written is in `RUN-TRACE.md` (next to this file). This file covers the
Builder, and the step style both pages share.

**One step component (both pages).** Steps are drawn only by `steps.js` with `steps.css`: same rows, same
stages, same status colours. The Builder draws its own card header, see "The workflow page" below.
**One outcome box (both pages).** A run's **Workflow outcome** is `Steps.outcome` in `steps.js`, drawn as a short
timeline by `Steps.flowBox` (a path's outcome on the Builder uses the same): a one- or two-sentence summary, then
only the steps that mattered (failed, waited on you, uncertain, made, changed, handed on) with the quiet ones as a
count, and a one-line tally; Copy and Open buttons sit on the step they are about. Its status is a thin band across
the top of the card ("✓ Done · took 1m 6s"; green, amber or red), and every section title has a thin black icon. Simple / Detail (Detail adds the facts
and each step's kind) is remembered apart from the steps' own. Rule 31 has the reasons. The Builder shows it on a run's page; the Inbox shows it, and only it, when you
open an item that ran, with the buttons under it: **Answer in Claude chat** (when it needs you), **Run again**,
**Discuss in Claude chat** and **Open in Builder ↗**, where the run's steps are.
A page only turns its steps into items (the Viewer from `workflows.json`, the Inbox from a run's trace) and hands
them over; neither page draws a step row itself. Change how steps look in those two files, never in a page, so
the pages can't drift apart. Which workflow step a trace step is comes from one test too: `RunPath.matches` in
`runpath.js`.

**Steps that ran.** When a page shows a real run (the Inbox always; the Viewer once a run is picked), each step that
ran gets a small badge on its number: ✓ done, ✕ failed, ! waiting on you, ? not sure, – left alone, with a faint
green line joining the finished steps. A stage whose steps all finished gets its own tick; one holding a failed or
waiting step opens by itself. A path's "what should happen" has no badges. The Viewer takes each step's status from
the run's trace line for it (`RunPath.mapSteps`, the same mapping the Inbox uses). A run still going opens too:
the Inbox's **Open in Builder ↗** links to it as soon as it starts, and the Builder (which reloads `board-data.js`
every second) adds its steps as they are logged, under a last pulsing **Now** row with the hooks' "now doing" line.

**Step style.** Every step is the same two lines: its kind in small grey capitals (READ, SEARCH, DECIDE, DRAFT…)
in a fixed column, then its title; under that, one grey line that only adds what the title doesn't already say.
In a run that line is the trace step's `sub`, else for a decision "→ " and the answer it gave, else the step's
result. Outside a run it is the step's `what`, unless that only repeats the title. A light bar on the left names
the skill doing the step, only where the skill changes.

**Step inspector.** Clicking a step opens it under its row, full width. In a run it has three tabs, Summary first:
- **Summary**: what went in, what came out (a few short tags, one plain line, an orange warning when the result
  doesn't match what was asked) and how, from the trace step's `in`, `tags`, `result`, `warn` and `why`.
- **Data**: the step's raw fields, Input above Output, as a table or as JSON (one switch for both), from the trace
  step's `io`. An older trace without `io` shows the fields it did log; the first step also shows the item's input.
- **Logic**: what the step does, the rule in plain words with **Show the rule text**, and for a decision every
  option with the one this run took marked.
A decision the trace never logged as its own step says so, and links to the step whose result decided it. Outside a
run there is no data, so a step opens on its logic alone, with no tabs. There is no global Details switch.

**Why the step list looks like this (0.12).** Designed on the "Workflow steps" canvas, in this order:
1. *Kind as a small grey word, not a coloured pill.* Pills on every row competed with the titles; the kind is
   still there for scanning, but the title is what you read.
2. *Same two lines for every step.* Decisions used to put their answer in a chip after the title and other steps
   put a result under it; one shape reads faster down the list.
3. *The grey line only adds information.* A result that restates the title ("Sign-in zero-days, last 24h" → "None
   found in the last 24 hours…") is noise; "None found · 3 searches" is news. Hence the trace's `sub` field.
4. *Compact rows, vertical layout kept.* A stripped-down list (no kinds, no skill rail) was less clear, and generous
   spacing made a short run look long; the fix was hierarchy and tight spacing, not removing structure.
5. *Quieter stages, inset steps.* Stages are buckets: a muted title and a step count, so the steps inside lead.
6. *Click a step instead of a Details switch.* The switch opened everything at once and sat in the header as one
   more control; you open the step you're asking about.
7. *Summary before Data.* Raw input/output tables look technical; a plain "went in / came out" with a warning is
   what you want first, like n8n's node output but in words. The raw fields stay one tab away, stacked (not side
   by side) so long values have room, with one table/JSON switch.
8. *Logic without "comes from".* The skill file and section added little; the rule text is still one click away.

**Stages (both pages).** A workflow with `stages` opens on them: one numbered row per stage with its
plain title and its step count (a stage holding a failed or waiting step is flagged). Clicking a stage opens its
steps under it; **Open all stages** opens every stage. A path hides a stage none of whose steps run. A workflow of 7 steps or fewer has no stages and shows
its steps flat, as before (the architect's rule 23). A trace step that matches no workflow step stays in the
stage before it.

### The workflow page (Builder)

Top to bottom, for one workflow (`?w=<id>`):

1. **Header.** Above the title, the category, a kind tag (Trigger, Workflow, Shared, Core, from the skill name)
   and the version in use as a label: "🕘 v4 · published 13 Nov · Versions" ("· editing a draft" while there is
   one; "Not published" for a new workflow, whose bar on top shows Draft › Connect › Test › Publish as a progress
   bar with one button, and whose **Run ▾** is hidden until it is ready to publish); it opens the **Versions** tab (a core or shared skill has no tabs: its versions open under its header). On the right, two buttons: **Run ▾** and **Change** (it copies `change workflow <name>: `
   for the chat; going back to an earlier version lives in Versions). Every action copies a request for the chat
   with Claude; the page never runs or changes anything itself (see "Actions" below). A core skill shows
   `Built in` and no buttons; a shared skill or a part that runs inside another has no **Run ▾**.
2. **Tabs**, on a workflow or trigger page (not on a core or shared skill, a part, the all-triggers page or an
   import): **Overview** · **Past runs N** · **Connections** · **Helper**, plus **Versions N** while it's open (only the
   version link opens it; moving to another tab hides it again). `?tab=runs`, `?tab=helper` or `?tab=versions` opens on
   that tab; an old `?tab=examples` opens the Overview, where the examples are.
   **Helper** is the actions (`helperActions`): every thing you can do to the workflow, grouped (Run it, Schedule,
   Change it, Tests and examples, Manage), each a card with its exact chat line and **Copy**; cards follow its state
   (Publish only with a draft, Undo after a change, Pause only with a schedule).
   **Schedules.** A schedule (`weekdays 08:00`, `every day 12:00 17:30`, `every 2 hours 08:00-18:00`) is set from
   the chat and kept in the data folder by `schedules.py` (a `schedule:` line in a Definition works too;
   `entries.parse_schedule`). Every scheduled run runs its items; anything that needs a yes waits on the Inbox. The build puts it on its trigger's entry;
   `RunPath.nextRun` works out the next time. The Overview shows a **Schedule** row (with **change**, which copies
   `change schedule workflow …`), its sidebar row a small clock, its live bar says when it runs, and the ⋯ menu offers
   **Schedule it** (or Change / Pause the schedule). On the Inbox, a request whose trace header has `schedule`
   (plus `due` and `since` when it ran late) is titled "Scheduled, …" with a clock, and the default view (All items) opens
   with one quiet row, "N scheduled workflows · next run …", whose **View scheduled ›** opens the built-in
   **Scheduled** view (in the sidebar once there is a schedule; its count is the schedules): each schedule and its
   next run (or paused) at the top, then the items scheduled runs found.
   Every box on the page has the same look: a bold header on a soft band, its content in a white list.

**Overview tab**, four boxes:

1. **Overview**: a compact list with no icons. **What it does** (the summary; **more** opens the full description
   and skill name), **Starts when** (triggers and workflows that hand it work; "you run it directly" only when
   nothing else starts it; on a trigger, the phrases), **Each run needs** (the fields from `needs`, optional ones
   behind "+ N optional"; on a trigger, **Each item has**) and **Can start next** (workflows it can hand work to; on a trigger, **Sends items to**) or **Gives back**. A workflow's own
   code adds **Part of**. A row with nothing to say is left out.

   **Summaries** live in `workflows.json` under the top-level `summaries` (`"workflow:<id>"`, `"trigger:<key>"`),
   apart from each workflow, so adding or editing a line never turns a workflow into a draft. A skill's
   Definition block `summary:` wins once it has one. A page without either falls back to the description's
   first sentence.
2. **Workflow decisions** (Trigger decisions on a trigger): one row per decision, the whole row a button that opens
   its answers, the answer picked on the right ("· stops" or "· waits for you" when it does). On top, **Example**:
   a few chips and "+N more" (never "+1 more"), which opens every example's card (Comes in, Steps, You get); a chip
   sets every answer for that example, and the one picked, clicked again, clears it: every route shows and each
   decision reads "any answer". Answers that match no example show **Custom**. Only the questions the chosen answers lead to
   are shown (built from each decision's `alts` and the saved paths in `simulated`); past 5, the rest sit behind
   **Show N more questions**. After a change, **Back to the usual run** sits in the header.
3. **Workflow steps** · "N stages based on workflow decisions": the steps for those answers (`steps.js`), with
   **Expand all** / **Collapse all** (when there are stages) and **Simple / Detail** (each step's logic under it: what it does, the
   rule behind it, every option and where it leads, this path marked, and the rule text; it opens closed stages
   too). A click on one step shows just that step's details; a second click hides them. On top, the trigger row:
   **Starts from** the trigger (a dropdown when there are several), or the workflow that hands it items, or "You,
   by hand", then this workflow, outlined. A trigger's page has it the other way round: **Where items go**.
   On a run's page the row reads **How this item got here**: the trigger that pulled the item in, with when, and a
   click opens that trigger run's own page (Viewing a request). A rerun points to the trigger run that first pulled
   the item in. With no trigger run to find (an item run by hand, an old trace), it opens the trigger's page.
4. **Workflow outcome**: the same timeline as a run's (above), for the route picked: a status pill (Done, Hands on,
   Waits for you, Check this, Stops, Ends with a note, from the path's `out`), the example's `ok` as the summary
   (else the path's "Shown to you" results), then the steps on this route that make or change something, hand on,
   or can wait on you or stop (from each step's `type`, `tag`, options and `starts`). Detail adds one line per
   result (top-level `results`, below), **Not touched** last. With no example picked: "Depends", every such step
   marked as only on some routes.

**Past runs tab**: every run, newest first: when, version (`v0` before version history started), the verdict and
path, the Inbox's status word (Done, Needs you, Check this, Failed, Stopped), **View here** · **Inbox ↗**.

**Examples tab**: one card per example (top-level `examples`, below): **Gets**, **Does** (numbered), **When it works** (or
**Then**, in amber when the path waits for you, grey when it stops), how often it happened ("4 of 12 runs", from
the runs that took its path) and **See this example step by step →**, which opens Overview with it picked.
With none written, the tab says so and copies a request for them.

**Versions tab**: the draft (with its changes and impact review) and every version, newest first, each with its
note and its runs. A run's version chip on Past runs opens it at that version.

**Actions.** **Run ▾** has two groups, each under a coloured header: amber *For real · uses your real accounts*
and green *Test on fake data · nothing real touched*. Each choice has an icon, a name and one short line: "Latest
item" (`run workflow <name> on the latest item`), led by "Run workflow" (its trigger's first phrase: fetches new
items and runs each; only when it has a trigger), "An item you choose" (`run workflow <name> on `), "This path"
(`test workflow <name> path <the path's words>`, for the path the decisions pick, when it has a test case) and
"Every path" (`test workflow <name>`), or "Add tests first" when there are none. **Every copy on the board, on
both pages, looks the same** (`TopBar.copy` in topbar.js): the button clicked pulses green, and one toast at the
bottom says "Copied", shows the text on a single line (cut short with …, in full on hover) and fades after 4 seconds
(it stays while the pointer is on it). When the browser blocks copying, the toast shows the text selected to copy by
hand. On a trigger: "Run it now" (its first phrase),
"This trigger" (`test trigger <key>`) and "End to end" (`test <key> end to end`). **Change** copies
`change workflow <name>: ` (or `change trigger <key>: `), which the architect makes a draft; an earlier version is
put back from the Versions tab. `<name>` is the skill without `workflow-` (`security-alert`). The command shows only as the
option's tooltip and in the "Copied" line; the menus close on a click outside or Escape.

**The state bar.** When the page is in a particular state, one bar at the top says so, and the page takes a
faint stripe and a coloured left edge in the same colour: **violet** for a draft. A published workflow's draft
shows three steps, **Draft → Validate → Publish**. At Draft: the title "Draft v5", one line under it on how it
differs from v4 (`draft_summary`, written by Claude; else the last edit's note), and **Details** at the end of that
line, which opens `draft_details` grouped as Does differently, New and No longer does, each with its reason and Show
step, the plain list from `draft_changes` folded last under "Every edit" (only the plain list when there are no
details). **Validate**, the main (recommended) button, copies `validate workflow <name>`; **Publish now** beside it copies `publish workflow <name> without validating` (saved at once, no checks or review, the version marked not validated); Undo, Run it again and Discard sit in ⋯. At Validate, once
the impact review is written and something will no longer happen (a "gone" line, or a past run that will or might
end differently): "Validate v5 · Approve what will no longer happen, in the chat", that list open with Show on the
flow for each run, and what it does instead), also on an import waiting for a yes
("Draft · importing …", **Import it**) and on a new workflow; **blue** for a run or test going on now
("Running now · …" or "Testing now · …" with a pulsing dot, the step it's on, **Chat about this**, **Open in Inbox ↗** and **✕ Close**);
**grey** for a finished run or test you opened ("Viewing a run · …" / "Viewing a test · <path>", which says
whether the test did what it should). ✕ Close returns to the normal page, with no bar.

**A new workflow** (`?w=new`, from **Add a workflow** in the top bar): the title and one centred card, nothing
else. There is no text box: the user copies a start and finishes the sentence in the chat. The card asks "How do
you want to start?" with three tiles: **Simple workflow** (one sentence, `Add a workflow: When …, then …`),
**Complex workflow** (the core and the first few steps, the same `Add a workflow: ` start; test, publish, then grow
it with `Add to workflow `) and **Import skill** (`import ` then the path). The picked tile sets the template line
and what the one **Copy template** button copies. Under it, **Show simple / complex / import examples** opens
examples for the picked tile, each with **Copy**: Simple has eight one-line, enterprise-style ones (Salesforce,
HubSpot, Zendesk, Jira, NetSuite, Workday, DocuSign) as "When … [app], then … [app]"; Complex has five with a
When line and First / Then / And steps, copied as one "Add a workflow: When …, first …, then …, and …." line;
Import has four `import <path>` lines (a skill folder, a .md file, a code project, a skill from another project). There is no
When / Do split and no trigger picker: the architect splits the request (rule 30), the trigger only finding items
(source, window, item, kind) and the workflow holding every check, threshold and action. The draft shows that split;
the page doesn't explain it up front. The architect drafts the smallest version that works, to test and publish,
then grow one change at a time.

**View here** opens the run on the same page, under the grey state bar (a run still going shows in blue, and
is listed first with the status Running). The tabs step aside and the run's page reads top to bottom: **Workflow outcome** (the status, then a headline and a short list, with `**bold**` kept from the end line and each of its `facts` as a label and value: when it worked, what it found; when it's waiting, "Waiting
**The run page design** (rule 31): a slim bar ("Try
on your real data · 17 Nov, 17:05 · nothing was sent", Chat, Inbox ↗, ✕); for several items, one line saying what
they are ("This try ran on 2 property emails from your Outlook, last 24 hours", a kind chip, tabs by status) and one
thin row each (status dot, kind icon, name, route, time; problems first, 8 a page); the outcome with its status band;
decisions once, on a white card, with the route and "Not reached"; steps that start with one "How it started" row (the
hand-off line's `found`; on the workflow page, what the trigger does, opening its own steps), a "Then · workflow · version" divider, a time per step, and skipped stages folded into one
line; Run details folded to one row at the bottom.
**The workflow page design** (the same layout where it applies): the Overview is one sentence with "more" (the full
description and the details), then the examples (chips, "+N more" as cards, the picked one described: comes in · what
it does · you get); Workflow decisions shows only the questions, set by the example; the steps start with the
trigger as a step like the others ("Check the BBC front page", its tile where a stage has its number), joined to
every stage by one line, and it always opens to its own steps (get, keep, and **Hand on this <item>**, whose Data is exactly what the workflow was given), each with the same panel (on a run, the item it found
on the right; a run started by hand still opens, saying the trigger didn't run); the outcome is one sentence that opens to Makes ·
Does · Then you.
**A step's panel** (click a step): on a run, Summary · Data · Logic; on a workflow page, Logic alone with no tab bar.
Summary is any warning as one line on top (not sure, failed, waiting on you), then one sentence and a few fact chips;
Data is what went in and came out as a plain list, with "Show as JSON"; Logic is one sentence, a decision's options
with the one taken highlighted, and "Show the rule" for the skill's own words (`Steps.inspector` in `steps.js`).
on you: …" first; when it didn't work, what happened; then its buttons, each copying a line for the Claude chat:
**Copy "yes"** / **Copy "no"** when it waits on you, **Copy rerun** / **Copy for Claude** when it failed, otherwise
**Run again** / **Ask Claude** (a test or a try: Ask Claude only); then, under **Created**, each thing it
made (drafts, a hand-off, a file) with a button to open it. From the trace's end line, `done`, `waiting`, `problems`
and `notes` (`RUN-TRACE.md`), or worked out from the steps for older runs), **Workflow decisions** (the answers it gave, read-only, with what it found; questions it never
reached in one line), **Workflow steps** (only the steps it ran, with their badges and real results; **Show steps
it didn't run** brings the rest back, **Show details** each step's logic) and, last, **Additional info** (when it
ran, version, step counts, path). Its bar has three small buttons: **Chat about this** copies a request naming the run ("About run wf-… (Security alert,
11 Nov, 17:50): ") so you can ask Claude about it; **Open in Inbox ↗** opens it on the Inbox page; **✕ Close** goes back.
The list of other runs isn't shown; **✕ Close** (or the browser's Back) returns to it.
**Items from the same request.** When the request that started the run pulled in two or more items for this
workflow, a strip under the bar lists them (`sibStrip`: the run's `group`, in the order they started), one button
each with its label and the path it took; the one shown is highlighted, and an item that took another path is
marked in red, with a count in the strip's heading. A click opens that item in place (`&run=`), so its decisions,
steps and outcome are its own. On a new workflow's Ready to publish bar, **View the try (N items)** opens the
first item.

**The address follows the page**: `?w=<page>`, plus `&tab=runs|examples` or `&run=<run id>`. Moving to another
page, tab or run adds a history entry, so the browser's Back and Forward work; picking answers doesn't.

## Inbox page (`workflows.html`)

One table of every item Delegate has seen, whether it has run or not. An item is one workflow ID:
its runs (the `<wf>-a<n>` traces), the times a trigger found it again (`link_wf` steps), and its done-list rows.

- **Statuses:** Not run (done-list status `pulled`: pulled in, nothing run yet), Running, Needs you (end
  `attention: action`, or a step waiting on the user), Check this (`review`), Stopped (stalled), Done, Skipped
  (done-list status `skipped`).
- **Run time.** A finished run shows how long it took next to its outcome ("Took 43s"), and how much of that it
  spent waiting on you (from a `needs_user` step to the line after it). It is the run's end line minus its start,
  both stamped by the clock. A run whose start and end were written in the same second was logged after the fact
  and shows no time. The Builder's Runs list and its versions panel show the same.
- **Rows open in place** (▸): not run shows the saved input and the workflow it will go to; ran shows the outcome,
  flow, steps and details.
- **The page changes nothing and runs nothing.** Every button that does something copies one line for the Claude
  chat and shows it in a note; the work happens when that line is pasted there. Only moving between pages and
  opening, folding or filtering what is on screen happen on the page itself. The board server is read-only (any
  POST is refused), so there is no other way in.

  | Button | Copies |
  |---|---|
  | Run, Run again, Run N, Run selected, Start (Run triggers) | `run workflow …` / `rerun workflow wf-…` / `run these N items …` / `run workflow manager with these triggers …` |
  | Answer, Discuss | a line that opens the question about that workflow ID |
  | Skip, Skip selected, ⋯ › Skipped | `skip wf-…` (or "Skip these items" with a list) |
  | ⋯ › Done / Needs you / Not run | `mark wf-… done` / `needs you` / `not run` (or "mark these items …") |
  | ⋯ › Delete row, Delete selected | `delete wf-… from the board` (or "delete these items …") |
  | Don't add them again: Turn on / off | `turn Run each item once on` / `off` |
  | + New view, Change with Claude | the start of a request for `views.json` |

  Skip, mark, delete and the switch are the dispatcher's **Change items by hand**. Their trace steps say `"hand": true` and never count as a trigger finding the item again (`RunPath.linkOf`, one test for both pages; older traces are known by their step type): done-list lines set by hand
  (`skipped`, `marked_done`, `marked_needs`, `pulled`, `deleted`, with `"manual": true`; not attempts), and a delete
  moves the item's run traces to `.trash`, so it leaves the table and comes back as new if a trigger finds it again.
- **Run triggers** (the top bar's button) opens a floating panel: tick triggers, Start: every new item runs (there is no pulling in without running). While a
  request is open the panel follows it and can collapse to a tab on the right edge. Its **Past runs** tab lists
  each request with what it found per trigger, and **Show items**. A finished request that ran and pulled in
  nothing adds one line: **Nothing new to run. See what it did in the Builder ↗**. The link opens the
  request on its workflow's page (`workflow-viewer.html?w=<workflow>&run=<request>`), where the trigger stage shows
  what it read and why nothing carried on. Show items still opens; for such a request the view is empty and says
  "This run didn't pull anything in: <verdict>", with the same Builder link. A test request's items open in
  the Tests view.

### The Run panel

**Run** opens it. **New run** is a box you type into: a workflow or a category becomes a tag (a category tag runs all
of it; click it to take one out), suggestions show as you type (Enter adds, ↑↓ move, Enter on an empty box runs,
Backspace removes the last tag). Above the box, a three-way switch: **Last time** (what you ran last, kept per browser;
its tooltip says when and what), **Everything** (all workflows) and **Choose** (pick your own). Under the box, every
category: click one to add or remove all of it, or open it to pick single workflows. It opens with what you ran last
time. **+ Add context for this run** opens the Context box, sent with the run line. The two standing switches,
**Approve automatically** and **Run each item once**, sit behind the gear in the panel's header ("Every run"); each
copies its "turn … on|off" line for the chat. **Past runs** lists runs newest first under day headings, one short line each (workflow, what it found, status, when), with
a filter box; a run of several opens to each workflow's result; hover a run for **Run again** (back into New run) and
**Open** (its items in the Inbox).

### Views (`views.json`)

Two views are built in: **Recent** (every run, tests included, grouped by pull-in, newest first) and **Scheduled**. Every view uses the same simple list (custom views
are listed under **Custom views**; grouped any other way, each group is a heading and each item its own row; A test (a try included: a test on real data) shows in Recent tagged **Test** (hover it for where its data came from), with
Passed / Failed when it has an expected path; Scheduled starts with **Coming up**, one row per schedule). Grouped by pull-in, it sits under
Today / Yesterday / Earlier: one row per run, with **Category · Workflow**, a grey line of
what it ran on (its items), one status and the time; open it for its items, joined by tree lines; open an item for
its Workflow outcome: the same box, with the same buttons, as the Builder's (`Steps.outcome` in `steps.js`), plus
**See details** for the full run in the Builder. A run of one
item opens straight to that sentence.
A run of several items opened in the Builder lists them at the top (**N items**, with counts that filter the list),
and each step and decision says how many of them reached it. Every other view is
written by Claude into `views.json` (in-project: `dispatcher-data/views.json`; installed: the config folder; the
exact path is `views_file` in `board-data.js`). The page has no filter controls: ask in the chat, Claude edits
this file, and the page picks it up within seconds.

```json
{"views": [{"id": "security-week", "name": "Security this week",
            "asked": "the user's words, shown on hover",
            "filter": {"status": ["notrun", "needs"], "area": "Security", "workflow": "alert",
                       "trigger": "email", "since": "7d", "q": "sign-in"},
            "group": "pullin | day | trigger | workflow | status | none",
            "sort": "newest | oldest",
            "columns": ["item", "trigger", "workflow", "category", "status", "when", "added", "lastrun", "time", "trigger", "pulled", "waiting", "attempts", "id"]}]}
```

All filter keys are optional; several values are a list or a comma string. `since` is `24h`, `3d`, `7d` or a
date. The same keys work as link parameters (`workflows.html?status=notrun&group=trigger`, `cols=` for columns), and
`?view=<id>` opens a saved view.

## Workflows written as code

A `workflow-` or `shared-` skill whose `.py` files have a function marked `@flow("Name")` is drawn from its code by
`scripts/codeflow.py` (Python's `ast`: the code is read, never run) and needs no entry in `workflows.json`:
- the `@flow` function's calls to `@step("Tag", "Title")` / `@decision("Question?", options=[...])` functions are
  its steps, in order; an `if` on a decision's variable (`==`, `!=`, `in`, `else`) sets `on`, which may list
  several options (`"alt": [0, 1]`); unmarked helpers are not drawn;
- each step's Why? is the function's docstring, and **Show the code** shows the function with its line numbers;
- one example path per combination of decision options; real runs match steps by `"from": {"key": <function>}`,
  because the markers write the function's name as `key` in each trace line;
- the category is the skill name's area; an area whose folder lives under another section (e.g. `common`) gets
  a `<area>-workflows` folder under Workflows; a `shared-` skill gets its own folder under its area in Shared
  (`<area>-<id>`). A hand-written workflow with the same id wins;
- code inside a hand-written workflow's own folder (that workflow's `match.skill`) is one of its steps: it is drawn
  as a child under that workflow (`"parent"`, id `<workflow id>-<flow name>`, no runs of its own), and the step that
  runs it names it with `"sub": "<that id>"`, which shows an "Open its steps" link.

Where each skill sits on the board follows the architect's rule 22 (the board follows use). The build prints a
`WARN` line for a `shared-` skill that fewer than two skills use (workflow steps and the triggers' get steps).

## Drafts (new workflows being drafted, and imports waiting for a yes)

**A new workflow's four steps: Draft → Connect → Try → Publish.** The try reads real data once, the way the user
picks on the Try bar: **Try as a test** copies "<phrase> as a test" (the older "held back" still works; every save, write and send held back: `run_item.py
start … --try`) and **Try for real** copies "<phrase> for real" (every step runs and the items count as handled:
`--try --real`, the header and done-list line marked `try_real`); the first recording of each path it took is that path's
test, so there is no separate Test step before publishing. The Try bar has no path list: once a try has run
without taking a path (nothing came in), its text says so ("Last try 10m ago: <verdict>") and its button reads **Try
again** (`lastTryReq`); the list of paths shows from Ready to publish on. **Create it** and **Publish v1** are one call each,
`scripts/new_workflow.py create <stem>` and `publish <workflow id>`: the script writes the skill, the board entry,
the trigger entry, a colour, examples and results (and on publish the rename, category, README row and v1), ticking
the "Claude is creating it" checklist as each part really lands. After a publish the page shows the workflow as it
is, with no extra banner.

**A change to a published workflow is one file too.** `scripts/change_workflow.py open <skill>` writes its skill and
board definition as one change file; Claude edits that, and `apply <skill> --note … --summary … --details …` writes
SKILL.md, the board (each step's lane and Why? worked out again; hand-named lanes, older `from` matchers and quoted
Why? parts kept), the README row and tests on a renamed path, then the draft iteration and the build (`--check`
shows the diff first). Workflows with code steps or `## Step` sections are still edited by hand.

**Never silent.** Along the bottom of the window every page shows one live strip, docked so it never moves the page (`topbar.js`): **Claude:** what it is doing now,
for any request (`activity.json`, written by `live.py` from the hooks on every tool call; "Claude is done · waiting
for you" when the turn ends), or, in red, **The board couldn't update** with the first error while a build fails
(`build-status.json`, written by `build_status.py` from both builds; the live dot turns red too). The Builder reloads
its data every 2.5 s whatever page is open. Every copy button confirms with a toast naming exactly what was copied,
or shows the text selected to copy by hand. On the Inbox a try shows with real work, tagged **Try · nothing sent**,
and a row waiting on you shows what it is waiting for.

**A run shows the moment it starts.** A request that has found nothing yet gets a placeholder on the Inbox ("Looking
for items…" with its live "Now:" line) as soon as its header exists. Right after its trigger keeps them, the dispatcher
lists every item at once (`run_item.py queue`): each row shows **Queued** until its turn, then Running, then its
result; a row whose run stopped before reaching it shows Not run. On a new workflow's Ready to publish bar, **View the
try** opens the try on the flow ("Viewing a try": what it read, worked out and would have sent), and each tried path
has its own View link.

**A new workflow** (the architect's Create mode) is `drafts/<stem>.json` with `"draft": {"kind": "new", ...}`, shown
under **Drafts › New** as `draft-<stem>`. It is written the moment the user asks, as a stub (`"status": "drafting"`,
`"started"`, `"request"`), then as a full workflow whose steps each carry a `mark`: `new` (from the user's words),
`guess` (Claude filled it in), `moved` (a condition the user put in "when", moved from the trigger into the
workflow, with `moved_why`: one line, shown under the title next to a **MOVED** label) or `ask` (an open question: the
step's title is the question). A new trigger rides in `draft.trigger` (`name`, `new`, `small`, `will_be`, `reads`,
`noun`, `takes`, `steps`) and is drawn as the first stage, which opens with its four slots (**Source**, **Window**,
**Item**, **Kind**, rule 30; a published trigger shows the same slots from its `reads` and `takes`); an existing one goes in
`entries`. `draft.will_be` names the workflow skill it becomes. The page reads **Editing · new workflow** (or **Claude is
drafting it**, pulsing), with **Discard** (copies "discard the draft <name>") and **Publish**, greyed until nothing is
open. The new-workflow page (`?w=new`) opens the first such draft started after **Build** was pressed; once the
architect builds it and deletes the file, the page follows to the workflow named by `will_be`. The Builder reloads
the definitions every 2 s while a new draft exists or the new-workflow page is open.

**Editing a workflow.** **Edit** on a workflow page copies "change workflow <name>: " for the chat and shows the page
as Editing until the draft arrives (Cancel). A draft (`edited`) shows its changes on the steps against the last
version (`step_marks`, `removed_steps` from `skill_history.draft_marks`): NEW, CHANGED, and REMOVED steps struck
through in place; a workflow never published shows every step NEW. Every stage starts open while editing. Its bar has
**Discard** (copies "discard the draft of workflow <name>") and **Publish**.

**Updating a draft (iterations).** Each change to a draft is one iteration (`skill_history.py checkpoint <skill>
--note "…" --summary "…" --details <file>`, kept in the data folder's `iterations/` until the draft is published).
`--summary` is one line on how the whole draft differs from the published version and `--details` a JSON list
`[{kind: changed|new|gone, t, why, keys}]`, both rewritten at every change and shown as `draft_summary` and
`draft_details`; a checkpoint with no file change only updates them; Undo brings back the ones before. The architect calls `updating`
first, so the bar pulses "Claude is updating it" with what it is doing. Afterwards the bar reads "Updated · 1 step
added, 1 changed", with **Undo this change** (copies "undo the last change to workflow …": `skill_history.py undo`
puts back the iteration before, files and board definition) and **Run again on "<item>"** (the item the draft was
last run on; "Not tried since this change" when that run is older). On the steps and in the decisions, the last
change is marked JUST ADDED / JUST CHANGED / JUST REMOVED (`just_marks`, `just_removed`); a workflow never
published shows no NEW marks, since every step is new. A run on a draft records its iteration in the done list.

**Changed since the last run.** A run's page compares it with the run before it on the same item: a strip ("Changed
since the last run on this item: 3 steps"), each changed step marked CHANGED SINCE LAST RUN with what it gave
before struck through, and decisions whose answer flipped. A run on an older iteration of a draft says "The draft
has changed since this run", with Run again on this item.

**Where items come from.** A trigger made for one workflow only is drawn as that workflow's first stage, "Where
items come from": the trigger's own get and sort steps (Delegate's ID and hand-off steps are left out).
A workflow without stages then gets a second one, "What it does". A trigger shared by several workflows keeps its
own page and is not repeated.

### Imports

The architect's Import mode draws a skill or project from elsewhere before it becomes a skill. Each draft is
`drafts/<name>.json` here (`.workflow-manager-data/config/drafts/` with the plugin; `paths.py drafts`): one
workflow in the `workflows.json` shape (`short`, `name`, `desc`, `steps`, `simulated`), with no `id`, `category`
or `entries` (the build sets them: id `draft-<name>`, under **Drafts** › Imports), plus:

```json
"draft": {
  "source": "~/Downloads/refunds.md", "kind": "markdown file", "will_be": "workflow-support-refund-request",
  "needs": {"order_id": {"required": true, "example": "A-1042"}, "reason": {"required": false, "example": "damaged"}},
  "started_by": "no trigger yet: run directly",
  "changes": ["Step 5 issues the refund in Stripe"],
  "overlaps": ["Step 2 (verify the customer) is also in workflow-support-address-change"],
  "left_out": ["tests/", "a hard-coded API key in config.py"]
}
```

A step's `why` takes `label`, `sum` and `rule` (the source's own lines) written in by the architect: nothing is
quoted from a skill file, because there isn't one yet. The page shows the draft with a dashed box saying what it
starts with, what it changes and what overlaps. The architect deletes the draft once it is imported or declined.

**While Claude reads it.** Import mode first writes a stub, `{"short": "<stem>", "steps": [], "draft": {"status":
"reading", "source": "<path>", "found": {}}}`, and fills `found` as it goes: `files` and `steps` (the scan's
totals), `outside` (what it reaches outside, in plain words), then `workflows` and `triggers` (what it judged).
The page shows that draft as **Importing <name>**, in the violet draft state with a pulsing dot, the steps
Pick › **Read** › Confirm › Draft, and "What Claude has found so far", one row per item above, each ticked when
filled. The Builder reloads the definitions every 2 s while an import is being read (15 s otherwise). The full
draft then replaces the stub in the same file (no `status`), and the page turns into it, at **Confirm**.

## Tests

Tests run the real skills on fake data, with every outside call refused (core-architect rule 28, core-dispatcher
**Tests**). Say "test workflow security-alert" (every path), "… path 2", "test trigger email" or "test email end to end".

- **Fakes** per outside system in `tests/fakes/<source>.json`, found with `paths.py fake <source>`: the folder's own first, then the ones that ship with the plugin (never copied into a user's folder, so they update with the plugin): records shaped like what the trigger
  hands on, each with `_sort` (how it should be sorted) and `_case` (the workflow case it should take).
- **Cases** in each skill's `tests/`: a workflow case per path (`path`, a seed `item`, `canned` answers by step key,
  `live`, `followup_case`); a trigger case `{"source": …}` and one with `"end_to_end": true`.
- **Test mode** (`scripts/test_mode.py`, turned on by the dispatcher): the PreToolUse hook `on_test_guard.sh` refuses
  outside writes (logged as `Mocked`) and outside reads (the canned answer is used, `Fake Read`); `live: true` allows
  reads only. A test-mode file older than 3 hours is ignored.
- **Results:** the dispatcher records each case with `--test --case --expect`. A case passes when its run took the
  expected path. The Inbox's **Tests** view holds every test run (no other view shows them), one group per test
  request with "N of M passed"; each path button in the Builder shows its latest test (✓ / ✗ with the version,
  or "not tested"); the Versions tab shows how many paths passed on each version. Test runs never count as real runs.
- **The build fails** while a path has no case, a case names a path that is gone, a seed item or fake record misses a
  field, or canned answers name a step that doesn't exist.

## Versions

Every skill and its board definition has a hidden history, separate from the project's own git:
`scripts/skill_history.py`, kept in `dispatcher-data/skill-history/` in-project or
`.workflow-manager-data/history/skill-history/` where the plugin is installed.

- **History starts by itself.** The prompt hook runs `skill_history.py start` before every request: the first time, it saves the skills as they are as "History started" (each one's v1), so a folder that had skills before it had a history (a new install, or an update from an older plugin) gets a version before Claude can edit anything. After that it does nothing. Should it fail (no git), a draft still shows: History · draft, "Not published yet".
- **Draft, then publish.** Every edit is a **draft**, whoever makes it: the architect's Change mode edits, does
  a quick build so the board shows it, opens the workflow's page beside the chat and stops. Nothing saves a draft
  on its own (the Stop hook only refreshes the board); the Versions tab shows a Draft row with what it changes
  in plain words, and a run on a draft is stamped "vN+draft", so it can be tried and tested as often as you like.
  `skill_history.py status` lists the drafts.
- **Publishing: one published draft is one version.** When you say "publish workflow <name>" (or "save a version
  of workflow <name>"; the Versions tab's **Publish** button copies it), the architect runs the heavy part once:
  `skill_history.py prepare` (build, diff, the draft's changes and the earlier runs, in one call), the Checks, the
  impact review, your yes, and the save. "Change X and publish it" does both in one request.
- **Impact review.** The draft is checked against earlier runs (the latest test of each case, every unusual run,
  then ordinary runs with other outcomes): same, might change or will change, each with a reason.
  `skill_history.py pending <skill> --review FILE` keeps it with the draft, so it shows under **Versions › Draft**
  before anything is saved ("waiting for you"), each run with its reason and **Show on the flow**: look at them
  there, then say publish or keep editing. A run that changes only in the way you asked (the new address you gave)
  needs no extra yes. A later edit marks the review out of date. On save it is stored with the version and shown
  under it ("Checked against 12 earlier runs: 11 same · 1 might change").
- **Versions.** Each skill gets v1, v2, ... : a new version whenever its folder or its board definition
  changed in a save. The build adds them to each workflow as `history` (never written by hand), with the
  board changes worked out in plain words (steps added, removed, renamed, options changed, examples).
- **Runs.** `item_id.py record --status started` stores the skill's version on the ledger line (`version`),
  saving any unsaved change first, so the number is exact. The run list shows it as a chip; an older
  version is marked, and clicking it opens the history at that version.
- **Versions tab.** On each workflow page (from the version link next to the title): every version, newest first, with its note, what changed on
  the board, the files changed and how many runs used it. **Restore vN** copies "restore workflow <name>
  to vN" to paste in the chat; the architect does the restore (`skill_history.py restore`), runs the checks
  and saves it as a new version.
- **Runs on vN.** Each version with runs has a **Runs on vN** button: a side panel lists every run of that
  workflow on that version, newest first, tests included (marked Test), each with its status, the path it took
  and its outcome. **Show on the flow** draws that run on the workflow (tests too, which the run list leaves
  out); **Open in Inbox** goes to its item. Runs from before versions were stamped have no version and show on
  no version.

## After any change to a skill or to `workflows.json`

1. Make `workflows.json` match the skill (fields below).
2. Run `python3 -I .claude/workflow-ui/scripts/build_workflows.py`. It must print no `ERROR` lines
   and exit 0. It still writes the page data when there are errors, so the board stays live, but
   the change isn't done until they're gone.
3. Open `http://127.0.0.1:8765/workflow-viewer.html?w=<workflow id>`, click **every** example button,
   and check that each one shows the path it describes. Only the steps on that path should be
   visible.

## `workflows.json`

Top level: `skills` (short name and colour code per skill), `categories`, `sections`, `entries`,
`dispatcher` (the "Triggers" page), `workflows`.

### The sidebar: read from the skill names

The sidebar is built from every skill's name, `<kind>-<category>-<description>` (architect rule 10), so a new
skill lands in the right place with nothing to add here:

```
 ▾ Triggers         2   ← header = kind; Triggers and Workflows lead (large, open)
     ■ SECURITY         ← subheader = category, its colour from `categories`
     Gmail inbox    9
 ▾ Workflows        3
     ■ SECURITY
     Security alert ● 12   ← dot: the latest run needs a look
     ■ NEWS
     BBC article   11
       Headline check  part of   ← a workflow's own code, under it
 ▾ SHARED           2   ← quieter, below a divider
     ■ COMMON
     Gmail              ← a shared or core skill is a row, its modes under it
       Draft mode   –
     ■ NEWS
     BBC website        ← a skill with no steps drawn yet still shows, greyed
 ▸ CORE 🔒          2   ← faintest, folded at first: "Built in · can't be changed"
```

- Every skill in `skills` (aliases left out) shows once: a trigger inside its workflow (no row of its own), a
  `workflow-` skill as its workflows, a `shared-`/`core-` skill as a row with its workflows (modes) under it,
  and `core-dispatcher` as Delegate (`?w=disp`).
- Tabs **All · Triggers · Workflows** sit under the search. **All** shows every kind, with each Trigger and
  Workflow category folded to one line (its count, and the dot if something in it needs a look) except the one
  holding the open page; Shared and Core are folded at the bottom. **Triggers** and **Workflows** list just
  that kind with every category open. This keeps the sidebar to about one screen at 20+ workflows.
- Headers and categories fold, and the choice (and the tab) is remembered in the browser; searching opens
  everything.
- `sections`: still read by the build, no longer by the sidebar.
- `categories`: `{key: {name, tone, section}}`. A top-level category is the area, one of the words in
  the category lists (the plugin's `core-architect/categories.md` and the folder's own `.workflow-manager-data/config/categories.md`). A sub-folder sets `parent` (another
  category's key) instead of `section`, and takes its section from the parent. A sub-folder is only for a
  skill with several **modes** (e.g. a shared skill with a read and a draft mode), never for a `workflow-` skill:
  a workflow's branches are paths on its one row (the architect's rule 24; the build fails otherwise).
- `entries`: `{key: {name, icon, desc}}`, one per trigger skill (its Definition block's `id`),
  using the same key. The build replaces `name` and adds `category` from the trigger's skill name
  (`trigger-security-gmail-inbox` → "Security · Gmail inbox"), and adds its `starts on`,
  `item key` and `in run all`, so a renamed trigger needs no edit here. The icon is shown as a tag. Each entry also gets its own item under the
  workflow it feeds: it has no page or sidebar row of its own (`wfOfEntry`, `pageOf`). There is no trigger page: a trigger is
  the first stage of its workflow, so `?w=disp:<key>`, with or without `&run=`, opens that workflow's page (and the
  run on it). A request (`&run=<request>`) shows on the workflow's page with its trigger stage holding what the
  trigger read and kept, and the workflow's steps below as what each item goes through; a try or a run of one
  workflow is watched there and the page moves to each item's run as it starts. Searching a trigger's name finds its workflow. A trigger that
  feeds several workflows (or none) keeps its own page. Delegate as a whole stays at `?w=disp`.
  A trigger's board definition lives in its entry (core-architect rule 17): `when` (its line on the routing
  step, e.g. "Mentions email"), `noun` (what one item is: "alert"), `feeds` (the workflows its items go to),
  `steps` (its own get and sort steps) and `simulated` (its paths). The build puts the dispatcher's definition
  together from them (`compose_dispatcher`): one routing option per trigger, then the fixed options (`id`: rerun,
  manager, lines, hand, none; a step points at one with `"on": {"step": "d1", "alt_id": "<id>"}`), each trigger's
  steps followed by the engine's two (`<key>-ids`, `<key>-send`, the same for every trigger), and its paths with
  the routing answer filled in. So adding a trigger never edits `dispatcher`. The page shows the routing step plus
  that trigger's steps and paths, and only the requests that matched it.
- `connections` (built, never written here): one per `connection-<system>` skill, from its Definition and its
  status (`scripts/connections.py`, kept in `dispatcher-data/connections/`): system, its `methods` (connector,
  chrome, browser, api), the chosen `method`, any guided setup in progress (`setup_now`: its steps, ticked live),
  check, reads, writes, status, why, when checked, the last few checks, and `used_by`. The connections manager
  (`core-connections`) writes the status while it sets a connection up or checks it. The Connections overview is
  `?w=connections` (from the sidebar's Connections rows). Each workflow and trigger gets `uses`
  from its Definition's `uses:` (`web` is built in), shown on its **Connections** tab, each card with **Set up** ("set up connection <name>")
  and **Check** ("check connection <name>"), both done by the connections manager, with no Inbox entry.
- A workflow in the `workflows` section lists the triggers that start it in `entries`
  (e.g. `["email"]`). The topic stays the folder; the source is only a tag, because the same
  workflow can be started from several sources.

### A workflow

| Field | Meaning |
|---|---|
| `id` | Short key, used in `?w=` |
| `category`, `short` | Required. `category` is the area (or, for a skill with several modes, its mode heading); `short` is the row label, e.g. "Security alert". `short` is a few words, at most 32 characters (one sidebar line; the build warns past that), names the workflow or mode in the skill's own terms and doesn't repeat the category. The build adds `skill` (shown under the title) from `match.skill`, the sub-folder's `skill`, or the steps |
| `entries` | Trigger ids that start it (required in the `workflows` section, unless `direct`) |
| `direct` | `true` for a workflow no trigger starts: it is run directly ("run workflow …"), and needs no `entries` |
| `stages` | Over 7 steps, required: 3 to 7 `{key, title, makes, tip}` in order, each title a plain outcome of up to 6 words with no file names, code words or abbreviations; `makes` what it produces in 2 to 5 words (the right of its line); `tip` one plain sentence for its hover ⓘ (rule 23). The build adds each one's `n` (steps) and `notes` |
| `loops` | Steps that repeat for each of several items, inside one run (rule 33): `[{key, each, title, over, steps, in}]`: `each` what one item is ("story"), `title` "For each <item>", `over` `"trigger"` or the step that made the list, `steps` the keys that repeat (next to each other; whole stages only), `in` the outer loop for a loop inside a loop (one level at most). A loop with steps after it is closed by the step straight after it, marked `combines`. The Inbox shows one row per run; the run page adds each loop step up across its items (Simple) or draws the loop as a thin grey line with a picker for one item (Detail) |
| `name`, `desc`, `from` | Title, one-paragraph summary, what starts it |
| `match` | Which finished traces count as real runs: `{"skill", "label_any" \| "label_all" \| "default"}`, or `{"none": true}` for workflows that are never traced . `skill` matches any skill the run used, under today's name (old names through `skills.*.alias_of`), plus the skill its trigger handed it to |
| `steps` | In order (below) |
| `simulated` | "If…" paths (below) |

A rerun is a new attempt of an existing run, never a workflow of its own.

### A step

| Field | Meaning |
|---|---|
| `key` | Unique in the workflow |
| `starts` | A follow-up: the id of the workflow this step hands work back for, run next by the dispatcher as its own item. Drawn as its own "Next workflow" row right after the step, in the target skill's colour (its `skills` entry needs a `code`; the build fails without one); the target's page gets "Also run next after …" (built as `followup_from`, never written by hand). The build fails while a skill has a **Follow-up item** and no step with `starts` (rule 25) |
| `sk` | Skill doing it. A change of `sk` between steps draws a hand-off band; give the step that receives the work `hand` (why it was handed over) |
| `lane` | The skill section it comes from, e.g. "Step 2 · Check A" |
| `type` | `route`, `read`, `check`, `act`, `guard`, or `dec` (a decision) |
| `title` | Required, up to 6 words: what the compact view shows, e.g. "3 newest Microsoft bugs". A decision's title is its question, e.g. "Any from the last 3 days?" |
| `tag` | Optional one-word label shown before the title (Search, Draft, Show…). Without it, the type is used: Route, Read, Check, Do, Guard, Decide |
| `what` | One plain sentence; shown under the title only with **Details** on |
| `tip` | One sentence of up to 13 words for the line's hover ⓘ: what the step does, or a decision's real question, in plainer words (rule 23). Never logic or rules; like examples it never makes a draft |
| `stage` | The `key` of the stage it belongs to, when the workflow has `stages`. A stage's steps sit next to each other |
| `combines` | On the step straight after a loop: that loop's `key`. It gathers every item's result into one ("5 → 1"), listing the ones that stopped; drawn with ⇉ |
| `why` | `{file, label, sum, parts: [{section, pick}]}`: the rule quoted from `file`'s SKILL.md. `section` is a `## ` heading; `pick` lists substrings of the lines to quote (table header picks like `"| When"` and `"|---"` keep the table readable) |
| `alts` | Options shown under the step: `{when, then, k}`, with `k` one of `done`, `info`, `stop`, `ask`, `check`, `next` |
| `from` | How a real run fills this step's result (below) |
| `on` | `{"step": <decision key>, "alt": <option index>}`: this step runs only on that option of an earlier decision. Examples that took another option hide it |

### The calm layout (Builder)

The Builder draws a workflow's steps with `Steps.calm` (steps.js; the Inbox keeps `Steps.layout`), in rule 23's four
layers: each stage is one line with its `makes` on the right (in a run, what it found, or "skipped"); plain steps in a
row fold into one "N steps" line; decisions, code steps and anything failed, waiting, new or changed keep their own;
steps on one answer sit indented under a grey "if …"; a code step's own steps hide behind it. A workflow's stages start
closed; a run opens only stages that failed, wait on you or are running. Stages the chosen route doesn't reach stay as
faded lines saying when they'd run. **Simple / Detail** (remembered, shared with the Inbox's Details switch) adds under
every line its rule, its answers and where each leads, and what went in and came out; a click on one line opens its
inspector as before. Every line with a `tip` gets a faint ⓘ that shows it on hover. **Workflow decisions** use the same
lines: only decisions that change which steps run are listed (the rest under "+N"); on a workflow's page an answer opens
its options inline, each with where it leads, and redraws the steps; on a run they show the answers it gave, read-only.
The build WARNs (never stops a draft) on a stage over 7 lines open, a branch of 5+ steps inside a stage, and a missing
`makes` or `tip`.

### Drawing rules (from core-architect rules 23 and 31)

Moved here from the architect's rules: how the Builder draws a workflow and a run. The rules keep what a skill's
text must say; this is how the page shows it.

**Flat workflows (rule 23).** A workflow of 7 steps or fewer stays flat: one stage would only add a row. It is still drawn like stage lines, so short and long read the same: every step a bold numbered line, decisions and steps on one answer included, so the board counts as the skill does, with what it makes on the right from the step's own `makes` (2 to 5 words, like a stage's); a step that runs on one answer sits indented under its decision with "only if …". On a run, a step that didn't run stays as a faded line saying why. Simple and Detail draw the same lines: Detail adds one grey sentence (the step's `what`) and a row of small fact chips under each (on a run, what it found; on the workflow page, when it runs and what it gives), and a click on any line opens its Summary · Data · Logic panel, inset under it. A decision's options say what happens in plain words, never a field name on its own.

**Folds (rule 23).**
plain steps in a row (reads, checks, writes) fold into one line only when it saves room: 4 or more
in a row, or 2 or more in a stage that would show over 7 lines. Never a whole stage: opening a stage shows its
steps. A fold is named by its first and last step (“Find the top 20 firms … Score each firm · 6 steps”).
Decisions, code steps, and anything failed, waiting on you, new or changed never fold.

**The workflow page (rule 31).**

- **The Overview says what it does, then shows examples.** One sentence (its `summary`); "more" opens only the skill's name, for whoever changes it. Nothing else goes there: the examples do the explaining. Under it the examples: picking one describes it right there (comes in · what it does · you get, from the example's `gets`, `does` and `ok`) and sets the decisions below, which show only the questions. With many examples, "+N more" opens them as small cards (name, how often real runs took it, comes in → you get).
- **Examples set the decisions.** They are a quick way to set every answer, shown as chips: a few, then "+N more", which opens every example's card (what comes in, its steps, what you get). Never "+1 more" (3 chips up to 6 examples, 4 beyond; 4 or fewer all show). The chip already picked, clicked again, clears it: every route shows and each decision reads "any answer". Answers that match no example read "Custom". So: titles are chips (rule 29), and `ok` is the sentence under them.
- **A decision is one row**, the whole row clickable, its answer on the right; only the decisions that change the route are listed, the rest fold away. Each answer in its menu says where it leads ("→ stops"). Its `tip` is the real question in plainer words (rule 23).
- **Steps are calm** (rule 23): one line per stage, Simple or Detail, **Expand all** / **Collapse all**.
- **On a workflow page, the outcome is one sentence** (the example's `ok`, else its results) that opens to what the route **makes** (shown, drafted, saved), **does** (hands on, leaves untouched) and leaves **for you** (a question, a stop, drafts to send). The timeline below is for a run's page only.
- **The outcome says what happened first, then only what mattered.** One or two sentences at the top (a run's end line `summary`, else its verdict and first facts; a path's example `ok`, else its results). Then a short timeline of only the steps that mattered, in the order they ran: failed, waited on you, raised a doubt, made something (a draft, a file, a report saved), changed something outside (sent, posted, updated), handed on. The quiet steps between them are one count ("5 steps fine"); a one-line tally closes it ("1 to check · 1 changed"). An action (Copy “yes”, Copy rerun, Open draft) sits on the step it is about. Nothing else: no "then" emphasis, no grid of labels, no paragraphs. **Simple** is one line each; **Detail** adds the facts (a run's `facts`, a path's `results`) and names each step's kind.
- **The result is a band, not an alert:** a thin status row across the top of the outcome card ("✓ Done · took 1m 6s"; "! Needs you"; "✕ Failed"), green, amber or red. No coloured edge or dot: those read as warnings.
- **Every section has a thin black icon by its title** (outcome, decisions, steps, run details): quiet wayfinding, never colour.
- **A run's page reads top down, short first** (the run page design):
  - **One slim bar** says what you are looking at ("Try on your real data · 17 Nov, 17:05 · nothing was sent") with quiet Chat, Inbox and ✕ (back); no explaining sentence.
  - **Its items, when there are several, say what they are in one line** ("This try ran on 2 property emails from your Outlook, last 24 hours", from the trigger's `noun`, connection and window), with a small chip for their kind (email, message, task, page, file). Then one thin line each: status dot, kind icon, name, route in plain words, how long it took; problems first, 8 a page, tabs by status. It has to hold 20.
  - **Decisions appear once**, on a white card: the route it took in the header, "Not reached: …" as a faint last line.
  - **Steps start with how it started, on every page, as a stage like the others:** the first stage, drawn by the same code as every stage (`steps.js` stageBlock), so it cannot look or behave differently: one line with a small tile (the item's kind) where a stage has its number, at the top of the one connected line through every stage, no divider. It says what the trigger does ("Check the BBC front page", from its name), with its `summary` as the ⓘ and, when open, the grey line under it. The `summary` (`summaries`, `trigger:<key>`) is one sentence Claude writes, never filled from a pattern: it names the source as its connection does (Outlook, Gmail, the BBC News website, X), the window and what it keeps ("Keeps the property-for-sale emails from your last 24 hours of Outlook"); a workflow's own `summary` (`workflow:<id>`) is the Overview's first line, written the same way. On the right, like any step's result: on a run, the item this run is about and how long the trigger's own steps took; on the workflow page, "one run per <item>". It always opens, like a stage, to its own steps (get, keep, then **Hand on this <item>**: where the batch narrows to one item, its line naming the item and its Data exactly what the workflow was given, from the run's started line; on the workflow page "Hand on each <item>", its Logic listing the workflow's `needs`), each opening the same panel as a workflow step (on a run Summary, Data and Logic from the trigger run's trace; on the workflow page Logic). A run the trigger didn't bring in (started by hand, a recorded item) still opens, to what the trigger does, saying it didn't run this time. A workflow started by another says so ("Started when Security alert hands it an item"). Steps or stages it never reached fold into one line ("2 stages skipped: only if in Manchester · show"). The header counts stages ("5 stages for each alert"; on a run "2 of 4 stages ran · 1m 6s").
  - **Run details are folded:** a section box closed to one row (when, version); open, it adds how long it took, the route and the run ID. Nothing the headers already say.

### Branches

Any step with two or more `alts` (a decision, a route, a guard…) that is followed by more steps
**must** say which steps belong to which option:

- Steps that run on one option only get `on`.
- Steps that run whatever the answer have no `on`.
- An option that stops the flow (e.g. "Not signed in: ask and wait") gets `"ends": true`. A path or
  run that takes it shows no later steps.
- If every option runs the same following steps (e.g. a per-item sort where both kinds carry on),
  set `"continues": "all"` on the step.

Paths describe a *kind* of request ("If: you ask to rerun a run"), never one real item or ID.
Real items and IDs belong in the Runs list.

Which path a finished run took is worked out once, in `runpath.js` (which workflow a run belongs to, its
decisions, and the first path whose decisions all match). Both pages load it, so the Builder's Runs
list and the Inbox page's steps header ("took the path “…”" / "not one of the paths") always agree.
Change the matching there, never in one page.

Without this, every example shows every step and the branches look identical.

### Matching real runs (`from`)

| `from` | Fills the result from |
|---|---|
| `{"type_any": [...], "step_any": [...]}` | The first trace step whose `type` is in `type_any` (empty: any type) and whose `step` or `result` text contains one of `step_any`. When two steps of a workflow match the same type, each needs its own `step_any`. On a decision, the option taken is the one whose words all appear in that step's title, step or result (most words wins; plurals count); with none named, a two-option decision reads the step's status (`done` = option 0) |
| `"verdict"` | The run's end line. With `"taken_by": "attention"`, highlights option 0/1/2 for action/none/review |
| `"entry"` | The trigger that matched (dispatcher page only) |
| `"seen"` | A decision answered by which steps ran. Each option lists the steps that show it (`"seen": [{"type_any", "step_any"}, ...]`); the option whose steps are all in the trace and that lists the most wins, and an option with `"seen": []` is the default once the run has ended (e.g. Security alert's "Which check fits?": A, B, A + B, or else C) |
| `"branch"` | A decision whose answer is whether a step happened. Needs `"taken_by": {"type_any", "step_any", "yes", "no"}`: option 0 (shown with the `yes` text) if a matching step exists, option 1 (`no`) once the run has ended without one |

### Paths and runs on a workflow page

- **Paths** are the "If…" buttons at the top, written by hand in `simulated`. They pick which
  route through the flow is drawn, and the page opens on the first one.
- **Runs** are the list under the flow, built from real traces, newest first (10 shown, then
  "Show all"). Each row shows when it ran, which path it took (the first path whose `taken`
  equals the run's; failing that, the first whose every decision shares a branch with the run's, so a
  run that sorted alerts and other emails still took "new security alerts"; put the more specific path
  first), and the result. Pulled-in items count as new, not as done before. Clicking a row draws that run on the flow; **Open in Inbox →** goes to
  that item on the Inbox page (`workflows.html?item=<wf>`, or `?pullin=<request id>` on
  the dispatcher page).
- "Not one of the paths" on a run means no written path matches the route it took. Add a path for
  it.

### A path (`simulated`)

`{label: "If: …", res: {<step key>: "expected result"}, taken: {<decision key>: [option index]}, out: [<k>, "result"], results: [{k, t, label?}]}`.
**Examples and results** live at the top level of `workflows.json`, apart from the workflows, like `summaries`,
so writing or editing them never turns a workflow into a draft (the build copies them in for the page):

- `examples`: `{"workflow:<id>" | "trigger:<key>": [{title, path, gets, does: [..], ok: [..]}]}`, 2 to 4 usual
  journeys, most common first. `path` is one of its `simulated` labels (a trigger's come from the dispatcher's);
  `gets` is what comes in, `does` 2 or 3 short steps, `ok` what's true when it works. Plain words, no field names.
- `results`: `{"workflow:<id>" | "trigger:<key>": {"<path label>": [{k, t, label?}]}}`, the outcome box: one entry
  per thing that's true when the path ends. `k` is one of `shown`, `mail`, `next`, `file`, `inbox`, `untouched`,
  `ask`, `stop`; `t` one plain line; `label` overrides the row's label ("In your Gmail"). Put `untouched` last:
  what the run promises not to change.
Every example sets `taken` for **every** `dec` in its workflow. Steps on an option it didn't take
are hidden, so they need no `res`.

## The user's own board definitions (user layer)

Where the plugin is installed in someone's folder, their own skills can't change `workflows.json` (it belongs to the
plugin). Their board definitions live in that folder's `.workflow-manager-data/config/board/`, one file per skill, named
after it (`.workflow-manager-data/config/board/workflow-news-guardian-article.json`), with the same shapes as here: `entries` (name, icon, desc),
`categories`, and `workflows` (each with `category`, `short`, steps…). The skill folders hold only skills. The build
adds them to `workflows.json`'s and never replaces anything: a key or workflow id that already exists is an ERROR,
and so is a file whose skill no longer exists. A step's `why.file` may name a skill in either layer. (Before 0.8.0 they were in `.dispatcher/board/`, before 0.5.0 `board.json` files inside the skill folders; old ones are
still read until the user agrees to move them.)

## What the build checks

`build_workflows.py` prints `ERROR` and exits 1 when:

1. a workflow has no `category`/`short`;
2. a step with options (on the dispatcher page too) is followed by steps, more than one of its
   options carries on, and no later step has `on` for it (and no `"continues": "all"`);
3. an `on` points to a missing or later step with options, or an option that doesn't exist;
4. a path leaves out `taken` for a decision it reaches;
5. two steps match real runs by the same type without different `step_any`;
6. a quoted rule is no longer in its skill, a step has no `title` or one over 6 words, or a
   `tag` longer than one short word;
7. a category has no section (directly or through its parents), names a missing parent, or its
   parents loop;
8. a workflow in the `workflows` section has no `entries`, or names one missing from the
   top-level `entries`;
9. a top-level entry isn't the id of any trigger skill;
10. a workflow has more than 7 steps and no `stages` (code-drawn children are exempt), or its stages
    aren't 3 to 7, share a key, have a title over 6 words or with a file name, code word,
    abbreviation or JoinedName, have no steps, are split or out of order, or a step names a stage
    that isn't there;
11. a loop's steps aren't next to each other, a stage is partly inside a loop, a loop sits inside a loop inside a
    loop, or a loop with steps after it isn't closed by a `combines` step straight after it (rule 33);
12. an example names a path that isn't one of its paths or has no title, or a path's `results` entry has an
    unknown `k` or no text.

Anything it can't check, such as whether the steps match what the skill really does, is step 3
of "After any change" above.
