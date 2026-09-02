# -*- coding: utf-8 -*-
"""One-shot: install CDP key pair into Render env. Run: python scripts/push_cdp_to_render.py <render_api_key>"""
import base64, json, os, re, sys, time, urllib.request

api_key = sys.argv[1].strip() if len(sys.argv) > 1 else ""
if not api_key:
    print("usage: python scripts/push_cdp_to_render.py <render_api_key>")
    sys.exit(1)

def rreq(url, method="GET", body=None):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body else None,
        method=method, headers={"Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

# 1) find the service
services = rreq("https://api.render.com/v1/services?limit=50")
services = services if isinstance(services, list) else services.get("services", [])
target = None
for s in services:
    svc = s.get("service", s)
    if "kristo" in (svc.get("name") or "").lower():
        target = svc
        break
if not target:
    print("[X] no service matching 'kristo' found:", [s.get('service', s).get('name') for s in services])
    sys.exit(1)
sid = target["id"]
print(f"[OK] service: {target['name']} ({sid})")

# 2) load + validate the CDP secret locally
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
raw = open("secrets/cdp_api_key_secret.txt", encoding="utf-8").read().strip().replace("\\n", "\n")
m = re.search(r"-----BEGIN ([A-Z ]+)-----(.*?)-----END", raw, re.S)
if not m:
    print("[X] no PEM in secrets/cdp_api_key_secret.txt"); sys.exit(1)
core = re.sub(r"\s+", "", m.group(2))
first = core.find("=")
if first != -1: core = core[:first]
core = core.rstrip("=")
der = base64.b64decode(core + "=" * ((-len(core)) % 4))
if der[:10] == b"-----BEGIN":
    raw = der.decode(); m = re.search(r"-----BEGIN ([A-Z ]+)-----(.*?)-----END", raw, re.S)
    core = re.sub(r"\s+", "", m.group(2)); first = core.find("=")
    if first != -1: core = core[:first]
    core = core.rstrip("="); der = base64.b64decode(core + "=" * ((-len(core)) % 4))
priv = serialization.load_der_private_key(der, password=None)
assert isinstance(priv, ec.EllipticCurvePrivateKey) and priv.curve.name == "secp256r1", "invalid key"
canonical_pem = priv.private_bytes(serialization.Encoding.PEM,
    serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()).decode()
print(f"[OK] secret validated (len={len(canonical_pem)})")

# 3) key ID: from secrets/cdp_api_key.json (name field)
kd = json.load(open("secrets/cdp_api_key.json", encoding="utf-8"))
key_id = kd["name"]
print(f"[OK] key ID: {key_id}")

# 4) update BOTH env vars (POST creates, PUT updates)
for k, v in (("CDP_API_KEY_ID", key_id), ("CDP_API_KEY_SECRET", canonical_pem)):
    url = f"https://api.render.com/v1/services/{sid}/env-vars/{k}"
    req = urllib.request.Request(url, data=json.dumps({"value": v}).encode(), method="PUT",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=30)
        print(f"[OK] updated {k}")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            rreq(f"https://api.render.com/v1/services/{sid}/env-vars", "POST",
                 {"envVars": [{"key": k, "value": v}]})
            print(f"[OK] created {k}")
        else:
            print(f"[X] {k}: HTTP {e.code} {e.read()[:150]}"); sys.exit(1)

print("\n[DONE] Render redeploys automatically. /api/connectors will show 'CDP (JWT OK)' in ~3 min.")
