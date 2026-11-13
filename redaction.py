"""Credential scrubbing for anything that leaves the process.

WHY THIS IS ITS OWN MODULE
--------------------------
The scrubber used to live in `integrations/dashboard_store.py`, which is a heavy
module (sqlite3, psycopg, the whole store). That made it awkward to use from the
places that need it most — `blockchain/wallet.py` and `services/base_listener.py`
raise `ConnectionError(f"Cannot connect to Base RPC at {rpc_url}")`, and an RPC
provider puts its API key IN that URL. So the exception text carried the
credential, and whether it leaked depended entirely on whether the caller
happened to wrap it. That is the same defect as "the log line is redacted but
the persisted detail is not": the secret is in the message, and the message
travels.

Redaction belongs at the point where the text is CREATED, not only where it is
printed. This module has no dependencies beyond the standard library so that
every layer can import it without dragging the store along.

WHAT IT CATCHES
---------------
1. RPC provider keys embedded in a URL path or query:
     https://base-mainnet.g.alchemy.com/v2/<KEY>   ->  .../v2/***
     https://x.io/rpc?apikey=<KEY>                 ->  ...?apikey=***
     https://x.io/rpc?token=<KEY>                  ->  ...?token=***
2. Passwords in connection URLs, where the credential is the password half of
   `scheme://user:password@host`:
     postgresql://user:<PASSWORD>@host:5432/db     ->  postgresql://user:***@host:5432/db
     redis://default:<PASSWORD>@cache:6379         ->  redis://default:***@cache:6379

The host and user are KEPT: an error that says only "***" is not diagnosable,
and a warning nobody can act on is its own defect.

WHAT IT DOES NOT CATCH
----------------------
A bare 64-hex private key with no surrounding context. There is no reliable way
to tell one from a transaction hash or a signature, and a rule that guessed
would corrupt legitimate output. Keys must not be put into exception text in the
first place.
"""

from __future__ import annotations

import re
from typing import Any

#: RPC providers embed the API key in the URL, e.g.
#: `https://base-mainnet.g.alchemy.com/v2/<KEY>`. Logging a raw httpx exception
#: (or our own "RPC not reachable: {url}") therefore writes the credential into
#: the log stream. Keep the host, drop the secret.
#:
#: The last two alternatives are the same defect in other shapes:
#:   * `https://quiknode.pro/<KEY>/` — the key is a PATH SEGMENT with no
#:     `/v2/` or `apikey=` marker in front of it.
#:   * `https://api.telegram.org/bot<id>:<token>/...` — the bot token is a
#:     path segment, not a query parameter.
_RPC_KEY_RE = re.compile(
    r"(/v[0-9]+/|apikey=|api-key=|key=|token=|quiknode\.pro/|bot[0-9]+:)"
    r"([A-Za-z0-9_\-]{6,})",
    re.I,
)

#: The same argument applies to connection URLs, where the credential is the
#: password half of `scheme://user:password@host`. A psycopg/redis exception
#: echoes the DSN it failed to reach, so an unredacted `str(exc)` on a public
#: surface publishes the database password. `[^/\s@:]+` stops at the first
#: delimiter, so a DSN inside a longer message is matched without swallowing the
#: surrounding text.
_URL_CRED_RE = re.compile(r"(://[^/\s@:]+:)([^/\s@:]+)(@)")


def redact_rpc(text: Any) -> str:
    """Return `text` with any embedded RPC API key or DSN password replaced by ***."""
    out = _RPC_KEY_RE.sub(lambda m: m.group(1) + "***", str(text))
    return _URL_CRED_RE.sub(lambda m: m.group(1) + "***" + m.group(3), out)
