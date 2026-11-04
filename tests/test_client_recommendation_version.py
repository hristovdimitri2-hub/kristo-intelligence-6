# -*- coding: utf-8 -*-
"""No surface we control may carry a version claim that has expired.

The history of this file is the point of it. It used to be called
test_client_recommendation_caveat.py and it *required* a warning on every surface
that named the package, because npm served kristo-x402-client@1.0.0 and that
release was wrong in the two ways that cost money and time:

  * its published README - the one npmjs.com shows and the one agents read - quoted
    `// { amount: 0.05 ... }` for /api/stats and a Pricing section promising a
    volume discount. The real price is 0.005, ten times less, and there is no
    discount: the discounted constant in the server (0.01) is above every real
    route price, so it can never trigger. The server accepts `amount >= price`, so
    a payer following that example sent ten times what was asked.
  * it documented only X-Payment-Proof, the legacy rail: twelve confirmations,
    roughly 24 seconds a call.

1.1.0 fixed both and was published on 2026-11-04. The moment it was, every one of
those warnings became false - they told readers to install from the repository
because the registry was stale, when the registry was current. A guard that keeps
demanding a warning after the warning has expired is not cautious, it is wrong.

So the guard is inverted, and it is deliberately symmetric: a surface may not claim
the package is unpublished, and may not name the superseded 1.0.0. Both are the
same defect - a claim with an expiry date that nobody came back to remove - and
this file is the thing that comes back.
"""
import io
import json
import os
import re

import pytest

CLIENT_DIR = os.path.join("packages", "x402-client")

#: Surfaces a reader or a scanner can reach, and that name the package.
NAMING_SURFACES = (
    "/",
    "/.well-known/ai-plugin.json",
)

#: Text that was true before 1.1.0 was published and is false now.
EXPIRED_MARKERS = ("1.0.0", "not published")


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


def test_no_surface_carries_an_expired_version_claim(client):
    """The general guard: a surface cannot keep warning about a fixed release.

    A sweep rather than two assertions, so that a surface which starts naming the
    package later is covered by existing rather than by remembering to add it.
    """
    checked = []
    for path in NAMING_SURFACES:
        body = client.get(path).get_data(as_text=True)
        if "kristo-x402-client" not in body:
            continue
        checked.append(path)
        window = " ".join(body.split())
        for marker in EXPIRED_MARKERS:
            assert marker not in window, (
                "%s still says %r. 1.1.0 was published, so that claim has expired - "
                "it now sends readers away from a registry that serves the fixed "
                "release" % (path, marker))

    assert checked, (
        "no surface names the package any more - this guard is now checking nothing, "
        "which is not the same as passing")


def test_the_landing_page_sends_readers_to_the_registry(client):
    """The footer is the one place a human sees the install line."""
    body = " ".join(client.get("/").get_data(as_text=True).split())

    assert "kristo-x402-client" in body, (
        "the landing page no longer tells anyone how to install the client")
    assert "npmjs.com/package/kristo-x402-client" in body, (
        "the landing page should point at the registry entry, which is now the "
        "fixed release, rather than at the source tree")


def test_the_ai_plugin_manifest_names_the_package_without_pinning_an_old_one(client):
    """A machine reads this field and installs what it says."""
    package = client.get("/.well-known/ai-plugin.json").get_json()[
        "x402_payment"]["client_package"]

    assert package == "kristo-x402-client", (
        "x402_payment.client_package = %r. It should name the package and stop "
        "there: a version in a manifest is a claim with an expiry date, and this "
        "one has already expired twice" % package)


# ── the artefact that gets published ─────────────────────────────────────────


@pytest.fixture()
def package_readme():
    return io.open(os.path.join(CLIENT_DIR, "README.md"),
                   encoding="utf-8").read()


def test_the_package_readme_does_not_promise_the_old_price(package_readme):
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
    assert "free tier: **none**" in package_readme.lower(), (
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


def test_the_package_readme_does_not_still_say_it_is_unpublished(package_readme):
    """The note that told readers to wait. It was true, and now it is not.

    The README in the repository is the release note for the next version, and the
    README on npmjs.com is what agents read. Both said 1.1.0 was "not published
    yet" - the repository one because it was written before the publish, the
    registry one because publishing copies the file. Removing it is the reason
    1.1.1 exists at all.
    """
    lowered = package_readme.lower()
    assert "not published" not in lowered, (
        "the README still tells readers the current release is unpublished, which "
        "sends them to the source tree for no reason")
    assert "1.1.0 or later" in lowered or "1.1.1" in package_readme, (
        "the README should say which release a reader gets")


def test_the_package_manifest_version_honours_the_floor_the_readme_claims(
        package_readme):
    """The README claims a minimum release; the manifest must not be below it.

    This started as `version in package_readme`, which failed the moment the README
    said "1.1.0 or later" and package.json said 1.1.1. The test was wrong and the
    README was right: a README that names the exact patch goes stale on every
    patch, which is the defect this whole file exists to catch. The honest
    invariant is the other way round - the README states the oldest release that
    has the fast rail, and the release being published must be at least that.
    """
    manifest = json.loads(
        io.open(os.path.join(CLIENT_DIR, "package.json"), encoding="utf-8").read())
    version = manifest["version"]

    assert re.match(r"^\d+\.\d+\.\d+$", version), (
        "package.json version %r is not a published-form semver" % version)
    assert manifest["repository"]["url"].startswith("git+"), (
        "npm normalises repository.url to git+https://... on publish and warns "
        "when it has to; write the normalised form here instead")

    claimed = re.search(r"(\d+\.\d+\.\d+) or later", package_readme)
    assert claimed, (
        "the README no longer states which release a reader gets; saying only "
        "'install this' leaves a reader pinned to an old copy unable to tell")
    floor = tuple(int(part) for part in claimed.group(1).split("."))
    current = tuple(int(part) for part in version.split("."))
    assert current >= floor, (
        "the README promises %s or later but package.json publishes %s, so the "
        "release would ship below its own documented floor"
        % (claimed.group(1), version))
