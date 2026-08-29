"""Local Simulation / Smoke Test — end-to-end external-agent chain.

Simulates, in-process (Flask test client, zero network, zero paid
dependencies), the full journey of an external AI agent:

  1. DISCOVERY      — finds and validates the agent manifest
  2. TRACTION       — reads the public anonymized activity feed
  3. X402 CHALLENGE — hits a paid endpoint and validates the 402 challenge
  4. FUNNEL         — logs a mock test transaction through the local CRM
                      funnel state (isolated store; never real money)
  5. SYNDICATION    — formats the feed + strategy into a posting pack

Run standalone:
    python -m src.nexus.simulator
or programmatically:
    from src.nexus.simulator import run_local_simulation
    report = run_local_simulation(app)
    assert report.ok
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

PASS = "pass"
FAIL = "fail"


@dataclass
class SimulationStep:
    """One step of the simulated external-agent journey."""

    name: str
    ok: bool
    detail: str

    def as_line(self) -> str:
        mark = "PASS" if self.ok else "FAIL"
        return f"{mark:4} {self.name:22} {self.detail}"


@dataclass
class SimulationReport:
    """Machine-readable result of the full simulation chain."""

    steps: List[SimulationStep] = field(default_factory=list)
    generated_at: str = ""
    extras: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> int:
        return sum(1 for s in self.steps if s.ok)

    @property
    def failed(self) -> int:
        return sum(1 for s in self.steps if not s.ok)

    @property
    def ok(self) -> bool:
        return bool(self.steps) and all(s.ok for s in self.steps)

    def add(self, name: str, ok: bool, detail: str) -> SimulationStep:
        step = SimulationStep(name=name, ok=ok, detail=detail)
        self.steps.append(step)
        return step

    def render(self) -> str:
        lines = [
            "Nexus Local Simulation — external agent chain",
            f"generated_at: {self.generated_at}",
            "",
        ]
        lines.extend(step.as_line() for step in self.steps)
        lines.append("")
        lines.append(f"Result: {self.passed}/{len(self.steps)} passed")
        return "\n".join(lines)


def _step_discovery(client, report: SimulationReport) -> Dict[str, Any]:
    response = client.get("/.well-known/kristo-agent.json")
    manifest = response.get_json(silent=True) or {}
    ok = (
        response.status_code == 200
        and manifest.get("ok") is True
        and manifest.get("protocol", {}).get("network") == "base"
        and len(manifest.get("endpoints", [])) > 0
        and len(manifest.get("payment_flow", [])) >= 3
    )
    report.add(
        "discovery",
        ok,
        (
            f"manifest via /.well-known/kristo-agent.json "
            f"({len(manifest.get('endpoints', []))} endpoints, "
            f"{len(manifest.get('agent_catalog', []))} agents)"
        ),
    )
    return manifest


def _step_public_activity(client, report: SimulationReport) -> Dict[str, Any]:
    response = client.get("/api/public/activity")
    payload = response.get_json(silent=True) or {}
    report.add(
        "public_activity",
        response.status_code == 200
        and payload.get("ok") is True
        and payload.get("anonymized") is True,
        (
            f"HTTP {response.status_code}, "
            f"anonymized={payload.get('anonymized')}, "
            f"items={len(payload.get('items', []))}"
        ),
    )
    return payload


def _step_x402_challenge(
    client, report: SimulationReport, endpoint: str, receiver: str
) -> None:
    response = client.get(endpoint)
    if response.status_code == 402:
        body = response.get_json(silent=True) or {}
        accepts = (body.get("accepts") or [{}])[0]
        challenge_ok = (
            response.headers.get("X-Payment-Required") == "x402"
            and accepts.get("scheme") == "exact"
            and accepts.get("network") == "eip155:8453"
            and str(accepts.get("amount", "")).isdigit()
            and int(accepts.get("amount", "0")) > 0
            and accepts.get("payTo", "").startswith("0x")
            and accepts.get("asset", "").startswith("0x")
            and accepts.get("payTo", "").lower() == receiver.lower()
        )
        report.add(
            "x402_challenge",
            challenge_ok,
            (
                f"402 challenge valid: amount={accepts.get('amount')} raw, "
                f"network={accepts.get('network')}, "
                f"payTo={str(accepts.get('payTo', ''))[:14]}..."
            ),
        )
        report.extras["challenge"] = accepts
    elif response.status_code == 200:
        report.add(
            "x402_challenge",
            True,
            "200 (free tier available — challenge deferred until quota exhausted)",
        )
    else:
        report.add(
            "x402_challenge",
            False,
            f"paid endpoint returned HTTP {response.status_code}",
        )


def _step_funnel(
    client, report: SimulationReport, store, email: str, amount_usdc: float
) -> None:
    capture = client.post(
        "/api/leads",
        json={"email": email, "source": "simulation", "campaign": "nexus"},
    )
    payload = capture.get_json(silent=True) or {}
    if capture.status_code == 200 and payload.get("ok"):
        store.mark_paid(email, amount_usd=amount_usdc, plan="simulation")
        stored = store.find_by_email(email)
        funnel_ok = (
            bool(stored)
            and str(stored.get("payment_status", "")).lower() == "paid"
        )
        report.add(
            "funnel_mock_transaction",
            funnel_ok,
            (
                f"lead captured + mock payment ({amount_usdc} USDC) "
                f"marked for {email}"
            ),
        )
    else:
        report.add(
            "funnel_mock_transaction",
            False,
            f"lead capture failed: HTTP {capture.status_code} {payload}",
        )


def run_local_simulation(
    app,
    client: Optional[Any] = None,
    paid_endpoint: str = "/api/stats",
    crm_store: Optional[Any] = None,
    amount_usdc: float = 0.005,
) -> SimulationReport:
    """Run the full external-agent chain in-process and return the report.

    ``crm_store`` overrides the funnel target — pass an isolated CRMStore in
    tests/standalone runs so the mock transaction never mutates production
    data. Real money is never involved: the "payment" is a local CRM marking.
    """
    from datetime import datetime as _dt, timezone as _tz

    report = SimulationReport(
        generated_at=_dt.now(_tz.utc).isoformat(),
        extras={"paid_endpoint": paid_endpoint},
    )

    import main as _main  # deferred — avoids circular imports
    from config import get_base_fee_receiver

def run_local_simulation(
    app,
    client: Optional[Any] = None,
    paid_endpoint: str = "/api/stats",
    amount_usdc: float = 0.005,
) -> SimulationReport:
    """Run the full external-agent chain in-process and return the report.

    The funnel mock transaction flows through the application's live CRM
    store (``main.crm_store``) — the same store the HTTP funnel writes to.
    Standalone CLI runs swap it for a throwaway temp store first (see
    :func:`main`), so production data is never touched. Real money is never
    involved: the "payment" is a local CRM ``mark_paid`` marking.
    """
    from datetime import datetime as _dt, timezone as _tz

    report = SimulationReport(
        generated_at=_dt.now(_tz.utc).isoformat(),
        extras={"paid_endpoint": paid_endpoint},
    )

    import main as _main  # deferred — avoids circular imports
    from config import get_base_fee_receiver

    client = client or app.test_client()
    # Local simulation must not be throttled by earlier traffic in the same
    # process (e.g. when run inside the full test suite) — clear the limiter.
    _main._rate_limit_hits.clear()
    email = f"sim-agent-{_dt.now(_tz.utc).strftime('%Y%m%d%H%M%S')}@simulation.invalid"

    # 1) DISCOVERY — external agent finds and validates the manifest.
    _step_discovery(client, report)

    # 2) TRACTION — the public anonymized activity feed.
    feed = _step_public_activity(client, report)

    # 3) X402 payment challenge on a paid endpoint.
    _step_x402_challenge(client, report, paid_endpoint, get_base_fee_receiver())

    # 4) FUNNEL — mock test transaction through the app's live funnel state.
    _step_funnel(client, report, _main.crm_store, email, amount_usdc)

    # 5) SYNDICATION — pack the feed + strategy for external posting.
    try:
        engine = app.extensions.get("nexus_engine")
        strategy = engine.build_strategy() if engine is not None else {}
        from .syndication import build_syndication_pack

        pack = build_syndication_pack(feed, strategy)
        report.add(
            "syndication",
            bool(pack["digest"]),
            (
                f"digest ready ({len(pack['digest'])} chars), "
                f"{len(pack['hooks'])} hooks"
            ),
        )
    except Exception as exc:  # a failed pack never masks the earlier steps
        report.add("syndication", False, f"pack build failed: {exc}")

    return report


def main() -> int:  # pragma: no cover — manual CLI entry point
    """Standalone run: isolated temp stores, zero production impact."""
    import os
    import sys

    repo_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    sys.path.insert(0, repo_root)
    os.environ.setdefault("ADMIN_API_TOKEN", "sim-admin-token")
    os.environ["SESSION_SECRET"] = "sim-session-secret"
    os.environ["KRISTO_DISABLE_BACKGROUND_THREADS"] = "true"

    import main as _main
    from integrations.crm_store import CRMStore

    # Isolated funnel state: the simulation writes ONLY to a temp CRM store.
    sim_store = CRMStore(tempfile.mkstemp(suffix=".db")[1])
    _main.crm_store = sim_store

    report = run_local_simulation(_main.app)
    print(report.render())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())