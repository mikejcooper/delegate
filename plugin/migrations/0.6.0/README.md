# 0.6.0: every skill named `<kind>-<category>-<description>`

The plugin's skills are renamed (`manager-work-dispatcher` → `core-dispatcher`, `workflow-security` →
`workflow-security-alert`, and so on: the full list is `renames.json`), and email and BBC News become entry-point
skills of their own.

- **Machine data:** nothing changes. Past runs keep the names they had at the time.
- **Your own files (on your yes):** your skills that are on the list get their new names (folder and `name:` line),
  your board files in `.dispatcher/board/` are renamed to match, and every reference inside them to a renamed skill
  (yours or the plugin's) is updated. Until then the board reads the old names as the new ones.
