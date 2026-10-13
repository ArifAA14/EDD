# Report schema

One report per eval run, at `evals/<feature>/results/<utc-ts>-<shorthash>.md`, with a sidecar `<utc-ts>-<shorthash>.cases.jsonl`.

- Timestamp is UTC, format `YYYYMMDDTHHMMSSZ`. The short hash suffix avoids collisions across branches.
- Reports are immutable once written. Only `status` and `promoted` may be amended by `eval promote`.

## Frontmatter

```yaml
---
id: 20261013T075500Z-a1b2c3
feature: retrieval
parent: 20261012T140200Z-9f8e7d      # report this run was compared to; null for the first run
run_type: dev                        # dev | gate
status: complete                     # complete | invalid | aborted
promoted: false                      # true only after `eval promote`

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
bundle_spec_version: 1

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
---
```

## Body sections

1. `## Why this run`: the hypothesis, what changed, and why it was run. Written by the agent before the run.
2. `## Outcome`: three-way counts, deltas, hypothesis confirmed or refuted, in prose.
3. `## Regressions and flips`: cases that changed verdict versus parent, by opaque case id.
4. `## UNCLEAR cases`: each with the judge's stated reason, awaiting human resolution.
5. `## Canaries and validity`: whether the run is valid. A passed canary invalidates the run.
6. `## Cost and latency`

## Sidecar `cases.jsonl`

One line per case per trial:

```json
{"case_id":"c_7f3a","trial":1,"scorers":{"schema_valid":true,"timeout_ok":true},"scorer_veto":false,"verdict":"PASS","evidence":"<quoted span from output>","rationale":"<one line>","bundle_hash":"sha256:...","latency_ms":2040,"cost_usd":0.031}
```

Verdicts are `PASS`, `FAIL`, `UNCLEAR`. A scorer veto records `FAIL` with `verdict_source: "scorer"` and skips the judge.

## Parent chain and baseline

- `parent` forms a chain. The head is the report no other report points to, derived from the chain, never from a mutable HEAD file.
- `evals/<feature>/baseline.md` names the blessed baseline report id and changes only on `eval promote`.
- A failed or refuted run is recorded but never becomes the baseline.
- Revert means: check out `git_sha` of the target baseline and restore its prompt, config, and golden set from the recorded hashes.

## Gate rules (defaults)

A gate run passes only if all hold:

1. Run is valid (all canaries caught, bundle leak check clean).
2. No regression on any previously-fixed case.
3. Pass rate meets the spec threshold, and the delta versus baseline is not `regressed`.
4. UNCLEAR rate is under the spec limit. UNCLEAR counts as non-pass.
5. Cost and latency stay within spec budgets.
