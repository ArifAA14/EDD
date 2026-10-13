"""CLI entrypoint. Commands are declared now and implemented in Phase 1."""
import argparse
import sys

COMMANDS = {
    "init": "Guided spec and golden bootstrap for a feature",
    "run": "Run a feature's eval (requires --hypothesis); judge blind; write a report",
    "diff": "Paired comparison of two reports with confidence intervals and flips",
    "promote": "Promote a passing gate report to baseline",
    "revert": "Restore the code, config, and goldens of a prior baseline",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eval", description="EDD harness engine")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, helptext in COMMANDS.items():
        sub.add_parser(name, help=helptext)
    args = parser.parse_args(argv)
    sys.stderr.write(f"`eval {args.command}` is not implemented yet (Phase 1).\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
