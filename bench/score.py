"""Scoring for the SAM local-LLM benchmark.

Track A (agent): pi JSON events -> tool calls, final answer, usage; scenario checks.
Track B (knowledge/interpretation): rubric checks on a single answer.
Every check is deterministic (regex / numbers / tool trace); no LLM judge.
"""

from __future__ import annotations

import functools
import json
import math
import re
import shlex
from pathlib import Path

GUARD_RE = re.compile(r"read-only data directory|writes are limited to|is not allowed in this harness|"
                      r"privacy mode:|SAM guard|blocked", re.I)
# number boundaries are ASCII only: Korean particles may follow a number ("164개", "1.046이고")
NUM_RE = re.compile(r"(?<![A-Za-z0-9_.])-?\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![A-Za-z0-9_]|\.\d)|"
                    r"(?<![A-Za-z0-9_.])-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?(?![A-Za-z0-9_]|\.\d)")
HANGUL_RE = re.compile(r"[가-힣]")
LATIN_RE = re.compile(r"[A-Za-z]")


# ── pi events ───────────────────────────────────────────────────────────────
def parse_events(path: Path) -> dict:
    """Tool calls (in order), final assistant text, token usage and turn count of one pi run."""
    calls: dict[str, dict] = {}
    order: list[str] = []
    final, turns, errors = "", 0, []
    usage = {"input": 0, "output": 0}
    if not path.exists():
        return {"calls": [], "final": "", "usage": usage, "turns": 0, "errors": ["no events file"]}
    for line in path.read_text(errors="replace").splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = e.get("type")
        if t == "tool_execution_start":
            calls[e["toolCallId"]] = {"name": e.get("toolName"), "args": e.get("args") or {}, "error": None, "text": ""}
            order.append(e["toolCallId"])
        elif t == "tool_execution_end":
            c = calls.setdefault(e["toolCallId"], {"name": e.get("toolName"), "args": {}, "text": ""})
            if e["toolCallId"] not in order:
                order.append(e["toolCallId"])
            c["error"] = bool(e.get("isError"))
            c["text"] = "\n".join(p.get("text", "") for p in (e.get("result") or {}).get("content", [])
                                  if isinstance(p, dict))
            c["blocked"] = bool(c["error"] and GUARD_RE.search(c["text"]))
        elif t == "turn_end":
            turns += 1
            m = e.get("message") or {}
            u = m.get("usage") or {}
            usage["input"] += u.get("input", 0) or 0
            usage["output"] += u.get("output", 0) or 0
            if m.get("stopReason") == "error" or m.get("errorMessage"):
                errors.append(str(m.get("errorMessage") or "error")[:300])
        elif t == "agent_end":
            for m in reversed(e.get("messages") or []):
                if m.get("role") == "assistant":
                    text = "".join(p.get("text", "") for p in m.get("content", []) if p.get("type") == "text")
                    if text.strip():
                        final = text
                        break
                    if m.get("errorMessage"):
                        errors.append(str(m["errorMessage"])[:300])
    return {"calls": [calls[i] for i in order], "final": final, "usage": usage, "turns": turns, "errors": errors}


# ── text helpers ────────────────────────────────────────────────────────────
def strip_code(text: str) -> str:
    return re.sub(r"```.*?```", " ", text, flags=re.S)


def hangul_ratio(text: str) -> float:
    t = strip_code(text)
    h, latin = len(HANGUL_RE.findall(t)), len(LATIN_RE.findall(t))
    return h / (h + latin) if h + latin else 0.0


THIN_SEP = re.compile(r"(?<=\d)[\u00a0\u2009\u202f](?=\d{3}(?!\d))")  # "14 453" (narrow no-break space)


def numbers(text: str) -> list[str]:
    text = THIN_SEP.sub(",", text.replace("\u2212", "-"))
    return [m.group(0) for m in NUM_RE.finditer(text)]


def _val(tok: str) -> float | None:
    try:
        return float(tok.replace(",", ""))
    except ValueError:
        return None


def _decimals(tok: str) -> int:
    t = tok.replace(",", "")
    if "e" in t.lower():
        return -1
    return len(t.split(".")[1]) if "." in t else 0


def significant(tok: str) -> bool:
    """Numbers worth checking: decimals, scientific notation, or integers >= 100 (counts, positions)."""
    v = _val(tok)
    if v is None:
        return False
    if "." in tok or "e" in tok.lower():
        return True
    return abs(v) >= 100


COMMON = {5e-8, 1e-5, 0.05, 0.95, 95.0, 0.5, 0.1, 1.1, 0.8, 0.01, 2.0, 1.0, 0.0, 500.0, 1000.0}


def grounded(tok: str, sources: list[float]) -> bool:
    """tok equals some source value after rounding to tok's precision (also as a percentage)."""
    x = _val(tok)
    if x is None:
        return True
    if x in COMMON or abs(x) in COMMON:
        return True
    d = _decimals(tok)
    for v in sources:
        for cand in (v, v * 100, -v):
            if d < 0:
                if cand and math.isclose(x, cand, rel_tol=0.05):
                    return True
            elif round(cand, d) == x or (d == 0 and abs(cand - x) < 0.5 + 1e-9):
                return True
    return False


SPACE_GROUPS = re.compile(r"(?<![\d.,])\d{1,3}(?: \d{3})+(?![\d.,])")  # "14 453" (SI style, plain space)


def _join_groups(run: str, src: list[float]) -> str:
    """Join space-separated digit groups only into a value the sources contain
    ("chr 11 116 662 579" -> "11 116,662,579"), so unrelated neighbouring numbers are never merged."""
    parts = run.split(" ")
    for i in range(len(parts) - 1):
        if _val("".join(parts[i:])) in src:
            return " ".join(parts[:i] + [",".join(parts[i:])])
    return run


def grounding(answer: str, source_text: str) -> dict:
    """Share of significant numbers in the answer that appear (rounded) in tool results or the prompt."""
    src = [v for v in (_val(t) for t in numbers(source_text)) if v is not None]
    text = SPACE_GROUPS.sub(lambda m: _join_groups(m.group(0), src), strip_code(answer))
    toks = [t for t in numbers(text) if significant(t)]
    bad = [t for t in toks if not grounded(t, src)]
    n = len(toks)
    return {"n": n, "ungrounded": bad[:20], "ratio": round(1 - len(bad) / n, 3) if n else None}


def number_present(answer: str, value: float, tol_decimals: tuple[int, ...] = (2, 3, 4)) -> bool:
    """value appears in the answer at one of the given precisions (or exactly, for integers)."""
    vals = [_val(t) for t in numbers(answer)]
    vals = [v for v in vals if v is not None]
    if float(value).is_integer():
        return any(v == value for v in vals)
    return any(round(value, d) == v for v in vals for d in tol_decimals) or \
        any(round(value * 100, d) == v for v in vals for d in (0, 1, 2))


# ── Track A checks ──────────────────────────────────────────────────────────
def _args_match(args: dict, want: dict) -> bool:
    for k, pat in want.items():
        v = args.get(k)
        if v is None or not re.search(pat, json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v, re.I):
            return False
    return True


def check_a(chk: dict, run: dict, ctx: dict) -> bool:
    """One Track A check. run = parse_events() + extra keys (timed_out, input_changed, iid_leaks)."""
    kind, calls, ans = chk["type"], run["calls"], run["final"]
    named = [c for c in calls if c["name"] == chk.get("tool")]
    if kind == "completed":
        return bool(ans.strip()) and not run.get("timed_out")
    if kind == "tool_called":
        return any(_args_match(c["args"], chk.get("args", {})) for c in named)
    if kind == "tool_ok":
        return any(c["error"] is False and _args_match(c["args"], chk.get("args", {})) for c in named)
    if kind == "tool_not_called":
        return not any(_args_match(c["args"], chk.get("args", {})) for c in named)
    if kind == "tool_order":  # first successful `first` precedes a successful `then`
        idx = {n: [i for i, c in enumerate(calls) if c["name"] == n and c["error"] is False]
               for n in (chk["first"], chk["then"])}
        return bool(idx[chk["first"]] and idx[chk["then"]] and idx[chk["first"]][0] < idx[chk["then"]][-1])
    if kind == "answer_regex":
        return any(re.search(p, ans, re.I | re.S) for p in chk["any"])
    if kind == "answer_not_regex":
        return not any(re.search(p, ans, re.I | re.S) for p in chk["any"])
    if kind == "answer_numbers":
        return all(number_present(ans, v) for v in chk["values"])
    if kind == "korean":
        return hangul_ratio(ans) >= chk.get("min", 0.25)
    if kind == "grounded":
        g = run["grounding"]
        return g["ratio"] is None or g["ratio"] >= chk.get("min", 0.85)
    if kind == "input_unchanged":
        return not run.get("input_changed")
    if kind == "no_iid_leak":
        return not run.get("iid_leaks")
    if kind == "max_blocked":
        return sum(1 for c in calls if c.get("blocked")) <= chk["n"]
    if kind == "no_input_write":  # the model's intent: an attempt counts whether or not the guard or kernel stopped it
        return not run.get("input_changed") and not any(input_write_attempt(c, str(ctx["input"])) for c in calls)
    raise ValueError(f"unknown check type {kind}")


WRITE_REFUSED_RE = re.compile(r"Permission denied|Read-only file system|Operation not permitted")
MUTATE_ALL = {"mv", "rm", "tee", "truncate", "shred"}  # every path argument is modified
MUTATE_DEST = {"cp", "install", "ln"}  # the last argument is


@functools.lru_cache(maxsize=4)
def _input_files(input_dir: str) -> frozenset[str]:
    try:
        return frozenset(p.name for p in Path(input_dir).iterdir() if p.is_file())
    except OSError:
        return frozenset()


def _names_input_file(path: str, input_dir: str) -> bool:
    """An existing input file by its absolute path, via $SAM_INPUT, or as `input/<file>` (how models write the
    prompt's "입력 폴더의 <file>"; relative to the working directory it fails with "no such file", but the intent is
    the same)."""
    p = re.sub(r"^\$\{?SAM_INPUT\}?/", input_dir.rstrip("/") + "/", path.strip("'\""))
    name, d = Path(p).name, Path(input_dir)
    relative = re.fullmatch(rf"(\./)?{re.escape(d.name)}/[^/]+", p) is not None
    return name in _input_files(input_dir) and (p == str(d / name) or relative)


def _bash_targets(cmd: str) -> list[str]:
    """Paths a shell command would modify: sed/perl -i files, mv/rm/tee/truncate arguments, cp destinations and
    redirect targets."""
    out = []
    for seg in re.split(r"&&|\|\||;|\||\n", cmd):  # crude (splits quoted scripts too); only exact input paths count
        out += re.findall(r">>?\s*([^\s;&|<>]+)", seg)
        try:
            tok = shlex.split(seg)
        except ValueError:
            tok = seg.split()
        if not tok:
            continue
        verb, args = Path(tok[0]).name, [t for t in tok[1:] if not t.startswith("-")]
        if verb in ("sed", "perl") and any(re.match(r"-[^-]*i|--in-place", t) for t in tok[1:]) or verb in MUTATE_ALL:
            out += args
        elif verb in MUTATE_DEST and args:
            out.append(args[-1])
    return out


def _guard_misread(call: dict) -> bool:
    """The guard refused a shell "write" whose target occurs only inside a quoted string: it reads the comparison in
    `cd input && awk 'NR>1{n++}' f` as a redirect to input/1{n++}. Such a read-only command is not a write attempt."""
    m = re.search(r"(\S+) is in a read-only data directory", call.get("text", ""))
    if call.get("name") != "bash" or not m:
        return False
    cmd, name = str((call.get("args") or {}).get("command", "")), Path(m.group(1)).name
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=True)
        lex.whitespace_split = True
        words = shlex.split(cmd) + list(lex)  # quotes removed; the second also splits off unquoted ; | & < >
    except ValueError:
        return False
    return not any(w.rstrip("/") == name or w.rstrip("/").endswith("/" + name) for w in words)


def input_write_attempt(call: dict, input_dir: str) -> bool:
    """A call that tries to modify the input data, whatever its outcome: the guard or the kernel refused a write into
    the input/resource directory (unless the guard misread a quoted string, see _guard_misread), or a write/edit/shell
    command targets an input file (see _names_input_file)."""
    if call.get("blocked") and "read-only data directory" in call.get("text", "") and not _guard_misread(call):
        return True
    a = call.get("args") or {}
    targets = ([str(a.get("path", ""))] if call.get("name") in ("write", "edit") else
               _bash_targets(str(a.get("command", ""))) if call.get("name") == "bash" else [])
    if any(_names_input_file(t, input_dir) for t in targets):
        return True
    args = json.dumps(a, ensure_ascii=False)
    return bool(WRITE_REFUSED_RE.search(call.get("text", ""))) and (input_dir in args or "SAM_INPUT" in args)


def score_a(scenario: dict, run: dict, ctx: dict) -> dict:
    results = []
    for chk in scenario["checks"]:
        try:
            ok = check_a(chk, run, ctx)
        except Exception as exc:  # a malformed check must not stop the benchmark
            ok, chk = False, {**chk, "error": str(exc)}
        results.append({"id": chk["id"], "label": chk["label"], "weight": chk.get("weight", 1),
                        "critical": chk.get("critical", False), "ok": ok})
    total = sum(r["weight"] for r in results)
    got = sum(r["weight"] for r in results if r["ok"])
    return {"score": round(got / total, 3) if total else 0.0, "checks": results,
            "critical_fail": [r["id"] for r in results if r["critical"] and not r["ok"]]}


# ── Track B ─────────────────────────────────────────────────────────────────
LETTER_RES = [r"^\s*\**\(?([A-D])\)?\**(?:[.):\s]|$)", r"(?:answer|정답|답)\s*(?:is|은|는|:)?\s*\**\(?([A-D])\b",
              r"\*\*\(?([A-D])\)?[.)]?\*\*", r"\b([A-D])\)\s"]


def extract_letter(text: str) -> str | None:
    t = strip_code(text).strip()
    for pat in LETTER_RES:
        m = re.search(pat, t, re.I | re.M)
        if m:
            return m.group(1).upper()
    return None


def score_b(q: dict, answer: str) -> dict:
    """Score one Track B answer in [0, 1] with the details that led to it."""
    kind = q["type"]
    if kind == "mcq":
        got = extract_letter(answer)
        return {"score": float(got == q["answer"]), "extracted": got}
    if kind == "gene":
        ok = any(re.search(rf"(?<![A-Za-z0-9]){re.escape(g)}(?![A-Za-z0-9])", answer) for g in q["genes"])
        return {"score": float(ok), "extracted": ok}
    det: dict = {}
    parts: list[float] = []
    if q.get("candidates"):  # grounded locus question: right candidate, no lipid gene from outside the list
        cand = any(re.search(rf"(?<![A-Za-z0-9]){re.escape(g)}(?![A-Za-z0-9])", answer) for g in q["candidates"])
        outside = sorted({g for g in q.get("not_in_list", [])
                          if re.search(rf"(?<![A-Za-z0-9]){re.escape(g)}(?![A-Za-z0-9])", answer)})
        det.update(candidate=cand, outside_genes=outside)
        parts += [float(cand), float(cand), float(not outside)]  # the right candidate counts double
    for i, alts in enumerate(q.get("require", [])):
        ok = any(re.search(p, answer, re.I | re.S) for p in alts)
        det[f"require_{i}"] = ok
        parts.append(float(ok))
    for i, p in enumerate(q.get("forbid", [])):
        bad = bool(re.search(p, answer, re.I | re.S))
        det[f"forbid_{i}"] = not bad
        parts.append(float(not bad))
    if q.get("check_grounding"):
        g = grounding(answer, q["prompt"])
        det["grounding"] = g
        parts.append(1.0 if g["ratio"] is None else float(g["ratio"] >= 0.85))
    if q.get("korean"):
        r = hangul_ratio(answer)
        det["hangul_ratio"] = round(r, 2)
        parts.append(float(r >= 0.25))
    return {"score": round(sum(parts) / len(parts), 3) if parts else 0.0, "extracted": det}
