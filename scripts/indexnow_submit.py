"""Submit our public URLs to IndexNow so Bing, Yandex and Seznam index them now.

Run:
    python scripts/indexnow_submit.py           # dry run: prints the plan only
    python scripts/indexnow_submit.py --send    # actually submits

WHY THIS EXISTS
We are effectively absent from public search, which the owner has named as the
single biggest visibility gap. IndexNow is the one indexing channel that needs
no account, no login and no verification meta tag: it only needs the key file
that app/blueprints/discovery.py already serves at /<key>.txt.

SAFETY
The URL list is read from the LIVE sitemap, so this can never submit a page the
sitemap does not list - and the sitemap is guarded by tests that forbid noindex
pages from appearing in it. Submitting is an outbound, public action, so it is
opt-in and the default is a dry run.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request

SITE = "https://kristo-intelligence-api.onrender.com"
KEY = "2c90228c28c14958f379d6fd487411d3"   # must equal discovery.INDEXNOW_KEY
ENDPOINT = "https://api.indexnow.org/indexnow"
UA = "kristo-indexnow/1.0 (+https://kristo-intelligence-api.onrender.com)"


def fetch(url, timeout=45):
    request = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")[:300]
    except Exception as exc:                                  # noqa: BLE001
        return 0, "%s: %s" % (type(exc).__name__, exc)


def live_urls():
    status, body = fetch(SITE + "/sitemap.xml")
    if status != 200:
        raise SystemExit("sitemap unavailable: HTTP %s %s" % (status, body[:160]))
    urls = [loc.strip() for loc in re.findall(r"<loc>(.*?)</loc>", body)]
    if not urls:
        raise SystemExit("sitemap listed no URLs")
    return urls


def verify_key():
    """The key file must be reachable and byte-exact, or IndexNow rejects us."""
    status, body = fetch("%s/%s.txt" % (SITE, KEY))
    if status != 200:
        raise SystemExit("key file missing: HTTP %s at /%s.txt" % (status, KEY))
    if body.strip() != KEY:
        raise SystemExit("key file content does not match the key: %r" % body[:80])
    print("key file OK: %s/%s.txt" % (SITE, KEY))


def submit(urls):
    host = SITE.split("//", 1)[1].rstrip("/")
    payload = {
        "host": host,
        "key": KEY,
        "keyLocation": "%s/%s.txt" % (SITE, KEY),
        "urlList": urls,
    }
    data = json.dumps(payload).encode()
    request = urllib.request.Request(
        ENDPOINT, data=data, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8",
                 "User-Agent": UA})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")[:400]
    except Exception as exc:                                  # noqa: BLE001
        return 0, "%s: %s" % (type(exc).__name__, exc)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--send", action="store_true",
                       help="actually submit (default is a dry run)")
    args = parser.parse_args(argv)

    verify_key()
    urls = live_urls()
    print("sitemap lists %d URLs:" % len(urls))
    for url in urls:
        print("   ", url)

    if not args.send:
        print()
        print("DRY RUN - nothing sent. Re-run with --send to submit.")
        return 0

    status, body = submit(urls)
    print()
    print("IndexNow responded HTTP %s %s" % (status, body.strip()[:200]))
    # 200/202 = accepted; 403 = key rejected; 422 = URL does not belong to host.
    return 0 if status in (200, 202) else 1


if __name__ == "__main__":
    sys.exit(main())
