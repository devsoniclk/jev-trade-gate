#!/usr/bin/env python3
"""CLI for Jev Trade Gate: serve, evaluate (one-shot), stats."""

import argparse
import json
import os
import sys

from dotenv import load_dotenv
import yaml


def load_config():
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    if os.path.exists(config_path):
        with open(config_path) as f:
            return yaml.safe_load(f) or {}
    return {}


def cmd_serve(args, config):
    from server import create_app
    app = create_app(config)
    host = args.host or config.get("server", {}).get("host", "0.0.0.0")
    port = args.port or config.get("server", {}).get("port", 8420)
    debug = config.get("server", {}).get("debug", False)
    print(f"Starting Jev Trade Gate on {host}:{port}")
    app.run(host=host, port=port, debug=debug)


def cmd_evaluate(args, config):
    from gate import TradeGate, TradeSignal
    from logger import TradeLogger

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("Error: OPENROUTER_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    log_cfg = config.get("logging", {})
    t_logger = TradeLogger(
        log_file=log_cfg.get("file", "logs/trades.jsonl"),
        enabled=log_cfg.get("enabled", True),
    )
    gate = TradeGate(api_key=api_key, config=config, trade_logger=t_logger)

    if args.json:
        data = json.loads(args.json)
    else:
        data = {
            "asset": args.asset,
            "side": args.side,
            "size": float(args.size),
            "price": float(args.price),
            "reason": args.reason,
        }

    signal = TradeSignal(
        asset=data["asset"], side=data["side"], size=data["size"],
        price=data["price"], reason=data["reason"],
        portfolio_context=data.get("portfolio_context", ""),
        recent_price_action=data.get("recent_price_action", ""),
    )
    decision = gate.evaluate(signal)
    result = {"signal": data, "decision": decision.to_dict()}
    print(json.dumps(result, indent=2))


def cmd_stats(args, config):
    from logger import TradeLogger
    log_cfg = config.get("logging", {})
    t_logger = TradeLogger(
        log_file=log_cfg.get("file", "logs/trades.jsonl"),
        enabled=True,
    )
    stats = t_logger.get_stats()
    print(json.dumps(stats, indent=2))


def main():
    load_dotenv()
    config = load_config()

    parser = argparse.ArgumentParser(description="Jev Trade Gate CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # serve
    p_serve = sub.add_parser("serve", help="Start the REST API server")
    p_serve.add_argument("--host", type=str, default=None)
    p_serve.add_argument("--port", type=int, default=None)

    # evaluate
    p_eval = sub.add_parser("evaluate", help="Evaluate a single trade signal")
    p_eval.add_argument("--json", type=str, help="Full signal as JSON string")
    p_eval.add_argument("--asset", type=str, default="BTC")
    p_eval.add_argument("--side", type=str, default="long")
    p_eval.add_argument("--size", type=str, default="0.1")
    p_eval.add_argument("--price", type=str, default="0")
    p_eval.add_argument("--reason", type=str, default="manual test")

    # stats
    sub.add_parser("stats", help="Show evaluation statistics")

    args = parser.parse_args()
    {"serve": cmd_serve, "evaluate": cmd_evaluate, "stats": cmd_stats}[args.command](args, config)


if __name__ == "__main__":
    main()
