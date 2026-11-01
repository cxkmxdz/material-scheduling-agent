"""Validated boundaries. Time intervals are half-open; every slot is one hour."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

SLOT = timedelta(hours=1)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class SearchWindow(StrictModel):
    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def validate_window(self):
        if not SLOT <= self.end - self.start <= timedelta(days=7):
            raise ValueError("search_window must span 1 hour to 7 days")
        return self


class Request(StrictModel):
    request_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    material_ids: list[str] = Field(min_length=1, max_length=20)
    channel: str = Field(min_length=1, max_length=100)
    requested_at: AwareDatetime
    time_requirement: Literal["hard", "flexible"]
    search_window: SearchWindow

    @model_validator(mode="after")
    def validate_request(self):
        if len(set(self.material_ids)) != len(self.material_ids) or any(not m.strip() for m in self.material_ids):
            raise ValueError("material_ids must be nonempty and unique")
        times = (self.requested_at, self.search_window.start, self.search_window.end)
        if any(t.minute or t.second or t.microsecond for t in times):
            raise ValueError("times must align to an hour boundary")
        if not self.search_window.start <= self.requested_at <= self.search_window.end - SLOT:
            raise ValueError("requested slot must fit inside [start, end)")
        return self

    def canonical(self) -> dict:
        obj = self.model_dump(mode="json")
        obj["material_ids"] = sorted(self.material_ids)
        obj["requested_at"] = utc(self.requested_at)
        obj["search_window"] = {"start": utc(self.search_window.start), "end": utc(self.search_window.end)}
        return obj

    def digest(self) -> str:
        return hashlib.sha256(dumps(self.canonical()).encode()).hexdigest()


class MaterialArgs(StrictModel):
    material_id: str


class SlotArgs(MaterialArgs):
    start: AwareDatetime
    end: AwareDatetime


class SaveArgs(MaterialArgs):
    proposed_at: AwareDatetime


class ToolAction(StrictModel):
    kind: Literal["tool"] = "tool"
    tool: str
    arguments: dict[str, Any]
    decision_summary: str = Field(min_length=1, max_length=600)


class FinalAction(StrictModel):
    kind: Literal["final"] = "final"
    decision_summary: str = Field(min_length=1, max_length=600)


class ToolResult(StrictModel):
    ok: bool
    code: str
    data: dict[str, Any] = Field(default_factory=dict)
    summary: str


class ItemOutput(StrictModel):
    material_id: str
    review_status: Literal["passed", "needs_information", "blocked"] | None = None
    risk_reasons: list[dict] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    original_requirement: dict
    proposed_at: str | None = None
    confirmation_status: Literal["not_required", "pending_confirmation"] = "not_required"
    pending_confirmations: list[str] = Field(default_factory=list)
    save_status: Literal["not_attempted", "saved", "failed"] = "not_attempted"
    draft_id: str | None = None
    task_status: Literal["completed", "needs_input", "blocked", "failed", "incomplete"] = "incomplete"
    unfinished_reason: str | None = None
    tool_errors: list[dict] = Field(default_factory=list)


class RunOutput(StrictModel):
    run_id: str
    mode: Literal["mock", "real"]
    model: str
    request_id: str
    task_status: Literal["completed", "needs_input", "blocked", "failed", "incomplete"]
    stop_reason: str
    steps: int
    tool_calls: int
    trace_path: str
    items: list[ItemOutput]
    errors: list[dict] = Field(default_factory=list)
    notice: str
