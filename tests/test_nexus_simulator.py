"""Regression tests for the Local Simulation / Smoke Test layer.

Covers:
  * run_local_simulation() executes the full external-agent chain in-process
    (discovery -> activity -> x402 challenge -> funnel -> syndication)
  * the funnel mock transaction lands in the isolated CRM store as PAID,
    with a non-routable .invalid email by construction
  * the x402 challenge step validates the canonical 402 contract when the
    free tier is disabled
  * report semantics (passed/ok/render)
"""

import pytest


@pytest.fixture()
def sim_env(monkeypatch, tmp_path):
    """Isolated app + durable stores, with the Nexus engine force-mounted."""
    monkeypatch.setenv("ADMIN_API_TOKEN", "sim-admin-token")
    monkeypatch.setenv("SESSION_SECRET", "sim-session-secret")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    import main
    from integrations.catalog_store import create_catalog_store
    from integrations.crm_store import CRMStore
    from integrations.research_store import ResearchInsightStore
    from src.nexus import mount_nexus_engine

    monkeypatch.setattr(
        main, "catalog_store", create_catalog_store(tmp_path / "catalog.db")
    )
    crm = CRMStore(tmp_path / "crm.db")
    monkeypatch.setattr(main, "crm_store", crm)
    monkeypatch.setattr(
        main, "research_store", ResearchInsightStore(tmp_path / "research.db")
    )

    mount_nexus_engine(main.app, force_rebuild=True)

    yield main, main.app.test_client(), crm

    main._request_log.clear()
    main._sales_history.clear()


def test_full_simulation_chain_passes(sim_env):
    main, client, crm = sim_env
    from src.nexus.simulator import run_local_simulation

    report = run_local_simulation(main.app, client=client)
    assert report.ok, [s.detail for s in report.steps if not s.ok]
    assert report.failed == 0
    step_names = [s.name for s in report.steps]
    assert step_names == [
        "discovery",
        "public_activity",
        "x402_challenge",
        "funnel_mock_transaction",
        "syndication",
    ]


def test_simulation_funnel_marks_mock_payment(sim_env):
    main, client, crm = sim_env
    from src.nexus.simulator import run_local_simulation

    report = run_local_simulation(main.app, client=client)
    assert report.ok

    sim_leads = [
        lead
        for lead in crm.get_all()
        if str(lead.get("email", "")).endswith("@simulation.invalid")
    ]
    sim_leads = [
        lead
        for lead in crm.get_all()
        if str(lead.get("email", "")).endswith("@simulation.invalid")
    ]
    assert len(sim_leads) == 1
    assert str(sim_leads[0]["payment_status"]).lower() == "paid"
    assert sim_leads[0]["plan"] == "simulation"


def test_x402_challenge_validated_when_free_tier_disabled(sim_env, monkeypatch):
    main, client, crm = sim_env
    from src.nexus.simulator import run_local_simulation

    monkeypatch.setenv("KRISTO_FREE_TIER_LIMIT", "0")
    report = run_local_simulation(main.app, client=client)
    assert report.ok

    challenge = report.extras.get("challenge")
    assert challenge is not None, "expected the 402 challenge path to be exercised"
    assert challenge["network"] == "eip155:8453"
    assert challenge["scheme"] == "exact"
    assert int(challenge["amount"]) > 0
    assert challenge["payTo"].startswith("0x")

    challenge_step = next(s for s in report.steps if s.name == "x402_challenge")
    assert challenge_step.ok
    assert "402 challenge valid" in challenge_step.detail


def test_report_render_and_counts(sim_env):
    main, client, crm = sim_env
    from src.nexus.simulator import run_local_simulation

    report = run_local_simulation(main.app, client=client)
    rendered = report.render()
    assert f"Result: {report.passed}/{len(report.steps)} passed" in rendered
    assert rendered.count("PASS") == len(report.steps)
    assert "discovery" in rendered and "funnel_mock_transaction" in rendered


def test_simulation_records_activity_in_request_log(sim_env):
    main, client, crm = sim_env
    from src.nexus.simulator import run_local_simulation

    main._request_log.clear()
    report = run_local_simulation(main.app, client=client)
    assert report.ok
    # The x402 challenge step flows through the app's real request accounting:
    # either a free-tier data unlock (200) is logged, or the 402 challenge is
    # served from the paywall without consuming upstream provider quota.
    challenge_step = next(s for s in report.steps if s.name == "x402_challenge")
    assert challenge_step.ok
    log_keys = {entry["endpoint"] for entry in main._request_log}
    assert log_keys or report.extras.get("challenge")
