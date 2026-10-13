"""RADAR-DIGEST → Gmail SMTP достава (Kristo Intelligence).

Чете RADAR-DIGEST.md (workspace файл), конвертира го в прост HTML
(plain-text частта = изходният Markdown) и изпраща multipart/alternative
през Gmail SMTP с STARTTLS.

Изпълнение:
    python scripts/send_radar_digest.py            # DRY-RUN (по подразбиране)
    python scripts/send_radar_digest.py --send     # реално изпращане (ДВОЙНА ВРАТА)

Env променливи (само околната среда / локален .env в .gitignore — паролата
НИКОГА не се пише в код, чат или репо):
    SMTP_HOST          по подразбиране smtp.gmail.com
    SMTP_PORT          по подразбиране 587 (STARTTLS)
    SMTP_USER          задължителен за изпращане — пълният Gmail адрес (login)
    SMTP_APP_PASSWORD  задължителен за --send — Gmail App Password
    MAIL_RECIPIENT     задължителен за изпращане — получател на дайджеста

Double-door: реалното изпращане (--send) изисква изрично "Да" от Богдан +
"Да" от асистента. Без --send скриптът само отпечатва плана и не докосва
мрежата (никакъв SMTP конектор).
"""

from __future__ import annotations

import argparse
import html
import os
import re
import smtplib
import sys
from dataclasses import dataclass
from datetime import date
from email import policy
from email.message import EmailMessage
from pathlib import Path

# Workspace дайджест — извън репото; през --digest може да се подмени.
DEFAULT_DIGEST_PATH = Path(
    r"C:\Users\AlienWare\.cline\data\workspaces\chat\RADAR-DIGEST.md"
)

# Всички env ключове на модула (паролата се чете САМО оттук).
ENV_KEYS = (
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USER",
    "SMTP_APP_PASSWORD",
    "MAIL_RECIPIENT",
)

DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 587


@dataclass(frozen=True)
class Config:
    """SMTP конфигурация, резолвната изцяло от околната среда."""

    host: str
    port: int
    user: str
    app_password: str
    recipient: str

    @property
    def missing_for_send(self) -> list[str]:
        """Env ключовете без стойност, задължителни за --send."""
        missing = []
        if not self.user:
            missing.append("SMTP_USER")
        if not self.app_password:
            missing.append("SMTP_APP_PASSWORD")
        if not self.recipient:
            missing.append("MAIL_RECIPIENT")
        return missing


def resolve_config(env: dict | None = None) -> Config:
    """Събира SMTP конфигурацията от околната среда (никакви hardcode стойности)."""
    if env is None:
        env = os.environ
    raw_port = (env.get("SMTP_PORT") or "").strip() or str(DEFAULT_SMTP_PORT)
    try:
        port = int(raw_port)
    except ValueError as exc:  # ясна грешка вместо traceback по-късно
        raise ValueError(f"SMTP_PORT не е число: {raw_port!r}") from exc
    return Config(
        host=(env.get("SMTP_HOST") or "").strip() or DEFAULT_SMTP_HOST,
        port=port,
        user=(env.get("SMTP_USER") or "").strip(),
        app_password=env.get("SMTP_APP_PASSWORD") or "",
        recipient=(env.get("MAIL_RECIPIENT") or "").strip(),
    )


def build_subject(today: date | None = None) -> str:
    """Subject: 'Kristo Intelligence — RADAR-DIGEST [дата на днешния ден]'."""
    day = today or date.today()
    return f"Kristo Intelligence — RADAR-DIGEST [{day.isoformat()}]"


def load_digest(path: Path | str) -> str:
    """Чете дайджеста; utf-8-sig толерира евентуален BOM."""
    return Path(path).read_text(encoding="utf-8-sig")


# ── Markdown → HTML (проста, line-based конверсия; без външни зависимости) ──

_MD_HEADING = re.compile(r"^(#{1,4})\s+(.+)$")
_MD_HR = re.compile(r"^\s*---\s*$")
_MD_OL = re.compile(r"^\d+\.\s+(.+)$")
_MD_UL = re.compile(r"^[-*]\s+(.+)$")
_MD_CODE = re.compile(r"`([^`]+)`")
_MD_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_MD_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_MD_BARE_URL = re.compile(r"https?://[^\s<]+")


def _trim_url(url: str) -> str:
    """Маха завършваща пунктуация/небалансирани скоби от linkify-нат URL."""
    while url and url[-1] in ".,;:!?…":
        url = url[:-1]
    while url.endswith(")") and url.count(")") > url.count("("):
        url = url[:-1]
    for suffix in ("&quot;", "&#x27;"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    return url


def _inline(text: str) -> str:
    """Екраниране + inline маркери: code, bold, [текст](url), голи URL-и."""
    out = html.escape(text, quote=True)
    out = _MD_CODE.sub(r"<code>\1</code>", out)
    out = _MD_BOLD.sub(r"<strong>\1</strong>", out)
    # Първо изваждаме markdown линковете с placeholder, за да не бъде
    # linkify-нат голият URL вътре в вече генерирания <a href="…">.
    placeholders: list[str] = []

    def _stash(m: re.Match) -> str:
        placeholders.append(f'<a href="{m.group(2)}">{m.group(1)}</a>')
        return f"\x00{len(placeholders) - 1}\x00"

    out = _MD_LINK.sub(_stash, out)

    def _linkify(m: re.Match) -> str:
        url = _trim_url(m.group(0))
        if not url:
            return m.group(0)
        return f'<a href="{url}">{url}</a>'

    out = _MD_BARE_URL.sub(_linkify, out)
    for i, fragment in enumerate(placeholders):
        out = out.replace(f"\x00{i}\x00", fragment)
    return out


def markdown_to_html(md: str) -> str:
    """Line-based Markdown → HTML фрагмент (заглавия, списъци, параграфи, hr)."""
    out: list[str] = []
    open_list: str | None = None
    in_para = False

    def close_list() -> None:
        nonlocal open_list
        if open_list:
            out.append(f"</{open_list}>")
            open_list = None

    def close_para() -> None:
        nonlocal in_para
        if in_para:
            out.append("</p>")
            in_para = False

    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            close_para()
            close_list()
            continue
        if _MD_HR.match(line):
            close_para()
            close_list()
            out.append("<hr>")
            continue
        m = _MD_HEADING.match(line)
        if m:
            close_para()
            close_list()
            level = len(m.group(1))
            body = _inline(m.group(2).strip())
            out.append(f"<h{level}>{body}</h{level}>")
            continue
        m = _MD_OL.match(line)
        if m:
            close_para()
            if open_list != "ol":
                close_list()
                out.append("<ol>")
                open_list = "ol"
            out.append(f"<li>{_inline(m.group(1))}</li>")
            continue
        m = _MD_UL.match(line)
        if m:
            close_para()
            if open_list != "ul":
                close_list()
                out.append("<ul>")
                open_list = "ul"
            out.append(f"<li>{_inline(m.group(1))}</li>")
            continue
        close_list()
        if not in_para:
            out.append("<p>")
            in_para = True
        out.append(_inline(line))

    close_para()
    close_list()
    return "\n".join(out)


def render_html_document(md: str) -> str:
    """Пълен HTML документ (simple styling, utf-8) около конверсията."""
    body = markdown_to_html(md)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="bg">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<title>Kristo Intelligence — RADAR-DIGEST</title>\n"
        "<style>\n"
        "body{font-family:Segoe UI,Arial,sans-serif;max-width:820px;"
        "margin:24px auto;padding:0 16px;color:#1a1a1a;line-height:1.5}\n"
        "h1,h2{border-bottom:1px solid #e0e0e0;padding-bottom:4px}\n"
        "code{background:#f2f2f2;padding:1px 4px;border-radius:3px}\n"
        "a{color:#0b57d0}\n"
        "hr{border:none;border-top:1px solid #e0e0e0;margin:20px 0}\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        "</body>\n"
        "</html>\n"
    )


def build_message(
    md: str, sender: str, recipient: str, subject: str
) -> EmailMessage:
    """multipart/alternative: text/plain = изходният Markdown, text/html = конверсията."""
    msg = EmailMessage(policy=policy.SMTP)
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject
    msg.set_content(md)
    msg.add_alternative(render_html_document(md), subtype="html")
    return msg


def _stdout_safe(text: str) -> str:
    """Печат без UnicodeEncodeError при cp1251 (и всякаква) конзола.

    Заменя само символите, недопустими в кодовата страница на stdout, с '?'.
    Прилага се САМО към CLI отпечатъците — текстовете на писмото (UTF-8)
    не минават оттук.
    """
    enc = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        return text.encode(enc, errors="replace").decode(enc)
    except (LookupError, UnicodeDecodeError):
        return text


def format_dry_run(
    md: str, msg: EmailMessage, cfg: Config, preview_lines: int = 20
) -> str:
    """Отпечатва плана БЕЗ изпращане: от→до, subject, размери, преглед."""
    plain = msg.get_body(preferencelist=("plain",))
    html_part = msg.get_body(preferencelist=("html",))
    plain_size = len(plain.get_content().encode("utf-8")) if plain else 0
    html_size = len(html_part.get_content().encode("utf-8")) if html_part else 0
    pwd_state = "зададена" if cfg.app_password else "НЕ е зададена"
    lines = md.splitlines()[:preview_lines]
    shown = len(lines)
    preview = "\n".join(lines) if lines else "(празен файл)"
    return "\n".join(
        [
            "=== DRY-RUN (нищо не се изпраща) ===",
            f"От (From):   {msg['From']}",
            f"До (To):     {msg['To']}",
            f"Subject:     {msg['Subject']}",
            f"Сървър:      {cfg.host}:{cfg.port} (STARTTLS)",
            "SMTP_APP_PASSWORD: "
            + pwd_state
            + " (само присъствие — стойността не се показва)",
            f"Тяло:        multipart/alternative · text/plain {plain_size} B"
            f" · text/html {html_size} B",
            f"--- Първите {shown} реда от plain тялото (Markdown) ---",
            preview,
            "--- край на прегледа ---",
        ]
    )


def send_message(msg: EmailMessage, cfg: Config) -> None:
    """РЕАЛНО изпращане — извиква се само при --send (двойна врата)."""
    with smtplib.SMTP(cfg.host, cfg.port, timeout=30) as server:
        server.starttls()
        server.login(cfg.user, cfg.app_password)
        server.send_message(msg)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="RADAR-DIGEST → Gmail SMTP (по подразбиране: dry-run)."
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="реално изпращане (изисква двойна врата: Богдан + асистент)",
    )
    parser.add_argument(
        "--digest",
        default=str(DEFAULT_DIGEST_PATH),
        help="път до RADAR-DIGEST.md",
    )
    args = parser.parse_args(argv)

    # .env се зарежда само при CLI изпълнение (никога при импорт в тестовете).
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    except ImportError:
        pass

    try:
        cfg = resolve_config()
    except ValueError as exc:
        print(_stdout_safe(f"ГРЕШКА: {exc}"), file=sys.stderr)
        return 2

    try:
        md = load_digest(args.digest)
    except OSError as exc:
        print(
            _stdout_safe(f"ГРЕШКА: не мога да прочета дайджеста: {exc}"),
            file=sys.stderr,
        )
        return 2

    subject = build_subject()
    msg = build_message(md, cfg.user, cfg.recipient, subject)

    if not args.send:
        print(_stdout_safe(format_dry_run(md, msg, cfg)))
        return 0

    missing = cfg.missing_for_send
    if missing:
        print(
            _stdout_safe(
                "ГРЕШКА: липсват env променливи за изпращане: "
                + ", ".join(missing)
                + " (попълни ги в локалния .env — никога в код/репо)"
            ),
            file=sys.stderr,
        )
        return 1

    send_message(msg, cfg)
    print(_stdout_safe(f"OK: изпратено {cfg.user} -> {cfg.recipient} · {subject}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


