# 0.9.0: `.workflow-manager/` becomes `.workflow-manager-data/`

Only the folder's name changes, so it reads as the plugin's data rather than the plugin itself. Inside it is
the same: `config/` (yours), `history/` (what happened), `system/` (plumbing).

- **Machine data (automatic, backed up first):** `history/`, `system/` and your `config/settings.json` move
  across unchanged. The board keeps its address.
- **Your own files (on your yes):** your board files move from `.workflow-manager/config/board/` to
  `.workflow-manager-data/config/board/`, unchanged. Until then the board still reads them where they are.
  The old folder is removed once it is empty.

Suggested `.gitignore` for your project: `.workflow-manager-data/history/` and `.workflow-manager-data/system/`.
