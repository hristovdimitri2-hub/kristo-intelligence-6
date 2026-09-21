"""Tests for the SLEEPING stdio bridge (scripts/mcp_stdio_bridge.py).

The bridge is deliberately not wired into any start command — it activates only
if Glama refuses a remote URL or if we ever want a Render-independent listing.
These tests keep it honest and ready:

* every payload must come from the REAL /mcp handler (no reimplementation),
* notifications and blank lines must never produce a frame,
* stdout stays protocol-only (one JSON line per request, nothing else),
* and the sleeping decision itself is asserted, so wiring it up is a conscious
  change rather than an accident.
"""

import importlib
import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.setenv("KRISTO_ALLOW_MOCK_PAYMENTS", "true")
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    import main
    from integrations.crm_store import CRMStore
    from integrations.stripe_checkout import StripeCheckoutService

    monkeypatch.setattr(main, "crm_store", CRMStore(tmp_path / "crm.db"))
    monkeypatch.setattr(main, "stripe_checkout", StripeCheckoutService())
    return main.app.test_client()


@pytest.fixture()
def bridge():
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    return importlib.import_module("scripts.mcp_stdio_bridge")


def _line(bridge, client, payload):
    return bridge.handle_line(json.dumps(payload), client)


def test_initialize_reaches_the_real_handler(bridge, client):
    reply = _line(bridge, client, {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05"}})
    assert reply["jsonrpc"] == "2.0" and reply["id"] == 1
    assert reply["result"]["serverInfo"]["name"] == "kristo-intelligence"
    assert reply["result"]["protocolVersion"] == "2024-11-05"
    assert "tools" in reply["result"]["capabilities"]


def test_tools_list_advertises_the_paid_tools(bridge, client):
    reply = _line(bridge, client, {"jsonrpc": "2.0", "id": 2,
                                   "method": "tools/list"})
    tools = reply["result"]["tools"]
    assert {"get_market_stats", "get_onchain_sales", "get_bot_status"} <= {
        t["name"] for t in tools}
    for tool in tools:
        assert tool["x402"]["price_usdc"] > 0


def test_tools_call_returns_x402_instructions_not_execution(bridge, client):
    reply = _line(bridge, client, {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "get_market_stats", "arguments": {}}})
    result = reply["result"]
    assert "x402" in result["content"][0]["text"]
    assert result["structuredContent"]["x402"]["endpoint"].endswith("/api/stats")


def test_unknown_method_is_answered_by_the_real_router(bridge, client):
    """A reimplementation would not know this code — the real router returns it."""
    reply = _line(bridge, client, {"jsonrpc": "2.0", "id": 4,
                                   "method": "bogus/method"})
    assert reply["error"]["code"] == -32601


def test_notifications_never_get_a_reply(bridge, client):
    assert bridge.handle_line(
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        client) is None
    # A message without an id is a notification even with a normal method name.
    assert bridge.handle_line(json.dumps({"jsonrpc": "2.0",
                                          "method": "ping"}), client) is None


def test_blank_lines_are_ignored(bridge, client):
    assert bridge.handle_line("   \n", client) is None


def test_parse_error_envelope(bridge, client):
    reply = bridge.handle_line("not json at all", client)
    assert reply["error"]["code"] == -32700 and reply["id"] is None


def test_non_object_message_is_invalid_request(bridge, client):
    reply = bridge.handle_line("[1, 2, 3]", client)
    assert reply["error"]["code"] == -32600


def test_run_writes_exactly_one_line_per_request(bridge, client):
    stream = io.StringIO()
    payload = "\n".join([
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        "",
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "ping"}),
        json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/list"}),
        "   ",
    ]) + "\n"
    rc = bridge.run(in_stream=io.StringIO(payload), out_stream=stream,
                    client=client)
    assert rc == 0
    lines = [ln for ln in stream.getvalue().splitlines() if ln.strip()]
    assert len(lines) == 3
    assert [json.loads(ln)["id"] for ln in lines] == [1, 2, 3]


def test_importing_the_bridge_does_not_hijack_stdout(bridge, client):
    """The fd duplication must stay lazy: tests (and imports) keep stdout."""
    bridge.run(in_stream=io.StringIO(""), out_stream=io.StringIO(), client=client)
    assert bridge._PROTOCOL_OUT is None


def test_bridge_is_not_wired_into_any_start_command():
    """SLEEPING ASSET: wiring it into a CMD must be a deliberate change."""
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    procfile = (ROOT / "Procfile").read_text(encoding="utf-8")
    assert "mcp_stdio_bridge" not in dockerfile
    assert "mcp_stdio_bridge" not in procfile
    # …and the HTTP entrypoints are the ones actually declared.
    assert "main:app" in dockerfile and "main:app" in procfile
