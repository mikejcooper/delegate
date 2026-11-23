# 0.4.0: example migration

A small, harmless change to show the walker working.

- **Machine data (automatic):** every trace's header line gets `"format": 2`, and
  `dispatcher-data/settings.json` gets `"show_seen_before": true` (created with the defaults if missing).
- **Your own files (on your yes):** each skill's `board.json` gets `"format": 2`.
