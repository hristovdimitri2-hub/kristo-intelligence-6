#!/usr/bin/env node
/**
 * register_bazaar.js
 * ==================
 * Registers the Kristo Intelligence API with the x402 Bazaar / Coinbase catalog.
 *
 * Sends a ping with our service metadata, x402 payment details, and discovery
 * endpoints so AI agents can find and pay for our API.
 *
 * Usage:
 *   node scripts/register_bazaar.js
 *
 * Environment variables (optional):
 *   API_BASE_URL       — Override the default production URL
 *   BAZAAR_REGISTRY_URL — Override the Bazaar registry endpoint
 */

"use strict";

const https = require("https");
const http = require("http");

// ── Configuration ───────────────────────────────────────────────────────────

const API_BASE_URL =
  process.env.API_BASE_URL || "https://kristo-intelligence-v5.onrender.com";

// x402 Bazaar / Coinbase catalog registry endpoint.
// This is the public ping endpoint for the x402 Bazaar directory.
const BAZAAR_REGISTRY_URL =
  process.env.BAZAAR_REGISTRY_URL ||
  "https://bazaar.x402.org/api/register";

// Service metadata
const SERVICE = {
  name: "Kristo Intelligence API",
  version: "5.0.0",
  description:
    "AI-powered DeFi trading signals and crypto market intelligence on Base. " +
    "Pay-per-call with USDC via x402 protocol.",
  base_url: API_BASE_URL,
  protocol: "x402",
  payment: {
    chain: "base",
    chain_id: 8453,
    currency: "USDC",
    token_contract: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    receiver_address: "0xd4cdA980839C8FED4374EE37EA8DBE8c4ECfd88f",
    price_per_call_usdc: 0.10,
    free_tier_limit: 1,
    monthly_vip_usdc: 29.00,
  },
  endpoints: {
    paid: [
      { path: "/api/stats", method: "GET", cost_usdc: 0.10, description: "Market activity and daily stats" },
      { path: "/api/sales", method: "GET", cost_usdc: 0.10, description: "Real on-chain sales history" },
      { path: "/api/bot-status", method: "GET", cost_usdc: 0.10, description: "Telegram bot status" },
    ],
    free: [
      { path: "/.well-known/x402.json", method: "GET", cost_usdc: 0.0, description: "x402 discovery file" },
      { path: "/openapi.json", method: "GET", cost_usdc: 0.0, description: "OpenAPI 3.0 specification" },
      { path: "/llms.txt", method: "GET", cost_usdc: 0.0, description: "LLM-friendly API description" },
      { path: "/api/mcp/manifest", method: "GET", cost_usdc: 0.0, description: "MCP/x402 manifest" },
      { path: "/health", method: "GET", cost_usdc: 0.0, description: "Health check" },
    ],
  },
  discovery: {
    x402: `${API_BASE_URL}/.well-known/x402.json`,
    openapi: `${API_BASE_URL}/openapi.json`,
    llms_txt: `${API_BASE_URL}/llms.txt`,
    mcp_manifest: `${API_BASE_URL}/api/mcp/manifest`,
  },
  registered_at: new Date().toISOString(),
};

// ── HTTP request helper ─────────────────────────────────────────────────────

function sendRequest(url, data) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify(data);
    const parsed = new URL(url);
    const isHttps = parsed.protocol === "https:";
    const lib = isHttps ? https : http;

    const options = {
      hostname: parsed.hostname,
      port: parsed.port || (isHttps ? 443 : 80),
      path: parsed.pathname + parsed.search,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Content-Length": Buffer.byteLength(body),
        "User-Agent": "kristo-intelligence-v5/register-bazaar",
      },
      timeout: 30000,
    };

    const req = lib.request(options, (res) => {
      let responseBody = "";
      res.on("data", (chunk) => (responseBody += chunk));
      res.on("end", () => {
        resolve({
          statusCode: res.statusCode,
          headers: res.headers,
          body: responseBody,
        });
      });
    });

    req.on("error", reject);
    req.on("timeout", () => {
      req.destroy();
      reject(new Error("Request timed out after 30s"));
    });

    req.write(body);
    req.end();
  });
}

// ── Self-health check ──────────────────────────────────────────────────────

async function selfHealthCheck() {
  return new Promise((resolve) => {
    const parsed = new URL(`${API_BASE_URL}/health`);
    const isHttps = parsed.protocol === "https:";
    const lib = isHttps ? https : http;

    const req = lib.get(
      {
        hostname: parsed.hostname,
        port: parsed.port || (isHttps ? 443 : 80),
        path: parsed.pathname,
        headers: { "User-Agent": "kristo-intelligence-v5/register-bazaar" },
        timeout: 15000,
      },
      (res) => {
        let body = "";
        res.on("data", (chunk) => (body += chunk));
        res.on("end", () => {
          resolve({ ok: res.statusCode === 200, statusCode: res.statusCode, body });
        });
      }
    );

    req.on("error", () => resolve({ ok: false, error: "health check failed" }));
    req.on("timeout", () => {
      req.destroy();
      resolve({ ok: false, error: "health check timed out" });
    });
  });
}

// ── Main ───────────────────────────────────────────────────────────────────

async function main() {
  console.log("╔══════════════════════════════════════════════════════════════╗");
  console.log("║  x402 Bazaar Registration — Kristo Intelligence API v5     ║");
  console.log("╚══════════════════════════════════════════════════════════════╝");
  console.log();

  console.log(`  Service:     ${SERVICE.name} v${SERVICE.version}`);
  console.log(`  Base URL:    ${API_BASE_URL}`);
  console.log(`  Receiver:    ${SERVICE.payment.receiver_address}`);
  console.log(`  Price:       $${SERVICE.payment.price_per_call_usdc} USDC/call`);
  console.log(`  Free tier:   ${SERVICE.payment.free_tier_limit} call(s)`);
  console.log(`  Registry:    ${BAZAAR_REGISTRY_URL}`);
  console.log();

  // Step 1: Self-health check
  console.log("  [1/3] Performing self-health check...");
  const health = await selfHealthCheck();
  if (health.ok) {
    console.log(`       ✅ Health check passed (HTTP ${health.statusCode})`);
  } else {
    console.log(`       ⚠️  Health check failed — ${health.error || health.statusCode}`);
    console.log("       Continuing registration anyway (service may be starting up)...");
  }
  console.log();

  // Step 2: Register with Bazaar
  console.log("  [2/3] Registering with x402 Bazaar catalog...");
  try {
    const response = await sendRequest(BAZAAR_REGISTRY_URL, SERVICE);

    if (response.statusCode >= 200 && response.statusCode < 300) {
      console.log(`       ✅ Registration successful (HTTP ${response.statusCode})`);
      try {
        const parsed = JSON.parse(response.body);
        if (parsed.id || parsed.service_id || parsed.status) {
          console.log(`       Service ID: ${parsed.id || parsed.service_id || "N/A"}`);
          console.log(`       Status: ${parsed.status || "registered"}`);
        }
      } catch {
        console.log(`       Response: ${response.body.substring(0, 200)}`);
      }
    } else if (response.statusCode === 404 || response.statusCode === 0) {
      console.log(`       ⚠️  Registry endpoint not reachable (HTTP ${response.statusCode})`);
      console.log("       This is expected if the Bazaar catalog is not yet live.");
      console.log("       The service metadata has been prepared for when it is.");
    } else {
      console.log(`       ⚠️  Registration returned HTTP ${response.statusCode}`);
      console.log(`       Response: ${response.body.substring(0, 300)}`);
    }
  } catch (err) {
    console.log(`       ⚠️  Registration request failed: ${err.message}`);
    console.log("       The service is ready for discovery via .well-known/x402.json regardless.");
  }
  console.log();

  // Step 3: Summary
  console.log("  [3/3] Registration ping complete.");
  console.log();
  console.log("  ── Discovery Endpoints ──────────────────────────────────");
  console.log(`  x402:       ${SERVICE.discovery.x402}`);
  console.log(`  OpenAPI:    ${SERVICE.discovery.openapi}`);
  console.log(`  LLMs:       ${SERVICE.discovery.llms_txt}`);
  console.log(`  MCP:        ${SERVICE.discovery.mcp_manifest}`);
  console.log();
  console.log("  ── Payment Details ──────────────────────────────────────");
  console.log(`  Chain:      Base (8453)`);
  console.log(`  Token:      USDC (${SERVICE.payment.token_contract})`);
  console.log(`  Receiver:   ${SERVICE.payment.receiver_address}`);
  console.log(`  Price:      $${SERVICE.payment.price_per_call_usdc} USDC per call`);
  console.log(`  VIP:        $${SERVICE.payment.monthly_vip_usdc} USDC / month`);
  console.log();
  console.log("  ✅ Done. AI agents can discover this service via the endpoints above.");
}

main().catch((err) => {
  console.error("Fatal error:", err);
  process.exit(1);
});