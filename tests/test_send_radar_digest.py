"""RADAR-DIGEST имейл достава — форматиране и CLI поведение БЕЗ реален SMTP.

Покрива: subject с датата, Markdown→HTML конверсията, multipart съобщението,
env резолвирането (паролата се чете САМО от околната среда), dry-run
(никакъв SMTP конектор) и --send пътят през фалшив smtplib.SMTP (никаква мрежа).
"""

from datetime import date
from pathlib import Path
import re
import smtplib

from scripts import send_radar_digest as srd

SAMPLE_MD = """# Заглавие

**Важно:** виж [сайта](https://example.com/x) и `код`.

1. Първи ред
2. Втори ред

- пункт

---
Край <script>alert(1)</script>
"""


def test_subject_uses_iso_date_of_the_day():
    assert srd.build_subject(date(2026, 10, 13)) == (
        "Kristo Intelligence — RADAR-DIGEST [2026-10-13]"
    )
    # По подразбиране = днешна дата (форматът е фиксиран).
    today = srd.build_subject()
    assert today.startswith("Kristo Intelligence — RADAR-DIGEST [")
    assert today.endswith("]")


def test_markdown_to_html_blocks_and_inline():
    html = srd.markdown_to_html(SAMPLE_MD)
    assert "<h1>Заглавие</h1>" in html
    assert "<strong>Важно:</strong>" in html
    assert "<code>код</code>" in html
    assert '<a href="https://example.com/x">сайта</a>' in html
    assert "<ol>" in html and "<ul>" in html
    assert html.count("<li>") == 3
    assert "<hr>" in html
    assert "<p>" in html


def test_markdown_to_html_escapes_raw_html():
    html = srd.markdown_to_html(SAMPLE_MD)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_bare_url_is_linkified_and_trailing_dot_trimmed():
    html = srd.markdown_to_html("Виж https://example.com/a. После")
    assert '<a href="https://example.com/a">https://example.com/a</a>' in html
    assert "a.</a>" not in html


def test_render_html_document_wraps_full_page():
    doc = srd.render_html_document(SAMPLE_MD)
    assert doc.startswith("<!DOCTYPE html>")
    assert 'charset="utf-8"' in doc
    assert "<h1>Заглавие</h1>" in doc
    assert doc.rstrip().endswith("</html>")


def test_build_message_is_multipart_with_plain_and_html():
    subject = srd.build_subject(date(2026, 10, 13))
    msg = srd.build_message(
        SAMPLE_MD, "sender@test.local", "rcpt@test.local", subject
    )
    assert str(msg["From"]) == "sender@test.local"
    assert str(msg["To"]) == "rcpt@test.local"
    assert str(msg["Subject"]) == subject
    plain = msg.get_body(preferencelist=("plain",))
    html_part = msg.get_body(preferencelist=("html",))
    assert plain is not None and html_part is not None
    # Plain частта = изходният Markdown (fallback), HTML = конверсията.
    assert plain.get_content().strip() == SAMPLE_MD.strip()
    assert "<h1>Заглавие</h1>" in html_part.get_content()


def test_resolve_config_full_env():
    cfg = srd.resolve_config(
        {
            "SMTP_HOST": "smtp.test",
            "SMTP_PORT": "2525",
            "SMTP_USER": "sender@test.local",
            "SMTP_APP_PASSWORD": "unit-test-app-pass",
            "MAIL_RECIPIENT": "rcpt@test.local",
        }
    )
    assert cfg.host == "smtp.test"
    assert cfg.port == 2525
    assert cfg.user == "sender@test.local"
    assert cfg.app_password == "unit-test-app-pass"
    assert cfg.recipient == "rcpt@test.local"
    assert cfg.missing_for_send == []


def test_resolve_config_defaults_and_missing_keys():
    cfg = srd.resolve_config({})
    # Gmail defaults са безопасни (не са секретове).
    assert cfg.host == srd.DEFAULT_SMTP_HOST == "smtp.gmail.com"
    assert cfg.port == srd.DEFAULT_SMTP_PORT == 587
    assert cfg.app_password == ""
    assert cfg.missing_for_send == [
        "SMTP_USER",
        "SMTP_APP_PASSWORD",
        "MAIL_RECIPIENT",
    ]


def test_resolve_config_rejects_non_numeric_port():
    import pytest

    with pytest.raises(ValueError, match="SMTP_PORT"):
        srd.resolve_config({"SMTP_PORT": "abc"})


def test_password_is_read_only_from_environment():
    """Паролата НИКОГА не е hardcode — чете се само от env mapping."""
    src = Path(srd.__file__).read_text(encoding="utf-8")
    assert not re.search(
        r"SMTP_APP_PASSWORD\s*=\s*['\"][^'\"]+['\"]", src
    ), "намерена hardcode стойност на SMTP_APP_PASSWORD"
    assert re.search(r"env\.get\(\s*['\"]SMTP_APP_PASSWORD['\"]", src)


class _FakeSMTP:
    """Falshiv SMTP — записва какво би се случило; никаква мрежа."""

    instances: list = []

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.tls = False
        self.logged = None
        self.sent = None
        _FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self):
        self.tls = True

    def login(self, user, password):
        self.logged = (user, password)

    def send_message(self, msg):
        self.sent = msg


def _set_env(monkeypatch, password: str = ""):
    """Детерминирана среда; password="" блокира внезапен injection от .env."""
    monkeypatch.setenv("SMTP_HOST", "smtp.test")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USER", "sender@test.local")
    monkeypatch.setenv("MAIL_RECIPIENT", "rcpt@test.local")
    monkeypatch.setenv("SMTP_APP_PASSWORD", password)


def _write_digest(tmp_path, text: str) -> Path:
    digest = tmp_path / "RADAR-DIGEST.md"
    digest.write_text(text, encoding="utf-8")
    return digest


def test_cli_dry_run_prints_plan_and_never_opens_smtp(tmp_path, monkeypatch, capsys):
    body = "\n".join(f"ред {i}" for i in range(1, 31))
    digest = _write_digest(tmp_path, body)
    _set_env(monkeypatch, password="")

    def _boom(*args, **kwargs):
        raise AssertionError("SMTP не бива да се отваря в dry-run")

    monkeypatch.setattr(smtplib, "SMTP", _boom)

    rc = srd.main(["--digest", str(digest)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "DRY-RUN" in out
    assert "От (From):   sender@test.local" in out
    assert "До (To):     rcpt@test.local" in out
    assert "Kristo Intelligence — RADAR-DIGEST [" in out
    assert "smtp.test:587" in out
    assert "НЕ е зададена" in out
    assert "text/plain" in out and "text/html" in out
    # Прегледът е точно първите 20 реда.
    assert "ред 20" in out and "ред 21" not in out


def test_cli_send_without_password_fails_before_smtp(tmp_path, monkeypatch, capsys):
    digest = _write_digest(tmp_path, "# т")
    _set_env(monkeypatch, password="")  # dotenv не може да я презапише (override=False)

    def _boom(*args, **kwargs):
        raise AssertionError("SMTP не бива да се отваря без парола")

    monkeypatch.setattr(smtplib, "SMTP", _boom)

    rc = srd.main(["--digest", str(digest), "--send"])
    captured = capsys.readouterr()

    assert rc == 1
    assert "SMTP_APP_PASSWORD" in captured.err


def test_cli_send_uses_starttls_login_and_send(tmp_path, monkeypatch, capsys):
    digest = _write_digest(tmp_path, "# т")
    _set_env(monkeypatch, password="unit-test-app-pass")
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)

    rc = srd.main(["--digest", str(digest), "--send"])
    out = capsys.readouterr().out

    assert rc == 0
    assert out.startswith("OK:")
    inst = _FakeSMTP.instances[-1]
    assert (inst.host, inst.port) == ("smtp.test", 587)
    assert inst.tls is True
    assert inst.logged == ("sender@test.local", "unit-test-app-pass")
    assert str(inst.sent["To"]) == "rcpt@test.local"
    assert str(inst.sent["Subject"]).startswith(
        "Kristo Intelligence — RADAR-DIGEST ["
    )

