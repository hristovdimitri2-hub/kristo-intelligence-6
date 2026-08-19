#!/usr/bin/env python3
"""
render_status_check.py
======================
Comprehensive health check and deployment status verification.
"""

import os
import sys
import requests
from datetime import datetime

RENDER_API_BASE = "https://api.render.com/v1"
RENDER_API_KEY = os.getenv("RENDER_API_KEY", "").strip()
SERVICE_ID = "srv-d9maroe7bikc73adkaug"
SERVICE_URL = "https://kristo-intelligence-api.onrender.com"


def get_render_headers():
    """Build Render API headers."""
    if not RENDER_API_KEY:
        raise RuntimeError("RENDER_API_KEY must be configured through Replit Secrets.")
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {RENDER_API_KEY}",
        "Content-Type": "application/json",
    }


def check_service_status():
    """Check the service status via Render API."""
    print("\n[1] Checking Render Service Status...")
    print("-" * 60)
    
    headers = get_render_headers()
    url = f"{RENDER_API_BASE}/services/{SERVICE_ID}"
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.ok:
            data = resp.json()
            service = data.get("service", data)
            
            print(f"  Service Name:    {service.get('name', 'N/A')}")
            print(f"  Service Type:    {service.get('type', 'N/A')}")
            print(f"  Service ID:      {service.get('id', 'N/A')}")
            print(f"  Status:          {service.get('status', 'N/A')}")
            print(f"  Updated At:      {service.get('updatedAt', 'N/A')}")
            
            return service
        else:
            print(f"  [ERROR] Failed to get service: {resp.status_code}")
            print(f"  Response: {resp.text[:300]}")
            return None
    except Exception as exc:
        print(f"  [ERROR] Failed to check service: {exc}")
        return None


def check_deployment_history():
    """Check recent deployment history."""
    print("\n[2] Checking Recent Deployment History...")
    print("-" * 60)
    
    headers = get_render_headers()
    url = f"{RENDER_API_BASE}/services/{SERVICE_ID}/deploys?limit=5"
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.ok:
            data = resp.json()
            
            # Handle pagination response
            deploys = []
            if isinstance(data, dict) and "deploys" in data:
                deploys = data["deploys"]
            elif isinstance(data, list):
                deploys = data
            
            if deploys:
                print(f"  Found {len(deploys)} recent deployment(s):")
                for i, deploy in enumerate(deploys[:3], 1):
                    deploy_id = deploy.get("id", "N/A")
                    status = deploy.get("status", "N/A")
                    created_at = deploy.get("createdAt", "N/A")
                    print(f"\n    [{i}] Deploy ID: {deploy_id}")
                    print(f"        Status:   {status}")
                    print(f"        Created:  {created_at}")
            else:
                print("  No deployments found.")
            
            return deploys
        else:
            print(f"  [ERROR] Failed to get deployments: {resp.status_code}")
            return []
    except Exception as exc:
        print(f"  [ERROR] Failed to check deployments: {exc}")
        return []


def check_health_endpoint():
    """Check the application health endpoint."""
    print("\n[3] Checking Application Health Endpoint...")
    print("-" * 60)
    
    health_url = f"{SERVICE_URL}/api/launch/health"
    
    try:
        resp = requests.get(health_url, timeout=10)
        status_code = resp.status_code
        
        print(f"  Health Endpoint: {health_url}")
        print(f"  Status Code:     {status_code}")
        
        if status_code == 200:
            print(f"  Response:        ✓ OK")
            try:
                data = resp.json()
                print(f"\n  Health Details:")
                for key, value in data.items():
                    print(f"    - {key}: {value}")
            except:
                print(f"  Response Body:   {resp.text[:200]}")
            return True
        else:
            print(f"  Response:        ✗ FAILED")
            print(f"  Body:            {resp.text[:300]}")
            return False
    except requests.exceptions.ConnectTimeout:
        print(f"  [WARN] Health endpoint is not responding (service may be building)")
        return None
    except Exception as exc:
        print(f"  [ERROR] Failed to check health: {exc}")
        return False


def check_env_vars():
    """Check current environment variables on Render."""
    print("\n[4] Verifying Synced Environment Variables...")
    print("-" * 60)
    
    headers = get_render_headers()
    url = f"{RENDER_API_BASE}/services/{SERVICE_ID}/env-vars"
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.ok:
            data = resp.json()
            
            stripe_vars = {}
            if isinstance(data, list):
                for var in data:
                    key = var.get("key", "")
                    if "STRIPE" in key or "BASE" in key:
                        value = var.get("value", "")
                        masked = value[:20] + "..." if len(value) > 20 else value
                        stripe_vars[key] = masked
            
            if stripe_vars:
                print(f"  ✓ Found {len(stripe_vars)} environment variables synced:")
                for key, value in stripe_vars.items():
                    print(f"    - {key}={value}")
            else:
                print("  No environment variables found")
            
            return stripe_vars
        else:
            print(f"  [ERROR] Failed to fetch env vars: {resp.status_code}")
            return {}
    except Exception as exc:
        print(f"  [ERROR] Failed to check env vars: {exc}")
        return {}


def main():
    print("\n" + "=" * 70)
    print("  Kristo Intelligence v5 - Production Deployment Status Check")
    print("=" * 70)

    if not RENDER_API_KEY:
        print("  [ERROR] RENDER_API_KEY is not configured.")
        print("  Add it through Replit Secrets before running this script.")
        sys.exit(1)

    service = check_service_status()
    deploys = check_deployment_history()
    health = check_health_endpoint()
    env_vars = check_env_vars()
    
    # Summary
    print("\n" + "=" * 70)
    print("  DEPLOYMENT STATUS SUMMARY")
    print("=" * 70)
    
    if service:
        status = service.get("status", "unknown")
        print(f"\n  Service Status:       {status}")
        print(f"  Environment Synced:   ✓ ({len(env_vars)} vars)")
        print(f"  Health Check:         {'✓ LIVE' if health is True else ('⏳ BUILDING' if health is None else '✗ FAILED')}")
    
    print(f"\n  Monitor Details:      https://dashboard.render.com/services/{SERVICE_ID}")
    print(f"  Service URL:          {SERVICE_URL}")
    
    if deploys:
        latest_deploy = deploys[0]
        latest_status = latest_deploy.get("status", "unknown")
        print(f"\n  Latest Deploy Status: {latest_status}")
        if latest_status in ["live", "deployed"]:
            print(f"  ✓ Production deployment is ACTIVE")
        elif latest_status == "build_in_progress":
            print(f"  ⏳ Build is in progress. Check Render dashboard for details.")
        else:
            print(f"  ⚠ Check Render dashboard for deployment details")
    
    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    main()
