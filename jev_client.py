"""Jev OpenRouter client — sends state+questions, returns parsed decisions."""

import time
import logging
from typing import Any

import requests

logger = logging.getLogger("jev_trade_gate")


class JevClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/alpha/decisions",
        model: str = "typesafe/jev-1.13",
        timeout: int = 30,
        max_retries: int = 3,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    def evaluate(
        self,
        state: dict[str, Any],
        questions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Send a decision request to Jev and return parsed answers."""
        payload = {
            "model": self.model,
            "state": state,
            "questions": questions,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_err = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.post(
                    self.base_url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 2 * attempt))
                    logger.warning(f"Rate limited, retrying in {retry_after}s")
                    time.sleep(retry_after)
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.exceptions.Timeout:
                last_err = "Jev API timeout"
                logger.warning(f"Attempt {attempt}/{self.max_retries}: timeout")
                time.sleep(2 * attempt)
            except requests.exceptions.RequestException as e:
                last_err = str(e)
                logger.warning(f"Attempt {attempt}/{self.max_retries}: {e}")
                time.sleep(2 * attempt)

        raise JevAPIError(f"Jev API failed after {self.max_retries} attempts: {last_err}")

    @staticmethod
    def build_trade_state(
        asset: str,
        price: float,
        side: str,
        size: float,
        reason: str,
        portfolio_context: str = "",
        recent_price_action: str = "",
    ) -> dict[str, Any]:
        """Build the state dict for Jev from trade signal fields."""
        return {
            "asset": asset,
            "current_price": price,
            "proposed_side": side,
            "proposed_size": size,
            "signal_reason": reason,
            "portfolio_context": portfolio_context or "No additional context provided",
            "recent_price_action": recent_price_action or "No recent price action data",
        }

    @staticmethod
    def default_questions() -> list[dict[str, Any]]:
        return [
            {
                "question": "Should this trade be executed?",
                "type": "choice",
                "choices": ["execute-full", "execute-half", "execute-quarter", "skip", "reverse"],
            },
            {
                "question": "Risk assessment?",
                "type": "score",
                "labels": ["very-low", "low", "medium", "high", "extreme"],
            },
            {
                "question": "Is this signal likely profitable?",
                "type": "bool",
            },
            {
                "question": "Is there a better entry available?",
                "type": "bool",
            },
        ]


class JevAPIError(Exception):
    pass
