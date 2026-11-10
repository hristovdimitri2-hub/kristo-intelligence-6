"""One Web3 per (class, RPC url, timeout) per process, instead of one per call.

THE LEAK THIS EXISTS FOR. Seven call sites in this codebase built their own
Web3 — `Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": N}))` — inside the
function that needed it, and never closed it. Each construction creates a
`requests.Session`, its urllib3 pool, its sockets and SSL buffers, and web3's own
object graph. None of it is ever released, so the process grows for as long as it
runs.

MEASURED, on the Render service on 2026-11-10. The container grew to its 512 MiB
ceiling in about an hour, every hour, and was OOM-killed on a 55-60 minute rhythm.
A read-only forensics pass established three things:

  * the leak is NOT recent — the growth regime changed on 2026-11-07 (median
    3.42 MiB/min, 13 of 15 instances "fast", against 0.5-1.1 MiB/min before);
  * the growth is TIME-driven, not workload-driven: across 16 clean 20-minute
    windows the correlation with every logged activity (health hits, scans,
    Stripe calls, agent cycles) was r <= 0.16, and the same per-minute workload
    produced 1.34 MiB/min in one window and 5.13 MiB/min in another;
  * the sites that consume Web3 on a fixed cadence and log nothing are exactly
    these — the blockchain monitor (~2/min), the reorg watch (up to 25 height
    reads per agent cycle, every 5 minutes) and the whale scan (1/min), about
    8 constructions per minute.

8/min against the measured 4.15 MiB/min implies roughly 0.5 MiB retained per
construction, which is the expected order for a Web3 instance plus its session,
pool and SSL context. That is a hypothesis the metric will confirm or refute
after deploy; it is not asserted as proven here.

WHY THE CACHE IS KEYED BY THE CLASS TOO, and not just by url. The test suite
installs a fake `web3` module per test and relies on the function importing it
lazily, so a cache keyed only by url would hand test two the fake installed by
test one. Including the class object in the key keeps each fake's clients
separate while still collapsing to a single client in production, where the class
is always the real `web3.Web3`. It also keeps a reference to that class, so the
key cannot be recycled by the garbage collector.

The provider is shared between threads. urllib3's pool is thread-safe and the
provider sets no cookies and mutates no per-request state, which is why this is
safe here; it is also what the existing `_payment_verify_w3` global in main.py
already relies on.
"""

from __future__ import annotations

import os
import threading

#: (Web3 class, rpc url, timeout seconds) -> the one client for that combination.
_CLIENTS: dict = {}
_LOCK = threading.Lock()

DEFAULT_RPC = "https://mainnet.base.org"
DEFAULT_TIMEOUT = 30


def default_rpc_url() -> str:
    """The configured Base RPC, or the public endpoint as a last resort."""
    return os.getenv("BASE_RPC_URL", DEFAULT_RPC)


def get_web3(url: str = "", timeout: int = DEFAULT_TIMEOUT):
    """Return the shared Web3 for `url`, constructing it once.

    `url` defaults to BASE_RPC_URL. Callers that used a different timeout keep it,
    because the timeout is part of the key — a client is never silently handed a
    deadline its caller did not ask for.
    """
    from web3 import Web3  # imported here so tests can substitute the module

    url = url or default_rpc_url()
    key = (Web3, url, int(timeout))

    client = _CLIENTS.get(key)
    if client is not None:
        return client

    with _LOCK:
        client = _CLIENTS.get(key)
        if client is None:
            client = Web3(Web3.HTTPProvider(
                url, request_kwargs={"timeout": int(timeout)}))
            _CLIENTS[key] = client
    return client


def client_count() -> int:
    """How many clients this process is holding. A leak makes this grow."""
    return len(_CLIENTS)


def reset_clients() -> None:
    """Drop every cached client. For tests, and for an explicit reconnect."""
    with _LOCK:
        _CLIENTS.clear()
