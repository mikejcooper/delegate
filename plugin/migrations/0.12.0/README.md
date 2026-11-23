# 0.12.0

- **Connections.** A new kind of skill, `connection-<system>`, holds everything about reaching one external account
  (setup, a harmless check, what it reads and writes). `shared-common-gmail` is now `connection-gmail`: a skill
  of yours with the old name is renamed on your yes, and the board reads the old name as the new one until then.
- Triggers and workflows say which connections they use in their Definition (`uses:`).
- **The plugin ships only the engine and one demo.** It now carries the `core-` skills, the board and a demo
  workflow, `workflow-news-wsj-headlines` ("check the wsj": a two-sentence brief on each of the WSJ's 5 newest world
  news stories, from the free headline and teaser; it needs no accounts and sends nothing). The workflows,
  connections and shared processes it carried before were its author's own and are gone from it. Their runs stay on
  your board; one this folder ran is named in the migration log. To keep using one, add it as a skill of your own
  in `.claude/skills/`.
- **The plugin's source repo is an install like any other.** The plugin sits in `plugin/` of its repo, which uses
  it from there with its own skills and data, as every install does (`paths.py` mode `source`).
- **A first look that opens itself.** The first Claude session in a folder with the plugin opens the dashboard
  (the board), and Claude suggests the demo. `/dashboard`, or just "dashboard" / "open the dashboard", opens it again.
  Until something runs, the board's Inbox shows a card to try the demo; afterwards, a link to what it made.
- **The demo makes a page.** "check the wsj" now ends by adding each brief to today's WSJ briefing page, grouped by
  region, which opens with the day's first story. Pages a workflow makes are served by the board at `/pages/`.
