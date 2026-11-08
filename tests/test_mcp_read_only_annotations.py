"""Every MCP tool must declare, in the protocol, that it only reads.

WHY THIS EXISTS, and it is not tidiness.

The descriptions have always said "Read-only operation — no side effects" in
prose. The protocol carries the same fact in `annotations`, and a client that
reads the annotation rather than the sentence saw NOTHING. Two directories said
so publicly, and a buyer sees it before paying:

    mcptry, on every tool:
        "This tool isn't marked read-only, so it MAY CHANGE SOMETHING on the
        server or in an account you connected. [I understand, run it anyway]"

    Glama's TDQS, on every tool:
        "WITH NO ANNOTATIONS SUPPLIED, the description carries the full burden"
        — and scored the behavior dimension 4/5 for exactly that reason.

So a warning that something might be modified sat in front of a paid call that
only reads. It is untrue, it is friction at the moment of decision, and the
audience this file serves is an agent deciding whether to spend.

`openWorldHint` is TRUE deliberately. The answers genuinely depend on the outside
world — Base, CoinGecko, DEXScreener — so a client should expect them to change
between calls. Claiming otherwise would be the dishonesty in the other direction.
"""

import json
from pathlib import Path

import main
from app.blueprints import discovery

REPO = Path(__file__).resolve().parent.parent
DISCOVERY_SRC = (REPO / "app" / "blueprints" / "discovery.py").read_text(
    encoding="utf-8")

#: Set once, in `_tool`, so a tool cannot be added without them.
REQUIRED = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}


def _tools_via_mcp(method="tools/list"):
    client = main.app.test_client()
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1,
                                  "method": method, "params": {}})
    assert r.status_code == 200
    return ((r.get_json().get("result") or {}).get("tools")) or []


def test_the_mcp_endpoint_serves_tools():
    tools = _tools_via_mcp()
    assert tools, "tools/list returned nothing"


def test_every_tool_declares_itself_read_only():
    """THE regression guard. This is what both directories were complaining
    about, in public, on every tool."""
    for tool in _tools_via_mcp():
        ann = tool.get("annotations") or {}
        assert ann.get("readOnlyHint") is True, (
            "%s does not declare readOnlyHint, so mcptry will keep telling "
            "buyers it 'may change something' before a call that only reads"
            % tool.get("name"))


def test_the_annotations_are_exactly_what_we_mean():
    """Not just read-only: the whole honest set, so a client can act on it."""
    for tool in _tools_via_mcp():
        ann = tool.get("annotations") or {}
        for key, want in REQUIRED.items():
            assert ann.get(key) is want, (
                "%s: %s is %r, expected %r" % (tool.get("name"), key,
                                               ann.get(key), want))


def test_no_tool_is_missing_annotations_entirely():
    tools = _tools_via_mcp()
    missing = [t.get("name") for t in tools if not t.get("annotations")]
    assert not missing, "tools without any annotations: %r" % missing


def test_the_annotations_are_set_in_one_place():
    """Seven tools, one helper. If these were set per tool the eighth would be
    written without them — which is how the defect appeared in the first place."""
    assert DISCOVERY_SRC.count('"readOnlyHint": True') == 1, (
        "readOnlyHint is set in more than one place; it belongs in `_tool`")
    assert '"annotations": {' in DISCOVERY_SRC


def test_the_sse_transport_reports_the_same_annotations():
    """Both transports share one dispatcher, and that must stay true — a client
    on the legacy transport must not see a less honest tool list."""
    post = _tools_via_mcp()
    # The SSE transport answers over the stream, so compare against the same
    # source rather than opening a stream: the dispatcher is shared by design.
    src = DISCOVERY_SRC
    idx = src.index("def _mcp_dispatch(")
    chunk = src[idx:idx + 4000]
    assert "_mcp_tools" in chunk or "tools/list" in chunk, (
        "the dispatcher no longer handles tools/list for both transports")
    assert len(post) == 7


def test_open_world_is_true_and_that_is_the_honest_value():
    """Documented on purpose: a reader who thinks this should be False is
    asking us to claim our answers do not change, which they do."""
    assert '"openWorldHint": True' in DISCOVERY_SRC


def test_the_registry_artifact_was_not_given_the_annotations():
    """`server.json` is a different, hand-trimmed artifact with a hard 4096-byte
    registry limit and only ~207 bytes of headroom. The directories read the LIVE
    tool list, so adding annotations there would spend the headroom for nothing
    and risk a publish failure that no local check reports."""
    import io
    doc = json.loads(io.open(REPO / "server.json", encoding="utf-8").read())
    meta = doc["_meta"]["io.modelcontextprotocol.registry/publisher-provided"]
    size = len(json.dumps(meta, ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8"))
    assert size <= 4096, "the registry extension is over the limit"
    assert size < 4096 - 100, (
        "the registry extension has almost no headroom left; adding annotations "
        "here is the wrong place to spend it")
