# -*- coding: utf-8 -*-
"""Render API helper for the self-paid E2E test (run via powershell wrapper)."""
import json
import os
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Never hardcode: read from the environment (set RENDER_API_KEY before use).
API_KEY = os.getenv("RENDER_API_KEY", "")
SERVICE_ID = os.getenv("RENDER_SERVICE_ID", "srv-d9maroe7bikc73adkaug")
BASE = "https://api.render.com/v1"

if not API_KEY:
    print("ERROR: set RENDER_API_KEY env var first (do not hardcode it here).")
    sys.exit(2)


def _req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": e.code, "detail": e.read().decode()[:500]}


def env_check():
    """Print whether WALLET_PRIVATE_KEY is set + key env values."""
    envs = _req("GET", f"/services/{SERVICE_ID}/env-vars?limit=50")
    if isinstance(envs, dict) and "error" in envs:
        print("ENV ERR:", envs)
        return
    keys = [e["envVar"]["key"] for e in envs]
    print("WALLET_PRIVATE_KEY set:", "WALLET_PRIVATE_KEY" in keys)
    for k in ("AGENT_AUTO_EXECUTE", "BASE_FEE_AMOUNT_USDC", "KRISTO_FREE_TIER_LIMIT"):
        v = _req("GET", f"/services/{SERVICE_ID}/env-vars/{k}")
        val = v.get("envVar", {}).get("value", "?") if isinstance(v, dict) else "?"
        print(f"{k} = {val!r}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "env"
    if cmd == "env":
        env_check()
    elif cmd == "raw":
        for k in ("AGENT_AUTO_EXECUTE", "BASE_FEE_AMOUNT_USDC"):
            print(k, "->", json.dumps(_req("GET", f"/services/{SERVICE_ID}/env-vars/{k}")))
    elif cmd == "fixfee":
        # Align the legacy fallback price env var with config.py default (0.005).
        r = _req("PUT", f"/services/{SERVICE_ID}/env-vars/BASE_FEE_AMOUNT_USDC",
                 {"value": "0.005"})
        print("PUT BASE_FEE_AMOUNT_USDC=0.005 ->", json.dumps(r))
    elif cmd == "gateway":
        # User's E2E gateway check script, executed inside the Render service
        # environment (where WALLET_PRIVATE_KEY lives). Read-only. Never
        # prints the key itself — only the derived address + balances.
        import base64
        script = """
import os
from web3 import Web3

KNOWN = {
    "0xd4cda900839c0fed4374ee37ea0dbe8e4c6fd08f": "RECEIVER (current)",
    "0xd4cda980839c8fed4374ee37ea8dbe8c4ecfd88f": "OLD WRONG ADDRESS (audit dcebafd)",
    "0x298268446cb8f5387258655527c7b70f876b7493": "previous Render key wallet",
}

print("--- SYSTEM E2E GATEWAY CHECK ---")
private_key = os.environ.get("WALLET_PRIVATE_KEY")
if not private_key:
    print("CRITICAL: WALLET_PRIVATE_KEY is missing from environment variables.")
    raise SystemExit(1)

w3 = Web3()
account = w3.eth.account.from_key(private_key)
derived_address = account.address
print(f"Derived Hot Wallet Address: {derived_address}")
print(f"Matches known: {KNOWN.get(derived_address.lower(), 'UNKNOWN / NEW address')}")

base_rpc = os.environ.get("BASE_RPC_URL", "https://mainnet.base.org")
w3p = Web3(Web3.HTTPProvider(base_rpc, request_kwargs={"timeout": 30}))
if w3p.is_connected():
    bal_wei = w3p.eth.get_balance(Web3.to_checksum_address(derived_address))
    print(f"Chain Connection Active: True")
    print(f"Wallet ETH Balance: {Web3.from_wei(bal_wei, 'ether')}")
    USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    abi = [
        {"constant": True, "inputs": [{"name": "o", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
        {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
    ]
    c = w3p.eth.contract(address=Web3.to_checksum_address(USDC), abi=abi)
    dec = c.functions.decimals().call()
    raw = c.functions.balanceOf(Web3.to_checksum_address(derived_address)).call()
    print(f"Wallet USDC Balance: {raw / 10**dec}")
else:
    print("Warning: Could not connect to chain RPC for live balance check.")

print(f"AGENT_AUTO_EXECUTE: {os.environ.get('AGENT_AUTO_EXECUTE')}")
print(f"BASE_FEE_AMOUNT_USDC: {os.environ.get('BASE_FEE_AMOUNT_USDC')}")
print("--- GATEWAY PASSED: Ready for execution sequence ---")
"""
        b64 = base64.b64encode(script.encode()).decode()
        body = {"startCommand": f"echo {b64} | base64 -d | python -"}
        r = _req("POST", f"/services/{SERVICE_ID}/jobs", body)
        print("JOB ->", json.dumps(r)[:400])
    elif cmd == "deploy":
        r = _req("POST", f"/services/{SERVICE_ID}/deploys", {})
        print("TRIGGER DEPLOY ->", json.dumps(r))
    elif cmd == "jobaddr":
        # Read-only Render job: derive the hot-wallet address from
        # WALLET_PRIVATE_KEY inside the service environment and print the
        # address + balances. NEVER prints the key itself.
        import base64
        script = """
import os
from web3 import Web3
w3 = Web3(Web3.HTTPProvider("https://mainnet.base.org", request_kwargs={"timeout": 30}))
acct = w3.eth.account.from_key(os.environ["WALLET_PRIVATE_KEY"])
addr = acct.address
print("DERIVED_ADDR:", addr)
print("ETH_BALANCE:", w3.eth.get_balance(addr) / 1e18)
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
abi = [
    {"constant": True, "inputs": [{"name": "o", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
]
c = w3.eth.contract(address=Web3.to_checksum_address(USDC), abi=abi)
dec = c.functions.decimals().call()
raw = c.functions.balanceOf(addr).call()
print("USDC_BALANCE:", raw / 10**dec)
print("AGENT_AUTO_EXECUTE:", os.environ.get("AGENT_AUTO_EXECUTE"))
print("BASE_FEE_AMOUNT_USDC:", os.environ.get("BASE_FEE_AMOUNT_USDC"))
"""
        b64 = base64.b64encode(script.encode()).decode()
        body = {"startCommand": f"echo {b64} | base64 -d | python -"}
        r = _req("POST", f"/services/{SERVICE_ID}/jobs", body)
        print("JOB ->", json.dumps(r)[:600])
    elif cmd == "joblogs":
        job_id = sys.argv[2]
        # List jobs via the service endpoint
        r = _req("GET", f"/services/{SERVICE_ID}/jobs?limit=5")
        print("JOBS LIST ->", json.dumps(r)[:1500])
    elif cmd == "startup":
        # Fetch startup logs from a deploy window (arg: ISO start like 2026-08-27T19:04:00Z)
        from datetime import datetime, timedelta, timezone as _tz
        start = sys.argv[2]
        end = (datetime.now(_tz.utc) + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        svc = _req("GET", f"/services/{SERVICE_ID}")
        owner = svc.get("ownerId") if isinstance(svc, dict) else None
        if owner:
            r = _req("GET", f"/logs?limit=100&startTime={start}&endTime={end}"
                            f"&ownerId={owner}&resource={SERVICE_ID}")
            logs = (r.get("logs") or []) if isinstance(r, dict) else []
            print(f"Fetched {len(logs)} logs since {start}:")
            for l in logs:
                msg = l.get("message", "")
                if "GET /health" not in msg:  # skip sentinel noise
                    print("  >", msg[:260])
        # Search recent logs for wallet/job markers
        from datetime import datetime, timedelta, timezone as _tz
        end_dt = datetime.now(_tz.utc).replace(microsecond=0)
        start_dt = end_dt - timedelta(hours=2)
        start = start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        end = end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        svc = _req("GET", f"/services/{SERVICE_ID}")
        owner = svc.get("ownerId") if isinstance(svc, dict) else None
        if not owner:
            print("Cannot resolve ownerId")
        else:
            r = _req("GET", f"/logs?limit=100&startTime={start}&endTime={end}"
                            f"&ownerId={owner}&resource={SERVICE_ID}")
            logs = r.get("logs", []) if isinstance(r, dict) else []
            markers = ("DERIVED_ADDR", "ETH_BALANCE", "USDC_BALANCE", "AGENT_AUTO_EXECUTE",
                       "BASE_FEE_AMOUNT_USDC", "wallet", "Wallet", "monitor-only", "monitor-only")
            hits = [l["message"] for l in logs
                    if any(m in l.get("message", "") for m in markers)]
            print(f"Scanned {len(logs)} logs, {len(hits)} hits:")
            for h in hits[:25]:
                print("  >", h[:250])
            if not hits:
                print("  (no markers in app logs — querying job-typed logs)")
                rj = _req("GET", f"/logs?limit=50&startTime={start}&endTime={end}"
                                 f"&ownerId={owner}&resource={SERVICE_ID}&type=job")
                jlogs = (rj.get("logs") or []) if isinstance(rj, dict) else []
                print(f"Job logs: {len(jlogs)}")
                for l in jlogs[:20]:
                    print("  J>", l.get("message", "")[:250])
                if isinstance(rj, dict) and "error" in rj:
                    print("  job-log err:", rj.get("detail", "")[:200])
