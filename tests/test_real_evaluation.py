"""Synthetic unit fixtures test the evaluator; these tests do not call a real provider."""
import json

from scheduling_agent.evaluation import evaluate_condition
from scheduling_agent.model import FinalAction, MockModel, ModelError


def fixture_evaluation(out, repo, tools, name, *, simulate_mode=True):
    records = [json.loads(line) for line in open(out.trace_path, encoding="utf-8")]
    if simulate_mode:
        # Only in-memory fixture flags, never written into shareable real evidence.
        out = out.model_copy(update={"mode": "real"})
        for row in records:
            row["mode"] = "real"
    return evaluate_condition(name, tools.request, out, repo.list_drafts(), records)


def test_mock_evidence_is_not_real_validation(execute):
    out, repo, tools = execute()
    report = fixture_evaluation(out, repo, tools, "free", simulate_mode=False)
    assert not report["acceptance_met"] and not report["checks"]["real_mode"]


def test_free_evaluation_checks_observed_save_and_db(execute):
    out, repo, tools = execute()
    report = fixture_evaluation(out, repo, tools, "free")
    assert report["acceptance_met"] and report["checks"]["saved_original_slot_after_observation"]
    out.items[0].proposed_at = "2026-11-05T10:00:00+00:00"
    assert fixture_evaluation(out, repo, tools, "free")["acceptance_met"]  # same instant


def test_occupied_evaluation_checks_confirmation_and_reaction(execute):
    out, repo, tools = execute(occupied=True)
    report = fixture_evaluation(out, repo, tools, "occupied")
    assert report["acceptance_met"]
    assert report["observed_reactions"][0]["next_model_action"]["action"] == "query_slots"
    out.items[0].confirmation_status = "not_required"
    assert not fixture_evaluation(out, repo, tools, "occupied")["acceptance_met"]


def test_failure_evaluation_requires_tool_failure_and_subsequent_decision(execute):
    out, repo, tools = execute(fail_saves=2)
    report = fixture_evaluation(out, repo, tools, "save_failure")
    assert report["acceptance_met"]
    assert [r["next_model_action"]["action"] for r in report["observed_reactions"]] == ["save_draft", "finish"]


class ErrorAfterSave(MockModel):
    def decide(self, request, history):
        if history and history[-1]["action"]["tool"] == "save_draft":
            raise ModelError("MODEL_TIMEOUT")
        return super().decide(request, history)


def test_api_error_after_failed_save_cannot_pass_evaluation(execute):
    out, repo, tools = execute(fail_saves=2, model=ErrorAfterSave())
    assert out.task_status == "failed" and out.items[0].save_status == "failed"
    report = fixture_evaluation(out, repo, tools, "save_failure")
    assert not report["acceptance_met"]
    assert not report["checks"]["model_finished_without_api_error"]
    assert not report["checks"]["model_decision_after_failure"]


class StopAfterSaveError(MockModel):
    def decide(self, request, history):
        if history and history[-1]["action"]["tool"] == "save_draft":
            return FinalAction(decision_summary="Stop after observing save failure")
        return super().decide(request, history)


def test_model_may_stop_after_one_save_error(execute):
    out, repo, tools = execute(fail_saves=2, model=StopAfterSaveError())
    report = fixture_evaluation(out, repo, tools, "save_failure")
    assert report["acceptance_met"] and len(report["observed_reactions"]) == 1
