"""Scorers: cheap, objective checks that can only VETO.

A scorer failure is an automatic FAIL and the judge is skipped. A scorer pass means nothing by
itself; every surviving case still goes to the judge, and only the judge can produce PASS.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

from .adapter import AdapterResult


def _schema_valid(spec, golden, res: AdapterResult):
    return (res.ok and not res.problems, "; ".join(res.problems) or "ok")


def _timeout_ok(spec, golden, res: AdapterResult):
    return (res.error != "timeout", res.detail if res.error == "timeout" else "ok")


def _no_forbidden_tools(spec, golden, res: AdapterResult):
    forbidden = set(spec.get("forbidden_tools") or [])
    used = [step.get("name") for step in res.trace if isinstance(step, dict) and step.get("type") == "tool_call"]
    bad = sorted({n for n in used if n in forbidden})
    return (not bad, f"forbidden tool(s) called: {', '.join(bad)}" if bad else "ok")


def _cost_budget(spec, golden, res: AdapterResult):
    limit = (spec.get("budgets") or {}).get("max_cost_usd_per_case")
    if limit is None:
        return True, "no per-case budget set"
    return (res.cost_usd <= float(limit), f"cost ${res.cost_usd:.4f} vs limit ${float(limit):.4f}")


BUILTIN = {
    "schema_valid": _schema_valid,
    "timeout_ok": _timeout_ok,
    "no_forbidden_tools": _no_forbidden_tools,
    "cost_budget": _cost_budget,
}


def _load_custom(feature_dir: Path, name: str):
    module_name = name.split(":", 1)[1]
    path = feature_dir / "graders" / f"{module_name}.py"
    if not path.exists():
        raise FileNotFoundError(f"custom scorer {name!r}: {path} not found")
    spec = importlib.util.spec_from_file_location(f"edd_scorer_{module_name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "score"):
        raise AttributeError(f"{path} must define score(case, result)")
    return module.score


def resolve_scorers(spec: dict, feature_dir: Path) -> dict:
    """Map scorer names to callables. Unknown or broken scorers raise now, not mid-run."""
    resolved = {}
    for name in spec.get("scorers") or []:
        if name in BUILTIN:
            resolved[name] = BUILTIN[name]
        elif name.startswith("custom:"):
            custom = _load_custom(feature_dir, name)

            def wrapper(spec_, golden, res, _custom=custom):
                case = {"id": golden.id, "input": golden.input}
                result = {"output": res.output, "trace": res.trace, "cost_usd": res.cost_usd,
                          "latency_ms": res.latency_ms, "meta": res.meta}
                out = _custom(case, result)
                if isinstance(out, tuple):
                    return bool(out[0]), str(out[1])
                return bool(out), "ok" if out else "custom scorer failed"

            resolved[name] = wrapper
        else:
            raise ValueError(f"unknown scorer {name!r}; built-ins: {sorted(BUILTIN)}; custom: custom:<module>")
    return resolved


def run_scorers(spec: dict, scorers: dict, golden, res: AdapterResult):
    """Return (results, notes, veto). Adapter failures veto without running scorers. Fails closed."""
    if not res.ok:
        return {"adapter": False}, {"adapter": f"{res.error}: {res.detail}"}, True
    results: dict[str, bool] = {}
    notes: dict[str, str] = {}
    for name, fn in scorers.items():
        try:
            passed, note = fn(spec, golden, res)
        except Exception as exc:  # a broken scorer must never wave a case through
            passed, note = False, f"scorer error: {exc}"
        results[name] = bool(passed)
        notes[name] = note
    return results, notes, not all(results.values())
