# 0.8.0: `.dispatcher/` becomes `.workflow-manager/`

The plugin is now called **workflow-manager**, and so is its folder in your project. Inside, three parts:

- `config/`: yours. `settings.json` (your switches) and `board/<skill>.json` (how your skills show on the board).
- `history/`: what happened. `requests/` (one file per time you asked), `runs/` (one per item),
  `screenshots/`, `done-list.jsonl`.
- `system/`: plumbing. Version, migration log, backups, generated board files.

**Machine data (automatic, backed up first):** traces are sorted into `history/requests/` and `history/runs/`,
`shots/` becomes `history/screenshots/`, `ledger.jsonl` becomes `history/done-list.jsonl`, your
"run each item once" switch moves to `config/settings.json`, and the version stamp, log and backups move to
`system/`. Generated files are rebuilt. The board keeps its address.

**Your own files (on your yes):** your board files move from `.dispatcher/board/` to
`.workflow-manager/config/board/`, unchanged. Until then the board still reads them where they are. When
`.dispatcher/` is empty it is removed.
