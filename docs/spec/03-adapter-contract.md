# Adapter contract

The adapter is how the runner invokes the system under test (SUT). It must work for arbitrary agents, so the contract is a command.

## Declared in `evals/<feature>/spec.md`

```yaml
adapter:
  command: "python -m myapp.eval_entry"   # executed once per case-trial
  timeout_s: 60
  env: {}
```

## Protocol

The engine writes one JSON object to the command's stdin and reads one JSON object from stdout.

Input:

```json
{"case_id": "c_7f3a", "trial": 1, "input": "<case input>"}
```

Output:

```json
{
  "output": "<final output of the SUT>",
  "trace": [
    {"type": "tool_call", "name": "search", "args": {...}, "result": "..."}
  ],
  "cost_usd": 0.031,
  "latency_ms": 2040
}
```

## Rules

- A nonzero exit, invalid JSON, or a timeout is a scorer-level FAIL for that case-trial and the judge is skipped.
- The adapter reports cost and latency itself; the engine verifies latency by wall clock and records both.
- The adapter must not read from `goldens/`. The engine passes only the input.
- Traces are normalized by the engine before judging (see `04-judge-bundle.md`). The raw trace is kept in `cases.jsonl` only if `keep_raw_trace: true`.
- Later: Python-function and HTTP adapters, once the command adapter works.
