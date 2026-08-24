#!/usr/bin/env python3
"""
discord_notifier.py
===================
Automated Discord webhook notifications for Kristo Intelligence API v6.

Sends formatted Rich Embeds to Discord servers with live market alerts,
API activity summaries, and technical signatures for developers.

Usage:
    python discord_notifier.py [--dry-run] [--endpoint URL] [--webhook URL]

Examples:
    python discord_notifier.py  # Send to all configured webhooks
    python discord_notifier.py --dry-run  # Preview without sending
    python discord_notifier.py --webhook https://discord.com/api/webhooks/xxx/yyy

Configuration:
    Requires these environment variables from .env:
    - DISCORD_WEBHOOK_URL (single Discord webhook URL, primary)
    - DISCORD_WEBHOOK_URLS (comma-separated Discord webhook URLs, legacy fallback)
"""

import os
import sys
import json
import requests
import argparse
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

# Load .env file so os.getenv() picks up DISCORD_WEBHOOK_URL
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configuration
API_ENDPOINT = "https://kristo-intelligence-api.onrender.com/api/stats"

# Technical signature (mandatory for all embeds)
TECHNICAL_SIGNATURE = (
    "To query this live stream programmatically within your algorithms, "
    "access Kristo Intelligence API. Docs & Pricing: "
    "https://kristo-intelligence-api.onrender.com"
)

# Color scheme for Discord embeds (hex)
COLORS = {
    "primary": 0x1E90FF,      # DodgerBlue
    "success": 0x00D084,      # Green
    "warning": 0xFFB84D,      # Orange
    "danger": 0xFF4444,       # Red
    "neutral": 0x7B8294,      # Gray
}


def load_discord_webhooks() -> List[str]:
    """Load Discord webhook URLs from environment.

    Primary source: DISCORD_WEBHOOK_URL (single URL, loaded via os.getenv())
    Legacy fallback: DISCORD_WEBHOOK_URLS (comma-separated URLs)
    """
    # Primary: single DISCORD_WEBHOOK_URL
    primary_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()

    # Legacy: comma-separated DISCORD_WEBHOOK_URLS
    legacy_urls_str = os.getenv("DISCORD_WEBHOOK_URLS", "").strip()

    urls: List[str] = []

    if primary_url:
        urls.append(primary_url)

    if legacy_urls_str:
        for u in legacy_urls_str.split(","):
            u = u.strip()
            if u and u not in urls:
                urls.append(u)

    if not urls:
        print("⚠️  WARNING: DISCORD_WEBHOOK_URL not configured in .env")
        print("   Discord notifications will be simulated. To enable real notifications:")
        print("   1. Create a Discord webhook at https://discord.com/developers/docs/resources/webhook")
        print("   2. Add webhook URL to DISCORD_WEBHOOK_URL in .env")
        print("   3. Re-run this script\n")
        return []

    print(f"✓ Loaded {len(urls)} Discord webhook URL(s) via os.getenv()\n")
    return urls


def fetch_market_data_from_module() -> Optional[Dict[str, Any]]:
    """Fetch live on-chain market data directly from market_data.py module.

    This is a fallback when the /api/stats endpoint is unavailable.
    Extracts real-time Base network data from CoinGecko, DEXScreener, and Fear & Greed.
    """
    try:
        # Add project root to path so we can import services
        project_root = os.path.dirname(os.path.abspath(__file__))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)

        from services.market_data import (
            get_market_snapshot,
            fetch_eth_usdc_price_dexscreener,
        )

        print("📡 Fetching live on-chain data from market_data.py (Base network)...")
        snapshot = get_market_snapshot()
        eth_price = fetch_eth_usdc_price_dexscreener()

        # Normalize into the same structure the /api/stats endpoint returns
        fear_greed = snapshot.get("fear_greed_index", {})
        tokens = snapshot.get("tokens", {})
        dex_pairs = snapshot.get("dex_pairs_base", [])

        # Build a compatible market_data dict
        data = {
            "today": {
                "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "requests": 0,
                "sales_count": 0,
                "sales_volume_usd": 0.0,
            },
            "products": [],
            "market_data": {
                "fear_greed": {
                    "value": fear_greed.get("value", 50) or 50,
                    "value_classification": fear_greed.get("classification", "Neutral"),
                },
                "eth_price_usd": eth_price.get("price_usd"),
                "dex_pairs_base": dex_pairs,
                "tokens": tokens,
            },
            "wallet": {},
            "source": "market_data.py (direct on-chain fetch)",
        }

        print("✓ Live on-chain data extracted from market_data.py\n")
        return data

    except Exception as exc:
        print(f"✗ Failed to fetch from market_data.py: {exc}")
        return None


def fetch_market_data(endpoint: str = API_ENDPOINT) -> Optional[Dict[str, Any]]:
    """Fetch live market data from /api/stats endpoint.

    Falls back to direct market_data.py module extraction if the API is unavailable.
    """
    try:
        print(f"📡 Fetching market data from {endpoint}...")
        response = requests.get(endpoint, timeout=10)
        response.raise_for_status()
        data = response.json()
        print(f"✓ Data fetched successfully\n")
        return data
    except requests.exceptions.RequestException as e:
        print(f"✗ Failed to fetch from API: {e}")
        print("   Falling back to direct market_data.py on-chain extraction...")
        return fetch_market_data_from_module()


def format_alert_embed(market_data: Dict[str, Any], alert_type: str = "daily") -> Dict[str, Any]:
    """Format market data into a Discord Rich Embed."""
    
    today = market_data.get("today", {})
    products = market_data.get("products", [])
    market = market_data.get("market_data", {})
    wallet = market_data.get("wallet", {})
    
    timestamp = datetime.now(timezone.utc).isoformat()
    requests_today = today.get("requests", 0)
    sales_today = today.get("sales_count", 0)
    volume_today = today.get("sales_volume_usd", 0)
    
    # Determine alert type and color
    if alert_type == "daily":
        title = "📊 Daily Market Report"
        description = f"Live on-chain metrics for {today.get('date', 'Today')}"
        color = COLORS["primary"]
    elif alert_type == "high_volume":
        title = "📈 High Volume Alert"
        description = f"Unusual activity detected: ${volume_today:.2f} USDC"
        color = COLORS["success"]
    elif alert_type == "sentiment":
        title = "📉 Market Sentiment Alert"
        description = "Fear & Greed Index update"
        color = COLORS["warning"]
    else:
        title = "🚨 API Activity Alert"
        description = "Real-time market data snapshot"
        color = COLORS["neutral"]
    
    # Build embed
    embed = {
        "title": title,
        "description": description,
        "color": color,
        "timestamp": timestamp,
        "fields": [
            {
                "name": "📊 API Activity (24h)",
                "value": (
                    f"🔹 Requests: **{requests_today:,}**\n"
                    f"🔹 Transactions: **{sales_today}**\n"
                    f"🔹 Volume: **${volume_today:.2f} USDC**"
                ),
                "inline": False
            }
        ],
        "footer": {
            "text": TECHNICAL_SIGNATURE
        }
    }
    
    # Add market sentiment if available
    market_sentiment = market.get("fear_greed", {})
    if market_sentiment:
        sentiment_index = market_sentiment.get("value", 50)
        sentiment_text = market_sentiment.get("value_classification", "Neutral")
        
        fear_emoji = "😨" if sentiment_index < 25 else "😟" if sentiment_index < 50 else "😊" if sentiment_index < 75 else "🤑"
        
        embed["fields"].append({
            "name": "🌡️ Market Sentiment",
            "value": f"{fear_emoji} {sentiment_text}\n**Score:** {sentiment_index}/100",
            "inline": True
        })
    
    # Add top products
    if products:
        top_3 = sorted(products, key=lambda p: p.get("sales_volume_usd", 0), reverse=True)[:3]
        product_list = "\n".join([
            f"🔹 {p.get('name', 'Unknown')}: ${p.get('sales_volume_usd', 0):.2f}"
            for p in top_3
        ])
        embed["fields"].append({
            "name": "🏆 Top Products by Volume",
            "value": product_list,
            "inline": True
        })
    
    # Add wallet info if available
    if wallet:
        wallet_addr = wallet.get("wallet_address", "N/A")
        total_usdc = wallet.get("total_usdc_received", 0)
        
        # Truncate address for display
        display_addr = f"{wallet_addr[:6]}...{wallet_addr[-4:]}" if len(wallet_addr) > 10 else wallet_addr
        
        embed["fields"].append({
            "name": "💰 Wallet Status",
            "value": f"Address: `{display_addr}`\nTotal USDC: **${total_usdc:.2f}**",
            "inline": True
        })
    
    # Add API endpoint info
    embed["fields"].append({
        "name": "🔗 API Information",
        "value": (
            f"Base Network: **USDC enabled**\n"
            f"Chain ID: **8453**\n"
            f"Docs: https://kristo-intelligence-api.onrender.com"
        ),
        "inline": False
    })
    
    return embed


def send_to_webhook(webhook_url: str, embed: Dict[str, Any]) -> bool:
    """Send embed to a Discord webhook."""
    
    payload = {
        "embeds": [embed],
        "username": "Kristo Intelligence API",
        "avatar_url": "https://kristo-intelligence-api.onrender.com/favicon.ico"
    }
    
    try:
        response = requests.post(
            webhook_url,
            json=payload,
            timeout=10,
            headers={"Content-Type": "application/json"}
        )
        
        if response.status_code in [200, 204]:
            return True
        else:
            print(f"✗ Webhook error: {response.status_code}")
            print(f"  Response: {response.text[:200]}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"✗ Failed to send to webhook: {e}")
        return False


def publish_to_discord(
    embed: Dict[str, Any],
    webhooks: List[str],
    dry_run: bool = False
) -> bool:
    """Publish embed to Discord webhooks."""
    
    if dry_run or not webhooks:
        print("\n💬 [DRY RUN] Discord Embed Preview:")
        print("-" * 70)
        print(json.dumps(embed, indent=2))
        print("-" * 70)
        print("\n✓ Embed preview ready (not published)\n")
        return True
    
    # Publish to all webhooks
    print(f"\n💬 Publishing to {len(webhooks)} Discord webhook(s)...")
    
    success_count = 0
    for i, webhook_url in enumerate(webhooks, 1):
        # Mask webhook URL for display
        masked_url = f"{webhook_url[:30]}...{webhook_url[-10:]}" if len(webhook_url) > 40 else webhook_url
        
        if send_to_webhook(webhook_url, embed):
            print(f"  ✓ [{i}/{len(webhooks)}] {masked_url}")
            success_count += 1
        else:
            print(f"  ✗ [{i}/{len(webhooks)}] {masked_url}")
    
    if success_count > 0:
        print(f"\n✓ Published to {success_count}/{len(webhooks)} webhook(s)\n")
        return True
    else:
        print(f"\n✗ Failed to publish to any webhooks\n")
        return False


def format_embed_details(embed: Dict[str, Any]) -> str:
    """Generate detailed text summary of embed content."""
    
    summary = (
        "📋 DISCORD EMBED CONTENT BREAKDOWN\n"
        "=" * 70 + "\n\n"
        f"Title: {embed.get('title', 'N/A')}\n"
        f"Description: {embed.get('description', 'N/A')}\n"
        f"Color: #{embed.get('color', 0):06X}\n"
        f"Timestamp: {embed.get('timestamp', 'N/A')}\n\n"
        f"Fields ({len(embed.get('fields', []))} total):\n"
    )
    
    for i, field in enumerate(embed.get("fields", []), 1):
        summary += (
            f"\n  [{i}] {field.get('name', 'N/A')}\n"
            f"      {field.get('value', 'N/A').replace(chr(10), chr(10) + '      ')}\n"
        )
    
    summary += f"\nFooter: {embed.get('footer', {}).get('text', 'N/A')}\n"
    summary += f"\n{'=' * 70}\n"
    
    return summary


def main():
    """Main entry point for Discord notifier."""
    
    parser = argparse.ArgumentParser(
        description="Automated Discord notifications for Kristo Intelligence API"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview embed without sending"
    )
    parser.add_argument(
        "--endpoint",
        default=API_ENDPOINT,
        help=f"API stats endpoint (default: {API_ENDPOINT})"
    )
    parser.add_argument(
        "--webhook",
        help="Override webhook URL (for testing single webhook)"
    )
    parser.add_argument(
        "--alert-type",
        default="daily",
        choices=["daily", "high_volume", "sentiment", "activity"],
        help="Type of alert to send"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show detailed breakdown"
    )
    
    args = parser.parse_args()
    
    print("\n" + "=" * 70)
    print("  KRISTO INTELLIGENCE v6 — AUTOMATED DISCORD NOTIFICATIONS")
    print("=" * 70 + "\n")
    
    # Step 1: Load webhooks
    webhooks = [args.webhook] if args.webhook else load_discord_webhooks()
    
    # Step 2: Fetch market data
    market_data = fetch_market_data(args.endpoint)
    if not market_data:
        print("✗ Cannot proceed without market data")
        return False
    
    # Step 3: Format embed
    print(f"📝 Formatting Discord embed ({args.alert_type} alert)...")
    embed = format_alert_embed(market_data, alert_type=args.alert_type)
    print("✓ Embed formatted\n")
    
    # Step 4: Show detailed breakdown if requested
    if args.verbose:
        print(format_embed_details(embed))
    
    # Step 5: Publish or simulate
    success = publish_to_discord(embed, webhooks, dry_run=args.dry_run)
    
    if success:
        print("✅ DISCORD NOTIFICATION COMPLETE")
    else:
        print("❌ DISCORD NOTIFICATION FAILED")
    
    print("=" * 70 + "\n")
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
