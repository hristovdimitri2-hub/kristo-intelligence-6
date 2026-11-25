# -*- coding: utf-8 -*-
"""How stale, and how true, is the x402 discovery layer's own data?

THE QUESTION. Every x402 catalogue is a promise to agents: "these endpoints sell
this, for this price". Yesterday's finding on our own row was that a CDP Bazaar
row is a snapshot of the last settled echo, so a row can keep advertising text
and a price the seller has since changed. If that is one seller's bad luck it is
an anecdote. If it is a property of the layer, it is the first measured statement
about the reliability of x402 discovery itself, and every buyer of agent
infrastructure needs it.

TWO MEASUREMENTS, one free and one bounded:

  1. THE AGE OF THE CATALOGUE (no third-party calls at all): page the public
     listing and read `lastUpdated` for every row. This alone says whether the
     layer is a live index or a museum.

  2. LIVE CONFORMANCE (bounded outbound sample): re-ask a random sample of rows
     what they sell, right now, with an unpaid request, and compare the live 402
     challenge against what the catalogue stored. Classifies each row as
     confirmed, price drift, description drift, free (advertised paid, answers
     without payment), dead (no longer sells), or unreachable.

Politeness: one request per target, small concurrency, a delay between them, a
short timeout, and a User-Agent that says who is asking. Nothing is paid for and
nothing is written to any third party.

A CORRECTION THIS SCRIPT CARRIES, because it is the reason to trust the numbers.
The first version probed every row with GET and counted HTTP 405 as a dead
listing, reporting 21.5% unreachable. 84 of the 200 sampled rows declare POST, and
a GET to a POST endpoint correctly answers 405 — the defect was in the probe. Each
row is now called with the method its own `extensions.bazaar.info.input.method`
declares, which moves the failure rate to 5.0%. The write-up in
`docs/DISCOVERY_TRUTH.md` publishes both numbers.

    python scripts/catalogue_truth_study.py --pages 50 --sample 200
    python scripts/catalogue_truth_study.py --pages 50 --sample 0    # age only
"""
import argparse
import base64
import json
import os
import random
import re
import statistics
import sys
import tempfile
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

LISTING = "https://api.cdp.coinbase.com/platform/v2/x402/discovery/resources"
UA = "kristo-intelligence-research/1.0 (+https://github.com/hristovdimitri2-hub)"
#: Where the raw result lands. Kept out of the repository by default: it carries
#: third-party URLs and prices, which belong in the write-up, not in the history.
OUT = Path(os.getenv("CATALOGUE_TRUTH_OUT")
           or (Path(tempfile.gettempdir()) / "catalogue_truth.json"))


def get_json(url, timeout=60):
    req = urllib.request.Request(url, headers={"Accept": "application/json",
                                               "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def page_rows(limit=200, offset=0):
    doc = get_json("%s?limit=%d&offset=%d" % (LISTING, limit, offset))
    return doc.get("items") or [], (doc.get("pagination") or {})


def resource_url(row):
    res = row.get("resource")
    if isinstance(res, dict):
        return res.get("url") or ""
    return res or ""


def declared_method(row):
    """The method the row's own bazaar declaration says to use.

    This exists because the first version of this study probed EVERY row with a
    GET and then counted HTTP 405 as a dead listing. A row that declares POST and
    answers 405 to a GET is not a broken listing — it is a broken probe, and the
    difference decides whether the headline number is 1 in 5 or 1 in 10.
    """
    ext = row.get("extensions") or {}
    info = (((ext.get("bazaar") or {}).get("info") or {}).get("input") or {})
    method = (info.get("method") or row.get("method") or "GET")
    method = str(method).upper()
    return method if method in ("GET", "POST", "PUT", "DELETE", "PATCH") else "GET"


def catalogue_view(row):
    acc = (row.get("accepts") or [{}])[0]
    return {
        "url": resource_url(row),
        "amount": str(acc.get("amount") or ""),
        "payTo": acc.get("payTo") or "",
        "description": row.get("description") or "",
        "lastUpdated": row.get("lastUpdated") or "",
        "type": row.get("type") or "",
        "method": declared_method(row),
    }


def decode_challenge(payload, headers):
    """Return (amount, description, source) from whichever form the seller uses."""
    if isinstance(payload, dict):
        acc = (payload.get("accepts") or [{}])[0]
        res = payload.get("resource")
        desc = payload.get("description") or ""
        if isinstance(res, dict):
            desc = res.get("description") or desc
        amount = acc.get("amount")
        if amount:
            return str(amount), desc, "body"
    for key, value in (headers or {}).items():
        if key.lower() in ("payment-required", "x-payment-required") and value:
            try:
                blob = base64.b64decode(value + "=" * (-len(value) % 4))
                doc = json.loads(blob)
            except Exception:                                  # noqa: BLE001
                continue
            acc = (doc.get("accepts") or [{}])[0]
            res = doc.get("resource")
            desc = doc.get("description") or ""
            if isinstance(res, dict):
                desc = res.get("description") or desc
            return str(acc.get("amount") or ""), desc, "header"
    return "", "", "none"


def probe(target, method="GET"):
    """Ask one endpoint what it sells, without paying for it.

    Uses the method the listing itself declares, so a 405 is the listing's fault
    rather than the probe's.
    """
    data = b"{}" if method in ("POST", "PUT", "PATCH") else None
    headers = {"Accept": "application/json", "User-Agent": UA}
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(target, headers=headers, data=data,
                                 method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read(65536).decode("utf-8", "replace")
            headers = dict(resp.headers)
            status = resp.status
    except urllib.error.HTTPError as exc:
        status = exc.code
        headers = dict(getattr(exc, "headers", {}) or {})
        try:
            body = exc.read(65536).decode("utf-8", "replace")
        except Exception:                                      # noqa: BLE001
            body = ""
    except Exception as exc:                                   # noqa: BLE001
        return {"status": 0, "error": type(exc).__name__}

    payload = None
    if body.strip().startswith("{"):
        try:
            payload = json.loads(body)
        except Exception:                                      # noqa: BLE001
            payload = None
    amount, desc, source = decode_challenge(payload, headers)
    return {"status": status, "amount": amount, "description": desc,
            "source": source, "body": body[:400]}


def normalise(text):
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", type=int, default=50, help="pages of 200 to read")
    ap.add_argument("--sample", type=int, default=200, help="live probes")
    ap.add_argument("--concurrency", type=int, default=4)
    args = ap.parse_args()

    rows, seen, total = [], 0, 0
    for page in range(args.pages):
        items, pagination = page_rows(200, page * 200)
        total = pagination.get("total") or total
        if not items:
            break
        rows.extend(catalogue_view(r) for r in items)
        seen += len(items)
    print("read %d rows of a %s-row listing" % (len(rows), total))

    now = datetime.now(timezone.utc)
    ages = []
    for row in rows:
        stamp = row["lastUpdated"]
        if not stamp:
            continue
        try:
            when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            continue
        ages.append((now - when).total_seconds() / 86400.0)

    print("\n=== THE AGE OF THE CATALOGUE (no third-party calls) ===")
    if ages:
        ages.sort()
        buckets = [(0, 1), (1, 3), (3, 7), (7, 14), (14, 30), (30, 90), (90, 10**6)]
        print("rows with a timestamp: %d" % len(ages))
        print("median age: %.2f days | mean: %.2f | newest: %.3f | oldest: %.1f"
              % (statistics.median(ages), statistics.mean(ages), ages[0], ages[-1]))
        for low, high in buckets:
            count = sum(1 for a in ages if low <= a < high)
            label = ("%dd+" % low if high > 10**5 else ("%d-%dd" % (low, high)))
            print("   %-9s %6d  %5.1f%%" % (label, count, 100.0 * count / len(ages)))

    if not args.sample:
        OUT.write_text(json.dumps({"rows_read": len(rows), "ages_days": ages[:5000]},
                                  indent=1), encoding="utf-8")
        return 0

    random.seed(20261125)
    targets = [r for r in rows if r["url"].startswith("http")]
    random.shuffle(targets)
    targets = targets[:args.sample]

    print("\n=== LIVE CONFORMANCE (%d endpoints, unpaid) ===" % len(targets))
    methods = {}
    for row in targets:
        methods[row["method"]] = methods.get(row["method"], 0) + 1
    print("declared methods in the sample: %s" % sorted(methods.items()))
    results = []
    started = time.time()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        probed = pool.map(lambda r: probe(r["url"], r["method"]), targets)
        for row, got in zip(targets, probed):
            time.sleep(0.05)
            got["cat_amount"] = row["amount"]
            got["cat_description"] = row["description"]
            got["cat_updated"] = row["lastUpdated"]
            got["url"] = row["url"]
            got["method"] = row["method"]
            results.append(got)
    print("probed in %.0fs" % (time.time() - started))

    tally = {}
    for got in results:
        status = got["status"]
        if status == 0:
            key = "unreachable (%s)" % got.get("error", "?")
        elif status == 200:
            key = "answers free (advertised paid)"
        elif status == 402 and got.get("amount"):
            key = "402 with a parsable challenge"
        elif status == 402:
            key = "402 without a parsable challenge"
        else:
            key = "HTTP %d" % status
        tally[key] = tally.get(key, 0) + 1

    by_method_status = {}
    for got in results:
        if got["status"] in (404, 405, 400, 403):
            key = (got["method"], got["status"])
            by_method_status[key] = by_method_status.get(key, 0) + 1
    print("failures by declared method: %s"
          % sorted(("%s/%d" % k, v) for k, v in by_method_status.items()))

    confirmed = price_drift = desc_drift = both_drift = 0
    examples = []
    for got in results:
        if got["status"] != 402 or not got.get("amount"):
            continue
        same_amount = str(got["amount"]) == str(got["cat_amount"])
        same_desc = normalise(got["description"]) == normalise(got["cat_description"])
        if same_amount and same_desc:
            confirmed += 1
            continue
        if not same_amount and same_desc:
            price_drift += 1
        elif same_amount and not same_desc:
            desc_drift += 1
        else:
            both_drift += 1
        if len(examples) < 12:
            examples.append({
                "url": got["url"],
                "amount_catalogue": got["cat_amount"], "amount_live": got["amount"],
                "desc_catalogue": (got["cat_description"] or "")[:110],
                "desc_live": (got["description"] or "")[:110],
                "catalogue_last_updated": got["cat_updated"],
            })

    print("\nrow outcomes:")
    for key in sorted(tally, key=lambda k: -tally[k]):
        print("   %-38s %4d  %5.1f%%" % (key, tally[key], 100.0 * tally[key] / len(results)))

    comparable = confirmed + price_drift + desc_drift + both_drift
    print("\nof the %d rows that still answer a parsable 402:" % comparable)
    print("   confirmed (price and description match)  %4d  %5.1f%%"
          % (confirmed, 100.0 * confirmed / max(1, comparable)))
    print("   price drift                              %4d  %5.1f%%"
          % (price_drift, 100.0 * price_drift / max(1, comparable)))
    print("   description drift only                   %4d  %5.1f%%"
          % (desc_drift, 100.0 * desc_drift / max(1, comparable)))
    print("   both differ                              %4d  %5.1f%%"
          % (both_drift, 100.0 * both_drift / max(1, comparable)))

    print("\nexamples:")
    for ex in examples:
        print("  %s" % ex["url"][:100])
        print("     price %s -> %s  (catalogue row %s)"
              % (ex["amount_catalogue"], ex["amount_live"],
                 ex["catalogue_last_updated"]))
        print("     cat  %s" % ex["desc_catalogue"])
        print("     live %s" % ex["desc_live"])

    OUT.write_text(json.dumps({"rows_read": len(rows), "probed": len(results),
                               "outcomes": tally, "confirmed": confirmed,
                               "price_drift": price_drift,
                               "description_drift": desc_drift,
                               "median_age_days": statistics.median(ages) if ages else None,
                               "examples": examples}, indent=1), encoding="utf-8")
    print("\nwritten to %s" % OUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
