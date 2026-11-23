# Template: a trigger (retired in 0.12.0)

A trigger is no longer a skill of its own: it lives inside the workflow it starts, as the first lines of its
`## Definition` (`trigger`, `starts on`, `in run all`, `reads`, `item key`, `takes`) and a `## Trigger` section
that gets and keeps the items. See `workflow-template.md` (next to this file) and rule 17.

A `trigger-` skill from before 0.12.0 still runs. When it or the workflow it feeds next changes, fold it in: copy its
id, phrases, item key and window into the workflow's Definition, its sort into `takes` and `## Trigger`, delete the
trigger skill, and keep its id so its items keep their workflow IDs (rule 13).
