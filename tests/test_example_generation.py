import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def test_generated_evidence_is_actual_and_consistent(tmp_path):
    root = Path(__file__).resolve().parents[1]
    out = tmp_path / "evidence"
    result = subprocess.run([sys.executable, str(root / "scripts/generate_examples.py"), "--out", str(out)],
                            cwd=root, capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    assert result.returncode == 0, result.stderr
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["scenarios"]) == 12 and manifest["mode"] == "mock"
    for name, digest in manifest["sha256"].items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    for case in manifest["scenarios"]:
        actual = json.loads((out / case["output"]).read_text(encoding="utf-8"))
        database = json.loads((out / case["database"]).read_text(encoding="utf-8"))
        ids = {row["draft_id"] for row in database["drafts"]}
        assert actual["task_status"] == case["expected_task_status"]
        for item in actual["items"]:
            if item["save_status"] == "saved":
                assert item["draft_id"] in ids
            else:
                assert item["draft_id"] is None
    normal = json.loads((out / "normal.output.json").read_text(encoding="utf-8"))
    duplicate = json.loads((out / "duplicate.output.json").read_text(encoding="utf-8"))
    assert normal["items"][0]["draft_id"] == duplicate["items"][0]["draft_id"]
