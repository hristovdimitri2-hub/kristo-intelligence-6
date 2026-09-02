# -*- coding: utf-8 -*-
"""DEFINITIVE test: build the JWT with Coinbase's OFFICIAL cdp-sdk
(generate_jwt / JwtOptions) using our key pair, then call the x402 verify
endpoint. If even the official SDK is rejected -> key pair is dead.
Prints only fingerprints + status codes."""
import os, json, time, urllib.request, urllib.error
from cdp.auth.utils.jwt import JwtOptions, generate_jwt

ORG = "3dc43ce6-05e8-4cb4-b9ad-cafcfd155082"
KEYID = "ad07bd0b-c931-407e-a379-fca88bedea27"
PEM = open("secrets/cdp_api_key_secret.txt", "rb").read().decode().strip()

# official builder
opts = JwtOptions(
    api_key_id=KEYID,
    api_key_secret=PEM,
    request_method="POST",
    request_host="api.cdp.coinbase.com",
    request_path="/platform/v2/x402/verify",
)
jwt = generate_jwt(opts)
parts = jwt.split(".")
import base64
def dec(s): return json.loads(base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)))
print("OFFICIAL JWT header :", dec(parts[0]))
print("OFFICIAL JWT payload:", dec(parts[1]))

req = urllib.request.Request("https://api.cdp.coinbase.com/platform/v2/x402/verify",
                             data=json.dumps({
    "x402Version": 2, "scheme": "exact", "network": "eip155:8453",
    "payload": {"signature": "0x" + "00" * 65,
                "authorization": {"from": "0x" + "01" * 20,
                                  "to": "0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f",
                                  "value": "5000", "validAfter": "0",
                                  "validBefore": "9999999999",
                                  "nonce": "0x" + "00" * 32},
                "resource": {"url": "https://kristo-intelligence-api.onrender.com/api/stats",
                             "mimeType": "application/json"}}}).encode(), method="POST")
req.add_header("Authorization", f"Bearer {jwt}")
req.add_header("Content-Type", "application/json")
try:
    r = urllib.request.urlopen(req, timeout=30)
    print("HTTP", r.status, "|", r.read().decode()[:400])
except urllib.error.HTTPError as e:
    print("HTTP", e.code, "|", e.read().decode()[:400])