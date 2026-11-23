# 0.7.0: entry points become triggers

The skills that start work are now called triggers: `entry-…` skills are renamed `trigger-…` (the list is
`renames.json`), their `## Entry` table becomes `## Trigger` (columns: Trigger, Phrases, Item key), and the board
says "Triggers" where it said "Workflow entry points". On the Activity page, one time you asked the dispatcher is
now a "Request" (it was called a trigger).

- **Machine data:** nothing changes. Trigger ids (`email`, `news`, `guardian`) are the same, so the done list
  still links items you've seen before.
- **Your own files (on your yes):** your `entry-` skills on the list get their `trigger-` names, their table
  heading is updated (`skill_text.json`), and your board files follow. Until then they keep working as they are.
