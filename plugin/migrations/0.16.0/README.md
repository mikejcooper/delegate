# 0.16.0: the data folder is called .delegate-data

The plugin was renamed Delegate in 0.15.0; its folder in yours now follows.

- **Machine data:** `.workflow-manager-data/` becomes `.delegate-data/`, the first time any of its scripts runs after
  the update (one rename, nothing copied: `paths.py`). The old name stays as a link to the new folder, so a board
  started before the update and anything else still using the old path keep working. Nothing for you to do.
- **Your own files (on your yes):** your skills that name `.workflow-manager-data/` (a page or file a workflow
  saves there) are changed to name `.delegate-data/`. They work as they are until then, through the link.
- **Your `.gitignore`:** if it lists `.workflow-manager-data/…`, change those lines to `.delegate-data/…`.
- **New installs** clone the plugin to `~/.delegate/delegate`. A computer that already has
  `~/.workflow-manager/workflow-manager` keeps using it and keeps updating from it.
