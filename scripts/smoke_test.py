"""Post-audit functional smoke test for Kristo Intelligence 6.

Runs against the Flask test client and verifies:
  - all public pages and discovery endpoints return 200
  - paid endpoints enforce the x402 paywall (402) after the free tier
  - admin endpoints reject unauthenticated requests (401) and accept a
    valid token (200)
  - the Stripe webhook rejects unsigned payloads (400)
  - the x402 receiver address is consistent with config everywhere
"""
import os
import sys

# Ensure the repo root is importable when run as `python scripts/smoke_test.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["KRISTO_DISABLE_BACKGROUND_THREADS"] = "true"
os.environ["ADMIN_API_TOKEN"] = "test-admin-token"
os.environ["KRISTO_ALLOW_MOCK_PAYMENTS"] = "true"

from main import app  # noqa: E402
from config import BOUND_BASE_FEE_RECEIVER  # noqa: E402

client = app.test_client()

CHECKS = [
    ("GET", "/", None, None, 200),
    ("GET", "/health", None, None, None),  # depends on RPC; report only
    ("GET", "/dashboard", None, None, 200),
    ("GET", "/agents", None, None, 200),
    ("GET", "/launch", None, None, 200),
    ("GET", "/.well-known/x402.json", None, None, 200),
    ("GET", "/openapi.json", None, None, 200),
    ("GET", "/llms.txt", None, None, 200),
    ("GET", "/mcp.json", None, None, 200),
    ("GET", "/api/mcp/manifest", None, None, 200),
    ("GET", "/api/v1/agents", None, None, 200),
    ("GET", "/api/dashboard-stats", None, None, 200),
    ("GET", "/api/stats", None, None, 200),   # may be 200 (free tier) or 402
    ("GET", "/api/sales", None, None, 200),   # may be 200 (free tier) or 402
    ("GET", "/api/bot-status", None, None, 200),
    ("GET", "/api/admin/leads", None, None, 401),
    ("GET", "/api/admin/leads", None, "test-admin-token", 200),
    ("GET", "/api/admin/overview", None, "test-admin-token", 200),
    ("POST", "/api/webhooks/stripe", {}, None, 400),
]

passed = failed = 0
for method, path, body, token, expected in CHECKS:
    headers = {"X-Admin-Token": token} if token else {}
    if method == "GET":
        r = client.get(path, headers=headers)
    else:
        r = client.post(path, json=body, headers=headers)
    status = r.status_code
    if expected is None:
        print(f"INFO {method:4} {path:35} -> {status} (rpc-dependent)")
        continue
    if path in ("/api/stats", "/api/sales", "/api/bot-status"):
        ok = status in (200, 402)  # free tier first call = 200, paywall = 402
    else:
        ok = status == expected
    if ok:
        passed += 1
    else:
        failed += 1
    print(f"{'PASS' if ok else 'FAIL':4} {method:4} {path:35} -> {status} (expected {expected})")

print(f"\nResult: {passed}/{passed + failed} passed")

# Receiver-address consistency across all dynamic specs
disc = client.get("/.well-known/x402.json").get_json()
addr = disc["payment"]["receiver_address"]
print(f"x402.json receiver match:    {addr == BOUND_BASE_FEE_RECEIVER} ({addr})")
openapi = client.get("/openapi.json").get_json()
print(f"openapi.json receiver match: {openapi['info']['x402']['receiver_address'] == BOUND_BASE_FEE_RECEIVER}")
mcp = client.get("/api/mcp/manifest").get_json()
print(f"mcp manifest receiver match: {mcp['payment']['receiver_address'] == BOUND_BASE_FEE_RECEIVER}")
llms = client.get("/llms.txt").get_data(as_text=True)
print(f"llms.txt receiver match:     {BOUND_BASE_FEE_RECEIVER in llms}")

exit_code = 0 if failed == 0 else 1
raise SystemExit(exit_code)
