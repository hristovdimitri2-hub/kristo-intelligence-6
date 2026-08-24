#!/usr/bin/env node
/**
 * Kristo Intelligence x402 client example
 * ========================================
 *
 * This is a complete Base Mainnet client flow:
 *   1. Request a paid endpoint.
 *   2. Parse the HTTP 402 payment requirement.
 *   3. Sign and broadcast an ERC-20 USDC transfer on Base.
 *   4. Wait for the transaction receipt.
 *   5. Retry with a request-bound X-Payment-Proof header.
 *
 * Install for external bots:
 *   npm install viem
 *
 * Run:
 *   X402_API_BASE=https://kristo-intelligence-v-6.replit.app \
 *   X402_PRIVATE_KEY=0xYOUR_BOT_WALLET_PRIVATE_KEY \
 *   node docs/x402-client-example.js
 *
 * SECURITY:
 *   - Use a dedicated low-balance bot wallet.
 *   - Put the private key in a secret manager or process environment.
 *   - Never commit X402_PRIVATE_KEY or print it in logs.
 *
 * IMPORTANT FOR THE CURRENT SERVICE:
 *   The current Kristo v6 deployment advertises settlement_status=discovery_only.
 *   It emits the 402 requirement and this script creates a valid Base USDC
 *   transaction, but the current server does not yet verify request-bound
 *   payment proofs in the paywall. The retry is still included because it is
 *   the exact client-side contract needed once the facilitator/settlement
 *   task is enabled. Until then, the script reports the server's 402 response
 *   instead of falsely claiming that payment was accepted.
 *
 * PAYMENT PROOF FORMAT USED HERE:
 *   X-Payment-Proof: base64url(JSON.stringify({
 *     x402_version, scheme, network, chain_id, token_contract,
 *     payer, receiver_address, amount_usdc, amount_atomic,
 *     transaction_hash, block_number
 *   }))
 *
 * If the facilitator selects the standardized PAYMENT-SIGNATURE header,
 * set X402_PAYMENT_PROOF_HEADER=PAYMENT-SIGNATURE. The header name is
 * intentionally configurable because the current discovery-only server does
 * not consume either proof header yet.
 */

import {
  createPublicClient,
  createWalletClient,
  http,
  isAddress,
  parseUnits,
} from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { base } from "viem/chains";

const BASE_CHAIN_ID = 8453;
const DEFAULT_API_BASE = "https://kristo-intelligence-v-6.replit.app";
const DEFAULT_ENDPOINT = "/api/stats";
const DEFAULT_PROOF_HEADER = "X-Payment-Proof";
const USDC_DECIMALS = 6;

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

function requiredEnv(name) {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`Missing ${name}. Store it in your secret manager, not in source.`);
  }
  return value;
}

function encodePaymentProof(proof) {
  return Buffer.from(JSON.stringify(proof), "utf8").toString("base64url");
}

async function readJson(response) {
  const text = await response.text();
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    return { raw: text };
  }
}

function assertPaymentRequirement(requirement) {
  const payment = requirement?.payment;
  if (requirement?.error !== "payment_required" || !payment) {
    throw new Error(`Expected an x402 payment requirement, received: ${JSON.stringify(requirement)}`);
  }
  if (payment.chain_id !== BASE_CHAIN_ID || payment.network !== "base") {
    throw new Error(`Refusing to pay on a non-Base network: ${JSON.stringify(payment)}`);
  }
  for (const field of ["token_contract", "receiver_address", "amount_usdc"]) {
    if (payment[field] === undefined || payment[field] === null) {
      throw new Error(`402 response is missing payment.${field}`);
    }
  }
  if (!isAddress(payment.token_contract) || !isAddress(payment.receiver_address)) {
    throw new Error(`402 response contains an invalid token or receiver address: ${JSON.stringify(payment)}`);
  }
  if (Number(payment.amount_usdc) <= 0) {
    throw new Error(`Refusing to send a non-positive amount: ${payment.amount_usdc}`);
  }
  return payment;
}

async function signAndSendUsdcTransfer(payment, privateKey, rpcUrl) {
  const account = privateKeyToAccount(privateKey);
  const transport = http(rpcUrl);
  const publicClient = createPublicClient({ chain: base, transport });
  const walletClient = createWalletClient({ account, chain: base, transport });

  const chainId = await publicClient.getChainId();
  if (chainId !== BASE_CHAIN_ID) {
    throw new Error(`RPC returned chain ID ${chainId}; expected Base Mainnet ${BASE_CHAIN_ID}.`);
  }

  const amountAtomic = parseUnits(String(payment.amount_usdc), USDC_DECIMALS);

  // viem signs the transaction with the bot wallet and broadcasts it to Base.
  const transactionHash = await walletClient.writeContract({
    address: payment.token_contract,
    abi: ERC20_TRANSFER_ABI,
    functionName: "transfer",
    args: [payment.receiver_address, amountAtomic],
  });

  const receipt = await publicClient.waitForTransactionReceipt({
    hash: transactionHash,
  });
  if (receipt.status !== "success") {
    throw new Error(`USDC payment transaction was not successful: ${transactionHash}`);
  }

  return {
    account,
    transactionHash,
    blockNumber: receipt.blockNumber.toString(),
    amountAtomic: amountAtomic.toString(),
  };
}

function buildPaymentProof(payment, transfer) {
  return {
    x402_version: "1.0",
    scheme: "exact",
    network: "base",
    chain_id: BASE_CHAIN_ID,
    token_contract: payment.token_contract,
    payer: transfer.account.address,
    receiver_address: payment.receiver_address,
    amount_usdc: String(payment.amount_usdc),
    amount_atomic: transfer.amountAtomic,
    transaction_hash: transfer.transactionHash,
    block_number: transfer.blockNumber,
  };
}

async function main() {
  const apiBase = process.env.X402_API_BASE?.trim() || DEFAULT_API_BASE;
  const endpoint = process.env.X402_ENDPOINT?.trim() || DEFAULT_ENDPOINT;
  const rpcUrl = process.env.BASE_RPC_URL?.trim() || "https://mainnet.base.org";
  const proofHeader = process.env.X402_PAYMENT_PROOF_HEADER?.trim() || DEFAULT_PROOF_HEADER;
  const privateKey = requiredEnv("X402_PRIVATE_KEY");
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

  const payment = assertPaymentRequirement(body);
  console.log(`402 received: paying ${payment.amount_usdc} USDC on Base to ${payment.receiver_address}`);

  const transfer = await signAndSendUsdcTransfer(payment, privateKey, rpcUrl);
  const proof = buildPaymentProof(payment, transfer);
  const encodedProof = encodePaymentProof(proof);

  console.log(`Payment confirmed in ${transfer.transactionHash}`);
  console.log(`Retrying with ${proofHeader} payment proof`);
  response = await fetch(url, {
    headers: {
      Accept: "application/json",
      [proofHeader]: encodedProof,
    },
  });
  body = await readJson(response);

  if (response.status === 402) {
    throw new Error(
      "The USDC transfer succeeded, but the server did not accept Payment Proof. " +
      "This deployment is discovery-only until facilitator settlement is enabled. " +
      `Server response: ${JSON.stringify(body)}`,
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