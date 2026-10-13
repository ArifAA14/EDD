# Roadmap

| Phase | Deliverable | Done when |
|---|---|---|
| 0 | Specs: report schema, golden format, adapter contract, judge bundle, skills map | One report and one golden can be hand-written and look right |
| 1 | Engine without Claude Code: `edd run`, `edd promote`, `edd diff` | **Built.** Demo project runs end to end with the real judge; 46 tests. Real-project dogfood still pending |
| 2 | Plugin: hooks, `/eval-spec`, `/eval-run`, hypothesis-before-run flow | The agent cannot finish a task without a passing gate |
| 3 | Bootstrap and golden mining | A new feature goes from zero to a first eval in one session |
| 4 | Judge calibration, flip analysis, cost dimension | Judge agreement is tracked, regressions listed by case |
| 5 | Dogfood on a real project, then harden | Two or three real features run end to end |

## Decisions made

1. Engine language: Python.
2. Judge call: Claude Code headless (`claude -p`), no tools, prompt owned by the engine.
3. First dogfood: the reply classifier (demo project stands in until pointed at real code).
4. Gate policy: block, with logged human override (invalid and dev runs cannot be overridden).

## Open decisions

1. **Judge model choice.** Defaults are dev `sonnet`, gate `fable`. Confirm by experiment: run canaries and a calibration set through Sonnet, Opus and Fable; compare false-pass rate, human agreement, cost.
2. **Folder root.** `evals/` (default here) vs `docs/`.
3. **Real dogfood target.** Which repo and code path hosts the reply classifier adapter.
