"""Mean ± SD of benchmark scores over repeated runs.

    ./sam bench aggregate [--runs 2026-10-28,2026-10-28-hart,...] [--out repeats]

Reads output/bench/<run-id>/{run.json,env.json,models.json,*/result.json} and writes output/bench/<out>/SUMMARY.md and
aggregate.json. Without --runs it takes every run whose run.json has a repeat number; the runner calls it after each
model of such a run, so the summary follows the repeats as they progress. Scores are pooled over every run that has the
model; generation speed only over runs on the same GPU as the latest run (speed depends on the hardware, the scores
should not). SD is the sample SD (n - 1).
"""

from __future__ import annotations

import json
import statistics
import time
from pathlib import Path

HOME = Path(__file__).resolve().parents[1]
BENCH = HOME / "bench"


def _load(p: Path) -> dict:
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return {}


def stat(values: list[float]) -> dict:
    v = [x for x in values if x is not None]
    if not v:
        return {"n": 0, "mean": None, "sd": None}
    return {"n": len(v), "mean": statistics.fmean(v), "sd": statistics.stdev(v) if len(v) > 1 else None,
            "min": min(v), "max": max(v)}


def fmt(s: dict, nd: int = 2, show_n: bool = False) -> str:
    if not s or not s.get("n"):
        return "—"
    out = f"{s['mean']:.{nd}f}" + (f" ± {s['sd']:.{nd}f}" if s.get("sd") is not None else "")
    return out + (f" (n={s['n']})" if show_n else "")


def _gpu(env: dict) -> str:
    return ", ".join(g.get("name", "?") for g in env.get("gpus") or []) or "?"


def discover() -> list[str]:
    """Run IDs with a repeat number in run.json."""
    return sorted(p.parent.name for p in (HOME / "output" / "bench").glob("*/run.json") if _load(p).get("repeat"))


def _write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")  # runs finishing together must not leave a half-written file
    tmp.write_text(text)
    tmp.replace(path)


def collect(run_ids: list[str]) -> dict:
    runs, models = [], {}
    for rid in run_ids:
        rd = HOME / "output" / "bench" / rid
        if not rd.is_dir():
            raise SystemExit(f"no run folder {rd}")
        meta, env = _load(rd / "run.json"), _load(rd / "env.json")
        cfg = _load(rd / "models.json") or _load(BENCH / "models.json")
        done = {}
        for m in cfg.get("models", []):
            r = _load(rd / m["id"] / "result.json")
            if not r:
                continue
            ta, tb = r.get("track_a") or {}, r.get("track_b") or {}
            done[m["id"]] = {
                "a": ta.get("overall") if ta.get("eligible") else None,
                "a_scenarios": ta.get("by_scenario") or {} if ta.get("eligible") else {},
                "critical": ta.get("critical_fails"), "timeouts": ta.get("timeouts"),
                "b": tb.get("overall"), "b_categories": tb.get("by_category") or {},
                "tok_s": tb.get("tokens_per_s"), "error": r.get("error"),
            }
        runs.append({"run_id": rid, "repeat": meta.get("repeat"), "seed": meta.get("track_b_seed", 7),
                     "gpu": _gpu(env), "host": env.get("host"), "n_models": len(cfg.get("models", [])),
                     "results": done, "entries": {m["id"]: m for m in cfg.get("models", [])}})
    runs.sort(key=lambda r: (r["repeat"] is None, r["repeat"] or 0, r["run_id"]))
    for r in runs:  # model names and groups from the latest run that has the model
        models.update({mid: r["entries"][mid] for mid in r["results"]})
    for r in runs:
        del r["entries"]
    return {"runs": runs, "models": models}


def summarize(data: dict) -> dict:
    runs = data["runs"]
    speed_gpu = runs[-1]["gpu"] if runs else None
    out = {}
    for mid in data["models"]:
        per = [(r, r["results"][mid]) for r in runs if mid in r["results"]]
        scen = sorted({k for _, x in per for k in x["a_scenarios"]})
        cats = list(dict.fromkeys(k for _, x in per for k in x["b_categories"]))
        out[mid] = {
            "a": stat([x["a"] for _, x in per]), "b": stat([x["b"] for _, x in per]),
            "tok_s": stat([x["tok_s"] for r, x in per if r["gpu"] == speed_gpu]),
            "critical": sum(x["critical"] or 0 for _, x in per),
            "timeouts": sum(x["timeouts"] or 0 for _, x in per),
            "errors": [r["run_id"] for r, x in per if x["error"]],
            "a_scenarios": {k: stat([x["a_scenarios"].get(k) for _, x in per]) for k in scen},
            "b_categories": {k: stat([x["b_categories"].get(k) for _, x in per]) for k in cats},
            "per_run": {r["run_id"]: {"a": x["a"], "b": x["b"]} for r, x in per},
        }
    return {"speed_gpu": speed_gpu, "models": out}


GROUPS = {"large": "40B 이상", "quant": "양자화 비교", "base": "기존", "template": "템플릿 수정"}


def _name(m: dict) -> str:
    return f"{m.get('family', m['id'])} {m.get('size', '')}".strip()


def write(run_ids: list[str], out: Path) -> Path:
    data = collect(run_ids)
    summ = summarize(data)
    out.mkdir(parents=True, exist_ok=True)
    _write(out / "aggregate.json", json.dumps({"runs": [{k: v for k, v in r.items() if k != "results"}
                                                        for r in data["runs"]], **summ}, ensure_ascii=False, indent=1))
    models, ms = data["models"], summ["models"]
    order = sorted(ms, key=lambda k: (ms[k]["a"]["n"] == 0, -(ms[k]["a"]["mean"] or 0), -(ms[k]["b"]["mean"] or 0)))
    lines = ["# SAM 로컬 LLM 벤치마크 — 반복 실행 종합 (mean ± SD)", "",
             f"> 갱신 {time.strftime('%Y-%m-%d %H:%M')} · `./sam bench aggregate`로 다시 만들 수 있습니다.",
             "> 값은 회차 평균 ± 표본 표준편차(n − 1). 회차가 1개뿐이면 SD 없이 값만 적습니다.",
             "> 각 회차의 모델별 보고서는 `output/bench/<실행 ID>/reports/`에 있습니다.", "", "## 회차", "",
             "| 회차 | 실행 ID | GPU | Track B seed | 완료 모델 |", "|---|---|---|---|---|"]
    for r in data["runs"]:
        lines.append(f"| {r['repeat'] or '—'} | `{r['run_id']}` | {r['gpu']} | {r['seed']} | "
                     f"{len(r['results'])}/{r['n_models']} |")
    lines += ["", "## 전체", "",
              f"생성 속도는 최근 회차와 같은 GPU({summ['speed_gpu']})의 회차만 평균합니다.", "",
              "| 모델 | 구분 | 회차 수 | Track A | 치명 실패(합) | 시간 초과(합) | Track B | tok/s |",
              "|---|---|---|---|---|---|---|---|"]
    for mid in order:
        s, m = ms[mid], models[mid]
        n = max(s["a"]["n"], s["b"]["n"])
        err = f" ⚠오류 {len(s['errors'])}회" if s["errors"] else ""
        lines.append(f"| {_name(m)} | {GROUPS.get(m.get('group'), '—')} | {n}{err} | {fmt(s['a'])} | {s['critical']} | "
                     f"{s['timeouts']} | {fmt(s['b'])} | {fmt(s['tok_s'], 1)} |")
    cats = list(dict.fromkeys(c for s in ms.values() for c in s["b_categories"]))
    lines += ["", "## Track B 범주", "", "| 모델 | " + " | ".join(cats) + " |", "|---" * (len(cats) + 1) + "|"]
    for mid in order:
        bc = ms[mid]["b_categories"]
        lines.append(f"| {_name(models[mid])} | " + " | ".join(fmt(bc.get(c, {})) for c in cats) + " |")
    scen = sorted({k for s in ms.values() for k in s["a_scenarios"]})
    lines += ["", "## Track A 시나리오", "", "| 모델 | " + " | ".join(scen) + " |", "|---" * (len(scen) + 1) + "|"]
    for mid in order:
        if ms[mid]["a"]["n"]:
            sc = ms[mid]["a_scenarios"]
            lines.append(f"| {_name(models[mid])} | " + " | ".join(fmt(sc.get(k, {})) for k in scen) + " |")
    ids = [r["run_id"] for r in data["runs"]]
    lines += ["", "## 회차별 값 (Track A / Track B)", "", "| 모델 | " + " | ".join(f"`{i}`" for i in ids) + " |",
              "|---" * (len(ids) + 1) + "|"]
    for mid in order:
        pr = ms[mid]["per_run"]
        cells = [(f"{pr[i]['a']:.2f}" if pr[i]["a"] is not None else "—") + " / " +
                 (f"{pr[i]['b']:.2f}" if pr[i]["b"] is not None else "—") if i in pr else "" for i in ids]
        lines.append(f"| {_name(models[mid])} | " + " | ".join(cells) + " |")
    _write(out / "SUMMARY.md", "\n".join(lines) + "\n")
    return out / "SUMMARY.md"
