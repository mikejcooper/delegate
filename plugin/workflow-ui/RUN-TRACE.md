# Run trace

The rules every dispatcher run follows. The hooks point here at the start of each run and give this project's
paths: the **requests folder** (the request trace), the **runs folder** (one trace per item run; in a project's own
`.claude/` this is the same folder), the **screenshots folder**, the **rebuild command** and the **board URL**. Use those
wherever these rules name them (in a project's own `.claude/` they are `.claude/workflow-ui/traces/`,
`.claude/workflow-ui/shots/`, `python3 -I .claude/workflow-ui/scripts/build_board.py` and port 8765; installed as a plugin
they are under the project's `.delegate-data/history/` with its own port, and in the plugin's source repo the
same, on port 8765).

Only dispatcher runs get a trace, shown on the trace board: requests that invoke `core-dispatcher`, such as "run dispatcher", "check my emails" or "rerun workflow wf-…". The skills it hands work to log into that same run. Any other request, including using another skill directly or working on the board or the skills, gets no trace and no board.

## Start
1. First message of a dispatcher request, before invoking the dispatcher, all in one message:
   - the request trace: never create it yourself. The hooks create it with its header (`kind`, `skip_done` included) when the request is sent, or, when they didn't recognise the request (a reply such as "Try it now"), the moment you invoke `core-dispatcher`; either way they tell you its run ID in context. Use that ID and don't create another trace or rewrite the header. Call the dispatcher with the user's words or the trigger's phrase only, never notes of your own (run IDs, "a try of …"): its arguments become the request the Inbox shows;
   - make the board visible: if a board tab exists, front it (`tabs_select`); otherwise open it with `preview_start` and the name `workflow-ui` (the hooks keep that entry in `.claude/launch.json` and, in the Claude app, leave the server to the app, so it owns the tab and can reopen it), then `navigate` that tab to the board URL; no `preview_start` tool: `navigate` to the board URL (this opens the pane). **A run of one workflow** (a try of a workflow not published yet, a test, or "run workflow …" / "rerun workflow …": the hooks say so and give its Builder address): show the **Builder** instead, by navigating the board tab to that address (`workflow-viewer.html?w=<workflow id>&run=<run ID>`: the workflow's own page; there is no trigger page). Its first stage, the trigger, shows the trigger's steps as they are logged, and the page moves to each item's run as it starts, so the user watches the steps themselves; the Inbox lists it too. Stay on the Builder for the whole run and after it ends: never navigate the board tab to the Inbox during such a run, and when it ends leave the Builder on the run it ended on (the first item's run, `?w=<workflow id>&run=<wf>-a<n>`, is fine to open). Then, in the same message, **always** call `show_pane` with `pane: "preview"` (load it first with ToolSearch `select:mcp__ccd_view__show_pane` if it is deferred). `navigate` and `tabs_select` load the page but leave a hidden pane hidden, and their results don't say so, so never skip this.
   **Which page** (the hooks say it, with the address): the run is watched where its line was copied on the board.
   Copied on a workflow's Builder page: that page. Copied on the Inbox (its Run panel, a row's buttons): the Inbox.
   Copied from the welcome (the first run): the Inbox, where its row opens by itself and offers **View in Builder**.
   Typed in the chat: one workflow's trigger phrase, or a run, rerun, test or try of one workflow, is watched on that
   workflow's Builder page; several workflows ("run workflow manager") on the Inbox.
2. The board has two pages and uses these names. **Inbox** (`workflows.html`, the board URL) is what happened: each **request** (one time the dispatcher was fired: the request trace, `"kind":"trigger"` in its header) is a group, newest first, holding the **items** it pulled in and the **runs** each one got (one item through one workflow: a `<wf>-a<n>` trace, with **attempts** for reruns). A request shows from the moment its header exists, with a **Now:** line the hooks keep updated while the run is open. A request that ran no item (its trigger kept nothing, or every item was already handled) is still a run of its workflow: its own **Nothing new** row on the Inbox and in the workflow's Past runs, its outcome the request's end line, while an already-handled item stays with the run that handled it. **Builder** (`workflow-viewer.html`; called the Workflow Viewer before) is what can happen: each **workflow** is a kind of run, defined in `workflows.json` with rule text quoted from the skills, and shown with its real runs as examples. Every workflow has a **category** and a **short name** (e.g. "Security" and "Security alert"); a new workflow needs both, and one workflow skill is one row (the architect's rule 24). Triggers show by their description (`trigger-security-gmail-inbox` → "Gmail inbox"). A rerun is a new attempt of an existing run, not a workflow of its own.
3. Invoke `core-dispatcher` and append the trigger line (which trigger skill matched).
4. The board stays the active tab for the whole run, on the page step 1 chose (the Builder for a run of one workflow). Open other pages (e.g. Gmail) in a background tab and work them there by `tabId` (clicks, typing, `find`, screenshots all work without fronting). Never `tabs_select` another tab; if one ever comes to the front, front the board again straight away.

If the board can't be opened, say so in one line and carry on.

## Logging
Every line goes through `run_item.py` (the scripts folder: `start`, `line`, `end`, `batch`, `queue`), with real
timestamps, one step at a time as it finishes, never ahead and never rewritten; the end line goes last. Write in plain
words: a step's `result` says what was found, in a line a person would use. No passwords, tokens, personal ID numbers
or full email bodies. Every field a line can have, and how to write each one: `RUN-TRACE-lines.md` next to this file
(read it before writing lines, once per chat).

## End of a run in the chat
Every run ends the same way in the chat, whatever the workflow, so anyone can read it at a glance:
1. **Its card.** Once a run has ended, print `python3 -I <scripts folder>/run_card.py <run ID>` word for word: its status
   and time, the run's `summary`, a few rows (Made, Sent, its items for a loop workflow, Waiting on you, What went
   wrong, Check) and a link to the run on the board. The card is drawn from the trace (the same record as the board's
   outcome), so write the end line's `summary`, `made` and `waiting` well and the card is right. Several runs in one
   request: one card each, then one closing line ("3 runs: 2 done, 1 needs you").
2. **Around it, keep it short.** Say what is going on while the run works, in a line at a time; after the card, add
   only what the card can't say (a question to answer, something to decide). Never retell the card.
3. **The check.** The run's review reports back one line (`run_card.py <run ID> --check`): pass it on word for word,
   on its own, as the card's update. Never turn it into a paragraph.
Any other agent a run starts reports back the same way: one fixed, short line, with its detail on the board.

## Run review
After a real run ends, the dispatcher runs the script check (`review_gate.py`). A clean run that only read things and
made something on this computer is reviewed by that check alone. Otherwise (drift from its path, a step that failed
or waited, something changed outside, an earlier try that already wrote something) the same session reviews it
straight after, following the run reviewer's skill (`core-run-reviewer`, "Review a run"). It checks
the finished run followed its workflow's path: every step on the path done, in order, nothing from another path,
each connection reached by its set method, each write confirmed, and the path named as the workflow names it
(`path_check.py` gives it the mechanical facts). It also checks what the run left behind: a page, message or draft
that an earlier try of the same item had already made (a run deleted from the board included), so there are now
two. For each problem it saves a warning
(`suggestions.py`), shown on the run's outcome, on its **Warnings** tab in the Builder, and as a small ⚠ on the
run's Inbox row. It never changes the run's status: a Done run stays Done. So the check can see what happened: pass `--path`
exactly as the workflow names it, log `via` on connection steps, and list what you knowingly did differently
under `deviations`.

## Run names
Every run's `label` (its header, `run_item.py start --label`, `queue`'s `label`) is the name every list shows for it: the
Inbox, a workflow's Past runs and the run's own page. One naming system, so they all read the same:
- **Name the item, in the source's own words:** the headline, the address, the business, or who sent it and what about
  ("2-bed flat, Mill Lane, Leeds", "Invoice to approve · Acme Supplies Ltd"). Up to about 6 words.
- **An item with no name of its own** (a status page is the same page every time) is named after what was found:
  "All systems operational", "Partial outage: API slow".
- **Never inside the name:** a date or time (the lists show how long ago, the run's page the exact time), the
  workflow's name, the kind of run ("Test:", "Sample:", "Try:"; tests and samples are tagged from their own flags) or
  attempt notes ("answered yes"; an answer is tagged from `--rerun-of`).
The board takes older labels apart the same way (runpath.js `runName`), so earlier runs read the same.

## Attention
If a step is `needs_user` or `failed` and the board isn't visible, also tell the user in chat.

A problem a run or its review found (a second copy, a note, a warning) lives on the board: the run's outcome and
its Warnings tab. In the chat, name it in one line and point to the board; never put it to the user as a question
or buttons in the chat ("Delete the duplicate?"). Acting on it is the user's call, from the board or in their own
words. Delete a run ("delete wf-…") only when the user asks to remove it.
