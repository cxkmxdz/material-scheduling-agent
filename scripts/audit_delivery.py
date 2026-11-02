"""Audit tracked deliverables and recorded evidence; no network and no mutations."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

from dotenv import dotenv_values

from scheduling_agent.evaluation import evaluate_condition
from scheduling_agent.schemas import Request, RunOutput

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads((ROOT / "examples/mock/manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["sha256"].items():
        assert hashlib.sha256((ROOT / "examples/mock" / name).read_bytes()).hexdigest() == expected, name
    assert len(list((ROOT / "docs").glob("*.md"))) == 5
    real_manifests = list((ROOT / "examples/real").glob("*/manifest.json"))
    for path in real_manifests:
        real_manifest = json.loads(path.read_text(encoding="utf-8"))
        assert real_manifest["mode"] == "real"
        for name, digest in real_manifest["sha256"].items():
            assert hashlib.sha256((path.parent / name).read_bytes()).hexdigest() == digest, str(path.parent / name)
        comparison = json.loads((path.parent / "comparison.json").read_text(encoding="utf-8"))
        request = Request.model_validate(comparison["same_request"])
        for condition in comparison["conditions"]:
            output = RunOutput.model_validate_json((path.parent / condition["output"]).read_text(encoding="utf-8"))
            drafts = json.loads((path.parent / condition["database"]).read_text(encoding="utf-8"))
            rows = [json.loads(s) for s in (path.parent / condition["trace"]).read_text(encoding="utf-8").splitlines()]
            evaluated = evaluate_condition(condition["condition"], request, output, drafts, rows)
            assert evaluated["acceptance_met"] == condition["acceptance_met"], str(path.parent)
    test_reports = list((ROOT / "examples").glob("test-results*/summary.json"))
    for path in test_reports:
        report = json.loads(path.read_text(encoding="utf-8"))
        assert report["exit_code"] == 0 and report["counts"]["failures"] == report["counts"]["errors"] == 0
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8").split("\0")
    tracked = [f for f in tracked if f]
    assert tracked, "Stage or commit delivery files first"
    prohibited, suspicious = [], []
    pattern = re.compile(rb"(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9_]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")
    local_key = dotenv_values(ROOT / ".env", encoding="utf-8-sig").get("MODEL_API_KEY")
    exact_secret = local_key.encode("utf-8") if local_key else None
    for name in tracked:
        p = Path(name)
        if (p.parts[0] in ("runtime", ".venv", ".pytest_cache") or "__pycache__" in p.parts or
                p.name == ".env" or (p.name.startswith(".env.") and p.name != ".env.example") or
                p.suffix in (".sqlite", ".db", ".pyc") or ".sqlite-" in p.name):
            prohibited.append(name)
        content = (ROOT / name).read_bytes()
        if pattern.search(content) or (exact_secret and exact_secret in content):
            suspicious.append(name)
    assert not prohibited, "Prohibited tracked files: " + repr(prohibited)
    assert not suspicious, "Potential credential material; inspect these files: " + repr(suspicious)
    whitespace = subprocess.run(["git", "-c", "core.whitespace=trailing-space,space-before-tab,cr-at-eol",
                                 "diff", "--cached", "--check"], cwd=ROOT, capture_output=True)
    assert whitespace.returncode == 0, "Staged whitespace errors"
    print(json.dumps({"ok": True, "tracked_files": len(tracked), "scenario_hashes_verified": len(manifest["sha256"]),
                      "documents": 5, "offline_test_reports": len(test_reports), "real_attempt_manifests": len(real_manifests), "prohibited_tracked_files": 0,
                      "credential_pattern_hits": 0, "remote_push_performed": False,
                      "limitation": "Pattern scan is a submission check, not proof against every secret format."}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
