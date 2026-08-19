from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def test_source_does_not_contain_known_credential_formats():
    files = [
        ROOT / "services" / "telegram_sales.py",
        ROOT / "PRODUCTION_DEPLOYMENT_REPORT.md",
        ROOT / "render_deploy.py",
        ROOT / "render_env_sync.py",
        ROOT / "render_status_check.py",
    ]
    credential_patterns = [
        re.compile(r"8882001607:[A-Za-z0-9_-]{20,}"),
        re.compile(r"sk_(?:live|test)_[A-Za-z0-9]{20,}"),
        re.compile(r"pk_(?:live|test)_[A-Za-z0-9]{20,}"),
        re.compile(r"whsec_[A-Za-z0-9]{20,}"),
        re.compile(r"rnd_[A-Za-z0-9]{20,}"),
    ]

    for path in files:
        content = path.read_text(encoding="utf-8")
        assert not any(pattern.search(content) for pattern in credential_patterns), path


def test_telegram_token_requires_environment_secret(monkeypatch):
    from services.telegram_sales import _get_token

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert _get_token() == ""