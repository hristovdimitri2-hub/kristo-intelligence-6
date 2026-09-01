# -*- coding: utf-8 -*-
"""
CDP secret tool - validate and install the Coinbase CDP API key WITHOUT
pasting it into chat.

Usage:
  1. Save the secret into secrets/cdp_api_key_secret.txt (gitignored).
     Accepted: raw PEM, portal .json export, or base64(PEM).
  2. Validate only:  python scripts/cdp_secret_tool.py --check
  3. Push to Render: python scripts/cdp_secret_tool.py --push
     (needs RENDER_API_KEY in env or secrets/render_api_key.txt,
      and KRISTO_RENDER_SERVICE_ID=srv-... )

The tool never prints the secret - only a fingerprint (len + sha256 prefix).
"""
import argparse, base64, hashlib, json, os, re, sys, urllib.request

SECRET_FILE = os.path.join(os.path.dirname(__file__), "..", "secrets", "cdp_api_key_secret.txt")
RENDER_KEY_FILE = os.path.join(os.path.dirname(__file__), "..", "secrets", "render_api_key.txt")

def load_secret():
    path = os.path.abspath(SECRET_FILE)
    if not os.path.exists(path):
        print(f"[X] Secret file not found: {path}")
        print("    Create it and paste the key from the CDP portal.")
        return None
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    return raw.strip().strip(chr(34)).strip(chr(39)).replace("\\n", "\n")

def fingerprint(raw):
    return f"len={len(raw)} sha256={hashlib.sha256(raw.encode()).hexdigest()[:12]}"

def extract_pem(raw):
    if "-----BEGIN" in raw:
        m = re.search(r"-----BEGIN ([A-Z ]+)-----(.*?)-----END [A-Z ]+-----", raw, re.S)
        if not m:
            return None, "PEM markers found but unparseable"
        return f"-----BEGIN {m.group(1)}-----" + m.group(2) + f"-----END {m.group(1)}-----", None
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            for key in ("api_key_secret", "secret", "private_key", "key"):
                if key in data:
                    return extract_pem(str(data[key]))
    except (ValueError, TypeError):
        pass
    return None, "no PEM found in the file (is it the raw EC private key?)"

def validate(raw):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    pem, err = extract_pem(raw)
    if not pem:
        return False, err
    m = re.search(r"-----BEGIN ([A-Z ]+?)-----", pem)
    if not m or "EC PRIVATE KEY" not in m.group(1):
        return False, f"PEM label mismatch - CDP EC keys say 'EC PRIVATE KEY', got '{m.group(1) if m else '?'}'"
    body = re.sub(r"\s+", "", re.search(r"-----(.*?)-----\n?(.*?)-----END", pem, re.S).group(2))
    core = body.rstrip("=")
    try:
        der = base64.b64decode(core + "=" * ((-len(core)) % 4))
    except Exception as e:
        return False, f"base64 payload undecodable: {e}"
    try:
        priv = serialization.load_der_private_key(der, password=None)
    except Exception as e:
        return False, f"DER parse failed (len={len(der)}B) - secret is corrupted (chars lost in copy/paste?): {e}"
    if not isinstance(priv, ec.EllipticCurvePrivateKey):
        return False, f"not an EC private key (got {type(priv).__name__})"
    if priv.curve.name != "secp256r1":
        return False, f"wrong curve: {priv.curve.name} - ES256 needs secp256r1"
    return True, f"VALID EC P-256 key ({fingerprint(raw)})"

def render_creds():
    key = os.getenv("RENDER_API_KEY", "").strip()
    if not key and os.path.exists(RENDER_KEY_FILE):
        with open(RENDER_KEY_FILE, "r", encoding="utf-8") as f:
            key = f.read().strip()
    if not key:
        print("[X] No RENDER_API_KEY (env or secrets/render_api_key.txt)")
        return None, None
    service = os.getenv("KRISTO_RENDER_SERVICE_ID", "").strip()
    if not service:
        print("[X] Set KRISTO_RENDER_SERVICE_ID (srv-... from Render dashboard)")
        return None, None
    return key, service

def push_to_render():
    raw = load_secret()
    if not raw:
        return 1
    ok, msg = validate(raw)
    print(("[OK] " if ok else "[X] ") + msg)
    if not ok:
        return 1
    key, service = render_creds()
    if not key:
        return 1
    pem, _err = extract_pem(raw)
    url = f"https://api.render.com/v1/services/{service}/env-vars/CDP_API_KEY_SECRET"
    req = urllib.request.Request(url, data=json.dumps({"value": pem}).encode(), method="PUT",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            print(f"[OK] Render env updated: HTTP {resp.status}")
            print("     Render redeploys automatically - watch /api/connectors for 'CDP (JWT OK)'")
            return 0
    except Exception as e:
        print(f"[X] Render API call failed: {e}")
        print("    Fallback: copy the value from secrets/cdp_api_key_secret.txt into Render manually.")
        return 1

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="validate only")
    ap.add_argument("--push", action="store_true", help="validate + push to Render")
    args = ap.parse_args()
    if args.push:
        sys.exit(push_to_render())
    raw = load_secret()
    if not raw:
        sys.exit(1)
    ok, msg = validate(raw)
    print(("[OK] " if ok else "[X] ") + msg)
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
