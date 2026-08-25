import { test } from "node:test";
import assert from "node:assert/strict";

import {
  KristoX402Client,
  buildPaymentProof,
  parsePaymentChallenge,
} from "../src/index.js";
import { createKristoTool } from "../src/langchain.js";

/** Decode an X-Payment-Proof header value back into its JSON payload. */
function decodeProof(proofHeader) {
  if (!proofHeader) return null;
  try {
    const b64 = proofHeader.replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(Buffer.from(b64, "base64").toString("utf8"));
  } catch {
    return null;
  }
}

/** Install a fake fetch that simulates the live x402 handshake. */
function installMockFetch({ saleTx }) {
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, init = {}) => {
    const proofHeader = init.headers?.get?.("X-Payment-Proof")
      ?? init.headers?.["X-Payment-Proof"];
    const decoded = decodeProof(proofHeader);
    calls.push({ url, proofHeader, decoded });

    if (String(url).endsWith("/api/stats") && !proofHeader) {
      return new Response(
        JSON.stringify({
          error: "payment_required",
          x402_network: "base-mainnet",
          x402_chain_id: 8453,
          x402_token: "USDC",
          x402_token_contract: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
          x402_amount: "0.05",
          x402_recipient: "0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f",
          x402_accepts: ["tx_hash"],
        }),
        { status: 402, headers: { "Content-Type": "application/json" } }
      );
    }

    // With a proof header: accept exactly the transaction we "paid" for.
    if (decoded && decoded.transaction_hash === saleTx) {
      return new Response(
        JSON.stringify({ ok: true, data: "market-intelligence" }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    // Unknown/replayed proof → server keeps the paywall up.
    return new Response(
      JSON.stringify({ error: "payment_required", x402_amount: "0.05",
                       x402_recipient: "0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f" }),
      { status: 402, headers: { "Content-Type": "application/json" } }
    );
  };
  return {
    calls,
    restore: () => { globalThis.fetch = originalFetch; },
  };
}

test("buildPaymentProof produces base64url JSON with server field names", () => {
  const proof = buildPaymentProof({
    payer: "0xAbCdEf0123456789012345678901234567890123",
    transactionHash: "0xDeadBeef" + "00".repeat(29),
    amountUsdc: 0.05,
  });
  assert.ok(!proof.includes("+") && !proof.includes("/") && !proof.includes("="));
  const decoded = JSON.parse(Buffer.from(proof, "base64").toString("utf8"));
  assert.equal(decoded.payer, "0xabcdef0123456789012345678901234567890123");
  assert.equal(decoded.transaction_hash.startsWith("0xdeadbeef"), true);
  assert.equal(decoded.amount_usdc, 0.05);
});

test("parsePaymentChallenge reads canonical x402_* fields", () => {
  const challenge = parsePaymentChallenge({
    error: "payment_required",
    x402_amount: "0.05",
    x402_recipient: "0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f",
    x402_token_contract: "0x8335",
    x402_chain_id: 8453,
  });
  assert.deepEqual(challenge, {
    amount: 0.05,
    recipient: "0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f",
    tokenContract: "0x8335",
    chainId: 8453,
  });
  assert.equal(parsePaymentChallenge({ error: "other" }), null);
});

test("client completes the full payment handshake (402 -> pay -> retry -> 200)", async () => {
  const saleTx = "0x" + "ab".repeat(32);
  const { calls, restore } = installMockFetch({ saleTx });
  try {
    const client = new KristoX402Client({
      pay: async ({ amount, recipient }) => {
        assert.equal(amount, 0.05);
        assert.ok(recipient.startsWith("0xd4cd"));
        return { payer: "0x" + "11".repeat(20), txHash: saleTx };
      },
    });

    const result = await client.get("/api/stats");
    assert.equal(result.ok, true);
    assert.equal(result.status, 200);
    assert.equal(result.data.data, "market-intelligence");

    // Two requests: initial (no proof) + retry (with proof).
    assert.equal(calls.length, 2);
    assert.equal(calls[0].proofHeader, undefined);
    assert.ok(calls[1].proofHeader.length > 20);
  } finally {
    restore();
  }
});

test("dry-run mode returns the payment challenge without paying", async () => {
  const saleTx = "0x" + "cd".repeat(32);
  const { calls, restore } = installMockFetch({ saleTx });
  try {
    const inspector = new KristoX402Client({ autoPay: false });
    const result = await inspector.get("/api/stats");

    assert.equal(result.status, 402);
    assert.equal(result.paymentRequired.amount, 0.05);
    assert.equal(result.paymentRequired.chainId, 8453);
    assert.equal(calls.length, 1); // no retry, no payment
  } finally {
    restore();
  }
});

test("client requires a pay callback unless autoPay is false", () => {
  assert.throws(() => new KristoX402Client(), TypeError);
  assert.doesNotThrow(() => new KristoX402Client({ autoPay: false }));
});

test("LangChain tool factory binds an endpoint and forwards results", async () => {
  const saleTx = "0x" + "ef".repeat(32);
  const { restore } = installMockFetch({ saleTx });
  try {
    const client = new KristoX402Client({
      pay: async () => ({ payer: "0x" + "22".repeat(20), txHash: saleTx }),
    });
    const tool = createKristoTool({
      client,
      path: "/api/stats",
      name: "kristo_market_stats",
    });

    assert.equal(tool.name, "kristo_market_stats");
    assert.ok(tool.description.includes("x402"));
    assert.deepEqual(tool.schema.properties, {});
    const out = JSON.parse(await tool.func({}));
    assert.equal(out.data, "market-intelligence");
  } finally {
    restore();
  }
});
