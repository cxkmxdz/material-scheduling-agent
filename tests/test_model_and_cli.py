import json
import os
import subprocess
import sys

import httpx
import pytest

from scheduling_agent.cli import main
from scheduling_agent.model import MockModel, ModelError, RealModel, function_tools
from scheduling_agent.schemas import Request
from scheduling_agent.trace import Trace


def reply(name="read_material", arguments=None):
    return {"choices": [{"message": {"tool_calls": [{"id": "test-call", "type": "function", "function": {
        "name": name, "arguments": json.dumps(arguments or {"material_id": "M01", "decision_summary": "Read metadata"})}}]}}]}


def test_real_adapter_sends_tools_and_observations(request_data):
    captured = []
    def handle(req):
        assert req.headers["authorization"] == "Bearer unit-test-secret"
        captured.append(json.loads(req.content))
        return httpx.Response(200, json=reply("finish", {"decision_summary": "Done"}))
    model = RealModel("unit-test-secret", "test-model", transport=httpx.MockTransport(handle))
    request = Request.model_validate(request_data)
    history = [{"action": {"tool": "query_slots", "arguments": {"material_id": "M01"}, "decision_summary": "Inspect"},
                "result": {"ok": True, "code": "SLOTS_QUERIED", "data": {"slots": []}, "summary": "No free slot"}}]
    try:
        assert model.decide(request, history).kind == "final"
    finally:
        model.close()
    sent = captured[0]
    assert sent["tool_choice"] == "required" and sent["parallel_tool_calls"] is False
    assert {t["function"]["name"] for t in sent["tools"]} == {"read_material", "check_rules", "query_slots", "save_draft", "finish"}
    assert sent["messages"][-1]["role"] == "tool"
    assert json.loads(sent["messages"][-1]["content"])["code"] == "SLOTS_QUERIED"
    assert sent["messages"][-2]["tool_calls"][0]["id"] == sent["messages"][-1]["tool_call_id"]


@pytest.mark.parametrize("status,code", [(401,"MODEL_AUTH_ERROR"), (403,"MODEL_AUTH_ERROR"), (429,"MODEL_RATE_OR_QUOTA_LIMIT"), (500,"MODEL_HTTP_ERROR")])
def test_api_errors_are_sanitized(request_data, status, code):
    model = RealModel("secret", "test", transport=httpx.MockTransport(lambda _: httpx.Response(status, text="private error body")))
    try:
        with pytest.raises(ModelError) as error:
            model.decide(Request.model_validate(request_data), [])
        assert error.value.code == code and "private" not in str(error.value)
    finally:
        model.close()


@pytest.mark.parametrize("exc,code", [(httpx.ReadTimeout("secret"), "MODEL_TIMEOUT"), (httpx.ConnectError("secret"), "MODEL_CONNECTION_ERROR")])
def test_timeout_and_connection_errors(request_data, exc, code):
    def handle(_):
        raise exc
    model = RealModel("secret", "test", transport=httpx.MockTransport(handle))
    try:
        with pytest.raises(ModelError, match=code):
            model.decide(Request.model_validate(request_data), [])
    finally:
        model.close()


@pytest.mark.parametrize("payload", [
    {}, {"choices": []}, {"choices": [{"message": {"content": "I saved draft-fake"}}]},
    {"choices": [{"message": {"tool_calls": []}}]},
    reply("read_material", {"material_id": "M01"}),
    reply("finish", {"decision_summary": "Done", "draft_id": "invented"}),
    {"choices": [{"message": {"tool_calls": [{"type": "function", "function": {"name": "finish", "arguments": "null"}}]}}]},
])
def test_malformed_model_response_cannot_fake_success(request_data, payload):
    model = RealModel("secret", "test", transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))
    try:
        with pytest.raises(ModelError, match="MODEL_RESPONSE_INVALID"):
            model.decide(Request.model_validate(request_data), [])
    finally:
        model.close()


def test_real_adapter_loop_with_fake_http_provider(execute):
    """Protocol integration only: fake provider uses MockModel; this is NOT real-model evidence."""
    seen = []
    def handle(req):
        body = json.loads(req.content)
        messages = body["messages"]
        request = Request.model_validate_json(messages[1]["content"])
        history = []
        for i in range(2, len(messages), 2):
            call = messages[i]["tool_calls"][0]["function"]
            args = json.loads(call["arguments"])
            summary = args.pop("decision_summary")
            history.append({"action": {"tool": call["name"], "arguments": args, "decision_summary": summary},
                            "result": json.loads(messages[i+1]["content"])})
        action = MockModel().decide(request, history)
        seen.append(history)
        if action.kind == "final":
            return httpx.Response(200, json=reply("finish", {"decision_summary": action.decision_summary}))
        return httpx.Response(200, json=reply(action.tool, dict(action.arguments, decision_summary=action.decision_summary)))
    model = RealModel("unit-test-secret", "FAKE-HTTP-PROVIDER", transport=httpx.MockTransport(handle))
    try:
        out, repo, _ = execute(occupied=True, fail_saves=1, model=model)
    finally:
        model.close()
    assert out.task_status == "completed" and out.items[0].confirmation_status == "pending_confirmation"
    assert len(repo.list_drafts()) == 1
    assert len(seen[-1]) == 6  # read, review, original, alternatives, failure, retry
    assert "unit-test-secret" not in open(out.trace_path, encoding="utf-8").read()


def test_trace_redacts_credentials_and_refuses_overwrite(tmp_path):
    path = tmp_path / "trace.jsonl"
    trace = Trace(path, "run", "real", "test", ("secret-credential",))
    trace.write(step=1, action="test", observation_summary="secret-credential", tool_status="error",
                observation={"nested": "secret-credential"})
    trace.close()
    assert "secret-credential" not in path.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        Trace(path, "other", "mock", "test")


def test_trace_redacts_escaped_secret_without_breaking_json(tmp_path):
    secret = 'key-with-"quote\\and-newline\n'
    path = tmp_path / "quoted.jsonl"
    trace = Trace(path, "run", "real", "test", (secret,))
    trace.write(step=1, action="test", observation_summary=secret, tool_status="error")
    trace.close()
    assert json.loads(path.read_text(encoding="utf-8"))["observation_summary"] == "[REDACTED]"


@pytest.mark.parametrize("key,name", [("", ""), ("key", ""), ("", "model")])
def test_missing_real_configuration(key, name):
    with pytest.raises(ModelError, match="MODEL_CONFIGURATION_MISSING"):
        RealModel(key, name)


def test_no_insecure_nonlocal_endpoint():
    with pytest.raises(ModelError, match="MODEL_BASE_URL_REQUIRES_HTTPS"):
        RealModel("key", "model", "http://example.test/v1")


def test_explicit_non_thinking_provider_configuration(request_data):
    sent = []
    def handle(req):
        sent.append(json.loads(req.content))
        data = reply("finish", {"decision_summary": "Stop"})
        data.update(id="response-test-123", model="provider-model", usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15, "private": "not-kept"})
        data["choices"][0]["message"]["reasoning_content"] = "private reasoning must not be retained"
        return httpx.Response(200, json=data)
    model = RealModel("secret", "test", thinking="disabled", transport=httpx.MockTransport(handle))
    try:
        model.decide(Request.model_validate(request_data), [])
        assert sent[0]["thinking"] == {"type": "disabled"}
        assert model.response_metadata == {"http_status": 200, "id": "response-test-123", "model": "provider-model",
                                           "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
        assert "reasoning" not in json.dumps(model.response_metadata)
    finally:
        model.close()


def test_default_payload_has_no_provider_specific_thinking_field(request_data):
    def handle(req):
        assert "thinking" not in json.loads(req.content)
        return httpx.Response(200, json=reply("finish", {"decision_summary": "Stop"}))
    model = RealModel("secret", "test", transport=httpx.MockTransport(handle))
    try:
        model.decide(Request.model_validate(request_data), [])
    finally:
        model.close()


def test_deepseek_endpoint_defaults_to_non_thinking_for_required_tools(request_data):
    def handle(req):
        assert json.loads(req.content)["thinking"] == {"type": "disabled"}
        return httpx.Response(200, json=reply("finish", {"decision_summary": "Stop"}))
    model = RealModel("secret", "deepseek-flash", base_url="https://api.deepseek.com", transport=httpx.MockTransport(handle))
    try:
        assert model.thinking == "disabled"
        model.decide(Request.model_validate(request_data), [])
    finally:
        model.close()


def test_auth_error_retains_http_status_without_response_body(request_data):
    model = RealModel("secret", "test", transport=httpx.MockTransport(lambda _: httpx.Response(401, text="private")))
    try:
        with pytest.raises(ModelError) as error:
            model.decide(Request.model_validate(request_data), [])
        assert error.value.details == {"http_status": 401}
        assert model.response_metadata == {"http_status": 401}
    finally:
        model.close()


def test_cli_runs_in_new_process_and_refuses_overwrite(tmp_path, request_data):
    input_path, output, trace = (tmp_path / n for n in ("input.json", "out.json", "trace.jsonl"))
    input_path.write_text(json.dumps(request_data), encoding="utf-8")
    command = [sys.executable, "-m", "scheduling_agent.cli", "run", "--input", str(input_path),
               "--db", str(tmp_path / "cli.sqlite"), "--output", str(output), "--trace", str(trace)]
    first = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    assert first.returncode == 0 and json.loads(output.read_text(encoding="utf-8"))["task_status"] == "completed"
    before = output.read_bytes()
    second = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    assert second.returncode == 2 and output.read_bytes() == before


def test_cli_reports_bad_input_without_stacktrace(tmp_path, capsys):
    source = tmp_path / "bad.json"
    source.write_text("{}", encoding="utf-8")
    assert main(["run", "--input", str(source)]) == 2
    assert json.loads(capsys.readouterr().err)["code"] == "ValidationError"
