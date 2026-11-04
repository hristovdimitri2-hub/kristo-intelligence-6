# -*- coding: utf-8 -*-
"""The legacy SSE transport must not be able to take the whole worker down.

F-21 in docs/PERFORMANCE_AND_ARCHITECTURE_AUDIT.md: POST /mcp/sse holds a worker
thread for each open stream, the endpoint is free, unauthenticated and was in
neither X402_FREE_ENDPOINTS nor X402_PAID_ENDPOINTS, and Procfile runs one worker
with eight threads. Eight anonymous connections therefore left no thread for
anything else, /health included, for a full idle window at a time - and a repeated
curl loop is a total outage.

The cap is on concurrency rather than request rate because the exhausted resource
is threads. A rate limit would still admit eight connections if they arrived spaced
apart, which is exactly the shape of the attack.

Nothing paying can be refused by this: the streamable POST /mcp transport, which is
what modern clients speak, is uncapped, and this one is free.
"""
import io
import re

import pytest


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    from integrations.catalog_store import create_catalog_store

    monkeypatch.setattr(
        main, "catalog_store", create_catalog_store(tmp_path / "catalog.db"))
    return main.app.test_client()


@pytest.fixture()
def sse(monkeypatch):
    from app.blueprints import discovery
    monkeypatch.setattr(discovery, "_SSE_SESSIONS", {})
    return discovery


def test_the_cap_is_below_the_thread_pool_it_protects(sse):
    """Read the real pool size out of Procfile instead of trusting a comment.

    If the cap ever reaches the thread count, or the pool ever shrinks under the
    cap, one client filling the cap alone can starve every other request - which is
    the defect. Checking the file means the two numbers cannot drift apart silently.
    """
    text = io.open("Procfile", encoding="utf-8").read()
    threads = re.search(r"--threads\s+(\d+)", text)
    workers = re.search(r"--workers\s+(\d+)", text)

    assert threads, "Procfile no longer states a thread count: %r" % text
    thread_count = int(threads.group(1))
    worker_count = int(workers.group(1)) if workers else 1

    assert sse._SSE_MAX_SESSIONS >= 1
    assert sse._SSE_MAX_SESSIONS < worker_count * thread_count, (
        "the SSE cap (%d) is not below the thread pool (%d worker(s) x %d threads); "
        "one client filling it can starve /health"
        % (sse._SSE_MAX_SESSIONS, worker_count, thread_count))
    assert sse._SSE_MAX_SESSIONS * 2 <= worker_count * thread_count, (
        "the cap should leave at least as many threads free as it hands out")


def test_the_last_free_thread_is_refused_with_retry_after(client, sse):
    """One past the cap: 503 and a Retry-After, not a pinned thread."""
    for index in range(sse._SSE_MAX_SESSIONS):
        sse._SSE_SESSIONS["held-%d" % index] = object()

    response = client.get("/mcp/sse")
    assert response.status_code == 503, (
        "with %d of %d sessions open the route answered %s instead of shedding "
        "load; it pins a worker thread per open stream"
        % (len(sse._SSE_SESSIONS), sse._SSE_MAX_SESSIONS, response.status_code))
    assert response.headers.get("Retry-After"), "a shed request must say when to retry"

    body = response.get_json()
    message = body["error"]["message"]
    assert "POST /mcp" in message, (
        "the refusal must name the uncapped transport (%r)" % message)
    assert "concurrent SSE sessions" in message


def test_a_refused_request_never_enters_the_session_table(client, sse):
    """The refusal must not leak a session, or the cap ratchets itself shut."""
    for index in range(sse._SSE_MAX_SESSIONS):
        sse._SSE_SESSIONS["held-%d" % index] = object()
    before = len(sse._SSE_SESSIONS)

    client.get("/mcp/sse")
    client.get("/mcp/sse")

    assert len(sse._SSE_SESSIONS) == before, (
        "refused requests were added to the table: %d -> %d"
        % (before, len(sse._SSE_SESSIONS)))


def test_under_the_cap_the_stream_is_still_served(client, sse):
    """The fix must shed load, not break the transport."""
    response = client.get("/mcp/sse")

    assert response.status_code == 200
    assert "text/event-stream" in response.content_type
    assert len(sse._SSE_SESSIONS) <= sse._SSE_MAX_SESSIONS
