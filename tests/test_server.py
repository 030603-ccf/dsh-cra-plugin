"""Protocol layer tests for the hand-written JSON-RPC stdio server.

These feed JSON lines into stdin and assert the exact wire responses, locking
down the riskiest hand-rolled code: version negotiation, error codes,
notification semantics, and parse errors.
"""

import io
import json
import sys

import pytest

from lra_mcp import server


def _run_server(lines: list[str]) -> list[dict]:
    """Feed JSON lines into the server's stdin; return parsed stdout responses."""
    stdin = io.StringIO("\n".join(lines) + "\n")
    stdout = io.StringIO()
    old_in, old_out = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = stdin, stdout
    try:
        server.main()
    finally:
        sys.stdin, sys.stdout = old_in, old_out
    return [json.loads(l) for l in stdout.getvalue().splitlines() if l.strip()]


def test_initialize_negotiates_version():
    out = _run_server([
        '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05"}}',
    ])
    assert out[0]["id"] == 1
    assert out[0]["result"]["protocolVersion"] == "2024-11-05"
    assert out[0]["result"]["capabilities"] == {"tools": {}}
    assert out[0]["result"]["serverInfo"]["name"] == "lra"
    assert out[0]["result"]["serverInfo"]["version"] == "0.1.0"


def test_ping():
    out = _run_server(['{"jsonrpc":"2.0","id":2,"method":"ping"}'])
    assert out[0] == {"jsonrpc": "2.0", "id": 2, "result": {}}


def test_tools_list_has_all_four_tools():
    out = _run_server(['{"jsonrpc":"2.0","id":3,"method":"tools/list"}'])
    tools = out[0]["result"]["tools"]
    assert {t["name"] for t in tools} == {
        "review_project", "review_diff", "get_finding", "generate_fix_prompt",
    }
    for t in tools:
        assert t["inputSchema"]["type"] == "object"


def test_parse_error_returns_minus_32700():
    out = _run_server(['this is not json'])
    assert out[0]["id"] is None
    assert out[0]["error"]["code"] == -32700


def test_method_not_found_returns_minus_32601():
    out = _run_server(['{"jsonrpc":"2.0","id":9,"method":"bogus/method"}'])
    assert out[0]["id"] == 9
    assert out[0]["error"]["code"] == -32601


def test_notification_produces_no_response():
    # notifications/* must be silently dropped; only the ping replies
    out = _run_server([
        '{"jsonrpc":"2.0","method":"notifications/initialized"}',
        '{"jsonrpc":"2.0","id":5,"method":"ping"}',
    ])
    assert len(out) == 1
    assert out[0]["id"] == 5


def test_tools_call_success_wraps_text(monkeypatch):
    monkeypatch.setattr(server, "_dispatch", lambda name, args: {"ok": True, "name": name})
    out = _run_server([
        '{"jsonrpc":"2.0","id":4,"method":"tools/call",'
        '"params":{"name":"review_project","arguments":{"path":"/x"}}}',
    ])
    result = out[0]["result"]
    assert result["isError"] is False
    assert result["content"][0]["type"] == "text"
    assert json.loads(result["content"][0]["text"]) == {"ok": True, "name": "review_project"}


def test_tools_call_error_is_marked_isError(monkeypatch):
    def boom(name, args):
        raise server.LraMcpError("UNKNOWN_TOOL", name=name)

    monkeypatch.setattr(server, "_dispatch", boom)
    out = _run_server([
        '{"jsonrpc":"2.0","id":5,"method":"tools/call",'
        '"params":{"name":"nope","arguments":{}}}',
    ])
    result = out[0]["result"]
    assert result["isError"] is True
    assert json.loads(result["content"][0]["text"])["code"] == "UNKNOWN_TOOL"


def test_tools_call_internal_error_keeps_traceback_out_of_client(monkeypatch):
    def boom(name, args):
        raise RuntimeError("boom secret details")

    monkeypatch.setattr(server, "_dispatch", boom)
    out = _run_server([
        '{"jsonrpc":"2.0","id":6,"method":"tools/call",'
        '"params":{"name":"x","arguments":{}}}',
    ])
    result = out[0]["result"]
    assert result["isError"] is True
    payload = json.loads(result["content"][0]["text"])
    assert payload["code"] == "INTERNAL_ERROR"
    # 完整 traceback（栈帧/文件路径）只进 stderr；客户端只拿到 code + 截断的异常消息
    assert "Traceback" not in result["content"][0]["text"]
    assert "boom secret details" in payload["detail"]
