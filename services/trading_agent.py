"""
Trading agent for Kristo Intelligence v6.

Combines CoinGecko prices with Base44-guided DeFi signals to produce a
single, human-readable trading decision per token plus an aggregate
portfolio recommendation.

Risk management parameters are read from environment variables (.env):
  AGENT_AUTO_EXECUTE       — If true, execute real transactions (default: false)
  AGENT_MAX_POSITION_USD   — Maximum size of a single position (default: 1000)
  AGENT_MAX_EXPOSURE_USD   — Maximum total portfolio exposure (default: 5000)
  AGENT_MIN_APY            — Minimum APY threshold for entering a position (default: 20)
  AGENT_MAX_RISK           — Maximum risk score 0-100 (default: 60)
  AGENT_MAX_GAS_GWEI       — Maximum gas price in Gwei (default: 0.5)
"""

from __future__ import annotations

import logging
import os
from typing import Dict, List

log = logging.getLogger("kristo.v6.agent")


class TradingAgent:
    """Aggregates prices + signals into actionable decisions with risk management."""

    def __init__(self, coingecko_client=None, signals: Dict[str, dict] | None = None):
        self.cg = coingecko_client
        self.signals = signals or {}

        # ── Risk Management Parameters (read from env) ──────────────────
        self.auto_execute = os.getenv("AGENT_AUTO_EXECUTE", "false").strip().lower() == "true"
        self.max_position_usd = float(os.getenv("AGENT_MAX_POSITION_USD", "1000"))
        self.max_exposure_usd = float(os.getenv("AGENT_MAX_EXPOSURE_USD", "5000"))
        self.min_apy = float(os.getenv("AGENT_MIN_APY", "20"))
        self.max_risk = float(os.getenv("AGENT_MAX_RISK", "60"))
        self.max_gas_gwei = float(os.getenv("AGENT_MAX_GAS_GWEI", "0.5"))

        log.info(
            "Risk Management config: auto_execute=%s, max_position=$%.0f, "
            "max_exposure=$%.0f, min_apy=%.1f%%, max_risk=%.0f, max_gas=%.3f Gwei",
            self.auto_execute, self.max_position_usd, self.max_exposure_usd,
            self.min_apy, self.max_risk, self.max_gas_gwei,
        )

    # ------------------------------------------------------------------
    # Evaluation
    # ------------------------------------------------------------------
    def evaluate(self) -> Dict[str, dict]:
        """
        Evaluate all signals and produce trading decisions with risk checks.

        For each token:
        1. Fetch live price from CoinGecko
        2. Apply risk management filters (max_risk, min_apy, max_position)
        3. Generate a final action: buy / hold / monitor / avoid

        Returns a dict {token: decision_dict}.
        """
        decisions: Dict[str, dict] = {}
        total_estimated_exposure = 0.0
        prices: Dict[str, float | None] = {}
        price_status = {"state": "unavailable", "age_seconds": None}

        # One CoinGecko batch request per evaluation avoids a per-token burst
        # against the public API. The client may return explicitly marked stale
        # cache data during a rate-limit cooldown.
        if self.cg is not None and self.signals:
            try:
                prices = self.cg.get_prices(list(self.signals))
                price_status = getattr(self.cg, "last_price_status", price_status)
            except Exception as exc:
                log.debug("Batch price fetch failed: %s", exc)

        for token, signal in self.signals.items():
            price = prices.get(token)

            bias = signal.get("bias", "NEUTRAL")
            conf = float(signal.get("confidence", 0.5))
            action = signal.get("action", "monitor")
            risk_score = float(signal.get("risk_score", 50))
            apy = float(signal.get("apy", 0))

            # Simple rule overlay: if no price available, downgrade confidence.
            if price is None:
                conf *= 0.8
                note = "no live price — reduced confidence"
            elif price_status.get("state") == "stale":
                conf *= 0.9
                age = price_status.get("age_seconds")
                age_note = f", age={age}s" if age is not None else ""
                note = f"stale cached price=${price:.4f}{age_note} — reduced confidence"
            else:
                note = f"price=${price:.4f}"

            # ── Risk Management Checks ──────────────────────────────────
            risk_flags: List[str] = []
            final_action = action
            approved = True

            # Check 1: Risk score exceeds maximum
            if risk_score > self.max_risk:
                risk_flags.append(f"RISK_TOO_HIGH: {risk_score:.0f} > {self.max_risk:.0f}")
                final_action = "avoid"
                approved = False

            # Check 2: APY below minimum threshold (for yield positions)
            if "yield" in action.lower() or "farm" in action.lower():
                if apy < self.min_apy:
                    risk_flags.append(f"APY_TOO_LOW: {apy:.1f}% < {self.min_apy:.1f}%")
                    final_action = "monitor"
                    approved = False

            # Check 3: Position size would exceed max_position
            suggested_position_usd = self._calculate_position_size(price, conf)
            if suggested_position_usd > self.max_position_usd:
                suggested_position_usd = self.max_position_usd
                risk_flags.append(f"POSITION_CAPPED: ${suggested_position_usd:.2f} (max=${self.max_position_usd:.0f})")

            # Check 4: Total exposure would exceed max_exposure
            if total_estimated_exposure + suggested_position_usd > self.max_exposure_usd:
                remaining = self.max_exposure_usd - total_estimated_exposure
                if remaining <= 0:
                    risk_flags.append(f"EXPOSURE_FULL: ${total_estimated_exposure:.2f} >= ${self.max_exposure_usd:.0f}")
                    final_action = "hold"
                    approved = False
                    suggested_position_usd = 0.0
                else:
                    suggested_position_usd = remaining
                    risk_flags.append(f"EXPOSURE_LIMITED: ${suggested_position_usd:.2f} remaining")

            # Check 5: Gas price check (would need live gas data)
            # This is a placeholder — actual gas check happens in wallet.py
            gas_flag = os.getenv("_CURRENT_GAS_GWEI", "")
            if gas_flag:
                gas_val = float(gas_flag)
                if gas_val > self.max_gas_gwei:
                    risk_flags.append(f"GAS_TOO_HIGH: {gas_val:.3f} > {self.max_gas_gwei:.3f} Gwei")
                    final_action = "wait"
                    approved = False

            # If auto_execute is false, downgrade all actions to recommendations
            if not self.auto_execute and approved and final_action not in ("monitor", "hold", "avoid", "wait"):
                final_action = f"recommend_{final_action}"

            # ── One-line buyer-facing reason (PayAPI reviewer feedback) ──
            # Names the MAIN driver behind the action instead of repeating
            # the price.  The narrative is the primary driver; live-data
            # state and the first risk flag are appended when they change
            # the call.  Kept to one line for easy agent consumption.
            narrative = (signal.get("narrative") or "").strip()
            reasoning = narrative or f"{bias.lower()} bias at {conf:.0%} confidence"
            if price is None:
                reasoning += "; live price unavailable — confidence reduced"
            elif price_status.get("state") == "stale":
                reasoning += "; price from stale cache — verify before sizing"
            if risk_flags:
                reasoning += "; " + risk_flags[0]

            total_estimated_exposure += suggested_position_usd

            decisions[token] = {
                "symbol": signal.get("symbol", token.upper()),
                "price_usd": price,
                "bias": bias,
                "confidence": round(conf, 3),
                "action": final_action,
                "approved": approved,
                "risk_score": risk_score,
                "risk_flags": risk_flags,
                "suggested_position_usd": round(suggested_position_usd, 2),
                "narrative": signal.get("narrative", ""),
                "reasoning": reasoning,
                "note": note,
                "market_data_status": price_status.get("state"),
                "source": signal.get("source", "baseline"),
            }

        # Log portfolio summary
        self._log_summary(decisions, total_estimated_exposure)
        return decisions

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _calculate_position_size(self, price: float | None, confidence: float) -> float:
        """
        Calculate suggested position size in USD based on confidence and max_position.
        Higher confidence → larger position (up to max_position_usd).
        """
        if price is None or price <= 0:
            return 0.0
        # Scale position by confidence: 0.0 conf → $0, 1.0 conf → max_position
        base_size = self.max_position_usd * confidence
        return base_size

    def _log_summary(self, decisions: Dict[str, dict], total_exposure: float) -> None:
        """Log a summary of all decisions and portfolio status."""
        log.info("--- Trading decisions ---")
        for tok, d in decisions.items():
            status = "✅" if d["approved"] else "❌"
            log.info(
                "  %s %s | %s | %s | conf=%.2f | risk=%.0f | pos=$%.2f | %s",
                status, d["symbol"], d["bias"], d["action"],
                d["confidence"], d["risk_score"], d["suggested_position_usd"],
                d["note"],
            )
            if d["risk_flags"]:
                for flag in d["risk_flags"]:
                    log.warning("    ⚠️  %s", flag)

        log.info(
            "--- Portfolio: total_exposure=$%.2f / $%.0f (max) | auto_execute=%s ---",
            total_exposure, self.max_exposure_usd, self.auto_execute,
        )