#!/usr/bin/env python3
"""Stop hook (NOT WIRED YET): block "done" without a passing gate run.

Intentionally not registered in hooks.json. A stub that exits 0 would wave
everything through, which is exactly the false-pass failure this project exists
to prevent. Wire it in Phase 2, once `edd run --gate` exists and this can fail
closed on a missing or failing gate report.

Planned behavior:
  1. Find features touched in the working tree (evals/<feature>/ and the code they cover).
  2. For each, locate the newest report whose git_sha matches HEAD (or is clean-dirty-equal).
  3. Require: status complete, run_type gate, gate.passed true, no unresolved override.
  4. Otherwise exit 2 with the failing reasons so the agent must continue.
"""
import sys

sys.stderr.write("stop_gate.py is a stub and must not be registered yet.\n")
sys.exit(1)
