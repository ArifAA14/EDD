# Report schema

One report per eval run, at `evals/<feature>/results/<utc-ts>-<shorthash>.md`, with a sidecar `<utc-ts>-<shorthash>.cases.jsonl`.

- Timestamp is UTC, format `YYYYMMDDTHHMMSSZ`. The short hash suffix avoids collisions across branches.
- Engine-authored facts are immutable once written (`facts_hash` detects edits; `edd verify` checks it). Mutable: `promoted`, `hypothesis_outcome`, `override`, `facts_hash` itself, the agent-interpretation block, and the `## Lifecycle` log after `<!-- facts:end -->`.
- Report id: `YYYYMMDDTHHMMSSZ-` + 3 hex (ms) + 4 random hex.

## Frontmatter

```yaml
---
id: 20261013T075500Z-a1b2c3
feature: retrieval
parent: 20261012T140200Z-9f8e7d      # report this run was compared to; null for the first run
run_type: dev                        # dev | gate
status: complete                     # complete | invalid | aborted
promoted: false                      # true only after `edd promote`

# Provenance: everything needed to reproduce or revert
git_sha: 4f2c9e1
git_dirty: false
config_hash: sha256:...
prompt_hash: sha256:...              # hash of the system-under-test prompt(s)
sut_model: <model id>                # model of the system under test
golden_set_hash: sha256:...
golden_count: 48
trials_per_case: 3

# Judge provenance
judge_model: <model id>
judge_prompt_hash: sha256:...
judge_tier: dev                      # dev | gate
judge_requested_model: sonnet        # alias requested; judge_model is what actually answered
judge_cost_usd: 0.42
bundle_spec_version: 1
seed: 1234                           # bootstrap + ordering seed
prompt_version: <from adapter meta>
cases_available: 48                  # cases in the spec's selected splits; partial runs are gate-ineligible
change_note: "<what changed since parent, engine-detected + agent-supplied>"
hypothesis_hash: sha256:...
findings: [...]                      # blocker | warning | note, each with a triage question
duration_s: 93.2

# Hypothesis (written BEFORE the run, resolved after)
hypothesis: "Reranking prompt change raises recall; latency flat."
hypothesis_outcome: confirmed        # confirmed | refuted | inconclusive

# Results
verdict_counts: {pass: 41, fail: 5, unclear: 2}
pass_rate: 0.854
pass_rate_ci95: [0.74, 0.93]
vs_parent:
  compared_cases: 46                 # intersection of cases when golden sets differ
  delta_pass_rate: 0.043
  delta_ci95: [-0.02, 0.10]
  verdict: within_noise              # improved | regressed | within_noise
  flips_to_pass: 3
  flips_to_fail: 1
cost_usd: 1.84
cost_delta_pct: 4.2
latency_p50_ms: 2100
latency_p95_ms: 5400
canaries: {total: 6, caught: 6, passed_wrongly: 0}
gate: {passed: false, reasons: ["delta within noise"]}
override: null                       # {by, reason} if a human overrode the gate
facts_hash: sha256:...               # covers all engine-authored sections; detects edits
hard_failures: 0                     # hard expectation violations (gate)
soft_warnings: 0                     # soft expectation misses (non-gating)
invariants:                          # named hard invariants from spec.md
  never_closed_on_interested: {cases: 10, trials: 20, model_decided_trials: 18, violations: 0, unclear: 0}
---
```

## Body sections

The body layout is defined in `06-report-format.md` (banner, summary, why this run, needs attention, provenance, results, evidence strength, comparison to parent, case matrix, case details, judge and validity, cost and latency, agent interpretation, appendix). Engine-authored sections are generated from run data; only the agent-interpretation section is agent-authored.

## Sidecar `cases.jsonl`

One line per case per trial, plus one per canary. `type` is `trial` or `canary`:

```json
{"type":"trial","case_id":"c_001","split":"dev","trial":1,"j_id":"j_3fa91c02","scorers":{"schema_valid":true,"timeout_ok":true},"scorer_veto":false,"verdict":"PASS","verdict_source":"judge","criteria":[{"id":"r1","severity":"hard","met":true,"evidence":"<verbatim quote>"}],"soft_misses":[],"judge_valid":true,"judge_attempts":1,"rationale":"<one line>","bundle_hash":"sha256:...","latency_ms":2040,"cost_usd":0.031,"judge_cost_usd":0.004,"meta":{"decided_by":"model"}}
```

- Verdicts: `PASS`, `FAIL`, `UNCLEAR`. A scorer or adapter failure records `FAIL` with `verdict_source: "scorer"` and skips the judge.
- `met` is `true | false | null`; `true` requires evidence that appears verbatim in the output or trace.
- `meta` comes from the adapter, appears in reports, and is never sent to the judge.
- Canary lines carry `canary_id`, `for` (golden id), `mode`, and `caught`.

## Parent chain and baseline

- `parent` forms a chain. The head is the report no other report points to, derived from the chain, never from a mutable HEAD file.
- `evals/<feature>/baseline.md` names the blessed baseline report id and changes only on `edd promote`.
- A failed or refuted run is recorded but never becomes the baseline.
- Revert means: check out `git_sha` of the target baseline and restore its prompt, config, and golden set from the recorded hashes.

## Gate rules (as implemented)

A gate run (`run_type: gate`: holdout plus pinned dev goldens by default; `--cases`/`--limit` are refused) passes only if all hold:

1. Run is valid: judge responses valid, canaries present and all caught. No canaries means the gate fails; a passed canary marks the run `invalid`.
2. No regression on any pinned golden (hard stop).
3. Zero violations of named hard invariants (any invariant UNCLEAR also blocks).
4. Pass rate >= `thresholds.min_pass_rate`; UNCLEAR rate <= `thresholds.max_unclear_rate`; guard share <= `max_guard_share`.
5. No statistically significant regression versus parent (paired bootstrap on shared cases; fewer than 10 shared cases is flagged underpowered rather than "no regression").
6. Cost per case-trial and latency stay within spec budgets.

Override and promote policy:

- `edd override` records a logged human override (by, reason). Invalid runs and dev runs cannot be overridden.
- `edd promote` requires `run_type: gate`, a verified `facts_hash`, and either a passing gate or a logged override. It rewrites `baseline.md` and sets `promoted: true`.
