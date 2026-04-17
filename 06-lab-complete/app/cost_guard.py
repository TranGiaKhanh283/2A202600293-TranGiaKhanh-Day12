"""
Cost guard — track daily LLM spend and cut off when the budget is exhausted.

Single-process implementation using module-level state. For multi-replica
deployments, persist the counter in Redis:

    key   = f"cost:{YYYY-MM-DD}"
    INCRBYFLOAT key <delta>   # after each call
    GET key                   # before each call
"""
import time
from fastapi import HTTPException

from app.config import settings

# Pricing for GPT-4o-mini as of 2025 (USD per 1K tokens)
_INPUT_PRICE_PER_1K = 0.00015
_OUTPUT_PRICE_PER_1K = 0.0006

_daily_cost: float = 0.0
_cost_reset_day: str = time.strftime("%Y-%m-%d")


def _roll_over_if_new_day() -> None:
    global _daily_cost, _cost_reset_day
    today = time.strftime("%Y-%m-%d")
    if today != _cost_reset_day:
        _daily_cost = 0.0
        _cost_reset_day = today


def check_and_record_cost(input_tokens: int, output_tokens: int) -> None:
    """
    Raise 503 if the daily budget is exhausted, otherwise charge the estimated
    cost of this call and continue.
    """
    global _daily_cost

    _roll_over_if_new_day()

    if _daily_cost >= settings.daily_budget_usd:
        raise HTTPException(
            status_code=503,
            detail="Daily budget exhausted. Try tomorrow.",
        )

    cost = (input_tokens / 1000) * _INPUT_PRICE_PER_1K \
         + (output_tokens / 1000) * _OUTPUT_PRICE_PER_1K
    _daily_cost += cost


def current_spend() -> float:
    _roll_over_if_new_day()
    return _daily_cost


def reset() -> None:
    """Test helper — clear daily spend."""
    global _daily_cost
    _daily_cost = 0.0
