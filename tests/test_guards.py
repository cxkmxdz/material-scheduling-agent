from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytest
from pydantic import ValidationError

from scheduling_agent.repository import Repository, RepositoryError
from scheduling_agent.schemas import Request, SLOT
from conftest import evidence


@pytest.mark.parametrize("arguments,code", [
    ({"material_id": "M01", "proposed_at": "2026-11-05T18:00:00+08:00"}, "REVIEW_REQUIRED"),
    ({"material_id": "M01", "proposed_at": "2026-11-05T18:00:00+08:00", "review_status": "passed"}, "INVALID_ARGUMENTS"),
    ({"material_id": "M01", "proposed_at": "2026-11-05T18:00:00+08:00", "confirmed": True}, "INVALID_ARGUMENTS"),
    ({"material_id": "M01", "proposed_at": "2026-11-05T18:00:00"}, "INVALID_ARGUMENTS"),
    ({"material_id": "M04", "proposed_at": "2026-11-05T18:00:00+08:00"}, "MATERIAL_OUT_OF_SCOPE"),
])
def test_forged_save_args_are_rejected(context, arguments, code):
    _, repo, tools = context
    assert tools.execute("save_draft", arguments).code == code
    assert not repo.list_drafts()


def test_read_and_review_do_not_replace_slot_evidence(context):
    _, repo, tools = context
    tools.execute("read_material", {"material_id": "M01"})
    tools.execute("check_rules", {"material_id": "M01"})
    assert tools.execute("save_draft", {"material_id": "M01", "proposed_at": "2026-11-05T18:00:00+08:00"}).code == "SLOT_EVIDENCE_REQUIRED"
    assert not repo.list_drafts()


@pytest.mark.parametrize("mid", ["M02", "M03"])
def test_model_cannot_bypass_bad_material(tmp_path, request_data, mid):
    from scheduling_agent.tools import Tools
    from conftest import DATA
    request = Request.model_validate(dict(request_data, material_ids=[mid]))
    repo = Repository(tmp_path / "guard.sqlite")
    repo.register(request)
    tools = Tools(request, repo, DATA)
    evidence(tools, mid)
    assert tools.execute("save_draft", {"material_id": mid, "proposed_at": request.requested_at.isoformat()}).code == "REVIEW_REQUIRED"
    assert not repo.list_drafts()


@pytest.mark.parametrize("value", ["2026-11-05T21:00:00+08:00", "2026-11-05T17:00:00+08:00", "2026-11-05T18:30:00+08:00"])
def test_window_and_grid_save_guard(context, value):
    _, repo, tools = context
    evidence(tools)
    assert tools.execute("save_draft", {"material_id": "M01", "proposed_at": value}).code == "OUTSIDE_WINDOW"
    assert not repo.list_drafts()


def test_stale_free_evidence_is_rechecked_atomically(context):
    request, repo, tools = context
    evidence(tools)
    repo.seed([{"schedule_id": "race", "channel": "demo", "start": request.requested_at.isoformat(), "end": (request.requested_at + SLOT).isoformat()}])
    result = tools.execute("save_draft", {"material_id": "M01", "proposed_at": request.requested_at.isoformat()})
    assert result.code == "SLOT_CONFLICT" and not repo.list_drafts()


def test_retry_limit_even_if_model_keeps_calling(context):
    request, repo, tools = context
    evidence(tools)
    tools.fail_saves = 99
    args = {"material_id": "M01", "proposed_at": request.requested_at.isoformat()}
    assert [tools.execute("save_draft", args).code for _ in range(3)] == ["SAVE_FAILED", "SAVE_FAILED", "SAVE_RETRY_LIMIT"]
    assert not repo.list_drafts()


def test_transaction_rollback_then_idempotent_reuse(context):
    request, repo, tools = context
    evidence(tools)
    tools.fail_saves = 1
    args = {"material_id": "M01", "proposed_at": request.requested_at.isoformat()}
    assert tools.execute("save_draft", args).code == "SAVE_FAILED"
    assert repo.list_drafts() == []
    first = tools.execute("save_draft", args)
    second = tools.execute("save_draft", args)
    assert first.ok and second.code == "DRAFT_REUSED"
    assert first.data["draft"]["draft_id"] == second.data["draft"]["draft_id"]


def test_pending_proposals_do_not_reserve_but_regular_drafts_do(context):
    request, repo, tools = context
    evidence(tools)
    pending_start = request.requested_at + SLOT
    tools.execute("save_draft", {"material_id": "M01", "proposed_at": pending_start.isoformat()})
    assert not repo.conflicts("demo", pending_start, pending_start + SLOT)
    assert repo.list_drafts()[0]["confirmation_status"] == "pending_confirmation"


def test_half_open_conflicts_include_partial_overlap(context):
    request, repo, _ = context
    repo.seed([{"schedule_id": "partial", "channel": "demo", "start": "2026-11-05T18:30:00+08:00", "end": "2026-11-05T19:30:00+08:00"}])
    assert repo.conflicts("demo", request.requested_at, request.requested_at + SLOT)
    assert repo.conflicts("demo", request.requested_at + SLOT, request.requested_at + 2*SLOT)
    assert not repo.conflicts("demo", request.requested_at + 2*SLOT, request.requested_at + 3*SLOT)
    assert not repo.conflicts("other", request.requested_at, request.requested_at + SLOT)


def test_parallel_same_key_has_one_draft(context):
    request, repo, _ = context
    def save(_):
        return repo.save(request, "M01", request.requested_at, False)[0]["draft_id"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(save, range(8)))
    assert len(set(ids)) == 1 and len(repo.list_drafts()) == 1


def test_parallel_distinct_requests_cannot_double_reserve(context, request_data):
    request, repo, _ = context
    other = Request.model_validate(dict(request_data, request_id="req-other"))
    repo.register(other)
    def save(req):
        try:
            repo.save(req, "M01", req.requested_at, False)
            return "saved"
        except RepositoryError as exc:
            return exc.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(save, [request, other]))
    assert sorted(outcomes) == ["SLOT_CONFLICT", "saved"] and len(repo.list_drafts()) == 1


def test_request_normalization_ignores_timezone_spelling(context, request_data):
    request, repo, _ = context
    raw = dict(request_data, requested_at="2026-11-05T10:00:00Z", search_window={"start": "2026-11-05T10:00:00Z", "end": "2026-11-05T13:00:00Z"})
    equivalent = Request.model_validate(raw)
    assert request.digest() == equivalent.digest()
    repo.register(equivalent)


@pytest.mark.parametrize("changes", [
    {"requested_at": "2026-11-05T18:00:00"}, {"requested_at": "2026-11-05T18:30:00+08:00"},
    {"material_ids": ["M01", "M01"]}, {"material_ids": []}, {"request_id": "../bad"},
    {"time_requirement": "anything"}, {"requested_at": "2026-11-05T21:00:00+08:00"},
    {"search_window": {"start": "2026-11-05T18:00:00+08:00", "end": "2026-11-04T21:00:00+08:00"}},
])
def test_invalid_inputs_are_rejected(request_data, changes):
    with pytest.raises(ValidationError):
        Request.model_validate(dict(request_data, **changes))
