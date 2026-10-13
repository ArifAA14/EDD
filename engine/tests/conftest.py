import json
import sys
import threading
from pathlib import Path

import pytest
import yaml

from edd.judge import RawResponse

ADAPTER = Path(__file__).parent / "adapter_stub.py"


def write_golden(folder: Path, g: dict) -> None:
    fm = {"id": g["id"], "title": g.get("title", f"Case {g['id']}"), "kind": g.get("kind", "normal"),
          "tags": g.get("tags", []), "invariants": g.get("invariants", []), "pinned": g.get("pinned", False),
          "description": g.get("description", f"why {g['id']} exists")}
    rubric = g.get("rubric", ["[hard] The answer is good"])
    body = f"## Input\n{g.get('input', 'question for ' + g['id'])}\n\n## Expected\nA good answer.\n\n## Rubric\n"
    body += "\n".join(f"- {r}" for r in rubric) + "\n"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{g['id']}.md").write_text("---\n" + yaml.safe_dump(fm) + "---\n" + body, encoding="utf-8")


def write_canary(folder: Path, name: str, for_case: str, output: str, mode: str = "wrong") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.md").write_text(f"---\nfor: {for_case}\nmode: {mode}\n---\n## Output\n{output}\n", encoding="utf-8")


@pytest.fixture
def make_project(tmp_path):
    def _make(dev=(), holdout=(), canaries=(), holdout_canaries=(), spec_extra=None, answers=None):
        root = tmp_path / "proj"
        feat = root / "evals" / "demo"
        spec = {
            "feature": "demo",
            "adapter": {"command": f"{sys.executable} {ADAPTER}", "timeout_s": 3},
            "trials_per_case": 2,
            "invariants": {"inv_one": "Invariant one must always hold."},
            "thresholds": {"min_pass_rate": 0.5, "max_unclear_rate": 0.5},
            "judge": {"concurrency": 2},
        }
        for k, v in (spec_extra or {}).items():
            if isinstance(v, dict) and isinstance(spec.get(k), dict):
                spec[k].update(v)
            else:
                spec[k] = v
        feat.mkdir(parents=True, exist_ok=True)
        (feat / "spec.md").write_text("---\n" + yaml.safe_dump(spec) + "---\nDemo feature.\n", encoding="utf-8")
        for g in dev:
            write_golden(feat / "goldens" / "dev", g)
        for g in holdout:
            write_golden(feat / "goldens" / "holdout", g)
        for name, for_case, output in canaries:
            write_canary(feat / "goldens" / "dev" / "canaries", name, for_case, output)
        for name, for_case, output in holdout_canaries:
            write_canary(feat / "goldens" / "holdout" / "canaries", name, for_case, output)
        (root / "answers.json").write_text(json.dumps(answers or {}), encoding="utf-8")
        return root, feat

    return _make


class FakeJudge:
    """Deterministic judge: GOOD in output -> met; UNSURE -> undecided; FABRICATE -> bogus quote."""

    def __init__(self):
        self.calls: list[dict] = []
        self.feedbacks: list = []
        self._lock = threading.Lock()

    def __call__(self, bundle, feedback=None):
        with self._lock:
            self.calls.append(bundle)
            self.feedbacks.append(feedback)
        out = bundle["output"]
        criteria = []
        for c in bundle["rubric"]:
            text = c["criterion"]
            if "SOFTCHECK" in text:
                met, ev = ("SOFTOK" in out), "SOFTOK"
            elif "GOOD" in out:
                met, ev = True, "GOOD"
            elif "UNSURE" in out:
                met, ev = None, ""
            elif "FABRICATE" in out:
                met, ev = True, "text that is not in the output"
            else:
                met, ev = False, ""
            criteria.append({"id": c["id"], "met": met, "evidence": ev if met else ""})
        verdict = "PASS" if all(c["met"] is True for c in criteria) else (
            "UNCLEAR" if any(c["met"] is None for c in criteria) else "FAIL")
        text = json.dumps({"verdict": verdict, "criteria": criteria, "evidence": "", "rationale": "fake"})
        return RawResponse(text=text, cost_usd=0.002, models={"fake-model": 0.002}, duration_ms=5)


@pytest.fixture
def fake_judge():
    return FakeJudge()


def factory_for(judge):
    return lambda model, prompt, spec: judge
