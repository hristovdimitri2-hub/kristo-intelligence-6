# -*- coding: utf-8 -*-
"""One Web3 per (class, url, timeout) — the pool actually pools.

THE LEAK THIS PINS. Seven call sites built `Web3(Web3.HTTPProvider(...))` inside
the function that needed it and never closed it. Each construction creates a
requests.Session, its urllib3 pool, its sockets and SSL buffers, and web3's own
object graph. On the Render service the container reached its 512 MiB ceiling in
about an hour and was OOM-killed on a 55-60 minute rhythm, and the growth was
measured as time-driven rather than workload-driven: across 16 clean 20-minute
windows the correlation with every logged activity was r <= 0.16, while the
per-call Web3 sites run on fixed cadences and log nothing.

The counts that motivate the tests: the blockchain monitor (~2 constructions per
minute), the reorg watch (up to 25 height reads per agent cycle, every 5 minutes)
and the whale scan (1 per minute) — roughly 8 per minute, against a measured
growth of 4.15 MiB/min after the unrelated isolation fix landed.
"""
import sys
from types import SimpleNamespace

import pytest


@pytest.fixture()
def pool(monkeypatch):
    """A fake web3 module, installed the way the suite's other tests do it."""
    import services.rpc_pool as rpc_pool
    rpc_pool.reset_clients()

    class FakeWeb3:
        built = 0

        def __init__(self, provider):
            FakeWeb3.built += 1
            self.provider = provider

        class HTTPProvider:  # noqa: N801
            def __init__(self, url, request_kwargs=None):
                self.url = url
                self.request_kwargs = request_kwargs

    fake = SimpleNamespace(Web3=FakeWeb3)
    monkeypatch.setitem(sys.modules, "web3", fake)
    yield rpc_pool, FakeWeb3
    rpc_pool.reset_clients()


def test_the_same_url_and_timeout_reuse_one_client(pool):
    """The whole point: a second call must not build a second session."""
    rpc_pool, FakeWeb3 = pool
    first = rpc_pool.get_web3("https://rpc.example", 30)
    second = rpc_pool.get_web3("https://rpc.example", 30)
    assert first is second
    assert FakeWeb3.built == 1, (
        "%d clients built for two identical calls — each one leaks a session"
        % FakeWeb3.built)


def test_a_different_timeout_is_not_silently_shared(pool):
    """A caller must never be handed a deadline it did not ask for.

    The sites use 15s, 20s and 30s for genuinely different jobs, so the timeout
    is part of the key rather than whatever the first caller happened to pass.
    """
    rpc_pool, FakeWeb3 = pool
    thirty = rpc_pool.get_web3("https://rpc.example", 30)
    twenty = rpc_pool.get_web3("https://rpc.example", 20)
    assert thirty is not twenty
    assert twenty.provider.request_kwargs["timeout"] == 20
    assert thirty.provider.request_kwargs["timeout"] == 30
    assert FakeWeb3.built == 2


def test_a_different_url_gets_its_own_client(pool):
    rpc_pool, FakeWeb3 = pool
    a = rpc_pool.get_web3("https://rpc-a.example", 30)
    b = rpc_pool.get_web3("https://rpc-b.example", 30)
    assert a is not b
    assert a.provider.url == "https://rpc-a.example"
    assert b.provider.url == "https://rpc-b.example"
    assert FakeWeb3.built == 2


def test_the_class_is_part_of_the_key_so_tests_cannot_leak_into_each_other(pool,
                                                                          monkeypatch):
    """The suite installs a fake web3 per test and imports it lazily.

    A cache keyed only by url would hand test two the client test one installed.
    The class is in the key, so a new fake gets a new client while production —
    always the real web3.Web3 — still collapses to one.
    """
    rpc_pool, first_fake = pool
    rpc_pool.get_web3("https://rpc.example", 30)

    class SecondFake:
        built = 0

        def __init__(self, provider):
            SecondFake.built += 1
            self.provider = provider

        class HTTPProvider:  # noqa: N801
            def __init__(self, url, request_kwargs=None):
                pass

    monkeypatch.setitem(sys.modules, "web3", SimpleNamespace(Web3=SecondFake))
    rpc_pool.get_web3("https://rpc.example", 30)
    assert SecondFake.built == 1, (
        "a different Web3 class reused the previous class's client")
    assert rpc_pool.client_count() == 2


def test_the_client_count_stays_bounded_under_repeated_use(pool):
    """The property that matters operationally: usage must not grow the pool.

    Before this existed the equivalent number was unbounded — one construction
    per call, never closed.
    """
    rpc_pool, FakeWeb3 = pool
    for _ in range(200):
        rpc_pool.get_web3("https://rpc.example", 30)
        rpc_pool.get_web3("https://rpc.example", 20)
    assert rpc_pool.client_count() == 2, (
        "the pool grew to %d after 400 calls" % rpc_pool.client_count())
    assert FakeWeb3.built == 2


def test_the_default_url_follows_configuration(pool, monkeypatch):
    """No caller may pin a host the configuration has moved away from."""
    rpc_pool, _fake = pool
    monkeypatch.setenv("BASE_RPC_URL", "https://configured.example")
    client = rpc_pool.get_web3()
    assert client.provider.url == "https://configured.example"
