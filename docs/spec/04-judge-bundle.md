# Judge bundle spec

The judge decides one thing: is this output correct for this input, per this rubric. It receives a **sealed bundle** assembled by the engine. The coding agent never writes or sees the judge's prompt.

## Invocation

- The engine invokes the judge headlessly: `claude -p --safe-mode --tools "" --no-session-persistence --output-format json --model <m> --system-prompt <prompt>`, run in an empty temp dir with the bundle on stdin. No tools, no repo access.
- The judge prompt lives in the engine package (`engine/src/edd/prompts/judge.md`), protected by the PreToolUse hook. There is no plugin-level judge agent, so the coding agent cannot spawn or edit the judge.
- Cost, duration and actual model are read from the CLI's JSON (`total_cost_usd`, `modelUsage`, `duration_ms`).
- One case per call, isolated context, random order, parallelizable.
- Structured output only.

## Bundle fields (allowed)

| Field | Content |
|---|---|
| `case_id` | Opaque id, re-randomized per run |
| `input` | The case input |
| `expected` | Golden expectation |
| `rubric` | `[{id, criterion}]` from the golden; severity tags (`[hard]`/`[soft]`) are stripped |
| `output` | The SUT output, scrubbed |
| `trace` | Normalized trace, only if the rubric depends on it |

## Never in the bundle

Agent or model names, the hypothesis, diffs, commit messages, report history, baseline scores, run type (dev or gate), judge tier, the existence of canaries or scorers, and any "better than before" framing. The judge grades absolutely; comparison happens later in the stats layer on stored verdicts.

## Scrubbing rules

1. Strip system prompts, agent and model identifiers, and repo or file paths from traces and outputs.
2. Remove self-references ("As the planner agent...") and stack traces with paths.
3. Normalize tool names to generic labels when names reveal the author.
4. Canaries pass through the identical pipeline and must match real outputs in format, length, and style.

## Judge output schema

```json
{
  "verdict": "PASS | FAIL | UNCLEAR",
  "criteria": [{"criterion": "...", "met": true, "evidence": "<quoted span>"}],
  "evidence": "<quoted span supporting the verdict>",
  "rationale": "<one line>"
}
```

- The judge returns per-criterion `met` (`true | false | null`) with a verbatim `evidence` quote. The engine derives the verdict: any hard criterion `false` -> FAIL; else any hard `null` -> UNCLEAR; else PASS. Soft misses become warnings.
- `met: true` without a quote that appears in the output/trace (whitespace, case and curly-quote normalized) is rejected with one retry carrying feedback, then recorded UNCLEAR with `judge_valid: false`.
- A top-level judge PASS contradicted by the criteria is flagged inconsistent; the derived verdict wins.
- Adapter `meta` (decided_by, model, prompt_version) is shown in reports and never enters the bundle.
- UNCLEAR means "cannot decide from the evidence given". The gate treats UNCLEAR as non-pass.
- Planned (not yet implemented): borderline cases get a second judge run; disagreement becomes UNCLEAR.

## Judge validity

- **Canaries**: known-wrong outputs must be FAILed. A passed canary invalidates the run.
- **Calibration set**: human-labeled cases; agreement tracked per judge model and prompt hash.
- **PASS audit**: humans sample PASS verdicts, not only failures.
- **Judge change**: a new model or prompt hash requires re-running calibration before results are comparable.

## Leak test

A separate judge instance receives bundles and guesses which agent, model, or version produced them. Above-chance accuracy means the scrubber leaks. Planned; not yet in the test suite. Current tests check bundle shape and strict leak needles.

## Tiering

- Dev runs: cheaper judge on a case subset.
- Gate runs: strongest judge on all holdout cases.
- Escalation: UNCLEAR or disagreeing cases go to the strongest judge.
- Judge model is config, not hard-coded. The report records model id and prompt hash.

## Known limit

Scrubbing removes metadata leakage, not stylistic fingerprints. Canaries and calibration are the backstop for measuring residual bias.
