"""
render_deploy.py
================
Triggers a new deployment on Render via the Render API.

Usage:
    python render_deploy.py

Requires the environment variable RENDER_API_KEY, supplied through a Replit
Secret. The key is intentionally never accepted as a command-line
argument, because command-line arguments can be persisted in shell history.
"""

import os
import sys
import json
import requests

RENDER_API_BASE = "https://api.render.com/v1"
SERVICE_ID = os.environ.get("RENDER_SERVICE_ID", "")  # kristo-intelligence-api on Render


def trigger_deploy(api_key: str, service_id: str) -> dict:
    """
    Trigger a new deploy on Render by clearing the build cache and
    initiating a fresh deploy via the Render API.
    """
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # 1. Try to list services to find the correct service ID
    print("  [INFO] Fetching services from Render API...")
    try:
        resp = requests.get(f"{RENDER_API_BASE}/services", headers=headers, timeout=30)
        if resp.ok:
            services = resp.json()
            print(f"  [INFO] Found {len(services)} service(s).")
            matches = []
            for entry in services:
                # Render API returns {"cursor": ..., "service": {...}}
                svc = entry.get("service", entry) if isinstance(entry, dict) else {}
                sid = svc.get("id", "")
                sname = svc.get("name", "")
                stype = svc.get("type", "")
                print(f"    - {sid} | {sname} | {stype}")
                if "kristo-intelligence" in sname.lower():
                    matches.append((sid, sname))
            # Only fall back to name-matching when the environment did not name
            # the service. This used to override RENDER_SERVICE_ID with the LAST
            # name match, so on an account holding more than one service with
            # "kristo-intelligence" in the name it could deploy to the wrong one
            # — and the explicit, correct ID was silently discarded.
            if service_id:
                print(f"  [INFO] Using RENDER_SERVICE_ID from the environment: "
                      f"{service_id}")
                if matches and service_id not in [m[0] for m in matches]:
                    print(f"  [WARN] That id is not among the name matches "
                          f"{[m[0] for m in matches]} — check you mean it.")
            elif len(matches) == 1:
                service_id = matches[0][0]
                print(f"  [INFO] Auto-detected service ID: {service_id} "
                      f"({matches[0][1]})")
            elif len(matches) > 1:
                print(f"  [ERROR] {len(matches)} services match "
                      f"'kristo-intelligence': {[m[0] for m in matches]}. "
                      f"Refusing to guess — set RENDER_SERVICE_ID.")
                return {}
            else:
                print("  [ERROR] No service matched 'kristo-intelligence' and "
                      "RENDER_SERVICE_ID is unset — nothing to deploy to.")
                return {}
        else:
            print(f"  [WARN] Could not list services: {resp.status_code} {resp.text[:200]}")
    except Exception as exc:
        print(f"  [WARN] Service listing failed: {exc}")

    # 2. Trigger deploy
    print(f"  [INFO] Triggering deploy for service: {service_id}")
    url = f"{RENDER_API_BASE}/services/{service_id}/deploys"
    payload = {"clearCache": "clear"}

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.ok:
            data = resp.json()
            deploy_id = data.get("id", "unknown")
            print(f"  [OK] Deploy triggered successfully!")
            print(f"    Deploy ID: {deploy_id}")
            print(f"    Status:    {data.get('status', 'unknown')}")
            print(f"    Commit:    {data.get('commit', {}).get('id', 'N/A')}")
            return data
        else:
            print(f"  [ERROR] Deploy trigger failed: {resp.status_code}")
            print(f"    Response: {resp.text[:500]}")
            return {}
    except Exception as exc:
        print(f"  [ERROR] Deploy trigger request failed: {exc}")
        return {}


def check_deploy_status(api_key: str, service_id: str, deploy_id: str) -> str:
    """Check the status of a deploy."""
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    url = f"{RENDER_API_BASE}/services/{service_id}/deploys/{deploy_id}"
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.ok:
            data = resp.json()
            return data.get("status", "unknown")
    except Exception:
        pass
    return "unknown"


def main():
    print("=" * 60)
    print("  Kristo Intelligence - Render Deploy Trigger")
    print("=" * 60)

    api_key = os.getenv("RENDER_API_KEY", "").strip()
    service_id = os.getenv("RENDER_SERVICE_ID", SERVICE_ID)

    if not api_key:
        print("  [ERROR] No Render API key provided.")
        print("  Add RENDER_API_KEY through Replit Secrets before running this script.")
        sys.exit(1)

    print(f"  Service ID: {service_id}")
    print("-" * 60)

    result = trigger_deploy(api_key, service_id)

    if result and result.get("id"):
        print()
        print("  Deploy has been triggered. It may take 2-5 minutes to complete.")
        print(f"  Check status at: https://dashboard.render.com/web/{service_id}")
    else:
        print()
        print("  [NOTE] If the service ID is incorrect, update SERVICE_ID in this script")
        print("  or set RENDER_SERVICE_ID environment variable.")

    print("=" * 60)


if __name__ == "__main__":
    main()