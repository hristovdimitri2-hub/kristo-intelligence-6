"""The 402reviews claim file, pinned to the bytes their checker will read.

Their provider docs offer a DNS TXT record at `_api-reviews.<domain>` or a file at
`/.well-known/api-reviews.txt`. This host is a Render subdomain, so the DNS zone is
not ours: the file is the only route we have, and a file that gains a trailing
newline is a different value from the record it replaces.
"""
import io
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
#: Copied as TEXT from their portal, not read from a screenshot. The first version
#: came from an image, used `-` instead of `=`, carried one extra hex character, and
#: did not verify — while their checker kept fetching it and getting 200, which is
#: what proved the path was right and the content was wrong.
TOKEN = "api-reviews-verification=42252f1ca1f725918d80d573"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    import main

    return main.app.test_client()


def test_the_file_carries_exactly_the_token_with_no_trailing_newline():
    raw = io.open(REPO / "api-reviews.txt", "rb").read()

    assert raw.decode("ascii") == TOKEN, "the served value must be the issued one"
    assert raw.endswith(b"3"), "a trailing newline would be a different value"
    assert b"\n" not in raw
    assert b"=" in raw, "the separator is `=`, which a screenshot read as `-`"
    assert len(raw) == 49


def test_the_route_serves_the_committed_bytes_unchanged(client):
    response = client.get("/.well-known/api-reviews.txt")

    assert response.status_code == 200
    assert response.data.decode("ascii") == TOKEN
    assert response.mimetype == "text/plain"


def test_a_missing_file_is_404_rather_than_an_empty_200(client, monkeypatch):
    """An empty 200 makes a verifier's "not verified" look like our bug."""
    import app.blueprints.discovery as discovery

    real_open = open

    def refuse(path, *args, **kwargs):
        if str(path).endswith("api-reviews.txt"):
            raise FileNotFoundError(path)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", refuse)
    response = client.get("/.well-known/api-reviews.txt")

    assert response.status_code == 404
