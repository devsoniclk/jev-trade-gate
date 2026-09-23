"""Flask REST API for Jev Trade Gate."""

import os
import logging
from functools import wraps
from time import time
from typing import Optional

from flask import Flask, request, jsonify

from gate import TradeGate, TradeSignal
from logger import TradeLogger

logger = logging.getLogger("jev_trade_gate")

app = Flask(__name__)
gate = None  # type: Optional[TradeGate]
trade_logger = None  # type: Optional[TradeLogger]
_rate_buckets: dict[str, list[float]] = {}


def init_app(gate_instance: TradeGate, logger_instance: TradeLogger) -> Flask:
    global gate, trade_logger
    gate = gate_instance
    trade_logger = logger_instance
    return app


def rate_limit(per_minute: int):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            now = time()
            bucket = _rate_buckets.setdefault(f.__name__, [])
            bucket[:] = [t for t in bucket if now - t < 60]
            if len(bucket) >= per_minute:
                return jsonify({"error": "Rate limit exceeded", "retry_after": 1}), 429
            bucket.append(now)
            return f(*args, **kwargs)
        return wrapper
    return decorator


@app.route("/gate/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": "jev-trade-gate",
        "version": "1.0.0",
    })


@app.route("/gate/evaluate", methods=["POST"])
@rate_limit(60)
def evaluate():
    if gate is None:
        return jsonify({"error": "Gate not initialized"}), 503

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON body required"}), 400

    required = ("asset", "side", "size", "price", "reason")
    missing = [k for k in required if k not in data]
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 400

    try:
        signal = TradeSignal(
            asset=str(data["asset"]),
            side=str(data["side"]),
            size=float(data["size"]),
            price=float(data["price"]),
            reason=str(data["reason"]),
            portfolio_context=str(data.get("portfolio_context", "")),
            recent_price_action=str(data.get("recent_price_action", "")),
        )
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid field types: {e}"}), 400

    try:
        decision = gate.evaluate(signal)
    except Exception as e:
        logger.exception("Evaluation error")
        return jsonify({"error": f"Evaluation failed: {e}"}), 500

    return jsonify({
        "signal": {
            "asset": signal.asset,
            "side": signal.side,
            "size": signal.size,
            "price": signal.price,
            "reason": signal.reason,
        },
        "decision": decision.to_dict(),
    })


@app.route("/gate/stats", methods=["GET"])
def stats():
    if trade_logger is None:
        return jsonify({"error": "Logger not initialized"}), 503
    return jsonify(trade_logger.get_stats())


def create_app(config: Optional[dict] = None) -> Flask:
    """Factory for creating the app with configuration."""
    from dotenv import load_dotenv
    load_dotenv()

    import yaml
    if config is None:
        config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
        if os.path.exists(config_path):
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
        else:
            config = {}

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable required")

    log_cfg = config.get("logging", {})
    t_logger = TradeLogger(
        log_file=log_cfg.get("file", "logs/trades.jsonl"),
        enabled=log_cfg.get("enabled", True),
    )
    g = TradeGate(api_key=api_key, config=config, trade_logger=t_logger)
    return init_app(g, t_logger)
