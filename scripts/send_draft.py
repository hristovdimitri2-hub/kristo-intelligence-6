"""Send a draft from docs/OUTREACH_DRAFTS.md, exactly as written there.

The body is extracted from the draft itself, so what is sent cannot drift from
what is documented. The recipient is never hardcoded: it is passed on the
command line, so an address chosen at send time is visible at send time.
Secrets are read from .env and never printed.

    python send_draft.py --section N --to someone@example.com            # dry run
    python send_draft.py --section N --to someone@example.com --send

A section is named by its letter. `--section O` matches the heading
`## O. ...` and takes everything up to the next `## ` heading. `--cc` may be
given more than once, which is how a person's address and the published
company inbox are both reached without choosing between them.
"""
import argparse
import os
import re
import smtplib
import sys
from email.message import EmailMessage

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRAFT = os.path.join(REPO, "docs", "OUTREACH_DRAFTS.md")
ENV = os.path.join(REPO, ".env")


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


def extract(path, section):
    """Return (subject, body) for the named draft section."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read()

    heading = re.search(r"^## %s\." % re.escape(section), text, re.M)
    if not heading:
        raise SystemExit("no heading '## %s.' in %s" % (section, path))
    start = heading.start()
    following = text.find("\n## ", start + 1)
    chunk = text[start:following if following != -1 else len(text)]

    subj = re.search(r"\*\*Subject:\*\*\s*`([^`]+)`", chunk)
    if not subj:
        raise SystemExit("no **Subject:** line in section %s" % section)
    body = re.search(r"```\n(.*?)\n```", chunk, re.S)
    if not body:
        raise SystemExit("no fenced body in section %s" % section)
    return subj.group(1), body.group(1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--section", required=True,
                    help="draft letter as it appears in '## <letter>.'")
    ap.add_argument("--to", required=True, help="recipient address")
    ap.add_argument("--cc", action="append", default=[],
                    help="carbon copy; may be repeated")
    ap.add_argument("--send", action="store_true", help="actually send")
    args = ap.parse_args()

    subject, body = extract(DRAFT, args.section)
    print("to:      %s" % args.to)
    if args.cc:
        print("cc:      %s" % ", ".join(args.cc))
    print("subject: %s" % subject)
    print("chars:   %d" % len(body))

    # Build the real message even on a dry run, so what is printed in the
    # header dump is what smtplib would put on the wire.
    msg = EmailMessage()
    msg["From"] = "draft@localhost"
    msg["To"] = args.to
    if args.cc:
        msg["Cc"] = ", ".join(args.cc)
    msg["Subject"] = subject
    msg.set_content(body, charset="utf-8")

    print("-" * 70)
    print(body)
    print("-" * 70)

    if not args.send:
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
    print("sent to %s as %s" % (", ".join([args.to] + args.cc), user))
    return 0


if __name__ == "__main__":
    sys.exit(main())
