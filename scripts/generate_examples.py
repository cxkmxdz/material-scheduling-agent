"""Execute actual local tools; export outputs, traces and database snapshots (no binary DB in Git)."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from scheduling_agent.agent import run_agent
from scheduling_agent.model import MockModel
from scheduling_agent.repository import Repository
from scheduling_agent.schemas import Request
from scheduling_agent.tools import Tools

ROOT = Path(__file__).resolve().parents[1]


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=ROOT / "runtime" / ("mock-" + datetime.now().strftime("%Y%m%d-%H%M%S")))
    args = p.parse_args()
    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=False)
    db_dir = ROOT / "runtime" / ("evidence-dbs-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    db_dir.mkdir(parents=True, exist_ok=False)
    # The two contrast cases intentionally use exactly the same input.
    cases = [
        ("normal", "normal", False, 0, {}, "normal", "completed"),
        ("conflict", "normal", True, 0, {}, "conflict", "completed"),
        ("missing", "missing", False, 0, {}, "missing", "needs_input"),
        ("risk", "risk", False, 0, {}, "risk", "blocked"),
        ("no_slots", "no_slots", True, 0, {}, "no_slots", "blocked"),
        ("duplicate", "normal", False, 0, {}, "normal", "completed"),
        ("id_conflict", "id_conflict", False, 0, {}, "normal", "failed"),
        ("save_failure", "normal", False, 2, {}, "save_failure", "failed"),
        ("save_retry", "normal", False, 1, {}, "save_retry", "completed"),
        ("step_limit", "normal", False, 0, {"max_steps": 1}, "step_limit", "incomplete"),
        ("tool_limit", "normal", False, 0, {"max_tools": 1}, "tool_limit", "incomplete"),
        ("multi", "multi", False, 0, {}, "multi", "needs_input"),
    ]
    manifest = {"mode": "mock", "generated_at": datetime.now(timezone.utc).isoformat(),
                "notice": "Actual local runs with scripted MockModel. No real model validation.", "scenarios": []}
    for name, input_name, seed, faults, limits, db_key, expected in cases:
        source = ROOT / "examples" / "inputs" / (input_name + ".json")
        request = Request.model_validate_json(source.read_text(encoding="utf-8"))
        repo = Repository(db_dir / (db_key + ".sqlite"))
        if seed:
            repo.seed(json.loads((ROOT / "data" / "schedules.json").read_text(encoding="utf-8")))
        tools = Tools(request, repo, ROOT / "data", faults)
        result = run_agent(request, MockModel(), tools, out_dir / (name + ".trace.jsonl"), **limits)
        write(out_dir / (name + ".output.json"), result.model_dump(mode="json"))
        with repo.connection() as db:
            snapshot = {table: [dict(row) for row in db.execute("SELECT * FROM " + table)]
                        for table in ("requests", "schedules", "drafts")}
        write(out_dir / (name + ".database.json"), snapshot)
        assert result.task_status == expected, f"{name}: expected {expected}, got {result.task_status}"
        assert len(snapshot["drafts"]) == sum(i.save_status == "saved" for i in result.items) or name == "id_conflict"
        manifest["scenarios"].append({"name": name, "input": "examples/inputs/" + source.name,
            "seed_confirmed_schedules": seed, "injected_save_failures": faults, "limits": limits,
            "database_group": db_key, "expected_task_status": expected, "actual_task_status": result.task_status,
            "output": name + ".output.json", "trace": name + ".trace.jsonl", "database": name + ".database.json"})
    manifest["sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out_dir.iterdir()) if p.is_file()}
    write(out_dir / "manifest.json", manifest)
    print(json.dumps({"ok": True, "scenarios": len(cases), "mode": "mock", "output_dir": str(out_dir)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
