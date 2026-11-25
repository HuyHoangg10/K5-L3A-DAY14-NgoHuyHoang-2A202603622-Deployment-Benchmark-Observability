"""
Cost guard (tiêu chí 8).
"""
import os
from fastapi import HTTPException
from app.config import settings
from app.redis_client import get_redis_client

PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    client = get_redis_client()
    if client is None:
        return

    budget = float(os.getenv("DAILY_BUDGET_USD", os.getenv("MONTHLY_BUDGET_USD", str(settings.daily_budget_usd))))
    try:
        total = float(client.get("total_llm_cost") or 0.0)
        if total >= budget:
            raise HTTPException(
                status_code=402,
                detail=f"Daily budget exceeded: ${total:.6f} >= ${budget:.6f}",
            )
    except HTTPException:
        raise
    except Exception:
        pass


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    cost = (input_tokens / 1000.0) * PRICE_INPUT_PER_1K + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    client = get_redis_client()
    if client is not None:
        try:
            client.incrbyfloat("total_llm_cost", cost)
        except Exception:
            pass
    return cost
