---
feature: sample-feature
adapter:
  command: "python -m myapp.eval_entry"
  timeout_s: 60
scorers:            # objective checks only; they can veto, never pass
  - schema_valid
  - timeout_ok
  - no_forbidden_tools
invariants:         # named hard invariants; any violation fails the gate
  never_wrong_example: "A request with no matching result never gets an invented answer."
thresholds:
  min_pass_rate: 0.85
  max_unclear_rate: 0.05
budgets:
  max_cost_usd_per_run: 5.00
  p95_latency_ms: 8000
trials_per_case: 3
judge:
  dev_model: <configure>
  gate_model: <configure>
---

## Job

Describe what the feature does and what a correct result looks like to a user.

## Failure modes

- Hallucinated answer when no result exists
- Wrong tool called
- Partial answer presented as complete

## Notes

This is a template. Copy it to `evals/<feature>/spec.md` in a project that uses the harness.
