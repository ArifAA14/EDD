"""Render the descriptive markdown report (docs/spec/06-report-format.md) and its integrity hash."""
from __future__ import annotations

import re
from pathlib import Path

from .analysis import ICON
from .util import hash_obj, join_frontmatter, split_frontmatter

FACTS_END = "<!-- facts:end -->"
AGENT_BEGIN, AGENT_END = "<!-- agent:begin -->", "<!-- agent:end -->"
AGENT_RE = re.compile(re.escape(AGENT_BEGIN) + r".*?" + re.escape(AGENT_END), re.S)
MUTABLE_FM = {"promoted", "hypothesis_outcome", "override", "facts_hash"}


# ---------- integrity ----------

def compute_facts_hash(fm: dict, body: str) -> str:
    region = AGENT_RE.sub("<!-- agent -->", body.split(FACTS_END, 1)[0])
    return hash_obj([{k: v for k, v in fm.items() if k not in MUTABLE_FM}, region])


def verify_report(path: Path) -> tuple[bool, str]:
    fm, body = split_frontmatter(path.read_text(encoding="utf-8"))
    if FACTS_END not in body:
        return False, "missing facts:end marker"
    expected, actual = fm.get("facts_hash"), compute_facts_hash(fm, body)
    return (expected == actual), ("engine-authored sections are intact" if expected == actual
                                  else "engine-authored sections or frontmatter were edited after the run")


# ---------- formatting helpers ----------

def pct(x, d: int = 1) -> str:
    return "n/a" if x is None else f"{x * 100:.{d}f}%"


def ci_str(ci) -> str:
    return "n/a" if not ci else f"{ci[0] * 100:.1f}% to {ci[1] * 100:.1f}%"


def money(x) -> str:
    return "n/a" if x is None else f"${x:.2f}"


def ms(x) -> str:
    return "n/a" if x is None else (f"{x / 1000:.1f} s" if x >= 1000 else f"{x:.0f} ms")


def cell(s) -> str:
    return str(s).replace("|", "\\|").replace("\n", " ⏎ ")


def fence(text: str, lang: str = "") -> str:
    ticks = "```"
    while ticks in text:
        ticks += "`"
    return f"{ticks}{lang}\n{text}\n{ticks}"


def case_list(ids, limit: int = 8) -> str:
    ids = list(ids)
    if not ids:
        return ""
    shown = ", ".join(f"`{i}`" for i in ids[:limit])
    return shown + (f" (+{len(ids) - limit} more)" if len(ids) > limit else "")


def pp(x) -> str:
    return f"{x * 100:+.1f} pp"


def block(label: str, text: str) -> list[str]:
    """Short text inline, long or multi-line text in a collapsible block. Never truncated."""
    if len(text) <= 200 and "\n" not in text:
        return [f"**{label}:** {text if text else '_(empty)_'}", ""]
    return [f"<details><summary>{label} ({len(text)} chars)</summary>", "", fence(text), "", "</details>", ""]


# ---------- sections ----------

def _banner(fm, a, spec) -> list[str]:
    gate = a["gate"]
    if gate["passed"] is None:
        gate_s = "not evaluated (dev run)"
    elif gate["passed"]:
        gate_s = "PASS"
    else:
        gate_s = "FAIL (" + "; ".join(gate["reasons"][:3]) + ")"
    can = a["canary"]
    if not a["valid"]:
        valid_s = "INVALID (" + ("canary passed" if can["passed_wrongly"] else "blinding leak") + ")"
    elif can["total"] == 0:
        valid_s = "unvalidated, no canaries configured"
    else:
        valid_s = f"valid ({can['caught']}/{can['total']} canaries caught)"
    return [
        f"# Eval report: {fm['feature']} ({fm['run_type']} run), {fm['created_at'].replace('T', ' ').replace('Z', ' UTC')}",
        "",
        f"**Gate:** {gate_s} · **Validity:** {valid_s} · **Hard failures:** {a['hard_failures']} · "
        f"**Soft warnings:** {a['soft_warnings']} · **UNCLEAR:** {a['counts']['UNCLEAR']}/{a['n']}",
        "",
    ]


def _summary(fm, a) -> list[str]:
    c, d = a["counts"], a["decided"]
    sev = {s: sum(f["severity"] == s for f in a["findings"]) for s in ("blocker", "warning", "note")}
    inv = sorted(a["invariants"])
    lines = ["## 1. Summary", ""]
    lines.append(f"- **Tested:** `{fm['feature']}`, {len(a['cases'])} cases, {a['n']} case-trials."
                 + (f" Hard invariants: {', '.join(f'`{i}`' for i in inv)}." if inv else ""))
    head = f"- **Headline:** {c['PASS']}/{a['n']} PASS ({pct(a['pass_rate'])}, 95% CI {ci_str(a['pass_ci'])}). {c['FAIL']} FAIL, {c['UNCLEAR']} UNCLEAR."
    p = a["parent"]
    head += (f" Versus parent `{p['parent_id']}`: {pp(p['delta'])} on {p['shared']} shared cases ({p['verdict'].replace('_', ' ')})."
             if p else " No parent run, so no comparison.")
    lines.append(head)
    if d["has"]:
        lo = d["model_ci"][0] if d["model_ci"] else None
        lines.append(
            f"- **Evidence strength:** {d['model_trials']} of {a['n']} trials ({d['model_scenarios']} of {len(a['cases'])} scenarios) "
            f"were decided by the model; {d['other_trials']} went through a non-model path and test that path, not the prompt."
            + (f" Zero failures in the model-decided trials supports a true pass rate of at least {pct(lo)}, not 100%."
               if c["FAIL"] == 0 and lo is not None else ""))
    else:
        lo = a["scenario"]["ci"][0] if a["scenario"]["ci"] else None
        lines.append(f"- **Evidence strength:** {len(a['cases'])} scenarios; scenario-level 95% CI {ci_str(a['scenario']['ci'])}."
                     + (f" A clean run supports a true pass rate of at least {pct(lo)}, not 100%." if c["FAIL"] == 0 and lo is not None else ""))
    flaky = [cid for cid, x in a["cases"].items() if x["verdict_flaky"] or x["output_flaky"] or x["behavior_flaky_keys"]]
    lines.append(f"- **Instability:** {len(flaky)} case(s) varied across trials." if flaky else "- **Instability:** none; every case behaved identically across trials.")
    top = a["findings"][0]["title"] if a["findings"] else "nothing flagged"
    lines.append(f"- **Needs attention:** {sev['blocker']} blocker(s), {sev['warning']} warning(s), {sev['note']} note(s). Top item: {top} See section 3.")
    lines.append("")
    return lines


def _why(fm, ctx) -> list[str]:
    lines = ["## 2. Why this run", "", "**Hypothesis** (written before the run, hash locked "
             f"`{fm['hypothesis_hash'][:19]}…`):", ""]
    lines += [f"> {ln}" for ln in fm["hypothesis"].splitlines() or [""]]
    lines.append("")
    if ctx.get("change_note"):
        lines += ["**What changed** (stated by the agent before the run): " + ctx["change_note"], ""]
    if ctx.get("refuted_if"):
        lines += ["**What would refute it:** " + ctx["refuted_if"], ""]
    if ctx.get("diff_stat"):
        lines += [f"**Code changes since the parent run** (`git diff --stat`):", "", fence("\n".join(ctx["diff_stat"])), ""]
    return lines


def _findings(a) -> list[str]:
    lines = ["## 3. Needs attention", ""]
    if not a["findings"]:
        return lines + ["No findings.", ""]
    lines += ["| # | Severity | Finding | Cases | Triage question |", "|---|---|---|---|---|"]
    for i, f in enumerate(a["findings"], 1):
        lines.append(f"| {i} | {f['severity']} | **{cell(f['title'])}** {cell(f['detail'])} | {cell(case_list(f['cases']))} | {cell(f['question'])} |")
    return lines + [""]


def _provenance(fm, ctx) -> list[str]:
    rows = [
        ("System under test", f"`{ctx['spec']['adapter']['command']}`"),
        ("SUT model", f"`{fm.get('sut_model')}`" if fm.get("sut_model") else "not reported (adapter `meta.model`)"),
        ("Prompt", (f"`{fm.get('prompt_version')}` " if fm.get("prompt_version") else "") + (f"(`{fm['prompt_hash']}`)" if fm.get("prompt_hash") else "no prompt files hashed")),
        ("Config hash", f"`{fm['config_hash']}`" if fm.get("config_hash") else "no config files hashed"),
        ("Git", f"`{fm.get('git_sha')}`, " + ("dirty tree" if fm.get("git_dirty") else "clean tree") if fm.get("git_sha") else "not a git repository"),
        ("Golden set", f"{fm['golden_count']} of {fm['cases_available']} cases (`{fm['golden_set_hash']}`)"),
        ("Trials per case", fm["trials_per_case"]),
        ("Judge", f"`{fm['judge_model']}` (requested `{fm['judge_requested_model']}`), tier {fm['judge_tier']}, prompt `{fm['judge_prompt_hash']}`, bundle spec v{fm['bundle_spec_version']}"),
        ("Judge isolation", "sealed bundle, no tools, empty working directory, one case per call, random order"),
        ("Reproduce", f"`edd run {fm['feature']} --hypothesis-file <file>`" + (" --gate" if fm["run_type"] == "gate" else "") + f" at `{fm.get('git_sha')}`"),
    ]
    return ["## 4. Configuration and provenance", "", "| Field | Value |", "|---|---|"] + [f"| {k} | {v} |" for k, v in rows] + [""]


def _results(a, trials) -> list[str]:
    c, n = a["counts"], a["n"]
    lines = ["## 5. Results", "", "| Verdict | Count | Share |", "|---|---|---|"]
    lines.append(f"| PASS | {c['PASS']} | {pct(a['pass_rate'])} (CI {ci_str(a['pass_ci'])}) |")
    lines.append(f"| FAIL | {c['FAIL']} | {pct(c['FAIL'] / n if n else 0)} |")
    lines.append(f"| UNCLEAR | {c['UNCLEAR']} | {pct(a['unclear_rate'])} |")
    lines.append("")
    if a["invariants"]:
        lines += ["**Hard invariants**", "", "| Invariant | Cases | Trials | Model-decided trials | Violations | UNCLEAR |", "|---|---|---|---|---|---|"]
        for name, v in a["invariants"].items():
            lines.append(f"| `{name}`{' — ' + cell(v['description']) if v['description'] else ''} | {v['cases']} | {v['trials']} | {v['model_decided_trials']} | {v['violations']} | {v['unclear']} |")
        lines.append("")
    soft_rows = [r for t in trials for r in t.get("criteria", []) if r["severity"] == "soft"]
    if soft_rows:
        met = sum(r["met"] is True for r in soft_rows)
        lines += [f"**Soft expectations:** met in {met}/{len(soft_rows)} evaluations; misses are warnings and do not gate.", ""]
    lines += ["**By kind**", "", "| Kind | PASS / trials |", "|---|---|"]
    lines += [f"| {k} | {v['pass']}/{v['trials']} |" for k, v in a["by_kind"].items()]
    if a["by_tag"]:
        lines += ["", "**By tag**", "", "| Tag | PASS / trials |", "|---|---|"]
        lines += [f"| {k} | {v['pass']}/{v['trials']} |" for k, v in a["by_tag"].items()]
    return lines + [""]


def _evidence(a, goldens) -> list[str]:
    d, s = a["decided"], a["scenario"]
    lines = ["## 6. Evidence strength", ""]
    if d["has"]:
        lines += ["| Decided by | Scenarios | Trials | What it tests |", "|---|---|---|---|",
                  f"| Model (judge-evaluated) | {d['model_scenarios']} | {d['model_trials']} | The prompt and model |",
                  f"| Other path (e.g. a deterministic guard) | {d['other_scenarios']} | {d['other_trials']} | That path's own rules |", ""]
    else:
        lines += ["The adapter did not report `meta.decided_by`, so all trials are treated as model-decided.", ""]
    lines.append(f"- **Effective sample size:** repeats of one scenario are not independent. Scenario-level (all trials PASS): {s['pass']}/{s['n']}, 95% CI {ci_str(s['ci'])}.")
    if d["has"] and d["model_scenarios"]:
        lines.append(f"- **Model-decided scenarios:** {d['model_scen_pass']}/{d['model_scenarios']} fully passing, 95% CI {ci_str(d['model_scen_ci'])}; trial level {d['model_pass']}/{d['model_trials']}, CI {ci_str(d['model_ci'])}.")
        lines.append(f"- **Stability (model-decided):** {d['stable_model_scenarios']} of {d['model_scenarios']} scenarios identical across trials in verdict, output and observed behavior.")
    if s["ci"]:
        lines.append(f"- **What a clean run can and cannot show:** a true pass rate as low as {pct(s['ci'][0])} is still consistent with this sample.")
    thin = sorted(t for t, v in a["by_tag"].items() if sum(1 for g in goldens.values() if t in g.tags and g.id in a["cases"]) < 3)
    if thin:
        lines.append(f"- **Tags covered by fewer than 3 cases:** {', '.join(f'`{t}`' for t in thin)}.")
    return lines + [""]


def _comparison(fm, a) -> list[str]:
    p = a["parent"]
    lines = ["## 7. Comparison to parent", ""]
    if not fm.get("parent"):
        return lines + ["No parent: first run recorded for this feature, so no deltas, flips, or stability changes are computed.", ""]
    if not p:
        return lines + [f"Parent `{fm['parent']}` shares no cases with this run, so no comparison is possible.", ""]
    pfm = p["parent_fm"]
    lines += [f"Parent: `{p['parent_id']}`. Compared on {p['shared']} shared cases ({p['only_parent']} only in parent, {p['only_new']} only in this run).", "",
              "| Metric | Parent | This run | Delta | 95% CI of delta | Verdict |", "|---|---|---|---|---|---|",
              f"| Pass rate (shared cases) | {pct(p['parent_pass_rate'])} | {pct(p['new_pass_rate'])} | {pp(p['delta'])} | [{p['ci'][0] * 100:+.1f}, {p['ci'][1] * 100:+.1f}] pp | {p['verdict'].replace('_', ' ')} |",
              f"| Pass rate (whole run) | {pct(pfm.get('pass_rate'))} | {pct(a['pass_rate'])} | | | |",
              f"| Hard failures | {pfm.get('hard_failures', 'n/a')} | {a['hard_failures']} | | | |",
              f"| System cost per run | {money(pfm.get('cost_usd'))} | {money(a['cost']['sut'])} | "
              + (f"{p['cost_delta_pct']:+.1f}%" if p.get("cost_delta_pct") is not None else "n/a") + " | | |",
              f"| p95 latency | {ms(pfm.get('latency_p95_ms'))} | {ms(a['cost']['p95'])} | "
              + (f"{p['p95_delta_ms']:+.0f} ms" if p.get("p95_delta_ms") is not None else "n/a") + " | | |", ""]
    fmt = lambda xs: ", ".join(f"`{x['case']}` ({x['before']} → {x['after']})" for x in xs) or "none"
    lines += [f"**Flips to PASS:** {fmt(p['to_pass'])}", f"**Flips away from PASS:** {fmt(p['to_fail'])}"]
    stab = ", ".join(f"`{x['case']}` ({x['before']} → {x['after']}, {x['before_ratio']} → {x['after_ratio']})" for x in p["stability_changes"]) or "none"
    return lines + [f"**Stability changes:** {stab}", ""]


def _matrix(a, goldens) -> list[str]:
    cases = a["cases"]
    show_decided = a["decided"]["has"]
    label_mode = all(all(len(o) <= 40 for o in c.get("outputs", [])) for c in cases.values()) and any(c.get("outputs") for c in cases.values())
    head = ["Case", "Kind", "Tags", "Trials", "Stability"] + (["Decided by"] if show_decided else []) + (["Outputs"] if label_mode else [])
    lines = ["## 8. Case matrix", "", "Legend: ✅ PASS · ❌ FAIL · ❔ UNCLEAR", "", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for cid, c in sorted(cases.items()):
        g = goldens[cid]
        stab = []
        if c["verdict_flaky"]:
            stab.append("verdict flaky")
        if c["output_flaky"]:
            stab.append("output flaky")
        if c["behavior_flaky_keys"]:
            stab.append("behavior flaky (" + ", ".join(c["behavior_flaky_keys"]) + ")")
        row = [f"`{cid}`", g.kind, ", ".join(g.tags), c["icons"], "; ".join(stab) or "stable"]
        if show_decided:
            row.append(", ".join(c["decided_by"]) or "model")
        if label_mode:
            row.append(" → ".join(f"`{cell(o)}`" for o in c["outputs"]))
        lines.append("| " + " | ".join(cell(x) if i not in (0,) else x for i, x in enumerate(row)) + " |")
    return lines + [""]


def _case_details(a, goldens, grouped) -> list[str]:
    lines = ["## 9. Case details", ""]
    for cid in sorted(grouped):
        g, ts, c = goldens[cid], grouped[cid], a["cases"][cid]
        lines += [f"### {cid}: {g.title or cid}", ""]
        if g.description or g.why_added:
            lines += [f"**Why this case exists:** {g.description or g.why_added}", ""]
        meta = [f"kind {g.kind}"] + ([f"source {g.source}"] if g.source else []) + ([f"tags {', '.join(g.tags)}"] if g.tags else []) + (["pinned"] if g.pinned else [])
        lines.append("**Invariants:** " + (", ".join(f"`{i}`" for i in g.invariants) or "none") + " · " + " · ".join(meta))
        lines.append("")
        lines += block("Input", g.input)
        if g.expected:
            lines += block("Expected", g.expected)
        lines += ["**Rubric**", ""] + [f"- [{r.severity}] {r.text}" for r in g.criteria] + [""]
        lines += ["| Trial | Verdict | Source | Scorers | Latency | Cost |", "|---|---|---|---|---|---|"]
        for t in ts:
            sc = " · ".join(f"{k} {'✅' if v else '❌'}" for k, v in t["scorers"].items())
            lines.append(f"| {t['trial']} | {ICON[t['verdict']]} {t['verdict']} | {t['verdict_source']} | {cell(sc)} | {ms(t['latency_ms'])} | ${t['cost_usd']:.4f} |")
        lines.append("")
        for t in ts:
            lines.append(f"**Trial {t['trial']}**")
            lines.append("")
            lines += block("Output", t["output"]) if t["output"] or t["verdict_source"] != "adapter" else []
            if t["verdict_source"] != "judge":
                note = "; ".join(f"{k}: {v}" for k, v in t["scorer_notes"].items() if not t["scorers"].get(k, True))
                lines += [f"Not judged. {t['verdict_source']} failure: {note}", ""]
            else:
                for r in t["criteria"]:
                    mark = {True: "✅ met", False: "❌ not met", None: "❔ undecided"}[r["met"]]
                    ev = f" — evidence: “{r['evidence']}”" if r["evidence"] else ""
                    lines.append(f"- {r['id']} [{r['severity']}] {mark}: {r['criterion']}{ev}")
                lines.append("")
                if t.get("judge_rationale"):
                    lines += [f"Judge rationale: _{t['judge_rationale']}_", ""]
                if not t.get("judge_valid", True):
                    lines += [f"Judge response rejected after {t['judge_attempts']} attempts: {t['judge_invalid_reason']}", ""]
            if t.get("meta"):
                lines += ["Adapter meta: " + ", ".join(f"`{k}`={v!r}" for k, v in t["meta"].items()), ""]
            lines += [f"<sub>bundle `{t.get('bundle_hash') or 'n/a'}` · judge cost ${t.get('judge_cost_usd', 0):.4f} · judge attempts {t.get('judge_attempts', 0)}</sub>", ""]
        notes = []
        if c["verdict_flaky"]:
            notes.append(f"verdicts differ across trials ({c['ratio']} PASS)")
        if c["output_flaky"]:
            notes.append("outputs differ with the same verdict: " + " / ".join(f"`{cell(t['output'])}`" for t in ts))
        for k in c["behavior_flaky_keys"]:
            notes.append(f"observed behavior `{k}` changed: " + " / ".join(repr((t.get('meta') or {}).get(k)) for t in ts))
        if notes:
            lines += ["**Cross-trial note:** " + "; ".join(notes) + ".", ""]
    return lines


def _validity(fm, a, canary_records) -> list[str]:
    can, j = a["canary"], a["judge"]
    lines = ["## 10. Judge and validity", "", "| Check | Result |", "|---|---|"]
    lines.append(f"| Canaries | {can['caught']}/{can['total']} caught (FAIL), {can['passed_wrongly']} passed wrongly, {can['unclear']} UNCLEAR"
                 + ("; **false-pass rate unmeasured**" if can["total"] == 0 else "") + " |")
    lines.append(f"| Blinding leak check (known identifiers in bundles) | {'clean' if not a['leaks'] else 'LEAK: ' + ', '.join(a['leaks'])} |")
    lines.append("| Statistical leak test (judge guessing the author) | not implemented yet |")
    lines.append("| Double-judged cases and agreement | none (single judge call per case) |")
    lines.append(f"| Judge calls | {j['calls']}; {j['retried']} retried, {j['invalid']} rejected after retry, {j['inconsistent']} self-inconsistent |")
    lines.append(f"| UNCLEAR rate | {a['counts']['UNCLEAR']}/{a['n']} ({pct(a['unclear_rate'])}) |")
    lines.append("| Human calibration set | none yet |")
    lines.append("")
    if canary_records:
        lines += ["**Canaries**", "", "| Canary | For case | Mode | Verdict | Outcome |", "|---|---|---|---|---|"]
        for c in canary_records:
            outcome = {"FAIL": "caught", "PASS": "**passed wrongly**", "UNCLEAR": "judge undecided"}[c["verdict"]]
            lines.append(f"| `{c['canary_id']}` | `{c['for_case']}` | {cell(c['mode'])} | {ICON[c['verdict']]} {c['verdict']} | {outcome} |")
        lines.append("")
    return lines


def _cost(fm, a) -> list[str]:
    c, spec_b = a["cost"], fm.get("_budgets", {})
    lines = ["## 11. Cost and latency", "", "| | This run | Budget |", "|---|---|---|",
             f"| System under test cost | {money(c['sut'])} | {money(spec_b.get('max_cost_usd_per_run')) if spec_b.get('max_cost_usd_per_run') is not None else ''} |",
             f"| Judge cost | {money(c['judge'])} | |", f"| **Total** | **{money(c['total'])}** | |",
             f"| System latency p50 / p95 | {ms(c['p50'])} / {ms(c['p95'])} | {('p95 ' + ms(spec_b['p95_latency_ms'])) if spec_b.get('p95_latency_ms') is not None else ''} |", ""]
    if c["top_cases"] and c["sut"] > 0:
        lines += ["Costliest cases: " + ", ".join(f"`{cid}` ({money(v)})" for cid, v in c["top_cases"]) + ".", ""]
    return lines


def _agent_block(a) -> list[str]:
    lines = ["## 12. Agent interpretation", "", AGENT_BEGIN,
             "_To be written by the coding agent after the run. This is interpretation, not measured data. Answer each finding's triage question; do not edit any other section._", "",
             "**Hypothesis outcome:** pending (`edd annotate <feature> <report> --outcome confirmed|refuted|inconclusive`)", ""]
    if a["findings"]:
        lines.append("**Triage of findings**")
        lines += [f"- Finding {i}: pending" for i, _ in enumerate(a["findings"], 1)]
        lines.append("")
    lines += ["**Next step:** pending", AGENT_END, ""]
    return lines


def _appendix(fm) -> list[str]:
    return ["## 13. Appendix", "",
            f"- Sidecar: `{fm['id']}.cases.jsonl` (one line per trial and per canary: scorer results, verdict, criteria with quoted evidence, rationale, bundle hash, cost, latency, adapter `meta`).",
            "- **PASS** = every hard criterion met, each with a verbatim quote from the output. **FAIL** = a hard criterion unmet, a scorer veto, or an adapter error. **UNCLEAR** = the judge could not decide, or its response could not be verified; counts as non-pass. Unmet soft criteria are warnings.",
            "- Intervals: Wilson 95% for proportions; seeded paired bootstrap (resampling cases) for deltas.",
            "- Integrity: `facts_hash` covers the engine-authored sections and frontmatter. `edd verify` recomputes it. Section 12 and the lifecycle log are excluded.",
            "", FACTS_END, "", "## Lifecycle", "", f"- {fm['created_at']}: run created ({fm['run_type']})", ""]


def render_report(fm: dict, ctx: dict) -> str:
    """Return the full report text (frontmatter + body) with facts_hash filled in."""
    a, goldens, grouped = ctx["analysis"], ctx["goldens"], ctx["grouped"]
    for cid, c in a["cases"].items():
        c["outputs"] = [t["output"] for t in grouped[cid]]
    fm_view = {**fm, "_budgets": ctx["spec"]["budgets"]}
    parts = (_banner(fm, a, ctx["spec"]) + _summary(fm, a) + _why(fm, ctx) + _findings(a) + _provenance(fm, ctx)
             + _results(a, ctx["trials"]) + _evidence(a, goldens) + _comparison(fm, a) + _matrix(a, goldens)
             + _case_details(a, goldens, grouped) + _validity(fm, a, ctx["canary_records"]) + _cost(fm_view, a)
             + _agent_block(a) + _appendix(fm))
    body = "\n".join(parts)
    fm = {**fm, "facts_hash": compute_facts_hash(fm, body)}
    return join_frontmatter(fm, body)


def render_diff(feature: str, a_id: str, b_id: str, cmp_: dict | None) -> str:
    if not cmp_:
        return f"No shared cases between `{a_id}` and `{b_id}`; nothing to compare.\n"
    fmt = lambda xs: ", ".join(f"{x['case']} ({x['before']} → {x['after']})" for x in xs) or "none"
    stab = ", ".join(f"{x['case']} ({x['before']} → {x['after']})" for x in cmp_["stability_changes"]) or "none"
    return "\n".join([
        f"# {feature}: {a_id} → {b_id}", "",
        f"Compared on {cmp_['shared']} shared cases ({cmp_['only_parent']} only in the first, {cmp_['only_new']} only in the second).", "",
        f"- Pass rate on shared cases: {pct(cmp_['parent_pass_rate'])} → {pct(cmp_['new_pass_rate'])} ({pp(cmp_['delta'])}, 95% CI [{cmp_['ci'][0] * 100:+.1f}, {cmp_['ci'][1] * 100:+.1f}] pp): **{cmp_['verdict'].replace('_', ' ')}**",
        f"- Flips to PASS: {fmt(cmp_['to_pass'])}", f"- Flips away from PASS: {fmt(cmp_['to_fail'])}", f"- Stability changes: {stab}", ""])
