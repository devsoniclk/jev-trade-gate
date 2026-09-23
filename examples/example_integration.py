#!/usr/bin/env python3
"""
Example: wrapping an existing trading bot with Jev Trade Gate.

Shows three integration patterns:
1. Decorator (@jev_gated)
2. Middleware function (jev_middleware)
3. Direct gate.evaluate()
"""

import os
import sys
import json

# Add parent dir to path so we can import the gate modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from gate import TradeGate, TradeSignal
from middleware import jev_gated, jev_middleware, GateRejectedError
from logger import TradeLogger

import yaml

# Load config
config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
with open(config_path) as f:
    config = yaml.safe_load(f)

api_key = os.environ.get("OPENROUTER_API_KEY", "demo-key")

trade_logger = TradeLogger(log_file="logs/trades.jsonl", enabled=True)
gate = TradeGate(api_key=api_key, config=config, trade_logger=trade_logger)


# ── Pattern 1: Decorator ─────────────────────────────────────────────

@jev_gated(gate)
def execute_trade_decorated(asset: str, side: str, size: float, price: float, reason: str, **kwargs):
    """Your existing trade execution function."""
    print(f"  → EXECUTING: {side} {size} {asset} @ {price}")
    return {"status": "filled", "asset": asset, "size": size}


# ── Pattern 2: Middleware function ────────────────────────────────────

def execute_trade_raw(asset: str, side: str, size: float, price: float, reason: str, **kwargs):
    """Another existing trade function."""
    print(f"  → EXECUTING: {side} {size} {asset} @ {price}")
    return {"status": "filled", "asset": asset, "size": size}

safe_execute = jev_middleware(gate)


# ── Pattern 3: Direct evaluation ─────────────────────────────────────

def evaluate_only(signal: TradeSignal):
    """Just evaluate without executing — for logging/monitoring."""
    decision = gate.evaluate(signal)
    print(f"  Decision: {decision.action} (confidence={decision.confidence}, risk={decision.risk})")
    return decision


# ── Demo ─────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Jev Trade Gate — Integration Examples")
    print("=" * 60)

    # Example signal
    print("\n[1] Decorator pattern:")
    try:
        result = execute_trade_decorated(
            asset="BTC", side="long", size=0.1, price=67500.0,
            reason="EMA crossover on 4h chart",
            portfolio_context="70% cash, 30% ETH",
            recent_price_action="BTC up 3% in 24h",
        )
        if result:
            print(f"  Result: {result}")
        else:
            print("  Trade was rejected by Jev gate")
    except GateRejectedError as e:
        print(f"  Rejected: {e}")

    print("\n[2] Middleware pattern:")
    result = safe_execute(
        execute_trade_raw,
        asset="ETH", side="short", size=1.0, price=3450.0,
        reason="Bearish divergence on RSI",
        portfolio_context="50% BTC, 50% cash",
        recent_price_action="ETH down 5% in 48h",
    )
    print(f"  Result: {json.dumps(result, indent=2, default=str)}")

    print("\n[3] Direct evaluation (no execution):")
    signal = TradeSignal(
        asset="SOL", side="long", size=10.0, price=145.0,
        reason="Breakout above resistance at $142",
        portfolio_context="Diversified, 20% alt exposure",
        recent_price_action="SOL up 12% this week, volume increasing",
    )
    evaluate_only(signal)

    print("\n[4] Stats:")
    stats = trade_logger.get_stats()
    print(f"  {json.dumps(stats, indent=2)}")


if __name__ == "__main__":
    main()
