---
name: core-renamer
description: Renamer of Delegate. Renames the user's own workflows (their name and the category they sit in), connections (their name, and their id when two accounts of one system need telling apart) and categories, one at a time or many at once — a whole category moved or renamed, a word swapped across every name, or tidier names Claude suggests for everything — and changes each name everywhere it is written, keeping the old one as an alias so earlier runs, tests and versions still show. Shows the old → new list first and renames on one yes. Never changes what a workflow does. Use when the user says "delegate rename workflow|connection|category …: <new name>", "delegate move workflow …: <category>", "delegate tidy names", asks to rename many at once ("move everything in <category> to …", "rename every … to …"), uses the older "rename … to …", or picks Rename on the board.
---

# Renamer

## In plain words
I change names. Tell me the new name for a workflow, a connection or
a category, or ask me to rename lots at once, and I show you the old
and new names side by side. Say yes and I change each one everywhere
it's written. Your runs and tests stay where they are.

## How it works
```
 "rename …" / "move … to …" / "tidy up the names" / Rename on the board
                          |
                     which kind?
                          |
   +---------+---------+--+------+-----------+
   |         |         |         |           |
  one      one       a whole   a word in   Claude
 workflow connection category  the names   suggests
   |         |         |         |           |
   +---------+---------+---------+-----------+
                          |
              rename.py <kind> ... : the plan
              (old -> new, and what blocks any)
                          |
              show the list, ask once
                    |            |
                   yes           no
                    |            |
              rename.py apply   stop, nothing changed
                    |
              build, one version per renamed skill
              (a skill with a draft: renamed, kept as a draft)
                    |
                  report
```

## Definition
```yaml
needs:
  what: required · "workflow BBC morning digest", "connection wework", "category property", "every name with alert"
  to: optional · a new name, a category, or a word to put in; not given for "tidy up the names"
gives: the renamed items, old -> new, and which were saved as versions and which stay drafts
```

## What it renames
| You ask for | Plan with | What changes |
|---|---|---|
| A workflow's name ("rename workflow BBC morning digest to BBC daily digest") | `rename.py workflow <name> --name "<new>"` | its name on the board, its skill name (`workflow-<category>-<new name>`), its heading |
| A workflow's category ("move workflow … to finance") | `rename.py workflow <name> --category <cat>` | its category and skill name; a category that doesn't exist yet is added to the folder's list |
| Both at once | both options | both |
| A connection's name ("rename connection gmail to Gmail (personal)") | `rename.py connection <name> --name "<label>"` | the name the board and the chat show; nothing else |
| A connection's id (a second account of the same system: "gmail" → "gmailwork") | add `--id <new id>` | its skill, its saved status, and every workflow's `uses:` line that names it |
| A whole category ("move everything in property to real estate", "rename category property to realestate") | `rename.py category <cat> --to <cat2> [--label "Real estate"] [--meaning "…"]` | every workflow of yours in it moves; the folder's own category row is renamed, or dropped when merged into one that exists |
| A word across names ("rename every 'alert' to 'watch'") | `rename.py pattern "<find>" "<replace>" [--category <cat>]` | every workflow name containing the word (any case), and its skill name |
| Tidier names for everything ("tidy up the names", "suggest better names") | write the list, then `rename.py list <file>` | what you agree to |

`<name>` is a workflow's name on the board, its skill name or its id; a connection's id or name. All scripts are in
`<paths.py folder>` (next to `paths.py`).

## Steps
**Step 1: Work out the plan.** Pick the row above from the request; say nothing and ask nothing when it is clear.
Something missing (a new name with no item, "rename the Gmail one" with two Gmail connections): ask for that one
thing in a line and wait. For **Claude suggests**, read every workflow and connection of the user's (the board's
names, `paths.py` `categories`), and propose a name only where one is unclear, inconsistent with its neighbours or
breaks rule 10 (core-architect `rules.md`): short, plain, the kind of item first ("Revolut approval alert", never
"Alert for Revolut"), one style per category. Write them to a file in the scratchpad as `[{"workflow": "<name>",
"name": "<new>", "category"?: "<cat>"}, {"connection": "<id>", "name": "<label>"}]`. Then run the plan command. It
changes nothing.

**Step 2: Show it and ask once.** Open the board on the first renamed item's page in the browser pane
(`workflow-viewer.html?w=<its id>`, a connection `?w=connections`), bring that tab to the front and show the pane.
Then the list in the chat, one line each, exactly as the plan's `items` gives them; under it, in a line each: any
item `blocked` and why (a workflow still in `new` is named when it is published; the plugin's own skills aren't
renamed from a folder that only has it installed); the items in `drafts` ("has changes not published yet: renamed
now, saved when you publish them"); and a scheduled workflow among them ("its schedule is set again with the new
name"). Then ask with the question tool: "Rename these" or "Change the list". A single rename the user spelled out
in full ("rename workflow X to Y") is the yes: no question, go to step 3. Nothing ready: say why and stop.

**Step 3: Rename.** `rename.py apply`. It renames, builds the board and saves one version per renamed skill
("Renamed: …"); it never saves a skill that has a draft. For each workflow in `schedules_to_update`, set its schedule
again with its new name (core-architect, **Common requests**: Schedule a workflow), so the scheduled task runs the
new name. `errors`: fix what the rename caused (an old name still written somewhere: put the new one in, build
again); anything else, say it.

**Step 4: Show it.** Reload the board on the renamed item's page (its id hasn't changed) and bring it to the front.

## Report
One line per rename, old → new, then in a line each: what was saved as a version, what stays a draft until it is
published, what was skipped and why. Never list files. Old names keep working: "earlier runs still show under the
new name".

## Rules
- Only names change: never a step, a trigger phrase, a test, a run or what a workflow does. Trigger phrases ("check
  my email") stay as they are; to change one, it's a change to the workflow (core-architect).
- A workflow keeps its id, so its runs, done list, tests and links stay as they are. Old skill names stay as
  aliases on the board.
- A workflow still in the category `new` is named when it is published, not here. Never rename the plugin's own
  skills from a folder that only has it installed, and never a `core-` skill.
- Category words follow rule 10: one lowercase word. A label ("Real estate") can have spaces.
- One yes covers the whole list shown; anything added after it is asked again.
