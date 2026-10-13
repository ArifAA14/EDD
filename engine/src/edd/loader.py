"""Load feature specs, goldens, and canaries from the evals/<feature>/ folder."""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from pathlib import Path

from .util import hash_obj, split_frontmatter

SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)
RUBRIC_RE = re.compile(r"^\s*[-*]\s*\[(hard|soft|x|\s)?\]\s*(.+?)\s*$", re.I)

KINDS = {"normal", "edge", "adversarial", "canary"}


class SpecError(Exception):
    """Raised for malformed or incomplete eval definitions."""


@dataclass
class Criterion:
    id: str
    text: str
    severity: str = "hard"  # hard | soft


@dataclass
class Golden:
    id: str
    split: str
    path: str
    title: str = ""
    description: str = ""
    kind: str = "normal"
    source: str = ""
    added: str = ""
    why_added: str = ""
    tags: list[str] = field(default_factory=list)
    invariants: list[str] = field(default_factory=list)
    pinned: bool = False
    needs_trace: bool = False
    input: str = ""
    expected: str = ""
    criteria: list[Criterion] = field(default_factory=list)
    resolution: str = ""


@dataclass
class Canary:
    id: str
    for_case: str
    split: str
    mode: str
    output: str
    path: str


DEFAULT_SPEC = {
    "adapter": {"timeout_s": 60, "env": {}},
    "scorers": ["schema_valid", "timeout_ok"],
    "forbidden_tools": [],
    "invariants": {},
    "thresholds": {"min_pass_rate": 0.85, "max_unclear_rate": 0.05, "max_guard_share": 0.30},
    "budgets": {},
    "trials_per_case": 3,
    "judge": {
        "dev_model": "sonnet",
        "gate_model": "fable",
        "concurrency": 4,
        "timeout_s": 180,
        "include_trace": False,
    },
    "scrub": [],
    "hash_inputs": {"prompts": [], "config": []},
    "gate": {"include": ["holdout", "pinned_dev"]},
    "keep_raw_trace": False,
}


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in (over or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_spec(feature_dir: Path) -> dict:
    path = feature_dir / "spec.md"
    if not path.exists():
        raise SpecError(f"missing {path}")
    fm, body = split_frontmatter(path.read_text(encoding="utf-8"))
    spec = _merge(DEFAULT_SPEC, fm)
    spec.setdefault("feature", feature_dir.name)
    spec["_body"] = body
    spec["_path"] = str(path)
    # Placeholder values like "<configure>" mean "use the default".
    for key in ("dev_model", "gate_model"):
        value = spec["judge"].get(key)
        if not isinstance(value, str) or value.strip().startswith("<") or not value.strip():
            spec["judge"][key] = DEFAULT_SPEC["judge"][key]
    if not (spec.get("adapter") or {}).get("command"):
        raise SpecError("spec.md must define adapter.command")
    if int(spec["trials_per_case"]) < 1:
        raise SpecError("trials_per_case must be >= 1")
    return spec


def parse_sections(body: str) -> dict[str, str]:
    matches = list(SECTION_RE.finditer(body))
    parts: dict[str, str] = {}
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        parts[m.group(1).strip().lower()] = body[m.end():end].strip()
    return parts


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value]
    return [str(value)]


def load_golden(path: Path, split: str) -> Golden:
    fm, body = split_frontmatter(path.read_text(encoding="utf-8"))
    if not fm.get("id"):
        raise SpecError(f"{path}: frontmatter must define an opaque `id`")
    secs = parse_sections(body)
    criteria: list[Criterion] = []
    for line in secs.get("rubric", "").splitlines():
        m = RUBRIC_RE.match(line)
        if not m:
            continue
        marker = (m.group(1) or " ").strip().lower()
        severity = "soft" if marker == "soft" else "hard"  # untagged criteria are hard
        criteria.append(Criterion(id=f"C{len(criteria) + 1}", text=m.group(2), severity=severity))
    if not criteria:
        raise SpecError(f"{path}: golden has no rubric criteria")
    if "input" not in secs:
        raise SpecError(f"{path}: golden has no ## Input section")
    kind = str(fm.get("kind", "normal"))
    if kind not in KINDS:
        raise SpecError(f"{path}: unknown kind {kind!r}")
    return Golden(
        id=str(fm["id"]),
        split=split,
        path=str(path),
        title=str(fm.get("title", "")),
        description=str(fm.get("description", "")),
        kind=kind,
        source=str(fm.get("source", "")),
        added=str(fm.get("added", "")),
        why_added=str(fm.get("why_added", "")),
        tags=_as_list(fm.get("tags")),
        invariants=_as_list(fm.get("invariants")),
        pinned=bool(fm.get("pinned", False)),
        needs_trace=bool(fm.get("needs_trace", False)),
        input=secs["input"],
        expected=secs.get("expected", ""),
        criteria=criteria,
        resolution=secs.get("resolution", ""),
    )


def load_goldens(feature_dir: Path, split: str) -> list[Golden]:
    folder = feature_dir / "goldens" / split
    if not folder.is_dir():
        return []
    goldens = [load_golden(p, split) for p in sorted(folder.glob("*.md"))]
    seen: set[str] = set()
    for g in goldens:
        if g.id in seen:
            raise SpecError(f"duplicate golden id {g.id!r} in {split}")
        seen.add(g.id)
    return goldens


def load_canaries(feature_dir: Path, split: str) -> list[Canary]:
    folder = feature_dir / "goldens" / split / "canaries"
    if not folder.is_dir():
        return []
    canaries = []
    for p in sorted(folder.glob("*.md")):
        fm, body = split_frontmatter(p.read_text(encoding="utf-8"))
        secs = parse_sections(body)
        if not fm.get("for"):
            raise SpecError(f"{p}: canary frontmatter must define `for: <case id>`")
        if "output" not in secs:
            raise SpecError(f"{p}: canary has no ## Output section")
        canaries.append(Canary(
            id=p.stem, for_case=str(fm["for"]), split=split,
            mode=str(fm.get("mode", "")), output=secs["output"], path=str(p),
        ))
    return canaries


def golden_set_hash(feature_dir: Path, splits: list[str]) -> str:
    """Hash every golden and canary file in the given splits (content plus relative path)."""
    entries = []
    for split in splits:
        folder = feature_dir / "goldens" / split
        if not folder.is_dir():
            continue
        for p in sorted(folder.rglob("*.md")):
            entries.append([p.relative_to(feature_dir).as_posix(), p.read_text(encoding="utf-8")])
    return hash_obj(entries)
