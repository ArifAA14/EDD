---
name: hypothesis-and-run
description: Use whenever you are about to run an eval, or after changing a prompt, model, config, or code path covered by an eval. Enforces writing a hypothesis before the run and recording the outcome after.
---

# Hypothesis, run, record

## Before the run

Write the hypothesis in one or two sentences, with direction and magnitude where you can: "Reranking prompt change raises recall on empty-result cases; latency flat." Also state what would refute it.

Then run: `eval run <feature> --hypothesis "<text>"`. The engine refuses to run without one.

## After the run

Read `evals/<feature>/INDEX.md` and the new report. Do not compute statistics yourself; the report already has the intervals and flip analysis.

Record in the report whether the hypothesis was **confirmed**, **refuted**, or **inconclusive**. A refuted hypothesis is a useful result, not a failure to hide. Do not rewrite the hypothesis after seeing results.

## Do not

- Run repeatedly with small tweaks until something passes. Each run needs its own hypothesis, and the report history is visible.
- Treat a within-noise improvement as a win.
- Declare the task done without a passing gate run.
