import json
from pathlib import Path

import pytest

from scheduling_agent.agent import run_agent
from scheduling_agent.model import MockModel
from scheduling_agent.repository import Repository
from scheduling_agent.schemas import Request
from scheduling_agent.tools import Tools

DATA = Path(__file__).resolve().parents[1] / "data"


@pytest.fixture
def request_data():
    return {"request_id": "req-test", "material_ids": ["M01"], "channel": "demo",
            "requested_at": "2026-11-05T18:00:00+08:00", "time_requirement": "hard",
            "search_window": {"start": "2026-11-05T18:00:00+08:00", "end": "2026-11-05T21:00:00+08:00"}}


@pytest.fixture
def context(tmp_path, request_data):
    request = Request.model_validate(request_data)
    repo = Repository(tmp_path / "test.sqlite")
    repo.register(request)
    return request, repo, Tools(request, repo, DATA)


@pytest.fixture
def execute(tmp_path, request_data):
    counter = 0

    def run(*, changes=None, occupied=False, fail_saves=0, repo=None, model=None, **limits):
        nonlocal counter
        counter += 1
        raw = dict(request_data)
        raw.update(changes or {})
        request = Request.model_validate(raw)
        repo = repo or Repository(tmp_path / f"db-{counter}.sqlite")
        if occupied:
            repo.seed(json.loads((DATA / "schedules.json").read_text(encoding="utf-8")))
        tools = Tools(request, repo, DATA, fail_saves)
        out = run_agent(request, model or MockModel(), tools, tmp_path / f"trace-{counter}.jsonl", **limits)
        return out, repo, tools

    return run


def evidence(tools, mid="M01"):
    assert tools.execute("read_material", {"material_id": mid}).ok
    assert tools.execute("check_rules", {"material_id": mid}).ok
    assert tools.execute("query_slots", {"material_id": mid, "start": tools.request.search_window.start.isoformat(),
                                        "end": tools.request.search_window.end.isoformat()}).ok
