# EDD Harness

A Claude Code harness for **eval-driven development**: the agent cannot declare a change "done" without eval evidence, judged blind by an independent judge agent.

TDD asserts exact outputs. Agents are stochastic and judged on qualities like "did it accomplish the task", so the loop becomes:

1. Write the eval spec (task set, rubric, thresholds, budgets) **before** implementing.
2. State a **hypothesis** before every run.
3. Run N trials. Cheap scorers can veto; only the judge can pass.
4. Compare against the blessed baseline with paired statistics.
5. Record the result as a markdown report with a parent pointer, then promote or revert.

## Principles

- **Local and file-based.** No hosted eval platform. Reports are markdown in git, diffable and reviewable in PRs.
- **Scorers veto, the judge passes.** A scorer failure is an automatic FAIL. A scorer pass means nothing alone. Every case that clears scorers goes to the judge, and PASS comes only from the judge.
- **Blind judging.** The judge never sees who or what produced the output, how, or why. No agent name, model, hypothesis, diff, baseline, or run type.
- **Gating, not reporting.** A Stop hook blocks completion without a passing gate run.
- **Protected eval surface.** Holdout goldens, graders, rubrics, and the judge definition are not editable or readable by the coding agent.
- **Hypothesis before run.** Every report records what was expected and whether it was confirmed or refuted.

## Layout

```
docs/spec/        Phase 0 specs (report schema, golden format, adapter contract, judge bundle, skills map)
engine/           Python CLI engine: eval init | run | promote | diff
plugin/           Claude Code plugin: hooks, skills, judge agent
examples/         Sample feature showing the per-feature eval layout
```

Per-feature layout inside a project that uses the harness:

```
evals/<feature>/
  spec.md            task, scorers, rubric, thresholds, cost/latency budgets
  goldens/dev/       agent may read and iterate against these
  goldens/holdout/   gate runs only; protected
  graders/           scorers and rubrics; protected once approved
  results/           <utc-ts>-<hash>.md + .cases.jsonl
  baseline.md        changes only on promotion
  INDEX.md           last 5 runs + current baseline; the agent reads this first
```

## Status

Phase 0 (spec). See `docs/spec/` and `docs/ROADMAP.md`.
