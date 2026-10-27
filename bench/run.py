"""SAM local-LLM benchmark runner.

    ./sam bench run    [--run-id ID] [--models a,b] [--tracks A,B] [--repeats N] [--scenarios A1,A2]
    ./sam bench report [--run-id ID]          re-render reports from saved results
    ./sam bench rescore [--run-id ID]         recompute scores from saved answers/events, then report

Models are processed one at a time in bench/models.json order; a model on the benchmark Ollama
server is started once its download finished (.sam/bench/pulled/<tag>). For each model:
Track B (knowledge and interpretation, no tools) then Track A (the model drives the real harness
through pi). Right after a model finishes, reports/<model>.md is written and reports/SUMMARY.md
is refreshed, so nobody has to wait for the whole benchmark.

Everything is written under output/bench/<run-id>/ (input and resource stay read-only).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import requests

BENCH = Path(__file__).resolve().parent
HOME = BENCH.parent
sys.path.insert(0, str(BENCH))
import report  # noqa: E402
import score  # noqa: E402

PULLED = HOME / ".sam" / "bench" / "pulled"
HF_PY = BENCH / "hf" / ".pixi" / "envs" / "default" / "bin" / "python"


def load(name: str) -> dict:
    return json.loads((BENCH / name).read_text())


def log(msg: str) -> None:
    print(f"[{time.strftime('%m-%d %H:%M:%S')}] {msg}", flush=True)


# ── Ollama ──────────────────────────────────────────────────────────────────
def api(url: str, path: str, payload: dict | None = None, timeout: float = 600) -> dict:
    r = (requests.post(f"{url}{path}", json=payload, timeout=timeout) if payload is not None
         else requests.get(f"{url}{path}", timeout=timeout))
    r.raise_for_status()
    return r.json() if r.content else {}


def marker(tag: str) -> Path:
    return PULLED / tag.replace("/", "_").replace(":", "_")


def downloads_finished() -> bool:
    f = HOME / ".sam" / "bench" / "pull.log"
    return f.exists() and "all downloads finished" in f.read_text(errors="replace")


def wait_until_ready(m: dict) -> None:
    """Block until the model's download finished; give up if the download queue ended without it."""
    if m.get("runner") == "hf":
        ready = lambda: marker("biogpt-large").exists() and HF_PY.exists()  # noqa: E731
    elif m["server"] == "bench":
        ready = lambda: marker(m["tag"]).exists()  # noqa: E731
    else:
        return
    while not ready():
        if downloads_finished():
            raise RuntimeError("download queue finished without this model (see .sam/bench/pull.log)")
        time.sleep(60)


MISTRAL_INST = ('{{- range .Messages }}{{- if eq .Role "user" }}[INST] {{ .Content }} [/INST]'
                '{{- else if eq .Role "assistant" }} {{ .Content }}</s>{{- end }}{{- end }}')


def make_variant(m: dict, cfg: dict) -> dict:
    """bench-<id>: the model with the benchmark's context length and output limit."""
    url = cfg["servers"][m["server"]]["url"]
    base = api(url, "/api/show", {"model": m["tag"]})
    ctx = min(m.get("num_ctx", cfg["num_ctx"]), cfg["num_ctx"])
    payload = {"model": f"bench-{m['id']}", "from": m["tag"], "stream": False,
               "parameters": {"num_ctx": ctx, "num_predict": cfg["num_predict"]}}
    tmpl = base.get("template") or ""
    if m.get("template") == "mistral-inst" and "[INST]" not in tmpl:
        payload["template"] = MISTRAL_INST
    api(url, "/api/create", payload, timeout=1800)
    info = api(url, "/api/show", {"model": payload["model"]})
    det = info.get("details") or {}
    return {"variant": payload["model"], "url": url, "num_ctx": ctx, "capabilities": info.get("capabilities") or [],
            "quantization": det.get("quantization_level"), "parameter_size": det.get("parameter_size"),
            "template_overridden": "template" in payload, "ollama_version": api(url, "/api/version").get("version")}


def unload(url: str, name: str) -> None:
    try:
        api(url, "/api/generate", {"model": name, "keep_alive": 0}, timeout=120)
    except requests.RequestException:
        pass


def loaded_models(cfg: dict) -> list[str]:
    out = []
    for s in cfg["servers"].values():
        try:
            out += [f"{s['url']}:{x['name']}" for x in api(s["url"], "/api/ps").get("models", [])]
        except requests.RequestException:
            pass
    return out


# ── Track B ─────────────────────────────────────────────────────────────────
def b_prompt(q: dict, qs: dict) -> str:
    pre = qs["preamble_ko"] if q.get("korean") else qs["preamble"]
    if q["type"] == "mcq":
        opts = "\n".join(f"{k}) {v}" for k, v in q["options"].items())
        return f"{pre}\n\n{qs['mcq_instruction']}\n\nQuestion: {q['prompt']}\n{opts}"
    return f"{pre}\n\n{q['prompt']}"


def track_b_ollama(m: dict, var: dict, qs: dict, out: Path) -> list[dict]:
    done = {}
    f = out / "answers.jsonl"
    if f.exists():
        done = {r["id"]: r for r in map(json.loads, f.read_text().splitlines())}
    with open(f, "a") as fh:
        for q in qs["questions"]:
            if q["id"] in done:
                continue
            prompt = b_prompt(q, qs)
            t0 = time.time()
            rec = {"id": q["id"]}
            try:
                r = api(var["url"], "/api/chat", {
                    "model": var["variant"], "stream": False, "keep_alive": "30m",
                    "messages": [{"role": "user", "content": prompt}],
                    "options": {"seed": 7, "num_predict": qs["num_predict"]}}, timeout=900)
                msg = r.get("message") or {}
                rec.update(answer=msg.get("content", ""), thinking_chars=len(msg.get("thinking") or ""),
                           eval_count=r.get("eval_count"), eval_s=(r.get("eval_duration") or 0) / 1e9,
                           prompt_tokens=r.get("prompt_eval_count"), done_reason=r.get("done_reason"))
            except requests.RequestException as exc:
                rec.update(answer="", error=f"{exc.__class__.__name__}: {str(exc)[:200]}")
            rec["seconds"] = round(time.time() - t0, 1)
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            done[q["id"]] = rec
    return [done[q["id"]] for q in qs["questions"]]


def track_b_hf(m: dict, qs: dict, out: Path) -> list[dict]:
    f = out / "answers.jsonl"
    if not f.exists():
        items = [{"id": q["id"], "type": q["type"], "prompt": b_prompt(q, qs),
                  "options": q.get("options"), "question": q["prompt"]} for q in qs["questions"]]
        (out / "hf_items.json").write_text(json.dumps(items, ensure_ascii=False))
        subprocess.run([str(HF_PY), "-I", str(BENCH / "biogpt.py"), str(HOME / m["path"]), str(out / "hf_items.json"),
                        str(f)], check=True, cwd=out)
    done = {r["id"]: r for r in map(json.loads, f.read_text().splitlines())}
    return [done.get(q["id"], {"id": q["id"], "answer": "", "error": "missing"}) for q in qs["questions"]]


def score_track_b(qs: dict, answers: list[dict]) -> dict:
    items = []
    for q, a in zip(qs["questions"], answers):
        s = score.score_b(q, a.get("answer", ""))
        item = {"id": q["id"], "category": q["category"], "type": q["type"], "score": s["score"],
                "extracted": s["extracted"], "seconds": a.get("seconds"), "error": a.get("error"),
                "done_reason": a.get("done_reason"), "answer": a.get("answer", "")}
        if q["type"] == "mcq" and a.get("loglik_choice"):
            item["loglik_choice"] = a["loglik_choice"]
            item["loglik_ok"] = a["loglik_choice"] == q["answer"]
        items.append(item)
    cats: dict[str, list[float]] = {}
    for it in items:
        cats.setdefault(it["category"], []).append(it["score"])
    by_cat = {c: round(sum(v) / len(v), 3) for c, v in cats.items()}
    toks = [(a.get("eval_count") or 0, a.get("eval_s") or 0) for a in answers]
    n_tok, secs = sum(t for t, _ in toks), sum(s for _, s in toks)
    res = {"items": items, "by_category": by_cat,
           "overall": round(sum(by_cat.values()) / len(by_cat), 3) if by_cat else 0.0,
           "tokens_per_s": round(n_tok / secs, 1) if secs else None,
           "seconds": round(sum(a.get("seconds") or 0 for a in answers), 1),
           "errors": sum(1 for a in answers if a.get("error"))}
    ll = [it["loglik_ok"] for it in items if "loglik_ok" in it]
    if ll:
        res["mcq_loglik_accuracy"] = round(sum(ll) / len(ll), 3)
    return res


# ── Track A ─────────────────────────────────────────────────────────────────
def input_snapshot(d: Path) -> list:
    return sorted((str(p.relative_to(d)), p.stat().st_size, p.stat().st_mtime_ns) for p in d.rglob("*")) + \
        [("<dir>", d.stat().st_mtime_ns)]


def descendants(pid: int) -> list[int]:
    kids: dict[int, list[int]] = {}
    for st in Path("/proc").glob("[0-9]*/stat"):
        try:
            parts = st.read_text().rsplit(")", 1)[1].split()
            kids.setdefault(int(parts[1]), []).append(int(st.parent.name))
        except (OSError, IndexError, ValueError):
            pass
    out, todo = [], [pid]
    while todo:
        p = todo.pop()
        for c in kids.get(p, []):
            out.append(c)
            todo.append(c)
    return out


def kill_tree(pid: int) -> None:
    """pi and the analysis processes it started (runner.ts puts each in its own process group)."""
    procs = [pid, *descendants(pid)]
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for p in procs:
            try:
                os.killpg(os.getpgid(p), sig)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                os.kill(p, sig)
            except (ProcessLookupError, PermissionError):
                pass
        time.sleep(5)


def seed(ref: Path, out: Path, spec: dict) -> None:
    """Start state of a scenario: copy parts of the reference output and its provenance records."""
    out.mkdir(parents=True, exist_ok=True)
    for rel in spec["paths"]:
        src, dst = ref / rel, out / rel
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        elif src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    man = ref / "manifest.jsonl"
    if man.exists() and spec["steps"]:
        keep = [line for line in man.read_text().splitlines() if json.loads(line).get("step") in spec["steps"]]
        (out / "manifest.jsonl").write_text("\n".join(keep) + "\n")


def write_pi_models(rundir: Path, cfg: dict, variants: dict) -> Path:
    agent_dir = rundir / "pi-agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    providers = {}
    for name, s in cfg["servers"].items():
        models = [{"id": v["variant"], "name": v["variant"], "reasoning": "thinking" in v["capabilities"],
                   "input": ["text"], "contextWindow": v["num_ctx"], "maxTokens": cfg["num_predict"],
                   "compat": {"maxTokensField": "max_tokens"}}
                  for v in variants.values() if v.get("url") == s["url"]]
        if models:
            providers[f"bench-{name}"] = {"baseUrl": f"{s['url']}/v1", "api": "openai-completions",
                                          "apiKey": "ollama", "models": models}
    (agent_dir / "models.json").write_text(json.dumps({"providers": providers}, indent=2))
    return agent_dir


def cleanup(out: Path) -> None:
    """Keep summaries, logs and plots of a scenario run; drop large result tables and caches."""
    for sub in ("_cache", "_tmp"):
        shutil.rmtree(out / sub, ignore_errors=True)
    for p in out.rglob("*"):
        if p.is_file() and p.stat().st_size > 5_000_000:
            p.unlink()


def redact(text: str, iids: set[str]) -> tuple[str, int]:
    n = 0

    def sub(mo):
        nonlocal n
        if mo.group(0) in iids:
            n += 1
            return "[IID]"
        return mo.group(0)
    return re.sub(r"[A-Za-z0-9]{6,}", sub, text), n


def run_scenario(m: dict, var: dict, sc: dict, rep: int, rundir: Path, ctx: dict) -> dict:
    d = rundir / m["id"] / "A" / f"{sc['id']}-r{rep}"
    if (d / "result.json").exists():
        return json.loads((d / "result.json").read_text())
    shutil.rmtree(d, ignore_errors=True)
    out = d / "output"
    seed(ctx["reference"], out, ctx["seeds"][sc["seed"]])
    before = input_snapshot(ctx["input"])
    provider = f"bench-{m['server']}"
    cmd = [str(HOME / "sam"), "agent", "--input", str(ctx["input"]), "--resource", str(ctx["resource"]),
           "--output", str(out), "--privacy", sc.get("privacy", "auto"), "--approvals", "deny", "--threads", "16",
           "--", "--model", f"{provider}/{var['variant']}", "--mode", "json", "-p", sc["prompt"]]
    env = {**os.environ, "SAM_PI_AGENT_DIR": str(ctx["agent_dir"])}
    t0 = time.time()
    timed_out = False
    with open(d / "events.jsonl", "w") as ev, open(d / "stderr.log", "w") as er:
        p = subprocess.Popen(cmd, cwd=d, stdin=subprocess.DEVNULL, stdout=ev, stderr=er, env=env,
                             start_new_session=True)
        try:
            p.wait(timeout=sc.get("timeout", ctx["timeout"]))
        except subprocess.TimeoutExpired:
            timed_out = True
            kill_tree(p.pid)
            p.wait()
    seconds = round(time.time() - t0, 1)
    run = score.parse_events(d / "events.jsonl")
    run["timed_out"] = timed_out
    run["input_changed"] = input_snapshot(ctx["input"]) != before
    final, leaks = redact(run["final"], ctx["iids"])
    run["iid_leaks"] = leaks
    source = sc["prompt"] + "\n" + "\n".join(c["text"] for c in run["calls"])
    run["grounding"] = score.grounding(run["final"], source)
    sc_res = score.score_a(sc, run, ctx)
    res = {"scenario": sc["id"], "rep": rep, "seconds": seconds, "timed_out": timed_out,
           "score": sc_res["score"], "checks": sc_res["checks"], "critical_fail": sc_res["critical_fail"],
           "tools": [{"name": c["name"], "args": c["args"], "error": c["error"], "blocked": c.get("blocked", False)}
                     for c in run["calls"]],
           "usage": run["usage"], "turns": run["turns"], "errors": run["errors"], "grounding": run["grounding"],
           "hangul_ratio": round(score.hangul_ratio(run["final"]), 2), "iid_leaks": leaks,
           "input_changed": run["input_changed"], "final": final, "exit_code": p.returncode}
    # the transcript may hold individual-level data the local model read; keep it out of reports
    (d / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    cleanup(out)
    return res


def track_a(m: dict, var: dict, scen: dict, rundir: Path, ctx: dict, only: set[str] | None, repeats: int | None):
    if "tools" not in var["capabilities"]:
        # confirm once that the model really cannot drive the harness (Ollama rejects tool definitions)
        probe = run_scenario(m, var, {**scen["scenarios"][0], "timeout": 300}, 0, rundir, ctx)
        return {"eligible": False, "reason": "Ollama reports no tool-calling capability for this model",
                "probe": {k: probe[k] for k in ("seconds", "errors", "final", "tools")}}
    runs = []
    for sc in scen["scenarios"]:
        if only and sc["id"] not in only:
            continue
        for rep in range(1, (repeats or sc.get("repeats", scen["repeats"])) + 1):
            log(f"  {m['id']} {sc['id']} r{rep}")
            runs.append(run_scenario(m, var, sc, rep, rundir, ctx))
            log(f"    score {runs[-1]['score']} ({runs[-1]['seconds']} s)")
    per: dict[str, list[dict]] = {}
    for r in runs:
        per.setdefault(r["scenario"], []).append(r)
    by_sc = {k: round(sum(r["score"] for r in v) / len(v), 3) for k, v in per.items()}
    return {"eligible": True, "runs": runs, "by_scenario": by_sc,
            "overall": round(sum(by_sc.values()) / len(by_sc), 3) if by_sc else 0.0,
            "critical_fails": sum(len(r["critical_fail"]) for r in runs),
            "timeouts": sum(r["timed_out"] for r in runs),
            "seconds": round(sum(r["seconds"] for r in runs), 1)}


# ── main ────────────────────────────────────────────────────────────────────
def context(rundir: Path, args) -> dict:
    sam = json.loads((Path(args.reference) / "sam.json").read_text())
    inp, res = Path(sam["input"]), Path(sam["resource"])
    fam = next(inp.glob("*.fam"))
    iids = {line.split()[1] for line in fam.read_text().splitlines() if line.strip()}
    scen = load("scenarios.json")
    return {"reference": Path(args.reference), "input": inp, "resource": res, "iids": iids,
            "seeds": scen["seeds"], "timeout": scen["timeout"], "agent_dir": rundir / "pi-agent"}


def cmd_run(args) -> int:
    cfg, scen, qs = load("models.json"), load("scenarios.json"), load("questions.json")
    rundir = HOME / "output" / "bench" / args.run_id
    (rundir / "reports").mkdir(parents=True, exist_ok=True)
    ctx = context(rundir, args)
    tracks = set(args.tracks.split(","))
    only_models = set(args.models.split(",")) if args.models else None
    only_sc = set(args.scenarios.split(",")) if args.scenarios else None
    variants: dict[str, dict] = {}
    vfile = rundir / "variants.json"
    if vfile.exists():
        variants = json.loads(vfile.read_text())
    for m in cfg["models"]:
        if only_models and m["id"] not in only_models:
            continue
        mdir = rundir / m["id"]
        if (mdir / "result.json").exists() and not args.force:
            log(f"{m['id']}: done earlier")
            continue
        log(f"{m['id']}: waiting for download")
        wait_until_ready(m)
        mdir.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        result: dict = {"model": m, "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
        try:
            if m.get("runner") == "hf":
                var = {"variant": m["id"], "capabilities": ["completion"], "num_ctx": m.get("num_ctx")}
            else:
                var = make_variant(m, cfg)
                variants[m["id"]] = var
                vfile.write_text(json.dumps(variants, indent=1))
                write_pi_models(rundir, cfg, variants)
            result["variant"] = var
            result["gpu_loaded_before"] = loaded_models(cfg)
            if "B" in tracks:
                log(f"{m['id']}: track B")
                (mdir / "B").mkdir(exist_ok=True)
                ans = (track_b_hf(m, qs, mdir / "B") if m.get("runner") == "hf"
                       else track_b_ollama(m, var, qs, mdir / "B"))
                result["track_b"] = score_track_b(qs, ans)
            if "A" in tracks:
                log(f"{m['id']}: track A")
                if m.get("runner") == "hf":
                    result["track_a"] = {"eligible": False, "reason": "not a chat/tool-calling model (transformers "
                                                                      "causal LM without chat template)"}
                else:
                    result["track_a"] = track_a(m, var, scen, rundir, ctx, only_sc, args.repeats)
        except Exception as exc:  # record and continue with the next model
            result["error"] = f"{exc.__class__.__name__}: {exc}"
            log(f"{m['id']}: ERROR {result['error']}")
        finally:
            if m.get("runner") != "hf" and m["id"] in variants:
                unload(variants[m["id"]]["url"], variants[m["id"]]["variant"])
        result["finished"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        result["minutes"] = round((time.time() - t0) / 60, 1)
        (mdir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=1))
        report.write_model_report(rundir, result)
        report.write_summary(rundir, cfg)
        log(f"{m['id']}: report written ({result['minutes']} min)")
    report.write_summary(rundir, cfg)
    log("all models done")
    return 0


def rescore_a(m: dict, ta: dict, scen: dict, rundir: Path, ctx: dict) -> dict:
    """Re-score Track A runs from their saved events (run-time facts such as input changes are kept)."""
    if not ta.get("eligible"):
        return ta
    by_id = {s["id"]: s for s in scen["scenarios"]}
    runs = []
    for old in ta["runs"]:
        d = rundir / m["id"] / "A" / f"{old['scenario']}-r{old['rep']}"
        run = score.parse_events(d / "events.jsonl")
        run.update(timed_out=old["timed_out"], input_changed=old["input_changed"])
        final, leaks = redact(run["final"], ctx["iids"])
        run["iid_leaks"] = leaks
        sc = by_id[old["scenario"]]
        source = sc["prompt"] + "\n" + "\n".join(c["text"] for c in run["calls"])
        run["grounding"] = score.grounding(run["final"], source)
        s = score.score_a(sc, run, ctx)
        new = {**old, "score": s["score"], "checks": s["checks"], "critical_fail": s["critical_fail"],
               "grounding": run["grounding"], "hangul_ratio": round(score.hangul_ratio(run["final"]), 2),
               "iid_leaks": leaks, "final": final}
        (d / "result.json").write_text(json.dumps(new, ensure_ascii=False, indent=1))
        runs.append(new)
    per: dict[str, list[dict]] = {}
    for r in runs:
        per.setdefault(r["scenario"], []).append(r)
    by_sc = {k: round(sum(r["score"] for r in v) / len(v), 3) for k, v in per.items()}
    return {**ta, "runs": runs, "by_scenario": by_sc,
            "overall": round(sum(by_sc.values()) / len(by_sc), 3) if by_sc else 0.0,
            "critical_fails": sum(len(r["critical_fail"]) for r in runs)}


def cmd_rescore(args) -> int:
    """Recompute all scores from saved answers and events (after a scoring fix), then re-render reports."""
    scen, qs = load("scenarios.json"), load("questions.json")
    rundir = HOME / "output" / "bench" / args.run_id
    ctx = context(rundir, args)
    for f in sorted(rundir.glob("*/result.json")):
        res = json.loads(f.read_text())
        mdir = f.parent
        if res.get("track_b") and (mdir / "B" / "answers.jsonl").exists():
            done = {r["id"]: r for r in map(json.loads, (mdir / "B" / "answers.jsonl").read_text().splitlines())}
            res["track_b"] = score_track_b(qs, [done.get(q["id"], {"id": q["id"], "answer": "", "error": "missing"})
                                               for q in qs["questions"]])
        if res.get("track_a"):
            res["track_a"] = rescore_a(res["model"], res["track_a"], scen, rundir, ctx)
        f.write_text(json.dumps(res, ensure_ascii=False, indent=1))
        log(f"{res['model']['id']}: rescored")
    return cmd_report(args)


def cmd_report(args) -> int:
    cfg = load("models.json")
    rundir = HOME / "output" / "bench" / args.run_id
    for f in sorted(rundir.glob("*/result.json")):
        report.write_model_report(rundir, json.loads(f.read_text()))
    report.write_summary(rundir, cfg)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(prog="sam bench")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("run", "report", "rescore"):
        s = sub.add_parser(name)
        s.add_argument("--run-id", default="2026-10-28")
        if name == "rescore":
            s.add_argument("--reference", default=str(HOME / "output" / "bench" / "reference" / "output"))
        if name == "run":
            s.add_argument("--models")
            s.add_argument("--tracks", default="B,A")
            s.add_argument("--scenarios")
            s.add_argument("--repeats", type=int)
            s.add_argument("--force", action="store_true")
            s.add_argument("--reference", default=str(HOME / "output" / "bench" / "reference" / "output"))
    a = p.parse_args()
    return {"run": cmd_run, "report": cmd_report, "rescore": cmd_rescore}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
