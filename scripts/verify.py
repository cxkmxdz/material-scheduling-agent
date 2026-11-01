"""Run pytest and retain measured, machine-readable evidence. Never manufacture counts."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, default=ROOT / "runtime" / ("tests-" + datetime.now().strftime("%Y%m%d-%H%M%S")))
    args = p.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    command = [sys.executable, "-m", "pytest", "-q", "--junitxml=" + str(out / "pytest.xml")]
    started = datetime.now(timezone.utc).isoformat()
    clock = time.perf_counter()
    result = subprocess.run(command, cwd=ROOT, env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                            capture_output=True, text=True, encoding="utf-8")
    duration = time.perf_counter() - clock
    (out / "pytest.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
    counts = {}
    if (out / "pytest.xml").exists():
        tree = ET.parse(out / "pytest.xml")
        for suite in tree.findall("testsuite"):
            # Do not put this computer's host name into shareable evidence.
            if "hostname" in suite.attrib:
                suite.set("hostname", "local")
            for key in ("tests", "failures", "errors", "skipped"):
                counts[key] = counts.get(key, 0) + int(suite.get(key, "0"))
        tree.write(out / "pytest.xml", encoding="utf-8", xml_declaration=True)
    report = {"started_at": started, "duration_seconds": round(duration, 3), "exit_code": result.returncode,
              "command": "python -m pytest -q --junitxml=<output>/pytest.xml", "counts": counts,
              "python": platform.python_version(), "platform": platform.system(),
              "versions": {name: importlib.metadata.version(name) for name in
                           ("material-scheduling-agent", "httpx", "pydantic", "python-dotenv", "pytest")},
              "boundary": "Offline tests only. httpx.MockTransport tests are fake HTTP responses, not real-model validation."}
    (out / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
