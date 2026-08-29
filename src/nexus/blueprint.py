"""Flask integration for the Nexus Intelligence Engine.

Exposes the secure internal strategy endpoint consumed by the NEXUS
dashboard. Authentication reuses the application's existing admin session /
X-Admin-Token machinery (deferred import avoids circular imports).
"""

from __future__ import annotations

from typing import Any, Dict

from flask import Blueprint, current_app, jsonify


def create_nexus_blueprint() -> Blueprint:
    bp = Blueprint("nexus_intel", __name__)

    @bp.get("/api/nexus/strategy")
    def nexus_strategy() -> Any:
        """Secure internal endpoint: aggregated strategic briefs for the dashboard."""
        from main import _require_admin_access  # deferred — avoids circular import

        auth_error = _require_admin_access()
        if auth_error is not None:
            return auth_error

        engine = current_app.extensions.get("nexus_engine")
        if engine is None:
            return jsonify({"ok": False, "error": "nexus_engine_not_mounted"}), 503

        payload: Dict[str, Any] = engine.build_strategy()
        return jsonify({"ok": True, **payload})

    return bp
