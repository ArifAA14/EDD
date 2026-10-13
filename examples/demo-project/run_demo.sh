#!/usr/bin/env bash
# Replays the demo story in a scratch git repo, using the REAL judge (`claude -p`). Costs roughly $1.
#
#   run 1  dev   v1   baseline: the bot invents terms for an unknown plan          -> c_002 fails
#   run 2  dev   v2   "fix" that only special-cases Platinum                       -> dev passes (overfit)
#   run 3  gate  v2   holdout asks about a Gold plan                               -> gate FAILS (overfit caught)
#   run 4  dev   v3   real fix                                                     -> dev passes
#   run 5  gate  v3   holdout + pinned c_002                                       -> gate PASSES, then promote
#
# Usage: ./run_demo.sh [destination-dir]      (needs `edd` on PATH: pip install -e engine)
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
dest="${1:-$(mktemp -d)}"
mkdir -p "$dest"
tar -C "$here" --exclude=sample-output --exclude=run_demo.sh -cf - . | tar -C "$dest" -xf -
cd "$dest"
rm -rf evals/refund-qa/results/* evals/refund-qa/INDEX.md evals/refund-qa/baseline.md
mkdir -p evals/refund-qa/results

git init -q -b main
git config user.name "edd demo"
git config user.email "demo@example.com"
git add -A
git commit -q -m "Initial support bot (v1) and evals"

feature=refund-qa
logs="$(mktemp -d)"
run() {  # run <outfile> <edd run args...>; never abort on a failed gate
  local out="$1"; shift
  edd run "$feature" "$@" 2>&1 | tee "$out" | grep -v '^\[edd\]' || true
}
rid() { grep '^report:' "$1" | sed 's#.*/##; s#\.md$##'; }

echo "=== run 1: v1 baseline (dev)"
run "$logs/run1.txt" --hypothesis "Baseline before any fix: c_002 (unknown plan) should fail because the bot invents refund terms; the other three cases should pass; both canaries should be caught." \
  --refuted-if "c_002 passes, any other case fails, or a canary passes."
r1=$(rid "$logs/run1.txt"); edd annotate "$feature" "$r1" --outcome confirmed

echo; echo "=== run 2: v2 special-cases Platinum (dev)"
echo v2 > bot_version.txt; git add bot_version.txt; git commit -q -m "Special-case Platinum in the support bot (v2)"
run "$logs/run2.txt" --parent "$r1" --change "support bot v2: honest answer for the Platinum plan" \
  --hypothesis "Special-casing the Platinum plan makes the bot decline instead of inventing terms, fixing c_002 without changing the other three cases." \
  --refuted-if "c_002 still fails, or any previously passing case regresses."
r2=$(rid "$logs/run2.txt"); edd annotate "$feature" "$r2" --outcome confirmed

sed -i 's/^invariants: \[never_invent_plans\]$/invariants: [never_invent_plans]\npinned: true/' evals/$feature/goldens/dev/c_002.md
git add evals/$feature/goldens/dev/c_002.md; git commit -q -m "Pin c_002 now that it is fixed"

echo; echo "=== run 3: gate on v2 (expected to FAIL on the Gold plan)"
run "$logs/run3.txt" --gate --parent "$r2" --change "support bot v2" \
  --hypothesis "The v2 Platinum fix generalizes: the holdout cases (Gold plan, day-20 refund) pass and pinned c_002 still passes, so the gate passes." \
  --refuted-if "Any holdout case fails, a canary passes, or the gate does not pass."
r3=$(rid "$logs/run3.txt"); edd annotate "$feature" "$r3" --outcome refuted

python3 - "$r3" "$feature" <<'PY'
import sys, pathlib
rid, feature = sys.argv[1], sys.argv[2]
p = pathlib.Path("evals") / feature / "results" / f"{rid}.md"
text = p.read_text()
start, end = text.index("<!-- agent:begin -->"), text.index("<!-- agent:end -->")
note = """<!-- agent:begin -->
_Written by the coding agent after the run. Interpretation, not measured data._

**Hypothesis outcome: refuted.** The holdout Gold-plan case (`h_002`) failed, so the gate failed.

**Triage of findings**
- Finding 1 (invariant `never_invent_plans` not upheld): real bug. The v2 change special-cased the one plan name seen in dev ("Platinum") instead of handling unknown plans in general. Not a bad golden: the Gold case is the same failure mode as `c_002`.
- Warnings (thin coverage, interval straddles threshold): expected with 2 holdout cases; the invariant needs more holdout cases before the gate means much.

**Next step:** replace the special case with a general rule (decline for any plan outside Standard and Annual), re-run dev, then re-run the gate. I am not touching the holdout or the rubric.
"""
p.write_text(text[:start] + note + text[end:])
PY
edd verify "$feature" "$r3"

echo; echo "=== run 4: v3 general fix (dev)"
echo v3 > bot_version.txt; git add bot_version.txt; git commit -q -m "Decline for any unknown plan, not just Platinum (v3)"
run "$logs/run4.txt" --parent "$r2" --change "support bot v3: honest answer for every unknown plan" \
  --hypothesis "Declining for any unknown plan (not just Platinum) keeps all dev cases passing, including pinned c_002." \
  --refuted-if "Any dev case fails or a canary passes."
r4=$(rid "$logs/run4.txt"); edd annotate "$feature" "$r4" --outcome confirmed

echo; echo "=== run 5: v3 gate (expected to PASS)"
run "$logs/run5.txt" --gate --parent "$r3" --change "support bot v3" \
  --hypothesis "v3 generalizes to the holdout: the Gold plan case now declines, the day-20 refund is approved, and pinned c_002 still passes, so the gate passes." \
  --refuted-if "Any holdout or pinned case fails, a canary passes, or the gate does not pass."
r5=$(rid "$logs/run5.txt"); edd annotate "$feature" "$r5" --outcome confirmed
edd promote "$feature" "$r5" --by demo

echo; echo "=== INDEX.md"; cat evals/$feature/INDEX.md
echo; echo "Reports are in: $dest/evals/$feature/results"
