import { test } from "node:test";
import assert from "node:assert/strict";

import {
  KristoX402Client,
  buildPaymentProof,
  buildPaymentSignatureHeader,
  parsePaymentChallenge,
  parsePaymentRequiredHeader,
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
          x402_amount: "5000",   // atomic, as the live server sends it
          x402_recipient: "0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f",
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
      JSON.stringify({ error: "payment_required", x402_amount: "5000",
                       x402_recipient: "0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f" }),
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

test("parsePaymentChallenge reads the 402 body and reports REAL USDC", () => {
  // The live server sends ATOMIC units here. main.py annotates the change:
  // "atomic units, as in accepts (was decimal)". The older fixture in this
  // file used the decimal form, so the test agreed with itself while the code
  // would have told a wallet to send 5000 USDC for a $0.005 call.
  const live = parsePaymentChallenge({
    error: "payment_required",
    x402_amount: "5000",
    x402_recipient: "0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f",
    x402_token_contract: "0x8335",
    x402_chain_id: 8453,
  });
  assert.deepEqual(live, {
    amount: 0.005,                     // human USDC, what a payer must send
    amountAtomic: "5000",              // what the server put on the wire
    recipient: "0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f",
    tokenContract: "0x8335",
    chainId: 8453,
  });

  // The v2 header agrees with the body it mirrors: 3000 atomic = 0.003.
  const cheaper = parsePaymentChallenge({
    error: "payment_required",
    payment: {
      amount_usdc: 3000,
      receiver_address: "0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f",
      token_contract: "0x8335",
      chain_id: 8453,
    },
  });
  assert.equal(cheaper.amount, 0.003);
  assert.equal(cheaper.amountAtomic, "3000");

  assert.equal(parsePaymentChallenge({ error: "other" }), null);
  assert.equal(parsePaymentChallenge({
    error: "payment_required", x402_amount: "0",
    x402_recipient: "0xabc",
  }), null);
});

test("a price is never OVERSTATED, whichever unit the server used", () => {
  // Overstating the price is the direction that costs money: a wallet told to
  // send 5000 USDC for a $0.005 call hands over 1000000x the price, and the
  // server's `amount >= price` check ACCEPTS it. Where the two readings could
  // disagree, the smaller must win.
  const atomic = parsePaymentChallenge({
    error: "payment_required", x402_amount: "5000",
    x402_recipient: "0xabc",
  });
  assert.equal(atomic.amount, 0.005);

  // A decimal from the older era is still read as the price it says.
  const decimal = parsePaymentChallenge({
    error: "payment_required", x402_amount: "0.005",
    x402_recipient: "0xabc",
  });
  assert.equal(decimal.amount, 0.005);
  assert.equal(decimal.amountAtomic, "5000");

  // Never more than the honest price, for either spelling.
  for (const value of ["5000", "0.005", 5000, 0.005]) {
    const parsed = parsePaymentChallenge({
      error: "payment_required", x402_amount: value,
      x402_recipient: "0xabc",
    });
    assert.ok(parsed.amount <= 0.005,
      `x402_amount=${JSON.stringify(value)} was read as ${parsed.amount}`);
  }
});

test("the v2 challenge and the legacy body never disagree about the price", () => {
  const header = parsePaymentRequiredHeader(v2ChallengeHeader());
  const body = parsePaymentChallenge({
    error: "payment_required",
    x402_amount: header.amountAtomic,       // same atomic string, as on the wire
    payment: { amount_usdc: Number(header.amountAtomic) },
    x402_recipient: header.recipient,
  });
  assert.equal(header.amount, 0.005);
  assert.equal(body.amount, header.amount);
  assert.equal(body.amountAtomic, header.amountAtomic);
});

test("client completes the full payment handshake (402 -> pay -> retry -> 200)", async () => {
  const saleTx = "0x" + "ab".repeat(32);
  const { calls, restore } = installMockFetch({ saleTx });
  try {
    const client = new KristoX402Client({
      pay: async ({ amount, amountAtomic, recipient }) => {
        // The callback is handed a REAL USDC price, not the atomic wire value.
        assert.equal(amount, 0.005);
        assert.equal(amountAtomic, "5000");
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
    assert.equal(result.paymentRequired.amount, 0.005);
    assert.equal(result.paymentRequired.amountAtomic, "5000");
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

// ── The standard x402 v2 rail ───────────────────────────────────────────────
//
// The v2 rail settles through a facilitator and unlocks in about two seconds.
// The smart-wallet rail this package used to be limited to waits for 3
// confirmations — roughly 6 seconds on Base. Both are supported; v2 is preferred.

/** Build a PAYMENT-REQUIRED header value shaped like the live one. */
function v2ChallengeHeader(overrides = {}) {
  const accepts = [{
    scheme: "exact",
    network: "eip155:8453",
    amount: "5000",
    payTo: "0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f",
    asset: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    maxTimeoutSeconds: 60,
    extra: { name: "USD Coin", version: "2" },
    ...overrides,
  }];
  return Buffer.from(JSON.stringify({
    x402Version: 2,
    error: "payment_required",
    accepts,
    resource: { url: "https://kristo-intelligence-api.onrender.com/api/stats" },
  }), "utf8").toString("base64").replace(/\+/g, "-").replace(/\//g, "_")
    .replace(/=+$/, "");
}

function decodeBase64url(value) {
  const normalised = value.replace(/-/g, "+").replace(/_/g, "/");
  const padding = normalised.length % 4
    ? "=".repeat(4 - (normalised.length % 4)) : "";
  return JSON.parse(Buffer.from(normalised + padding, "base64").toString("utf8"));
}

test("parsePaymentRequiredHeader decodes the standard v2 challenge", () => {
  const challenge = parsePaymentRequiredHeader(v2ChallengeHeader());
  assert.equal(challenge.rail, "v2");
  assert.equal(challenge.x402Version, 2);
  assert.equal(challenge.chainId, 8453);
  assert.equal(challenge.network, "eip155:8453");
  assert.equal(challenge.amountAtomic, "5000");
  // The header carries atomic units; a legacy-only signer needs a number.
  assert.equal(challenge.amount, 0.005);
  assert.equal(challenge.recipient, "0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f");
  assert.equal(challenge.tokenContract, "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913");
  assert.deepEqual(challenge.extra, { name: "USD Coin", version: "2" });
  assert.equal(challenge.accepted.amount, "5000");

  // Absent or garbage must return null so the caller can fall back.
  assert.equal(parsePaymentRequiredHeader(undefined), null);
  assert.equal(parsePaymentRequiredHeader(""), null);
  assert.equal(parsePaymentRequiredHeader("not-base64!!"), null);
  assert.equal(parsePaymentRequiredHeader(
    Buffer.from(JSON.stringify({ x402Version: 2, accepts: [] })).toString("base64")
  ), null);
});

test("buildPaymentSignatureHeader echoes the accepted terms", () => {
  const accepted = { scheme: "exact", network: "eip155:8453", amount: "5000" };
  const header = buildPaymentSignatureHeader({
    signature: "0xdeadbeef",
    authorization: { from: "0xabc", to: "0xdef", value: "5000" },
    accepted,
  });
  assert.ok(!header.includes("+") && !header.includes("/") && !header.includes("="));
  const decoded = decodeBase64url(header);
  assert.equal(decoded.x402Version, 2);
  assert.deepEqual(decoded.accepted, accepted);
  assert.equal(decoded.payload.signature, "0xdeadbeef");
  assert.equal(decoded.payload.authorization.value, "5000");
  assert.throws(() => buildPaymentSignatureHeader({ signature: "0x" }), TypeError);
});

test("client completes the v2 handshake and never waits for the slow rail", async () => {
  const originalFetch = globalThis.fetch;
  const seen = [];
  globalThis.fetch = async (url, init = {}) => {
    const signature =
      init.headers?.get?.("PAYMENT-SIGNATURE") ?? init.headers?.["PAYMENT-SIGNATURE"];
    seen.push({ url, signature });
    if (!signature) {
      return new Response(JSON.stringify({ error: "payment_required" }), {
        status: 402,
        headers: {
          "Content-Type": "application/json",
          "PAYMENT-REQUIRED": v2ChallengeHeader(),
        },
      });
    }
    return new Response(JSON.stringify({ ok: true, data: "signals" }),
      { status: 200, headers: { "Content-Type": "application/json" } });
  };
  try {
    let sawAccepted = null;
    const client = new KristoX402Client({
      pay: async (challenge) => {
        // The signer gets everything EIP-3009 needs, in atomic units.
        assert.equal(challenge.rail, "v2");
        assert.equal(challenge.amountAtomic, "5000");
        assert.equal(challenge.maxTimeoutSeconds, 60);
        sawAccepted = challenge.accepted;
        return {
          signature: "0x" + "ab".repeat(65),
          authorization: {
            from: "0x" + "11".repeat(20),
            to: challenge.recipient,
            value: challenge.amountAtomic,
          },
        };
      },
    });

    const result = await client.get("/api/stats");
    assert.equal(result.ok, true);
    assert.equal(result.data.data, "signals");
    assert.equal(seen.length, 2, "one challenge, one paid retry");
    assert.equal(seen[0].signature, undefined, "the first call must not pay");

    // What went on the wire must echo the server's own accept block.
    const sent = decodeBase64url(seen[1].signature);
    assert.deepEqual(sent.accepted, sawAccepted);
    assert.equal(sent.payload.authorization.value, "5000");

    // And it must NOT have used the 24-second legacy rail.
    const legacyHeader = sent && Object.keys(sent).includes("transaction_hash");
    assert.equal(legacyHeader, false);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("client prefers the v2 rail but still drives a legacy-only signer", async () => {
  const originalFetch = globalThis.fetch;
  const seen = [];
  globalThis.fetch = async (url, init = {}) => {
    const legacyProof =
      init.headers?.get?.("X-Payment-Proof") ?? init.headers?.["X-Payment-Proof"];
    seen.push({ legacyProof });
    if (!legacyProof) {
      // A server offering BOTH rails: the v2 header and the legacy body.
      return new Response(JSON.stringify({
        error: "payment_required",
        x402_amount: "5000",
        x402_recipient: "0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f",
        x402_chain_id: 8453,
      }), {
        status: 402,
        headers: {
          "Content-Type": "application/json",
          "PAYMENT-REQUIRED": v2ChallengeHeader(),
        },
      });
    }
    return new Response(JSON.stringify({ ok: true, data: "legacy-ok" }),
      { status: 200, headers: { "Content-Type": "application/json" } });
  };
  try {
    const txHash = "0x" + "cd".repeat(32);
    const client = new KristoX402Client({
      // A signer with no EIP-3009 support: it broadcasts a transfer instead.
      pay: async ({ amount }) => {
        assert.equal(amount, 0.005, "the v2 challenge still exposes a USDC number");
        return { payer: "0x" + "22".repeat(20), txHash };
      },
    });

    const result = await client.get("/api/stats");
    assert.equal(result.ok, true);
    assert.equal(result.data.data, "legacy-ok");

    const proof = decodeBase64url(seen[1].legacyProof);
    assert.equal(proof.transaction_hash, txHash.toLowerCase());
    assert.equal(proof.amount_usdc, 0.005);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("client re-sends the SAME credential through a 425 settlement window", async () => {
  const originalFetch = globalThis.fetch;
  let attempts = 0;
  const credentials = [];
  globalThis.fetch = async (url, init = {}) => {
    const signature =
      init.headers?.get?.("PAYMENT-SIGNATURE") ?? init.headers?.["PAYMENT-SIGNATURE"];
    credentials.push(signature);
    if (!signature) {
      return new Response(JSON.stringify({ error: "payment_required" }), {
        status: 402,
        headers: {
          "Content-Type": "application/json",
          "PAYMENT-REQUIRED": v2ChallengeHeader(),
        },
      });
    }
    attempts += 1;
    if (attempts < 3) {
      // "the payment is settling, re-send this same credential shortly"
      return new Response(JSON.stringify({ error: "settlement_in_flight" }),
        { status: 425, headers: { "Content-Type": "application/json" } });
    }
    return new Response(JSON.stringify({ ok: true, data: "settled" }),
      { status: 200, headers: { "Content-Type": "application/json" } });
  };
  try {
    let paid = 0;
    const client = new KristoX402Client({
      inFlightDelayMs: 1,
      pay: async () => {
        paid += 1;
        return {
          signature: "0x" + "ee".repeat(65),
          authorization: { from: "0x" + "33".repeat(20), value: "5000" },
        };
      },
    });

    const result = await client.get("/api/stats");
    assert.equal(result.ok, true);
    assert.equal(result.data.data, "settled");
    assert.equal(paid, 1, "a settling payment must not be paid for twice");

    // Every retry after the challenge carried the identical credential.
    const afterChallenge = credentials.filter(Boolean);
    assert.equal(afterChallenge.length, 3);
    assert.equal(new Set(afterChallenge).size, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("a repeated 402 never buys the same purchase twice", async () => {
  // The client used to call `pay()` on EVERY 402 round, so a server that
  // answered 402 after the first credential had already been broadcast was
  // handed a SECOND, independent authorization — the buyer paid twice. A 402
  // cannot say whether anything was broadcast, so the client must not sign
  // again; it reports the outcome as unknown instead.
  const originalFetch = globalThis.fetch;
  const credentials = [];
  globalThis.fetch = async (url, init = {}) => {
    const signature =
      init.headers?.get?.("PAYMENT-SIGNATURE") ?? init.headers?.["PAYMENT-SIGNATURE"];
    credentials.push(signature);
    // ALWAYS 402, even after a credential was presented.
    return new Response(JSON.stringify({ error: "payment_required" }), {
      status: 402,
      headers: {
        "Content-Type": "application/json",
        "PAYMENT-REQUIRED": v2ChallengeHeader(),
      },
    });
  };
  try {
    let paid = 0;
    const client = new KristoX402Client({
      pay: async () => {
        paid += 1;
        return {
          signature: "0x" + "ee".repeat(65),
          authorization: { from: "0x" + "33".repeat(20), value: "5000" },
        };
      },
    });

    const result = await client.get("/api/stats");
    assert.equal(result.ok, false);
    assert.equal(result.error, "payment_outcome_unknown");
    assert.equal(paid, 1, "the buyer must be charged at most once per request");
    assert.equal(credentials.filter(Boolean).length, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("client rejects a signer that returns neither rail's credential", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(
    JSON.stringify({ error: "payment_required" }), {
      status: 402,
      headers: {
        "Content-Type": "application/json",
        "PAYMENT-REQUIRED": v2ChallengeHeader(),
      },
    });
  try {
    const client = new KristoX402Client({ pay: async () => ({}) });
    await assert.rejects(() => client.get("/api/stats"), (error) => {
      assert.equal(error instanceof TypeError, true);
      assert.ok(error.message.includes("signature"));
      return true;
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});
