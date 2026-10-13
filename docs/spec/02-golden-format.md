# Golden format

Goldens live in `evals/<feature>/goldens/dev/` and `evals/<feature>/goldens/holdout/`. One file per case, YAML frontmatter plus markdown body. Filenames use the opaque case id.

```markdown
---
id: c_7f3a                 # opaque; never encodes author, feature version, or source
kind: normal               # normal | edge | adversarial | canary
source: prod_failure       # prod_failure | synthetic | human_written | mined
added: 2026-10-13
why_added: "Prod trace showed empty-result queries returned a hallucinated answer."
tags: [empty-result]
---

## Input
<what the system under test receives>

## Expected
<golden expectation: the correct answer, or the properties a correct answer must have>

## Rubric
- [ ] <criterion 1, checkable from the output>
- [ ] <criterion 2>
```

## Rules

- **Opaque ids.** The judge sees the id, so it must carry no information.
- **Rubric travels with the case.** The judge needs the *what* even though it never sees the *who*.
- **Human resolutions.** When an UNCLEAR case is resolved by a human, the resolution is appended under `## Resolution` with date and reason. This becomes a labeled calibration example.
- **Dev vs holdout.** The coding agent iterates on `dev/`. `holdout/` is read only by gate runs and is protected by hook.
- **Growth.** New goldens change `golden_set_hash`. Comparisons across different sets use the intersection of cases, or re-run the baseline on the new set.
- **Regression pins.** Once a case that failed is fixed, it is flagged `pinned: true`. A later failure on a pinned case is a hard gate stop.

## Canaries

Canaries are *outputs*, not inputs: a plausible but incorrect output for a golden input, stored in `goldens/<split>/canaries/` and injected by the engine in place of the real output. Requirements:

- Indistinguishable from real outputs in format, length, and style.
- Cover distinct failure modes: subtle factual error, confident hallucination, partial answer, correct-looking wrong format.
- A canary the judge passes invalidates the run.
