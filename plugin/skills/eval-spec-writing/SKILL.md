---
name: eval-spec-writing
description: Use before implementing or changing any feature that has AI behavior. Turns a feature into an eval spec (task set, scorers, rubric, thresholds, cost and latency budgets) before any code is written.
---

# Writing an eval spec

No implementation starts until `evals/<feature>/spec.md` exists and a human has approved it.

## Steps

1. **State the job.** One paragraph: what the feature does and what a correct result looks like to a user.
2. **List failure modes.** What does wrong look like? Hallucination, wrong tool, partial answer, unsafe output, slow, expensive. Each failure mode needs at least one golden and one rubric criterion.
3. **Write rubric criteria** that a reader can check from the output alone. Prefer "states the refund window as 30 days" over "answers accurately".
4. **Choose scorers for objective checks only**: schema validity, timeout, forbidden tool calls, cost budget. Scorers can only veto. Never write a scorer that decides correctness; the judge does that.
5. **Set thresholds and budgets**: minimum pass rate, maximum UNCLEAR rate, cost and latency limits.
6. **Propose goldens** across normal, edge, and adversarial kinds. Mark what is dev vs holdout. Ask the human to review.

## Do not

- Write a scorer a plausible-but-wrong output would pass (substring match, non-empty check, regex for a keyword).
- Edit an approved spec, scorer, or rubric to make a run pass. Propose the change to the human instead.
- Read `goldens/holdout/`.

See `docs/spec/` for formats.
