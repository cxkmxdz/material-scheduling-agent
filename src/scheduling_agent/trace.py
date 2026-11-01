"""Append-only JSONL observations, with credential redaction at serialization boundary."""
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any


class Trace:
    def __init__(self, path: str | Path, run_id: str, mode: str, model: str,
                 secrets: tuple[str, ...] = ()):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents accidental overwriting of earlier evidence.
        self.file = self.path.open("x", encoding="utf-8")
        self.base = {"run_id": run_id, "mode": mode, "model": model}
        self.secrets = tuple(s for s in secrets if s)

    def write(self, *, step: int, action: str, tool_arguments: dict | None = None,
              observation_summary: str, tool_status: str,
              decision_summary: str = "", **extra: Any):
        record = dict(self.base, step=step, action=action, tool_arguments=tool_arguments or {},
                      observation_summary=observation_summary, tool_status=tool_status,
                      decision_summary=decision_summary, timestamp=datetime.now(timezone.utc).isoformat(), **extra)
        def redact(value):
            if isinstance(value, str):
                for secret in sorted(self.secrets, key=len, reverse=True):
                    value = value.replace(secret, "[REDACTED]")
                return value
            if isinstance(value, dict):
                return {redact(str(k)): redact(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [redact(v) for v in value]
            return value
        line = json.dumps(redact(record), ensure_ascii=False, default=str)
        self.file.write(line + "\n")
        self.file.flush()

    def close(self):
        self.file.close()
