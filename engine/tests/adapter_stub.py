"""Stub system-under-test for tests. Reads answers.json from the working directory.

answers.json maps case_id -> str | list[str] | {"output": str|list, "meta": dict|list, "cost": float,
"trace": list, "mode": "crash" | "sleep" | "badjson"}. List values are indexed by trial.
"""
import json
import sys
import time

req = json.load(sys.stdin)
answers = json.load(open("answers.json"))
spec = answers.get(req["case_id"], "GOOD default")
if isinstance(spec, (str, list)):
    spec = {"output": spec}
idx = (req["trial"] - 1)

mode = spec.get("mode")
if mode == "crash":
    sys.stderr.write("boom")
    sys.exit(3)
if mode == "sleep":
    time.sleep(spec.get("seconds", 5))
if mode == "badjson":
    print("not json")
    sys.exit(0)

out = spec["output"]
if isinstance(out, list):
    out = out[idx % len(out)]
meta = spec.get("meta", {})
if isinstance(meta, list):
    meta = meta[idx % len(meta)]
print("some log line before the result")
print(json.dumps({
    "output": out, "trace": spec.get("trace", []), "cost_usd": spec.get("cost", 0.01),
    "latency_ms": 5, "meta": meta,
}))
