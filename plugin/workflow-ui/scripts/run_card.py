#!/usr/bin/env python3
"""The run card: the one block every dispatcher run ends with in the chat, the same for every workflow.

    run_card.py <run id>            the card, as markdown: status and time, the run's summary, then a few rows
                                    (what it made, what it sent, its items, what waits on you, what went wrong,
                                    the check), and a link to the run on the board
    run_card.py <run id> --widget   the same card as HTML for the chat's card tool (show_widget), kept simple: the
                                    summary, only the steps that failed or wait on you, what it made with Copy
                                    link, and a check warning if any (no View in Builder: the chat's card
                                    can't open a page)
    run_card.py <run id> --url      the run's page on the board (the Builder)
    run_card.py <run id> --check    one line, once the run's check (core-run-reviewer) has reported:
                                    "**<workflow> · Check:** No warnings ✓" or "… ⚠ 2 warnings · <first> · see them ↗"

Everything comes from the run's own record (its trace, the check's saved warnings), the same record the board's
outcome card is drawn from, so the chat and the board say the same thing. Claude prints it word for word
(RUN-TRACE.md, "End of a run in the chat"). Read only.
"""
import glob
import json
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402
import path_check  # noqa: E402

BASE = paths.URL.rsplit("/", 1)[0] + "/"
MADE = re.compile(r"(Created|Drafted|Changed|Saved|Made)$", re.I)
SENT = re.compile(r"(Sent|Posted|Reply|Updated)$", re.I)
NOT_YES = re.compile(r"no yes|sent nothing|not sent|said no|didn.t say yes", re.I)


def trace(run):
    folder = paths.RUNS if run.startswith(("wf-", "run-")) else paths.REQUESTS
    try:
        with open(os.path.join(folder, run + ".jsonl"), encoding="utf-8") as fh:
            return [json.loads(x) for x in fh if x.strip()]
    except (OSError, ValueError):
        return []


def when(v):
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def dur(s):
    s = max(0, round(s))
    return f"{s}s" if s < 60 else f"{s // 60}m" + (f" {s % 60}s" if s % 60 else "")


def link(href):
    href = str(href or "")
    if re.match(r"^https?://", href):
        return href.replace("|", "%7C").replace(" ", "%20").replace(")", "%29")
    if re.match(r"^(shots|pages)/", href):
        return BASE + href
    return ""


def md(t):
    """one line of the record as markdown: its own **bold** kept, nothing else that could break the table"""
    return re.sub(r"\s+", " ", str(t or "")).replace("|", "/").strip()


def check_state(run):
    try:
        import suggestions
        items, reviews = suggestions.current()
    except Exception:
        return None, []
    open_ = [s for s in items if s.get("run") == run and s.get("status") == "open"]
    return (run in reviews), open_


def board_url(wid, run):
    return f"{BASE}workflow-viewer.html?w={wid}&run={run}" if wid else BASE + "workflows.html"


def facts(run):
    tl = trace(run)
    hdr = next((x for x in tl if x.get("header")), {})
    end = next((x for x in tl if x.get("end")), None)
    steps = [x for x in tl if x.get("id") and not x.get("header") and not x.get("end")]
    W = path_check.load_defs()
    sk = hdr.get("skill", "")
    if not sk:   # a request: its trigger's workflow (the header's trigger, or the dispatcher's match line)
        trig = hdr.get("trigger") or next((x.get("entry_match") for x in tl if x.get("entry_match")), "")
        sk = ((W or {}).get("entries", {}).get(trig) or {}).get("skill", "") if trig else ""
        if trig and not sk.startswith("workflow-"):   # a trigger inside its workflow: the workflow that lists it
            sk = next((w.get("match", {}).get("skill", "") for w in (W or {}).get("workflows", [])
                       if trig in (w.get("entries") or [])), sk)
    d = path_check.find_def(W, sk) if W and sk else None
    name = (d or {}).get("short") or (d or {}).get("name") or hdr.get("skill") or "Workflow"
    return tl, hdr, end, steps, d, name


def card(run):
    tl, hdr, end, steps, d, name = facts(run)
    if not hdr:
        return f"No run {run} on the board."
    failed = [s for s in steps if s.get("status") == "failed"]
    waits = [s for s in steps if s.get("status") == "needs_user"]
    att = (end or {}).get("attention", "")
    if failed:
        mark, word = "✕", "Failed"
    elif not end:
        mark, word = "…", "Running"
    elif att == "action" or waits:
        mark, word = "!", "Needs you"
    elif att == "review":
        mark, word = "?", "Check this"
    else:
        mark, word = "✓", "Done"
    a, b = when(hdr.get("started")), when((end or {}).get("t"))
    took = dur(b - a) if a and b and b - a >= 2 else ""
    test = (" · a try for real: every step ran" if hdr.get("try") and hdr.get("try_real") else
            " · a test run: nothing was saved or sent" if hdr.get("try") else " · a test" if hdr.get("test") else "")
    out = [f"**{mark} {name}** · {word}" + (f" · {took}" if took else "") + test, ""]
    summ = (end or {}).get("summary") or (end or {}).get("verdict") or ""
    if summ:
        out += [md(summ), ""]
    rows = []
    # what it made and sent: the steps that logged "made", then the run's own "done" list, never the same thing twice
    made, sent, seen, hrefs, held = [], [], set(), set(), 0
    trying = bool(hdr.get("try") and not hdr.get("try_real") or hdr.get("test"))   # a try for real holds nothing back
    for s in steps:
        if s.get("status") != "done":
            continue
        if s.get("type") == "Mocked" or trying and not (s.get("made") or {}).get("href") and re.match(r"(?i)would\b", str(s.get("result", ""))):
            held += 1   # a try's held-back send or write: it made nothing
            continue
        m = s.get("made") or {}
        ty = s.get("as") if s.get("type") == "Fake Read" else s.get("type", "")
        if m.get("name"):
            u = link(m.get("href"))
            t = f"[{m['name']} ↗]({u})" if u else md(m["name"])
            (sent if SENT.search(ty or "") else made).append(t)
            seen.add(m["name"])
            hrefs.add(str(m.get("href") or ""))
        elif SENT.search(ty or "") and not NOT_YES.search(str(s.get("result", ""))):
            sent.append(md(s.get("title") or s.get("step")))
    for x in (end or {}).get("done") or []:
        if isinstance(x, dict) and x.get("t") and x["t"] not in seen and x.get("k") in ("mail", "file") \
                and not (x.get("href") and str(x["href"]) in hrefs):   # the same thing under another name: once
            u = link(x.get("href"))
            made.append(f"[{x['t']} ↗]({u})" if u else md(x["t"]))
    not_yes = any(s.get("type") == "Asked You" and s.get("status") == "done" and NOT_YES.search(str(s.get("result", "")))
                  for s in steps)
    if made:
        rows.append(("Made", " · ".join(made)))
    if sent:
        rows.append(("Sent", " · ".join(sent)))
    elif not_yes:
        rows.append(("Sent", "Not sent: you didn’t say yes"))
    elif end and not made and not waits and not held:
        rows.append(("Made", "Nothing made or sent" if hdr.get("kind") != "trigger" else "Nothing new to run"))
    if held:
        rows.append(("Not sent", f"{held} send{'s' if held > 1 else ''} or write{'s' if held > 1 else ''}: a try sends nothing"))
    # a loop workflow's run: its items, added up
    if hdr.get("kind") == "batch":
        its = []
        for p in glob.glob(os.path.join(paths.RUNS, "wf-*.jsonl")):
            t2 = trace(os.path.basename(p)[:-6])
            h2 = next((x for x in t2 if x.get("header")), {})
            if h2.get("batch") == run:
                its.append(t2)
        each = ((d or {}).get("loops") or [{}])[0].get("each", "item")
        stops = {str(p.get("label", "")).replace("If: ", "").lower() for p in (d or {}).get("simulated", [])
                 if (p.get("out") or [""])[0] == "stop"}
        n_stop = sum(1 for t2 in its if str(next((x for x in t2 if x.get("end")), {}).get("path", "")).replace("If: ", "").lower() in stops)
        n_fail = sum(1 for t2 in its if any(x.get("status") == "failed" for x in t2))
        n = len(its)
        plural = each if n == 1 else (each[:-1] + "ies" if re.search(r"[^aeiou]y$", each) else each + "s")
        parts = ([f"{n - n_stop - n_fail} done"] if n - n_stop - n_fail else []) + ([f"{n_stop} stopped"] if n_stop else []) + ([f"{n_fail} failed"] if n_fail else [])
        rows.append((plural.capitalize(), f"{n} · " + " · ".join(parts)))
    if waits or att == "action":
        w = (end or {}).get("waiting") or (waits[-1].get("result") if waits else "")
        wf = hdr.get("wf", "")
        ans = f" · paste `answer {wf}: yes` or `answer {wf}: no`" if wf and waits else ""
        rows.append(("Waiting on you", md(w) + ans))
    if failed or (end or {}).get("problems"):
        p = ((end or {}).get("problems") or [{}])[0]
        what = md(p.get("what") or (failed[0].get("title") or failed[0].get("step")) + ": " + str(failed[0].get("result", "")))
        rows.append(("What went wrong", what + (f" · fix: {md(p['fix'])}" if p.get("fix") else "")))
    ran = hdr.get("kind") != "trigger" or any(str(x.get("step", "")).startswith("forked") for x in steps)
    if end and ran and not hdr.get("test") and (not hdr.get("try") or hdr.get("try_real")):   # a try for real is reviewed too; a request that ran nothing isn't
        reviewed, open_ = check_state(run)
        rows.append(("Check", ("No warnings" if not open_ else f"⚠ {len(open_)} warning{'s' if len(open_) > 1 else ''}: {md(open_[0].get('title'))}")
                     if reviewed else "running…"))
    if rows:
        out += ["| | |", "|---|---|"] + [f"| **{k}** | {v} |" for k, v in rows] + [""]
    out.append(f"[See the run on the board ↗]({board_url((d or {}).get('id'), run)})")
    return "\n".join(out)



CSS = ("<style>.rc{background:var(--surface-2);border:.5px solid var(--border);border-radius:12px;padding:1rem 1.25rem;"
       "font-size:13px;margin:.5rem 0}.rh{display:flex;align-items:center;gap:10px}.rn{font-weight:500;font-size:15px}"
       ".rb{margin-left:auto;font-size:12px;padding:2px 10px;border-radius:var(--radius)}.ok{background:var(--bg-success);"
       "color:var(--text-success)}.bad{background:var(--bg-danger);color:var(--text-danger)}.wait{background:var(--bg-warning);"
       "color:var(--text-warning)}.rs{color:var(--text-secondary);font-size:14px;line-height:1.6;margin:6px 0 10px}"
       ".rl{border-top:.5px solid var(--border);padding-top:8px;margin-top:8px;line-height:1.9}.rl i{margin-right:6px}"
       ".rr{display:flex;gap:8px;align-items:center}.rr span{color:var(--text-secondary);min-width:64px}"
       ".rf{display:flex;gap:8px;align-items:center;border-top:.5px solid var(--border);margin-top:8px;padding-top:10px}"
       ".rf span{color:var(--text-secondary);flex:1}</style>")
JS = ("<script>function cp(b,u){var d=function(){b.textContent='Link copied'};try{navigator.clipboard.writeText(u)"
      ".then(d,function(){prompt('Copy the link',u)})}catch(e){prompt('Copy the link',u)}}</script>")


def esc(t):
    return (str(t or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
            .replace("'", "&#39;"))


def widget(run):
    tl, hdr, end, steps, d, name = facts(run)
    if not hdr:
        return f"No run {run} on the board."
    md_card = card(run).split("\n")
    head = md_card[0]   # "**✓ Name** · Done · 51s"
    word = head.split("**")[-1].strip(" ·").split(" · ")[0] if "** · " in head else ""
    cls = {"Done": "ok", "Failed": "bad", "Needs you": "wait", "Check this": "wait"}.get(word, "")
    badge = esc(" · ".join(x for x in head.split("**")[-1].strip(" ·").split(" · ") if x))
    summ = (end or {}).get("summary") or (end or {}).get("verdict") or ""
    icon = {"ok": "ti-circle-check", "bad": "ti-circle-x", "wait": "ti-alert-circle"}.get(cls, "ti-loader")
    col = {"ok": "success", "bad": "danger", "wait": "warning"}.get(cls, "secondary")
    h = [CSS, f'<h2 class="sr-only">{esc(name)}: {esc(word)}. {esc(summ)}</h2><div class="rc">',
         f'<div class="rh"><i class="ti {icon}" style="font-size:20px;color:var(--text-{col})" aria-hidden="true"></i>'
         f'<span class="rn">{esc(name)}</span><span class="rb {cls}">{badge}</span></div>']
    if summ:
        h.append(f'<p class="rs">{esc(summ)}</p>')
    # kept simple: the summary says what happened; only a step that failed or waits on the user gets a line
    # (every step stays on the board, one click away)
    rows = []
    for x in steps:
        st = x.get("status")
        if st not in ("failed", "needs_user"):
            continue
        ic, c = ("ti-x", "danger") if st == "failed" else ("ti-hand-stop", "warning")
        t = x.get("title") or x.get("step") or x.get("type") or ""
        r = str(x.get("result") or "")
        rows.append(f'<div><i class="ti {ic}" style="color:var(--text-{c})" aria-hidden="true"></i>{esc(t)}'
                    + (f' <span style="color:var(--text-secondary)">· {esc(r[:90] + ("…" if len(r) > 90 else ""))}</span>' if r else "")
                    + "</div>")
    if rows:
        h.append('<div class="rl">' + "".join(rows[:5]) + "</div>")
    # the card's rows (Made, Sent, items, waiting, what went wrong): links become Copy link buttons;
    # "nothing made" and the check while it runs say nothing the summary doesn't, so they're left out
    extra = []
    for line in md_card:
        m = re.match(r"^\| \*\*(.+?)\*\* \| (.*) \|$", line)
        if not m or m.group(1) == "Check":
            continue
        k, v = m.group(1), m.group(2)
        if k == "Made" and v.startswith("Nothing"):
            continue
        btns = "".join(f'<button onclick="cp(this,\'{esc(u)}\')"><i class="ti ti-copy" aria-hidden="true"></i> '
                       f'{esc(t)}: Copy link</button>' for t, u in re.findall(r"\[(.+?) ↗\]\((.+?)\)", v))
        text = re.sub(r"\[(.+?) ↗\]\((.+?)\)", "", v).strip(" ·`")
        text = re.sub(r"`([^`]*)`", r"\1", text)
        extra.append(f'<div class="rr"><span>{esc(k)}</span>{esc(text)}{btns}</div>')
    if extra:
        h.append('<div class="rl">' + "".join(extra) + "</div>")
    chk = next((re.match(r"^\| \*\*Check\*\* \| (.*) \|$", x).group(1) for x in md_card
                if re.match(r"^\| \*\*Check\*\* \|", x)), "")
    chk = chk if chk.startswith("⚠") else ""   # only a warning earns a line
    # no View in Builder: the chat's card can't open a page (links, window.open and sendPrompt all go nowhere)
    if chk:
        h.append(f'<div class="rf"><span>Check: {esc(chk)}</span></div>')
    h.append("</div>" + JS)
    return "".join(h)

def check_line(run):
    _, hdr, _, _, d, name = facts(run)
    reviewed, open_ = check_state(run)
    if not reviewed:
        return f"**{name} · Check:** still running"
    if not open_:
        return f"**{name} · Check:** No warnings ✓"
    return (f"**{name} · Check:** ⚠ {len(open_)} warning{'s' if len(open_) > 1 else ''} · {md(open_[0].get('title'))} · "
            f"[see them ↗]({board_url((d or {}).get('id'), run)})")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        sys.exit(1)
    if "--url" in sys.argv:
        print(board_url((facts(args[0])[4] or {}).get("id"), args[0]))
    elif "--widget" in sys.argv:
        print(widget(args[0]))
    else:
        print(check_line(args[0]) if "--check" in sys.argv else card(args[0]))
