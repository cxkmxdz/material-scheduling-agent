"""Exercise README CLI operations and record their actual exit codes without requiring credentials."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    evidence = ROOT / "examples/cli-smoke.json"
    if evidence.exists():
        raise FileExistsError("CLI smoke evidence already exists")
    runtime = ROOT / "runtime" / ("cli-smoke-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    runtime.mkdir(parents=True)
    records = []

    def call(label, arguments, expected_code):
        completed = subprocess.run([sys.executable, "-m", "scheduling_agent.cli", *arguments], cwd=ROOT,
                                   capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        assert completed.returncode == expected_code, (label, completed.stderr)
        payload = json.loads(completed.stdout or completed.stderr)
        records.append({"operation": label, "arguments": arguments, "exit_code": completed.returncode, "result": payload})
        return payload

    common = ["--input", "examples/inputs/normal.json"]
    normal = call("normal", ["run", *common, "--db", str(runtime / "normal.sqlite")], 0)
    occupied_db = str(runtime / "occupied.sqlite")
    call("init", ["init", "--db", occupied_db], 0)
    occupied = call("conflict", ["run", *common, "--db", occupied_db], 0)
    persisted = call("inspect", ["inspect", "--db", occupied_db], 0)
    call("missing", ["run", "--input", "examples/inputs/missing.json", "--db", str(runtime / "missing.sqlite")], 2)
    failed = call("save_failure", ["run", *common, "--db", str(runtime / "failure.sqlite"), "--fail-saves", "2"], 2)
    assert normal["items"][0]["proposed_at"].endswith("18:00:00+08:00")
    assert occupied["items"][0]["confirmation_status"] == "pending_confirmation"
    assert occupied["items"][0]["draft_id"] == persisted[0]["draft_id"]
    assert failed["items"][0]["draft_id"] is None
    report = {"timestamp": datetime.now(timezone.utc).isoformat(), "mode": "mock", "checks_passed": True, "commands": records}
    evidence.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"ok": True, "commands": len(records), "output": "examples/cli-smoke.json"}))


if __name__ == "__main__":
    main()
