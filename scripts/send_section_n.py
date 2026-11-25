"""Send the §N draft to Ernest, exactly as written in docs/OUTREACH_DRAFTS.md.

The body is extracted from the draft itself, so what is sent cannot drift from
what is documented. Secrets are read from .env and never printed.

    python send_section_n.py --dry-run   # print what would be sent
    python send_section_n.py --send      # actually send
"""
import os
import re
import smtplib
import sys
from email.message import EmailMessage

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRAFT = os.path.join(REPO, "docs", "OUTREACH_DRAFTS.md")
ENV = os.path.join(REPO, ".env")
TO = "ernest@nolimbsfighting.com"
SECTION = "## N. Ernest"


def load_env(path):
    env = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def extract(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    start = text.index(SECTION)
    end = text.find("\n## ", start + 1)
    chunk = text[start:end if end != -1 else len(text)]

    subj = re.search(r"\*\*Subject:\*\*\s*`([^`]+)`", chunk)
    if not subj:
        raise SystemExit("no **Subject:** line found in the section")
    body = re.search(r"```\n(.*?)\n```", chunk, re.S)
    if not body:
        raise SystemExit("no fenced body found in the section")
    return subj.group(1), body.group(1)


def main():
    subject, body = extract(DRAFT)
    print("to:      %s" % TO)
    print("subject: %s" % subject)
    print("chars:   %d" % len(body))

    # Build the real message even on a dry run, so what is printed in the
    # header dump is what smtplib would put on the wire.
    msg = EmailMessage()
    msg["From"] = "draft@localhost"
    msg["To"] = TO
    msg["Subject"] = subject
    msg.set_content(body, charset="utf-8")

    print("-" * 70)
    print(body)
    print("-" * 70)

    if "--send" not in sys.argv:
        raw = msg.as_bytes().decode("utf-8", "replace")
        print("--- encoded headers as they would go on the wire ---")
        print(raw.split("\n\n", 1)[0])
        print("dry run: nothing sent.")
        return 0

    env = load_env(ENV)
    user = env.get("SMTP_USER", "")
    password = env.get("SMTP_APP_PASSWORD", "")
    if not user or not password:
        raise SystemExit("SMTP_USER / SMTP_APP_PASSWORD missing from .env")

    msg.replace_header("From", user)

    with smtplib.SMTP(env.get("SMTP_HOST") or "smtp.gmail.com",
                      int(env.get("SMTP_PORT") or 587), timeout=45) as s:
        s.starttls()
        s.login(user, password)
        s.send_message(msg)
    print("sent to %s as %s" % (TO, user))
    return 0


if __name__ == "__main__":
    sys.exit(main())
