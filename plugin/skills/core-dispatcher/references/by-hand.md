# Front door: Changing items or settings by hand

Part of core-dispatcher (its SKILL.md says when to read this). Names in bold are sections of SKILL.md or of the
other files in this folder.

## Change items by hand
The user changes items or the **Run each item once** switch themselves, usually with a line the board's Inbox page copied. It runs nothing: it changes only the done list, the switch, and (for a delete) where the item's run traces are kept.
1. Take each workflow ID (`wf-` + 8 hex) or request ID (`dispatch-…`) from the request. None, for anything but the switch: ask for them and wait.
2. Make the change with `item_id.py` (it looks each item up; an ID with no done-list line comes back in `not_found`: say so):

   | Request | Command | What it means from then on |
   |---|---|---|
   | "skip wf-…" | `mark <wf>... --to skipped --run <run ID>` | linked by every trigger; runs again only when the user names its workflow ID |
   | "mark wf-… done" | `mark <wf>... --to done --run <run ID>` | linked, as handled |
   | "mark wf-… needs you" | `mark <wf>... --to needs --run <run ID>` | linked, shown as waiting on the user |
   | "mark wf-… not run" | `mark <wf>... --to notrun --run <run ID>` | run by the next trigger run that finds it, or by "run workflow … on wf-…" |
   | "delete wf-…" | `delete <wf>... --run <run ID>` | off the board; its run traces go to the traces folder's `.trash/`; a trigger that finds it again runs it as new |
   | "delete request dispatch-…" (a "Nothing new" row: its trigger kept nothing, or everything was already handled) | `delete-request <request ID>... --run <run ID>` | that request off the board (its trace to `.trash/`); no item or done list changes. A request that ran items is refused (`refused_ran_items`): say so, and that its items are deleted with "delete wf-…" |
   | "turn Run each item once on" / "off" | `setting --skip-done on` / `off` | on: items already handled are linked; off: they run again |
   | "turn Approve automatically on" / "off" | `setting --auto-approve on` / `off` | on: a real run's "Send it?" steps are answered yes; off: they wait on the Inbox as Needs you |

3. Say what changed, one line per item (or the switch's new value).

The two switches are run settings, not items: changing one writes no step for an item and changes no done list.
