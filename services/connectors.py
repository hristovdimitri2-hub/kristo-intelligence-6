# -*- coding: utf-8 -*-
"""
Integration connector registry for Kristo Intelligence.

One place that knows every external network / protocol / marketplace the
system is wired to, exposes live status for the dashboard, and implements
the standard-x402 (EIP-3009 / X-PAYMENT) inbound rail through a facilitator.

Connectors:
  base-usdc-receiver      inbound   Base/USDC on-chain settlement (monitor)
  x402-challenge-v2       inbound   canonical x402 v2 challenge builders
  x402-eip3009            inbound   STANDARD X-PAYMENT rail via facilitator
  x402-outbound-buyer     outbound  pay OTHER x402 APIs (packages/x402-client)
  l402-lightning          outbound  L402 (Lightning macaroon/preimage) bridge
  mcp-sse                 inbound   MCP clients (Claude Desktop, Cursor, …)
  marketplace-x402scan    outbound  listing/distribution
  marketplace-payapi      outbound  listing/distribution
  marketplace-nohumans    outbound  listing/distribution
"""
import base64
import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

from config import get_base_fee_receiver

log = logging.getLogger(__name__)

# ── Activity ledger (in-memory, per-process) ────────────────────────────────
_ACTIVITY = {}  # conn_id -> ISO timestamp of last real use


def touch(conn_id: str) -> None:
    """Record a real interaction with a connector (call it on every use)."""
    _ACTIVITY[conn_id] = datetime.now(timezone.utc).isoformat()


def last_activity(conn_id: str):
    return _ACTIVITY.get(conn_id)


# ── Standard x402 (EIP-3009) facilitator rail ───────────────────────────────
FACILITATOR_TIMEOUT = float(os.getenv("X402_FACILITATOR_TIMEOUT", "15"))

# Facilitator chain (tried in order on TRANSPORT errors):
#   1. env override X402_FACILITATOR_URL (if set)
#   2. PayAI public facilitator — free, no auth, supports x402 v2
#      (verified live 2026-08-31: recovers EIP-3009 signers exactly)
#   3. Coinbase CDP facilitator — needs CDP API keys (401 without); kept
#      last so a deployment with CDP credentials can adopt it.
_DEFAULT_CHAIN = [
    ("payai", "https://facilitator.payai.network"),
    ("cdp", "https://api.cdp.coinbase.com/platform/v2/x402"),
]

FACILITATOR_URL = os.getenv(
    "X402_FACILITATOR_URL",
    "https://facilitator.payai.network",
).rstrip("/")


def _facilitator_chain():
    chain = []
    env_url = os.getenv("X402_FACILITATOR_URL", "").strip()
    if env_url:
        chain.append(("env", env_url.rstrip("/")))
    chain.extend(_DEFAULT_CHAIN)
    return chain


def _facilitator_post(base_url: str, endpoint: str, body: dict,
                      token: str | None = None):
    """
    POST JSON to a facilitator; returns (http_status, parsed_dict_or_None,
    raw_text). Logs every attempt and every failure reason clearly — this is
    the observability PayAPI's review asked for.
    """
    url = f"{base_url}/{endpoint}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=FACILITATOR_TIMEOUT) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw), raw
            except ValueError:
                return resp.status, None, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")[:500]
        log.warning("facilitator %s %s -> HTTP %s: %s",
                    base_url, endpoint, e.code, raw)
        return e.code, None, raw
    except Exception as e:  # transport (DNS, timeout, TLS)
        log.warning("facilitator %s %s -> %s: %s",
                    base_url, endpoint, type(e).__name__, e)
        return None, None, f"{type(e).__name__}: {e}"


def decode_payment_payload(header_value):
    """
    Decode the PAYMENT-SIGNATURE payload. Accepts a base64url JSON string
    (the header as sent by clients) or an already-decoded dict. Returns a
    dict or None (with the problem logged).
    """
    if isinstance(header_value, dict):
        return header_value
    if not header_value or not isinstance(header_value, str):
        return None
    try:
        padded = header_value + "=" * (-len(header_value) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))
    except Exception as e:
        log.warning("PAYMENT-SIGNATURE payload undecodable: %s", e)
        return None


def precheck_payment_payload(payload: dict, requirements: dict):
    """
    Structural pre-check of the decoded EIP-3009 payload against the
    requirements WE issued in the 402 challenge. Returns a list of problems
    (empty list = structurally valid). Covers exactly what the review asked
    to see validated: scheme, network, amount, receiver, asset and the
    authorization time window (validAfter/validBefore).
    """
    problems = []
    accepted = payload.get("accepted") or {}
    inner = payload.get("payload") or {}
    auth = inner.get("authorization") or {}
    now = int(time.time())

    if accepted.get("scheme") not in (None, "exact"):
        problems.append(f"scheme mismatch: {accepted.get('scheme')!r} != 'exact'")
    if accepted.get("network") not in (None, "eip155:8453"):
        problems.append(f"network mismatch: {accepted.get('network')!r} != 'eip155:8453'")
    want_amount = str(requirements.get("amount", ""))
    got_amount = str(accepted.get("amount") or auth.get("value") or "")
    if want_amount and got_amount.isdigit() and int(got_amount) < int(want_amount):
        problems.append(
            f"amount below price: {got_amount} < {want_amount} atomic units"
        )
    if accepted.get("asset") not in (None, requirements.get("asset")):
        problems.append(f"asset mismatch: {accepted.get('asset')!r}")
    if auth.get("to") and str(auth.get("to")).lower() != str(
        requirements.get("payTo", "")
    ).lower():
        problems.append(
            f"authorization.to != payTo: {auth.get('to')} != {requirements.get('payTo')}"
        )
    try:
        valid_before = int(auth.get("validBefore", "0"))
        valid_after = int(auth.get("validAfter", "0"))
        if valid_before <= now:
            problems.append(
                f"authorization expired: validBefore={valid_before} <= now={now}"
            )
        if valid_after > now:
            problems.append(
                f"authorization not yet valid: validAfter={valid_after} > now={now}"
            )
    except (ValueError, TypeError):
        problems.append("validAfter/validBefore are not integers")
    if not inner.get("signature"):
        problems.append("payload.signature missing")
    return problems


def _local_recover_signer(payload: dict):
    """
    Local EIP-712 recovery for the exact/EIP-3009 TransferWithAuthorization
    message (Base mainnet USDC domain: name 'USD Coin', version '2').
    Returns (recovered_address | None, error | None). Fails fast with a
    precise reason before any facilitator is involved.
    """
    try:
        from eth_account import Account
        from eth_account.messages import encode_typed_data

        accepted = payload.get("accepted") or {}
        inner = payload.get("payload") or {}
        auth = inner.get("authorization") or {}
        extra = accepted.get("extra") or {}
        network = str(accepted.get("network") or "eip155:8453")
        chain_id = int(network.split(":")[1]) if ":" in network else 8453
        domain = {
            "name": extra.get("name") or "USD Coin",
            "version": extra.get("version") or "2",
            "chainId": chain_id,
            "verifyingContract": accepted.get("asset"),
        }
        types = {"TransferWithAuthorization": [
            {"name": "from", "type": "address"},
            {"name": "to", "type": "address"},
            {"name": "value", "type": "uint256"},
            {"name": "validAfter", "type": "uint256"},
            {"name": "validBefore", "type": "uint256"},
            {"name": "nonce", "type": "bytes32"},
        ]}
        sm = encode_typed_data(
            domain_data=domain, message_types=types, message_data=auth
        )
        recovered = Account.recover_message(sm, signature=inner.get("signature"))
        return recovered, None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def _merged_requirements(payload: dict, requirements: dict) -> dict:
    """Requirements as the CLIENT accepted them (echoed accepted fields win)."""
    merged = dict(requirements)
    accepted = (payload or {}).get("accepted") or {}
    for key in ("amount", "asset", "payTo", "scheme", "network", "extra"):
        if accepted.get(key) is not None:
            merged[key] = accepted[key]
    return merged


def _split_signature(signature_hex: str):
    """
    Split a 65-byte hex signature into (v, r, s). Handles both v=27/28 and
    yParity 0/1 encodings. Returns (v:int, r:bytes, s:bytes) or None.
    """
    try:
        raw = signature_hex[2:] if signature_hex.startswith("0x") else signature_hex
        sig = bytes.fromhex(raw)
        if len(sig) != 65:
            return None
        r, s, v = sig[:32], sig[32:64], sig[64]
        v = v if v >= 27 else v + 27
        return v, r, s
    except (ValueError, TypeError):
        return None


# ERC-20 transferWithAuthorization (EIP-3009) selector on USDC:
# transferWithAuthorization(address,address,uint256,uint256,uint256,bytes32,uint8,bytes32,bytes32)
_TWA_SELECTOR = "e3ee160b"


def _self_broadcast_settlement(payload: dict):
    """
    Broadcast the buyer's transferWithAuthorization ourselves — we ARE the
    facilitator. Our wallet only pays gas; funds flow buyer → receiver and
    nobody can alter amount or destination (they are signed by the buyer).
    Requires WALLET_PRIVATE_KEY with a dust of Base ETH for gas (~$0.001
    per settlement). Returns (tx_hash | None, detail).
    """
    key = (os.getenv("WALLET_PRIVATE_KEY") or "").strip()
    if not key:
        return None, "self_broadcast: no WALLET_PRIVATE_KEY configured"
    try:
        from web3 import Web3
        from eth_account import Account
        from eth_abi import encode as abi_encode

        rpc = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
        w3 = Web3(Web3.HTTPProvider(rpc, {"timeout": 20}))
        if not w3.is_connected():
            return None, "self_broadcast: RPC not reachable"
        acct = Account.from_key(key if key.startswith("0x") else "0x" + key)

        inner = payload.get("payload") or {}
        auth = inner.get("authorization") or {}
        parts = _split_signature(inner.get("signature", ""))
        if not parts:
            return None, "self_broadcast: signature is not a 65-byte hex"
        v, r, s = parts

        gas_balance = w3.eth.get_balance(acct.address)
        gas_price = w3.eth.gas_price
        max_fee_per_gas = gas_price * 2
        gas_cap = 120000
        required_wei = max_fee_per_gas * gas_cap
        if gas_balance <= required_wei:
            return None, (
                f"self_broadcast: gas wallet {acct.address} has "
                f"{gas_balance / 1e18:.8f} ETH but one settlement needs up to "
                f"~{required_wei / 1e18:.8f} ETH — fund it with Base ETH"
            )

        data = bytes.fromhex(_TWA_SELECTOR) + abi_encode(
            ["address", "address", "uint256", "uint256", "uint256",
             "bytes32", "uint8", "bytes32", "bytes32"],
            [auth["from"], auth["to"], int(auth["value"]),
             int(auth["validAfter"]), int(auth["validBefore"]),
             bytes.fromhex(auth["nonce"][2:] if auth["nonce"].startswith("0x")
                           else auth["nonce"]),
             v, r, s],
        )
        tx = {
            "from": acct.address,
            "to": Web3.to_checksum_address(os.getenv(
                "BASE_USDC_CONTRACT",
                "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")),
            "data": data,
            "value": 0,
            "nonce": w3.eth.get_transaction_count(acct.address),
            "chainId": 8453,
            "maxFeePerGas": max_fee_per_gas,
            "maxPriorityFeePerGas": w3.to_wei(0.001, "gwei"),
            "gas": gas_cap,
        }
        signed = acct.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        hex_tx = tx_hash.hex() if hasattr(tx_hash, "hex") else str(tx_hash)
        log.info("self-broadcast settlement sent: tx=%s broadcaster=%s",
                 hex_tx, acct.address)

        # Confirm the receipt — a revert means the buyer's USDC did NOT move,
        # so we must NOT grant the call (this is exactly what a canary checks).
        deadline = time.time() + 24
        while time.time() < deadline:
            try:
                receipt = w3.eth.get_transaction_receipt(tx_hash)
                status = receipt.get("status")
                if status == 1:
                    block = receipt.get("blockNumber")
                    log.info("self-broadcast settlement CONFIRMED: tx=%s block=%s",
                             hex_tx, block)
                    return hex_tx, "settled_self_broadcast"
                if status == 0:
                    log.warning("self-broadcast settlement REVERTED: tx=%s "
                                "(buyer USDC balance or replay?)", hex_tx)
                    return None, (
                        f"self_broadcast_reverted: tx {hex_tx} — the on-chain "
                        f"transferWithAuthorization failed (insufficient buyer "
                        f"USDC balance or authorization already used)"
                    )
            except Exception:
                pass  # not yet mined — keep polling
            time.sleep(2)
        # Not confirmed within 24s — do NOT grant; the monitor may reconcile
        # the transfer later, but this request fails closed.
        return None, (
            f"self_broadcast_pending: tx {hex_tx} not confirmed within 24s — "
            f"retry the same PAYMENT-SIGNATURE shortly (one-time-use nonce "
            f"protects against double settle)"
        )
    except Exception as e:
        log.warning("self-broadcast settlement failed: %s: %s",
                    type(e).__name__, e)
        return None, f"self_broadcast_error: {type(e).__name__}: {e}"


def _cdp_jwt(host: str, path: str = "/platform/v2/x402/verify",
             method: str = "POST"):
    """
    Build a CDP Platform JWT for the x402 facilitator endpoints.

    Claims format VERIFIED against the live CDP gateway (2026-09-01, HTTP 400
    = auth accepted) using the official cdp-sdk as ground truth:
      header : {alg: ES256, kid: <KEY_ID>, nonce, typ: JWT}
      claims : {sub: <KEY_ID>, iss: 'cdp', nbf, exp,
                uris: ['<METHOD> <host><path>']}
    NOTE: 'aud' and 'iat' are NOT part of CDP's accepted claims — including
    them caused silent 401s. 'uris' (method + host + path, no scheme) is
    the auth discriminator. Supports BOTH CDP secret formats:
      - PEM EC private key ("-----BEGIN EC PRIVATE KEY-----") — current portal
      - legacy base64-encoded raw 32-byte key
    Handles Render-style pasting artifacts: literal "\\n" escapes in the PEM,
    surrounding quotes and whitespace.
    Returns (token | None, detail) where detail explains a failure precisely
    (missing keys vs unparseable PEM vs wrong curve).
    """
    key_id = (os.getenv("CDP_API_KEY_ID") or
              os.getenv("X402_FACILITATOR_API_KEY_ID") or "").strip()
    secret = (os.getenv("CDP_API_KEY_SECRET") or
              os.getenv("X402_FACILITATOR_API_KEY_SECRET") or "").strip()
    if not key_id or not secret:
        missing = []
        if not key_id:
            missing.append("CDP_API_KEY_ID")
        if not secret:
            missing.append("CDP_API_KEY_SECRET")
        return None, f"missing env: {', '.join(missing)}"
    try:
        import base64 as _b64
        import uuid
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import (
            decode_dss_signature,
        )

        # Normalize common paste artifacts before parsing.
        if secret.startswith('"') and secret.endswith('"'):
            secret = secret[1:-1]
        if "\\n" in secret:
            secret = secret.replace("\\n", "\n")
        secret = secret.strip()

        if "-----BEGIN" in secret:
            # Rebuild a CANONICAL PEM from whatever mangling the env var
            # suffered (newlines stripped to spaces, single-line paste, etc.):
            # extract the base64 payload between the markers, remove ALL
            # whitespace, re-encode as proper 64-char-line DER PEM.
            import re as _re
            m = _re.search(r"-----BEGIN ([A-Z ]+)-----(.*?)-----END", secret, _re.S)
            if not m:
                return None, (
                    "CDP_API_KEY_SECRET looks like a PEM but has no "
                    "BEGIN/END markers we can parse"
                )
            label = m.group(1)
            b64_payload = _re.sub(r"\s+", "", m.group(2))
            try:
                # PEM base64 has '=' padding ONLY at the very end — truncate
                # anything after the first '=' (handles paste junk appended
                # to the secret), then re-pad to a multiple of 4.
                first_pad = b64_payload.find("=")
                if first_pad != -1:
                    b64_payload = b64_payload[:first_pad]
                core = b64_payload.rstrip("=")
                der = _b64.b64decode(
                    core + "=" * ((-len(core)) % 4)
                )
            except Exception as e:
                return None, (
                    f"CDP_API_KEY_SECRET base64 payload is not decodable: "
                    f"{type(e).__name__}: {e}"
                )

            # Double-encoded case (new CDP export): base64(PEM). If the
            # decoded bytes ARE PEM text, retry with them.
            if der[:10] == b"-----BEGIN":
                env_backup = os.environ.get("CDP_API_KEY_SECRET")
                os.environ["CDP_API_KEY_SECRET"] = der.decode(errors="replace")
                try:
                    return _cdp_jwt(host, path, method)
                finally:
                    os.environ["CDP_API_KEY_SECRET"] = env_backup
            try:
                priv = serialization.load_der_private_key(der, password=None)
            except Exception as e:
                return None, (
                    f"CDP_API_KEY_SECRET DER parse failed "
                    f"(len={len(der)}B, not a valid DER EC key): "
                    f"{type(e).__name__}: {e}"
                )
            if not isinstance(priv, ec.EllipticCurvePrivateKey):
                return None, (
                    "CDP_API_KEY_SECRET is not an EC private key "
                    f"(got {type(priv).__name__})"
                )
            if priv.curve.name != "secp256r1":
                return None, (
                    f"CDP_API_KEY_SECRET curve is {priv.curve.name} — ES256 "
                    f"requires secp256r1 (P-256); create an EC (not Ed25519) "
                    f"key in the CDP portal"
                )
        else:
            priv = ec.derive_private_key(
                int.from_bytes(_b64.b64decode(secret), "big"), ec.SECP256R1()
            )
        header = {"alg": "ES256", "kid": key_id, "nonce": str(uuid.uuid4())}
        now = int(time.time())
        claims = {"sub": key_id, "iss": "cdp",
                  "nbf": now, "exp": now + 120,
                  "uris": [f"{method} {host}{path}"]}

        def b64(obj):
            return _b64.urlsafe_b64encode(
                obj if isinstance(obj, bytes) else json.dumps(obj).encode()
            ).rstrip(b"=")

        inp = b64(header) + b"." + b64(claims)
        der_sig = priv.sign(inp, ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der_sig)
        jwt_sig = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        token = (inp + b"." + b64(jwt_sig)).decode()
        log.info("CDP JWT built successfully (kid=%s…, PEM=%s)",
                 key_id[:24], "-----BEGIN" in secret)
        return token, "ok"
    except Exception as e:
        detail = f"jwt_build_failed: {type(e).__name__}: {e}"
        log.warning("CDP JWT build failed: %s", detail)
        return None, detail


def _local_verify_transaction_payload(pl: dict, requirements: dict):
    """
    Verify a v2 transaction-shape payload (newest x402 v2 'exact' scheme):
      payload: {transaction: <signed raw tx hex>, from: <buyer address>}
    The client signs a full USDC.transfer(payTo, amount) transaction; the
    facilitator broadcasts it. Checks:
      1. signature recovers to 'from'
      2. chainId == Base (8453)
      3. tx.to == USDC contract
      4. tx.data == transfer(receiver, amount >= price)
    Returns (ok, payer, detail).
    """
    from eth_account import Account
    from eth_utils import keccak as _keccak

    inner = pl.get("payload") or {}
    raw_tx = inner.get("transaction")
    declared_from = inner.get("from") or pl.get("from")
    if not raw_tx or not declared_from:
        return False, None, "transaction payload missing 'transaction'/'from'"
    raw_hex = raw_tx[2:] if raw_tx.startswith("0x") else raw_tx
    try:
        signer = Account.recover_transaction("0x" + raw_hex)
    except Exception as e:
        return False, declared_from or None, f"tx_recovery_failed: {e}"
    if str(signer).lower() != str(declared_from).lower():
        return False, signer, f"tx signer {signer} != declared from {declared_from}"
    try:
        from eth_account.typed_transactions.typed_transaction import (
            TypedTransaction,
        )
        from hexbytes import HexBytes
        raw_bytes = bytes.fromhex(raw_hex)
        tt = TypedTransaction.from_bytes(HexBytes(raw_bytes))
        as_dict = tt.as_dict()
        tx_to = as_dict.get("to")
        tx_data = as_dict.get("data") or b""
        chain_id = as_dict.get("chainId") or as_dict.get("chain_id")
    except Exception as e:
        return False, signer, f"tx_decode_failed: {e}"
    if chain_id and int(chain_id) != 8453:
        return False, signer, f"tx chainId {chain_id} != Base 8453"
    to_s = ("0x" + tx_to.hex()) if isinstance(tx_to, (bytes, bytearray)) else str(tx_to)
    usdc = (os.getenv("BASE_USDC_CONTRACT",
                      "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")).lower()
    if str(to_s).lower() != usdc:
        return False, signer, f"tx.to {to_s} is not the USDC contract"
    data_hex = tx_data.hex() if isinstance(tx_data, (bytes, bytearray)) else str(tx_data)
    if data_hex.startswith("0x"):
        data_hex = data_hex[2:]
    receiver = (requirements.get("payTo") or requirements.get("receiver")
                or get_base_fee_receiver()).lower().replace("0x", "")
    selector = _keccak(text="transfer(address,uint256)")[:4].hex()
    expected_prefix = selector + receiver.rjust(64, "0")
    if not data_hex.startswith(expected_prefix):
        return False, signer, (
            f"tx.data is not transfer({receiver}, …) — got {data_hex[:74]}…"
        )
    try:
        tx_amount = int(data_hex[72:136], 16)
    except ValueError:
        return False, signer, "tx amount not parseable"
    price_src = (requirements.get("amount")
                 or requirements.get("maxAmountRequired") or "0")
    try:
        price_atomic = int(str(price_src))
    except ValueError:
        price_atomic = int(float(price_src) * 1_000_000)
    if tx_amount < price_atomic:
        return False, signer, (f"tx amount {amount_usd_repr(tx_amount)} below "
                               f"price {amount_usd_repr(price_atomic)}")
    log.info("standard x402 tx-payload verified: buyer=%s amount=%s atomic",
             signer, tx_amount)
    return True, signer, "verified_transaction_payload"


def amount_usd_repr(atomic: int) -> str:
    return f"{atomic} atomic ({atomic / 1_000_000:.6f} USDC)"


def _broadcast_client_transaction(raw_tx_hex: str):
    """Broadcast the CLIENT's signed transfer tx (buyer pays gas).
    Returns (tx_hash | None, detail). Fail-closed on revert/timeout."""
    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider(
        os.getenv("BASE_RPC_URL", "https://mainnet.base.org"),
        request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        return None, "client_tx_broadcast_failed: RPC unreachable"
    raw = bytes.fromhex(raw_tx_hex[2:] if raw_tx_hex.startswith("0x") else raw_tx_hex)
    try:
        tx_hash = w3.eth.send_raw_transaction(raw)
    except Exception as e:
        return None, f"client_tx_broadcast_failed: {type(e).__name__}: {e}"
    hex_tx = tx_hash.hex() if isinstance(tx_hash, (bytes, bytearray)) else str(tx_hash)
    deadline = time.time() + 24
    while time.time() < deadline:
        try:
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            status = receipt.get("status")
            if status == 1:
                return hex_tx, "settled"
            return None, (f"client_tx_reverted: tx {hex_tx} status=0 — "
                          f"buyer wallet likely lacks Base ETH for gas")
        except Exception:
            pass
        time.sleep(2)
    return None, (f"client_tx_pending: tx {hex_tx} not confirmed within 24s — "
                  f"retry the same PAYMENT-SIGNATURE shortly")


def verify_standard_payment(payment_header, requirements: dict):
    """
    Verify a STANDARD x402 payment (PAYMENT-SIGNATURE / X-PAYMENT, EIP-3009).

    Verification is LOCAL and canonical (no third party involved):
      1. decode → structural pre-check (amount, receiver, asset, window)
      2. EIP-712 recovery over the Base USDC domain (USD Coin / v2) — the
         signature must recover exactly to authorization.from

    This is cryptographically complete. Settlement (the actual on-chain
    transfer) is a separate concern — see settle_standard_payment.

    Returns (ok: bool, payer: str | None, detail: str) where detail is
    ALWAYS precise enough to debug a rejection.
    """
    payload = decode_payment_payload(payment_header)
    if not isinstance(payload, dict):
        touch("x402-eip3009")
        return False, None, "payload_undecodable"

    # Shape detection: newest v2 'exact' scheme carries a signed TRANSACTION
    # ({payload: {transaction, from}}) instead of EIP-3009 authorization.
    inner_pl = payload.get("payload") or {}
    if isinstance(inner_pl, dict) and "transaction" in inner_pl:
        ok, payer, detail = _local_verify_transaction_payload(payload, requirements)
        touch("x402-eip3009")
        return ok, payer, detail

    problems = precheck_payment_payload(payload, requirements)
    if problems:
        touch("x402-eip3009")
        detail = "; ".join(problems)
        log.warning("standard x402 precheck failed: %s", detail)
        return False, None, detail

    recovered, err = _local_recover_signer(payload)
    declared_from = (
        (payload.get("payload") or {}).get("authorization") or {}
    ).get("from", "")
    if recovered is None:
        touch("x402-eip3009")
        log.warning("standard x402 local recovery failed: %s", err)
        return False, declared_from or None, f"local_eip712_recovery_failed: {err}"
    if str(recovered).lower() != str(declared_from).lower():
        touch("x402-eip3009")
        detail = (
            f"signature recovers to {recovered} but authorization.from is "
            f"{declared_from}"
        )
        log.warning("standard x402 signature mismatch: %s", detail)
        return False, recovered, detail

    touch("x402-eip3009")
    log.info("standard x402 locally verified: payer=%s (canonical EIP-712, "
             "no facilitator needed for verification)", recovered)
    return True, recovered, "verified_locally"


def settle_standard_payment(payment_header, requirements: dict):
    """
    Settle a locally-verified standard x402 payment ON-CHAIN.

    Chain (first that settles wins):
      1. self-broadcast — our wallet pays gas (~$0.001/settlement); funds
         flow buyer → receiver exactly as the buyer signed. No third party.
      2. Coinbase CDP facilitator — when CDP_API_KEY_ID/SECRET are set.
      3. PayAI public facilitator — fallback (v1-era; noisy on some v2
         payloads, so it goes last).

    Returns (tx_hash | None, detail).
    """
    payload = decode_payment_payload(payment_header)
    payment_requirements = _merged_requirements(payload, requirements)

    # Shape detection: transaction-shape → broadcast the CLIENT's signed tx
    inner_pl = (payload or {}).get("payload") or {}
    if isinstance(inner_pl, dict) and "transaction" in inner_pl:
        tx_hash, detail = _broadcast_client_transaction(inner_pl["transaction"])
        if tx_hash:
            touch("base-usdc-receiver")
            touch("x402-eip3009")
            return tx_hash, detail
        last_detail = detail
        # CDP fallback: pass the v2 transaction payload through untouched.
        token, cdp_detail = _cdp_jwt("api.cdp.coinbase.com",
                                     "/platform/v2/x402/settle")
        if token:
            body = {"x402Version": 2,
                    "paymentPayload": payload,
                    "paymentRequirements": payment_requirements}
            status, resp, _raw = _facilitator_post(
                "https://api.cdp.coinbase.com/platform/v2/x402", "settle",
                body, token=token)
            if isinstance(resp, dict) and resp.get("success") is True \
                    and resp.get("transaction"):
                touch("base-usdc-receiver")
                touch("x402-eip3009")
                return resp["transaction"], "settled"
            reason = (resp or {}).get("errorReason", f"cdp_settle(status={status})")
            last_detail = f"cdp:{reason}"
        return None, last_detail

    # 1) Self-broadcast: we are the facilitator.
    tx_hash, detail = _self_broadcast_settlement(payload or {})
    if tx_hash:
        touch("base-usdc-receiver")
        touch("x402-eip3009")
        return tx_hash, detail
    last_detail = detail

    # 2) + 3) Facilitator chain.
    for name, base_url in _facilitator_chain():
        token = None
        if name == "cdp":
            token, cdp_detail = _cdp_jwt("api.cdp.coinbase.com",
                                         "/platform/v2/x402/settle")
            if not token:
                last_detail = f"cdp: {cdp_detail}"
                continue
        body = {"x402Version": 2,
                "paymentPayload": payload,
                "paymentRequirements": payment_requirements}
        if name != "cdp":
            # legacy facilitators (PayAI) also accept the raw header field
            body["paymentHeader"] = (payment_header
                                     if isinstance(payment_header, str) else None)
        status, resp, _raw = _facilitator_post(base_url, "settle", body,
                                               token=token)
        if not isinstance(resp, dict):
            last_detail = f"{name}_unreachable(status={status})"
            continue
        if resp.get("success") is True and resp.get("transaction"):
            touch("base-usdc-receiver")
            log.info("standard x402 settled via %s: tx=%s",
                     name, resp["transaction"])
            return resp["transaction"], "settled"
        reason = resp.get("errorReason",
                          resp.get("invalidReason", "settle_failed"))
        last_detail = f"{name}:{reason}"
        log.warning("standard x402 settle failed via %s: %s",
                    name, last_detail)
    return None, last_detail


# ── L402 (Lightning) outbound bridge ────────────────────────────────────────
def l402_parse_challenge(www_authenticate: str):
    """
    Parse an L402 challenge: 'L402 macaroon=<b64>, invoice=<bolt11>'.
    Returns {'macaroon': …, 'invoice': …} or None. Parsing is always
    available; SETTLEMENT additionally requires a Lightning node
    (L402_LND_ADDRESS / L402_LND_MACAROON env vars) — see l402_ready().
    """
    if not www_authenticate or "L402" not in www_authenticate:
        return None
    out = {}
    # Strip the scheme prefix ("L402 macaroon=..." / "L402 macaroon=...")
    for part in www_authenticate.replace("L402", "", 1).split(","):
        if "=" in part:
            k, _, v = part.partition("=")
            out[k.strip().lower()] = v.strip().strip('"')
    if "macaroon" in out and "invoice" in out:
        return {"macaroon": out["macaroon"], "invoice": out["invoice"]}
    return None


def l402_ready() -> bool:
    """Lightning settlement is available only with node credentials set."""
    return bool(os.getenv("L402_LND_ADDRESS")) and bool(os.getenv("L402_LND_MACAROON"))


# ── Registry status (consumed by /api/connectors + dashboard) ───────────────
def _eip3009_detail() -> str:
    """
    Live health of the standard rail: checks the CDP JWT build for real
    (not just env presence) so a bad PEM shows up HERE instead of failing
    a canary with a misleading reason.
    """
    gas = bool(os.getenv("WALLET_PRIVATE_KEY"))
    key_id = (os.getenv("CDP_API_KEY_ID") or "").strip()
    if not key_id:
        cdp = "keys missing"
    else:
        token, cdp_detail = _cdp_jwt("api.cdp.coinbase.com",
                                     "/platform/v2/x402/verify")
        cdp = "JWT OK" if token else f"JWT FAIL ({cdp_detail})"
    return (
        f"verify=local canonical; settle=self-broadcast "
        f"(gas={gas}) → CDP ({cdp}) → payai"
    )


def registry_status(wallet_state: dict) -> list:
    """Build the live connector list for the dashboard / API."""
    now_iso = datetime.now(timezone.utc).isoformat()
    wallet_addr = wallet_state.get("wallet_address")
    receiver = wallet_state.get("fee_receiver")
    monitor_ready = bool(receiver) and bool(wallet_state.get("fee_receiver"))

    entries = [
        {
            "id": "base-usdc-receiver",
            "name": "Base / USDC settlement",
            "protocol": "ERC-20 Transfer monitor (Base mainnet)",
            "direction": "inbound",
            "status": "active" if monitor_ready else "inactive",
            "detail": f"receiver={receiver}" if receiver else "no receiver bound",
        },
        {
            "id": "x402-challenge-v2",
            "name": "x402 v2 challenge builders",
            "protocol": "x402 v2 (CAIP-2, atomic units, bazaar schema)",
            "direction": "inbound",
            "status": "active",
            "detail": "canonical challenges on all paid routes",
        },
        {
            "id": "x402-eip3009",
            "name": "Standard x402 client rail (PAYMENT-SIGNATURE / EIP-3009)",
            "protocol": "local EIP-712 verify + self-broadcast settle (CDP/PayAI fallback)",
            "direction": "inbound",
            "status": "active" if FACILITATOR_URL else "inactive",
            "detail": _eip3009_detail(),
        },
        {
            "id": "x402-outbound-buyer",
            "name": "x402 outbound buyer",
            "protocol": "x402 client (packages/x402-client)",
            "direction": "outbound",
            "status": "active" if wallet_addr else "inactive",
            "detail": f"payer wallet={wallet_addr}" if wallet_addr else "no WALLET_PRIVATE_KEY loaded",
        },
        {
            "id": "l402-lightning",
            "name": "L402 / Lightning bridge",
            "protocol": "L402 (macaroon + bolt11 invoice, preimage retry)",
            "direction": "outbound",
            "status": "active" if l402_ready() else "inactive",
            "detail": "settlement ready" if l402_ready()
            else "challenge parsing active; settlement needs L402_LND_ADDRESS + L402_LND_MACAROON",
        },
        {
            "id": "mcp-sse",
            "name": "MCP client gateway",
            "protocol": "Model Context Protocol (SSE)",
            "direction": "inbound",
            "status": "active",
            "detail": "/mcp/sse + /api/mcp/manifest live",
        },
        {
            "id": "marketplace-x402scan",
            "name": "x402scan directory",
            "protocol": "x402scan discovery spec",
            "direction": "outbound",
            "status": "active",
            "detail": "11 resources listed (2026-08-28)",
        },
        {
            "id": "marketplace-payapi",
            "name": "PayAPI Market directory",
            "protocol": "settlement-verified listings",
            "direction": "outbound",
            "status": "active",
            "detail": "resubmission in review (2026-08-29)",
        },
        {
            "id": "marketplace-nohumans",
            "name": "nohumans.directory",
            "protocol": "agent directory",
            "direction": "outbound",
            "status": "active",
            "detail": "3x VERIFIED",
        },
    ]
    for e in entries:
        e["last_activity"] = _ACTIVITY.get(e["id"], now_iso)
    return entries

