#!/usr/bin/env node
/**
 * Kristo Intelligence x402 client example — a complete, working Base Mainnet flow.
 * ========================================
 *
 * The server accepts TWO rails. This script drives both; the standard one is
 * the default because it settles in about two seconds instead of about
 * twenty-four.
 *
 *   STANDARD RAIL (default) — x402 v2, EIP-3009
 *     1. Request a paid endpoint.
 *     2. Read the base64url `PAYMENT-REQUIRED` response header.
 *     3. Sign a TransferWithAuthorization with the bot wallet — no gas, no
 *        broadcast; the facilitator submits it.
 *     4. Retry with the `PAYMENT-SIGNATURE` header.
 *     5. HTTP 200 + data.       (~2 seconds)
 *
 *   LEGACY RAIL (X402_RAIL=legacy)
 *     1. Request a paid endpoint.
 *     2. Read the `payment` block from the 402 body.
 *     3. Sign and broadcast a plain ERC-20 USDC transfer on Base.
 *     4. Wait for 12 confirmations — the server enforces this.
 *     5. Retry with the `X-Payment-Proof` header.
 *     6. HTTP 200 + data.       (~24 seconds)
 *
 * BOTH rails are real and both are verified server-side. The paywall checks
 * the signed authorization (standard) or decodes the ERC-20 Transfer event of
 * the named transaction (legacy), and both unlock exactly one call.
 *
 * Install for external bots:
 *   npm install viem
 *
 * Run (standard rail):
 *   X402_API_BASE=https://kristo-intelligence-api.onrender.com \
 *   X402_PRIVATE_KEY=0xYOUR_BOT_WALLET_PRIVATE_KEY \
 *   node docs/x402-client-example.js
 *
 * Run (legacy rail):
 *   X402_RAIL=legacy X402_PRIVATE_KEY=0x... node docs/x402-client-example.js
 *
 * SECURITY:
 *   - Use a dedicated low-balance bot wallet.
 *   - Put the private key in a secret manager or process environment.
 *   - Never commit X402_PRIVATE_KEY or print it in logs.
 *
 * On the standard rail the payer needs NO Base ETH: signing is free. Only the
 * legacy rail broadcasts a transaction and therefore needs gas.
 */

import { randomBytes } from "node:crypto";

import {
  createPublicClient,
  createWalletClient,
  http,
  isAddress,
} from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { base } from "viem/chains";

const BASE_CHAIN_ID = 8453;
const DEFAULT_API_BASE = "https://kristo-intelligence-api.onrender.com";
const DEFAULT_ENDPOINT = "/api/v1/signal";
const USDC_DECIMALS = 6;

const STANDARD_HEADER = "PAYMENT-SIGNATURE";
const CHALLENGE_HEADER = "PAYMENT-REQUIRED";
const LEGACY_HEADER = "X-Payment-Proof";

const ERC20_TRANSFER_ABI = [
  {
    type: "function",
    name: "transfer",
    stateMutability: "nonpayable",
    inputs: [
      { name: "to", type: "address" },
      { name: "value", type: "uint256" },
    ],
    outputs: [{ name: "success", type: "bool" }],
  },
];

const EIP3009_TYPES = {
  TransferWithAuthorization: [
    { name: "from", type: "address" },
    { name: "to", type: "address" },
    { name: "value", type: "uint256" },
    { name: "validAfter", type: "uint256" },
    { name: "validBefore", type: "uint256" },
    { name: "nonce", type: "bytes32" },
  ],
};

function requiredEnv(name) {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`Missing ${name}. Store it in your secret manager, not in source.`);
  }
  return value;
}

function decodeChallengeHeader(headerValue) {
  if (!headerValue) return null;
  const normalised = headerValue.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalised + "=".repeat((4 - (normalised.length % 4)) % 4);
  try {
    return JSON.parse(Buffer.from(padded, "base64").toString("utf8"));
  } catch {
    return null;
  }
}

async function readJson(response) {
  const text = await response.text();
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { raw: text };
  }
}

function assertBaseNetwork(chainId, network) {
  if (chainId !== BASE_CHAIN_ID) {
    throw new Error(`Refusing to pay on chain ${chainId}; expected Base ${BASE_CHAIN_ID}.`);
  }
  if (network && !String(network).endsWith(String(BASE_CHAIN_ID))) {
    throw new Error(`Refusing to pay on network ${network}; expected eip155:${BASE_CHAIN_ID}.`);
  }
}

// ── STANDARD RAIL (x402 v2 / EIP-3009) ──────────────────────────────────────

function readStandardChallenge(response, body) {
  const decoded = decodeChallengeHeader(response.headers.get(CHALLENGE_HEADER));
  const accepts = decoded?.accepts;
  if (!Array.isArray(accepts) || accepts.length === 0) return null;
  const accepted = accepts.find((entry) => entry?.payTo && entry?.asset) ?? accepts[0];
  if (!accepted?.payTo || !accepted?.asset || accepted.amount === undefined) {
    return null;
  }
  return { decoded, accepted };
}

async function payStandard(account, { accepted, decoded }, endpointUrl) {
  const chainId = Number(
    (accepted.network ?? "").split(":").pop() || accepted.chainId || BASE_CHAIN_ID
  );
  assertBaseNetwork(chainId, accepted.network);

  if (!isAddress(accepted.payTo) || !isAddress(accepted.asset)) {
    throw new Error(`Invalid payTo/asset in the challenge: ${JSON.stringify(accepted)}`);
  }

  const now = Math.floor(Date.now() / 1000);
  const maxTimeout = Number(accepted.maxTimeoutSeconds ?? 60);
  const authorization = {
    from: account.address,
    to: accepted.payTo,
    value: String(accepted.amount),
    validAfter: String(now - 60),
    validBefore: String(now + Math.max(1, maxTimeout - 5)),
    nonce: "0x" + randomBytes(32).toString("hex"),
  };

  // Signing costs nothing and needs no Base ETH — the facilitator submits it.
  const signature = await account.signTypedData({
    domain: {
      name: accepted.extra?.name ?? "USD Coin",
      version: accepted.extra?.version ?? "2",
      chainId,
      verifyingContract: accepted.asset,
    },
    types: EIP3009_TYPES,
    primaryType: "TransferWithAuthorization",
    message: authorization,
  });

  const payload = {
    x402Version: Number(decoded?.x402Version ?? 2),
    accepted,
    payload: { signature, authorization },
  };
  return Buffer.from(JSON.stringify(payload), "utf8").toString("base64url");
}

// ── LEGACY RAIL (plain ERC-20 transfer + X-Payment-Proof) ───────────────────

/**
 * Interpret `payment.amount_usdc` in EITHER unit, safely.
 *
 * THE FIELD NAME LIES. On the live server it is ATOMIC units: a $0.005 call
 * arrives as `amount_usdc: 5000`. It was a DECIMAL in an earlier release
 * (`main.py` annotates the change: "atomic units, as in accepts (was decimal)").
 *
 * The original version of this file did `parseUnits(String(amount_usdc), 6)`,
 * which turns 5000 into 5,000,000,000 atomic units — a 5000 USDC transfer for a
 * $0.005 call. The server compares the decoded on-chain amount against the price
 * with `>=`, so it would have ACCEPTED that transfer and kept the money.
 *
 * A value with a decimal point is therefore taken as human USDC and a bare
 * integer as atomic. Where the two readings could disagree, the smaller one
 * wins: understating the price costs a rejected call (HTTP 401, nothing moves),
 * overstating it costs the payer's balance.
 */
function toAtomicString(raw) {
  const text = String(raw).trim();
  if (text.includes(".")) {
    const asNumber = Number(text);
    if (!Number.isFinite(asNumber) || asNumber <= 0) return null;
    return String(Math.round(asNumber * 10 ** USDC_DECIMALS));
  }
  return text;
}

/** True for Base, however the server spells it (CAIP-2 today, plain before). */
function isBaseNetwork(network) {
  const text = String(network ?? "").trim().toLowerCase();
  return text === "base" || text === "base-mainnet" || text === "eip155:8453";
}

function assertLegacyRequirement(body) {
  const payment = body?.payment;
  if (body?.error !== "payment_required" || !payment) {
    throw new Error(`Expected an x402 payment requirement, received: ${JSON.stringify(body)}`);
  }
  if (payment.chain_id !== BASE_CHAIN_ID) {
    throw new Error(
      `Refusing to pay on chain ${payment.chain_id}; expected Base ${BASE_CHAIN_ID}.`);
  }
  // The live challenge uses the canonical CAIP-2 string "eip155:8453". Older
  // releases sent "base" / "base-mainnet", so accept those too — but do not
  // reject CAIP-2, which is what an earlier version of THIS FILE did, making
  // the legacy rail throw before it could ever pay.
  if (payment.network !== undefined && payment.network !== null &&
      !isBaseNetwork(payment.network)) {
    throw new Error(`Refusing to pay on a non-Base network: ${payment.network}`);
  }
  for (const field of ["token_contract", "receiver_address", "amount_usdc"]) {
    if (payment[field] === undefined || payment[field] === null) {
      throw new Error(`402 response is missing payment.${field}`);
    }
  }
  if (!isAddress(payment.token_contract) || !isAddress(payment.receiver_address)) {
    throw new Error(`Invalid token or receiver address: ${JSON.stringify(payment)}`);
  }
  const amountAtomic = toAtomicString(payment.amount_usdc);
  if (amountAtomic === null || !/^\d+$/.test(amountAtomic) || BigInt(amountAtomic) <= 0n) {
    throw new Error(`Refusing to send a non-positive amount: ${payment.amount_usdc}`);
  }
  return { payment, amountAtomic };
}

async function payLegacy(account, payment, amountAtomic, rpcUrl) {
  const transport = http(rpcUrl);
  const publicClient = createPublicClient({ chain: base, transport });
  const walletClient = createWalletClient({ account, chain: base, transport });

  const chainId = await publicClient.getChainId();
  assertBaseNetwork(chainId, "eip155:8453");

  // amountAtomic is already in atomic units — do NOT multiply it again.
  const transactionHash = await walletClient.writeContract({
    address: payment.token_contract,
    abi: ERC20_TRANSFER_ABI,
    functionName: "transfer",
    args: [payment.receiver_address, BigInt(amountAtomic)],
  });

  const receipt = await publicClient.waitForTransactionReceipt({ hash: transactionHash });
  if (receipt.status !== "success") {
    throw new Error(`USDC transfer reverted: ${transactionHash}`);
  }

  // The server reads payer/transaction_hash and IGNORES amount_usdc — it
  // decodes the on-chain Transfer event itself and never trusts a claimed
  // amount, so this field cannot be used to underpay. We send the human USDC
  // value because the only remaining reader is a person looking at the header,
  // and `amount_usdc: 0.005` is unambiguous where `5000` is not.
  const proof = {
    payer: account.address.toLowerCase(),
    transaction_hash: transactionHash.toLowerCase(),
    amount_usdc: Number(amountAtomic) / 10 ** USDC_DECIMALS,
  };
  return {
    header: LEGACY_HEADER,
    value: Buffer.from(JSON.stringify(proof), "utf8").toString("base64url"),
    transactionHash,
    amountAtomic,
  };
}

// ── main ────────────────────────────────────────────────────────────────────

async function main() {
  const apiBase = process.env.X402_API_BASE?.trim() || DEFAULT_API_BASE;
  const endpoint = process.env.X402_ENDPOINT?.trim() || DEFAULT_ENDPOINT;
  const rpcUrl = process.env.BASE_RPC_URL?.trim() || "https://mainnet.base.org";
  const rail = (process.env.X402_RAIL?.trim() || "standard").toLowerCase();
  const privateKey = requiredEnv("X402_PRIVATE_KEY");
  const account = privateKeyToAccount(privateKey);
  const url = new URL(endpoint, apiBase).toString();

  console.log(`Requesting ${url}`);

  let response = await fetch(url, { headers: { Accept: "application/json" } });
  let body = await readJson(response);

  if (response.status !== 402) {
    if (!response.ok) {
      throw new Error(`Initial request failed with HTTP ${response.status}: ${JSON.stringify(body)}`);
    }
    console.log("Endpoint was available without payment:");
    console.log(JSON.stringify(body, null, 2));
    return;
  }

  let credential;

  if (rail === "legacy") {
    const { payment, amountAtomic } = assertLegacyRequirement(body);
    console.log(
      `402 received: legacy rail — paying ${amountAtomic} atomic USDC ` +
      `(${Number(amountAtomic) / 10 ** USDC_DECIMALS} USDC) on Base ` +
      `to ${payment.receiver_address} (this waits for 12 confirmations, ~24s)`
    );
    credential = await payLegacy(account, payment, amountAtomic, rpcUrl);
    console.log(`Payment confirmed in ${credential.transactionHash}`);
  } else {
    const challenge = readStandardChallenge(response, body);
    if (!challenge) {
      throw new Error(
        "This endpoint returned no PAYMENT-REQUIRED header, so the standard x402 " +
        "rail is unavailable here. Re-run with X402_RAIL=legacy to use a plain " +
        `ERC-20 transfer instead. Server response: ${JSON.stringify(body)}`
      );
    }
    const { accepted } = challenge;
    console.log(
      `402 received: standard rail — authorising ${accepted.amount} atomic USDC ` +
      `(${Number(accepted.amount) / 10 ** USDC_DECIMALS} USDC) to ${accepted.payTo}`
    );
    credential = {
      header: STANDARD_HEADER,
      value: await payStandard(account, challenge, url),
    };
    console.log("Authorization signed (no gas spent, nothing broadcast by us)");
  }

  console.log(`Retrying with ${credential.header}`);
  response = await fetch(url, {
    headers: { Accept: "application/json", [credential.header]: credential.value },
  });
  body = await readJson(response);

  // 425 means the settlement is still confirming. The correct move is to
  // re-send the SAME credential shortly — never to pay again, because the
  // authorization nonce is one-time-use.
  for (let attempt = 0; response.status === 425 && attempt < 5; attempt++) {
    console.log("425 settlement_in_flight — re-sending the same credential");
    await new Promise((resolve) => setTimeout(resolve, 1500));
    response = await fetch(url, {
      headers: { Accept: "application/json", [credential.header]: credential.value },
    });
    body = await readJson(response);
  }

  if (response.status === 402) {
    throw new Error(
      "Payment was presented but the server still asks for payment. Do NOT pay " +
      "again: the same credential is being re-sent above, and a second payment " +
      `would be a second charge. Server response: ${JSON.stringify(body)}`
    );
  }
  if (response.status === 401) {
    throw new Error(
      `The credential was unusable: ${JSON.stringify(body)}. The server names the ` +
      "exact cause in `reason` — fix that rather than paying again."
    );
  }
  if (!response.ok) {
    throw new Error(`Paid retry failed with HTTP ${response.status}: ${JSON.stringify(body)}`);
  }

  console.log("Payment accepted; response:");
  console.log(JSON.stringify(body, null, 2));
}

main().catch((error) => {
  console.error(`x402 client error: ${error.message}`);
  process.exitCode = 1;
});
