"""Acceptance checks use actual traces and database snapshots, never model claims."""
from __future__ import annotations

from datetime import datetime

from .schemas import Request, RunOutput, SLOT


def _same_time(a: str | None, b) -> bool:
    return bool(a) and datetime.fromisoformat(a) == b


def evaluate_condition(name: str, request: Request, output: RunOutput,
                       drafts: list[dict], records: list[dict]) -> dict:
    item = output.items[0]
    events = [r for r in records if "observation" in r]
    actions = [{"step": r["step"], "action": r["action"],
                "arguments": r.get("tool_arguments", {}), "code": r.get("observation", {}).get("code"),
                "decision_summary": r.get("decision_summary", "")}
               for r in records if r["action"] not in ("start", "result")]
    saves = [r for r in events if r["action"] == "save_draft"]
    queries = [r for r in events if r["action"] == "query_slots" and r["observation"]["ok"]]
    original_slots = [(r, s) for r in queries for s in r["observation"]["data"]["slots"]
                      if _same_time(s["start"], request.requested_at)]
    checks = {
        "real_mode": output.mode == "real" and all(r["mode"] == "real" for r in records),
        "model_finished_without_api_error": output.stop_reason == "model_finished" and not output.errors,
        "passing_review_observed": any(r["action"] == "check_rules" and r["observation"]["ok"] and
                                       r["observation"]["data"].get("review_status") == "passed" for r in events),
        "original_requirement_preserved": item.original_requirement == request.model_dump(mode="json"),
        "no_publication": all(d.get("published") is False and d.get("record_type") == "draft" for d in drafts),
        "database_output_consistent": ({item.draft_id} == {d["draft_id"] for d in drafts}) if item.save_status == "saved" else not drafts and item.draft_id is None,
    }
    reactions = []
    if name == "free":
        free_reads = [r for r, s in original_slots if s["available"]]
        checks.update({
            "original_slot_available_observed": bool(free_reads),
            "saved_original_slot_after_observation": any(
                s["observation"]["ok"] and _same_time(s["tool_arguments"].get("proposed_at"), request.requested_at)
                and any(q["step"] < s["step"] for q in free_reads) for s in saves),
            "completed_saved_without_confirmation": output.task_status == "completed" and item.save_status == "saved"
                and _same_time(item.proposed_at, request.requested_at) and item.confirmation_status == "not_required",
            "ordinary_draft_reserves_slot": len(drafts) == 1 and drafts[0]["reserves_slot"] is True,
        })
    elif name == "occupied":
        conflicts = [r for r, s in original_slots if not s["available"]]
        alt_saves = [s for s in saves if s["observation"]["ok"] and not _same_time(s["tool_arguments"].get("proposed_at"), request.requested_at)]
        for conflict in conflicts:
            followups = [a for a in actions if a["step"] > conflict["step"]]
            if followups:
                reactions.append({"observation_step": conflict["step"], "observation": "original_slot_occupied",
                                  "next_model_action": followups[0]})
        proposed = datetime.fromisoformat(item.proposed_at) if item.proposed_at else None
        checks.update({
            "original_conflict_observed": bool(conflicts),
            "alternative_chosen_after_conflict": any(c["step"] < s["step"] for c in conflicts for s in alt_saves),
            "free_alternative_evidence_before_save": any(
                q["step"] < s["step"] and slot["available"] and _same_time(slot["start"], datetime.fromisoformat(s["tool_arguments"]["proposed_at"]))
                for q in queries for slot in q["observation"]["data"]["slots"] for s in alt_saves),
            "alternative_inside_window": proposed is not None and request.search_window.start <= proposed <= request.search_window.end - SLOT,
            "completed_saved_pending_confirmation": output.task_status == "completed" and item.save_status == "saved"
                and item.confirmation_status == "pending_confirmation" and bool(item.pending_confirmations),
            "pending_draft_does_not_reserve": len(drafts) == 1 and drafts[0]["reserves_slot"] is False,
        })
    elif name == "save_failure":
        failures = [s for s in saves if s["observation"]["code"] == "SAVE_FAILED"]
        for failed in failures:
            followups = [a for a in actions if a["step"] > failed["step"] and a["action"] != "model_error"]
            if followups:
                reactions.append({"observation_step": failed["step"], "observation": "sqlite_save_failed",
                                  "next_model_action": followups[0]})
        checks.update({
            "real_save_failure_observed": bool(failures),
            "bounded_save_attempts": 1 <= len(saves) <= 2,
            "model_decision_after_failure": bool(reactions),
            "failed_without_fake_id": output.task_status == "failed" and item.save_status == "failed" and item.draft_id is None,
            "database_rolled_back": not drafts,
        })
    else:
        raise ValueError("Unknown comparison condition")
    return {"condition": name, "run_id": output.run_id, "model": output.model,
            "observed_status": output.task_status, "stop_reason": output.stop_reason,
            "proposed_at": item.proposed_at, "confirmation_status": item.confirmation_status,
            "save_status": item.save_status, "draft_id": item.draft_id,
            "database_draft_count": len(drafts), "errors": output.errors,
            "acceptance_met": all(checks.values()), "checks": checks,
            "actions": actions, "observed_reactions": reactions, "tool_calls": output.tool_calls,
            "output": name + ".output.json", "trace": name + ".trace.jsonl",
            "database": name + ".database.json"}
