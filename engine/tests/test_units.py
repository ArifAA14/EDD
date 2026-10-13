import json

import pytest

from edd import judge as J
from edd.adapter import AdapterResult
from edd.bundle import IdAllocator, build_bundle, compile_patterns, find_leaks, scrub
from edd.loader import Criterion, Golden, SpecError, load_golden
from edd.scorers import resolve_scorers, run_scorers
from edd.stats import classify_delta, paired_bootstrap, wilson
import random


def golden(criteria):
    return Golden(id="c_1", split="dev", path="x", input="q", expected="e",
                  criteria=[Criterion(f"C{i + 1}", t, s) for i, (t, s) in enumerate(criteria)])


def resp(**kw):
    return J.RawResponse(**kw)


# ---------- stats ----------

def test_wilson_matches_known_values():
    lo, hi = wilson(28, 28)
    assert round(lo, 3) == 0.879 and hi == 1.0
    assert wilson(0, 0) is None
    lo, hi = wilson(5, 10)
    assert 0.23 < lo < 0.24 and 0.76 < hi < 0.77


def test_paired_bootstrap_is_deterministic_and_signed():
    a, b = [1.0] * 10, [0.0] * 10
    d1 = paired_bootstrap(a, b)
    assert d1 == paired_bootstrap(a, b)
    assert d1[0] == -1.0 and classify_delta(d1[1], d1[2]) == "regressed"
    same = paired_bootstrap([1.0, 0.0, 1.0], [1.0, 0.0, 1.0])
    assert classify_delta(same[1], same[2]) == "within_noise"
    assert paired_bootstrap([], []) is None


# ---------- loader ----------

def test_untagged_rubric_criteria_are_hard(tmp_path):
    p = tmp_path / "g.md"
    p.write_text("---\nid: c_1\n---\n## Input\nq\n## Rubric\n- [ ] a\n- [soft] b\n- [hard] c\n- d\n", encoding="utf-8")
    g = load_golden(p, "dev")
    assert [c.severity for c in g.criteria] == ["hard", "soft", "hard"]


def test_golden_without_rubric_is_rejected(tmp_path):
    p = tmp_path / "g.md"
    p.write_text("---\nid: c_1\n---\n## Input\nq\n", encoding="utf-8")
    with pytest.raises(SpecError):
        load_golden(p, "dev")


# ---------- blinding ----------

def test_bundle_has_only_allowed_fields_and_is_scrubbed():
    g = golden([("be right", "hard")])
    g.title, g.description, g.invariants, g.tags = "SECRET title", "SECRET desc", ["inv_x"], ["tagx"]
    patterns = compile_patterns({"scrub": []}, ["pv-777", "abc1234"])
    out = ("As the planner agent I used claude-opus-9 and openai/gpt-9 pv-777 at abc1234; "
           'File "/home/u/app/x.py", line 3 in /Users/me/repo/y.py')
    b = build_bundle("j_1", g, out, [], patterns, include_trace=False)
    assert set(b) == {"case_id", "input", "expected", "rubric", "output"}
    assert set(b["rubric"][0]) == {"id", "criterion"}
    dumped = json.dumps(b)
    for needle in ("SECRET", "inv_x", "tagx", "claude-opus-9", "gpt-9", "pv-777", "abc1234", "/home/u", "/Users/me", "planner agent"):
        assert needle not in dumped
    assert find_leaks(b, ["pv-777", "abc1234", "claude-opus-9"]) == []


def test_scrub_leaves_urls_alone():
    assert scrub("see https://example.com/a/b for 8/17 notes", compile_patterns({})) == "see https://example.com/a/b for 8/17 notes"


def test_trace_only_included_when_needed():
    g = golden([("x", "hard")])
    steps = [{"type": "tool_call", "name": "search", "args": {"q": "hi"}, "result": "ok", "secret": "drop"}]
    p = compile_patterns({})
    assert "trace" not in build_bundle("j", g, "o", steps, p, False)
    g.needs_trace = True
    t = build_bundle("j", g, "o", steps, p, False)["trace"]
    assert t == [{"type": "tool_call", "name": "search", "args": {"q": "hi"}, "result": "ok"}]


def test_judge_ids_are_opaque_and_unique():
    ids = IdAllocator(random.Random(1))
    got = {ids.next() for _ in range(500)}
    assert len(got) == 500 and all(i.startswith("j_") for i in got)


# ---------- judge parsing and verdict derivation ----------

BUNDLE = {"case_id": "j_1", "input": "q", "expected": "e", "rubric": [], "output": "The refund window is 30 days."}


def reply(criteria, verdict="PASS", **extra):
    return json.dumps({"verdict": verdict, "criteria": criteria, "evidence": "", "rationale": "r", **extra})


def test_met_true_requires_verbatim_quote_and_retries_once():
    g = golden([("states 30 days", "hard")])
    calls = []

    def backend(bundle, feedback=None):
        calls.append(feedback)
        ev = "made up text" if len(calls) == 1 else "refund window is 30 days"
        return resp(text=reply([{"id": "C1", "met": True, "evidence": ev}]), cost_usd=0.01, models={"m": 0.01}, duration_ms=3)

    out = J.judge_case(backend, BUNDLE, g)
    assert out["valid"] and out["verdict"] == "PASS" and out["attempts"] == 2
    assert "exact quote" in calls[1] and calls[0] is None
    assert out["cost_usd"] == pytest.approx(0.02)


def test_unverifiable_quotes_end_as_unclear():
    g = golden([("states 30 days", "hard")])
    backend = lambda b, f=None: resp(text=reply([{"id": "C1", "met": True, "evidence": "nope"}]))
    out = J.judge_case(backend, BUNDLE, g)
    assert out["verdict"] == "UNCLEAR" and not out["valid"] and "exact quote" in out["invalid_reason"]


def test_quote_matching_ignores_whitespace_case_and_curly_quotes():
    b = {**BUNDLE, "output": "It’s  a\nGreat   answer"}
    g = golden([("c", "hard")])
    out = J.judge_case(lambda bb, f=None: resp(text=reply([{"id": "C1", "met": True, "evidence": "it's a great answer"}])), b, g)
    assert out["verdict"] == "PASS"


def test_input_text_is_not_valid_evidence():
    b = {**BUNDLE, "input": "unique input phrase", "output": "something else"}
    g = golden([("c", "hard")])
    out = J.judge_case(lambda bb, f=None: resp(text=reply([{"id": "C1", "met": True, "evidence": "unique input phrase"}])), b, g)
    assert out["verdict"] == "UNCLEAR"


def test_backend_errors_become_unclear_not_exceptions():
    out = J.judge_case(lambda b, f=None: resp(error="judge timed out"), BUNDLE, golden([("c", "hard")]))
    assert out["verdict"] == "UNCLEAR" and "timed out" in out["invalid_reason"]


def test_missing_criterion_is_rejected():
    g = golden([("a", "hard"), ("b", "hard")])
    out = J.judge_case(lambda bb, f=None: resp(text=reply([{"id": "C1", "met": False, "evidence": ""}])), BUNDLE, g)
    assert not out["valid"] and "C2" in out["invalid_reason"]


def test_verdict_derivation_uses_severity():
    g = golden([("hard one", "hard"), ("soft one", "soft")])
    ok = reply([{"id": "C1", "met": True, "evidence": "30 days"}, {"id": "C2", "met": False, "evidence": ""}], verdict="FAIL")
    out = J.judge_case(lambda b, f=None: resp(text=ok), BUNDLE, g)
    assert out["verdict"] == "PASS"  # only the soft criterion failed
    assert [r["met"] for r in out["criteria"]] == [True, False]
    hard_undecided = reply([{"id": "C1", "met": None, "evidence": ""}, {"id": "C2", "met": True, "evidence": "30 days"}], verdict="UNCLEAR")
    assert J.judge_case(lambda b, f=None: resp(text=hard_undecided), BUNDLE, g)["verdict"] == "UNCLEAR"


def test_judge_claiming_pass_over_failed_criterion_is_overruled_and_flagged():
    g = golden([("hard", "hard")])
    out = J.judge_case(lambda b, f=None: resp(text=reply([{"id": "C1", "met": False, "evidence": ""}], verdict="PASS")), BUNDLE, g)
    assert out["verdict"] == "FAIL" and out["inconsistent"]


def test_json_inside_fences_and_prose_is_parsed():
    g = golden([("c", "hard")])
    wrapped = "Sure!\n```json\n" + reply([{"id": "C1", "met": True, "evidence": "30 days"}]) + "\n```\nDone."
    assert J.judge_case(lambda b, f=None: resp(text=wrapped), BUNDLE, g)["verdict"] == "PASS"


def test_resolve_model_prefers_requested_alias():
    assert J.resolve_model("sonnet", {"claude-haiku-5-5": 0.5, "claude-sonnet-5-5": 0.1}) == "claude-sonnet-5-5"
    assert J.resolve_model("x", {}) == "x"


def test_judge_prompt_is_packaged():
    text = J.load_judge_prompt()
    assert "evaluation judge" in text and J.judge_prompt_hash(text).startswith("sha256:")


# ---------- scorers ----------

def test_scorers_can_only_veto_and_fail_closed(tmp_path):
    spec = {"scorers": ["schema_valid", "timeout_ok", "no_forbidden_tools"], "forbidden_tools": ["rm"], "budgets": {}}
    sc = resolve_scorers(spec, tmp_path)
    ok = AdapterResult(ok=True, output="x", trace=[{"type": "tool_call", "name": "search"}])
    assert run_scorers(spec, sc, None, ok)[2] is False
    bad = AdapterResult(ok=True, output="x", trace=[{"type": "tool_call", "name": "rm"}])
    assert run_scorers(spec, sc, None, bad)[2] is True
    crashed = AdapterResult(ok=False, error="exit_nonzero", detail="boom")
    results, notes, veto = run_scorers(spec, sc, None, crashed)
    assert veto and results == {"adapter": False}


def test_custom_scorer_exceptions_fail_closed(tmp_path):
    (tmp_path / "graders").mkdir()
    (tmp_path / "graders" / "boom.py").write_text("def score(case, result):\n    raise RuntimeError('x')\n")
    spec = {"scorers": ["custom:boom"]}
    sc = resolve_scorers(spec, tmp_path)
    g = golden([("c", "hard")])
    results, notes, veto = run_scorers(spec, sc, g, AdapterResult(ok=True, output="x"))
    assert veto and "scorer error" in notes["custom:boom"]


def test_unknown_scorer_is_rejected_up_front(tmp_path):
    with pytest.raises(ValueError):
        resolve_scorers({"scorers": ["nope"]}, tmp_path)
