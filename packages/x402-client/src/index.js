/**
 * kristo-x402-client — zero-dependency x402 payment client.
 *
 * Handles the full Kristo Intelligence payment handshake automatically:
 *   1. Call any paid endpoint.
 *   2. On HTTP 402, read the canonical x402 v2 challenge from the
 *      `PAYMENT-REQUIRED` response header (falling back to the legacy
 *      `x402_*` fields in the body).
 *   3. Invoke YOUR signer callback (viem / ethers / anything) to authorise
 *      USDC on Base — either by signing an EIP-3009 authorization (v2, no gas,
 *      no waiting) or by broadcasting a plain transfer (legacy).
 *   4. Retry the original request with `PAYMENT-SIGNATURE` (v2) or
 *      `X-Payment-Proof` (legacy).
 *   5. Return the paid response.
 *
 * Provider-agnostic by design: the core has ZERO dependencies. Bring your
 * own signer through the `pay` callback.
 *
 * THE TWO RAILS ARE NOT EQUALLY FAST. The v2 rail settles through a
 * facilitator and unlocks in about two seconds. The legacy rail verifies a
 * plain ERC-20 transfer on-chain and waits for 12 confirmations — roughly 24
 * seconds on Base. Prefer the v2 rail; the legacy one is kept so existing
 * callbacks keep working.
 */

const DEFAULT_BASE_URL = "https://kristo-intelligence-api.onrender.com";

/** Legacy rail: a self-describing proof of a plain ERC-20 transfer. */
export const PROOF_HEADER = "X-Payment-Proof";
/** Standard rail (x402 v2): the signed EIP-3009 payload. */
export const PAYMENT_SIGNATURE_HEADER = "PAYMENT-SIGNATURE";
/** Standard rail (x402 v2): the challenge the server sends on a 402. */
export const PAYMENT_REQUIRED_HEADER = "PAYMENT-REQUIRED";

/** Atomic units per USDC (the token has 6 decimals). */
const USDC_DECIMALS = 6;
const ATOMIC_PER_USDC = 10 ** USDC_DECIMALS;

function toBase64url(text) {
  return Buffer.from(text, "utf8")
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

function fromBase64url(value) {
  const normalised = String(value).replace(/-/g, "+").replace(/_/g, "/");
  const padding = normalised.length % 4
    ? "=".repeat(4 - (normalised.length % 4))
    : "";
  return Buffer.from(normalised + padding, "base64").toString("utf8");
}

/** base64url-encode a JSON payment proof (no padding, no dependencies). */
export function buildPaymentProof({ payer, transactionHash, amountUsdc }) {
  const payload = JSON.stringify({
    payer: String(payer).toLowerCase(),
    transaction_hash: String(transactionHash).toLowerCase(),
    amount_usdc: Number(amountUsdc),
  });
  return toBase64url(payload);
}

/**
 * Interpret a price field from a 402 payload, in EITHER unit, safely.
 *
 * `x402_amount` and `payment.amount_usdc` are ATOMIC units on the live server:
 * a $0.005 call arrives as `"5000"` and `5000` respectively. The field was a
 * DECIMAL in an earlier release (`main.py` annotates the change: "atomic units,
 * as in accepts (was decimal)"), and sample clients written against that era
 * fed the raw number straight into `parseUnits(amount, 6)`, which instructs the
 * wallet to transfer 5000 USDC for a $0.005 call. The server compares the
 * decoded on-chain amount against the price with `>=`, so it would ACCEPT that
 * transfer and keep the money.
 *
 * So: a value with a decimal point is taken as human USDC, a bare integer is
 * taken as atomic. That is correct for both eras, and where the two readings
 * could ever disagree the one chosen is the SMALLER — an understated price
 * costs a rejected call (HTTP 401, no money moves), an overstated one costs
 * the payer's balance.
 */
function toAtomicString(raw) {
  const text = String(raw).trim();
  if (text.includes(".")) {
    const asNumber = Number(text);
    if (!Number.isFinite(asNumber) || asNumber <= 0) return null;
    return String(Math.round(asNumber * ATOMIC_PER_USDC));
  }
  return text;
}

/**
 * Parse a legacy 402 response body into a payment challenge object.
 *
 * `amount` is HUMAN USDC (0.005) and `amountAtomic` is the string of atomic
 * units ("5000"). Prefer `parsePaymentRequiredHeader`, which reads the standard
 * x402 v2 challenge.
 */
export function parsePaymentChallenge(body) {
  if (!body || body.error !== "payment_required") return null;
  const amountAtomic = toAtomicString(
    body.x402_amount ?? body.payment?.amount_usdc);
  if (amountAtomic === null) return null;
  const atomic = Number(amountAtomic);
  const recipient =
    body.x402_recipient ?? body.payment?.receiver_address;
  const tokenContract =
    body.x402_token_contract ?? body.payment?.token_contract;
  const chainId = Number(body.x402_chain_id ?? body.payment?.chain_id ?? 8453);
  if (!recipient || !Number.isFinite(atomic) || atomic <= 0) return null;
  return {
    amount: atomic / ATOMIC_PER_USDC,
    amountAtomic,
    recipient,
    tokenContract,
    chainId,
  };
}

/**
 * Parse the canonical x402 v2 challenge from a `PAYMENT-REQUIRED` header.
 *
 * The header is base64url-encoded JSON whose `accepts` array carries the terms.
 * Returns `null` when the header is absent, undecodable, or carries no usable
 * `exact`-scheme accept — so a caller can fall back to the legacy body shape
 * instead of throwing.
 *
 * `amount` is exposed both as atomic units (the string the header uses) and as
 * a human USDC number, so a legacy-only signer can still be driven from a v2
 * challenge without doing the decimals itself.
 */
export function parsePaymentRequiredHeader(headerValue) {
  if (!headerValue) return null;
  let decoded;
  try {
    decoded = JSON.parse(fromBase64url(headerValue));
  } catch {
    return null;
  }
  const accepts = Array.isArray(decoded?.accepts) ? decoded.accepts : [];
  const accepted = accepts.find((entry) => entry?.payTo && entry?.amount)
    ?? accepts[0];
  if (!accepted || !accepted.payTo || accepted.amount === undefined) return null;

  const amountAtomic = toAtomicString(accepted.amount);
  if (amountAtomic === null) return null;
  const atomic = Number(amountAtomic);
  if (!Number.isFinite(atomic) || atomic <= 0) return null;

  const network = String(accepted.network ?? "");
  const chainId = Number(
    accepted.chainId ?? network.split(":").pop() ?? 8453
  );

  return {
    rail: "v2",
    x402Version: Number(decoded.x402Version ?? 2),
    scheme: accepted.scheme ?? "exact",
    network,
    chainId: Number.isFinite(chainId) ? chainId : 8453,
    amountAtomic,
    amount: atomic / 10 ** USDC_DECIMALS,
    recipient: accepted.payTo,
    tokenContract: accepted.asset,
    maxTimeoutSeconds: Number(accepted.maxTimeoutSeconds ?? 60),
    extra: accepted.extra ?? null,
    resourceUrl: decoded?.resource?.url ?? null,
    /** The raw accept block, echoed back inside the signed payload. */
    accepted,
  };
}

/**
 * Build the base64url `PAYMENT-SIGNATURE` header value for a v2 payment.
 *
 * `accepted` must be the accept block from the challenge the server issued —
 * the server compares it with what the signature authorises.
 */
export function buildPaymentSignatureHeader({
  signature,
  authorization,
  accepted,
  x402Version = 2,
}) {
  if (!signature || !authorization || !accepted) {
    throw new TypeError(
      "buildPaymentSignatureHeader needs { signature, authorization, accepted }"
    );
  }
  return toBase64url(JSON.stringify({
    x402Version,
    accepted,
    payload: { signature, authorization },
  }));
}

export class KristoX402Client {
  /**
   * @param {object} options
   * @param {string} [options.baseUrl] API base URL.
   * @param {function} options.pay Signer callback invoked with the payment
   *   challenge. Resolve with EITHER
   *     `{ signature, authorization }` — an EIP-3009 authorization signed by
   *     the payer (preferred: settles in ~2s through the facilitator), OR
   *     `{ payer, txHash }` — a broadcast plain USDC transfer (legacy: the
   *     server waits for 12 confirmations, ~24s).
   *   The challenge carries `amountAtomic`, `recipient`, `tokenContract`,
   *   `chainId`, `extra` and `accepted` when the standard rail is available.
   * @param {number} [options.maxPaymentRetries=3] How many payment rounds
   *   to attempt before giving up.
   * @param {boolean} [options.autoPay=true] When false, a 402 response is
   *   returned to the caller as `{ paymentRequired: challenge }` without
   *   paying (useful for inspection / dry runs).
   * @param {number} [options.maxInFlightRetries=5] How many times to re-send
   *   the SAME credential when the server answers 425 `settlement_in_flight`
   *   (the payment is settling; a new payment must not be made).
   * @param {number} [options.inFlightDelayMs=1500] Delay between those retries.
   */
  constructor({
    baseUrl = DEFAULT_BASE_URL,
    pay,
    maxPaymentRetries = 3,
    autoPay = true,
    maxInFlightRetries = 5,
    inFlightDelayMs = 1500,
  } = {}) {
    if (autoPay && typeof pay !== "function") {
      throw new TypeError(
        "KristoX402Client: a `pay` callback is required (or set autoPay: false)."
      );
    }
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.pay = pay;
    this.maxPaymentRetries = maxPaymentRetries;
    this.autoPay = autoPay;
    this.maxInFlightRetries = maxInFlightRetries;
    this.inFlightDelayMs = inFlightDelayMs;
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
      const response = await this._fetchSettling(path, init);

      if (response.status !== 402) {
        const data = await this._safeJson(response);
        return { ok: response.ok, status: response.status, data };
      }

      const body = await this._safeJson(response);
      // Prefer the standard v2 challenge; fall back to the legacy body shape so
      // an older server (or an older proxy) still works.
      const challenge = parsePaymentRequiredHeader(
        response.headers?.get?.(PAYMENT_REQUIRED_HEADER)
      ) ?? parsePaymentChallenge(body);
      if (!challenge) {
        // Malformed 402 — surface it instead of looping forever.
        return { ok: false, status: 402, data: body };
      }
      if (!this.autoPay) {
        return { ok: false, status: 402, paymentRequired: { ...challenge, path } };
      }

      const payment = await this.pay({ ...challenge, path });
      const headers = new Headers(init.headers ?? {});

      if (payment?.signature && payment?.authorization && challenge.accepted) {
        headers.set(PAYMENT_SIGNATURE_HEADER, buildPaymentSignatureHeader({
          signature: payment.signature,
          authorization: payment.authorization,
          accepted: challenge.accepted,
        }));
      } else if (payment?.txHash) {
        headers.set(PROOF_HEADER, buildPaymentProof({
          payer: payment.payer,
          transactionHash: payment.txHash,
          amountUsdc: challenge.amount,
        }));
      } else {
        throw new TypeError(
          "KristoX402Client: `pay` must resolve with { signature, " +
          "authorization } (x402 v2) or { payer, txHash } (legacy). " +
          "Received: " + JSON.stringify(payment ?? null)
        );
      }
      init = { ...init, headers };
    }
    return { ok: false, status: 402, error: "max_payment_retries_exceeded" };
  }

  /**
   * Fetch, absorbing HTTP 425 `settlement_in_flight`.
   *
   * The server answers 425 while a settlement is still being confirmed and the
   * correct response is to re-send the SAME credential shortly. Making a second
   * payment here would be wrong — and the server would reject it anyway, since
   * the authorization nonce is one-time-use.
   */
  async _fetchSettling(path, init) {
    let response = await fetch(`${this.baseUrl}${path}`, init);
    for (let attempt = 0;
      response.status === 425 && attempt < this.maxInFlightRetries;
      attempt++) {
      await new Promise((resolve) => setTimeout(resolve, this.inFlightDelayMs));
      response = await fetch(`${this.baseUrl}${path}`, init);
    }
    return response;
  }

  async _safeJson(response) {
    try {
      return await response.json();
    } catch {
      return null;
    }
  }
}
