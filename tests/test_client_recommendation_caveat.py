# -*- coding: utf-8 -*-
"""Nothing we control may send a reader to the npm release without saying so.

kristo-x402-client@1.0.0 is what `npm install kristo-x402-client` gives you today,
and its published README - the one npmjs.com shows and the one agents read - is
wrong in the two ways that cost money and time:

  * it quotes `// { amount: 0.05 ... }` for /api/stats and a Pricing section saying
    "$0.05 USDC (volume discount to $0.01 after 10 paid calls)". The real price is
    0.005, ten times less, and there is no volume discount: the discounted constant
    in the server (0.01) is above every real route price, so it can never trigger.
    A payer following that example sends ten times what was asked, and the server
    accepts it, because it checks `amount >= price`.
  * "How it works" documents only X-Payment-Proof - the legacy rail, twelve
    confirmations, roughly 24 seconds per call. Nothing about PAYMENT-SIGNATURE.

1.1.0 in this repository fixes both and is not published yet. So every surface we
control that names the package must say which version a reader will actually get,
and the README that will become 1.1.0 must not repeat either mistake - publishing it
is the one action that can replace the wrong text, and it must not replace it with
more of the same.
"""
import io
import json
import os

import pytest

CLIENT_DIR = os.path.join("packages", "x402-client")

#: Surfaces that a reader or a scanner can reach, and that name the package.
NAMING_SURFACES = (
    "/",
    "/.well-known/ai-plugin.json",
)

CAVEAT_MARKERS = ("1.1.0", "1.0.0", "not published", "legacy rail")


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


def test_every_surface_naming_the_package_says_which_version(client):
    """The general guard: a new surface cannot quietly recommend 1.0.0.

    Written as a sweep rather than two assertions so that a surface which mentions
    the package later is covered by existing rather than by remembering to add it.
    """
    checked = []
    for path in NAMING_SURFACES:
        body = client.get(path).get_data(as_text=True)
        if "kristo-x402-client" not in body:
            continue
        checked.append(path)
        window = " ".join(body.split())
        assert any(marker in window for marker in CAVEAT_MARKERS), (
            "%s tells a reader to install kristo-x402-client without saying which "
            "version they will get; npm currently serves 1.0.0, which waits ~24s per "
            "call and quotes a price ten times the real one" % path)

    assert checked, (
        "no surface names the package any more - this guard is now checking nothing, "
        "which is not the same as passing")


def test_the_landing_page_names_the_version_a_reader_will_get(client):
    """The footer is the one place a human sees the install line."""
    body = " ".join(client.get("/").get_data(as_text=True).split())

    assert "kristo-x402-client@1.1.0" in body, (
        "the landing page does not pin the version it is recommending")
    assert "1.0.0" in body, (
        "the landing page recommends the package without warning that npm still "
        "serves 1.0.0")
    assert "24" in body and "rail" in body.lower(), (
        "the warning must say what is wrong with 1.0.0, not only that it is old")


def test_the_ai_plugin_manifest_carries_the_version(client):
    """A machine reads this field and installs what it says."""
    doc = client.get("/.well-known/ai-plugin.json").get_json()
    package = doc["x402_payment"]["client_package"]

    assert "1.1.0" in package, (
        "x402_payment.client_package = %r does not name a version, so a machine "
        "reading it installs whatever npm serves" % package)
    assert "1.0.0" in package


# ── the artefact that will be published ──────────────────────────────────────


@pytest.fixture()
def package_readme():
    return io.open(os.path.join(CLIENT_DIR, "README.md"),
                   encoding="utf-8").read()


def test_the_package_readme_does_not_promise_the_old_price(package_readme):
    """Publishing 1.1.0 replaces the wrong text; it must not repeat it."""
    assert "$0.05" not in package_readme, (
        "the README still quotes $0.05; the most expensive route is 0.005")
    assert "amount: 0.05" not in package_readme, (
        "the README still shows a 0.05 challenge example")


def test_the_package_readme_does_not_promise_a_volume_discount(package_readme):
    """The discounted constant is above every real price, so it cannot trigger."""
    lowered = package_readme.lower()
    assert "no volume discount" in lowered, (
        "the README must state plainly that there is no volume discount")
    assert "volume discount to" not in lowered, (
        "the README promises a volume discount that cannot trigger")


def test_the_package_readme_does_not_promise_a_free_call(package_readme):
    """Production runs with a free-tier limit of zero."""
    lowered = package_readme.lower()
    assert "free tier: **none**" in lowered, (
        "the README must say there is no free tier")


def test_the_package_readme_documents_both_rails_and_prefers_the_fast_one(
        package_readme):
    """1.0.0 documented only the slow rail; that is what made it look 24s slow."""
    assert "PAYMENT-SIGNATURE" in package_readme
    assert "X-Payment-Proof" in package_readme
    assert "EIP-3009" in package_readme
    assert package_readme.index("PAYMENT-SIGNATURE") < package_readme.index(
        "X-Payment-Proof"), (
        "the fast rail must be presented first; a reader stops at the first example")


def test_the_package_readme_admits_the_version_is_not_published(package_readme):
    """Otherwise a reader installs the old release and blames the new docs."""
    lowered = package_readme.lower()
    assert "not published yet" in lowered or "not published" in lowered
    assert "1.0.0" in package_readme


def test_the_package_manifest_version_matches_the_docs(package_readme):
    """The README is the release note for whatever package.json says."""
    manifest = json.loads(
        io.open(os.path.join(CLIENT_DIR, "package.json"), encoding="utf-8").read())
    version = manifest["version"]

    assert version == "1.1.0", (
        "package.json says %s but the README describes 1.1.0 as the fixed release"
        % version)
    assert version in package_readme, (
        "the README never names the version package.json is about to publish")
