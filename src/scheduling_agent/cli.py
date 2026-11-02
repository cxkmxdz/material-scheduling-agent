from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from pydantic import ValidationError

from .agent import run_agent
from .model import MockModel, ModelError, RealModel
from .repository import Repository
from .schemas import Request
from .tools import Tools


def parser():
    p = argparse.ArgumentParser(description="Question 1: material review and draft scheduling; never publishes")
    sub = p.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Create DB and seed confirmed demo schedules; repeat is safe")
    init.add_argument("--db", type=Path, default=Path("runtime/agent.sqlite"))
    init.add_argument("--data-dir", type=Path, default=Path("data"))
    run = sub.add_parser("run")
    run.add_argument("--input", type=Path, required=True)
    run.add_argument("--mode", choices=("mock", "real"), default="mock")
    run.add_argument("--db", type=Path, default=Path("runtime/agent.sqlite"))
    run.add_argument("--data-dir", type=Path, default=Path("data"))
    run.add_argument("--output", type=Path)
    run.add_argument("--trace", type=Path)
    run.add_argument("--max-steps", type=int, default=24)
    run.add_argument("--max-tools", type=int, default=24)
    run.add_argument("--fail-saves", type=int, default=0, help="Inject N actual SQLite failures after INSERT (rollback)")
    inspect = sub.add_parser("inspect", help="Read durable drafts")
    inspect.add_argument("--db", type=Path, default=Path("runtime/agent.sqlite"))
    return p


def write_json_exclusive(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main(argv=None) -> int:
    args = parser().parse_args(argv)
    model = None
    try:
        if args.command == "run":
            if args.max_steps < 1 or args.max_tools < 1 or args.fail_saves < 0:
                raise ValueError("limits must be positive and --fail-saves nonnegative")
            if args.output and args.output.exists():
                raise FileExistsError("output already exists; choose a new output path")
            if args.trace and args.trace.exists():
                raise FileExistsError("trace already exists; choose a new trace path")
            if args.output and args.trace and args.output.resolve() == args.trace.resolve():
                raise ValueError("output and trace must be different files")
            request = Request.model_validate_json(args.input.read_text(encoding="utf-8-sig"))
            load_dotenv(override=False, encoding="utf-8-sig")
            model = MockModel() if args.mode == "mock" else RealModel.from_env()
            repo = Repository(args.db)
            tools = Tools(request, repo, args.data_dir, args.fail_saves)
            trace = args.trace or Path("runtime/traces") / (uuid4().hex + ".jsonl")
            output = run_agent(request, model, tools, trace, args.max_steps, args.max_tools)
            value = output.model_dump(mode="json")
            if args.output:
                write_json_exclusive(args.output, value)
            print(json.dumps(value, ensure_ascii=False, indent=2))
            return 0 if output.task_status == "completed" else 2
        repo = Repository(args.db)
        if args.command == "init":
            repo.seed(json.loads((args.data_dir / "schedules.json").read_text(encoding="utf-8")))
            print(json.dumps({"ok": True, "db": str(args.db.resolve()), "note": "Seeded demo confirmed schedules; existing drafts preserved"}, ensure_ascii=False))
        else:
            print(json.dumps(repo.list_drafts(), ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, ValidationError, ModelError, sqlite3.Error) as exc:
        code = exc.code if isinstance(exc, ModelError) else type(exc).__name__
        # Do not echo input values, API response bodies, URLs, or credentials.
        print(json.dumps({"task_status": "failed", "code": code,
                          "summary": "Startup or output error; check input schema, configuration, data and unused output paths"}), file=sys.stderr)
        return 2
    finally:
        if isinstance(model, RealModel):
            model.close()


if __name__ == "__main__":
    raise SystemExit(main())
