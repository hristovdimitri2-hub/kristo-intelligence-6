# -*- coding: utf-8 -*-
"""well-known-names (x402 Doctor, 21.10): 6 of 6 resources in
/.well-known/x402 were bare URL strings — directories (XRPL AI Hub …) list
each resource BY name and description, otherwise it shows up as a generic
label. Fix: every resource becomes {"url", "name", "description"}, same
6 URLs, same order, brand "Kristo — …".

Doctor's own hint pins the shape (no guessing):
  Serve the resources as {"url": …, "name": "Short name",
                           "description": "One line on what it returns"}.
"""
import pytest


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    return main.app.test_client()


EXPECTED_PATHS = [
    "/api/stats",
    "/api/sales",
    "/api/bot-status",
    "/api/arb/opportunities",
    "/api/v1/signal",
    "/api/v1/whaleflow",
]


def test_resources_are_named_objects(client):
    r = client.get("/.well-known/x402")
    assert r.status_code == 200
    data = r.get_json()
    resources = data["resources"]
    assert len(resources) == 6, f"expected 6 resources: {resources}"
    for res in resources:
        assert isinstance(res, dict), f"resource must be an object: {res!r}"
        assert set(res) >= {"url", "name", "description"}, res
        assert res["url"].startswith("http"), res["url"]
        # short name + one-line description, both non-empty
        assert 0 < len(res["name"]) <= 60, res["name"]
        assert res["name"].startswith("Kristo"), f"brand missing: {res['name']}"
        assert 0 < len(res["description"]) <= 200, res["description"]


def test_resources_keep_same_urls_and_order(client):
    """Only the wrapping changed — the 6 URLs and their order are frozen.

    The base host comes from request.host_url (test client →
    http://localhost), so compare PATHS and a single shared base."""
    data = client.get("/.well-known/x402").get_json()
    urls = [res["url"] for res in data["resources"]]
    # every url = <same base> + expected path, in the frozen order
    bases = {u[: u.find(p)] for u, p in zip(urls, EXPECTED_PATHS)
             if u.find(p) != -1}
    assert len(bases) == 1, f"resources must share one base: {urls}"
    paths = [u[len(next(iter(bases))):] for u in urls]
    assert paths == EXPECTED_PATHS, paths


def test_trust_file_untouched(client):
    """x402-trust.txt stays a separate, plain-text well-known file with the
    untouched x402-trust-verification=v1: signature payload."""
    r = client.get("/.well-known/x402-trust.txt")
    assert r.status_code == 200
    text = r.get_data(as_text=True)
    assert text.startswith("x402-trust-verification=v1:"), text[:60]