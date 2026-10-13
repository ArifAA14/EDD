"""Orchestrate one eval run: adapter -> scorers -> sealed bundles -> blind judge -> analysis -> report."""
from __future__ import annotations

import json
import random
import secrets
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import chain
from .adapter import run_adapter
from .analysis import analyze, group_trials
from .bundle import IdAllocator, build_bundle, bundle_hash, compile_patterns, find_leaks
from .judge import ClaudeCliBackend, judge_case, judge_prompt_hash, load_judge_prompt, resolve_model
from .loader import SpecError, golden_set_hash, load_canaries, load_goldens, load_spec
from .report import render_report
from .scorers import resolve_scorers, run_scorers
from .util import git_diff_stat, git_info, hash_files, hash_obj, iso, make_report_id, sha256_text, utc_now

BUNDLE_SPEC_VERSION = 1
MIN_HYPOTHESIS_CHARS = 10


def _default_log(msg: str) -> None:
    print(f"[edd] {msg}", file=sys.stderr)


def default_backend_factory(model: str, system_prompt: str, spec: dict):
    return ClaudeCliBackend(model, system_prompt, timeout_s=float(spec["judge"].get("timeout_s", 180)))


def _select(spec: dict, feature_dir: Path, run_type: str):
    include = set(spec["gate"].get("include") or [])
    if run_type == "gate":
        splits = ["holdout"] + (["dev"] if include & {"pinned_dev", "dev"} else [])
        goldens = load_goldens(feature_dir, "holdout") if "holdout" in include else []
        if "dev" in include:
            goldens += load_goldens(feature_dir, "dev")
        elif "pinned_dev" in include:
            goldens += [g for g in load_goldens(feature_dir, "dev") if g.pinned]
    else:
        splits = ["dev"]
        goldens = load_goldens(feature_dir, "dev")
    canaries = [c for s in splits for c in load_canaries(feature_dir, s)]
    return goldens, canaries, splits


def _common(values: list) -> str | None:
    seen = sorted({str(v) for v in values if v})
    if not seen:
        return None
    return seen[0] if len(seen) == 1 else "multiple: " + ", ".join(seen)


def run_eval(root: Path, feature: str, hypothesis: str, *, run_type: str = "dev", trials: int | None = None,
             case_ids: list[str] | None = None, limit: int | None = None, parent: str | None = "auto",
             judge_model: str | None = None, concurrency: int | None = None, seed: int | None = None,
             backend_factory=None, change_note: str | None = None, refuted_if: str | None = None,
             evals_dir: str = "evals", log=_default_log) -> dict:
    root = Path(root).resolve()
    feature_dir = root / evals_dir / feature
    if not feature_dir.is_dir():
        raise SpecError(f"no such feature folder: {feature_dir}")
    if not hypothesis or len(hypothesis.strip()) < MIN_HYPOTHESIS_CHARS:
        raise SpecError("refusing to run: write a hypothesis first (what you expect this run to show, "
                        f"at least {MIN_HYPOTHESIS_CHARS} characters). See the hypothesis-and-run skill.")
    if run_type not in {"dev", "gate"}:
        raise SpecError("run_type must be dev or gate")
    if run_type == "gate" and (case_ids or limit):
        raise SpecError("gate runs must cover the full gate set; --cases and --limit are not allowed")

    spec = load_spec(feature_dir)
    goldens, canary_defs, splits = _select(spec, feature_dir, run_type)
    if not goldens:
        raise SpecError(f"no goldens to run for a {run_type} run in {feature_dir / 'goldens'}")
    available = len(goldens)
    seed = secrets.randbits(32) if seed is None else seed
    rng = random.Random(seed)
    if case_ids:
        unknown = sorted(set(case_ids) - {g.id for g in goldens})
        if unknown:
            raise SpecError(f"unknown case ids: {', '.join(unknown)}")
        goldens = [g for g in goldens if g.id in set(case_ids)]
    if limit and limit < len(goldens):
        goldens = sorted(rng.sample(goldens, limit), key=lambda g: g.id)
    by_id = {g.id: g for g in goldens}
    canary_defs = [c for c in canary_defs if c.for_case in by_id]
    n_trials = int(trials or spec["trials_per_case"])
    started = time.monotonic()
    now = utc_now()

    scorers = resolve_scorers(spec, feature_dir)
    sha, dirty = git_info(root)
    prompt_hash, _ = hash_files(root, spec["hash_inputs"].get("prompts") or [])
    config_hash, _ = hash_files(root, spec["hash_inputs"].get("config") or [])

    # 1. Run the system under test.
    work = [(g, t) for g in goldens for t in range(1, n_trials + 1)]
    log(f"running {len(goldens)} cases x {n_trials} trials = {len(work)} case-trials ({run_type} run)")
    adapter_workers = int(concurrency or spec["adapter"].get("concurrency", 4))
    with ThreadPoolExecutor(max_workers=adapter_workers) as pool:
        results = list(pool.map(lambda w: run_adapter(spec, root, w[0].id, w[1], w[0].input), work))

    # 2. Scorers (veto only).
    records: list[dict] = []
    for (g, t), res in zip(work, results):
        sc, notes, veto = run_scorers(spec, scorers, g, res)
        rec = {
            "type": "trial", "case_id": g.id, "trial": t, "judge_id": None, "scorers": sc, "scorer_notes": notes,
            "scorer_veto": veto, "adapter_error": res.error, "output": res.output, "verdict": None,
            "verdict_source": None, "criteria": [], "judge_verdict_raw": None, "judge_rationale": "",
            "judge_valid": True, "judge_invalid_reason": None, "judge_attempts": 0, "judge_inconsistent": False,
            "judge_models": {}, "bundle_hash": None, "soft_misses": 0, "latency_ms": res.latency_ms,
            "cost_usd": res.cost_usd, "judge_cost_usd": 0.0, "judge_duration_ms": 0, "meta": res.meta,
        }
        if spec["keep_raw_trace"]:
            rec["trace"] = res.trace
        if veto:
            rec["verdict"], rec["verdict_source"] = "FAIL", ("adapter" if not res.ok else "scorer")
        records.append(rec)
    sut_model = _common([r["meta"].get("model") for r in records])
    prompt_version = _common([r["meta"].get("prompt_version") for r in records])

    # 3. Sealed bundles for everything that survived the scorers, plus canaries.
    literal = [x for x in {sut_model, prompt_version, sha} if x and not str(x).startswith("multiple")]
    patterns = compile_patterns(spec, literal)
    ids = IdAllocator(rng)
    include_trace = bool(spec["judge"].get("include_trace"))
    tasks: list[dict] = []
    for rec, res in zip(records, results):
        if rec["verdict"] is None:
            rec["judge_id"] = ids.next()
            bundle = build_bundle(rec["judge_id"], by_id[rec["case_id"]], res.output, res.trace, patterns, include_trace)
            tasks.append({"kind": "trial", "rec": rec, "bundle": bundle, "golden": by_id[rec["case_id"]]})
    canary_recs: list[dict] = []
    for c in canary_defs:
        rec = {"type": "canary", "canary_id": c.id, "for_case": c.for_case, "mode": c.mode, "judge_id": ids.next(),
               "verdict": None, "criteria": [], "judge_valid": True, "judge_attempts": 0, "judge_cost_usd": 0.0,
               "bundle_hash": None}
        bundle = build_bundle(rec["judge_id"], by_id[c.for_case], c.output, [], patterns, include_trace)
        tasks.append({"kind": "canary", "rec": rec, "bundle": bundle, "golden": by_id[c.for_case]})
        canary_recs.append(rec)
    rng.shuffle(tasks)  # random order; the judge never sees run position
    leaks = sorted({leak for t in tasks for leak in find_leaks(t["bundle"], literal)})

    # 4. Blind judge, one case per call, in parallel.
    requested = judge_model or spec["judge"]["gate_model" if run_type == "gate" else "dev_model"]
    system_prompt = load_judge_prompt()
    backend = (backend_factory or default_backend_factory)(requested, system_prompt, spec)
    judge_workers = int(spec["judge"].get("concurrency", 4))
    log(f"judging {len(tasks)} sealed bundles with `{requested}` ({judge_workers} parallel)")
    with ThreadPoolExecutor(max_workers=judge_workers) as pool:
        outcomes = list(pool.map(lambda t: judge_case(backend, t["bundle"], t["golden"]), tasks))
    model_costs: Counter = Counter()
    for task, out in zip(tasks, outcomes):
        rec = task["rec"]
        rec["bundle_hash"] = bundle_hash(task["bundle"])
        rec["criteria"], rec["verdict"] = out["criteria"], out["verdict"]
        rec["judge_valid"], rec["judge_attempts"] = out["valid"], out["attempts"]
        rec["judge_cost_usd"], rec["judge_models"] = out["cost_usd"], out["models"]
        model_costs.update(out["models"])
        if task["kind"] == "trial":
            rec["verdict_source"] = "judge"
            rec["judge_verdict_raw"], rec["judge_rationale"] = out["verdict_raw"], out["rationale"]
            rec["judge_invalid_reason"], rec["judge_inconsistent"] = out["invalid_reason"], out["inconsistent"]
            rec["judge_duration_ms"] = out["duration_ms"]
            rec["soft_misses"] = sum(r["severity"] == "soft" and r["met"] is False for r in out["criteria"])
    judge_resolved = resolve_model(requested, dict(model_costs))

    # 5. Parent, analysis, report.
    parent_data = None
    parent_id = None
    if parent == "auto":
        parent_id = chain.default_parent(feature_dir)
    elif parent:
        parent_id = chain.resolve_id(feature_dir, parent)
    if parent_id:
        loaded = chain.load_report(feature_dir, parent_id)
        parent_data = {"id": parent_id, "fm": loaded["fm"], "trials": loaded["trials"]}
    provenance = {"prompt_hash": prompt_hash, "config_hash": config_hash}
    a = analyze(spec, by_id, records, canary_recs, parent_data, run_type, leaks, provenance,
                partial_of=available)
    grouped = group_trials(records)
    # Suffix = milliseconds (so ids sort in creation order within a second) + random bits (so branches never collide).
    rid = make_report_id(now, "%03x" % (now.microsecond // 1000) + secrets.token_hex(2))
    cmp_ = a["parent"]
    fm = {
        "id": rid, "feature": feature, "created_at": iso(now), "parent": parent_id, "run_type": run_type,
        "status": "complete" if a["valid"] else "invalid", "promoted": False,
        "git_sha": sha, "git_dirty": dirty, "config_hash": config_hash, "prompt_hash": prompt_hash,
        "sut_model": sut_model, "prompt_version": prompt_version,
        "golden_set_hash": golden_set_hash(feature_dir, splits), "golden_count": len(goldens),
        "cases_available": available, "trials_per_case": n_trials,
        "judge_requested_model": requested, "judge_model": judge_resolved,
        "judge_prompt_hash": judge_prompt_hash(system_prompt), "judge_tier": run_type,
        "bundle_spec_version": BUNDLE_SPEC_VERSION,
        "hypothesis": hypothesis.strip(), "hypothesis_hash": sha256_text(hypothesis.strip()),
        "hypothesis_outcome": None, "change_note": change_note, "seed": seed,
        "verdict_counts": {"pass": a["counts"]["PASS"], "fail": a["counts"]["FAIL"], "unclear": a["counts"]["UNCLEAR"]},
        "pass_rate": round(a["pass_rate"], 6), "pass_rate_ci95": [round(x, 6) for x in a["pass_ci"]] if a["pass_ci"] else None,
        "hard_failures": a["hard_failures"], "soft_warnings": a["soft_warnings"],
        "invariants": {k: {x: v[x] for x in ("cases", "trials", "model_decided_trials", "violations", "unclear")}
                       for k, v in a["invariants"].items()},
        "vs_parent": ({"parent": cmp_["parent_id"], "compared_cases": cmp_["shared"], "delta_pass_rate": round(cmp_["delta"], 6),
                       "delta_ci95": [round(x, 6) for x in cmp_["ci"]], "verdict": cmp_["verdict"],
                       "flips_to_pass": len(cmp_["to_pass"]), "flips_to_fail": len(cmp_["to_fail"])} if cmp_ else None),
        "cost_usd": round(a["cost"]["sut"], 6), "judge_cost_usd": round(a["cost"]["judge"], 6),
        "latency_p50_ms": a["cost"]["p50"], "latency_p95_ms": a["cost"]["p95"],
        "canaries": {"total": a["canary"]["total"], "caught": a["canary"]["caught"],
                     "passed_wrongly": a["canary"]["passed_wrongly"]},
        "findings": {s: sum(f["severity"] == s for f in a["findings"]) for s in ("blocker", "warning", "note")},
        "gate": a["gate"], "override": None, "duration_s": round(time.monotonic() - started, 1),
    }
    diff_stat = []
    if parent_data and parent_data["fm"].get("git_sha") and sha and parent_data["fm"]["git_sha"] != sha:
        diff_stat = git_diff_stat(root, parent_data["fm"]["git_sha"])
    ctx = {"analysis": a, "goldens": by_id, "grouped": grouped, "trials": records, "canary_records": canary_recs,
           "spec": spec, "change_note": change_note, "refuted_if": refuted_if, "diff_stat": diff_stat}
    text = render_report(fm, ctx)

    folder = chain.results_dir(feature_dir)
    folder.mkdir(parents=True, exist_ok=True)
    report_file = chain.report_path(feature_dir, rid)
    report_file.write_text(text, encoding="utf-8")
    with chain.cases_path(feature_dir, rid).open("w", encoding="utf-8") as fh:
        for rec in records + canary_recs:
            fh.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    chain.write_index(feature_dir)
    return {"id": rid, "path": report_file, "analysis": a, "fm": fm}
