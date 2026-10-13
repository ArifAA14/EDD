"""Sealed judge bundles: allowed fields only, scrubbed, hashed (docs/spec/04-judge-bundle.md).

The judge may see: opaque case id, input, expected answer, rubric text, the (scrubbed) output,
and optionally a normalized trace. It never sees agent or model names, the hypothesis, diffs,
report history, baseline scores, run type, severity tags, invariant names, kinds, titles,
descriptions, adapter `meta`, or the existence of canaries.
"""
from __future__ import annotations

import random
import re

from .util import hash_obj

# Order matters: the traceback pattern must run before the generic path pattern.
_DEFAULT_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r'File "[^"]+", line \d+'), 'File "<path>", line N'),
    (re.compile(r"/(?:home|Users|tmp|var|opt|usr|mnt|workspace|app|srv|root)/[^\s\"'`<>)\]]+"), "<path>"),
    (re.compile(r"\b[A-Za-z]:\\(?:[^\s\"'`<>\\]+\\)*[^\s\"'`<>\\]*"), "<path>"),
    (re.compile(r"\b(?:claude|gpt|gemini|llama|mistral|grok)-[\w.\-]+", re.I), "<model>"),
    (re.compile(r"\b(?:openai|anthropic|google|meta|mistralai|xai)/[\w.\-]+", re.I), "<model>"),
    (re.compile(r"\b(as|i am|i'm) (the |an? )?[\w\-]+ agent\b", re.I), r"\1 the assistant"),
]


def compile_patterns(spec: dict, literal_terms: list[str] | None = None) -> list[tuple[re.Pattern, str]]:
    patterns = list(_DEFAULT_PATTERNS)
    for item in spec.get("scrub") or []:
        if isinstance(item, dict):
            patterns.append((re.compile(item["pattern"]), item.get("replacement", "<redacted>")))
        else:
            patterns.append((re.compile(str(item)), "<redacted>"))
    for term in literal_terms or []:
        if term and len(term) >= 3:
            patterns.append((re.compile(re.escape(term), re.I), "<redacted>"))
    return patterns


def scrub(text: str, patterns) -> str:
    for rx, repl in patterns:
        text = rx.sub(repl, text)
    return text


def _scrub_obj(obj, patterns):
    if isinstance(obj, str):
        return scrub(obj, patterns)
    if isinstance(obj, list):
        return [_scrub_obj(x, patterns) for x in obj]
    if isinstance(obj, dict):
        return {k: _scrub_obj(v, patterns) for k, v in obj.items()}
    return obj


def normalize_trace(trace: list, patterns) -> list:
    keep = ("type", "name", "args", "result")
    return [
        {k: _scrub_obj(step.get(k), patterns) for k in keep if k in step}
        for step in trace if isinstance(step, dict)
    ]


def trace_text(trace) -> str:
    """Flatten a trace to plain text for quote verification."""
    parts: list[str] = []

    def walk(x):
        if isinstance(x, str):
            parts.append(x)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
        elif x is not None:
            parts.append(str(x))

    walk(trace)
    return "\n".join(parts)


def build_bundle(judge_id: str, golden, output: str, trace: list, patterns, include_trace: bool) -> dict:
    bundle = {
        "case_id": judge_id,
        "input": golden.input,
        "expected": golden.expected,
        "rubric": [{"id": c.id, "criterion": c.text} for c in golden.criteria],
        "output": scrub(output, patterns),
    }
    if include_trace or golden.needs_trace:
        bundle["trace"] = normalize_trace(trace, patterns)
    return bundle


def bundle_hash(bundle: dict) -> str:
    return hash_obj(bundle)


def find_leaks(bundle: dict, terms: list[str]) -> list[str]:
    """Return any identifying terms still present in the output or trace after scrubbing."""
    haystack = (bundle.get("output", "") + "\n" + trace_text(bundle.get("trace"))).lower()
    return sorted({t for t in terms if t and len(t) >= 3 and t.lower() in haystack})


class IdAllocator:
    """Opaque, per-run random judge-facing case ids."""

    def __init__(self, rng: random.Random):
        self._rng = rng
        self._used: set[str] = set()

    def next(self) -> str:
        while True:
            candidate = "j_%08x" % self._rng.getrandbits(32)
            if candidate not in self._used:
                self._used.add(candidate)
                return candidate
