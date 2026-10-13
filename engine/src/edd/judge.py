"""Invoke the blind judge and turn its response into a verified verdict.

The judge is called headlessly with no tools, no repo access, one case per call. The coding agent
never writes or sees the judge's prompt. Final verdicts are derived by the engine from per-criterion
results and the rubric severities (which the judge is never told):

  any hard criterion unmet            -> FAIL
  else any hard criterion undecided   -> UNCLEAR
  else                                -> PASS     (unmet soft criteria become warnings)

A criterion marked met must carry a verbatim quote from the output or trace; unverifiable quotes
are rejected and the judge is asked once more before the case is recorded as UNCLEAR.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from .bundle import trace_text
from .util import sha256_text

PROMPT_PATH = Path(__file__).parent / "prompts" / "judge.md"


def load_judge_prompt(path: Path | None = None) -> str:
    return (path or PROMPT_PATH).read_text(encoding="utf-8").strip()


def judge_prompt_hash(prompt: str) -> str:
    return sha256_text(prompt)


@dataclass
class RawResponse:
    text: str = ""
    cost_usd: float = 0.0
    models: dict = field(default_factory=dict)  # canonical model id -> cost usd
    duration_ms: int = 0
    error: str | None = None


def render_user_prompt(bundle: dict, feedback: str | None = None) -> str:
    text = (
        "Evaluate the following case. Respond with only the JSON object described in your instructions.\n\n"
        "<case>\n" + json.dumps(bundle, indent=2, ensure_ascii=False) + "\n</case>"
    )
    if feedback:
        text += (
            "\n\nYour previous response was rejected: " + feedback +
            "\nRespond again with a corrected JSON object only."
        )
    return text


class ClaudeCliBackend:
    """Run the judge through `claude -p` in a throwaway empty directory with all tools disabled."""

    def __init__(self, model: str, system_prompt: str, timeout_s: float = 180, claude_bin: str = "claude"):
        self.model = model
        self.system_prompt = system_prompt
        self.timeout_s = timeout_s
        self.claude_bin = claude_bin

    def __call__(self, bundle: dict, feedback: str | None = None) -> RawResponse:
        cmd = [
            self.claude_bin, "-p", "--safe-mode", "--tools", "", "--no-session-persistence",
            "--output-format", "json", "--model", self.model, "--system-prompt", self.system_prompt,
        ]
        started = time.monotonic()
        try:
            with tempfile.TemporaryDirectory(prefix="edd-judge-") as workdir:
                proc = subprocess.run(
                    cmd, input=render_user_prompt(bundle, feedback), capture_output=True, text=True,
                    timeout=self.timeout_s, cwd=workdir,
                )
        except subprocess.TimeoutExpired:
            return RawResponse(error=f"judge timed out after {self.timeout_s:g}s")
        except OSError as exc:
            return RawResponse(error=f"could not start judge: {exc}")
        elapsed = int((time.monotonic() - started) * 1000)
        if proc.returncode != 0:
            return RawResponse(error=f"judge exit {proc.returncode}: {proc.stderr.strip()[-300:]}", duration_ms=elapsed)
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return RawResponse(error="judge stdout was not JSON", duration_ms=elapsed)
        if data.get("is_error"):
            return RawResponse(error=f"judge reported an error: {str(data.get('result'))[:300]}", duration_ms=elapsed)
        models = {name: float(info.get("costUSD", 0.0)) for name, info in (data.get("modelUsage") or {}).items()}
        return RawResponse(
            text=str(data.get("result", "")),
            cost_usd=float(data.get("total_cost_usd", 0.0) or 0.0),
            models=models,
            duration_ms=int(data.get("duration_ms", elapsed) or elapsed),
        )


def resolve_model(requested: str, models: dict) -> str:
    """Pick the model that actually did the judging (the CLI may add a small auxiliary model)."""
    if not models:
        return requested
    for name in models:
        if requested.lower() in name.lower():
            return name
    return max(models, key=models.get)


def _norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def _extract_json(text: str):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    decoder = json.JSONDecoder()
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = decoder.raw_decode(text[m.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def parse_and_validate(text: str, bundle: dict, golden):
    """Return (rows, parsed, problem). `problem` is a string when the response must be rejected."""
    parsed = _extract_json(text)
    if parsed is None:
        return None, None, "the response was not a JSON object"
    items = parsed.get("criteria")
    if not isinstance(items, list):
        return None, parsed, "`criteria` must be a list"
    by_id = {}
    for item in items:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            by_id.setdefault(item["id"], item)
    haystack = _norm(bundle.get("output", "") + "\n" + trace_text(bundle.get("trace")))
    rows = []
    for c in golden.criteria:
        item = by_id.get(c.id)
        if item is None:
            return None, parsed, f"criterion {c.id} is missing from `criteria`"
        met = item.get("met")
        if met not in (True, False, None):
            return None, parsed, f"criterion {c.id}: `met` must be true, false, or null"
        evidence = item.get("evidence") or ""
        if not isinstance(evidence, str):
            return None, parsed, f"criterion {c.id}: `evidence` must be a string"
        verified = bool(evidence) and _norm(evidence) in haystack
        if met is True and not verified:
            return None, parsed, (
                f"criterion {c.id}: `met` is true but `evidence` is not an exact quote from the output"
            )
        rows.append({
            "id": c.id, "criterion": c.text, "severity": c.severity, "met": met,
            "evidence": evidence if verified else "", "evidence_verified": verified,
        })
    return rows, parsed, None


def derive_verdict(rows: list[dict]) -> str:
    hard = [r for r in rows if r["severity"] == "hard"]
    if any(r["met"] is False for r in hard):
        return "FAIL"
    if any(r["met"] is None for r in hard):
        return "UNCLEAR"
    return "PASS"


def judge_case(backend, bundle: dict, golden, max_attempts: int = 2) -> dict:
    """Judge one sealed bundle. Never raises; failures become an UNCLEAR outcome."""
    feedback = None
    cost, duration, models = 0.0, 0, {}
    reason = "no attempt made"
    for attempt in range(1, max_attempts + 1):
        raw = backend(bundle, feedback)
        cost += raw.cost_usd
        duration += raw.duration_ms
        for name, c in raw.models.items():
            models[name] = models.get(name, 0.0) + c
        if raw.error:
            reason, feedback = raw.error, None
            continue
        rows, parsed, problem = parse_and_validate(raw.text, bundle, golden)
        if problem is None:
            verdict = derive_verdict(rows)
            raw_verdict = str(parsed.get("verdict", "")).upper() or None
            return {
                "criteria": rows, "verdict": verdict, "verdict_raw": raw_verdict,
                "rationale": str(parsed.get("rationale", "")), "valid": True, "invalid_reason": None,
                "inconsistent": raw_verdict == "PASS" and verdict != "PASS",
                "attempts": attempt, "cost_usd": cost, "models": models, "duration_ms": duration,
            }
        reason, feedback = problem, problem
    rows = [{"id": c.id, "criterion": c.text, "severity": c.severity, "met": None,
             "evidence": "", "evidence_verified": False} for c in golden.criteria]
    return {
        "criteria": rows, "verdict": "UNCLEAR", "verdict_raw": None, "rationale": "", "valid": False,
        "invalid_reason": reason, "inconsistent": False, "attempts": max_attempts, "cost_usd": cost,
        "models": models, "duration_ms": duration,
    }
