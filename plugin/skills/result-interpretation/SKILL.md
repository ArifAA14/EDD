---
name: result-interpretation
description: Use after an eval run completes, to read the report correctly: noise vs signal, flips, UNCLEAR cases, cost and latency tradeoffs, and what to do next.
---

# Reading an eval report

Start with the report's banner, summary, and "Needs attention" sections (roughly the first 60 lines). Open case details only for flagged cases. Engine-authored sections are facts; you may only write in the agent-interpretation section, and you answer each finding's triage question there.

Read in this order:

1. **Validity.** If any canary passed, or the leak check failed, the run is invalid. Stop and fix the harness problem; do not interpret the numbers.
2. **Verdict counts.** PASS, FAIL, UNCLEAR. UNCLEAR counts as non-pass. A high UNCLEAR rate means the rubric or golden is ambiguous; raise it with the human rather than tuning around it.
3. **Delta versus parent.** If the verdict is `within_noise`, the change did not demonstrably help or hurt, whatever the raw percentages say. Do not claim improvement.
4. **Flips.** Which cases moved to FAIL? Triage each: real bug, bad golden, or bad scorer. Only a real bug is fixed in the code. Never "fix" a regression by editing a grader, rubric, or golden.
5. **Cost and latency.** A small quality gain at a large cost increase is not a win unless the spec budget allows it.

Use `eval diff <report-a> <report-b>` for any comparison. Do not compute statistics by hand.

## Next step

- Confirmed and gate passes: ask the human to promote the baseline.
- Refuted or within noise: revise the hypothesis, or revert via the parent chain.
- Regressions on pinned cases: hard stop; fix before anything else.
