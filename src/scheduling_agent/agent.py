"""Decision → tool → observation loop; final truth is derived from guarded evidence."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .model import Model, ModelError
from .repository import RepositoryError
from .schemas import FinalAction, ItemOutput, Request, RunOutput, SLOT, ToolAction, utc
from .tools import Tools
from .trace import Trace


def _items(request: Request, tools: Tools, registered: bool) -> list[ItemOutput]:
    results = []
    for mid in request.material_ids:
        state = tools.evidence[mid]
        item = ItemOutput(material_id=mid, original_requirement=request.model_dump(mode="json"),
                          tool_errors=state["errors"])
        read, review = state.get("read", {}), state.get("review", {})
        item.missing_fields = read.get("missing_fields", [])
        item.review_status = review.get("review_status") or read.get("review_status")
        item.risk_reasons = review.get("risk_reasons", [])
        if "proposed_at" in state:
            item.proposed_at = state["proposed_at"]
            if request.time_requirement == "hard" and datetime.fromisoformat(item.proposed_at) != request.requested_at:
                item.confirmation_status = "pending_confirmation"
                item.pending_confirmations = ["Confirm proposed time change before any execution"]
        saved = tools.repository.get_draft(request.request_id, mid) if registered else None
        if not registered:
            item.task_status, item.unfinished_reason = "failed", "Request registration failed; see run errors"
        elif saved:
            item.review_status = "passed"  # A durable draft was guarded at creation.
            item.proposed_at = saved["proposed_at"]
            item.confirmation_status = saved["confirmation_status"]
            item.save_status, item.draft_id = "saved", saved["draft_id"]
            item.task_status = "completed"
            if item.confirmation_status == "pending_confirmation":
                item.pending_confirmations = ["Confirm change from " + request.requested_at.isoformat() + " to " + saved["proposed_at"]]
        elif item.missing_fields:
            item.task_status, item.unfinished_reason = "needs_input", "Provide missing fields: " + ", ".join(item.missing_fields)
        elif item.review_status == "blocked":
            item.task_status, item.unfinished_reason = "blocked", "Blocking demo rules must be resolved"
        elif state["save_attempts"]:
            item.save_status, item.task_status = "failed", "failed"
            item.unfinished_reason = "No durable draft after save attempts"
        else:
            current, all_occupied = request.search_window.start, True
            while current + SLOT <= request.search_window.end:
                slot = state["slots"].get(utc(current))
                if not slot or slot["available"]:
                    all_occupied = False
                    break
                current += SLOT
            if all_occupied:
                item.task_status, item.unfinished_reason = "blocked", "No free slot inside the search window"
            else:
                item.unfinished_reason = "Required tool evidence or durable save is incomplete"
        results.append(item)
    return results


def run_agent(request: Request, model: Model, tools: Tools, trace_path: str | Path,
              max_steps: int = 24, max_tools: int = 24) -> RunOutput:
    if max_steps < 1 or max_tools < 1:
        raise ValueError("limits must be positive")
    run_id = "run-" + uuid4().hex
    trace = Trace(trace_path, run_id, model.mode, model.name, getattr(model, "secrets", ()))
    history, errors = [], []
    step, calls, registered = 0, 0, False
    stop = "step_limit"
    try:
        trace.write(step=0, action="start", observation_summary="Run started", tool_status="ok",
                    request=request.model_dump(mode="json"), max_steps=max_steps, max_tools=max_tools,
                    notice="Scripted offline simulation" if model.mode == "mock" else "Real API adapter; inspect errors for actual availability")
        try:
            tools.repository.register(request)
            registered = True
        except RepositoryError as exc:
            errors.append({"code": exc.code, "summary": "Request ID is already bound to different normalized content"})
            stop = "request_rejected"
        except sqlite3.Error:
            errors.append({"code": "DATABASE_ERROR", "summary": "Could not register request"})
            stop = "database_error"
        if registered:
            for step in range(1, max_steps + 1):
                try:
                    action = model.decide(request, history)
                    if not isinstance(action, (ToolAction, FinalAction)):
                        raise ModelError("MODEL_RESPONSE_INVALID")
                except ModelError as exc:
                    errors.append({"code": exc.code, "summary": "Model decision failed; no implicit retry"})
                    trace.write(step=step, action="model_error", tool_status="error",
                                observation_summary=exc.code)
                    stop = "model_error"
                    break
                if isinstance(action, FinalAction):
                    trace.write(step=step, action="finish", tool_status="ok", decision_summary=action.decision_summary,
                                observation_summary="Model requested stop; runtime verifies final state")
                    stop = "model_finished"
                    break
                if calls >= max_tools:
                    stop = "tool_limit"
                    trace.write(step=step, action="limit", tool_status="not_executed", tool_arguments=action.arguments,
                                decision_summary=action.decision_summary, observation_summary="Tool-call budget exhausted")
                    break
                calls += 1
                result = tools.execute(action.tool, action.arguments)
                history.append({"action": action.model_dump(), "result": result.model_dump(mode="json")})
                trace.write(step=step, action=action.tool, tool_arguments=action.arguments,
                            decision_summary=action.decision_summary, observation_summary=result.summary,
                            tool_status="ok" if result.ok else "error", observation=result.model_dump(mode="json"))
        try:
            items = _items(request, tools, registered)
        except sqlite3.Error:
            # If final DB verification fails, do not invent a successful save or draft ID.
            items = [ItemOutput(material_id=m, original_requirement=request.model_dump(mode="json"),
                                task_status="failed", unfinished_reason="Final database verification failed") for m in request.material_ids]
            errors.append({"code": "DATABASE_VERIFICATION_FAILED", "summary": "Final persistent state unavailable"})
        priorities = ("failed", "incomplete", "needs_input", "blocked", "completed")
        status = next(s for s in priorities if any(i.task_status == s for i in items))
        if errors:
            status = "failed"
        elif stop in ("step_limit", "tool_limit"):
            status = "incomplete"
        output = RunOutput(run_id=run_id, mode=model.mode, model=model.name, request_id=request.request_id,
                           task_status=status, stop_reason=stop, steps=step, tool_calls=calls,
                           trace_path=str(Path(trace_path).resolve()), items=items, errors=errors,
                           notice="MOCK: validates local flow only, not real-model decisions. Drafts only; nothing published." if model.mode == "mock" else "Real API mode. Drafts only; nothing published. Check status and errors.")
        trace.write(step=step, action="result", tool_status=status, observation_summary=stop,
                    output=output.model_dump(mode="json"))
        return output
    finally:
        trace.close()
