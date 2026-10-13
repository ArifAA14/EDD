"""Turn raw trial records into aggregates, findings, parent comparison, and a gate decision."""
from __future__ import annotations

from collections import defaultdict

from .stats import classify_delta, paired_bootstrap, wilson
from .util import canonical_json, percentile

ICON = {"PASS": "✅", "FAIL": "❌", "UNCLEAR": "❔"}
_IGNORED_META = {"prompt_version", "model"}
SEVERITY_ORDER = {"blocker": 0, "warning": 1, "note": 2}


def group_trials(trials: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for t in sorted(trials, key=lambda r: (r["case_id"], r["trial"])):
        grouped[t["case_id"]].append(t)
    return dict(grouped)


def _frac(verdicts: list[str]) -> float:
    return sum(v == "PASS" for v in verdicts) / len(verdicts)


def _ratio(verdicts: list[str]) -> str:
    return f"{sum(v == 'PASS' for v in verdicts)}/{len(verdicts)}"


def compare_runs(parent_trials: list[dict], new_trials: list[dict], seed: int = 1337) -> dict | None:
    """Paired comparison on the cases present in both runs."""
    old, new = group_trials(parent_trials), group_trials(new_trials)
    shared = sorted(set(old) & set(new))
    if not shared:
        return None
    ov = {c: [t["verdict"] for t in old[c]] for c in shared}
    nv = {c: [t["verdict"] for t in new[c]] for c in shared}
    boot = paired_bootstrap([_frac(ov[c]) for c in shared], [_frac(nv[c]) for c in shared], seed=seed)
    delta, lo, hi = boot
    to_fail, to_pass, stability = [], [], []
    for c in shared:
        was_all, is_all = all(v == "PASS" for v in ov[c]), all(v == "PASS" for v in nv[c])
        if was_all and not is_all:
            to_fail.append({"case": c, "before": _ratio(ov[c]), "after": _ratio(nv[c])})
        elif is_all and not was_all:
            to_pass.append({"case": c, "before": _ratio(ov[c]), "after": _ratio(nv[c])})
        was_stable, is_stable = len(set(ov[c])) == 1, len(set(nv[c])) == 1
        if was_stable != is_stable:
            stability.append({"case": c, "before": "consistent" if was_stable else "flaky",
                              "after": "consistent" if is_stable else "flaky",
                              "before_ratio": _ratio(ov[c]), "after_ratio": _ratio(nv[c])})
    return {
        "shared": len(shared), "only_parent": len(set(old) - set(new)), "only_new": len(set(new) - set(old)),
        "delta": delta, "ci": (lo, hi), "verdict": classify_delta(lo, hi),
        "to_fail": to_fail, "to_pass": to_pass, "stability_changes": stability,
        "parent_pass_rate": sum(_frac(ov[c]) for c in shared) / len(shared),
        "new_pass_rate": sum(_frac(nv[c]) for c in shared) / len(shared),
    }


def analyze(spec: dict, goldens: dict, trials: list[dict], canaries: list[dict], parent: dict | None,
            run_type: str, leaks: list[str] | None = None, provenance: dict | None = None,
            partial_of: int | None = None) -> dict:
    thresholds, budgets = spec["thresholds"], spec["budgets"]
    n = len(trials)
    counts = {v: sum(t["verdict"] == v for t in trials) for v in ("PASS", "FAIL", "UNCLEAR")}
    pass_rate = counts["PASS"] / n if n else 0.0
    grouped = group_trials(trials)
    has_decided = any("decided_by" in (t.get("meta") or {}) for t in trials)

    def model_decided(t: dict) -> bool:
        return (not has_decided) or (t.get("meta") or {}).get("decided_by", "model") == "model"

    cases: dict[str, dict] = {}
    for cid, ts in grouped.items():
        verdicts = [t["verdict"] for t in ts]
        outputs = [t["output"] for t in ts]
        meta_keys = sorted({k for t in ts for k in (t.get("meta") or {}) if k not in _IGNORED_META})
        flaky_keys = [k for k in meta_keys if len({canonical_json((t.get("meta") or {}).get(k)) for t in ts}) > 1]
        short = all(len(o) <= 60 for o in outputs)
        cases[cid] = {
            "verdicts": verdicts, "icons": "".join(ICON[v] for v in verdicts), "ratio": _ratio(verdicts),
            "verdict_flaky": len(set(verdicts)) > 1,
            "output_flaky": short and len(set(outputs)) > 1 and len(set(verdicts)) == 1,
            "behavior_flaky_keys": flaky_keys,
            "model_decided_trials": sum(model_decided(t) for t in ts),
            "decided_by": sorted({str((t.get("meta") or {}).get("decided_by", "")) for t in ts} - {""}),
            "soft_misses": sum(t.get("soft_misses", 0) for t in ts),
            "cost": sum(t["cost_usd"] for t in ts),
        }

    # Hard invariants.
    names = set(spec.get("invariants") or {}) | {i for g in goldens.values() for i in g.invariants}
    invariants = {}
    for name in sorted(names):
        ids = [cid for cid in grouped if name in goldens[cid].invariants]
        ts = [t for cid in ids for t in grouped[cid]]
        invariants[name] = {
            "description": (spec.get("invariants") or {}).get(name, ""),
            "cases": len(ids), "trials": len(ts),
            "model_decided_trials": sum(model_decided(t) for t in ts),
            "model_decided_cases": sum(cases[cid]["model_decided_trials"] > 0 for cid in ids),
            "violations": sum(t["verdict"] == "FAIL" for t in ts),
            "unclear": sum(t["verdict"] == "UNCLEAR" for t in ts),
        }

    def breakdown(key_fn):
        out: dict[str, dict] = defaultdict(lambda: {"pass": 0, "trials": 0})
        for cid, ts in grouped.items():
            for key in key_fn(goldens[cid]):
                out[key]["trials"] += len(ts)
                out[key]["pass"] += sum(t["verdict"] == "PASS" for t in ts)
        return dict(sorted(out.items()))

    by_kind = breakdown(lambda g: [g.kind])
    by_tag = breakdown(lambda g: g.tags)

    scen_pass = sum(1 for c in cases.values() if all(v == "PASS" for v in c["verdicts"]))
    model_cases = [cid for cid, c in cases.items() if c["model_decided_trials"] > 0]
    model_scen_pass = sum(1 for cid in model_cases if all(v == "PASS" for v in cases[cid]["verdicts"]))
    model_trials = [t for t in trials if model_decided(t)]
    decided = {
        "has": has_decided,
        "model_trials": len(model_trials), "other_trials": n - len(model_trials),
        "model_scenarios": len(model_cases), "other_scenarios": len(cases) - len(model_cases),
        "other_share": (n - len(model_trials)) / n if n else 0.0,
        "model_pass": sum(t["verdict"] == "PASS" for t in model_trials),
        "model_ci": wilson(sum(t["verdict"] == "PASS" for t in model_trials), len(model_trials)),
        "model_scen_pass": model_scen_pass,
        "model_scen_ci": wilson(model_scen_pass, len(model_cases)),
        "stable_model_scenarios": sum(
            1 for cid in model_cases
            if not cases[cid]["verdict_flaky"] and not cases[cid]["output_flaky"] and not cases[cid]["behavior_flaky_keys"]),
    }

    sut_cost = sum(t["cost_usd"] for t in trials)
    judge_cost = sum(t.get("judge_cost_usd", 0.0) for t in trials) + sum(c.get("judge_cost_usd", 0.0) for c in canaries)
    latencies = [t["latency_ms"] for t in trials if t.get("latency_ms")]
    cost = {
        "sut": sut_cost, "judge": judge_cost, "total": sut_cost + judge_cost,
        "p50": percentile(latencies, 0.5), "p95": percentile(latencies, 0.95),
        "top_cases": sorted(((cid, c["cost"]) for cid, c in cases.items()), key=lambda x: -x[1])[:3],
    }
    canary = {
        "total": len(canaries),
        "caught": sum(c["verdict"] == "FAIL" for c in canaries),
        "passed_wrongly": sum(c["verdict"] == "PASS" for c in canaries),
        "unclear": sum(c["verdict"] == "UNCLEAR" for c in canaries),
    }
    judged = [t for t in trials if t["verdict_source"] == "judge"]
    judge = {
        "calls": len(judged) + len(canaries),
        "invalid": sum(not t.get("judge_valid", True) for t in judged) + sum(not c.get("judge_valid", True) for c in canaries),
        "retried": sum(t.get("judge_attempts", 1) > 1 for t in judged) + sum(c.get("judge_attempts", 1) > 1 for c in canaries),
        "inconsistent": sum(bool(t.get("judge_inconsistent")) for t in judged),
    }

    comparison = None
    if parent:
        comparison = compare_runs(parent["trials"], trials)
        if comparison:
            pfm = parent["fm"]
            comparison["parent_id"] = parent["id"]
            comparison["parent_fm"] = pfm
            if pfm.get("cost_usd"):
                comparison["cost_delta_pct"] = (sut_cost - pfm["cost_usd"]) / pfm["cost_usd"] * 100
            if pfm.get("latency_p95_ms") and cost["p95"] is not None:
                comparison["p95_delta_ms"] = cost["p95"] - pfm["latency_p95_ms"]

    result = {
        "n": n, "counts": counts, "pass_rate": pass_rate, "pass_ci": wilson(counts["PASS"], n),
        "unclear_rate": counts["UNCLEAR"] / n if n else 0.0,
        "hard_failures": counts["FAIL"], "soft_warnings": sum(t.get("soft_misses", 0) for t in trials),
        "cases": cases, "invariants": invariants, "by_kind": by_kind, "by_tag": by_tag,
        "scenario": {"pass": scen_pass, "n": len(cases), "ci": wilson(scen_pass, len(cases))},
        "decided": decided, "cost": cost, "canary": canary, "judge": judge, "parent": comparison,
        "leaks": leaks or [], "run_type": run_type, "partial_of": partial_of,
        "adapter_errors": sum(t["verdict_source"] == "adapter" for t in trials),
        "scorer_vetoes": sum(t["verdict_source"] == "scorer" for t in trials),
    }
    result["valid"] = canary["passed_wrongly"] == 0 and not result["leaks"]
    result["findings"] = build_findings(spec, goldens, grouped, result, provenance or {})
    result["gate"] = evaluate_gate(spec, result)
    return result


def _finding(sev, fid, title, detail, cases=None, question=""):
    return {"severity": sev, "id": fid, "title": title, "detail": detail, "cases": cases or [], "question": question}


def build_findings(spec, goldens, grouped, a, provenance) -> list[dict]:
    gate = a["run_type"] == "gate"
    thr, budgets = spec["thresholds"], spec["budgets"]
    out: list[dict] = []
    cases = a["cases"]

    if a["canary"]["passed_wrongly"]:
        out.append(_finding("blocker", "canary_passed", "A canary passed: the judge or rubric let known-wrong output through.",
                            f"{a['canary']['passed_wrongly']} of {a['canary']['total']} canaries were judged PASS. This run is invalid.",
                            question="Is the rubric too loose for this failure mode, or is the judge being lenient?"))
    if a["leaks"]:
        out.append(_finding("blocker", "blinding_leak", "Identifying terms survived scrubbing.",
                            "Found in judge bundles: " + ", ".join(a["leaks"]) + ". This run is invalid.",
                            question="Which scrub pattern is missing?"))
    if a["canary"]["total"] == 0 and a["judge"]["calls"]:
        out.append(_finding("blocker" if gate else "warning", "no_canaries", "No canaries configured.",
                            "Every PASS is unchecked against known-wrong outputs, so the judge's false-pass rate is unknown.",
                            question="Which failure modes need a canary? Write a plausible but wrong output for each."))
    pinned = sorted(cid for cid, g in goldens.items() if g.pinned and cid in cases
                    and any(v != "PASS" for v in cases[cid]["verdicts"]))
    if pinned:
        out.append(_finding("blocker", "pinned_regression", "A pinned case regressed.", "Pinned cases previously failed and were fixed.",
                            pinned, "What change reintroduced this failure?"))
    bad_inv = {k: v for k, v in a["invariants"].items() if v["violations"] or v["unclear"]}
    for name, v in bad_inv.items():
        ids = sorted(cid for cid in cases if name in goldens[cid].invariants and any(x != "PASS" for x in cases[cid]["verdicts"]))
        out.append(_finding("blocker", "invariant_violation", f"Invariant `{name}` was not upheld.",
                            f"{v['violations']} FAIL and {v['unclear']} UNCLEAR across {v['trials']} trials.", ids,
                            "Is this a real regression, a bad golden, or an ambiguous rubric criterion?"))
    failing = sorted(cid for cid, c in cases.items() if "FAIL" in c["verdicts"] and cid not in pinned
                     and not any(cid in f["cases"] for f in out if f["id"] == "invariant_violation"))
    if failing:
        out.append(_finding("warning", "cases_failing", "Cases with FAIL verdicts.",
                            f"{len(failing)} case(s) had at least one FAIL trial.", failing,
                            "For each: real bug, bad golden, or bad scorer? Fix only real bugs in the code."))
    if a["adapter_errors"] or a["scorer_vetoes"]:
        out.append(_finding("warning", "vetoes", "Trials failed before reaching the judge.",
                            f"{a['adapter_errors']} adapter errors and {a['scorer_vetoes']} scorer vetoes (all recorded as FAIL).",
                            sorted(cid for cid, ts in grouped.items() if any(t["verdict_source"] != "judge" for t in ts)),
                            "Are these crashes, timeouts, or schema problems in the system under test?"))
    cmp_ = a["parent"]
    if cmp_ and cmp_["to_fail"]:
        out.append(_finding("blocker" if gate else "warning", "regression_vs_parent", "Cases regressed versus the parent run.",
                            f"{len(cmp_['to_fail'])} case(s) went from all-PASS to not all-PASS.",
                            [x["case"] for x in cmp_["to_fail"]], "Did the change cause this, or is it noise from a flaky case?"))
    if a["judge"]["invalid"]:
        out.append(_finding("warning", "judge_invalid", "Judge responses were rejected after a retry.",
                            f"{a['judge']['invalid']} judge call(s) returned malformed or unverifiable output and were recorded UNCLEAR.",
                            question="Is the judge prompt failing on a particular input shape?"))
    if a["judge"]["inconsistent"]:
        out.append(_finding("note", "judge_inconsistent", "Judge overall verdict disagreed with its own criteria.",
                            f"{a['judge']['inconsistent']} trial(s) where the judge said PASS but a hard criterion was not met. Engine used the criteria.",
                            question="Does the judge need a stricter instruction on the overall verdict?"))
    clusters: dict[str, set] = defaultdict(set)
    for cid, ts in grouped.items():
        for t in ts:
            for row in t.get("criteria", []):
                if row["severity"] == "hard" and row["met"] is None:
                    clusters[row["criterion"]].add(cid)
    for text, ids in clusters.items():
        if len(ids) >= 2:
            out.append(_finding("warning", "unclear_cluster", "The same criterion produced UNCLEAR in several cases.",
                                f"Criterion: “{text}”", sorted(ids), "Is the criterion ambiguous or missing context?"))
    flaky = sorted(cid for cid, c in cases.items() if c["verdict_flaky"])
    if flaky:
        out.append(_finding("warning", "verdict_flaky", "Verdicts differed across trials of the same case.",
                            "Same input, different verdicts.", flaky, "Is the system nondeterministic here, or is the rubric borderline?"))
    out_flaky = sorted(cid for cid, c in cases.items() if c["output_flaky"])
    if out_flaky:
        out.append(_finding("note", "output_flaky", "Same verdict, different short outputs across trials.",
                            "Outputs look like labels that changed between trials.", out_flaky,
                            "Is the accepted set intentionally broad, or should the rubric tell these outputs apart?"))
    beh = sorted(cid for cid, c in cases.items() if c["behavior_flaky_keys"])
    if beh:
        keys = sorted({k for cid in beh for k in cases[cid]["behavior_flaky_keys"]})
        out.append(_finding("note", "behavior_flaky", "Observed behavior differed across trials.",
                            "Adapter meta keys that changed: " + ", ".join(keys), beh,
                            "Should this behavior be pinned down by a rubric criterion, or is the variation intended?"))
    soft = sorted(cid for cid, c in cases.items() if c["soft_misses"])
    if soft:
        out.append(_finding("warning", "soft_failed", "Soft expectations were not met.",
                            f"{a['soft_warnings']} soft criterion miss(es); these do not gate.", soft,
                            "Should any of these be promoted to hard criteria?"))
    d = a["decided"]
    if d["has"] and d["other_share"] > float(thr.get("max_guard_share", 0.3)):
        out.append(_finding("warning", "guard_heavy", "Many trials never exercised the model.",
                            f"{d['other_trials']}/{a['n']} trials ({d['other_share']:.1%}) were decided by a non-model path.",
                            sorted(cid for cid, c in cases.items() if c["model_decided_trials"] == 0),
                            "Is this by design? Should these cases be reported as their own suite?"))
    for name, v in a["invariants"].items():
        covered = v["model_decided_cases"] if d["has"] else v["cases"]
        if v["cases"] and covered < 3:
            out.append(_finding("warning", "thin_coverage", f"Thin coverage of invariant `{name}`.",
                                f"Only {covered} model-decided case(s) exercise it.",
                                question="Add more cases for this invariant, including adversarial variants."))
    ci = a["pass_ci"]
    if ci and ci[0] < float(thr["min_pass_rate"]) < ci[1] and a["n"]:
        out.append(_finding("warning", "near_threshold", "The pass-rate interval straddles the threshold.",
                            f"Pass rate {a['pass_rate']:.1%} (95% CI {ci[0]:.1%} to {ci[1]:.1%}) vs threshold {float(thr['min_pass_rate']):.1%}.",
                            question="Is the sample large enough to tell whether the threshold is met?"))
    if budgets.get("max_cost_usd_per_run") is not None and a["cost"]["sut"] > float(budgets["max_cost_usd_per_run"]):
        out.append(_finding("blocker" if gate else "warning", "cost_over_budget", "System cost exceeded the run budget.",
                            f"${a['cost']['sut']:.2f} vs budget ${float(budgets['max_cost_usd_per_run']):.2f}."))
    p95 = a["cost"]["p95"]
    if budgets.get("p95_latency_ms") is not None and p95 is not None and p95 > float(budgets["p95_latency_ms"]):
        out.append(_finding("blocker" if gate else "warning", "latency_over_budget", "p95 latency exceeded the budget.",
                            f"{p95:.0f} ms vs budget {float(budgets['p95_latency_ms']):.0f} ms."))
    if cmp_ and cmp_.get("cost_delta_pct") is not None and cmp_["cost_delta_pct"] > 25:
        out.append(_finding("warning", "cost_spike", "Cost rose sharply versus the parent.",
                            f"+{cmp_['cost_delta_pct']:.1f}% system cost.", question="Is the quality change worth the cost?"))
    if not provenance.get("prompt_hash") and not provenance.get("config_hash"):
        out.append(_finding("note", "provenance_incomplete", "No prompt or config files are hashed.",
                            "Without hash_inputs in spec.md, a revert cannot verify it restored the same prompt and config."))
    if a["partial_of"] and a["partial_of"] > len(cases):
        out.append(_finding("note", "partial_run", "Only a subset of cases was run.",
                            f"Ran {len(cases)} of {a['partial_of']} cases. Not eligible for the gate."))
    out.sort(key=lambda f: SEVERITY_ORDER[f["severity"]])
    return out


def evaluate_gate(spec: dict, a: dict) -> dict:
    if a["run_type"] != "gate":
        return {"passed": None, "reasons": ["dev run; gate not evaluated"]}
    thr, budgets = spec["thresholds"], spec["budgets"]
    reasons: list[str] = []
    if a["partial_of"] and a["partial_of"] > len(a["cases"]):
        reasons.append("partial run is not eligible for the gate")
    if a["canary"]["passed_wrongly"]:
        reasons.append(f"{a['canary']['passed_wrongly']} canary(ies) passed; run is invalid")
    if a["leaks"]:
        reasons.append("blinding leak detected; run is invalid")
    if a["canary"]["total"] == 0:
        reasons.append("no canaries configured; judge validity unproven")
    for f in a["findings"]:
        if f["id"] == "pinned_regression":
            reasons.append("pinned case regressed: " + ", ".join(f["cases"]))
        if f["id"] == "invariant_violation":
            reasons.append(f["title"])
    if a["pass_rate"] < float(thr["min_pass_rate"]):
        reasons.append(f"pass rate {a['pass_rate']:.1%} below threshold {float(thr['min_pass_rate']):.1%}")
    if a["unclear_rate"] > float(thr["max_unclear_rate"]):
        reasons.append(f"UNCLEAR rate {a['unclear_rate']:.1%} above limit {float(thr['max_unclear_rate']):.1%}")
    if a["parent"] and a["parent"]["verdict"] == "regressed":
        reasons.append("statistically significant regression versus parent")
    if budgets.get("max_cost_usd_per_run") is not None and a["cost"]["sut"] > float(budgets["max_cost_usd_per_run"]):
        reasons.append("system cost over budget")
    p95 = a["cost"]["p95"]
    if budgets.get("p95_latency_ms") is not None and p95 is not None and p95 > float(budgets["p95_latency_ms"]):
        reasons.append("p95 latency over budget")
    return {"passed": not reasons, "reasons": reasons or ["all gate rules satisfied"]}
