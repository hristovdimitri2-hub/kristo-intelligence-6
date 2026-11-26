# -*- coding: utf-8 -*-
"""The SealKeeper claim file must be served EXACTLY, byte for byte.

SealKeeper's SEAL version 9 records a verified owner's proof as
`{"url", "sha256"}` — the URL it re-reads every day and the SHA-256 of the token
it finds there. That makes one whitespace character the difference between a
verified domain and a silent "not verified", and a trailing newline is the
default behaviour of most editors, `echo`, and `WriteAllText` on Windows.

These tests pin the two things that can drift: the body must equal the file, and
the file must have no trailing newline when it exists.
"""
import hashlib
import io
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLAIM = os.path.join(REPO, "sealkeeper-claim.txt")


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    return main.app.test_client()


def test_the_route_answers_and_never_invents_a_token(client):
    """200 with the file, 404 without it — never an empty 200."""
    r = client.get("/.well-known/sealkeeper.txt")
    if os.path.exists(CLAIM):
        assert r.status_code == 200, r.status_code
        assert r.get_data() == io.open(CLAIM, "rb").read(), (
            "the served body differs from the committed file — a verifier "
            "hashes what we serve, not what we committed")
    else:
        assert r.status_code == 404, (
            "no claim file is committed, so the route must say 404 rather than "
            "answer 200 with nothing")


def test_the_claim_file_has_no_trailing_newline():
    """The whole reason this file exists as a test.

    `sha256(token)` is what SealKeeper compares. If the file ends with `\\n`,
    the hash is of `token + "\\n"` and the claim stops verifying — with no error
    anywhere, because the fetch succeeds.
    """
    if not os.path.exists(CLAIM):
        pytest.skip("no claim token issued yet")
    raw = io.open(CLAIM, "rb").read()
    assert raw, "the claim file is empty"
    assert not raw.endswith(b"\n"), (
        "sealkeeper-claim.txt ends with a newline; the SHA-256 SealKeeper "
        "compares is of the token alone. Rewrite it without the trailing byte.")
    assert raw.strip() == raw, (
        "the claim file has leading or trailing whitespace")
    assert b" " not in raw, "a token with a space in it is almost certainly two"
    print("claim file: %d bytes, sha256 %s"
          % (len(raw), hashlib.sha256(raw).hexdigest()))
