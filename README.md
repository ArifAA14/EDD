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
engine/           Python engine and `edd` CLI: run, diff, verify, annotate, override, promote
plugin/           Claude Code plugin: hooks and skills (the judge lives in the engine, not the plugin)
examples/         Sample feature, example report, and a runnable demo project
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

## Quickstart

```bash
cd engine && pip install -e . && pytest        # 46 tests, no network or judge needed
edd run <feature> --hypothesis "what you expect, and what would refute it"
edd run <feature> --gate --hypothesis "..."     # holdout + pinned goldens, strongest judge
edd diff <feature> <report-a> <report-b>
edd verify <feature> <report>                   # detects edited engine facts
edd promote <feature> <report>                  # needs passing gate or logged override
```

The judge is `claude -p` (headless, no tools). A full end-to-end replay with the real judge (about 1.5 min, about $1):

```bash
examples/demo-project/run_demo.sh
```

Sample output of that replay is in `examples/demo-project/sample-output/`.

## Status

Phase 1 (engine) is built: run, diff, verify, annotate, override, promote, blind judge, canaries, gate. Not yet: `edd init`, `edd revert`, wiring the Stop hook, double-judge on borderline cases, calibration set, statistical leak test. See `docs/ROADMAP.md`.
