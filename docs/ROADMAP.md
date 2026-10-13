# Roadmap

| Phase | Deliverable | Done when |
|---|---|---|
| 0 | Specs: report schema, golden format, adapter contract, judge bundle, skills map | One report and one golden can be hand-written and look right |
| 1 | Engine without Claude Code: `eval run`, `eval promote`, `eval diff` | Runs a real feature and produces a correct report with confidence intervals |
| 2 | Plugin: hooks, `/eval-spec`, `/eval-run`, hypothesis-before-run flow | The agent cannot finish a task without a passing gate |
| 3 | Bootstrap and golden mining | A new feature goes from zero to a first eval in one session |
| 4 | Judge calibration, flip analysis, cost dimension | Judge agreement is tracked, regressions listed by case |
| 5 | Dogfood on a real project, then harden | Two or three real features run end to end |

## Open decisions

1. **Engine language.** Default Python. Confirm.
2. **Dogfood project.** Which real project does Phase 5 target? Pick early so the schema stays honest.
3. **Gate override.** Hard block, or block with a logged human override?
4. **Judge model choice.** Decided by experiment: run the canary and calibration sets through Sonnet, Opus, and Fable; compare false-pass rate, human agreement, and cost.
5. **Folder root.** `evals/` (default here) vs `docs/`.
