#!/usr/bin/env python3
"""Today's NY Times briefing page: one page with every story briefed today, newest first.

    scripts/page.py build --stories '[{"headline", "link", "sentence", "published", "author"}, …]'

Puts the run's stories on the page at once (step 3, after the stories are put together). A story already on today's
page is replaced (by link); earlier stories from today stay. Writes nyt-briefing.html in the folder the workflow
manager serves at /pages/ (its board), so the board links to it and the Claude app can show it. A new day starts a
new page. Prints {"page", "url", "open", "stories", "added", "first_today"}: "open" is what to show (the board's
address when the board is up, else the file). While a test runs it writes nothing and says what it would have added.
"""
import argparse
import datetime
import html
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "..", "..", "workflow-ui", "scripts")))
import paths  # noqa: E402

NAME = "nyt-briefing"
KEYS = ("headline", "link", "sentence", "published", "author")


def up(url):
    try:
        with urllib.request.urlopen(url, timeout=1) as r:
            return r.status == 200
    except Exception:
        return False


def render(day, stories):
    e = html.escape
    cards = "".join(
        f'<article><h2><a href="{e(s["link"])}" target="_blank" rel="noopener">{e(s["headline"])}</a></h2>'
        f'<p>{e(s["sentence"])}</p><div class="m">{e(" · ".join(x for x in (s.get("author"), s.get("published")) if x))}'
        f"</div></article>" for s in stories)
    when = datetime.date.fromisoformat(day).strftime("%A %-d %B %Y")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Morning briefing · {e(when)}</title>
<style>
:root{{--bg:#F6F5F1;--card:#fff;--ink:#1f1e1c;--mut:#6b6a66;--line:#E4E2DC;--acc:#2b55c6}}
@media (prefers-color-scheme:dark){{:root{{--bg:#1f1e1d;--card:#262624;--ink:#ecebe8;--mut:#a3a29e;--line:#3d3d3a;--acc:#9db8f5}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 -apple-system,system-ui,"Segoe UI",sans-serif}}
main{{max-width:720px;margin:0 auto;padding:32px 16px 48px}}
header h1{{margin:0;font-size:26px}}header p{{margin:4px 0 24px;color:var(--mut);font-size:13.5px}}
article{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:0 0 10px}}
article h2{{margin:0 0 6px;font-size:16px;line-height:1.35}}article a{{color:var(--ink);text-decoration:none}}
article a:hover{{color:var(--acc);text-decoration:underline}}article p{{margin:0}}
.m{{margin-top:8px;color:var(--mut);font-size:12.5px}}
footer{{margin-top:28px;color:var(--mut);font-size:12.5px}}
</style></head><body><main>
<header><h1>Your morning briefing</h1><p>{e(when)} · {len(stories)} stor{"y" if len(stories) == 1 else "ies"} from the
New York Times, one sentence each from the free headline and summary · the full articles are on nytimes.com</p></header>
{cards}
<footer>Made by the workflow manager's demo workflow. Say “check the new york times” in Claude for the newest stories.</footer>
</main></body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--stories", required=True, help="the stories put together, a JSON list")
    args = ap.parse_args()
    try:
        got = json.loads(args.stories)
    except ValueError as err:
        print(json.dumps({"written": False, "error": f"--stories is not valid JSON ({err})"}, indent=1))
        sys.exit(1)
    new = [{k: str(x.get(k) or "").strip() for k in KEYS} for x in got if isinstance(x, dict)]
    new = [x for x in new if x["headline"] and x["link"] and x["sentence"]]
    if not new:
        print(json.dumps({"written": False, "error": "no stories to put on the page"}, indent=1))
        sys.exit(1)
    if os.path.exists(paths.TEST_MODE):
        print(json.dumps({"test": True, "written": False, "would_add": [x["headline"] for x in new]}, indent=1))
        return
    if os.path.realpath(paths.PROJECT).startswith(os.path.realpath(os.path.join(HERE, "..", "..", "..")) + os.sep) \
            and not paths.SOURCE:
        # run from inside the plugin's own folder: there is no project here to keep the page in
        print(json.dumps({"written": False, "error": "run this from the project's own folder (where the session "
                          "started), not from inside the plugin"}, indent=1))
        sys.exit(1)
    os.makedirs(paths.PAGES, exist_ok=True)
    store, page = os.path.join(paths.PAGES, NAME + ".json"), os.path.join(paths.PAGES, NAME + ".html")
    today = datetime.date.today().isoformat()
    try:
        with open(store, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        data = {}
    first = data.get("day") != today or not data.get("stories")
    if data.get("day") != today:
        data = {"day": today, "stories": []}
    links = {x["link"] for x in new}
    data["stories"] = new + [s for s in data["stories"] if s["link"] not in links]   # this run's on top
    data["updated"] = time.time()
    for path, text in ((store, json.dumps(data, indent=1, ensure_ascii=False)), (page, render(today, data["stories"]))):
        with open(path + ".tmp", "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(path + ".tmp", path)
    url = paths.PAGES_URL + NAME + ".html"
    print(json.dumps({"page": paths.rel(page), "url": url, "open": url if up(paths.URL) else page,
                      "stories": len(data["stories"]), "added": len(new), "first_today": first}, indent=1))


if __name__ == "__main__":
    main()
