# Report format (descriptive reports)

A report must let a reader who was not there answer five questions without opening anything else:

1. **Why** was this run done, and what did we expect?
2. **What exactly** ran (code, prompt, model, goldens, judge), so it can be reproduced or reverted?
3. **What happened**, per case and per trial, with the evidence?
4. **How much should we trust it?** Sample size, who actually decided each case, judge validity.
5. **What needs a human or agent to look at it next?**

`01-report-schema.md` defines the frontmatter and sidecar. This doc defines the body. A worked example is in `examples/reports/reply-classification-EXAMPLE.md`.

## Facts and interpretation are separate

- **Engine-authored sections** (everything except section 12) are generated from run data. The agent cannot edit them. `facts_hash` in the frontmatter covers them, so tampering is detectable by `edd diff` and the gate.
- **Agent-authored section 12** sits between `<!-- agent:begin -->` and `<!-- agent:end -->`. It holds interpretation, triage decisions, and the hypothesis outcome. It is labeled as such, so a reader never mistakes an opinion for a measurement.
- The hypothesis itself is written before the run, hashed, and shown in section 2 unchanged.

## Rules for every report

- **Every number carries its denominator**: `41/48 (85.4%)`, not `85.4%`.
- **Proportions carry a 95% interval** (Wilson for single runs, bootstrap for paired deltas).
- **Never truncate** inputs or outputs. Long ones go in `<details>` blocks; they are not shortened.
- **State who decided each case** (judge-evaluated model output vs. a deterministic path in the system under test) and report evidence strength accordingly.
- **Say what zero means.** "0 failures in 18 model-decided trials" supports a true pass rate of at least ~82%, not 100%. The report states this.
- **Report instability, not just pass/fail.** A case that passes with different labels across trials is a finding.
- **Hard vs soft.** Hard expectations gate; soft expectations warn. Both are counted separately.
- **The judge never sees any of this.** The report is for humans and the coding agent. Judge bundles follow `04-judge-bundle.md`.

## Reading order

The first ~60 lines (banner, summary, needs-attention) are all an agent should read by default. Everything below is reference, and per-case details open only for flagged cases.

## Sections

| # | Section | Purpose |
|---|---|---|
| 0 | **Banner** | Feature, run id, run type, date, gate result with reasons, validity |
| 1 | **Summary** | Five bullets: what was tested, headline result with interval, change vs parent, evidence strength, what needs attention |
| 2 | **Why this run** | Hypothesis (pre-run, hashed), what changed (diff stat), expected effect, what would refute it |
| 3 | **Needs attention** | Ranked findings: blocker, warning, note. Each: what, which cases, evidence, a triage question |
| 4 | **Configuration and provenance** | SUT model, prompt version and hash, git SHA, config and golden hashes, trials, adapter, judge model, tier, prompt hash, bundle spec version, reproduce command |
| 5 | **Results** | Verdict counts; per-invariant table; breakdown by kind and by tag |
| 6 | **Evidence strength** | Who decided each case, effective sample sizes, intervals, minimum detectable change, coverage gaps |
| 7 | **Comparison to parent** | Deltas with intervals, verdict, flips, stability changes, cost and latency deltas. If no parent, says so |
| 8 | **Case matrix** | One row per case: kind, tags, per-trial verdicts, stability, decided-by, cost, latency |
| 9 | **Case details** | Per case: title, why it exists, full input, expectation, rubric, and per trial: output, scorer results, judge criteria with quoted evidence, rationale, cost, latency, bundle hash |
| 10 | **Judge and validity** | Canaries, leak test, double-judge agreement, UNCLEAR rate, calibration status |
| 11 | **Cost and latency** | Totals, p50/p95, top cost cases, budgets, deltas |
| 12 | **Agent interpretation** | Agent-authored: findings accepted or disputed, triage class per flagged case, next step, hypothesis outcome |
| 13 | **Appendix** | Sidecar paths, verdict glossary, how to reproduce |

## Findings catalog

The engine raises these from rules, so reports surface problems consistently. Severity in brackets.

- **Pinned regression**: a pinned case failed [blocker]
- **Hard expectation failed** [blocker]
- **Canary passed / leak test failed**: run is invalid [blocker]
- **Regression vs parent** (case flipped to FAIL) [blocker for gate runs, warning for dev]
- **Judge-scorer conflict**: scorers all passed but judge FAILed, or the reverse [warning]
- **UNCLEAR cluster**: same rubric criterion causes UNCLEAR in 2+ cases [warning]
- **Verdict flaky**: different verdicts across trials of one case [warning]
- **Label or output flaky**: same verdict, materially different outputs across trials [note]
- **Soft expectation failed** [warning]
- **Behavior flaky**: an observed attribute (e.g. human-handoff flag) differs across trials [note]
- **Guard-heavy run**: more than a set share of trials never exercised the model [warning]
- **Thin coverage**: an invariant or tag has fewer than 3 model-decided cases [warning]
- **Near threshold**: pass-rate interval straddles the threshold [warning]
- **Cost or latency spike** vs parent or budget [warning]
- **Judge disagreement** on double-judged cases [warning]

Each finding includes a **triage question**, not an answer: "Is the label change between trials an ambiguity in the rubric, or instability in the prompt?" The agent answers it in section 12.

## Comparison table layout (when a parent exists)

```markdown
| Metric | Parent | This run | Delta | 95% CI of delta | Verdict |
|---|---|---|---|---|---|
| Pass rate | 40/48 (83.3%) | 41/48 (85.4%) | +2.1 pp | [-4.2, +8.3] | within noise |
| UNCLEAR rate | 3/48 | 2/48 | -1 | n/a | n/a |
| Hard-invariant violations | 0 | 0 | 0 | n/a | unchanged |
| Cost per run | $1.77 | $1.84 | +4.2% | n/a | within budget |
| p95 latency | 5.1 s | 5.4 s | +0.3 s | n/a | within budget |

**Flips (compared on the 46 shared cases):** to PASS: c_12a, c_88f, c_3d1. To FAIL: c_7f3a.
**Stability changes:** c_55b went from consistent to flaky (3/3 -> 2/3).
```
