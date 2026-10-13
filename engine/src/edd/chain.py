"""Reports on disk: parent chain, baseline, promotion, override, and the per-feature INDEX.md."""
from __future__ import annotations

import json
from pathlib import Path

from .report import FACTS_END, verify_report
from .util import iso, join_frontmatter, split_frontmatter, utc_now


class ChainError(Exception):
    """Raised when a report operation is not allowed."""


def results_dir(feature_dir: Path) -> Path:
    return feature_dir / "results"


def report_path(feature_dir: Path, rid: str) -> Path:
    return results_dir(feature_dir) / f"{rid}.md"


def cases_path(feature_dir: Path, rid: str) -> Path:
    return results_dir(feature_dir) / f"{rid}.cases.jsonl"


def list_reports(feature_dir: Path) -> list[dict]:
    out = []
    folder = results_dir(feature_dir)
    if folder.is_dir():
        for p in sorted(folder.glob("*.md")):
            fm, _ = split_frontmatter(p.read_text(encoding="utf-8"))
            if fm.get("id"):
                out.append({"id": fm["id"], "path": p, "fm": fm})
    return sorted(out, key=lambda r: r["id"])


def resolve_id(feature_dir: Path, prefix: str) -> str:
    matches = [r["id"] for r in list_reports(feature_dir) if r["id"].startswith(prefix)]
    if not matches:
        raise ChainError(f"no report matching {prefix!r} in {results_dir(feature_dir)}")
    if len(matches) > 1:
        raise ChainError(f"{prefix!r} is ambiguous: {', '.join(matches)}")
    return matches[0]


def read_cases(feature_dir: Path, rid: str) -> tuple[list[dict], list[dict]]:
    trials, canaries = [], []
    p = cases_path(feature_dir, rid)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            (canaries if rec.get("type") == "canary" else trials).append(rec)
    return trials, canaries


def load_report(feature_dir: Path, rid: str) -> dict:
    path = report_path(feature_dir, rid)
    if not path.exists():
        raise ChainError(f"report {rid} not found")
    fm, body = split_frontmatter(path.read_text(encoding="utf-8"))
    trials, canaries = read_cases(feature_dir, rid)
    return {"id": rid, "path": path, "fm": fm, "body": body, "trials": trials, "canaries": canaries}


def get_baseline(feature_dir: Path) -> str | None:
    p = feature_dir / "baseline.md"
    if not p.exists():
        return None
    fm, _ = split_frontmatter(p.read_text(encoding="utf-8"))
    return fm.get("report")


def default_parent(feature_dir: Path) -> str | None:
    """Baseline if one exists, else the newest complete run (so early iteration still compares)."""
    base = get_baseline(feature_dir)
    if base and report_path(feature_dir, base).exists():
        return base
    complete = [r for r in list_reports(feature_dir) if r["fm"].get("status") == "complete"]
    return complete[-1]["id"] if complete else None


def heads(feature_dir: Path) -> list[str]:
    reports = list_reports(feature_dir)
    referenced = {r["fm"].get("parent") for r in reports}
    return [r["id"] for r in reports if r["id"] not in referenced]


def append_lifecycle(path: Path, line: str) -> None:
    text = path.read_text(encoding="utf-8")
    path.write_text(text.rstrip("\n") + f"\n- {line}\n", encoding="utf-8")


def _rewrite_fm(path: Path, updates: dict) -> dict:
    fm, body = split_frontmatter(path.read_text(encoding="utf-8"))
    fm.update(updates)
    path.write_text(join_frontmatter(fm, body), encoding="utf-8")
    return fm


def annotate(feature_dir: Path, rid: str, outcome: str) -> None:
    if outcome not in {"confirmed", "refuted", "inconclusive"}:
        raise ChainError("outcome must be confirmed, refuted, or inconclusive")
    path = report_path(feature_dir, rid)
    _rewrite_fm(path, {"hypothesis_outcome": outcome})
    append_lifecycle(path, f"{iso(utc_now())}: hypothesis outcome recorded as {outcome}")
    write_index(feature_dir)


def override(feature_dir: Path, rid: str, by: str, reason: str) -> None:
    """Logged human override of a failed gate. Invalid runs cannot be overridden."""
    path = report_path(feature_dir, rid)
    fm, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    if not by.strip() or not reason.strip():
        raise ChainError("an override needs --by and --reason")
    if fm.get("run_type") != "gate":
        raise ChainError("only gate runs can be overridden")
    if fm.get("status") != "complete":
        raise ChainError(f"run status is {fm.get('status')!r}; invalid runs cannot be overridden")
    if (fm.get("gate") or {}).get("passed") is not False:
        raise ChainError("the gate did not fail; nothing to override")
    stamp = iso(utc_now())
    _rewrite_fm(path, {"override": {"by": by, "reason": reason, "at": stamp}})
    append_lifecycle(path, f"{stamp}: gate OVERRIDDEN by {by}: {reason}")
    write_index(feature_dir)


def promote(feature_dir: Path, rid: str, by: str) -> None:
    path = report_path(feature_dir, rid)
    fm, _ = split_frontmatter(path.read_text(encoding="utf-8"))
    ok, detail = verify_report(path)
    if not ok:
        raise ChainError(f"refusing to promote: {detail}")
    if fm.get("status") != "complete":
        raise ChainError(f"run status is {fm.get('status')!r}")
    if fm.get("run_type") != "gate":
        raise ChainError("only gate runs can become the baseline")
    gate_passed = (fm.get("gate") or {}).get("passed")
    if not gate_passed and not fm.get("override"):
        raise ChainError("the gate did not pass and no human override is recorded")
    previous = get_baseline(feature_dir)
    stamp = iso(utc_now())
    _rewrite_fm(path, {"promoted": True})
    append_lifecycle(path, f"{stamp}: promoted to baseline by {by}" + ("" if gate_passed else " (via logged override)"))
    base_fm = {"report": rid, "promoted_at": stamp, "promoted_by": by, "previous_baseline": previous,
               "via_override": not gate_passed, "pass_rate": fm.get("pass_rate"), "git_sha": fm.get("git_sha")}
    body = (f"# Baseline for `{fm.get('feature')}`\n\nCurrent blessed baseline: `{rid}`. "
            f"Changes only on `edd promote`. To revert, restore the code, prompts, config, and goldens "
            f"recorded in that report (git SHA `{fm.get('git_sha')}`) and promote the previous baseline"
            + (f" `{previous}`" if previous else "") + ".\n")
    (feature_dir / "baseline.md").write_text(join_frontmatter(base_fm, body), encoding="utf-8")
    write_index(feature_dir)


def write_index(feature_dir: Path) -> None:
    reports = list_reports(feature_dir)
    feature = feature_dir.name
    base = get_baseline(feature_dir)
    lines = [f"# {feature}: eval index", "", "Read this first. Open a report only for the run you need.", ""]
    if base:
        bfm = next((r["fm"] for r in reports if r["id"] == base), {})
        lines.append(f"**Baseline:** `{base}` (pass rate {bfm.get('pass_rate', 'n/a')})")
    else:
        lines.append("**Baseline:** none yet. Promote a passing gate run with `edd promote`.")
    hs = heads(feature_dir)
    lines.append(f"**Chain heads:** {', '.join(f'`{h}`' for h in hs) or 'none'}" + (" (more than one head: branches diverged)" if len(hs) > 1 else ""))
    lines += ["", "| Run | Type | Pass | vs parent | Gate | Findings (B/W/N) | Hypothesis → outcome |", "|---|---|---|---|---|---|---|"]
    for r in reversed(reports[-5:]):
        fm = r["fm"]
        vc = fm.get("verdict_counts") or {}
        total = sum(vc.values()) if vc else 0
        gate = fm.get("gate") or {}
        gate_s = "—" if gate.get("passed") is None else ("pass" if gate["passed"] else ("override" if fm.get("override") else "FAIL"))
        fnd = fm.get("findings") or {}
        vp = (fm.get("vs_parent") or {}).get("verdict", "—")
        hyp = str(fm.get("hypothesis", "")).replace("\n", " ")
        hyp = (hyp[:70] + "…") if len(hyp) > 70 else hyp
        marker = " ★" if r["id"] == base else ""
        lines.append(f"| `{r['id']}`{marker} | {fm.get('run_type')}{'' if fm.get('status') == 'complete' else ' (' + str(fm.get('status')) + ')'} | "
                     f"{vc.get('pass', 0)}/{total} | {str(vp).replace('_', ' ')} | {gate_s} | "
                     f"{fnd.get('blocker', 0)}/{fnd.get('warning', 0)}/{fnd.get('note', 0)} | {hyp} → {fm.get('hypothesis_outcome') or 'pending'} |")
    (feature_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
