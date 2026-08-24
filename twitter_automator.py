#!/usr/bin/env python3
"""
twitter_automator.py
====================
Automated X (Twitter) marketing module for Kristo Intelligence API v6.

Pulls live on-chain market data from /api/stats endpoint, formats it into
technical posts suitable for developer/trading audiences, and publishes to X.

Usage:
    python twitter_automator.py [--dry-run] [--endpoint URL]

Examples:
    python twitter_automator.py  # Uses production endpoint
    python twitter_automator.py --dry-run  # Preview post without publishing
    python twitter_automator.py --endpoint http://localhost:5000

Configuration:
    Requires these environment variables from .env:
    - TWITTER_API_KEY (X/Twitter API v2 key)
    - TWITTER_API_SECRET (X/Twitter API v2 secret)
    - TWITTER_ACCESS_TOKEN (Bearer token for API v2)
"""

import os
import sys
import json
import requests
import argparse
from datetime import datetime, timezone
from typing import Optional, Dict, Any

# Configuration
API_ENDPOINT = "https://kristo-intelligence-api.onrender.com/api/stats"
TWITTER_API_BASE = "https://api.twitter.com/2"

# Marketing CTA signature (mandatory)
DEVELOPER_PITCH = (
    "🚀 Data stream provided via Kristo Intelligence API v6\n"
    "Request cost: 0.10 USDC | Base Network\n"
    "Connect via: https://kristo-intelligence-api.onrender.com"
)


def load_twitter_credentials() -> Dict[str, str]:
    """Load Twitter API credentials from environment."""
    credentials = {
        "api_key": os.getenv("TWITTER_API_KEY", ""),
        "api_secret": os.getenv("TWITTER_API_SECRET", ""),
        "access_token": os.getenv("TWITTER_ACCESS_TOKEN", ""),
        "access_token_secret": os.getenv("TWITTER_ACCESS_TOKEN_SECRET", ""),
        "bearer_token": os.getenv("TWITTER_BEARER_TOKEN", ""),
    }
    
    # Check if at least bearer token is configured (required for v2 API)
    if not credentials["bearer_token"]:
        print("⚠️  WARNING: TWITTER_BEARER_TOKEN not configured in .env")
        print("   Twitter posting will be simulated. To enable real posting:")
        print("   1. Generate credentials at https://developer.twitter.com/")
        print("   2. Add TWITTER_BEARER_TOKEN to .env")
        print("   3. Re-run this script\n")
    
    return credentials


def fetch_market_data(endpoint: str = API_ENDPOINT) -> Optional[Dict[str, Any]]:
    """Fetch live market data from /api/stats endpoint."""
    try:
        print(f"📡 Fetching market data from {endpoint}...")
        response = requests.get(endpoint, timeout=10)
        response.raise_for_status()
        data = response.json()
        print(f"✓ Data fetched successfully\n")
        return data
    except requests.exceptions.RequestException as e:
        print(f"✗ Failed to fetch data: {e}")
        return None


def format_twitter_post(market_data: Dict[str, Any]) -> str:
    """Format market data into a technical Twitter post."""
    
    # Extract key metrics
    today = market_data.get("today", {})
    products = market_data.get("products", [])
    market = market_data.get("market_data", {})
    
    requests_today = today.get("requests", 0)
    sales_today = today.get("sales_count", 0)
    volume_today = today.get("sales_volume_usd", 0)
    
    # Get top product by sales volume
    top_product = max(products, key=lambda p: p.get("sales_volume_usd", 0)) if products else None
    
    # Extract market sentiment
    market_sentiment = market.get("fear_greed", {})
    sentiment_index = market_sentiment.get("value", 50)
    sentiment_text = market_sentiment.get("value_classification", "Neutral")
    
    # Build the post
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    
    post = (
        "📊 Kristo Intelligence — LIVE Market Snapshot\n"
        f"⏰ {timestamp}\n\n"
        f"📈 API Activity (24h):\n"
        f"   • {requests_today:,} requests processed\n"
        f"   • {sales_today} on-chain transactions\n"
        f"   • ${volume_today:.2f} USDC volume\n\n"
    )
    
    # Add market sentiment if available
    if sentiment_index:
        fear_emoji = "😨" if sentiment_index < 25 else "😟" if sentiment_index < 50 else "😊" if sentiment_index < 75 else "🤑"
        post += (
            f"{fear_emoji} Market Sentiment: {sentiment_text} ({sentiment_index}/100)\n"
            f"   • Real-time data from Base network\n"
            f"   • USDC tracking enabled\n\n"
        )
    
    # Add top product info if available
    if top_product:
        top_name = top_product.get("name", "Top Product")
        top_volume = top_product.get("sales_volume_usd", 0)
        post += (
            f"🏆 Top Product:\n"
            f"   • {top_name}: ${top_volume:.2f}\n\n"
        )
    
    # Add developer pitch (mandatory)
    post += f"---\n{DEVELOPER_PITCH}"
    
    return post


def publish_to_twitter(post: str, credentials: Dict[str, str], dry_run: bool = False) -> bool:
    """Publish post to X/Twitter (or simulate if dry-run)."""
    
    if dry_run or not credentials["bearer_token"]:
        print("\n🎯 [DRY RUN] Simulated Twitter Post:")
        print("-" * 70)
        print(post)
        print("-" * 70)
        print("\n✓ Post preview ready (not published)\n")
        return True
    
    # Real Twitter API posting
    print("\n🐦 Publishing to X/Twitter...")
    
    headers = {
        "Authorization": f"Bearer {credentials['bearer_token']}",
        "Content-Type": "application/json",
    }
    
    payload = {"text": post}
    
    try:
        response = requests.post(
            f"{TWITTER_API_BASE}/tweets",
            headers=headers,
            json=payload,
            timeout=10
        )
        
        if response.status_code == 201:
            tweet_data = response.json()
            tweet_id = tweet_data.get("data", {}).get("id", "unknown")
            print(f"✓ Tweet published successfully!")
            print(f"  Tweet ID: {tweet_id}")
            print(f"  View at: https://twitter.com/search?q={tweet_id}\n")
            return True
        else:
            print(f"✗ Twitter API error: {response.status_code}")
            print(f"  Response: {response.text}\n")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"✗ Failed to publish to Twitter: {e}\n")
        return False


def format_post_details(market_data: Dict[str, Any]) -> str:
    """Generate detailed text summary of post content."""
    
    today = market_data.get("today", {})
    products = market_data.get("products", [])
    market = market_data.get("market_data", {})
    wallet = market_data.get("wallet", {})
    
    summary = (
        "📋 POST CONTENT BREAKDOWN\n"
        "=" * 70 + "\n\n"
        f"Date/Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        f"API Requests (today): {today.get('requests', 0)}\n"
        f"On-chain Sales: {today.get('sales_count', 0)}\n"
        f"Volume (USDC): ${today.get('sales_volume_usd', 0):.2f}\n"
    )
    
    if market:
        summary += (
            f"\nMarket Data Available:\n"
            f"  - Fear & Greed Index: {market.get('fear_greed', {}).get('value', 'N/A')}\n"
            f"  - BTC Price: ${market.get('bitcoin_price', 'N/A')}\n"
            f"  - ETH Price: ${market.get('ethereum_price', 'N/A')}\n"
        )
    
    if products:
        summary += f"\nTop {min(3, len(products))} Products by Volume:\n"
        for i, prod in enumerate(sorted(products, key=lambda p: p.get('sales_volume_usd', 0), reverse=True)[:3], 1):
            summary += f"  {i}. {prod.get('name')}: ${prod.get('sales_volume_usd', 0):.2f}\n"
    
    if wallet:
        summary += (
            f"\nWallet Activity:\n"
            f"  - Address: {wallet.get('wallet_address', 'N/A')[:10]}...\n"
            f"  - Total USDC Received: ${wallet.get('total_usdc_received', 0):.2f}\n"
        )
    
    summary += f"\n{'=' * 70}\n"
    return summary


def main():
    """Main entry point for Twitter automator."""
    
    parser = argparse.ArgumentParser(
        description="Automated Twitter posting for Kristo Intelligence API"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview post without publishing"
    )
    parser.add_argument(
        "--endpoint",
        default=API_ENDPOINT,
        help=f"API stats endpoint (default: {API_ENDPOINT})"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed breakdown"
    )
    
    args = parser.parse_args()
    
    print("\n" + "=" * 70)
    print("  KRISTO INTELLIGENCE v6 — AUTOMATED TWITTER MARKETING")
    print("=" * 70 + "\n")
    
    # Step 1: Load credentials
    credentials = load_twitter_credentials()
    
    # Step 2: Fetch market data
    market_data = fetch_market_data(args.endpoint)
    if not market_data:
        print("✗ Cannot proceed without market data")
        return False
    
    # Step 3: Show detailed breakdown if requested
    if args.verbose:
        print(format_post_details(market_data))
    
    # Step 4: Format post
    print("📝 Formatting Twitter post...")
    post = format_twitter_post(market_data)
    post_length = len(post)
    print(f"✓ Post formatted ({post_length} characters)\n")
    
    # Step 5: Publish or simulate
    success = publish_to_twitter(post, credentials, dry_run=args.dry_run)
    
    if success:
        print("✅ TWITTER MARKETING AUTOMATION COMPLETE")
    else:
        print("❌ TWITTER MARKETING AUTOMATION FAILED")
    
    print("=" * 70 + "\n")
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
