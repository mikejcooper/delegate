# Categories

The `<category>` part of every skill name (`<kind>-<category>-<description>`, rule 10). One word each. The same list for
workflows and shared processes, so everything about one area sorts and shows together.

Two lists, read together like the skills: **this file**, the few the plugin ships with, and **the folder's own**,
`.workflow-manager-data/config/categories.md` (`paths.py` lists both under `categories`, the folder's first). A
folder's own list holds the areas its own workflows belong to; it never ships with the plugin. A word in both lists
means the same area: the folder's line wins.

| Category | What belongs here |
|---|---|
| `news` | reading and summarising news |
| `common` | processes used across several categories (mostly `shared-` skills) |
| `new` | reserved: a new workflow and its trigger from the first draft until they are named, as they are first published (Create mode). Never published |

**Adding one.** When nothing fits, the architect proposes a new category in its plan, with a one-line meaning,
and adds it on a yes: to the folder's own list (an install, or the plugin's source repo for its own workflows),
or here only for the plugin's own skills (the engine and the demo, in its source repo).
