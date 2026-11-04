# -*- coding: utf-8 -*-
"""server.json has a hard size limit that our own validator does not check.

Publishing 6.2.0 to the official MCP registry failed with:

    _meta.io.modelcontextprotocol.registry/publisher-provided extension exceeds
    4KB limit (4575 bytes)

`mcp-publisher validate` had just said "server.json is valid" for the same file. The
validator and the server disagree, so nothing in the repository could have caught
this: the registry sat at 6.1.0 while the repository moved on, and the only symptom
was a version that never appeared.

The block had grown to 4560 bytes of two kinds of repetition:

  * `paid_endpoints` repeated each tool's endpoint and price_usd, both already on the
    tool entry;
  * "Paid via x402 (HTTP 402 challenge with the exact USDC amount and receiver on
    Base)." ended all six descriptions, while `pricing.note` states it once.

The limit is the registry's, so these tests measure the same thing it measures - the
compact JSON encoding, not the pretty-printed file - and they leave headroom, because
a block that just fits is a block that breaks on the next small addition.
"""
import io
import json

SERVER_JSON = "server.json"
META_KEY = "io.modelcontextprotocol.registry/publisher-provided"

#: The registry's own limit, in bytes, as it reported it.
REGISTRY_LIMIT = 4096

#: A block that merely fits will fail on the next edit. Keep room to breathe.
REQUIRED_HEADROOM = 200


def _meta_bytes(meta):
    """The size the registry measures: compact JSON, UTF-8."""
    return len(json.dumps(meta, ensure_ascii=False,
                          separators=(",", ":")).encode("utf-8"))


def _load():
    doc = json.loads(io.open(SERVER_JSON, encoding="utf-8").read())
    return doc, doc["_meta"][META_KEY]


def test_the_publisher_provided_extension_fits_the_registry_limit():
    """The defect itself, measured the way the registry measures it."""
    _doc, meta = _load()
    size = _meta_bytes(meta)

    assert size <= REGISTRY_LIMIT, (
        "the publisher-provided extension is %d bytes and the registry rejects "
        "anything over %d. Publishing fails with a 400 that no local check reports: "
        "`mcp-publisher validate` calls this file valid. Trim repetition, not facts."
        % (size, REGISTRY_LIMIT))


def test_the_extension_keeps_headroom_below_the_limit():
    """So the next small addition does not silently break publishing again."""
    _doc, meta = _load()
    size = _meta_bytes(meta)
    headroom = REGISTRY_LIMIT - size

    assert headroom >= REQUIRED_HEADROOM, (
        "only %d bytes of headroom below the registry's %d-byte limit (%d used). "
        "The last time this block crept over, publishing stopped for every version "
        "afterwards without a single failing test"
        % (headroom, REGISTRY_LIMIT, size))


def test_every_advertised_tool_is_complete_without_a_duplicate_list():
    """The tools replaced `paid_endpoints`, so they must carry what it carried."""
    _doc, meta = _load()
    tools = meta["tools"]

    assert tools, "the extension advertises no tools"
    for tool in tools:
        for field in ("name", "description", "endpoint", "price_usd"):
            assert field in tool, (
                "tool %r has no %r; the block no longer carries a separate "
                "paid_endpoints list, so each tool entry must be self-contained"
                % (tool.get("name"), field))
        assert str(tool["endpoint"]).startswith("/"), (
            "tool %r has endpoint %r, which is not a path"
            % (tool["name"], tool["endpoint"]))

    endpoints = [tool["endpoint"] for tool in tools]
    assert len(set(endpoints)) == len(endpoints), (
        "two tools advertise the same endpoint: %s" % sorted(endpoints))


def test_the_block_does_not_repeat_the_challenge_sentence():
    """Repetition is what pushed it over the limit. pricing.note says it once."""
    _doc, meta = _load()
    text = json.dumps(meta, ensure_ascii=False)
    phrase = "HTTP 402 challenge with the exact USDC amount"

    assert text.count(phrase) <= 1, (
        "the challenge sentence appears %d times. It belongs in pricing.note once, "
        "not at the end of every tool description - that repetition is what took the "
        "block past 4KB" % text.count(phrase))


def test_the_server_identity_and_version_are_present():
    """A publish with no version, or a name outside our namespace, would fail."""
    doc, _meta = _load()

    assert doc["name"].startswith("io.github.hristovdimitri2-hub/"), (
        "name %r is outside the namespace this account can publish" % doc["name"])
    assert doc.get("version"), "server.json declares no version"
    assert doc.get("remotes"), "server.json declares no remotes"
