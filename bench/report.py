"""Reports for the SAM local-LLM benchmark: one per model (as soon as it finishes) and a summary.

Templates: bench/templates/model_report.md and common.md (data + experiment design, shared by all
model reports). Values come from the reference run, scenarios.json, questions.json, each model's
result.json, and the run's own copies of models.json and env.json (machine and software).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

BENCH = Path(__file__).resolve().parent
TPL = BENCH / "templates"


def _load(p: Path) -> dict:
    return json.loads(p.read_text()) if p.exists() else {}


def _fill(text: str, values: dict) -> str:
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", str(v))
    return text


def _f(x, nd=3, dash="—"):
    if x is None:
        return dash
    return f"{x:.{nd}f}" if isinstance(x, float) else str(x)


def _pct(x):
    return "—" if x is None else f"{100 * x:.0f}%"


def model_name(m: dict) -> str:
    return f"{m['family']} {m['size']}"


def run_config(rundir: Path) -> dict:
    """Model list of the run (copied into the run folder when it started), else the current one."""
    return _load(rundir / "models.json") or _load(BENCH / "models.json")


def _env_rows(env: dict, variants: dict, cfg: dict) -> dict:
    gpus = ", ".join(f"{g['name']} {g['memory_gb']} GB" for g in env.get("gpus") or []) or "—"
    hw = f"{gpus}, {env.get('cpu_cores', '—')} CPU 코어, RAM {env.get('ram_gb', '—')} GB"
    if env.get("host"):
        hw += f" (`{env['host']}`, 커널 {env.get('kernel', '—')})"
    if env.get("note"):
        hw += f". {env['note']}"
    ver = sorted({v.get("ollama_version") for v in variants.values() if v.get("ollama_version")})
    ver = ver or sorted({v for v in (env.get("ollama") or {}).values() if v}) or ["—"]
    used = {v.get("url") for v in variants.values()}
    label = {"system": "시스템 서비스", "bench": "벤치마크 전용, 저장소 `.sam/ollama/models`"}
    servers = [f"{s['url'].rsplit(':', 1)[1]}({label.get(name, name)})"
               for name, s in cfg.get("servers", {}).items() if s["url"] in used or not used]
    if env.get("read_only_note"):
        ro = env["read_only_note"]
    elif env.get("landlock_abi") and env.get("sandbox", "on") != "off":
        ro = (f"입력·리소스는 커널(Linux Landlock ABI {env['landlock_abi']}) 수준 읽기 전용이고, 명령 패턴 가드가 먼저 "
              "거절·설명함. 모델의 쓰기 시도는 막혀도 `no_input_write`로 감점")
    else:
        ro = "입력 읽기 전용을 명령 패턴 가드로만 지킴(커널 보호 없음)"
    return {"HARDWARE": hw, "OLLAMA_VERSION": ", ".join(ver), "SERVERS": ", ".join(servers) or "—",
            "PI_VERSION": env.get("pi") or "—", "READ_ONLY": ro,
            "SCOPE": cfg.get("scope") or "—"}


def _run_rows(meta: dict) -> dict:
    """Repeat number and Track B seed (run.json; runs before repeats were introduced used seed 7)."""
    return {"REPEAT": f" (반복 {meta['repeat']}회차)" if meta.get("repeat") else "",
            "TRACK_B_SEED": meta.get("track_b_seed", 7)}


# ── reference values ────────────────────────────────────────────────────────
def reference(rundir: Path) -> dict:
    ref = rundir.parent / "reference" / "output"
    g = _load(ref / "gwas" / "HDL" / "summary.json").get("summary", {})
    ld = _load(ref / "ldsc" / "HDL" / "summary.json").get("summary", {})
    st = _load(rundir.parent / "reference" / "json" / "status.json")
    geno = ((st.get("input") or {}).get("genotypes") or [{}])[0]
    fm = {}
    for f in sorted((ref / "loci" / "HDL").glob("*/susie_summary.json")):
        fm = _load(f).get("summary", {})
        fm["_locus"] = f.parent.name
    prs = _load(ref / "prs" / "HTN_PRS_weight" / "summary.json").get("summary", {})
    return {"lambda": g.get("lambda_gc"), "n_sig": g.get("n_genome_wide_significant"),
            "n_loci": g.get("n_independent_loci_500kb"), "h2": ld.get("h2_observed"), "h2_se": ld.get("h2_observed_se"),
            "intercept": ld.get("intercept"), "n_cs": fm.get("n_credible_sets"),
            "locus2": fm.get("_locus"), "prs_match": (prs.get("matching") or {}).get("match_rate"),
            "n_samples": geno.get("samples"), "n_variants": geno.get("variants")}


def common_section(rundir: Path, cfg: dict) -> str:
    scen = _load(BENCH / "scenarios.json")
    qs = _load(BENCH / "questions.json")
    r = reference(rundir)
    variants = _load(rundir / "variants.json")
    rows = ["| ID | 요청(요약) | 시작 상태 | 반복 | 확인 항목 |", "|---|---|---|---|---|"]
    for s in scen.get("scenarios", []):
        rows.append(f"| {s['id']} | {s['title']} | {scen['seed_labels'][s['seed']]} | "
                    f"{s.get('repeats', scen['repeats'])} | {', '.join(c['label'] for c in s['checks'])} |")
    cats: dict[str, int] = {}
    for q in qs.get("questions", []):
        cats[q["category"]] = cats.get(q["category"], 0) + 1
    qrows = ["| 범주 | 문항 | 내용 |", "|---|---|---|"]
    for c, n in cats.items():
        qrows.append(f"| {c} | {n} | {qs['category_labels'].get(c, '')} |")
    z = r["h2"] / r["h2_se"] if r.get("h2") and r.get("h2_se") else None
    vals = {"N_SAMPLES": f"{r['n_samples']:,}" if r.get("n_samples") else "—",
            "N_VARIANTS": f"{r['n_variants']:,}" if r.get("n_variants") else "—",
            "REF_DIR": "`output/bench/reference`", "LAMBDA": _f(r["lambda"], 4), "N_SIG": _f(r["n_sig"]),
            "N_LOCI": _f(r["n_loci"]), "H2": _f(r["h2"], 4), "H2_SE": _f(r["h2_se"], 4), "H2_Z": _f(z, 2),
            "INTERCEPT": _f(r["intercept"], 4), "LOCUS2": r.get("locus2") or "—", "N_CS": _f(r["n_cs"]),
            "PRS_MATCH": _pct(r["prs_match"]) if isinstance(r.get("prs_match"), float) else _f(r.get("prs_match")),
            "N_QUESTIONS": len(qs.get("questions", [])), "SCENARIO_TABLE": "\n".join(rows),
            "QUESTION_TABLE": "\n".join(qrows), "NUM_CTX": cfg["num_ctx"],
            "NUM_PREDICT": cfg["num_predict"], "TIMEOUT": scen.get("timeout"), "RUN_ID": rundir.name,
            **_run_rows(_load(rundir / "run.json")), **_env_rows(_load(rundir / "env.json"), variants, cfg)}
    return _fill((TPL / "common.md").read_text(), vals)


# ── per-model report ────────────────────────────────────────────────────────
def _tools_str(tools: list[dict]) -> str:
    out = []
    for t in tools:
        mark = "⛔" if t.get("blocked") else ("✗" if t.get("error") else "")
        out.append(f"{t['name']}{mark}")
    return " → ".join(out) or "(없음)"


def _excerpt(text: str, n: int) -> str:
    t = (text or "").strip()
    if not t:
        return "> (답변 없음)"
    t = t if len(t) <= n else t[:n] + " …"
    return "\n".join("> " + line for line in t.splitlines())


def track_a_md(ta: dict | None) -> tuple[str, list[str]]:
    obs: list[str] = []
    if not ta:
        return "실행하지 않음.", obs
    if not ta.get("eligible"):
        probe = ta.get("probe") or {}
        err = "; ".join(probe.get("errors") or []) or (probe.get("final") or "")[:200]
        obs.append(f"하네스를 운용할 수 없음: {ta.get('reason')}.")
        return (f"**해당 없음** — {ta.get('reason')}.\n\n" +
                (f"확인 실행(A1) 결과: `{err[:300]}`" if err else "")), obs
    rows = ["| 시나리오 | 반복 | 점수 | 시간(s) | 도구 호출 (✗ 오류, ⛔ 가드 차단) | 턴 | 토큰 in/out | "
            "수치 근거율 | 한글 비율 | 실패 항목 |", "|---|---|---|---|---|---|---|---|---|---|"]
    fails: dict[str, int] = {}
    for r in ta["runs"]:
        failed = [c["label"] for c in r["checks"] if not c["ok"]]
        for f in failed:
            fails[f] = fails.get(f, 0) + 1
        g = r.get("grounding") or {}
        rows.append(f"| {r['scenario']} | {r['rep']} | {r['score']:.2f} | {r['seconds']:.0f}"
                    f"{' ⏱' if r['timed_out'] else ''} | {_tools_str(r['tools'])} | {r['turns']} | "
                    f"{r['usage']['input']:,}/{r['usage']['output']:,} | {_f(g.get('ratio'), 2)} | "
                    f"{r['hangul_ratio']:.2f} | {'; '.join(failed) or '—'} |")
    parts = [f"**전체 {ta['overall']:.2f}** (시나리오 평균) · 치명 항목 실패 {ta['critical_fails']}건 · "
             f"시간 초과 {ta['timeouts']}건 · 총 {ta['seconds'] / 60:.0f}분", "", "\n".join(rows), "",
             "### 시나리오별 최종 답변 (첫 반복, 앞부분)", ""]
    seen = set()
    for r in ta["runs"]:
        if r["scenario"] in seen:
            continue
        seen.add(r["scenario"])
        parts += [f"**{r['scenario']}** — 점수 {r['score']:.2f}", "", _excerpt(r["final"], 900), ""]
    if ta["critical_fails"]:
        obs.append(f"**치명 항목 실패 {ta['critical_fails']}건** (입력 변경 또는 개인 ID 노출). 세부는 5절 표.")
    if fails:
        top = sorted(fails.items(), key=lambda x: -x[1])[:5]
        obs.append("자주 실패한 확인 항목: " + ", ".join(f"{k} ({v}회)" for k, v in top) + ".")
    gr = [r["grounding"]["ratio"] for r in ta["runs"] if r.get("grounding", {}).get("ratio") is not None]
    if gr:
        obs.append(f"답변 수치 근거율 평균 {sum(gr) / len(gr):.2f} (1에 가까울수록 도구 결과에 있는 수치만 씀).")
    if ta["timeouts"]:
        obs.append(f"시간 초과 {ta['timeouts']}건.")
    errs = sorted({e for r in ta["runs"] for e in r.get("errors", [])})
    if errs:
        obs.append("모델/서버 오류: " + "; ".join(f"`{e[:120]}`" for e in errs[:3]))
    return "\n".join(parts), obs


def track_b_md(tb: dict | None, qs: dict) -> tuple[str, list[str]]:
    obs: list[str] = []
    if not tb:
        return "실행하지 않음.", obs
    labels = qs.get("category_labels", {})
    rows = ["| 범주 | 점수 |", "|---|---|"] + [f"| {c} — {labels.get(c, '')} | {v:.2f} |"
                                              for c, v in tb["by_category"].items()]
    extra = (f" · 객관식 로그 우도 정답률 {tb['mcq_loglik_accuracy']:.2f}" if "mcq_loglik_accuracy" in tb else "")
    head = (f"**전체 {tb['overall']:.2f}** (범주 평균) · 생성 속도 {_f(tb.get('tokens_per_s'), 1)} tok/s · "
            f"총 {tb['seconds'] / 60:.1f}분 · 오류 {tb['errors']}건{extra}")
    items = ["| 문항 | 범주 | 점수 | 판정 근거 | 시간(s) |", "|---|---|---|---|---|"]
    trunc = 0
    hallu = 0
    for it in tb["items"]:
        ex = it["extracted"]
        if isinstance(ex, dict):
            if ex.get("outside_genes"):
                hallu += 1
            ex = ", ".join(f"{k}={v if not isinstance(v, dict) else v.get('ratio')}" for k, v in ex.items())
        if it.get("done_reason") == "length":
            trunc += 1
        ll = f" (LL: {it['loglik_choice']})" if it.get("loglik_choice") else ""
        items.append(f"| {it['id']} | {it['category']} | {it['score']:.2f} | {str(ex)[:160]}{ll} | "
                     f"{_f(it.get('seconds'), 0)} |")
    ex_parts = ["### 해석 문항 답변 (앞부분)", ""]
    for it in tb["items"]:
        if it["type"] == "open":
            ex_parts += [f"**{it['id']}** — 점수 {it['score']:.2f}", "", _excerpt(it.get("answer", ""), 600), ""]
    weakest = min(tb["by_category"].items(), key=lambda x: x[1]) if tb["by_category"] else None
    if weakest:
        obs.append(f"Track B에서 가장 약한 범주: {weakest[0]} ({weakest[1]:.2f}).")
    if hallu:
        obs.append(f"주어진 유전자 목록 밖의 지질 관련 유전자를 후보로 언급한 답변 {hallu}건(근거 없는 유전자 언급).")
    if trunc:
        obs.append(f"출력 상한에 걸려 잘린 답변 {trunc}건.")
    if tb["errors"]:
        obs.append(f"응답 오류 {tb['errors']}건.")
    return "\n".join([head, "", "\n".join(rows), "", "\n".join(items), "", *ex_parts]), obs


def _load_str(ld: dict) -> str:
    if not ld:
        return "—"
    gpu = (f" · GPU 메모리 +{ld['gpu_delta_gb']} GB (적재 후 전체 {ld.get('gpu_used_gb')}/{ld.get('gpu_total_gb')} GB, "
           "nvidia-smi)" if ld.get("gpu_delta_gb") is not None else "")
    where = "**CPU 오프로드 있음**" if ld.get("cpu_offload") else "GPU에 모두 적재"
    return f"{where} · 적재 {ld.get('seconds', '—')}초{gpu} · 컨텍스트 {ld.get('context_length', '—')}"


def write_model_report(rundir: Path, res: dict) -> Path:
    cfg = run_config(rundir)
    qs = _load(BENCH / "questions.json")
    m, var = res["model"], res.get("variant") or {}
    ta, tb = res.get("track_a"), res.get("track_b")
    a_md, a_obs = track_a_md(ta)
    b_md, b_obs = track_b_md(tb, qs)
    summ = ["| 지표 | 값 |", "|---|---|",
            f"| Track A 하네스 운용 | {('%.2f' % ta['overall']) if ta and ta.get('eligible') else '해당 없음'} |",
            f"| Track A 치명 항목 실패 | {ta.get('critical_fails', '—') if ta and ta.get('eligible') else '—'} |",
            f"| Track B 지식·해석 | {_f(tb and tb['overall'], 2)} |"]
    if tb:
        summ += [f"| · {c} | {v:.2f} |" for c, v in tb["by_category"].items()]
        summ.append(f"| 생성 속도 (Track B) | {_f(tb.get('tokens_per_s'), 1)} tok/s |")
    summ.append(f"| 소요 시간 | {res.get('minutes', '—')}분 |")
    hi = []
    if res.get("error"):
        hi.append(f"- **실행 오류**: `{res['error'][:300]}`")
    if ta and ta.get("eligible"):
        perfect = sum(1 for v in ta["by_scenario"].values() if v >= 0.999)
        hi.append(f"- Track A: 시나리오 {len(ta['by_scenario'])}개 중 {perfect}개 만점. "
                  f"가장 낮은 시나리오: {min(ta['by_scenario'].items(), key=lambda x: x[1])[0]}.")
    elif ta:
        hi.append("- Track A: 도구 호출을 지원하지 않아 하네스의 주 모델로 쓸 수 없음 (자문 역할만 평가).")
    if tb:
        best = max(tb["by_category"].items(), key=lambda x: x[1])
        hi.append(f"- Track B: 가장 강한 범주 {best[0]} ({best[1]:.2f}).")
    mt = ["| 항목 | 값 |", "|---|---|", f"| 계열 / 크기 | {m['family']} / {m['size']} |",
          f"| 종류 | {'유전체·의생명 특화' if m['kind'] == 'biomedical' else '범용'} |"]
    if m.get("group"):
        mt.append(f"| 구분 | {cfg.get('groups', {}).get(m['group'], m['group'])} |")
    mt += [
          f"| 출처 | {m['source']} (`{m.get('tag') or m.get('path')}`) |",
          f"| 라이선스 | {m.get('license', '—')} |",
          f"| 양자화 / 파라미터 | {var.get('quantization') or ('FP32' if m.get('runner') == 'hf' else '—')} / "
          f"{var.get('parameter_size') or m['size']} |",
          f"| 기능 (Ollama) | {', '.join(var.get('capabilities') or []) or '—'} |",
          f"| 벤치마크 변형 | `{var.get('variant', '—')}`, num_ctx {var.get('num_ctx', '—')}"
          f"{', 채팅 템플릿 보정' if var.get('template_overridden') else ''}"
          f"{''.join(f', {k} {str(v).lower()}' for k, v in (var.get('extra_parameters') or {}).items())} |"]
    if res.get("load"):
        mt.append(f"| GPU 적재 | {_load_str(res['load'])} |")
    if res.get("loadavg_start") is not None:
        mt.append(f"| 서버 CPU 부하(1분 평균) | 시작 {res['loadavg_start']} · 끝 {res.get('loadavg_end', '—')} "
                  "(공유 서버: 다른 작업이 실행 시간에 영향) |")
    if m.get("note") or m.get("reference"):
        mt.append(f"| 비고 | {m.get('reference') or m.get('note')} |")
    if res.get("gpu_loaded_before"):
        mt.append(f"| 시작 시 GPU에 올라 있던 다른 모델 | {', '.join(res['gpu_loaded_before'])} |")
    files = [f"- 결과 JSON: `output/bench/{rundir.name}/{m['id']}/result.json`",
             f"- Track A 실행별 이벤트·로그: `output/bench/{rundir.name}/{m['id']}/A/<시나리오>-r<반복>/`",
             f"- Track B 답변: `output/bench/{rundir.name}/{m['id']}/B/answers.jsonl`"]
    vals = {"MODEL_NAME": model_name(m), "RUN_ID": rundir.name, "STARTED": res.get("started", "—"),
            "FINISHED": res.get("finished", "—"), "MINUTES": res.get("minutes", "—"),
            "SUMMARY_TABLE": "\n".join(summ), "HIGHLIGHTS": "\n".join(hi), "MODEL_TABLE": "\n".join(mt),
            "COMMON": common_section(rundir, cfg), "TRACK_A": a_md, "TRACK_B": b_md,
            "OBSERVATIONS": "\n".join(f"- {o}" for o in (a_obs + b_obs)) or "- 특이 사항 없음.",
            "FILES": "\n".join(files)}
    out = rundir / "reports" / f"{m['id']}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_fill((TPL / "model_report.md").read_text(), vals))
    return out


# ── summary ─────────────────────────────────────────────────────────────────
def write_summary(rundir: Path, cfg: dict) -> Path:
    scen = _load(BENCH / "scenarios.json")
    qs = _load(BENCH / "questions.json")
    results = {m["id"]: _load(rundir / m["id"] / "result.json") for m in cfg["models"]}
    done = [m for m in cfg["models"] if results[m["id"]]]
    pending = [m for m in cfg["models"] if not results[m["id"]]]
    cats = list(qs.get("category_labels", {}))
    sc_ids = [s["id"] for s in scen.get("scenarios", [])]
    status = "완료" if not pending else f"진행 중, {len(done)}/{len(cfg['models'])} 모델 완료"
    lines = [f"# SAM 로컬 LLM 벤치마크 — 비교 요약 ({status})", "",
             f"> 실행 ID `{rundir.name}` · 갱신 {time.strftime('%Y-%m-%d %H:%M')} · "
             "모델 하나가 끝날 때마다 자동 갱신됩니다.",
             "> 데이터·실험 설계·채점 방법은 각 모델 보고서의 3–4절(공통)에 있습니다.", ""]
    if pending:
        lines += ["대기 중: " + ", ".join(model_name(m) for m in pending), ""]
    groups = cfg.get("groups", {})
    lines += ["## 1. 전체 비교", "",
              "| 모델 | 종류 | 양자화 | Track A 운용 | 치명 실패 | Track B 지식·해석 | " +
              " | ".join(cats) + " | tok/s | 소요(분) | 보고서 |",
              "|---|---|---|---|---|---|" + "---|" * len(cats) + "---|---|---|"]
    for m in done:
        r = results[m["id"]]
        ta, tb, var = r.get("track_a") or {}, r.get("track_b") or {}, r.get("variant") or {}
        a = f"{ta['overall']:.2f}" if ta.get("eligible") else ("N/A" if ta else "—")
        crit = ta.get("critical_fails", "—") if ta.get("eligible") else "—"
        bc = " | ".join(_f((tb.get("by_category") or {}).get(c), 2) for c in cats)
        tag = " ★" if m.get("group") in ("large", "quant") else ""
        offload = " ⚠오프로드" if (r.get("load") or {}).get("cpu_offload") else ""
        lines.append(f"| {model_name(m)}{tag}{' (기준)' if m.get('reference') else ''}{offload} | "
                     f"{'특화' if m['kind'] == 'biomedical' else '범용'} | "
                     f"{var.get('quantization') or ('FP32' if m.get('runner') == 'hf' else '—')} | {a} | {crit} | "
                     f"{_f(tb.get('overall'), 2)} | {bc} | {_f(tb.get('tokens_per_s'), 1)} | "
                     f"{r.get('minutes', '—')} | [{m['id']}]({m['id']}.md) |")
    note = ["", "N/A: 도구 호출을 지원하지 않아 하네스 주 모델로 쓸 수 없음."]
    if groups:
        note.append("★: 이번 실행에서 추가한 모델(" + ", ".join(v for k, v in groups.items() if k != "base") + ").")
    lines += note + ["",
              "## 2. Track A 시나리오별 점수", "",
              "| 모델 | " + " | ".join(sc_ids) + " | 전체 |", "|---|" + "---|" * (len(sc_ids) + 1)]
    for m in done:
        ta = results[m["id"]].get("track_a") or {}
        if not ta.get("eligible"):
            continue
        cells = " | ".join(_f(ta["by_scenario"].get(s), 2) for s in sc_ids)
        lines.append(f"| {model_name(m)} | {cells} | {ta['overall']:.2f} |")
    labels = {s["id"]: s["title"] for s in scen.get("scenarios", [])}
    lines += ["", "시나리오: " + "; ".join(f"{k} {v}" for k, v in labels.items()), ""]
    elig = [(m, results[m["id"]]["track_a"]["overall"]) for m in done
            if (results[m["id"]].get("track_a") or {}).get("eligible")]
    tbs = [(m, results[m["id"]]["track_b"]["overall"]) for m in done if results[m["id"]].get("track_b")]
    lines += ["## 3. 자동 순위", ""]
    if elig:
        lines.append("- Track A 상위: " + ", ".join(f"{model_name(m)} {s:.2f}"
                                                  for m, s in sorted(elig, key=lambda x: -x[1])[:5]))
    if tbs:
        lines.append("- Track B 상위: " + ", ".join(f"{model_name(m)} {s:.2f}"
                                                  for m, s in sorted(tbs, key=lambda x: -x[1])[:5]))
    lines += ["", "## 4. 제외한 모델", "", "| 모델 | 이유 |", "|---|---|"]
    lines += [f"| {e['name']} | {e['reason']} |" for e in cfg.get("excluded", [])]
    out = rundir / "reports" / "SUMMARY.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    return out
