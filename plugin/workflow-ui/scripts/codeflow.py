#!/usr/bin/env python3
"""Draw a workflow or shared process written as code: read its Python with the ast module (never run it) and return a workflow
definition in the same shape as workflows.json, so the Workflow Viewer shows it like any other.

A skill folder is a code workflow when one of its .py files has a function marked @flow("Name"). From there:
- every call to a function marked @step("Tag", "Title") inside the @flow function is a step, in order;
- a call to a function marked @decision("Question?", options=[...]) is a decision, and an `if` on the variable
  it was assigned to (==, !=, in, not in, else) puts the steps in its body on those options;
- unmarked functions (helpers) are not drawn;
- each step's Why? is its docstring, with the function's code (file and lines) under "Show the code";
- real runs match by key: the markers write the function's name into each trace line.

    python3 -I codeflow.py <skill folder>     prints the definition as JSON (for checking by hand)
"""
import ast
import itertools
import json
import os
import sys

MARKS = ("flow", "step", "decision")
TYPE = {"Read": "read", "Check": "check", "Search": "check", "Score": "check", "Write": "check", "Report": "read"}


def _mark(fn):
    """('flow'|'step'|'decision', args, kwargs) for a function's marker decorator, or None."""
    for d in fn.decorator_list:
        if isinstance(d, ast.Call):
            name = d.func.id if isinstance(d.func, ast.Name) else d.func.attr if isinstance(d.func, ast.Attribute) else ""
            if name in MARKS:
                args = [a.value for a in d.args if isinstance(a, ast.Constant)]
                kw = {}
                for k in d.keywords:
                    try:
                        kw[k.arg] = ast.literal_eval(k.value)
                    except ValueError:
                        pass
                return name, args, kw
    return None


def _called(node, marked):
    """Marked functions called inside a statement, in source order."""
    calls = [n for n in ast.walk(node) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in marked]
    return sorted(calls, key=lambda n: (n.lineno, n.col_offset))


def _options(test, var_dec, decisions):
    """(decision key, [option indexes]) that an if-test selects, or (None, None)."""
    if isinstance(test, ast.Compare) and isinstance(test.left, ast.Name) and test.left.id in var_dec and len(test.ops) == 1:
        key = var_dec[test.left.id]
        opts = decisions[key]
        right, op = test.comparators[0], test.ops[0]
        vals = [right.value] if isinstance(right, ast.Constant) else \
            [e.value for e in getattr(right, "elts", []) if isinstance(e, ast.Constant)]
        idx = [opts.index(v) for v in vals if v in opts]
        if isinstance(op, (ast.NotEq, ast.NotIn)):
            idx = [i for i in range(len(opts)) if i not in idx]
        return key, idx
    return None, None


def read(folder):
    """The workflow definition for a code-workflow skill folder, or None when it has no @flow function."""
    skill = os.path.basename(os.path.normpath(folder))
    funcs, entry, src_of = {}, None, {}
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".py"):
            continue
        path = os.path.join(folder, name)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        lines = text.splitlines()
        for fn in tree.body:
            if not isinstance(fn, ast.FunctionDef):
                continue
            m = _mark(fn)
            if not m:
                continue
            start = min([d.lineno for d in fn.decorator_list] + [fn.lineno])
            code = "\n".join(f"{i:4d}  {lines[i - 1]}" for i in range(start, fn.end_lineno + 1))
            info = {"kind": m[0], "args": m[1], "kw": m[2], "doc": ast.get_docstring(fn) or "", "file": name,
                    "lines": (start, fn.end_lineno), "code": code, "node": fn}
            if m[0] == "flow":
                entry = info
            else:
                funcs[fn.name] = info
        src_of[name] = ast.get_docstring(tree) or ""
    if not entry:
        return None
    decisions = {k: f["kw"].get("options") or (f["args"][1] if len(f["args"]) > 1 else []) for k, f in funcs.items()
                 if f["kind"] == "decision"}
    steps, var_dec, order = [], {}, {}

    def add(key, on):
        f = funcs[key]
        n = len(steps) + 1
        tag, title = (f["args"] + ["", ""])[:2] if f["kind"] == "step" else ("Decide", (f["args"] or [key])[0])
        doc = f["doc"].split("\n\n")[0].replace("\n", " ")
        st = {"key": key, "sk": skill, "lane": f"{f['file']} · {key}()", "type": "dec" if f["kind"] == "decision" else TYPE.get(tag, "check"),
              "title": title, "tag": tag if f["kind"] == "step" else "Decide", "what": doc,
              "from": {"key": key},
              "why": {"file": skill, "label": f"{f['file']} · {key}() · lines {f['lines'][0]}–{f['lines'][1]}", "sum": doc,
                      "rule": f["code"], "code": True, "missing": False}}
        if f["kind"] == "decision":
            st["alts"] = [{"when": o, "then": "carries on", "k": "next"} for o in decisions[key]]
            st["from"] = {"key": key}
            st["taken_by"] = "result"
        if on:
            st["on"] = on
        steps.append(st)
        order[key] = n

    def walk(body, on=None):
        for stmt in body:
            if isinstance(stmt, ast.If):
                key, idx = _options(stmt.test, var_dec, decisions)
                if key is None:
                    walk(stmt.body, on)
                    walk(stmt.orelse, on)
                    continue
                walk(stmt.body, {"step": key, "alt": idx if len(idx) > 1 else idx[0]})
                rest = [i for i in range(len(decisions[key])) if i not in idx]
                if stmt.orelse and rest:
                    walk(stmt.orelse, {"step": key, "alt": rest if len(rest) > 1 else rest[0]})
                continue
            for call in _called(stmt, funcs):
                if call.func.id in order:
                    continue
                add(call.func.id, on)
            if isinstance(stmt, ast.Assign) and isinstance(stmt.value, ast.Call) and isinstance(stmt.value.func, ast.Name) \
                    and stmt.value.func.id in decisions:
                for t in stmt.targets:
                    if isinstance(t, ast.Name):
                        var_dec[t.id] = stmt.value.func.id

    walk(entry["node"].body)
    # say what each branch leads to, from the first step on that option
    for st in steps:
        for i, alt in enumerate(st.get("alts", [])):
            first = next((x for x in steps if (x.get("on") or {}).get("step") == st["key"]
                          and i in ([x["on"]["alt"]] if isinstance(x["on"]["alt"], int) else x["on"]["alt"])), None)
            alt["then"] = first["title"] if first else "carries on"
    # one example path per combination of decision options
    decs = [s for s in steps if s["type"] == "dec"]
    paths = []
    for combo in itertools.product(*[range(len(d["alts"])) for d in decs]):
        taken = {d["key"]: [c] for d, c in zip(decs, combo)}
        label = "If: " + ", then ".join(d["alts"][c]["when"] for d, c in zip(decs, combo))
        paths.append({"label": label, "res": {}, "taken": taken, "out": ["done", "Writes the report"]})
    name = entry["args"][0] if entry["args"] else skill
    area = skill.split("-")[1] if skill.count("-") >= 2 else "common"
    return {"id": skill.split("-", 2)[-1] if skill.count("-") >= 2 else skill, "category": area, "short": name,
            "name": name, "code": True, "direct": True, "entries": [],
            "desc": (src_of.get(entry["file"]) or "").split("\n\n")[0].replace("\n", " "),
            "from": "you, or a test (no trigger)", "match": {"skill": skill, "default": True},
            "steps": steps, "simulated": paths,
            "source": {"file": entry["file"], "lines": sum(1 for _ in open(os.path.join(folder, entry["file"]), encoding="utf-8"))}}


if __name__ == "__main__":
    print(json.dumps(read(sys.argv[1]), indent=1, ensure_ascii=False))
