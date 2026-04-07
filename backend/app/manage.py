from __future__ import annotations

import argparse

from app.db import create_tables


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.manage")
    subparsers = parser.add_subparsers(dest="command", required=True)

    migrate_parser = subparsers.add_parser("migrate", help="Apply schema migrations for the global DB and mailbox DBs")
    migrate_parser.set_defaults(handler=_handle_migrate)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 1
    return int(handler(args) or 0)


def _handle_migrate(_args: argparse.Namespace) -> int:
    create_tables()
    print("Schema migrations applied for global and mailbox databases.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
