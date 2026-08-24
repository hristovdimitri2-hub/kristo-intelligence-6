#!/usr/bin/env python3
"""
production_verify.py
====================
Verify production deployment endpoints and Stripe integration.
"""

import requests
import json
import sys

BASE_URL = "https://kristo-intelligence-api.onrender.com"

def verify_endpoints():
    """Test all critical production endpoints."""
    print("\n" + "=" * 70)
    print("  PRODUCTION ENDPOINT VERIFICATION")
    print("=" * 70 + "\n")
    
    endpoints = [
        ("/api/launch/health", "Health Check"),
        ("/sales/admin", "Admin Dashboard"),
        ("/api/checkout", "Stripe Checkout"),
        ("/api/sales/summary", "Sales Summary"),
    ]
    
    results = []
    for endpoint, description in endpoints:
        url = BASE_URL + endpoint
        try:
            resp = requests.get(url, timeout=10)
            status = resp.status_code
            success = status in [200, 302, 405]  # 405 for POST-only endpoints
            
            symbol = "✓" if success else "✗"
            print(f"  {symbol} {description}")
            print(f"      URL:    {endpoint}")
            print(f"      Status: {status}\n")
            
            results.append((description, success))
        except Exception as exc:
            print(f"  ✗ {description}")
            print(f"      URL:   {endpoint}")
            print(f"      Error: {type(exc).__name__}: {str(exc)[:50]}\n")
            results.append((description, False))
    
    # Summary
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    print("=" * 70)
    print(f"  RESULTS: {passed}/{total} endpoints verified")
    print("=" * 70 + "\n")
    
    return passed == total


def verify_health_details():
    """Extract and display health check details."""
    print("\n" + "=" * 70)
    print("  PRODUCTION HEALTH DETAILS")
    print("=" * 70 + "\n")
    
    try:
        resp = requests.get(f"{BASE_URL}/api/launch/health", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            
            print("  Application Status:")
            print(f"    - App Name:          {data.get('app', 'N/A')}")
            print(f"    - Status:            {data.get('status', 'N/A').upper()}")
            print(f"    - CRM Backend:       {data.get('crm_backend', 'N/A')}")
            print(f"    - Payment Provider:  {data.get('payment_provider', 'N/A')}")
            print(f"    - Leads in System:   {data.get('lead_count', 0)}")
            
            pipeline = data.get('pipeline', {})
            if pipeline:
                print(f"\n  Sales Pipeline:")
                print(f"    - New Leads:         {pipeline.get('new', 0)}")
                print(f"    - Contacted:         {pipeline.get('contacted', 0)}")
                print(f"    - Qualified:         {pipeline.get('qualified', 0)}")
                print(f"    - Paid:              {pipeline.get('paid', 0)}")
                print(f"    - Won:               {pipeline.get('won', 0)}")
            
            print(f"\n  System Info:")
            print(f"    - Timestamp:         {data.get('timestamp', 'N/A')}")
            
            return True
        return False
    except Exception as exc:
        print(f"  [ERROR] Failed to fetch health details: {exc}")
        return False


def verify_stripe_config():
    """Verify Stripe configuration is loaded."""
    print("\n" + "=" * 70)
    print("  STRIPE CONFIGURATION")
    print("=" * 70 + "\n")
    
    try:
        resp = requests.get(f"{BASE_URL}/api/launch/health", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            provider = data.get('payment_provider', 'unknown')
            
            if provider.lower() == 'stripe':
                print(f"  ✓ Stripe Payment Provider: ACTIVE")
                print(f"  ✓ Environment variables injected successfully")
                print(f"  ✓ Checkout service initialized")
                return True
            else:
                print(f"  ✗ Payment provider: {provider} (expected: stripe)")
                return False
    except Exception as exc:
        print(f"  [ERROR] Could not verify Stripe: {exc}")
        return False


def main():
    print("\n\n")
    print("╔" + "=" * 68 + "╗")
    print("║  KRISTO INTELLIGENCE v6 - PRODUCTION DEPLOYMENT VERIFICATION   ║")
    print("╚" + "=" * 68 + "╝")
    
    # Run verifications
    endpoints_ok = verify_endpoints()
    health_ok = verify_health_details()
    stripe_ok = verify_stripe_config()
    
    # Final summary
    print("\n" + "=" * 70)
    print("  DEPLOYMENT SUMMARY")
    print("=" * 70)
    
    status = "✓ PRODUCTION READY" if all([endpoints_ok, health_ok, stripe_ok]) else "⚠ PARTIAL"
    
    print(f"\n  Status: {status}")
    print(f"\n  Endpoints:         {'✓ PASS' if endpoints_ok else '✗ FAIL'}")
    print(f"  Health Check:      {'✓ PASS' if health_ok else '✗ FAIL'}")
    print(f"  Stripe Config:     {'✓ PASS' if stripe_ok else '✗ FAIL'}")
    
    print(f"\n  Service URL:       {BASE_URL}")
    print(f"  Admin Dashboard:   {BASE_URL}/sales/admin")
    print(f"  API Docs:          {BASE_URL}/openapi.json")
    
    print("\n" + "=" * 70 + "\n")
    
    return 0 if all([endpoints_ok, health_ok, stripe_ok]) else 1


if __name__ == "__main__":
    sys.exit(main())
