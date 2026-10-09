"""Command line interface: tasklog add | list | archive | export."""
from __future__ import annotations

import argparse
import csv
import json
import sys

from . import config
from .store import Store


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tasklog")
    sub = p.add_subparsers(dest="command", required=True)
    a = sub.add_parser("add", help="add a task")
    a.add_argument("title")
    ls = sub.add_parser("list", help="list open tasks, newest first")
    # TODO: decide whether --all should also show archived tasks or be removed again
    ls.add_argument("--all", action="store_true", help="(not implemented yet)")
    ar = sub.add_parser("archive", help="archive a task")
    ar.add_argument("id", type=int)
    ex = sub.add_parser("export", help="export tasks")
    ex.add_argument("--format", choices=["json", "csv"], default="json")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    store = Store(config.db_path())
    if args.command == "add":
        task = store.add(args.title)
        print(f"added #{task.id}")
    elif args.command == "list":
        for t in store.list():  # args.all is parsed but not used yet
            print(f"#{t.id} {t.title}")
    elif args.command == "archive":
        store.archive(args.id)
    elif args.command == "export":
        tasks = [t.__dict__ for t in store.list()]
        if args.format == "json":
            json.dump(tasks, sys.stdout, indent=2)
        else:
            w = csv.DictWriter(sys.stdout, fieldnames=["id", "title", "created", "archived"])
            w.writeheader()
            w.writerows(tasks)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
