"""Audit #6 BREAK 3: DeFiLlama trend notifications were ALWAYS rejected by
Telegram — legacy parse_mode:'Markdown' pairs `_*`[ across the WHOLE message,
and the branch literals 'defi_protocol' (1 '_') + 'high_tvl_protocol' (2 '_')
= 3 unpaired underscores -> 400 "can't parse entities" on every send.

These tests run REAL trends through the REAL JS builder
(`mdEsc` + `buildTrendApprovalText`, exported by market_evaluator.js) and
lint the result under Telegram's documented legacy-Markdown rules
(backslash escapes honored; Telegram's own parser is closed source).
"""
from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess

import pytest
import requests

REPO = pathlib.Path(__file__).resolve().parents[1]
EVALUATOR = REPO / "lib" / "agents" / "market_evaluator.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(
    NODE is None, reason="node is required to run the REAL JS builder")

# The 10 DeFiLlama titles audit #6 captured LIVE and saw REJECTED (23.09).
AUDIT6_REJECTED_LIVE = [
    "Binance CEX (Multi-Chain)", "OKX (Multi-Chain)", "Lido (Multi-Chain)",
    "Bitfinex (Multi-Chain)", "Aave V3 (Multi-Chain)", "Bybit (Multi-Chain)",
    "Robinhood (Multi-Chain)", "SSV Network (Ethereum)",
    "Morpho Blue (Multi-Chain)", "Binance staked ETH (Multi-Chain)",
]


def _legacy_markdown_ok(text: str):
    """Telegram legacy-Markdown pairing rules, escapes honored."""
    stripped = re.sub(r"\\(.)", "\x00", text)   # \X -> placeholder, not a toggle
    for ch in ("*", "_", "`"):
        if stripped.count(ch) % 2:
            return False, f"unpaired {ch!r} x{stripped.count(ch)}"
    if stripped.count("[") != stripped.count("]"):
        return False, "unpaired [ ]"
    return True, ""


def _build_via_real_js(trend: dict) -> str:
    """Run the exported builder from market_evaluator.js (their code = ours)."""
    script = (
        "const {buildTrendApprovalText}=require(process.argv[1]);"
        "process.stdout.write(buildTrendApprovalText("
        "JSON.parse(process.argv[2])));"
    )
    r = subprocess.run(
        [NODE, "-e", script, str(EVALUATOR),
         json.dumps(trend, ensure_ascii=False)],
        capture_output=True, text=True, encoding="utf-8",
        timeout=30, cwd=str(REPO))
    assert r.returncode == 0, f"node failed: {r.stderr[:400]}"
    return r.stdout


def _defillama_trend(name: str, chain: str, tvl: float) -> dict:
    """Mirror the EXACT field values scanDeFiLlamaProtocols builds."""
    return {
        "id": "dl_" + name.lower().replace(" ", "_"),
        "title": f"{name} ({chain})",
        "category": "defi_protocol",
        "source": "DeFiLlama",
        "demandScore": min(100, round((tvl / 1e9) * 10 + 30)),
        "type": "high_tvl_protocol",
        "description": f"DeFi протокол {name} на {chain} "
                       f"с TVL ${tvl / 1e6:.1f}M.",
        "suggestedService":
            "x402-defi-monitor-" + name.lower().replace(" ", "-"),
    }


def test_md_esc_escapes_every_legacy_toggle():
    script = ("const {mdEsc}=require(process.argv[1]);"
              "process.stdout.write(mdEsc(process.argv[2]));")
    r = subprocess.run([NODE, "-e", script, str(EVALUATOR),
                        "defi_protocol *x* `y` [z]"],
                       capture_output=True, text=True, encoding="utf-8",
                       timeout=30, cwd=str(REPO))
    assert r.returncode == 0, r.stderr
    # mdEsc escapes toggles * _ ` [ — a bare ']' never opens an entity.
    assert r.stdout == "defi\\_protocol \\*x\\* \\`y\\` \\[z]"


def test_the_10_audit6_rejected_titles_now_parse():
    """The 10 LIVE titles that audit #6 proved Telegram rejected: 0 rejected."""
    rejected = []
    for title in AUDIT6_REJECTED_LIVE:
        name, rest = title.rsplit(" (", 1)
        chain = rest.rstrip(")")
        trend = _defillama_trend(name, chain, tvl=1e9)
        text = _build_via_real_js(trend)
        ok, why = _legacy_markdown_ok(text)
        if not ok:
            rejected.append((title, why))
    assert not rejected, f"still rejected: {rejected}"
    # sanity: the OLD (pre-fix) text really would have failed the same lint
    raw_unesc = json.dumps(_defillama_trend("Lido", "Multi-Chain", 1e9))
    old_text = (f"*Категория:* defi_protocol\n*Тип:* high_tvl_protocol\n"
                f"*Име:* {json.loads(raw_unesc)['title']}")
    assert not _legacy_markdown_ok(old_text)[0], \
        "control: the un-escaped literals must still fail the lint"


def test_live_defillama_top10_zero_rejected():
    """10 LIVE probes — real current DeFiLlama top protocols through the real
    builder: 0 rejected (network failures skip, never fake a pass)."""
    try:
        resp = requests.get("https://api.llama.fi/protocols", timeout=30)
        resp.raise_for_status()
        protos = resp.json()
    except Exception as exc:                     # offline CI must stay green
        pytest.skip(f"live DeFiLlama unreachable: {exc}")

    picked = [p for p in protos if p.get("tvl") and p["tvl"] > 1_000_000]
    picked = sorted(picked, key=lambda p: -p["tvl"])[:10]
    assert len(picked) == 10, f"expected 10 live probes, got {len(picked)}"

    rejected = []
    for p in picked:
        trend = _defillama_trend(p["name"], p.get("chain") or "multi-chain",
                                 float(p["tvl"]))
        text = _build_via_real_js(trend)
        ok, why = _legacy_markdown_ok(text)
        if not ok:
            rejected.append((p["name"], why))
    assert not rejected, f"live probes rejected: {rejected}"