# Jev Trade Gate

A reusable Python middleware that gates every trade signal through [Jev](https://openrouter.ai) (typesafe/jev-1.13) before execution. Drop it into any trading bot — decorator, middleware function, or REST API.

## Quick Start

```bash
cd ~/Projects/jev-trade-gate
python3 -m venv .venv && source .venv/bin/activate
pip install requests python-dotenv pyyaml flask

# Set your API key
cp .env.example .env
# Edit .env and set OPENROUTER_API_KEY

# Evaluate a single signal
python run.py evaluate --asset BTC --side long --size 0.1 --price 67500 --reason "EMA crossover"

# Start the REST API
python run.py serve

# View stats
python run.py stats
```

## Integration Patterns

### 1. Decorator

```python
from gate import TradeGate
from middleware import jev_gated

gate = TradeGate(api_key="sk-or-...", config=config)

@jev_gated(gate)
def execute_trade(asset, side, size, price, reason, **kwargs):
    # Your existing execution logic — only called if Jev approves
    exchange.create_order(asset, side, size)
```

### 2. Middleware Function

```python
from middleware import jev_middleware

safe_execute = jev_middleware(gate)
result = safe_execute(my_trade_fn, asset="BTC", side="long", ...)
# result = {"rejected": False, "decision": {...}, "result": ...}
```

### 3. REST API

```bash
curl -X POST http://localhost:8420/gate/evaluate \
  -H "Content-Type: application/json" \
  -d '{"asset":"BTC","side":"long","size":0.1,"price":67500,"reason":"EMA crossover"}'
```

## Jev Questions Per Signal

| # | Question | Type | Options |
|---|----------|------|---------|
| 1 | Should this trade be executed? | choice | execute-full, execute-half, execute-quarter, skip, reverse |
| 2 | Risk assessment? | score | very-low, low, medium, high, extreme |
| 3 | Is this signal likely profitable? | bool | true/false |
| 4 | Is there a better entry available? | bool | true/false |

## State Sent to Jev

- `asset` — trading pair (e.g. "BTC")
- `current_price` — signal price
- `proposed_side` — long or short
- `proposed_size` — position size
- `signal_reason` — why the signal fired
- `portfolio_context` — current holdings/risk
- `recent_price_action` — recent market movement

## REST API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/gate/evaluate` | Evaluate a trade signal |
| GET | `/gate/stats` | Evaluation statistics |
| GET | `/gate/health` | Health check |

## Configuration

Edit `config.yaml` to tune thresholds, sizing, rate limits, and logging.

## Architecture

```
Signal → TradeGate.evaluate() → JevClient → OpenRouter/Jev
                                              ↓
                              GateDecision (approve/reject + confidence)
                                              ↓
                              TradeLogger → logs/trades.jsonl
```

Fail-safe: if Jev API is unreachable, signals are **rejected** (not approved).
