#!/usr/bin/env python3
"""The run card: the one block every dispatcher run ends with in the chat, the same for every workflow.

    run_card.py <run id>            the card, as markdown: status and time, the run's summary, then a few rows
                                    (what it made, what it sent, its items, what waits on you, what went wrong,
                                    the check), and a link to the run on the board
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
    print(check_line(args[0]) if "--check" in sys.argv else card(args[0]))
