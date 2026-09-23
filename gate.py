"""Core TradeGate — evaluates signals through Jev and returns approve/reject decisions."""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from jev_client import JevClient, JevAPIError
from logger import TradeLogger

logger = logging.getLogger("jev_trade_gate")


@dataclass
class TradeSignal:
    asset: str
    side: str  # "long" or "short"
    size: float
    price: float
    reason: str
    portfolio_context: str = ""
    recent_price_action: str = ""


@dataclass
class GateDecision:
    action: str  # execute-full, execute-half, execute-quarter, skip, reverse
    risk: str  # very-low, low, medium, high, extreme
    likely_profitable: Optional[bool]
    better_entry_available: Optional[bool]
    confidence: float
    size_multiplier: float
    approved: bool
    raw: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "risk": self.risk,
            "likely_profitable": self.likely_profitable,
            "better_entry_available": self.better_entry_available,
            "confidence": self.confidence,
            "size_multiplier": self.size_multiplier,
            "approved": self.approved,
        }


class TradeGate:
    def __init__(
        self,
        api_key: str,
        config: Optional[dict] = None,
        trade_logger: Optional[TradeLogger] = None,
    ):
        cfg = config or {}
        gate_cfg = cfg.get("gate", {})
        or_cfg = cfg.get("openrouter", {})
        rl_cfg = cfg.get("rate_limit", {})

        self.client = JevClient(
            api_key=api_key,
            base_url=or_cfg.get("base_url", "https://openrouter.ai/api/alpha/decisions"),
            model=or_cfg.get("model", "typesafe/jev-1.13"),
            timeout=or_cfg.get("timeout", 30),
            max_retries=or_cfg.get("max_retries", 3),
        )
        self.auto_approve = gate_cfg.get("auto_approve_threshold", 0.85)
        self.auto_reject = gate_cfg.get("auto_reject_threshold", 0.20)
        self.sizing_map = gate_cfg.get("sizing_map", {
            "execute-full": 1.0, "execute-half": 0.5, "execute-quarter": 0.25,
            "skip": 0.0, "reverse": -1.0,
        })
        self.per_asset_cooldown = rl_cfg.get("per_asset_cooldown", 5)
        self.trade_logger = trade_logger or TradeLogger(enabled=False)
        self._last_eval: dict[str, float] = {}  # asset -> epoch

    def evaluate(self, signal: TradeSignal) -> GateDecision:
        """Evaluate a trade signal through Jev. Returns a GateDecision."""
        # Cooldown check
        now = time.time()
        last = self._last_eval.get(signal.asset, 0)
        if now - last < self.per_asset_cooldown:
            logger.info(f"Cooldown active for {signal.asset}, skipping")
            return GateDecision(
                action="skip", risk="medium", likely_profitable=None,
                better_entry_available=None, confidence=0.0, size_multiplier=0.0, approved=False,
            )

        state = self.client.build_trade_state(
            asset=signal.asset, price=signal.price, side=signal.side,
            size=signal.size, reason=signal.reason,
            portfolio_context=signal.portfolio_context,
            recent_price_action=signal.recent_price_action,
        )
        questions = self.client.default_questions()

        try:
            raw = self.client.evaluate(state, questions)
        except JevAPIError as e:
            logger.error(f"Jev API error: {e}")
            self.trade_logger.log_error("gate.evaluate", str(e))
            # Fail-safe: reject on API failure
            return GateDecision(
                action="skip", risk="extreme", likely_profitable=None,
                better_entry_available=None, confidence=0.0, size_multiplier=0.0,
                approved=False, raw={"error": str(e)},
            )

        self._last_eval[signal.asset] = now

        decision = self._parse_decision(raw)
        self.trade_logger.log_signal(
            signal={"asset": signal.asset, "side": signal.side, "size": signal.size,
                    "price": signal.price, "reason": signal.reason},
            decision=decision.to_dict(),
        )
        return decision

    def _parse_decision(self, raw: dict) -> GateDecision:
        """Parse Jev response into a GateDecision."""
        answers = raw.get("answers", raw.get("decisions", []))
        if not answers:
            answers = raw.get("results", [])

        # Extract answers by position (matching our question order)
        action = "skip"
        risk = "medium"
        likely_profitable = None
        better_entry = None

        for i, ans in enumerate(answers):
            val = ans.get("answer", ans.get("value", ans.get("choice", "")))
            if i == 0:  # Should this trade be executed?
                action = str(val) if val else "skip"
            elif i == 1:  # Risk assessment
                risk = str(val) if val else "medium"
            elif i == 2:  # Likely profitable
                likely_profitable = _to_bool(val)
            elif i == 3:  # Better entry available
                better_entry = _to_bool(val)

        # Compute confidence score
        confidence = self._compute_confidence(action, risk, likely_profitable, better_entry)
        size_mult = self.sizing_map.get(action, 0.0)
        approved = action in ("execute-full", "execute-half", "execute-quarter")

        return GateDecision(
            action=action, risk=risk, likely_profitable=likely_profitable,
            better_entry_available=better_entry, confidence=confidence,
            size_multiplier=size_mult, approved=approved, raw=raw,
        )

    def _compute_confidence(
        self, action: str, risk: str, profitable: Optional[bool], better_entry: Optional[bool]
    ) -> float:
        score = 0.5
        action_scores = {"execute-full": 0.3, "execute-half": 0.15, "execute-quarter": 0.05, "skip": -0.2, "reverse": -0.3}
        score += action_scores.get(action, 0.0)
        risk_scores = {"very-low": 0.15, "low": 0.1, "medium": 0.0, "high": -0.1, "extreme": -0.2}
        score += risk_scores.get(risk, 0.0)
        if profitable is True:
            score += 0.1
        elif profitable is False:
            score -= 0.1
        if better_entry is True:
            score -= 0.05
        return round(max(0.0, min(1.0, score)), 4)


def _to_bool(val: Any) -> Optional[bool]:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "yes", "1")
    if isinstance(val, (int, float)):
        return bool(val)
    return None
