# 0.10.0: one Definition block per skill, and five ways to run

You can now run everything ("run workflow manager"), one trigger ("run trigger guardian", or its own phrase),
one workflow on one item ("run workflow security-alert on the latest alert"), a test of a workflow on its
example item ("test workflow bbc-article"), or an earlier item again ("rerun workflow wf-…").

Each skill now keeps everything structured about it in one `## Definition` block: a trigger's id, phrases,
"in run all", item key and the fields each item has; a workflow's `needs` (the work item it takes, with examples).

- **Machine data:** nothing changes.
- **Your own files (on your yes):** your triggers' `## Trigger` tables become `## Definition` blocks (same id,
  phrases and item key, in "run all"). The fields each item has can't be worked out automatically: the architect
  adds them, and a `needs` block to your workflows, the next time it changes them. Until then they work as before.
