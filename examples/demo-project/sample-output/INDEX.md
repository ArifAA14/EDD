# refund-qa: eval index

Read this first. Open a report only for the run you need.

**Baseline:** `20261013T083653Z-20eda7d` (pass rate 1.0)
**Chain heads** (runs nothing else was compared to): dev `20261013T083638Z-0f14ea0`; gate `20261013T083653Z-20eda7d`

| Run | Type | Pass | vs parent | Gate | Findings (B/W/N) | Hypothesis → outcome |
|---|---|---|---|---|---|---|
| `20261013T083653Z-20eda7d` ★ | gate | 6/6 | within noise (n=3) | pass | 0/2/0 | v3 generalizes to the holdout: the Gold plan case now declines, the da… → confirmed |
| `20261013T083638Z-0f14ea0` | dev | 8/8 | within noise (n=4) | — | 0/2/0 | Declining for any unknown plan (not just Platinum) keeps all dev cases… → confirmed |
| `20261013T083614Z-04e80c6` | gate | 4/6 | within noise (n=1) | FAIL | 1/2/0 | The v2 Platinum fix generalizes: the holdout cases (Gold plan, day-20 … → refuted |
| `20261013T083558Z-2436701` | dev | 8/8 | within noise (n=4) | — | 0/2/0 | Special-casing the Platinum plan makes the bot decline instead of inve… → confirmed |
| `20261013T083543Z-205739e` | dev | 6/8 | — | — | 1/2/0 | Baseline before any fix: c_002 (unknown plan) should fail because the … → confirmed |
