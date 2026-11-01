"""Audit tracked deliverables and recorded evidence; no network and no mutations."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads((ROOT / "examples/mock/manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["sha256"].items():
        assert hashlib.sha256((ROOT / "examples/mock" / name).read_bytes()).hexdigest() == expected, name
    assert len(list((ROOT / "docs").glob("*.md"))) == 5
    for name in ("test-results", "test-results-clean"):
        report = json.loads((ROOT / "examples" / name / "summary.json").read_text(encoding="utf-8"))
        assert report["exit_code"] == 0 and report["counts"]["failures"] == report["counts"]["errors"] == 0
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode("utf-8").split("\0")
    tracked = [f for f in tracked if f]
    assert tracked, "Stage or commit delivery files first"
    prohibited, suspicious = [], []
    pattern = re.compile(rb"(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9_]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")
    for name in tracked:
        p = Path(name)
        if (p.parts[0] in ("runtime", ".venv", ".pytest_cache") or "__pycache__" in p.parts or
                p.name == ".env" or (p.name.startswith(".env.") and p.name != ".env.example") or
                p.suffix in (".sqlite", ".db", ".pyc") or ".sqlite-" in p.name):
            prohibited.append(name)
        if pattern.search((ROOT / name).read_bytes()):
            suspicious.append(name)
    assert not prohibited, "Prohibited tracked files: " + repr(prohibited)
    assert not suspicious, "Potential credential material; inspect these files: " + repr(suspicious)
    whitespace = subprocess.run(["git", "-c", "core.whitespace=trailing-space,space-before-tab,cr-at-eol",
                                 "diff", "--cached", "--check"], cwd=ROOT, capture_output=True)
    assert whitespace.returncode == 0, "Staged whitespace errors"
    print(json.dumps({"ok": True, "tracked_files": len(tracked), "scenario_hashes_verified": len(manifest["sha256"]),
                      "documents": 5, "offline_test_reports": 2, "prohibited_tracked_files": 0,
                      "credential_pattern_hits": 0, "remote_push_performed": False,
                      "limitation": "Pattern scan is a submission check, not proof against every secret format."}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
