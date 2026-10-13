"""Run the system under test through the command adapter (see docs/spec/03-adapter-contract.md)."""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import time
from dataclasses import dataclass, field

from .loader import SpecError


@dataclass
class AdapterResult:
    ok: bool
    error: str | None = None  # timeout | exit_nonzero | invalid_json | missing_output | invalid_output_type | spawn_failed
    detail: str = ""
    output: str = ""
    trace: list = field(default_factory=list)
    cost_usd: float = 0.0
    latency_ms: int = 0  # wall clock measured by the engine
    reported_latency_ms: int | None = None
    meta: dict = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)


def _parse_json_object(stdout: str):
    text = stdout.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Adapters often print log lines before the result; take the last line that is a JSON object.
    for line in reversed(text.splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def run_adapter(spec: dict, root, case_id: str, trial: int, input_text: str) -> AdapterResult:
    cfg = spec["adapter"]
    command = cfg.get("command")
    if not command:
        raise SpecError("adapter.command is required")
    timeout = float(cfg.get("timeout_s", 60))
    env = {**os.environ, **{str(k): str(v) for k, v in (cfg.get("env") or {}).items()}}
    payload = json.dumps({"case_id": case_id, "trial": trial, "input": input_text})
    started = time.monotonic()
    try:
        proc = subprocess.run(
            shlex.split(command), input=payload, capture_output=True, text=True,
            timeout=timeout, cwd=root, env=env,
        )
    except subprocess.TimeoutExpired:
        return AdapterResult(False, "timeout", f"exceeded {timeout:g}s",
                             latency_ms=int((time.monotonic() - started) * 1000))
    except OSError as exc:
        return AdapterResult(False, "spawn_failed", str(exc))
    latency_ms = int((time.monotonic() - started) * 1000)
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip()[-400:]
        return AdapterResult(False, "exit_nonzero", f"exit {proc.returncode}: {tail}", latency_ms=latency_ms)
    data = _parse_json_object(proc.stdout)
    if not isinstance(data, dict):
        return AdapterResult(False, "invalid_json", "stdout was not a JSON object", latency_ms=latency_ms)
    if "output" not in data:
        return AdapterResult(False, "missing_output", "response has no `output` key", latency_ms=latency_ms)
    if not isinstance(data["output"], str):
        return AdapterResult(False, "invalid_output_type", "`output` must be a string", latency_ms=latency_ms)

    problems: list[str] = []
    trace = data.get("trace", [])
    if not isinstance(trace, list):
        problems.append("`trace` must be a list")
        trace = []
    cost = data.get("cost_usd", 0.0)
    if not isinstance(cost, (int, float)) or isinstance(cost, bool):
        problems.append("`cost_usd` must be a number")
        cost = 0.0
    reported = data.get("latency_ms")
    if reported is not None and (not isinstance(reported, (int, float)) or isinstance(reported, bool)):
        problems.append("`latency_ms` must be a number")
        reported = None
    meta = data.get("meta", {})
    if not isinstance(meta, dict):
        problems.append("`meta` must be an object")
        meta = {}
    return AdapterResult(
        ok=True, output=data["output"], trace=trace, cost_usd=float(cost), latency_ms=latency_ms,
        reported_latency_ms=int(reported) if reported is not None else None, meta=meta, problems=problems,
    )
