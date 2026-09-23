"""JSONL trade logger for Jev Trade Gate."""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class TradeLogger:
    def __init__(self, log_file: str = "logs/trades.jsonl", enabled: bool = True):
        self.enabled = enabled
        self.log_file = log_file
        if self.enabled:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    def log(self, event_type: str, data: dict[str, Any]) -> None:
        if not self.enabled:
            return
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "epoch": time.time(),
            "event": event_type,
            **data,
        }
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def log_signal(self, signal: dict, decision: dict) -> None:
        self.log("gate_evaluation", {"signal": signal, "decision": decision})

    def log_error(self, context: str, error: str) -> None:
        self.log("error", {"context": context, "error": error})

    def read_all(self) -> list[dict]:
        if not os.path.exists(self.log_file):
            return []
        entries = []
        with open(self.log_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries

    def get_stats(self) -> dict:
        entries = self.read_all()
        evaluations = [e for e in entries if e.get("event") == "gate_evaluation"]
        total = len(evaluations)
        if total == 0:
            return {"total_evaluations": 0, "approved": 0, "rejected": 0, "approval_rate": 0.0}

        approved = sum(
            1 for e in evaluations
            if e.get("decision", {}).get("action") in ("execute-full", "execute-half", "execute-quarter")
        )
        rejected = sum(
            1 for e in evaluations
            if e.get("decision", {}).get("action") in ("skip", "reverse")
        )
        errors = sum(1 for e in entries if e.get("event") == "error")

        action_counts = {}
        for e in evaluations:
            action = e.get("decision", {}).get("action", "unknown")
            action_counts[action] = action_counts.get(action, 0) + 1

        risk_counts = {}
        for e in evaluations:
            risk = e.get("decision", {}).get("risk", "unknown")
            risk_counts[risk] = risk_counts.get(risk, 0) + 1

        return {
            "total_evaluations": total,
            "approved": approved,
            "rejected": rejected,
            "errors": errors,
            "approval_rate": round(approved / total, 4) if total else 0.0,
            "action_breakdown": action_counts,
            "risk_breakdown": risk_counts,
        }
