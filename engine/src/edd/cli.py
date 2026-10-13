"""`edd` command line. (Named `edd`, not `eval`, because `eval` is a shell builtin.)"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import chain
from .analysis import compare_runs
from .loader import SpecError
from .report import render_diff, verify_report
from .runner import run_eval


def _feature_dir(args) -> Path:
    return Path(args.root).resolve() / args.evals_dir / args.feature


def _cmd_run(args) -> int:
    if args.hypothesis_file:
        hypothesis = Path(args.hypothesis_file).read_text(encoding="utf-8")
    else:
        hypothesis = args.hypothesis or ""
    parent = None if args.no_parent else (args.parent or "auto")
    out = run_eval(
        Path(args.root), args.feature, hypothesis, run_type="gate" if args.gate else "dev", trials=args.trials,
        case_ids=args.cases.split(",") if args.cases else None, limit=args.limit, parent=parent,
        judge_model=args.judge_model, concurrency=args.concurrency, seed=args.seed, change_note=args.change,
        refuted_if=args.refuted_if, evals_dir=args.evals_dir,
    )
    a = out["analysis"]
    c = a["counts"]
    print(f"report: {out['path']}")
    print(f"PASS {c['PASS']}/{a['n']}  FAIL {c['FAIL']}  UNCLEAR {c['UNCLEAR']}  "
          f"valid={a['valid']}  cost ${a['cost']['total']:.2f}")
    g = a["gate"]
    print("gate: " + ("not evaluated (dev run)" if g["passed"] is None else ("PASS" if g["passed"] else "FAIL")))
    if g["passed"] is False:
        for r in g["reasons"]:
            print(f"  - {r}")
    for f in a["findings"][:6]:
        print(f"  [{f['severity']}] {f['title']}")
    if not a["valid"]:
        return 2
    return 0 if g["passed"] in (None, True) else 1


def _cmd_diff(args) -> int:
    fd = _feature_dir(args)
    a_id, b_id = chain.resolve_id(fd, args.a), chain.resolve_id(fd, args.b)
    ta, _ = chain.read_cases(fd, a_id)
    tb, _ = chain.read_cases(fd, b_id)
    print(render_diff(args.feature, a_id, b_id, compare_runs(ta, tb)))
    return 0


def _cmd_verify(args) -> int:
    fd = _feature_dir(args)
    rid = chain.resolve_id(fd, args.report)
    ok, detail = verify_report(chain.report_path(fd, rid))
    print(f"{rid}: {'OK' if ok else 'TAMPERED'}: {detail}")
    return 0 if ok else 1


def _cmd_annotate(args) -> int:
    fd = _feature_dir(args)
    chain.annotate(fd, chain.resolve_id(fd, args.report), args.outcome)
    print("hypothesis outcome recorded")
    return 0


def _cmd_override(args) -> int:
    fd = _feature_dir(args)
    chain.override(fd, chain.resolve_id(fd, args.report), args.by, args.reason)
    print("override logged in the report")
    return 0


def _cmd_promote(args) -> int:
    fd = _feature_dir(args)
    rid = chain.resolve_id(fd, args.report)
    chain.promote(fd, rid, args.by)
    print(f"{rid} is now the baseline")
    return 0


def _cmd_unimplemented(args) -> int:
    sys.stderr.write(f"`edd {args.command}` is not implemented yet.\n")
    return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="edd", description="Eval-driven development engine")
    p.add_argument("--root", default=".", help="project root containing the evals folder")
    p.add_argument("--evals-dir", default="evals")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="run a feature's eval, judge it blind, and write a report")
    r.add_argument("feature")
    r.add_argument("--hypothesis")
    r.add_argument("--hypothesis-file")
    r.add_argument("--change", help="one line on what you changed (stated by the agent)")
    r.add_argument("--refuted-if", help="what result would refute the hypothesis")
    r.add_argument("--gate", action="store_true", help="gate run: holdout goldens, strongest judge, full set only")
    r.add_argument("--trials", type=int)
    r.add_argument("--cases", help="comma-separated case ids (dev runs only)")
    r.add_argument("--limit", type=int, help="random subset size (dev runs only)")
    r.add_argument("--parent", help="report id to compare against (default: baseline, else latest complete run)")
    r.add_argument("--no-parent", action="store_true")
    r.add_argument("--judge-model", help="override the judge model for this run")
    r.add_argument("--concurrency", type=int, help="parallel adapter calls")
    r.add_argument("--seed", type=int)
    r.set_defaults(fn=_cmd_run)

    d = sub.add_parser("diff", help="paired comparison of two reports")
    d.add_argument("feature"); d.add_argument("a"); d.add_argument("b")
    d.set_defaults(fn=_cmd_diff)

    v = sub.add_parser("verify", help="check a report's engine-authored sections were not edited")
    v.add_argument("feature"); v.add_argument("report")
    v.set_defaults(fn=_cmd_verify)

    n = sub.add_parser("annotate", help="record whether the hypothesis was confirmed or refuted")
    n.add_argument("feature"); n.add_argument("report")
    n.add_argument("--outcome", required=True, choices=["confirmed", "refuted", "inconclusive"])
    n.set_defaults(fn=_cmd_annotate)

    o = sub.add_parser("override", help="human override of a failed gate (logged in the report)")
    o.add_argument("feature"); o.add_argument("report")
    o.add_argument("--by", required=True); o.add_argument("--reason", required=True)
    o.set_defaults(fn=_cmd_override)

    pr = sub.add_parser("promote", help="make a passing gate report the baseline")
    pr.add_argument("feature"); pr.add_argument("report")
    pr.add_argument("--by", required=True)
    pr.set_defaults(fn=_cmd_promote)

    for name, text in (("init", "guided spec and golden bootstrap (not implemented)"),
                       ("revert", "restore a prior baseline (not implemented)")):
        sub.add_parser(name, help=text).set_defaults(fn=_cmd_unimplemented)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except (SpecError, chain.ChainError, FileNotFoundError, ValueError) as exc:
        sys.stderr.write(f"edd: {exc}\n")
        return 2


if __name__ == "__main__":
    sys.exit(main())
