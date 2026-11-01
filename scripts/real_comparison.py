"""Run the SAME request/model against free, occupied and saving-failure data. Requires real API."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from scheduling_agent.agent import run_agent
from scheduling_agent.model import ModelError, RealModel
from scheduling_agent.repository import Repository
from scheduling_agent.schemas import Request
from scheduling_agent.tools import Tools

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=ROOT / "runtime" / ("real-" + datetime.now().strftime("%Y%m%d-%H%M%S")))
    args = p.parse_args()
    load_dotenv(ROOT / ".env", override=False)
    try:
        model = RealModel.from_env()
    except ModelError as exc:
        print(json.dumps({"mode": "real", "validation_status": "not_run", "code": exc.code,
                          "required": ["MODEL_API_KEY", "MODEL_NAME", "MODEL_BASE_URL (if using compatible provider)"]}))
        return 2
    output_dir = args.out.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)
    request = Request.model_validate_json((ROOT / "examples/inputs/normal.json").read_text(encoding="utf-8"))
    comparisons = []
    try:
        for name, seed, failures in (("free", False, 0), ("occupied", True, 0), ("save_failure", False, 2)):
            repo = Repository(output_dir / (name + ".sqlite"))
            if seed:
                repo.seed(json.loads((ROOT / "data/schedules.json").read_text(encoding="utf-8")))
            result = run_agent(request, model, Tools(request, repo, ROOT / "data", failures), output_dir / (name + ".trace.jsonl"))
            payload = result.model_dump(mode="json")
            (output_dir / (name + ".output.json")).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            (output_dir / (name + ".database.json")).write_text(json.dumps(repo.list_drafts(), ensure_ascii=False, indent=2), encoding="utf-8")
            item = result.items[0]
            expected = ((name == "free" and item.save_status == "saved" and item.proposed_at == request.requested_at.isoformat()) or
                        (name == "occupied" and item.save_status == "saved" and item.proposed_at != request.requested_at.isoformat() and item.confirmation_status == "pending_confirmation") or
                        (name == "save_failure" and result.task_status == "failed" and item.save_status == "failed" and not repo.list_drafts()))
            comparisons.append({"condition": name, "observed_status": result.task_status, "errors": result.errors,
                                "acceptance_met": expected, "tool_calls": result.tool_calls, "output": name + ".output.json"})
    finally:
        model.close()
    report = {"mode": "real", "model": model.name, "timestamp": datetime.now(timezone.utc).isoformat(),
              "same_request": request.model_dump(mode="json"), "conditions": comparisons,
              "all_acceptance_met": all(c["acceptance_met"] for c in comparisons),
              "review": "Read all traces to explain action changes. API/protocol errors do not prove real model decision quality."}
    (output_dir / "comparison.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["all_acceptance_met"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
