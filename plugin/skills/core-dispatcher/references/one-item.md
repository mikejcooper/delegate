# Front door: One workflow on one item, a rerun, several items, an answer to a waiting run, follow-up items

Part of core-dispatcher (its SKILL.md says when to read this). Names in bold are sections of SKILL.md or of the
other files in this folder.

## Run one workflow
Runs one named workflow on one item, without a trigger.
1. **Find it.** The `workflow-` skill `<name>` matches (see **What to run**). Read its `needs`.
2. **Get the item's input,** from the first of these the request gives:
   - "on the latest <thing>" (e.g. "the latest alert"): `item_id.py latest <trigger id>` for the trigger whose items it takes; use its saved input and its workflow ID.
   - a workflow ID (`wf-…`): `item_id.py lookup <wf>`; use its saved input.
   - details in the request itself: match them to the `needs` fields.
3. **Check it.** Every required field must be there. Missing ones: ask for them in one short question and wait. Extra details are kept.
4. **Give it an ID.** From a saved item: that workflow ID, as its next attempt. From the request: `check direct <workflow name>:<the required fields' values> --fingerprint`.
5. **Run it.** Record it as started, hand the input to that workflow, record how it ended.

## Rerun a workflow
Runs one earlier workflow again, whatever the Run each item once switch says (the user asked for it).
1. Take the workflow ID (`wf-` + 8 hex) from the request. None given: ask for it and wait.
2. `item_id.py lookup <wf>`. Nothing found: say so and stop.
3. Find an available skill whose description fits the saved input. None fits: say so and stop.
4. Record a new attempt as started, with `--rerun-of <wf>#<last attempt>` and the saved input, hand that saved input to the skill, and record how it ended.

## Run several items
A list of lines in one request (the board's Inbox page copies these), each "run workflow <name> on wf-…" or "rerun workflow wf-…".
1. Take the lines in order. A line that is neither: say so and move on.
2. Run each as its own level, one at a time: **Run one workflow** (its input from the workflow ID) or **Rerun a workflow**. One fails or stops to ask: note it and carry on with the rest.
3. End with one line per item: what ran and how it ended.

## Answer a waiting run
"answer wf-…: yes" or "answer wf-…: no", one line per run (the Inbox's Yes / No buttons copy these). The user
sending that line in the chat is the yes for that one run's waiting action, and nothing more.
1. `item_id.py lookup <wf>`: its last attempt must have ended `needs_user`. Not waiting (already answered, never
   asked, or a try): say so and stop for that line.
2. Read that attempt's trace (`<runs folder>/<wf>-a<n>.jsonl`): its `needs_user` step's `ask` and `io.out` are the
   action and everything it needs. Anything missing there: say so and stop for that line; never rebuild the
   message from scratch.
3. Record a new attempt as started with `--rerun-of <wf>#<n>`, the same input, the same label (the board tags it Answered)
   and `--found "You answered <yes|no> on the Inbox"`. Log the answer as its first step: `{"type":"Asked You",
   "step":"<the waiting step's title>","status":"done","result":"You said <yes|no> on the Inbox"}`.
4. **Yes:** hand the workflow the waiting step's `io.out` and run only the steps after the waiting one (the send
   itself, through its connection), logging each as usual; earlier steps are not run again. **No:** do nothing
   more. End the attempt with how it went and `--path` the path it took.
5. Several lines: one at a time, one line each at the end (what was sent, or not).

## Recording one item at a time
**Recording.** Every attempt goes through `run_item.py` (next to `paths.py`), which writes the done-list line, the trace lines with real timestamps and the board rebuild in one call each: `run_item.py start <request ID> --wf <wf> --attempt <n> --entry <entry> --item <item key> --label "<short name>" --skill <workflow skill> --input '<the details handed over, as JSON>' --found "<one plain line>"` before handing it off (prints the run ID, `<wf>-a<n>`; `--label` is the item's own name, never a time or the kind of run (RUN-TRACE.md, Run names); `--found` is what the trigger found for this item, written for a person: who sent it or where it came from, and what it is about, e.g. "Found a Savills email about a Stratford bid deadline", never the trigger's name; the run page shows it as the first row of the steps); `run_item.py line <run ID> '<step JSON>'` for each step the moment it finishes, never saved up and written together at the end (the board times each step, and the whole run, from these lines: a run whose lines all land in the same second shows no times on its page or the Inbox); `run_item.py end <run ID> --status done|review|action|needs_user '<end JSON>' --path "<the path it took>"` when it finishes. The input holds only the short details handed over: no full emails, passwords or personal ID numbers. (`item_id.py record` stays for skipped and by-hand lines.)

**Skipped lines** are not attempts, so they take no `--attempt` or `--trace`: `record <wf> --status skipped --run <run ID> --entry <entry> --item <item key> --label "<short name>" --skill <the workflow that fits>`. Every item a trigger keeps either runs or is linked: there is no pulling in without running (`pulled` lines from older runs still show as Not run, and run when a trigger finds them again). Lines set by hand (**Change items by hand**: `marked_done`, `marked_needs`, `deleted`, and `pulled` / `skipped` with `"manual": true`) are not attempts either.

**Follow-up items.** A workflow's report can hand back follow-up items: work to run next, with its details. After recording how that workflow ended, take each one, one at a time:

| When | Do |
|---|---|
| it is itself a follow-up | List it, don't run it (no chains). |
| the workflow ran as a test | Run it in test mode too (**Tests**, step 3) with the target's case that the source case names in `followup_case`; none named: list it, don't run it. |
| anything else | `check followup <the parent's wf>:<what the follow-up is, in two or three words>`; find the available workflow whose `needs` and description fit its details (none fits: say so and move on); `run`: check every required field is there (missing: note it and move on), then record and run it like any item, with `--entry followup` and `--item` the key from `check`; `link`: name the run it links to. |

The key comes from the parent's workflow ID, so rerunning the same alert never runs its follow-up twice while **Run each item once** is on. A follow-up gets its own run trace and row, not the parent's.
