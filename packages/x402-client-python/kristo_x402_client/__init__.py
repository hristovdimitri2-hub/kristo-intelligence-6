# -*- coding: utf-8 -*-
"""kristo-x402-client — zero-dependency x402 payment client for Python.

Handles the full Kristo Intelligence payment handshake automatically:

1. Call any paid endpoint.
2. On HTTP 402, read the canonical x402 v2 challenge from the
   ``PAYMENT-REQUIRED`` response header (falling back to the legacy
   ``x402_*`` fields in the body).
3. Invoke YOUR signer callback to authorise USDC on Base — either by signing
   an EIP-3009 authorization (v2, no gas, no waiting) or by broadcasting a
   plain transfer (legacy).
4. Retry the original request with ``PAYMENT-SIGNATURE`` (v2) or
   ``X-Payment-Proof`` (legacy).
5. Return the paid response.

Provider-agnostic by design: the core has ZERO dependencies. Bring your own
signer through the ``pay`` callback. The two rails are not equally fast: the
v2 rail settles through a facilitator and unlocks in about two seconds; the
smart-wallet rail verifies a plain ERC-20 transfer on-chain and waits for 12
confirmations, roughly 2.5 seconds on Base. Prefer the v2 rail.

This mirrors the published JavaScript client (``kristo-x402-client`` on npm)
so both languages behave identically.
"""

import base64
import json
import time
import urllib.error
import urllib.request

__all__ = [
    "DEFAULT_BASE_URL",
    "PROOF_HEADER",
    "PAYMENT_SIGNATURE_HEADER",
    "PAYMENT_REQUIRED_HEADER",
    "USDC_DECIMALS",
    "build_payment_proof",
    "parse_payment_challenge",
    "parse_payment_required_header",
    "build_payment_signature_header",
    "KristoX402Client",
]

DEFAULT_BASE_URL = "https://kristo-intelligence-api.onrender.com"

#: Smart-wallet rail: a self-describing proof of a plain ERC-20 transfer.
PROOF_HEADER = "X-Payment-Proof"
#: Standard rail (x402 v2): the signed EIP-3009 payload.
PAYMENT_SIGNATURE_HEADER = "PAYMENT-SIGNATURE"
#: Standard rail (x402 v2): the challenge the server sends on a 402.
PAYMENT_REQUIRED_HEADER = "PAYMENT-REQUIRED"

#: Atomic units per USDC (the token has 6 decimals).
USDC_DECIMALS = 6
ATOMIC_PER_USDC = 10 ** USDC_DECIMALS


def _to_base64url(text):
    """base64url-encode text with no padding."""
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


def _from_base64url(value):
    """base64url-decode text, tolerating missing padding."""
    normalised = str(value).replace("-", "+").replace("_", "/")
    padding = "=" * (-len(normalised) % 4)
    return base64.b64decode(normalised + padding).decode("utf-8")


def _to_atomic_string(raw):
    """Interpret a price field in EITHER unit, safely.

    ``x402_amount`` and ``payment.amount_usdc`` are ATOMIC units on the live
    server: a $0.005 call arrives as ``"5000"`` and ``5000`` respectively. The
    field was a DECIMAL in an earlier release, and sample clients written
    against that era fed the raw number straight into a 6-decimal conversion,
    which instructs the wallet to transfer 5000 USDC for a $0.005 call. The
    server compares the decoded on-chain amount against the price with ``>=``,
    so it would ACCEPT that transfer and keep the money.

    So: a value with a decimal point is taken as human USDC, a bare integer is
    taken as atomic. That is correct for both eras, and where the two readings
    could ever disagree the one chosen is the SMALLER — an understated price
    costs a rejected call (HTTP 401, no money moves), an overstated one costs
    the payer's balance.
    """
    text = str(raw).strip()
    if "." in text:
        try:
            as_number = float(text)
        except ValueError:
            return None
        if as_number <= 0:
            return None
        return str(int(round(as_number * ATOMIC_PER_USDC)))
    return text


def build_payment_proof(payer, transaction_hash, amount_usdc):
    """base64url-encode a JSON payment proof for the smart-wallet rail."""
    payload = json.dumps({
        "payer": str(payer).lower(),
        "transaction_hash": str(transaction_hash).lower(),
        "amount_usdc": float(amount_usdc),
    }, separators=(",", ":"))
    return _to_base64url(payload)


def parse_payment_challenge(body):
    """Parse a legacy 402 response body into a payment challenge object.

    ``amount`` is HUMAN USDC (0.005) and ``amount_atomic`` is the string of
    atomic units ("5000"). Prefer :func:`parse_payment_required_header`, which
    reads the standard x402 v2 challenge.
    """
    if not body or body.get("error") != "payment_required":
        return None
    payment = body.get("payment") or {}
    amount_atomic = _to_atomic_string(
        body.get("x402_amount", payment.get("amount_usdc")))
    if amount_atomic is None:
        return None
    try:
        atomic = int(amount_atomic)
    except (TypeError, ValueError):
        return None
    recipient = body.get("x402_recipient") or payment.get("receiver_address")
    token_contract = (body.get("x402_token_contract")
                      or payment.get("token_contract"))
    chain_id = body.get("x402_chain_id", payment.get("chain_id", 8453))
    if not recipient or atomic <= 0:
        return None
    return {
        "rail": "legacy",
        "amount": atomic / ATOMIC_PER_USDC,
        "amount_atomic": amount_atomic,
        "recipient": recipient,
        "token_contract": token_contract,
        "chain_id": int(chain_id),
    }


def parse_payment_required_header(header_value):
    """Parse the canonical x402 v2 challenge from a ``PAYMENT-REQUIRED`` header.

    The header is base64url-encoded JSON whose ``accepts`` array carries the
    terms. Returns ``None`` when the header is absent, undecodable, or carries
    no usable ``exact``-scheme accept — so a caller can fall back to the legacy
    body shape instead of raising.

    ``amount`` is exposed both as atomic units (the string the header uses) and
    as a human USDC number, so a legacy-only signer can still be driven from a
    v2 challenge without doing the decimals itself.
    """
    if not header_value:
        return None
    try:
        decoded = json.loads(_from_base64url(header_value))
    except (ValueError, TypeError):
        return None
    accepts = decoded.get("accepts") if isinstance(decoded, dict) else None
    if not isinstance(accepts, list):
        accepts = []
    accepted = next(
        (a for a in accepts if isinstance(a, dict) and a.get("payTo") and a.get("amount")),
        accepts[0] if accepts else None,
    )
    if not isinstance(accepted, dict) or not accepted.get("payTo"):
        return None
    if accepted.get("amount") is None:
        return None
    amount_atomic = _to_atomic_string(accepted["amount"])
    if amount_atomic is None:
        return None
    try:
        atomic = int(amount_atomic)
    except (TypeError, ValueError):
        return None
    if atomic <= 0:
        return None

    network = str(accepted.get("network") or "")
    chain_id = accepted.get("chainId")
    if chain_id is None:
        tail = network.split(":")[-1] if network else ""
        chain_id = int(tail) if tail.isdigit() else 8453
    try:
        chain_id = int(chain_id)
    except (TypeError, ValueError):
        chain_id = 8453

    resource = decoded.get("resource") or {}
    return {
        "rail": "v2",
        "x402_version": int(decoded.get("x402Version", 2)),
        "scheme": accepted.get("scheme", "exact"),
        "network": network,
        "chain_id": chain_id,
        "amount_atomic": amount_atomic,
        "amount": atomic / ATOMIC_PER_USDC,
        "recipient": accepted["payTo"],
        "token_contract": accepted.get("asset"),
        "max_timeout_seconds": int(accepted.get("maxTimeoutSeconds", 60)),
        "extra": accepted.get("extra"),
        "resource_url": resource.get("url") if isinstance(resource, dict) else None,
        # The raw accept block, echoed back inside the signed payload.
        "accepted": accepted,
    }


def build_payment_signature_header(signature, authorization, accepted,
                                   x402_version=2):
    """Build the base64url ``PAYMENT-SIGNATURE`` header value for a v2 payment.

    ``accepted`` must be the accept block from the challenge the server issued —
    the server compares it with what the signature authorises.
    """
    if not signature or not authorization or not accepted:
        raise TypeError(
            "build_payment_signature_header needs signature, authorization "
            "and accepted")
    return _to_base64url(json.dumps({
        "x402Version": x402_version,
        "accepted": accepted,
        "payload": {"signature": signature, "authorization": authorization},
    }, separators=(",", ":")))


class KristoX402Client:
    """Zero-dependency x402 client for the Kristo Intelligence API.

    :param base_url: API base URL.
    :param pay: Signer callback invoked with the payment challenge. It must
        return EITHER ``{"signature": ..., "authorization": ...}`` — an
        EIP-3009 authorization signed by the payer (preferred: settles in ~2s
        through the facilitator) — OR ``{"payer": ..., "txHash": ...}`` — a
        broadcast plain USDC transfer (smart-wallet: the server waits for 12
        confirmations, ~2.5s). The challenge carries ``amount_atomic``,
        ``recipient``, ``token_contract``, ``chain_id``, ``extra`` and
        ``accepted`` when the standard rail is available.
    :param max_payment_retries: Upper bound on payment rounds. In practice a
        request signs AT MOST ONCE: a second 402 for the same terms returns
        ``payment_outcome_unknown`` instead of signing again, because a second
        signature is a second payment. Kept as a hard stop so a misbehaving
        server can never drive an unbounded loop.
    :param auto_pay: When False, a 402 response is returned to the caller as
        ``{"payment_required": challenge}`` without paying (useful for
        inspection / dry runs).
    :param max_in_flight_retries: How many times to re-send the SAME
        credential when the server answers 425 ``settlement_in_flight`` (the
        payment is settling; a new payment must not be made).
    :param in_flight_delay: Seconds between those retries.
    :param timeout: Socket timeout in seconds for each request.
    """

    def __init__(self, base_url=DEFAULT_BASE_URL, pay=None,
                 max_payment_retries=3, auto_pay=True,
                 max_in_flight_retries=5, in_flight_delay=1.5, timeout=60):
        if auto_pay and not callable(pay):
            raise TypeError(
                "KristoX402Client: a `pay` callback is required "
                "(or set auto_pay=False).")
        self.base_url = base_url.rstrip("/")
        self.pay = pay
        self.max_payment_retries = max_payment_retries
        self.auto_pay = auto_pay
        self.max_in_flight_retries = max_in_flight_retries
        self.in_flight_delay = in_flight_delay
        self.timeout = timeout

    # ── public API ────────────────────────────────────────────────────────
    def get(self, path):
        """GET a paid endpoint, completing the x402 handshake when required.

        Returns ``{"ok": bool, "status": int, "data": any}``.
        """
        return self._request_with_payments(path, "GET")

    def post(self, path, json_body=None):
        """POST JSON to a paid endpoint with the same automatic payments."""
        return self._request_with_payments(
            path, "POST", json_body=json_body if json_body is not None else {},
            headers={"Content-Type": "application/json"})

    # ── internals ─────────────────────────────────────────────────────────
    def _request_with_payments(self, path, method="GET", headers=None,
                               json_body=None):
        # AT MOST ONE SIGNATURE PER REQUEST.
        #
        # Signing on every 402 round would sign a FRESH authorization with a
        # FRESH nonce each time, so a server that answered 402 after the first
        # credential had already been broadcast would be handed a SECOND,
        # independent payment — the buyer pays twice. A 402 does not say
        # whether anything was broadcast, so this client cannot decide safely
        # on its own. It signs once, re-presents that same credential (the 425
        # path does exactly that), and if a 402 comes back for terms it has
        # ALREADY paid, it stops and says the outcome is unknown rather than
        # spending the buyer's money again.
        signed = None
        base_headers = dict(headers or {})
        body_bytes = None
        if json_body is not None:
            body_bytes = json.dumps(json_body).encode("utf-8")

        for _round in range(self.max_payment_retries + 1):
            status, resp_headers, raw = self._fetch_settling(
                path, method, base_headers, body_bytes)
            body = _safe_json(raw)

            if status != 402:
                return {"ok": 200 <= status < 300, "status": status, "data": body}

            challenge = (parse_payment_required_header(
                resp_headers.get(PAYMENT_REQUIRED_HEADER.lower()))
                or parse_payment_challenge(body))
            if not challenge:
                # Malformed 402 — surface it instead of looping forever.
                return {"ok": False, "status": 402, "data": body}
            if not self.auto_pay:
                return {"ok": False, "status": 402,
                        "payment_required": dict(challenge, path=path)}
            if signed is not None:
                # We already handed this server a credential and it asked for
                # payment again. Signing would be a second payment.
                return {
                    "ok": False,
                    "status": 402,
                    "error": "payment_outcome_unknown",
                    "message": (
                        "The server answered 402 again for terms this client "
                        "had already signed. A new signature would be a SECOND "
                        "payment, so none was made. Check the chain for the "
                        "authorization nonce before retrying, and retry only "
                        "if it is unused."),
                }

            payment = self.pay(dict(challenge, path=path))
            signed = payment
            headers_now = dict(base_headers)

            if (isinstance(payment, dict)
                    and payment.get("signature")
                    and payment.get("authorization")
                    and challenge.get("accepted")):
                headers_now[PAYMENT_SIGNATURE_HEADER] = (
                    build_payment_signature_header(
                        payment["signature"], payment["authorization"],
                        challenge["accepted"]))
            elif isinstance(payment, dict) and payment.get("txHash"):
                headers_now[PROOF_HEADER] = build_payment_proof(
                    payment.get("payer"),
                    payment["txHash"],
                    challenge["amount"])
            else:
                raise TypeError(
                    "KristoX402Client: `pay` must return "
                    "{signature, authorization} (x402 v2) or {payer, txHash} "
                    "(legacy). Received: %r" % (payment,))
            base_headers = headers_now

        return {"ok": False, "status": 402, "error": "max_payment_retries_exceeded"}

    def _fetch_settling(self, path, method, headers, body_bytes):
        """Fetch, absorbing HTTP 425 ``settlement_in_flight``.

        The server answers 425 while a settlement is still being confirmed and
        the correct response is to re-send the SAME credential shortly. Making
        a second payment here would be wrong — and the server would reject it
        anyway, since the authorization nonce is one-time-use.
        """
        url = self.base_url + path
        status, resp_headers, raw = self._fetch(url, method, headers, body_bytes)
        attempt = 0
        while status == 425 and attempt < self.max_in_flight_retries:
            time.sleep(self.in_flight_delay)
            status, resp_headers, raw = self._fetch(
                url, method, headers, body_bytes)
            attempt += 1
        return status, resp_headers, raw

    def _fetch(self, url, method, headers, body_bytes):
        request = urllib.request.Request(url, data=body_bytes, method=method)
        for name, value in (headers or {}).items():
            request.add_header(name, value)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                return resp.status, dict(resp.headers), resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, dict(exc.headers or {}), exc.read()


def _safe_json(raw):
    try:
        return json.loads(raw.decode("utf-8")) if raw else None
    except (ValueError, UnicodeDecodeError):
        return None
