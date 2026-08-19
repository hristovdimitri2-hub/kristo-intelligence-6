#!/usr/bin/env python3
"""
render_env_sync.py
==================
Synchronizes local .env variables to Render Web Service via Render API,
then triggers a new production deployment.

Usage:
    python render_env_sync.py

Environment Variables Required:
    - RENDER_API_KEY (must be supplied through the environment)
    - Local .env file with variables to sync

Features:
    1. Reads local .env file
    2. Updates Render service environment variables via API
    3. Triggers a new deployment with cache clear
    4. Verifies deployment status
"""

import os
import sys
import json
import requests
from pathlib import Path

# Render API Configuration
RENDER_API_BASE = "https://api.render.com/v1"
RENDER_API_KEY = os.getenv("RENDER_API_KEY", "").strip()
SERVICE_ID = "srv-d9maroe7bikc73adkaug"  # kristo-intelligence-api

# Environment variables to sync to Render
SYNC_ENV_VARS = [
    "STRIPE_API_KEY",
    "STRIPE_PUBLISHABLE_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "BASE44_API_KEY",
    "BASE_RPC_URL",
    "BASE_CHAIN_ID",
    "BASE_USDC_CONTRACT",
    "BASE_FEE_AMOUNT_USDC",
    "BASE_FEE_RECEIVER",
    "DISCORD_WEBHOOK_URL",
]


def parse_env_file(file_path: str) -> dict:
    """Parse .env file manually without external dependencies."""
    env_vars = {}
    try:
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue
                # Parse KEY=VALUE
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    # Remove quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    env_vars[key] = value
    except Exception as exc:
        print(f"  [ERROR] Failed to parse .env: {exc}")
    return env_vars


def load_local_env():
    """Load environment variables from local .env file."""
    env_path = ".env"
    if not Path(env_path).exists():
        print("  [ERROR] .env file not found!")
        return {}
    
    all_env = parse_env_file(env_path)
    env_vars = {}
    for key in SYNC_ENV_VARS:
        value = all_env.get(key)
        if value:
            env_vars[key] = value
    return env_vars


def get_render_headers():
    """Build Render API headers."""
    if not RENDER_API_KEY:
        raise RuntimeError("RENDER_API_KEY must be configured through Replit Secrets.")
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {RENDER_API_KEY}",
        "Content-Type": "application/json",
    }


def get_current_env_vars(service_id: str) -> dict:
    """Fetch current environment variables from Render."""
    print("  [INFO] Fetching current environment variables from Render...")
    headers = get_render_headers()
    url = f"{RENDER_API_BASE}/services/{service_id}/env-vars"
    
    try:
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.ok:
            data = resp.json()
            env_vars = {}
            if isinstance(data, list):
                for var in data:
                    env_vars[var.get("key", "")] = var.get("value", "")
            else:
                env_vars = data
            print(f"  [OK] Retrieved {len(env_vars)} environment variables")
            return env_vars
        else:
            print(f"  [WARN] Failed to fetch env vars: {resp.status_code}")
            return {}
    except Exception as exc:
        print(f"  [ERROR] Failed to fetch env vars: {exc}")
        return {}


def update_env_vars(service_id: str, env_vars: dict) -> bool:
    """Update environment variables on Render service."""
    print("  [INFO] Updating environment variables on Render...")
    headers = get_render_headers()
    url = f"{RENDER_API_BASE}/services/{service_id}/env-vars"
    
    # Build payload for each environment variable
    updates = []
    for key, value in env_vars.items():
        updates.append({
            "key": key,
            "value": value,
        })
    
    try:
        # Update each variable
        for update in updates:
            resp = requests.put(
                f"{url}/{update['key']}",
                headers=headers,
                json={"value": update["value"]},
                timeout=30
            )
            if resp.ok:
                print(f"    ✓ {update['key']} updated")
            else:
                print(f"    ✗ {update['key']} failed: {resp.status_code}")
                return False
        
        print(f"  [OK] All {len(updates)} environment variables updated successfully!")
        return True
    except Exception as exc:
        print(f"  [ERROR] Failed to update env vars: {exc}")
        return False


def trigger_deployment(service_id: str) -> dict:
    """Trigger a new deployment on Render."""
    print("  [INFO] Triggering new production deployment on Render...")
    headers = get_render_headers()
    url = f"{RENDER_API_BASE}/services/{service_id}/deploys"
    payload = {"clearCache": "clear"}
    
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.ok:
            data = resp.json()
            deploy_id = data.get("id", "unknown")
            print(f"  [OK] Deployment triggered!")
            print(f"    Deploy ID: {deploy_id}")
            print(f"    Status:    {data.get('status', 'pending')}")
            return data
        else:
            print(f"  [ERROR] Failed to trigger deployment: {resp.status_code}")
            print(f"    Response: {resp.text[:500]}")
            return {}
    except Exception as exc:
        print(f"  [ERROR] Deployment trigger failed: {exc}")
        return {}


def check_deployment_status(service_id: str, deploy_id: str):
    """Check the status of a deployment."""
    print(f"\n  [INFO] Checking deployment status (ID: {deploy_id})...")
    headers = get_render_headers()
    url = f"{RENDER_API_BASE}/services/{service_id}/deploys/{deploy_id}"
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.ok:
            data = resp.json()
            status = data.get("status", "unknown")
            print(f"    Status: {status}")
            if status == "live":
                print(f"  [OK] ✓ Deployment is LIVE!")
            elif status == "build_in_progress":
                print(f"  [INFO] Build in progress... check Render dashboard for details")
            return status
        else:
            print(f"  [WARN] Could not fetch status: {resp.status_code}")
    except Exception as exc:
        print(f"  [WARN] Status check failed: {exc}")
    
    return "unknown"


def main():
    print("\n" + "="*70)
    print("  Kristo Intelligence v5 - Automated Stripe & Render Sync")
    print("="*70 + "\n")

    if not RENDER_API_KEY:
        print("  [ERROR] RENDER_API_KEY is not configured.")
        print("  Add it through Replit Secrets before running this script.")
        sys.exit(1)

    # Step 1: Load local environment variables
    print("[1/4] Loading local environment variables from .env...")
    local_env = load_local_env()
    if not local_env:
        print("  [ERROR] No environment variables found to sync!")
        return False
    print(f"  [OK] Loaded {len(local_env)} variables for sync:\n")
    for key in sorted(local_env):
        print(f"    ✓ {key} configured")
    
    # Step 2: Update Render environment variables
    print("\n[2/4] Syncing variables to Render Web Service...")
    if not update_env_vars(SERVICE_ID, local_env):
        print("  [ERROR] Failed to update Render environment variables!")
        return False
    
    # Step 3: Trigger deployment
    print("\n[3/4] Triggering production deployment...")
    deploy_result = trigger_deployment(SERVICE_ID)
    if not deploy_result:
        print("  [ERROR] Failed to trigger deployment!")
        return False
    
    deploy_id = deploy_result.get("id", "unknown")
    
    # Step 4: Check status
    print("\n[4/4] Verifying deployment status...")
    status = check_deployment_status(SERVICE_ID, deploy_id)
    
    # Success summary
    print("\n" + "="*70)
    print("  ✓ AUTOMATED DEPLOYMENT COMPLETE")
    print("="*70)
    print(f"\nDeployment Details:")
    print(f"  Service ID:       {SERVICE_ID}")
    print(f"  Deploy ID:        {deploy_id}")
    print(f"  Status:           {status}")
    print(f"  Environment Vars: {len(local_env)} synced")
    print(f"\nMonitor live deployment:")
    print(f"  https://dashboard.render.com/services/{SERVICE_ID}")
    print("\n")
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
