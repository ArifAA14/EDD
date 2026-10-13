# Skills map: skill vs hook vs engine

Rule: anything that must always hold is a **hook** or **engine** behavior. Anything that needs judgment is a **skill**. Skills are advisory; agents under pressure skip advice.

## Enforcement (hooks and engine)

| Rule | Mechanism |
|---|---|
| No "done" without a passing gate run | Stop hook |
| No reads of `goldens/holdout/` or judge internals | PreToolUse hook |
| No edits to `graders/`, rubrics, judge definition, bundle builder | PreToolUse hook |
| Judge invoked by engine, never by the coding agent | Engine |
| Bundle scrubbing and hashing | Engine |
| Confidence intervals, flip analysis, parent chain | Engine (`eval diff`) |
| Canary injection and validity check | Engine |
| Hypothesis recorded before run | Engine refuses `eval run` without one |

## Skills

| Skill | Purpose | Priority |
|---|---|---|
| `eval-spec-writing` | Turn a feature into tasks, scorers, rubric, thresholds, budgets | v1 |
| `hypothesis-and-run` | Pre-run ritual, run, record confirmed or refuted | v1 |
| `result-interpretation` | Noise vs signal, flips, cost explosions; call `eval diff`, never compute stats by hand | v1 |
| `golden-authoring` | Good cases, edge and adversarial coverage, source and why-added | later |
| `golden-mining` | Prod logs to candidate goldens, dedupe | later |
| `scorer-design` | Objective checks only; scorers veto, never pass; validated against canaries | later |
| `regression-triage` | Regressed case is a real bug, bad golden, or bad scorer; never fix by editing graders | later |
| `baseline-promotion-and-revert` | When to promote, how to walk the parent chain | later |
| `eval-bootstrap` | Cold-start interview from nothing to first eval | later |

Write the three v1 skills first, wire them to the hooks, run a real project through, and let observed agent mistakes decide which skills come next.

## Skills need evals too

Scenarios scored on agent behavior: Does it write a good hypothesis? Does it refuse to edit graders under pressure? Does it bootstrap a decent spec from a vague description? This is the Phase 5 dogfooding loop.
