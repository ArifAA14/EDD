#!/usr/bin/env python3
"""PreToolUse hook: keep the coding agent away from the protected eval surface.

Blocks (exit code 2, reason on stderr):
  - any access to evals/*/goldens/holdout/
  - any write/edit to evals/*/graders/ (scorers, rubrics)
  - any access to the judge definition or bundle builder

Best-effort for Bash: matches protected paths in the command string. A determined
agent can evade string matching in a shell, so the engine must also run the judge
and holdout in a process the coding agent cannot reach. This hook is the first
line of defense, not the only one.
"""
import json
import re
import sys

# (pattern, applies_to) where applies_to is "any" or "write"
PROTECTED = [
    (re.compile(r"evals/[^/]+/goldens/holdout(/|$)"), "any"),
    (re.compile(r"evals/[^/]+/graders(/|$)"), "write"),
    (re.compile(r"plugin/agents/judge\.md$"), "write"),
    (re.compile(r"engine/src/edd/(bundle|judge)[^/]*\.py$"), "write"),
]
READ_TOOLS = {"Read", "Grep", "Glob"}
WRITE_TOOLS = {"Edit", "Write", "NotebookEdit"}
WRITE_VERBS = re.compile(r"(>|>>|\btee\b|\bsed\s+-i\b|\bmv\b|\bcp\b|\brm\b|\btruncate\b)")


def candidate_paths(tool: str, tool_input: dict) -> list[str]:
    paths = []
    for key in ("file_path", "path", "notebook_path", "pattern"):
        value = tool_input.get(key)
        if isinstance(value, str):
            paths.append(value)
    if tool == "Bash":
        paths.append(tool_input.get("command", ""))
    return paths


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0  # not our event shape; do not break the session
    tool = event.get("tool_name", "")
    tool_input = event.get("tool_input", {}) or {}

    is_write = tool in WRITE_TOOLS or (
        tool == "Bash" and bool(WRITE_VERBS.search(tool_input.get("command", "")))
    )

    for text in candidate_paths(tool, tool_input):
        for pattern, applies_to in PROTECTED:
            if not pattern.search(text):
                continue
            if applies_to == "write" and not is_write:
                continue
            sys.stderr.write(
                "Blocked by edd-harness: this path is part of the protected eval "
                "surface (holdout goldens, graders, rubrics, judge). Eval design "
                "changes go through a human-approved spec change, not the coding agent.\n"
            )
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
