"""Tools own all evidence; models can propose actions but cannot supply approvals."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from .repository import Repository, RepositoryError
from .schemas import MaterialArgs, Request, SaveArgs, SlotArgs, SLOT, ToolResult, utc

ARGUMENT_MODELS = {"read_material": MaterialArgs, "check_rules": MaterialArgs,
                   "query_slots": SlotArgs, "save_draft": SaveArgs}
DESCRIPTIONS = {
    "read_material": "Read one requested material, missing critical fields, and any existing idempotent draft.",
    "check_rules": "Review a previously read material against demo rules. Never invent review evidence.",
    "query_slots": "Query hourly slots in [start,end) inside the request window, including conflicts. Query original first; query alternatives if occupied.",
    "save_draft": "Save ONE draft after successful read, rule check, and free-slot query. Hard-time changes automatically remain pending confirmation. Maximum two new save attempts per material.",
}


def success(code: str, data: dict, summary: str) -> ToolResult:
    return ToolResult(ok=True, code=code, data=data, summary=summary)


def failure(code: str, summary: str, data: dict | None = None) -> ToolResult:
    return ToolResult(ok=False, code=code, data=data or {}, summary=summary)


class Tools:
    def __init__(self, request: Request, repository: Repository, data_dir: Path, fail_saves: int = 0):
        self.request, self.repository = request, repository
        materials = json.loads((data_dir / "materials.json").read_text(encoding="utf-8"))
        self.materials = {m["material_id"]: m for m in materials}
        self.rules = json.loads((data_dir / "rules.json").read_text(encoding="utf-8"))
        self.fail_saves = fail_saves
        self.evidence: dict[str, dict] = {m: {"slots": {}, "errors": [], "save_attempts": 0}
                                          for m in request.material_ids}

    def execute(self, name: str, arguments: dict) -> ToolResult:
        if name not in ARGUMENT_MODELS:
            return failure("UNKNOWN_TOOL", "Tool is not available")
        try:
            args = ARGUMENT_MODELS[name].model_validate(arguments)
        except ValidationError:
            return failure("INVALID_ARGUMENTS", "Arguments do not match the tool schema")
        if args.material_id not in self.evidence:
            return failure("MATERIAL_OUT_OF_SCOPE", "Material is not part of this request")
        try:
            result = getattr(self, name)(args)
        except sqlite3.Error:
            result = failure("DATABASE_ERROR", "SQLite operation failed; no successful save is claimed")
        if not result.ok:
            self.evidence[args.material_id]["errors"].append({"tool": name, "code": result.code,
                                                             "summary": result.summary})
        return result

    def read_material(self, args: MaterialArgs) -> ToolResult:
        material = self.materials.get(args.material_id)
        if material is None:
            missing = ["material_record"]
        else:
            missing = [k for k in ("title", "asset_url", "rights_owner") if not material.get(k)]
        result = success("MATERIAL_READ", {
            "material": material, "missing_fields": missing,
            "review_status": "needs_information" if missing else None,
            "existing_draft": self.repository.get_draft(self.request.request_id, args.material_id),
        }, "Missing required fields: " + ", ".join(missing) if missing else "Material metadata is complete")
        self.evidence[args.material_id]["read"] = result.data
        return result

    def check_rules(self, args: MaterialArgs) -> ToolResult:
        state = self.evidence[args.material_id]
        if "read" not in state:
            return failure("EVIDENCE_REQUIRED", "Read material before checking rules")
        read = state["read"]
        risks = []
        for rule in self.rules:
            value = (read["material"] or {}).get(rule["field"])
            matches = ((rule["operator"] == "contains" and rule["value"] in str(value or "")) or
                       (rule["operator"] == "equals" and value == rule["value"]))
            if matches:
                risks.append({"rule_id": rule["rule_id"], "severity": rule["severity"], "reason": rule["reason"]})
        status = ("needs_information" if read["missing_fields"] else
                  "blocked" if any(r["severity"] == "block" for r in risks) else "passed")
        state["review"] = {"review_status": status, "risk_reasons": risks,
                           "missing_fields": read["missing_fields"], "demo_rules": True}
        return success("RULES_CHECKED", state["review"], "Demo-rule review: " + status)

    def _valid_range(self, start: datetime, end: datetime) -> bool:
        w = self.request.search_window
        return (w.start <= start < end <= w.end and not any(
            t.minute or t.second or t.microsecond for t in (start, end)))

    def query_slots(self, args: SlotArgs) -> ToolResult:
        if not self._valid_range(args.start, args.end):
            return failure("OUTSIDE_WINDOW", "Query must align to hourly slots inside [window.start,window.end)")
        slots, current = [], args.start
        while current + SLOT <= args.end:
            conflicts = self.repository.conflicts(self.request.channel, current, current + SLOT)
            slot = {"start": current.isoformat(), "end": (current + SLOT).isoformat(),
                    "available": not conflicts, "conflicts": conflicts}
            slots.append(slot)
            self.evidence[args.material_id]["slots"][utc(current)] = slot
            current += SLOT
        return success("SLOTS_QUERIED", {"slots": slots},
                       f"{sum(s['available'] for s in slots)}/{len(slots)} queried slots available")

    def save_draft(self, args: SaveArgs) -> ToolResult:
        state = self.evidence[args.material_id]
        if ("read" not in state or state["read"]["missing_fields"] or
                state.get("review", {}).get("review_status") != "passed"):
            return failure("REVIEW_REQUIRED", "Complete material and passing tool review are required")
        existing = self.repository.get_draft(self.request.request_id, args.material_id)
        if existing:
            return success("DRAFT_REUSED", {"draft": existing, "reused": True}, "Existing durable draft returned")
        if not self._valid_range(args.proposed_at, args.proposed_at + SLOT):
            return failure("OUTSIDE_WINDOW", "Proposed slot is outside the allowed hourly window")
        slot = state["slots"].get(utc(args.proposed_at))
        if not slot or not slot["available"]:
            return failure("SLOT_EVIDENCE_REQUIRED", "Query evidence for a free proposed slot is required")
        if state["save_attempts"] >= 2:
            return failure("SAVE_RETRY_LIMIT", "Two save attempts exhausted; stop or request manual handling")
        state["proposed_at"] = args.proposed_at.isoformat()
        state["save_attempts"] += 1
        pending = self.request.time_requirement == "hard" and args.proposed_at != self.request.requested_at
        inject = self.fail_saves > 0
        if inject:
            self.fail_saves -= 1
        try:
            draft, reused = self.repository.save(self.request, args.material_id, args.proposed_at, pending, inject)
        except RepositoryError as exc:
            # A racing save can invalidate earlier query evidence.
            if exc.code == "SLOT_CONFLICT":
                state["slots"].pop(utc(args.proposed_at), None)
            return failure(exc.code, "Save rejected by transactional validation")
        except sqlite3.Error:
            return failure("SAVE_FAILED", "SQLite save failed and transaction rolled back", {"retryable": True})
        return success("DRAFT_REUSED" if reused else "DRAFT_SAVED", {"draft": draft, "reused": reused},
                       "Draft persisted; pending confirmation" if pending else "Draft persisted; no publication performed")
