"""A toy support bot, used as the system under test in the demo.

Speaks the edd adapter protocol: one JSON object on stdin, one JSON object on stdout.
BOT_VERSION selects the behavior so the demo can show a regression, an overfit fix, and a real fix:

  v1  hallucinates refund terms for any plan it has never heard of
  v2  only fixes the one example the developer saw ("platinum"); still hallucinates for others
  v3  declines for any unknown plan
"""
import json
import os
import re
import sys

req = json.load(sys.stdin)
version = os.environ.get("BOT_VERSION", "v1")
question = req["input"].lower()

unknown = re.search(r"\b(platinum|gold|premium|enterprise|pro|basic)\b", question)
decided_by = "model"

if unknown:
    name = unknown.group(1).capitalize()
    honest = (f"I don't have any information about a {name} plan. Our plans are Standard and Annual, "
              "and I can explain the refund policy for either of those.")
    made_up = f"The {name} plan has a 60-day refund window."
    if version == "v1" or (version == "v2" and name != "Platinum"):
        output = made_up
    else:
        output = honest
elif "45 days" in question:
    output = "Refunds are only available within 30 days of purchase, so a request after 45 days would not qualify."
elif "20 days" in question:
    output = "Yes. A refund is available within 30 days of purchase, so day 20 qualifies."
elif "annual" in question:
    output = "Annual plans are refundable within 30 days of purchase."
else:
    output = "You can request a refund within 30 days of purchase on the Standard plan."

print(json.dumps({
    "output": output, "trace": [], "cost_usd": 0.0004, "latency_ms": 3,
    "meta": {"decided_by": decided_by, "model": "demo-model-1", "prompt_version": f"support-bot-{version}"},
}))
