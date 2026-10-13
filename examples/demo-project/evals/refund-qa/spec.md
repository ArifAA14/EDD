---
feature: refund-qa
adapter:
  command: "python3 support_bot.py"
  timeout_s: 30
trials_per_case: 2
scorers: [schema_valid, timeout_ok]
invariants:
  never_invent_plans: "The bot never states policy details for a plan that does not exist."
thresholds:
  min_pass_rate: 0.85
  max_unclear_rate: 0.05
budgets:
  max_cost_usd_per_run: 1.00
  p95_latency_ms: 5000
hash_inputs:
  prompts: ["support_bot.py"]
  config: ["bot_version.txt"]
---

## Job

Answer customer questions about refund policy using only what the company actually offers.

## Facts the bot may rely on

- Plans: Standard and Annual.
- Both are refundable within 30 days of purchase. After 30 days, no refund.

## Failure modes

- Invents terms for a plan that does not exist.
- States the wrong window.
- Approves a refund outside the window.
