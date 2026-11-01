import json
from datetime import datetime

import pytest

from scheduling_agent.model import MockModel, ModelError
from scheduling_agent.schemas import FinalAction, ToolAction


def records(output):
    return [json.loads(line) for line in open(output.trace_path, encoding="utf-8")]


def test_normal_is_a_durable_draft(execute):
    out, repo, _ = execute()
    item = out.items[0]
    assert out.task_status == "completed"
    assert item.review_status == "passed" and item.save_status == "saved"
    assert item.draft_id == repo.list_drafts()[0]["draft_id"]
    assert repo.list_drafts()[0]["published"] is False
    assert item.confirmation_status == "not_required"


@pytest.mark.parametrize("mid,missing", [("M02", ["asset_url", "rights_owner"]), ("M99", ["material_record"])])
def test_missing_information(execute, mid, missing):
    out, repo, _ = execute(changes={"material_ids": [mid]})
    assert out.task_status == "needs_input"
    assert out.items[0].review_status == "needs_information"
    assert out.items[0].missing_fields == missing
    assert repo.list_drafts() == [] and out.items[0].draft_id is None


@pytest.mark.parametrize("mid,rule", [("M03", "DEMO-R001"), ("M05", "DEMO-R002")])
def test_rule_risk(execute, mid, rule):
    out, repo, _ = execute(changes={"material_ids": [mid]})
    assert out.task_status == "blocked" and out.items[0].review_status == "blocked"
    assert rule in [r["rule_id"] for r in out.items[0].risk_reasons]
    assert repo.list_drafts() == []


def test_warning_is_explained_and_not_blocked(execute):
    out, repo, _ = execute(changes={"material_ids": ["M06"]})
    assert out.task_status == "completed"
    assert out.items[0].risk_reasons[0]["severity"] == "warning"
    assert len(repo.list_drafts()) == 1


def test_same_input_different_observation_changes_mock_actions(execute):
    free, _, _ = execute()
    conflict, repo, _ = execute(occupied=True)
    assert free.items[0].proposed_at.endswith("18:00:00+08:00")
    item = conflict.items[0]
    assert item.proposed_at.endswith("19:00:00+08:00")
    assert item.confirmation_status == "pending_confirmation" and item.pending_confirmations
    assert item.original_requirement["requested_at"].endswith("18:00:00+08:00")
    assert repo.list_drafts()[0]["reserves_slot"] is False
    assert len([r for r in records(free) if r["action"] == "query_slots"]) == 1
    assert len([r for r in records(conflict) if r["action"] == "query_slots"]) == 2


def test_flexible_alternative_within_window_reserves_slot(execute):
    out, repo, _ = execute(occupied=True, changes={"time_requirement": "flexible"})
    assert out.items[0].confirmation_status == "not_required"
    assert repo.list_drafts()[0]["reserves_slot"] is True


def test_no_slots(execute):
    out, repo, _ = execute(occupied=True, changes={"search_window": {
        "start": "2026-11-05T18:00:00+08:00", "end": "2026-11-05T19:00:00+08:00"}})
    assert out.task_status == "blocked"
    assert out.items[0].unfinished_reason.startswith("No free slot")
    assert not repo.list_drafts()


def test_duplicate_returns_same_id_without_more_rows(execute):
    first, repo, _ = execute()
    second, _, _ = execute(repo=repo)
    assert first.items[0].draft_id == second.items[0].draft_id
    assert len(repo.list_drafts()) == 1


def test_id_collision_never_overwrites(execute):
    first, repo, _ = execute()
    second, _, _ = execute(repo=repo, changes={"channel": "other"})
    assert second.task_status == "failed" and second.errors[0]["code"] == "REQUEST_ID_CONFLICT"
    assert second.items[0].draft_id is None
    assert repo.list_drafts()[0]["draft_id"] == first.items[0].draft_id


@pytest.mark.parametrize("failures,expected,count", [(1, "completed", 1), (2, "failed", 0), (10, "failed", 0)])
def test_failure_rollback_and_bounded_retry(execute, failures, expected, count):
    out, repo, _ = execute(fail_saves=failures)
    assert out.task_status == expected and len(repo.list_drafts()) == count
    saves = [r for r in records(out) if r["action"] == "save_draft"]
    assert len(saves) == 2 and saves[0]["observation"]["code"] == "SAVE_FAILED"
    if count == 0:
        assert out.items[0].draft_id is None and out.items[0].save_status == "failed"


@pytest.mark.parametrize("limits,reason", [({"max_steps": 1}, "step_limit"), ({"max_tools": 1}, "tool_limit")])
def test_limits_preserve_observations(execute, limits, reason):
    out, repo, _ = execute(**limits)
    assert out.task_status == "incomplete" and out.stop_reason == reason
    assert any(r["action"] == "read_material" for r in records(out))
    assert not repo.list_drafts()


def test_multi_material_local_success_does_not_hide_failure(execute):
    out, repo, _ = execute(changes={"material_ids": ["M01", "M02", "M03", "M04"]})
    assert out.task_status == "needs_input"
    assert [i.task_status for i in out.items] == ["completed", "needs_input", "blocked", "completed"]
    assert len(repo.list_drafts()) == 2
    assert out.items[3].confirmation_status == "pending_confirmation"


def test_all_multi_material_children_are_idempotent(execute):
    first, repo, _ = execute(changes={"material_ids": ["M01", "M04"]})
    second, _, _ = execute(repo=repo, changes={"material_ids": ["M04", "M01"]})
    assert {i.draft_id for i in first.items} == {i.draft_id for i in second.items}
    assert len(repo.list_drafts()) == 2


class ImmediateFinish(MockModel):
    def decide(self, request, history):
        return FinalAction(decision_summary="Stop without doing work")


def test_model_cannot_claim_completed_without_tools(execute):
    out, repo, _ = execute(model=ImmediateFinish())
    assert out.task_status == "incomplete" and not repo.list_drafts()


class ErrorModel(MockModel):
    def decide(self, request, history):
        raise ModelError("MODEL_TIMEOUT")


def test_model_error_is_explicit(execute):
    out, repo, _ = execute(model=ErrorModel())
    assert out.task_status == "failed" and out.errors[0]["code"] == "MODEL_TIMEOUT"
    assert not repo.list_drafts()


class CorrectAfterInvalid(MockModel):
    def decide(self, request, history):
        if not history:
            return ToolAction(tool="publish", arguments={}, decision_summary="Invalid tool attempt")
        return super().decide(request, history)


def test_invalid_tool_is_observation_model_can_correct(execute):
    out, repo, _ = execute(model=CorrectAfterInvalid())
    assert out.task_status == "completed"
    assert records(out)[1]["observation"]["code"] == "UNKNOWN_TOOL"
    assert len(repo.list_drafts()) == 1


def test_trace_contract_and_timestamp(execute):
    out, _, _ = execute()
    required = {"run_id", "mode", "model", "step", "action", "tool_arguments", "observation_summary", "tool_status", "decision_summary", "timestamp"}
    for record in records(out):
        assert required <= record.keys() and record["mode"] == "mock"
        assert record["run_id"] == out.run_id
        assert datetime.fromisoformat(record["timestamp"]).tzinfo
    assert all("observation" in r for r in records(out) if r["action"] in ("read_material", "check_rules", "query_slots", "save_draft"))
