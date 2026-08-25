/**
 * kristo-x402-client — zero-dependency x402 payment client.
 *
 * Handles the full Kristo Intelligence payment handshake automatically:
 *   1. Call any paid endpoint.
 *   2. On HTTP 402, parse the canonical x402_* fields (amount, recipient,
 *      token contract, chain).
 *   3. Invoke YOUR payer callback (viem / ethers / anything) to send USDC
 *      on Base and obtain the transaction hash.
 *   4. Retry the original request with the X-Payment-Proof header.
 *   5. Return the paid response.
 *
 * Provider-agnostic by design: the core has ZERO dependencies. Bring your
 * own signer through the `pay` callback.
 */

const DEFAULT_BASE_URL = "https://kristo-intelligence-api.onrender.com";
const PROOF_HEADER = "X-Payment-Proof";

/** base64url-encode a JSON payment proof (no padding, no dependencies). */
export function buildPaymentProof({ payer, transactionHash, amountUsdc }) {
  const payload = JSON.stringify({
    payer: String(payer).toLowerCase(),
    transaction_hash: String(transactionHash).toLowerCase(),
    amount_usdc: Number(amountUsdc),
  });
  return Buffer.from(payload, "utf8")
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

/** Parse a 402 response body into a payment challenge object. */
export function parsePaymentChallenge(body) {
  if (!body || body.error !== "payment_required") return null;
  const amount = Number(body.x402_amount ?? body.payment?.amount_usdc);
  const recipient =
    body.x402_recipient ?? body.payment?.receiver_address;
  const tokenContract =
    body.x402_token_contract ?? body.payment?.token_contract;
  const chainId = Number(body.x402_chain_id ?? body.payment?.chain_id ?? 8453);
  if (!recipient || !Number.isFinite(amount) || amount <= 0) return null;
  return { amount, recipient, tokenContract, chainId };
}

export class KristoX402Client {
  /**
   * @param {object} options
   * @param {string} [options.baseUrl] API base URL.
   * @param {function} options.pay Payer callback invoked with the payment
   *   challenge `{ amount, recipient, tokenContract, chainId, path }`.
   *   Must resolve with `{ payer, txHash }` after broadcasting the USDC
   *   transfer. Bring your own signer (viem, ethers, ...).
   * @param {number} [options.maxPaymentRetries=3] How many payment rounds
   *   to attempt before giving up.
   * @param {boolean} [options.autoPay=true] When false, a 402 response is
   *   returned to the caller as `{ paymentRequired: challenge }` without
   *   paying (useful for inspection / dry runs).
   */
  constructor({ baseUrl = DEFAULT_BASE_URL, pay, maxPaymentRetries = 3, autoPay = true } = {}) {
    if (autoPay && typeof pay !== "function") {
      throw new TypeError(
        "KristoX402Client: a `pay` callback is required (or set autoPay: false)."
      );
    }
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.pay = pay;
    this.maxPaymentRetries = maxPaymentRetries;
    this.autoPay = autoPay;
  }

  /**
   * GET a paid endpoint, completing the x402 handshake when required.
   * @returns {Promise<{ok: boolean, status: number, data: any}>}
   */
  async get(path) {
    return this._requestWithPayments(path);
  }

  /** POST JSON to a paid endpoint with the same automatic payments. */
  async post(path, json) {
    return this._requestWithPayments(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(json ?? {}),
    });
  }

  async _requestWithPayments(path, init = {}) {
    for (let round = 0; round <= this.maxPaymentRetries; round++) {
      const response = await fetch(`${this.baseUrl}${path}`, init);
      if (response.status !== 402) {
        const data = await this._safeJson(response);
        return { ok: response.ok, status: response.status, data };
      }

      const body = await this._safeJson(response);
      const challenge = parsePaymentChallenge(body);
      if (!challenge) {
        // Malformed 402 — surface it instead of looping forever.
        return { ok: false, status: 402, data: body };
      }
      if (!this.autoPay) {
        return { ok: false, status: 402, paymentRequired: { ...challenge, path } };
      }

      const { payer, txHash } = await this.pay({ ...challenge, path });
      const proof = buildPaymentProof({
        payer,
        transactionHash: txHash,
        amountUsdc: challenge.amount,
      });
      // Merge the proof header into the retry request.
      const headers = new Headers(init.headers ?? {});
      headers.set(PROOF_HEADER, proof);
      init = { ...init, headers };
    }
    return { ok: false, status: 402, error: "max_payment_retries_exceeded" };
  }

  async _safeJson(response) {
    try {
      return await response.json();
    } catch {
      return null;
    }
  }
}
