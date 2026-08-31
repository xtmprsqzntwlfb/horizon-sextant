"""Tests for tool dispatch and the read-only agentic loop (no live cloud)."""

import json

import pytest

from conftest import (
    FakeClient,
    final_message,
    make_server,
    text_block,
    tool_use_block,
)


# --------------------------------------------------------------------------- #
# Tool dispatch
# --------------------------------------------------------------------------- #
def test_list_instances_summarizes_and_flags_truncation(api):
    from sextant.agent import tools

    servers = [make_server(id="i-%d" % n) for n in range(tools.MAX_ITEMS + 5)]
    api.nova.server_list = lambda request, search_opts=None: (servers, False)

    result = tools.list_instances(request=object())

    assert result["count_returned"] == tools.MAX_ITEMS
    assert result["truncated"] is True
    first = result["instances"][0]
    assert first["id"] == "i-0"
    assert first["host"] == "compute-1"
    assert first["horizon_url"] == "/admin/instances/i-0/detail"


def test_list_instances_passes_filters(api):
    from sextant.agent import tools

    captured = {}

    def fake_list(request, search_opts=None):
        captured.update(search_opts)
        return ([], False)

    api.nova.server_list = fake_list
    tools.list_instances(request=object(), status="error", host="compute-9")

    assert captured["all_tenants"] is True
    assert captured["status"] == "ERROR"          # upper-cased
    assert captured["host"] == "compute-9"


def test_execute_tool_unknown_returns_error(api):
    from sextant.agent import tools

    out = tools.execute_tool(object(), "does_not_exist", {})
    assert out["is_error"] is True
    assert "Unknown tool" in out["content"]


def test_execute_tool_wraps_exceptions(api):
    from sextant.agent import tools

    def boom(request, search_opts=None):
        raise RuntimeError("nova is down")

    api.nova.server_list = boom
    out = tools.execute_tool(object(), "list_instances", {})

    assert out["is_error"] is True
    assert "nova is down" in out["content"]


def test_execute_tool_returns_json_on_success(api):
    from sextant.agent import tools

    api.nova.server_list = lambda request, search_opts=None: ([make_server()], False)
    out = tools.execute_tool(object(), "list_instances", {})

    assert out["is_error"] is False
    payload = json.loads(out["content"])          # must be valid JSON
    assert payload["instances"][0]["name"] == "web01"


def test_connectivity_flags_missing_floating_ip(api):
    from sextant.agent import tools

    api.nova.server_get = lambda request, iid: make_server(id=iid, status="ACTIVE")
    api.neutron.port_list = lambda request, device_id=None: []
    api.neutron.tenant_floating_ip_list = lambda request: []

    result = tools.check_instance_connectivity(object(), "i-1")

    assert any("No floating IP" in o for o in result["observations"])


def test_connectivity_flags_non_active_instance(api):
    from sextant.agent import tools

    api.nova.server_get = lambda request, iid: make_server(id=iid, status="ERROR")
    api.neutron.port_list = lambda request, device_id=None: []
    api.neutron.tenant_floating_ip_list = lambda request: []

    result = tools.check_instance_connectivity(object(), "i-1")

    assert any("not ACTIVE" in o for o in result["observations"])


# --------------------------------------------------------------------------- #
# Agentic loop
# --------------------------------------------------------------------------- #
def test_loop_runs_tool_then_answers(api, monkeypatch):
    from sextant.agent import loop

    # Real tool will be dispatched; back it with a fake nova call.
    calls = {"server_list": 0}

    def fake_list(request, search_opts=None):
        calls["server_list"] += 1
        return ([make_server()], False)

    api.nova.server_list = fake_list

    # Script two turns: (1) call list_instances, (2) final answer.
    turns = [
        {
            "texts": ["Let me look.\n"],
            "final": final_message(
                "tool_use", [tool_use_block("t1", "list_instances", {})]),
        },
        {
            "texts": ["You have 1 instance: web01."],
            "final": final_message(
                "end_turn", [text_block("You have 1 instance: web01.")]),
        },
    ]
    monkeypatch.setattr(loop, "get_client", lambda: FakeClient(turns))

    events = list(loop.run_agent(
        request=object(),
        messages=[{"role": "user", "content": "list my instances"}],
    ))

    types_seen = [e["type"] for e in events]
    assert "tool_call" in types_seen
    assert "tool_result" in types_seen
    assert types_seen[-1] == "done"

    tool_call = next(e for e in events if e["type"] == "tool_call")
    assert tool_call["name"] == "list_instances"

    # The real tool actually ran (once) against the fake API.
    assert calls["server_list"] == 1

    # Final answer text was streamed.
    answer = "".join(e["text"] for e in events if e["type"] == "token")
    assert "web01" in answer


def test_loop_reports_client_error(api, monkeypatch):
    from sextant.agent import loop

    def raising_client():
        raise RuntimeError("no api key")

    monkeypatch.setattr(loop, "get_client", raising_client)

    events = list(loop.run_agent(
        request=object(),
        messages=[{"role": "user", "content": "hi"}],
    ))

    assert events == [] or events[0]["type"] == "error"
    assert any(e["type"] == "error" and "no api key" in e["message"]
               for e in events)


def test_loop_surfaces_tool_errors_but_continues(api, monkeypatch):
    from sextant.agent import loop

    # Tool raises -> dispatch returns is_error; loop should feed it back and
    # still reach the model's final answer.
    def boom(request, search_opts=None):
        raise RuntimeError("nova exploded")

    api.nova.server_list = boom

    turns = [
        {
            "texts": [""],
            "final": final_message(
                "tool_use", [tool_use_block("t1", "list_instances", {})]),
        },
        {
            "texts": ["I couldn't reach Nova."],
            "final": final_message(
                "end_turn", [text_block("I couldn't reach Nova.")]),
        },
    ]
    monkeypatch.setattr(loop, "get_client", lambda: FakeClient(turns))

    events = list(loop.run_agent(
        request=object(),
        messages=[{"role": "user", "content": "list"}],
    ))

    tool_result = next(e for e in events if e["type"] == "tool_result")
    assert tool_result["is_error"] is True
    assert events[-1]["type"] == "done"
