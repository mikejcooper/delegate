# Front door: Running several triggers, a scheduled run, or a run with context

Part of core-dispatcher (its SKILL.md says when to read this). Names in bold are sections of SKILL.md or of the
other files in this folder.

## Run your triggers
Runs the triggers you pick, one after another, in this one request. Only triggers whose Definition says `in run all: yes` are offered: every workflow's own trigger, and any older trigger skill.
1. **List them.** None: say so and stop.
2. **Pick which to run.**

   | When | Runs |
   |---|---|
   | the request names the triggers ("with these triggers: email, news") | those, no question |
   | "run all triggers", or only one trigger is listed | all of them, no question |
   | nobody is there to answer (a scheduled or background run) | all of them, no question |
   | anything else ("run workflow manager") | the ones ticked in the tick boxes below |

   **Tick boxes:** ask with the question tool (AskUserQuestion), `multiSelect: true`: "Which triggers should run?", one option per trigger, labelled `<Category> · <description>` from its skill name (`trigger-support-salesforce-task` → "Support · Salesforce task") and described by its first `starts on` phrase. A question holds 4 options: more than 4 triggers, one question per category (4 questions at most); more than that, or no question tool, list them in chat and ask which. Wait for the answer. Nothing ticked: say nothing ran and stop.
3. For each picked trigger, run **Run a trigger** below (steps 1 to 4), then go on to the next. One fails or finds nothing: note it and carry on with the rest.
4. End with one line per trigger: how many items it found, ran, linked, or why it stopped.

## Scheduled runs
A request that ends "(scheduled: <when>)" was started by the app's scheduled task for that trigger, and nobody is
watching it. It is **Run your triggers** with the named trigger, with three differences:
1. **Its window.** Before the trigger's get: `python3 -I <paths.py folder>/schedules.py window <trigger id>`. Log its
   `line` to the request trace (`run_item.py line`), so the Inbox shows it as scheduled (and as late when it is).
   The trigger reads from its `since` instead of its usual window ("since <since>" in place of "the last 24 hours"),
   so a run that was due while the app was closed still finds everything that came in.
2. **No questions.** Nothing waits for an answer in the chat: a step that needs a yes is answered by the
   **Approve automatically** switch, as in every run (**Approvals**). A connection that needs setup ends the request with `next` "set up connection <name>".
3. **A test or try never runs on a schedule:** a trigger still in category `new` is skipped, saying so.

## Context
A run request can end with "Context: <text>" (the board's Run panel adds it when the user types something there).
Take it off before matching the request, write it to the request trace as one step (`{"type":"Context Added",
"step":"Your context","result":"<the text, cut to a line>","status":"done"}`), and hand it to every workflow the
request runs, with each item's details, as the extra field `context`: the user's own words about this run, which
the workflow's steps follow where they fit (who to write to, what to look for, what to leave out). It never makes a
step do what its skill doesn't (no new recipients beyond what a step already writes to, no skipped checks); a
line that asks for that is noted in the report and not followed. It goes in `--input` with the item's fields.
