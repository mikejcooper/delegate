# 0.5.0: tidy `.dispatcher/` into `board/` and `data/`

- **Machine data (automatic):** everything that was directly in `.dispatcher/` (traces, screenshots, the done
  list, settings, backups, the version stamp, the log) moves into `.dispatcher/data/`. The board keeps its port.
- **Your own files (on your yes):** each skill's `board.json` moves out of the skill folder to
  `.dispatcher/board/<skill name>.json`. Its content doesn't change. Until then the board still reads it
  where it is.
