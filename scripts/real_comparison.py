"""Run the SAME request/model against free, occupied and saving-failure data. Requires real API."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

from scheduling_agent.agent import run_agent
from scheduling_agent.evaluation import evaluate_condition
from scheduling_agent.model import ModelError, RealModel
from scheduling_agent.repository import Repository
from scheduling_agent.schemas import Request
from scheduling_agent.tools import Tools

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=ROOT / "examples/real" / datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    args = p.parse_args()
    load_dotenv(ROOT / ".env", override=False, encoding="utf-8-sig")
    try:
        model = RealModel.from_env()
    except ModelError as exc:
        print(json.dumps({"mode": "real", "validation_status": "not_run", "code": exc.code,
                          "required": ["MODEL_API_KEY", "MODEL_NAME", "MODEL_BASE_URL (if using compatible provider)"]}))
        return 2
    comparisons = []
    try:
        output_dir = args.out.resolve()
        output_dir.mkdir(parents=True, exist_ok=False)
        db_dir = ROOT / "runtime/real-databases" / uuid4().hex
        db_dir.mkdir(parents=True, exist_ok=False)
        request = Request.model_validate_json((ROOT / "examples/inputs/normal.json").read_text(encoding="utf-8"))

        def write(name, value):
            text = json.dumps(value, ensure_ascii=False, indent=2)
            for secret in model.secrets:
                text = text.replace(json.dumps(secret, ensure_ascii=False)[1:-1], "[REDACTED]")
            with (output_dir / name).open("x", encoding="utf-8") as f:
                f.write(text + "\n")

        write("input.json", request.model_dump(mode="json"))
        for name, seed, failures in (("free", False, 0), ("occupied", True, 0), ("save_failure", False, 2)):
            print(json.dumps({"condition": name, "status": "started"}), flush=True)
            repo = Repository(db_dir / (name + ".sqlite"))
            if seed:
                repo.seed(json.loads((ROOT / "data/schedules.json").read_text(encoding="utf-8")))
            trace_path = output_dir / (name + ".trace.jsonl")
            result = run_agent(request, model, Tools(request, repo, ROOT / "data", failures), trace_path)
            drafts = repo.list_drafts()
            records = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
            write(name + ".output.json", result.model_dump(mode="json"))
            write(name + ".database.json", drafts)
            evaluated = evaluate_condition(name, request, result, drafts, records)
            evaluated.update(seed_confirmed_schedules=seed, injected_save_failures=failures)
            comparisons.append(evaluated)
            print(json.dumps({"condition": name, "status": "finished", "acceptance_met": evaluated["acceptance_met"],
                              "task_status": result.task_status, "errors": result.errors}), flush=True)
        report = {"mode": "real", "model": model.name, "timestamp": datetime.now(timezone.utc).isoformat(),
                  "model_settings": {"thinking": model.thinking, "tool_choice": "required", "parallel_tool_calls": False},
                  "same_request": request.model_dump(mode="json"), "request_digest": request.digest(),
                  "conditions": comparisons, "all_acceptance_met": all(c["acceptance_met"] for c in comparisons),
                  "review": "Acceptance uses ordered tool observations, subsequent model actions and durable database records. Inspect traces for decision quality; a single comparison does not establish stability."}
        write("comparison.json", report)
        hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output_dir.iterdir()) if p.is_file()}
        write("manifest.json", {"mode": "real", "model": model.name, "sha256": hashes,
                                "all_acceptance_met": report["all_acceptance_met"]})
        print(json.dumps({"mode": "real", "all_acceptance_met": report["all_acceptance_met"], "output_dir": str(output_dir)}, ensure_ascii=False))
        return 0 if report["all_acceptance_met"] else 2
    finally:
        model.close()


if __name__ == "__main__":
    raise SystemExit(main())
