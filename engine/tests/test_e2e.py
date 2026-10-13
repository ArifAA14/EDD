import json

import pytest

from conftest import factory_for
from edd import chain
from edd.cli import main
from edd.loader import SpecError
from edd.report import AGENT_BEGIN, AGENT_END, verify_report
from edd.runner import run_eval
from edd.util import split_frontmatter

HYP = "Changing the prompt should keep all good cases passing."


def run(root, judge, **kw):
    kw.setdefault("seed", 7)
    return run_eval(root, "demo", kw.pop("hypothesis", HYP), backend_factory=factory_for(judge), log=lambda m: None, **kw)


def sidecar(feat, rid):
    return [json.loads(x) for x in chain.cases_path(feat, rid).read_text().splitlines()]


def test_hypothesis_is_required(make_project, fake_judge):
    root, _ = make_project(dev=[{"id": "c_a"}])
    for bad in ("", "   ", "short"):
        with pytest.raises(SpecError, match="hypothesis"):
            run(root, fake_judge, hypothesis=bad)
    assert fake_judge.calls == []


def test_dev_run_end_to_end(make_project, fake_judge):
    answers = {
        "c_a": {"output": "GOOD one", "meta": {"decided_by": "model"}},
        "c_b": "BAD answer",
        "c_c": "UNSURE answer",
        "c_d": {"output": "x", "mode": "crash"},
        "c_e": "GOOD and SOFTOK",
    }
    root, feat = make_project(
        dev=[{"id": "c_a", "invariants": ["inv_one"], "tags": ["t1"]},
             {"id": "c_b", "invariants": ["inv_one"], "kind": "edge"},
             {"id": "c_c"}, {"id": "c_d"},
             {"id": "c_e", "rubric": ["[hard] be good", "[soft] SOFTCHECK also nice"]}],
        answers=answers)
    out = run(root, fake_judge)
    a, fm = out["analysis"], out["fm"]

    assert a["n"] == 10 and a["counts"] == {"PASS": 4, "FAIL": 4, "UNCLEAR": 2}
    assert len(fake_judge.calls) == 8  # the crashed case never reached the judge
    rows = sidecar(feat, out["id"])
    assert len(rows) == 10
    crashed = [r for r in rows if r["case_id"] == "c_d"]
    assert all(r["verdict_source"] == "adapter" and r["verdict"] == "FAIL" for r in crashed)
    assert fm["status"] == "complete" and fm["gate"]["passed"] is None and fm["parent"] is None
    assert fm["hard_failures"] == 4 and fm["soft_warnings"] == 0
    assert fm["invariants"]["inv_one"]["violations"] == 2

    text = out["path"].read_text()
    for n in range(1, 14):
        assert f"\n## {n}. " in text
    assert "Not judged." in text and "<!-- facts:end -->" in text
    ids = {f["id"] for f in a["findings"]}
    assert {"invariant_violation", "cases_failing", "vetoes", "no_canaries", "provenance_incomplete"} <= ids
    assert (feat / "INDEX.md").exists()
    assert verify_report(out["path"])[0]


def test_soft_criteria_warn_but_do_not_fail(make_project, fake_judge):
    root, _ = make_project(dev=[{"id": "c_e", "rubric": ["[hard] be good", "[soft] SOFTCHECK nice"]}],
                           answers={"c_e": "GOOD but no extra"})
    out = run(root, fake_judge)
    assert out["analysis"]["counts"]["PASS"] == 2 and out["analysis"]["soft_warnings"] == 2
    assert any(f["id"] == "soft_failed" for f in out["analysis"]["findings"])


def test_integrity_hash_detects_edits_but_allows_agent_section(make_project, fake_judge):
    root, feat = make_project(dev=[{"id": "c_a"}], answers={"c_a": "GOOD"})
    out = run(root, fake_judge)
    path = out["path"]
    original = path.read_text()
    edited_agent = original.replace(AGENT_BEGIN, AGENT_BEGIN + "\nI think this is fine.\n")
    path.write_text(edited_agent)
    assert verify_report(path)[0]
    tampered = original.replace("**Hard failures:** 0", "**Hard failures:** 5")
    assert tampered != original
    path.write_text(tampered)
    ok, detail = verify_report(path)
    assert not ok and "edited" in detail
    path.write_text(original)
    assert main(["--root", str(root), "verify", "demo", out["id"]]) == 0


def test_judge_never_sees_identifying_or_internal_fields(make_project, fake_judge):
    answers = {"c_a": {"output": "GOOD via gpt-9-secret pv-777 at /home/u/app/x.py",
                       "meta": {"model": "gpt-9-secret", "prompt_version": "pv-777", "decided_by": "model"}},
               "c_b": {"output": "GOOD again", "meta": {"model": "gpt-9-secret", "prompt_version": "pv-777"}}}
    root, _ = make_project(dev=[{"id": "c_a", "invariants": ["inv_one"], "tags": ["tagx"], "title": "SECRET title"}, {"id": "c_b"}],
                           canaries=[("can1", "c_a", "WRONG output")], answers=answers)
    run(root, fake_judge)
    assert len(fake_judge.calls) == 2 * 2 + 1  # 4 trials + 1 canary
    for b in fake_judge.calls:
        # Only the allowed fields exist, rubric items carry no severity, ids are opaque and re-randomized.
        assert set(b) <= {"case_id", "input", "expected", "rubric", "output", "trace"}
        assert all(set(r) == {"id", "criterion"} for r in b["rubric"])
        assert b["case_id"].startswith("j_") and b["case_id"] not in ("c_a", "c_b")
    # None of the identifying or internal strings appear anywhere in anything the judge received.
    everything = json.dumps(fake_judge.calls).lower()
    for needle in ("gpt-9-secret", "pv-777", "/home/u", "inv_one", "tagx", "secret title", "decided_by",
                   '"severity"', '"hypothesis"', '"kind"', '"meta"', '"pinned"'):
        assert needle not in everything, needle
    # Canary bundles are indistinguishable in shape from real ones.
    assert len({tuple(sorted(b)) for b in fake_judge.calls}) == 1


def test_scorer_veto_skips_the_judge(make_project, fake_judge):
    answers = {"c_a": {"output": "GOOD", "trace": [{"type": "tool_call", "name": "rm"}]}, "c_b": "GOOD"}
    root, feat = make_project(dev=[{"id": "c_a"}, {"id": "c_b"}], answers=answers,
                              spec_extra={"scorers": ["schema_valid", "timeout_ok", "no_forbidden_tools"], "forbidden_tools": ["rm"]})
    out = run(root, fake_judge)
    rows = sidecar(feat, out["id"])
    vetoed = [r for r in rows if r["case_id"] == "c_a"]
    assert all(r["verdict"] == "FAIL" and r["verdict_source"] == "scorer" and r["scorer_veto"] for r in vetoed)
    assert len(fake_judge.calls) == 2  # only c_b's two trials


def test_adapter_timeout_is_a_fail(make_project, fake_judge):
    root, feat = make_project(dev=[{"id": "c_a"}], answers={"c_a": {"output": "x", "mode": "sleep", "seconds": 10}},
                              spec_extra={"adapter": {"timeout_s": 0.5}, "trials_per_case": 1})
    out = run(root, fake_judge)
    row = sidecar(feat, out["id"])[0]
    assert row["adapter_error"] == "timeout" and row["verdict"] == "FAIL" and not fake_judge.calls


def test_label_and_behavior_flakiness_are_reported(make_project, fake_judge):
    answers = {"c_a": {"output": ["GOOD alpha", "GOOD beta"], "meta": [{"hitl": True}, {"hitl": False}]},
               "c_b": "GOOD same"}
    root, _ = make_project(dev=[{"id": "c_a"}, {"id": "c_b"}], answers=answers)
    a = run(root, fake_judge)["analysis"]
    ids = {f["id"] for f in a["findings"]}
    assert {"output_flaky", "behavior_flaky"} <= ids
    assert a["cases"]["c_a"]["behavior_flaky_keys"] == ["hitl"] and a["cases"]["c_b"]["behavior_flaky_keys"] == []


def test_guard_heavy_runs_are_called_out(make_project, fake_judge):
    answers = {"c_a": {"output": "GOOD", "meta": {"decided_by": "model"}},
               "c_b": {"output": "GOOD", "meta": {"decided_by": "guard"}},
               "c_c": {"output": "GOOD", "meta": {"decided_by": "guard"}}}
    root, _ = make_project(dev=[{"id": "c_a"}, {"id": "c_b"}, {"id": "c_c"}], answers=answers)
    a = run(root, fake_judge)["analysis"]
    assert a["decided"]["model_trials"] == 2 and a["decided"]["other_trials"] == 4
    assert any(f["id"] == "guard_heavy" for f in a["findings"])


def test_canary_caught_makes_run_valid_and_wrongly_passed_makes_it_invalid(make_project, fake_judge):
    root, _ = make_project(dev=[{"id": "c_a"}], answers={"c_a": "GOOD"},
                           canaries=[("can_wrong", "c_a", "plain wrong answer")])
    out = run(root, fake_judge)
    assert out["fm"]["status"] == "complete" and out["analysis"]["canary"] == {"total": 1, "caught": 1, "passed_wrongly": 0, "unclear": 0}

    root2, feat2 = make_project(dev=[{"id": "c_a"}], answers={"c_a": "GOOD"},
                                canaries=[("can_lenient", "c_a", "GOOD but this canary is wrong and a lenient judge passes it")])
    out2 = run(root2, fake_judge)
    assert out2["fm"]["status"] == "invalid" and not out2["analysis"]["valid"]
    assert any(f["id"] == "canary_passed" and f["severity"] == "blocker" for f in out2["analysis"]["findings"])
    _, body = split_frontmatter(out2["path"].read_text())
    banner = next(line for line in body.splitlines() if line.startswith("**Gate:**"))
    assert "INVALID (canary passed)" in banner


def test_parent_comparison_and_flips(make_project, fake_judge):
    root, feat = make_project(dev=[{"id": "c_a"}, {"id": "c_b"}, {"id": "c_c"}], answers={"c_a": "GOOD", "c_b": "GOOD", "c_c": "GOOD"})
    first = run(root, fake_judge)
    assert first["fm"]["parent"] is None
    (root / "answers.json").write_text(json.dumps({"c_a": "GOOD", "c_b": "BAD", "c_c": "GOOD"}))
    second = run(root, fake_judge)
    assert second["fm"]["parent"] == first["id"]  # no baseline yet: parent is the latest complete run
    cmp_ = second["analysis"]["parent"]
    assert [x["case"] for x in cmp_["to_fail"]] == ["c_b"] and cmp_["to_fail"][0]["after"] == "0/2"
    assert any(f["id"] == "regression_vs_parent" for f in second["analysis"]["findings"])
    assert second["fm"]["vs_parent"]["flips_to_fail"] == 1
    assert chain.heads(feat) == [second["id"]]
    assert "Flips away from PASS" in second["path"].read_text()


def test_report_ids_sort_in_creation_order_and_prefixes_must_be_unambiguous(make_project, fake_judge):
    root, feat = make_project(dev=[{"id": "c_a"}], answers={"c_a": "GOOD"})
    ids = [run(root, fake_judge)["id"] for _ in range(4)]
    assert [r["id"] for r in chain.list_reports(feat)] == ids == sorted(ids)
    with pytest.raises(chain.ChainError, match="ambiguous"):
        chain.resolve_id(feat, ids[0][:10])


def test_diff_command(make_project, fake_judge, capsys):
    root, feat = make_project(dev=[{"id": "c_a"}, {"id": "c_b"}], answers={"c_a": "GOOD", "c_b": "GOOD"})
    first = run(root, fake_judge)
    (root / "answers.json").write_text(json.dumps({"c_a": "GOOD", "c_b": "BAD"}))
    second = run(root, fake_judge)
    assert main(["--root", str(root), "diff", "demo", first["id"], second["id"]]) == 0
    out = capsys.readouterr().out
    assert "c_b (2/2 → 0/2)" in out and "Pass rate on shared cases" in out


def _gate_project(make_project, **kw):
    return make_project(
        dev=[{"id": "c_pin", "pinned": True}, {"id": "c_unpinned"}],
        holdout=[{"id": "h_1"}, {"id": "h_2"}],
        holdout_canaries=[("can_h", "h_1", "plain wrong answer")],
        answers={"c_pin": "GOOD", "c_unpinned": "BAD", "h_1": "GOOD", "h_2": "GOOD"}, **kw)


def test_gate_runs_holdout_plus_pinned_dev_cases(make_project, fake_judge):
    root, feat = _gate_project(make_project)
    out = run(root, fake_judge, run_type="gate")
    assert sorted(out["analysis"]["cases"]) == ["c_pin", "h_1", "h_2"]  # unpinned dev case excluded
    assert out["fm"]["gate"]["passed"] is True and out["fm"]["judge_tier"] == "gate"
    with pytest.raises(SpecError, match="gate runs"):
        run(root, fake_judge, run_type="gate", limit=1)


def test_gate_requires_canaries(make_project, fake_judge):
    root, _ = make_project(holdout=[{"id": "h_1"}], answers={"h_1": "GOOD"})
    out = run(root, fake_judge, run_type="gate")
    assert out["fm"]["gate"]["passed"] is False
    assert any("no canaries" in r for r in out["fm"]["gate"]["reasons"])


def test_pinned_regression_blocks_the_gate(make_project, fake_judge):
    root, _ = _gate_project(make_project)
    (root / "answers.json").write_text(json.dumps({"c_pin": "BAD", "h_1": "GOOD", "h_2": "GOOD"}))
    out = run(root, fake_judge, run_type="gate")
    assert out["fm"]["gate"]["passed"] is False
    assert any("pinned case regressed" in r for r in out["fm"]["gate"]["reasons"])


def test_promotion_rules_and_baseline_chain(make_project, fake_judge):
    root, feat = _gate_project(make_project)
    dev = run(root, fake_judge)
    with pytest.raises(chain.ChainError, match="only gate runs"):
        chain.promote(feat, dev["id"], "riffy")
    gate = run(root, fake_judge, run_type="gate")
    chain.promote(feat, gate["id"], "riffy")
    base_fm, _ = split_frontmatter((feat / "baseline.md").read_text())
    assert base_fm["report"] == gate["id"] and base_fm["previous_baseline"] is None
    report_fm, _ = split_frontmatter(gate["path"].read_text())
    assert report_fm["promoted"] is True and verify_report(gate["path"])[0]  # promotion does not break the hash
    assert "★" in (feat / "INDEX.md").read_text()
    nxt = run(root, fake_judge)  # a later dev run compares against the baseline
    assert nxt["fm"]["parent"] == gate["id"]


def test_promote_refuses_tampered_reports(make_project, fake_judge):
    root, feat = _gate_project(make_project)
    gate = run(root, fake_judge, run_type="gate")
    gate["path"].write_text(gate["path"].read_text().replace("**Hard failures:** 0", "**Hard failures:** 9"))
    with pytest.raises(chain.ChainError, match="refusing to promote"):
        chain.promote(feat, gate["id"], "riffy")


def test_failed_gate_needs_a_logged_override_to_promote(make_project, fake_judge):
    root, feat = _gate_project(make_project, spec_extra={"thresholds": {"min_pass_rate": 0.99}})
    (root / "answers.json").write_text(json.dumps({"c_pin": "GOOD", "h_1": "GOOD", "h_2": "BAD"}))
    gate = run(root, fake_judge, run_type="gate")
    assert gate["fm"]["gate"]["passed"] is False
    with pytest.raises(chain.ChainError, match="no human override"):
        chain.promote(feat, gate["id"], "riffy")
    with pytest.raises(chain.ChainError, match="--by and --reason"):
        chain.override(feat, gate["id"], "riffy", " ")
    chain.override(feat, gate["id"], "riffy", "known flaky grader, fix scheduled")
    fm, body = split_frontmatter(gate["path"].read_text())
    assert fm["override"]["by"] == "riffy" and "OVERRIDDEN" in body and verify_report(gate["path"])[0]
    chain.promote(feat, gate["id"], "riffy")
    base_fm, _ = split_frontmatter((feat / "baseline.md").read_text())
    assert base_fm["via_override"] is True


def test_invalid_runs_and_dev_runs_cannot_be_overridden(make_project, fake_judge):
    root, feat = make_project(dev=[], holdout=[{"id": "h_1"}], answers={"h_1": "GOOD"},
                              holdout_canaries=[("can_lenient", "h_1", "GOOD but wrong")])
    gate = run(root, fake_judge, run_type="gate")
    assert gate["fm"]["status"] == "invalid"
    with pytest.raises(chain.ChainError, match="invalid"):
        chain.override(feat, gate["id"], "riffy", "please")
    root2, feat2 = make_project(dev=[{"id": "c_a"}], answers={"c_a": "GOOD"})
    dev = run(root2, fake_judge)
    with pytest.raises(chain.ChainError, match="only gate runs"):
        chain.override(feat2, dev["id"], "riffy", "please")


def test_annotate_records_outcome_without_breaking_integrity(make_project, fake_judge):
    root, feat = make_project(dev=[{"id": "c_a"}], answers={"c_a": "GOOD"})
    out = run(root, fake_judge)
    assert main(["--root", str(root), "annotate", "demo", out["id"], "--outcome", "confirmed"]) == 0
    fm, _ = split_frontmatter(out["path"].read_text())
    assert fm["hypothesis_outcome"] == "confirmed" and verify_report(out["path"])[0]
    assert "confirmed" in (feat / "INDEX.md").read_text()


def test_cli_run_refuses_without_hypothesis(make_project, capsys):
    root, _ = make_project(dev=[{"id": "c_a"}])
    assert main(["--root", str(root), "run", "demo"]) == 2
    assert "hypothesis" in capsys.readouterr().err


def test_report_shows_full_untruncated_text(make_project, fake_judge):
    long_input = "x" * 900
    long_output = "GOOD " + "y" * 900
    root, _ = make_project(dev=[{"id": "c_a", "input": long_input}], answers={"c_a": long_output})
    text = run(root, fake_judge)["path"].read_text()
    assert long_input in text and long_output in text
