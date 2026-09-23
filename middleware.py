"""Drop-in decorator/middleware for existing trading bots."""

import functools
import logging
from typing import Callable, Any, Optional

from gate import TradeGate, TradeSignal, GateDecision

logger = logging.getLogger("jev_trade_gate")


def jev_gated(gate: TradeGate, on_reject: str = "skip"):
    """
    Decorator that gates a trade execution function through Jev.

    Usage:
        gate = TradeGate(api_key="...", config=config)

        @jev_gated(gate)
        def execute_trade(asset, side, size, price, reason, **kwargs):
            # actual execution logic
            return {"status": "executed", ...}

    The decorated function's kwargs are inspected for signal fields.
    If the gate rejects, the original function is NOT called.

    on_reject: "skip" (return None), "raise" (raise GateRejectedError), or "callback"
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            signal = _extract_signal(kwargs)
            if signal is None:
                logger.warning("Could not extract trade signal from kwargs, passing through")
                return func(*args, **kwargs)

            decision = gate.evaluate(signal)
            if not decision.approved:
                logger.info(f"Trade REJECTED by Jev: {signal.asset} {signal.side} → {decision.action}")
                if on_reject == "raise":
                    raise GateRejectedError(signal, decision)
                return None

            # Inject adjusted size
            adjusted_size = signal.size * decision.size_multiplier
            kwargs["size"] = adjusted_size
            kwargs["_jev_decision"] = decision
            logger.info(f"Trade APPROVED by Jev: {signal.asset} {signal.side} size={adjusted_size:.4f}")
            return func(*args, **kwargs)
        return wrapper
    return decorator


def jev_middleware(gate: TradeGate) -> Callable:
    """
    Returns a function that wraps any trade-execution callable.
    Useful for bots that don't use decorators.

    Usage:
        gate = TradeGate(api_key="...", config=config)
        safe_execute = jev_middleware(gate)
        result = safe_execute(execute_trade, asset="BTC", side="long", ...)
    """
    def wrapper(func: Callable, **kwargs) -> Any:
        signal = _extract_signal(kwargs)
        if signal is None:
            return func(**kwargs)

        decision = gate.evaluate(signal)
        if not decision.approved:
            return {"rejected": True, "decision": decision.to_dict()}

        kwargs["size"] = signal.size * decision.size_multiplier
        result = func(**kwargs)
        return {"rejected": False, "decision": decision.to_dict(), "result": result}
    return wrapper


class GateRejectedError(Exception):
    def __init__(self, signal: TradeSignal, decision: GateDecision):
        self.signal = signal
        self.decision = decision
        super().__init__(
            f"Gate rejected {signal.asset} {signal.side}: {decision.action} (risk={decision.risk})"
        )


def _extract_signal(kwargs: dict) -> Optional[TradeSignal]:
    """Try to build a TradeSignal from keyword arguments."""
    required = ("asset", "side", "size", "price", "reason")
    if not all(k in kwargs for k in required):
        return None
    return TradeSignal(
        asset=str(kwargs["asset"]),
        side=str(kwargs["side"]),
        size=float(kwargs["size"]),
        price=float(kwargs["price"]),
        reason=str(kwargs["reason"]),
        portfolio_context=str(kwargs.get("portfolio_context", "")),
        recent_price_action=str(kwargs.get("recent_price_action", "")),
    )
