# Front door: Tests, a new workflow's tries, and recordings

Part of core-dispatcher (its SKILL.md says when to read this). Names in bold are sections of SKILL.md or of the
other files in this folder.

## A new workflow's runs
A workflow (or trigger) still in the reserved category `new` (not published yet) runs only as a **try**: every run
of it, by its trigger's phrase or "test workflow <name> on real data", reads real data (**Tests**, its sources), and
its recordings become its tests. A try runs one of two ways, the user's choice each time:

| Way | Asked as | What runs | Counts as handled? |
|---|---|---|---|
| **As a test** | "<its phrase> as a test" (or the older "held back"), the board's **Try as a test** | every read for real; every save, write, create and send is held back: logged as "would …" (Mocked), test mode on `--live` | no: the first real run after publishing runs the same items again |
| **For real** | "<its phrase> for real", the board's **Try for real** | every step for real, saves, writes, creates and sends included; test mode stays off; a "Send it?" step follows **Approvals** like any real run | yes, like any real run: items it handled are linked afterwards, never done twice |

**Which way.** The request says it ("for real" / "as a test", or the older "held back", or the board's button copied it): run that way, no
question. Otherwise, before the trigger's get, ask with the question tool "How should this try run?", two options in
this order: **Run it for real** ("every step runs: <what it saves, writes, creates or sends, from the workflow's
write and send steps, in a few words>") and **Run it as a test** ("reads your real data; saves, writes and sends
nothing, and shows you what it would have done"). A sample (**Tests**, its sources) always runs as a test: it is not
a real item. A try for real passes `--real` with every `--try` (`run_item.py batch`, `queue`, `start`), so its runs
are tagged as tries for real, count as handled and get their review like a real run (**After each run**). Its
trigger keeps nothing: the try can't finish its Try step yet, so ask how (**Nothing to test on**).

**The try must reach the main path.** The workflow's **main path** is the path of its first example (its most
common journey: on the board, the workflow's first `examples` entry). Once the trigger's items have run, compare the
paths they took with it. When none took the main path (e.g. every post stopped at "Talks about Claude?"), the try
hasn't tried the workflow's real work yet: say so in one line ("none of the 3 posts was about Claude, so the release
check never ran") and, before the question below, ask with the question tool how to reach it:

| Option | Then |
|---|---|
| A sample that takes the main path (Recommended) | **Tests**' sample source, for that path, in the same request: its item from the workflow's examples or a real public one that fits, every step after the item's own read run for real |
| An item you name | the user gives one (its link, ID or pasted text); run it as that source |
| Look further back | real data again, 7 days (then 30) |
| Leave it for now | go on to the question below; the main path stays a gap |

Its run is one more item of the same try, so the Builder shows it beside the others.

**When a try ends,** the Builder stays on it (the same for a test or a run of one named workflow), on its "Viewing a try" page: the run as a whole. For a workflow
with a loop (rule 33, most new ones) that is its batch run (`workflow-viewer.html?w=<workflow id>&run=<the batch run
ID run_item.py batch gave>`), which shows the workflow's steps with the items in its loop; never one item's run. For
a workflow that runs once per item, the first item's run (`?w=<workflow id>&run=<wf>-a<n>`). When no item ran, the request on the same workflow page (`?w=<workflow id>&run=<request ID>`), its trigger stage showing what it read. Don't move it to
another page. Then, in the chat, say in a line or two what each item did and would have sent, and ask with the
question tool whether the steps did what the user wanted:

| Option | Then |
|---|---|
| Looks right (Recommended when the main path was tried) | it is ready to publish: an available skill whose description fits publishing a workflow names and publishes it |
| Change something | the user says what; the change is made to the draft (by the skill that guards skill changes), then try again |
| Try it on something else (Recommended when the main path still has no try) | **Nothing to test on**'s options: another source for the same try |

List the recommended one first. Say in the question which paths were tried and which weren't.

A scheduled run never asks (a try never runs on a schedule).

## Recordings
Every real run keeps what it read, so tests replay real data and never made-up data (rule 28 in the architect's
rules). `run_item.py end … --path "<the path it took>"` saves it after a real run or a try (never a test replay).
After a trigger's get and sort: `recording.py trigger <trigger skill> --run <run ID> --items '<the items that carried
on: only their handed-on fields, with their item key>' --others <how many stopped>`. The first recording of a path
becomes its test; only the newest few per path are kept.

## Tests
A test runs the real skills in test mode, on one **source**, and never counts as handled, so real items still run.
Recorded runs are the default; the others give a workflow something to run on when nothing has been recorded yet.

| Source | What goes in | Test mode | Recorded? |
|---|---|---|---|
| **recorded runs** (default) | each test case's recording (steps 1 to 6 below) | on: every outside call refused | never: it replays one |
| **real data** | the workflow's own trigger, its window (or "last 7 days" / "last 30 days": it reads "since" that time, like a scheduled run), each item it keeps | live: reads real, every send held back; a try for real: off, every step runs (**A new workflow's runs**) | yes, as a try (`--try`; for real `--try --real`) |
| **an item you name** | that one item: by its ID or link, through its connection's one-item read when it has one; or the text you paste, matched to the `needs` fields (a required field missing: ask for it) | live, or on for pasted text | yes, as a try (`--try`) |
| **a sample** | a sample item for the path asked for (or the most common path): built from the workflow's own examples (its `needs` examples, or one path's values from its board `simulated`); where the item stands for something public that the steps look up (an address, a listing, a company, an article), a real one found on the public web that fits that path, saying where it came from | live: every step that can run for real does; only a read of the item itself from the user's own account (the email, the message) uses the sample's values; every send held back | yes, marked sample (`--try --sample`); a real recording of the same path later takes over its test |

Real data, an item or a sample: write the request's trigger line (`entry_match` the trigger for real data, null with
the source in `why` otherwise), give each item its ID (real data: `check <trigger id> <item key>`; an item:
`check direct <workflow>:<its ID or first line> --fingerprint`; a sample: `check direct sample:<workflow>:<path or
default> --fingerprint`), run it like any item with `run_item.py start … --try` (a sample adds `--sample`), and end
it with `--path` so its recording is kept (**Recordings**). Test mode stays on for the whole request: `test_mode.py on
--run <run ID> --case <workflow skill>/<source> [--live]` (`--live` for real data, a named item and a sample), off at
the end.

**Running a sample: simulate as little as possible.** The sample is only the item; its steps are the real ones.

| A step that | Runs as |
|---|---|
| reads the public web or a read-only lookup (a search, a public page, a public register) | real, live |
| reads the item itself from the user's own account (the email by its ID, the message) | the sample's own values, logged as Fake Read, saying the item is a sample |
| needs something the sample can't give (a real account record, an attachment) | a canned answer from the path's board values, logged as Fake Read, saying why it couldn't run |
| would change the outside world (send, post, save, draft) | never done: logged as Mocked, saying what would have happened |

The path is whatever the real steps find. When it isn't the path asked for, end on it and say so in the report
(e.g. "asked for 'listed'; the real search found no listing, so it took 'not listed'"); never steer a step to reach
a path. An item made up for a path (no public one fits) says so in its label and its first step.

**Nothing to test on.** Real data whose trigger keeps nothing, or recorded runs when the workflow has no cases: end
that part of the request and ask with the question tool how to go on, the first one marked "(Recommended)":

| Option | Offered when |
|---|---|
| Look further back: 7 days (after 7 days found nothing: 30 days) | real data found nothing in its window |
| An item you name (its ID, link or pasted text) | always |
| A sample from the workflow's examples | always |
| Leave it for now | always; a new workflow can still publish without a try |

Run the one picked in the same request, as its source above. A scheduled run never asks: it reports nothing found.

On **recorded runs**: Test cases sit in each skill's `tests/` folder; each fake source (a fake inbox, a fake front page) is the file `paths.py fake <source>` prints: this folder's own if it has one, else the one that ships with the plugin.

| Test | Cases |
|---|---|
| a workflow | every `<workflow>/tests/*.json`; "path <N>" or a path's words: only the case whose `path` is that path on the board |
| a trigger | its `tests/*.json` whose `end_to_end` isn't true: the trigger on the fake source the case names |
| end to end | the trigger's case with `end_to_end: true`: the fake source through the trigger, then each record that carries on through its workflow, using the workflow case its `_case` names |

No cases: **Nothing to test on**; never fall back to another source without asking.

1. **Say it is a test,** and which cases will run. Every test, try and run of one named workflow is watched on the
   Builder (the address the hooks give: RUN-TRACE.md, Start), never the Inbox, and the Builder stays on its last run
   when it ends.
2. **Test mode on:** `python3 -I <paths.py folder>/test_mode.py on --run <run ID> --case <skill>/<case>` (add `--live` only for a case with `live: true`). While it is on, a hook refuses every outside read and write. Turn it on again for each case.
3. **Each workflow case:** `check direct test:<skill>:<case> --fingerprint`, record it started with `--test --case <skill>/<case> --expect "<its path>"`, and hand the workflow its item: a case with `recording` replays `<skill>/tests/recordings/<recording>.json` (its `item`; its `reads` are the canned answers, by step title), an older case uses its own `item` and `canned`. Note: *"TEST MODE. Canned answers by step: <the answers>. Use a canned answer instead of reading from outside, logged as type Fake Read. A step that would change the outside world isn't done: log it as type Mocked, saying what would have happened. Both also get "as": the type the real step would have had. A refused call is expected: don't retry it."* Record how it ended with `--test`; follow-ups as in **Follow-up items**.
4. **A trigger case:** invoke the trigger skill with this note: *"TEST MODE. The source returned these records: <the fake source's records, without the fields starting with _>"*. Its get step uses them (logged as Fake Read) and its sort runs as usual. Compare what carried on with each record's `_sort`. A trigger-only test records each record that carried on as `pulled` with `--test --case <trigger>/<case> --expect "<its _sort>" --result pass` (or `fail` when its `_sort` says it should have stopped); records that should have carried on but stopped are named in the request's end line. End to end: give each record that carried on its ID as usual (`check <trigger id> <record id>`, recorded with `--test`), then run step 3 with the case its `_case` names.
5. **Test mode off,** always, even when a case failed or stopped: `test_mode.py off`.
   A **test item asked for by its workflow ID** ("run workflow … on wf-…" for an item a test pulled in, e.g. copied from the Inbox's Tests view) is never run for real: its done-list lines say `test` (read them from the done list; `lookup` skips test lines), so run it as step 3 in test mode, with the workflow case its fake record's `_case` names. No `_case`: say so and don't run it.
6. **Report** one line per case: expected path, the path it took (pass / fail), and what was mocked. A test is never counted as handled, so real items still run.
