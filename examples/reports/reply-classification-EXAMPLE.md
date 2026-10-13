---
id: 20260817T172058Z-ex0001
illustrative: true
feature: reply-classification
parent: null
run_type: dev
status: complete
promoted: false
git_sha: 4f2c9e1
git_dirty: false
config_hash: sha256:ex-config-0001
prompt_hash: sha256:ex-prompt-0001
prompt_version: reply-classification-v4
sut_model: openai/gpt-5.6-luna
golden_set_hash: sha256:ex-goldens-0001
golden_count: 14
trials_per_case: 2
judge_model: <judge model id>
judge_prompt_hash: sha256:ex-judge-0001
judge_tier: dev
bundle_spec_version: 1
hypothesis: "Stripping quoted history before the opt-out scan stops interested replies that quote our unsubscribe footer from being classified closed, without breaking genuine opt-outs."
hypothesis_outcome: confirmed
verdict_counts: {pass: 28, fail: 0, unclear: 0}
pass_rate: 1.0
pass_rate_ci95: [0.879, 1.0]
hard_failures: 0
soft_warnings: 0
invariants:
  never_closed_on_interested: {cases: 10, trials: 20, model_decided_trials: 18, violations: 0}
  genuine_optout_closes: {cases: 2, trials: 4, model_decided_trials: 0, violations: 0}
  bounce_detected: {cases: 2, trials: 4, model_decided_trials: 0, violations: 0}
canaries: {total: 0, caught: 0, passed_wrongly: 0}
gate: {passed: null, reasons: ["dev run; gate not evaluated"]}
facts_hash: sha256:ex-facts-0001
---

# Eval report: reply-classification (dev run), 2026-08-17 17:20 UTC

> **ILLUSTRATIVE EXAMPLE.** Scenario inputs, classifications, and model reasons come from a real earlier run of a reply-classification harness (14 scenarios, 2 repeats, `openai/gpt-5.6-luna`, prompt `reply-classification-v4`). Judge verdicts, quoted evidence, kinds and tags, hashes, git SHA, cost, latency, and the hypothesis wording were invented to show the format. Only 4 of 14 case-detail blocks are included; the rest follow the same layout.

**Gate:** not evaluated (dev run) · **Validity:** unvalidated, no canaries configured · **Hard failures:** 0 · **Soft warnings:** 0 · **UNCLEAR:** 0/28

## 1. Summary

- **Tested:** the shipped reply classifier against 14 scenarios x 2 trials (28 case-trials). The crown-jewel invariant is that an interested or question reply is never classified `closed`.
- **Headline:** 28/28 PASS (95% CI 87.9% to 100%). 0 hard failures, 0 soft warnings. No parent run, so no comparison.
- **Evidence strength is lower than 28/28 suggests.** Only 18 of the 28 trials (9 of 14 scenarios) were decided by the model. The other 10 trials went through a deterministic guard and test the guard, not the prompt. The invariant's model-decided evidence supports a true pass rate of at least ~82% (trial level) or ~70% (scenario level).
- **Instability:** 2 scenarios changed label between trials (R01, R04) and 1 changed its human-handoff flag (R06). All stayed inside accepted outcomes.
- **Needs attention:** no canaries exist, so a PASS cannot yet be checked against known-bad outputs. See section 3.

## 2. Why this run

**Hypothesis (written before the run, hash locked):**
Stripping quoted history before the opt-out scan stops interested replies that quote our unsubscribe footer from being classified `closed`, without breaking genuine opt-outs.

**What changed:** prompt `reply-classification-v3` to `v4`; the classifier now receives the thread, and the opt-out scan runs on newly written text only. _(illustrative diff stat: 3 files changed, +61 -14)_

**Expected effect:** 0 `closed` verdicts on R01, R02, R08, and the other interested or question scenarios; R10 and R11 still `closed`; R12 and R13 still `bounce`.

**What would refute it:** any `closed` on a scenario marked never-`closed`, or any genuine opt-out not `closed`.

## 3. Needs attention

| # | Severity | Finding | Cases | Triage question |
|---|---|---|---|---|
| 1 | blocker (gate runs) / warning (dev) | **No canaries configured.** Every PASS here is unchecked against known-wrong outputs, so the false-pass rate of the judge and rubrics is unknown. | all | Which failure modes need a canary? At minimum: an interested reply classified `closed`, an opt-out classified `interested`. |
| 2 | warning | **Thin coverage of the crown-jewel invariant.** 0 violations in 9 model-decided scenarios (18 trials). Lower bound 82.4% (trials) or 70.1% (scenarios). | R01-R09 | Is 9 enough for the invariant that caused a real incident? Candidates: Apple Mail and Outlook-web quote styles, long forwarded chains, non-English opt-out words in quoted text. |
| 3 | warning | **Guard-heavy run.** 10/28 trials (35.7%) never exercised the model. | R10-R14 | Expected by design for compliance and bounce paths. Should guard-decided cases be reported as a separate suite so they do not inflate the headline? |
| 4 | note | **Label flaky.** Same verdict, different label across trials: R01 `interested` then `question`; R04 `price_objection` then `question`. | R01, R04 | Is the accepted-label set intentionally broad, or should the rubric distinguish these labels? |
| 5 | note | **Behavior flaky.** R06 `not_now` with human-handoff `true` in trial 1 and `false` in trial 2 (no reason given in trial 2). No expectation covers it. | R06 | Should a deferral with a date require a human pause? If yes, add a criterion; if no, record it as intentional. |

## 4. Configuration and provenance

| Field | Value |
|---|---|
| System under test | shipped `classifyLeadReply` |
| SUT model | `openai/gpt-5.6-luna` |
| Prompt | `reply-classification-v4` (`sha256:ex-prompt-0001`) |
| Git | `4f2c9e1`, clean tree |
| Config hash | `sha256:ex-config-0001` |
| Golden set | 14 cases (`sha256:ex-goldens-0001`): 9 normal, 4 edge, 1 adversarial |
| Trials per case | 2 |
| Judge | `<judge model id>`, tier dev, prompt `sha256:ex-judge-0001`, bundle spec v1 |
| Judge isolation | sealed bundle, no tools, one case per call, random order |
| Reproduce | `edd run reply-classification --trials 2 --hypothesis-file <hash-locked file>` at `4f2c9e1` |

## 5. Results

| Verdict | Count | Share |
|---|---|---|
| PASS | 28 | 100% (CI 87.9 to 100) |
| FAIL | 0 | 0% |
| UNCLEAR | 0 | 0% |

**Hard invariants**

| Invariant | Cases | Trials | Model-decided trials | Violations |
|---|---|---|---|---|
| Never `closed` on interested, question, deferral, or objection | 10 | 20 | 18 | 0 |
| Genuine opt-out closes | 2 | 4 | 0 | 0 |
| Bounce detected | 2 | 4 | 0 | 0 |

**Soft expectations:** "should pause for a human" held in 10/10 applicable trials (R01, R03, R04, R05, R14).

**By kind:** normal 18/18, edge 8/8, adversarial 2/2.

**By tag:** quoted-footer 8/8 (R01, R02, R08, R14) · pricing 4/4 (R04, R07) · scheduling 2/2 (R05) · deferral 2/2 (R06) · one-word 2/2 · opt-out 4/4 · bounce 4/4 · forward-only 2/2.

## 6. Evidence strength

| Decided by | Scenarios | Trials | What it tests |
|---|---|---|---|
| Model (judge-evaluated) | 9 (R01-R09) | 18 | The prompt and model |
| Deterministic guard | 5 (R10-R14) | 10 | The guard rules |

- **Effective sample size:** repeats of one scenario are not independent. Scenario-level intervals are the conservative reading: all 14 scenarios, CI 78.5% to 100%; model-decided 9 scenarios, CI 70.1% to 100%.
- **Stability across trials (model-decided):** 6 of 9 scenarios identical in label and handoff flag; R01 and R04 changed label; R06 changed handoff flag.
- **Minimum detectable change:** with 9 model-decided scenarios, a drop of up to ~30 points in true pass rate would still be consistent with a clean run. Do not read this suite as proof of robustness.
- **Coverage gaps:** no scenario for multi-language text, long forwarded chains, or mixed signals (interested and opt-out in the same new text).

## 7. Comparison to parent

No parent: first run recorded for this feature, so no deltas, flips, or stability changes are computed. This run becomes eligible as a baseline only after a passing gate run.

## 8. Case matrix

Legend: ✅ PASS · ❌ FAIL · ❔ UNCLEAR. Labels in brackets are the classification the system returned.

| Case | Kind | Tags | Trial 1 | Trial 2 | Stability | Decided by |
|---|---|---|---|---|---|---|
| R01 | edge | quoted-footer | ✅ [interested] | ✅ [question] | label flaky | model |
| R02 | edge | quoted-footer | ✅ [interested] | ✅ [interested] | stable | model |
| R03 | normal | | ✅ [interested] | ✅ [interested] | stable | model |
| R04 | normal | pricing | ✅ [price_objection] | ✅ [question] | label flaky | model |
| R05 | normal | scheduling | ✅ [interested] | ✅ [interested] | stable | model |
| R06 | normal | deferral | ✅ [not_now, handoff] | ✅ [not_now, no handoff] | behavior flaky | model |
| R07 | normal | pricing | ✅ [price_objection] | ✅ [price_objection] | stable | model |
| R08 | adversarial | quoted-footer | ✅ [interested] | ✅ [interested] | stable | model |
| R09 | edge | one-word | ✅ [interested] | ✅ [interested] | stable | model |
| R10 | normal | opt-out | ✅ [closed] | ✅ [closed] | stable | guard |
| R11 | normal | opt-out | ✅ [closed] | ✅ [closed] | stable | guard |
| R12 | normal | bounce | ✅ [bounce] | ✅ [bounce] | stable | guard |
| R13 | normal | bounce | ✅ [bounce] | ✅ [bounce] | stable | guard |
| R14 | edge | quoted-footer, forward-only | ✅ [question] | ✅ [question] | stable | guard |

## 9. Case details

### R01: Interested Outlook reply quoting our unsubscribe footer

**Why this case exists:** the production incident. The new text is plainly interested; the only "unsubscribe" is in the quoted footer.
**Invariants:** never closed on interested.

**Input** _(shown as stored in the source report, which cut it at 160 characters; the harness stores and shows inputs in full)_:
> Hey Sounds interesting and it was great meeting you. Can you send me a contact number so I can get in touch?? Thanks Ali Sent from Outlook f…

**Rubric**
- [hard] Not classified `closed`
- [hard] Classified `interested` or `question`
- [soft] Human handoff set

| Trial | Output | Scorers | Judge | Handoff |
|---|---|---|---|---|
| 1 | `interested` | schema ✅ · timeout ✅ | ✅ PASS | yes |
| 2 | `question` | schema ✅ · timeout ✅ | ✅ PASS | yes |

**Trial 1.** Reason given by the system: _The lead expressed interest and requested a contact number to get in touch, requiring a human to provide contact details and coordinate follow-up._
Judge criteria: not closed ✅ (evidence: `classification: interested`) · interested or question ✅ (same) · handoff ✅ (`hitl: true`). Rationale: _Output matches all criteria; the reason cites the contact request._

**Trial 2.** Reason given by the system: _The lead is interested and requested a contact number for direct follow-up._
Judge criteria: not closed ✅ (evidence: `classification: question`) · interested or question ✅ (same) · handoff ✅ (`hitl: true`). Rationale: _Label differs from trial 1 but is inside the accepted set._

**Cross-trial note:** label changed between trials for the same input. The reasons describe the same intent, so this is a naming ambiguity, not a behavior difference (finding 4).

### R04: A direct pricing question

**Why this case exists:** must not close; pricing needs a human.
**Input:** Interesting. Roughly what does this cost for a team of five engineers?

**Rubric**
- [hard] Not classified `closed`
- [hard] Classified `question` or `price_objection`
- [soft] Human handoff set

| Trial | Output | Scorers | Judge | Handoff |
|---|---|---|---|---|
| 1 | `price_objection` | schema ✅ · timeout ✅ | ✅ PASS | yes |
| 2 | `question` | schema ✅ · timeout ✅ | ✅ PASS | yes |

**Trial 1.** _The lead is asking for specific pricing for a five-engineer team, which requires a tailored quote or pricing approval._
**Trial 2.** _The lead is asking for pricing for a specific five-engineer team, which requires a tailored quote or pricing approval._
**Cross-trial note:** the person asked a question; `price_objection` in trial 1 overstates it. Both labels are accepted by the rubric, which may be too loose (finding 4).

### R06: Not now, come back later

**Why this case exists:** a deferral is not an opt-out.
**Input:** We're heads-down until Q4. Worth picking this up in October, ping me then.

**Rubric**
- [hard] Not classified `closed`
- [hard] Classified `not_now` or `question`

| Trial | Output | Scorers | Judge | Handoff |
|---|---|---|---|---|
| 1 | `not_now` | schema ✅ · timeout ✅ | ✅ PASS | yes |
| 2 | `not_now` | schema ✅ · timeout ✅ | ✅ PASS | **no** |

**Trial 1.** _The lead requested a follow-up in October, requiring a scheduled future outreach commitment._
**Trial 2.** No reason returned.
**Cross-trial note:** the handoff flag changed with no expectation covering it, and trial 2 returned no reason. The follow-up date may not get scheduled when handoff is `false` (finding 5).

### R10: A genuinely typed opt-out

**Why this case exists:** compliance must still fire; a real "unsubscribe me" in the new text closes.
**Input:** Please unsubscribe me from this. I'm not interested.

**Rubric**
- [hard] Classified `closed`

| Trial | Output | Scorers | Judge | Decided by |
|---|---|---|---|---|
| 1 | `closed` | schema ✅ · timeout ✅ | ✅ PASS | deterministic guard |
| 2 | `closed` | schema ✅ · timeout ✅ | ✅ PASS | deterministic guard |

**Note:** the guard decided both trials, so the model was not exercised. This case verifies the guard rules, not the prompt.

_R02, R03, R05, R07, R08, R09, R11, R12, R13, R14 omitted from this example._

## 10. Judge and validity

| Check | Result |
|---|---|
| Canaries | none configured; **false-pass rate unmeasured** |
| Leak test (agent, model, or version guessable from bundles) | not run in dev tier |
| Double-judged cases and agreement | none (dev tier runs a single judge) |
| UNCLEAR rate | 0/28 |
| Human calibration set | none yet |
| Judge or prompt changed since last calibration | n/a |

## 11. Cost and latency _(illustrative values)_

| | This run | Budget |
|---|---|---|
| System under test cost | $0.41 | |
| Judge cost | $0.38 | |
| **Total** | **$0.79** | $5.00 |
| Latency p50 / p95 | 1.9 s / 4.2 s | p95 8 s |

Guard-decided trials carry no model cost and near-zero latency, which lowers the averages. Model-decided p95 is 4.2 s.

## 12. Agent interpretation

<!-- agent:begin -->
_Written by the coding agent after the run. Not measured data._

**Hypothesis outcome: confirmed.** No `closed` on any never-closed scenario; R10 and R11 still close; R12 and R13 still bounce.

**Triage of findings**
- Finding 1 (no canaries): real gap in the eval, not the feature. Proposing three canaries for human approval before the next run.
- Finding 2 (thin coverage): proposing 4 more quoted-footer goldens (Apple Mail, Outlook web, long forward chain, non-English). Needs human review of the golden set.
- Finding 3 (guard-heavy): by design. Proposing the guard cases be reported as their own suite.
- Findings 4 and 5: not bugs in the feature. Both need a human decision on the rubric (tighten label sets? require handoff on dated deferrals?). I am not editing the rubric.

**Next step:** wait for approval of canaries and new goldens, then run a gate-tier run on the expanded set.
<!-- agent:end -->

## 13. Appendix

- Sidecar: `20260817T172058Z-ex0001.cases.jsonl` (28 lines: per-trial scorer results, verdict, quoted evidence, rationale, bundle hash, cost, latency, `meta`).
- Verdicts: **PASS** = every rubric criterion met per the judge with quoted evidence. **FAIL** = a criterion unmet, a scorer veto, or an adapter error. **UNCLEAR** = the evidence given cannot decide; counts as non-pass.
- Intervals: Wilson 95% for proportions; bootstrap 95% for paired deltas.
