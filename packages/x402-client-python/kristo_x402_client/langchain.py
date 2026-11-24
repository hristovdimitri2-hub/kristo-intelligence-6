# -*- coding: utf-8 -*-
"""LangChain tool factory for the Kristo Intelligence x402 API.

Optional: the core client has no dependencies. This module imports LangChain
only when you call :func:`make_langchain_tools`, so importing
``kristo_x402_client`` never requires LangChain to be installed.

    from kristo_x402_client import KristoX402Client
    from kristo_x402_client.langchain import make_langchain_tools

    client = KristoX402Client(pay=my_signer)
    tools = make_langchain_tools(client)   # ready for an agent
"""

from __future__ import annotations

#: The routes this package knows how to expose as tools, with the description
#: an agent needs in order to choose correctly. Prices are in USDC per call and
#: are read from the live 402 challenge, not from this table — the table exists
#: so the agent can see the cost before it decides.
TOOLS = {
    "get_trading_signal": {
        "path": "/api/v1/signal",
        "price_usdc": 0.01,
        "description": (
            "Live DeFi trading signal for an AI agent: direction, confidence, "
            "entry/exit levels and the reason. Read-only; no parameters. "
            "Authoritative for the current signal. Price is per call."),
    },
    "get_whale_flow": {
        "path": "/api/v1/whaleflow",
        "price_usdc": 0.01,
        "description": (
            "Recent large-wallet USDC transfers on Base with sender, "
            "recipient and amount. Read-only; no parameters. Authoritative "
            "for whale activity."),
    },
    "get_arbitrage_opportunities": {
        "path": "/api/arb/opportunities",
        "price_usdc": 0.005,
        "description": (
            "Cross-DEX arbitrage opportunities on Base with the pair, the two "
            "venues, and the spread. Read-only; no parameters. Authoritative "
            "for the current scan."),
    },
    "get_market_stats": {
        "path": "/api/stats",
        "price_usdc": 0.005,
        "description": (
            "Aggregate market statistics: volume, TVL and activity. Read-only; "
            "no parameters. Authoritative for market data."),
    },
    "get_onchain_sales": {
        "path": "/api/sales",
        "price_usdc": 0.005,
        "description": (
            "This service's own on-chain sales, read from the chain. Read-only; "
            "no parameters. Authoritative for provable revenue."),
    },
    "get_bot_status": {
        "path": "/api/bot-status",
        "price_usdc": 0.005,
        "description": (
            "This service's health, heartbeat and wallet state. Read-only; no "
            "parameters. Authoritative for whether the service is alive."),
    },
    "verify_seller_receiver": {
        "path": "/api/v1/verify-seller",
        "price_usdc": 0.05,
        "description": (
            "Check a seller's receiver address before paying it: whether the "
            "address is known, what it has received, and any risk signals. "
            "Takes a wallet address. Use before a large payment to an "
            "unfamiliar counterparty."),
    },
}


def make_langchain_tools(client, names=None):
    """Return LangChain ``StructuredTool`` objects bound to ``client``.

    :param client: a :class:`kristo_x402_client.KristoX402Client`.
    :param names: optional subset of :data:`TOOLS` keys to expose. Defaults to
        all of them.
    :returns: a list of tools ready to pass to an agent.

    Each tool's ``_run`` returns the JSON body as a string, which is what a
    LangChain agent expects. Payment happens inside the client, so the agent
    never sees the 402 handshake.
    """
    from langchain_core.tools import StructuredTool  # imported lazily

    selected = names or list(TOOLS)
    tools = []
    for name in selected:
        spec = TOOLS[name]
        tools.append(StructuredTool.from_function(
            func=_make_runner(client, spec["path"]),
            name=name,
            description="%s Price: $%s USDC per call, paid automatically."
                        % (spec["description"], spec["price_usdc"]),
        ))
    return tools


def _make_runner(client, path):
    def _run(**kwargs):
        result = client.get(path)
        if not result.get("ok"):
            return "error: %s" % (result.get("error")
                                  or result.get("message")
                                  or "request failed with status %s"
                                  % result.get("status"))
        import json
        return json.dumps(result.get("data"), ensure_ascii=False)
    return _run


def make_openai_tool(client, name):
    """Return an OpenAI-style function tool definition for one route.

    Returns ``{"type": "function", "function": {...}}`` plus a callable under
    ``"call"`` so the caller can dispatch ``tool_call`` results without writing
    the plumbing. The ``parameters`` schema is empty: every route is read-only
    and takes no arguments.
    """
    spec = TOOLS[name]
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "%s Price: $%s USDC per call, paid automatically."
                           % (spec["description"], spec["price_usdc"]),
            "parameters": {"type": "object", "properties": {},
                           "additionalProperties": False},
        },
        "call": _make_runner(client, spec["path"]),
    }
