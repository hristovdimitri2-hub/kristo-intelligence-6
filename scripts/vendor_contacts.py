"""Find a published contact address for each trust-layer vendor with no site address.

Order of evidence: npm registry author/maintainers (emails are published there),
crates.io owners, then the GitHub repo's own metadata. Nothing is inferred: a field
that is absent is printed as absent.
"""
import json
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

NPM = [
    ("Teppi", "teppi-client"),
    ("zauth", "@zauthx402/sdk"),
    ("PEAC Protocol", "@peac/adapter-x402"),
    ("OMATrust", "@oma3/omatrust"),
    ("AffixIO", "affixio"),
    ("x402aff", "x402aff"),
]

GH = [
    ("Teppi", "teppi-xyz/teppi-client"),
    ("zauth", "zauthofficial/zauthSDK"),
    ("PEAC Protocol", "peacprotocol/peac"),
    ("OMATrust", "oma3dao/omatrust-sdk"),
    ("AffixIO", "AffixIO/SDK"),
    ("Elara", "navigatorbuilds/elara-mesh"),
]


def get(url, accept="application/json"):
    req = urllib.request.Request(url, headers={"User-Agent": "kristo-outreach/1.0",
                                               "Accept": accept})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:300]
    except Exception as e:                                        # noqa: BLE001
        return None, "%s: %s" % (type(e).__name__, e)


print("=" * 78)
print("npm registry — author / maintainers / homepage")
print("=" * 78)
for label, pkg in NPM:
    url = "https://registry.npmjs.org/" + pkg.replace("/", "%2F")
    code, body = get(url)
    if code != 200:
        print("%-14s %-22s HTTP %s %s" % (label, pkg, code, body[:120]))
        continue
    d = json.loads(body)
    latest = d.get("dist-tags", {}).get("latest")
    ver = d.get("versions", {}).get(latest, {})
    author = ver.get("author") or d.get("author")
    print("%-14s %-22s latest=%s" % (label, pkg, latest))
    print("    author      : %s" % json.dumps(author, ensure_ascii=False))
    print("    maintainers : %s" % json.dumps(
        [{"name": m.get("name"), "email": m.get("email")}
         for m in d.get("maintainers", [])], ensure_ascii=False))
    print("    homepage    : %s" % (ver.get("homepage") or d.get("homepage")))
    print("    repo        : %s" % json.dumps(ver.get("repository"), ensure_ascii=False))
    bugs = ver.get("bugs") or d.get("bugs")
    print("    bugs        : %s" % json.dumps(bugs, ensure_ascii=False))

print()
print("=" * 78)
print("crates.io — Elara")
print("=" * 78)
code, body = get("https://crates.io/api/v1/crates/elara-verify")
if code == 200:
    d = json.loads(body)
    c = d.get("crate", {})
    print("homepage   :", c.get("homepage"))
    print("repository :", c.get("repository"))
    print("description:", (c.get("description") or "")[:160])
    print("owners     :", json.dumps(
        [{"login": o.get("login"), "name": o.get("name")}
         for o in d.get("users", [])], ensure_ascii=False))
else:
    print("HTTP", code, body[:200])

print()
print("=" * 78)
print("GitHub repo metadata")
print("=" * 78)
for label, repo in GH:
    code, body = get("https://api.github.com/repos/" + repo)
    if code != 200:
        print("%-14s %-34s HTTP %s %s" % (label, repo, code, body[:100]))
        continue
    d = json.loads(body)
    owner = d.get("owner", {})
    print("%-14s %-34s" % (label, repo))
    print("    owner      : %s (%s)" % (owner.get("login"), owner.get("type")))
    print("    owner email: %s" % owner.get("email"))
    print("    homepage   : %s" % d.get("homepage"))
    print("    pushed_at  : %s   stars=%s" % (d.get("pushed_at"), d.get("stargazers_count")))
