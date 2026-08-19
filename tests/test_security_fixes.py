import json
import re
import subprocess
from pathlib import Path

import pytest


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    import main
    from integrations.crm_store import CRMStore

    monkeypatch.setattr(main, "crm_store", CRMStore(tmp_path / "crm.db"))
    main._free_tier_usage.clear()
    return main.app.test_client()


def test_admin_routes_require_token(client):
    assert client.get("/api/admin/leads").status_code == 401
    assert client.get("/sales/admin").status_code == 401
    assert client.get("/api/sales/summary").status_code == 401


def test_admin_routes_accept_server_token(client):
    response = client.get(
        "/api/admin/leads",
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert response.status_code == 200
    assert response.get_json()["ok"] is True


def test_stripe_webhook_requires_signature(client):
    response = client.post(
        "/api/webhooks/stripe",
        data=json.dumps({"type": "checkout.session.completed"}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "missing_signature"


def test_referer_cannot_bypass_x402(client, monkeypatch):
    import main

    monkeypatch.setitem(main._free_tier_usage, "127.0.0.1", 1)
    response = client.get(
        "/api/stats",
        headers={"Referer": "http://localhost:5000/dashboard"},
    )
    assert response.status_code == 402


def test_telegram_token_requires_runtime_secret(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    from services.telegram_sales import _get_token

    assert _get_token() == ""


def test_tracked_files_do_not_contain_credentials():
    """Prevent real Stripe, Telegram, and Render credentials from being committed."""
    repo_root = Path(__file__).resolve().parents[1]
    tracked_files = subprocess.check_output(
        ["git", "ls-files", "-z"],
        cwd=repo_root,
    ).split(b"\0")
    secret_patterns = (
        re.compile(rb"sk_(?:test|live)_[A-Za-z0-9]{20,}"),
        re.compile(rb"pk_(?:test|live)_[A-Za-z0-9]{20,}"),
        re.compile(rb"whsec_[A-Za-z0-9]{20,}"),
        re.compile(rb"\b[0-9]{8,}:AA[A-Za-z0-9_-]{20,}\b"),
        re.compile(rb"rnd_[A-Za-z0-9]{20,}"),
    )

    exposed = []
    for raw_path in tracked_files:
        if not raw_path:
            continue
        path = repo_root / raw_path.decode("utf-8")
        try:
            content = path.read_bytes()
        except (OSError, UnicodeDecodeError):
            continue
        if any(pattern.search(content) for pattern in secret_patterns):
            exposed.append(path.relative_to(repo_root).as_posix())

    assert exposed == []


def test_documentation_does_not_contain_secret_shaped_placeholders():
    """Keep documentation from teaching users to paste credential-shaped values."""
    repo_root = Path(__file__).resolve().parents[1]
    tracked_files = subprocess.check_output(
        ["git", "ls-files", "-z"],
        cwd=repo_root,
    ).split(b"\0")
    documentation_patterns = (
        re.compile(rb"\b(?:sk|pk)_(?:test|live)_[A-Za-z0-9._-]+"),
        re.compile(rb"\bwhsec_[A-Za-z0-9._-]+"),
        re.compile(rb"\b[0-9]{8,}:AA[A-Za-z0-9_-]+"),
        re.compile(rb"\brnd_[A-Za-z0-9._-]+"),
        re.compile(rb"\bTELEGRAM_BOT_TOKEN\s*=\s*[0-9]+:[A-Za-z0-9_-]+"),
    )
    documentation_suffixes = {".md", ".txt"}

    exposed = []
    for raw_path in tracked_files:
        if not raw_path:
            continue
        path = repo_root / raw_path.decode("utf-8")
        if path.suffix.lower() not in documentation_suffixes:
            continue
        try:
            content = path.read_bytes()
        except OSError:
            continue
        if any(pattern.search(content) for pattern in documentation_patterns):
            exposed.append(path.relative_to(repo_root).as_posix())

    assert exposed == []


def test_reachable_git_history_does_not_contain_credentials():
    """Prevent credentials from remaining reachable through historical refs."""
    repo_root = Path(__file__).resolve().parents[1]
    revisions = subprocess.check_output(
        ["git", "rev-list", "--all"],
        cwd=repo_root,
        text=True,
    ).splitlines()
    credential_pattern = (
        r"sk_(test|live)_[A-Za-z0-9]{20,}|"
        r"pk_(test|live)_[A-Za-z0-9]{20,}|"
        r"whsec_[A-Za-z0-9]{20,}|"
        r"[0-9]{8,}:AA[A-Za-z0-9_-]{20,}|"
        r"rnd_[A-Za-z0-9]{20,}"
    )

    exposed_revisions = []
    for revision in revisions:
        result = subprocess.run(
            ["git", "grep", "-I", "-l", "-E", credential_pattern, revision],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode in (0, 1), result.stderr
        if result.returncode == 0:
            exposed_revisions.append(revision)

    assert exposed_revisions == []


def test_unreachable_git_objects_do_not_contain_credentials():
    """Ensure the local object store has no recoverable credentials."""
    repo_root = Path(__file__).resolve().parents[1]
    fsck_output = subprocess.check_output(
        ["git", "fsck", "--no-reflogs", "--unreachable", "--no-progress"],
        cwd=repo_root,
        text=True,
    )
    object_ids = [
        line.rsplit(maxsplit=1)[-1]
        for line in fsck_output.splitlines()
        if line.startswith("unreachable ")
    ]
    secret_patterns = (
        re.compile(rb"sk_(?:test|live)_[A-Za-z0-9]{20,}"),
        re.compile(rb"pk_(?:test|live)_[A-Za-z0-9]{20,}"),
        re.compile(rb"whsec_[A-Za-z0-9]{20,}"),
        re.compile(rb"\b[0-9]{8,}:AA[A-Za-z0-9_-]{20,}\b"),
        re.compile(rb"rnd_[A-Za-z0-9]{20,}"),
    )

    exposed_objects = []
    for object_id in object_ids:
        content = subprocess.check_output(
            ["git", "cat-file", "-p", object_id],
            cwd=repo_root,
        )
        if any(pattern.search(content) for pattern in secret_patterns):
            exposed_objects.append(object_id)

    assert exposed_objects == []