"""
Dual-rail CDP facilitator selection (config only, double-gated 11.10).

FACILITATOR_CDP_API_KEY_ID / FACILITATOR_CDP_API_KEY_SECRET are an opt-in
switch: BOTH present → the defaults portion of the facilitator chain prefers
the CDP facilitator; anything less (every current deployment) keeps the chain
and every byte of the default behavior exactly as today. X402_FACILITATOR_URL
keeps absolute priority. No network: chain building, the readiness gate and
the JWT admission checks are all local.
"""
import pytest

NEW_ID = "FACILITATOR_CDP_API_KEY_ID"
NEW_SECRET = "FACILITATOR_CDP_API_KEY_SECRET"
_ALL_RELEVANT = (
    NEW_ID, NEW_SECRET,
    "CDP_API_KEY_ID", "CDP_API_KEY_SECRET",
    "X402_FACILITATOR_API_KEY_ID", "X402_FACILITATOR_API_KEY_SECRET",
    "X402_FACILITATOR_URL",
)
PAYAI = ("payai", "https://facilitator.payai.network")
CDP = ("cdp", "https://api.cdp.coinbase.com/platform/v2/x402")


@pytest.fixture()
def clean_env(monkeypatch):
    for name in _ALL_RELEVANT:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_default_chain_is_byte_identical(clean_env):
    """No new keys → the chain is EXACTLY today's: payai first, cdp last."""
    from services.connectors import _facilitator_chain, _cdp_rail_ready
    assert _cdp_rail_ready() is False
    assert _facilitator_chain() == [PAYAI, CDP]


def test_legacy_env_override_keeps_absolute_priority(clean_env):
    """X402_FACILITATOR_URL still wins and keeps its historical position."""
    from services.connectors import _facilitator_chain
    clean_env.setenv("X402_FACILITATOR_URL", "https://legacy.example/")
    assert _facilitator_chain() == [
        ("env", "https://legacy.example"), PAYAI, CDP]


def test_partial_cdp_pair_never_activates(clean_env):
    """One half of the pair (either half) must NOT flip the selection."""
    from services.connectors import _facilitator_chain, _cdp_rail_ready
    clean_env.setenv(NEW_ID, "id-only")
    assert _cdp_rail_ready() is False
    assert _facilitator_chain() == [PAYAI, CDP]
    clean_env.delenv(NEW_ID)
    clean_env.setenv(NEW_SECRET, "secret-only")
    assert _cdp_rail_ready() is False
    assert _facilitator_chain() == [PAYAI, CDP]


def test_full_pair_prefers_cdp_but_keeps_payai_fallback(clean_env):
    """Both keys → CDP is the selection; PayAI stays reachable behind it."""
    from services.connectors import _facilitator_chain, _cdp_rail_ready
    clean_env.setenv(NEW_ID, "id")
    clean_env.setenv(NEW_SECRET, "secret")
    assert _cdp_rail_ready() is True
    chain = _facilitator_chain()
    assert chain == [CDP, PAYAI]


def test_full_pair_with_env_override_envs_first(clean_env):
    from services.connectors import _facilitator_chain
    clean_env.setenv(NEW_ID, "id")
    clean_env.setenv(NEW_SECRET, "secret")
    clean_env.setenv("X402_FACILITATOR_URL", "https://explicit.example")
    assert _facilitator_chain() == [
        ("env", "https://explicit.example"), CDP, PAYAI]


def test_cdp_jwt_reads_the_new_env_names(clean_env):
    """Admission must see the new pair FIRST — no legacy names involved."""
    from services.connectors import _cdp_jwt
    clean_env.setenv(NEW_ID, "organizations/x/apiKeys/y")
    clean_env.setenv(NEW_SECRET, "not-a-pem-but-present")
    token, detail = _cdp_jwt("api.cdp.coinbase.com")
    assert token is None
    assert "missing env" not in detail, (
        "new env names were not read: %r" % detail)


def test_missing_env_surface_unchanged(clean_env):
    """Default (nothing set) keeps today's failure surface verbatim."""
    from services.connectors import _cdp_jwt
    token, detail = _cdp_jwt("api.cdp.coinbase.com")
    assert token is None and "missing env" in detail


def test_eip3009_detail_default_unchanged(clean_env):
    """Dashboard health string keeps 'keys missing' when unconfigured."""
    from services.connectors import _eip3009_detail
    detail = _eip3009_detail()
    assert "keys missing" in detail


def test_eip3009_detail_picks_up_new_pair(clean_env):
    """With the new pair set the health check stops saying 'keys missing'."""
    from services.connectors import _eip3009_detail
    clean_env.setenv(NEW_ID, "organizations/x/apiKeys/y")
    clean_env.setenv(NEW_SECRET, "not-a-pem-but-present")
    detail = _eip3009_detail()
    assert "keys missing" not in detail
    assert "JWT" in detail
