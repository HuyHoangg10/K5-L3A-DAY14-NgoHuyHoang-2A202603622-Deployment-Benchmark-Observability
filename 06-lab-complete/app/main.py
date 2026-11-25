"""
Production AI Agent — Part 6 Final Project
"""
import json
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import redis_healthy
from utils.mock_llm import ask as llm_ask


# Structured logging (tiêu chí 10): Mọi dòng log là JSON hợp lệ
class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        return json.dumps(log_obj, ensure_ascii=False)


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
logger = logging.getLogger("agent")


# Lifespan context manager for graceful shutdown (tiêu chí 11)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Agent process started successfully")
    yield
    # Shutdown on SIGTERM
    logger.info("Agent received shutdown signal (SIGTERM), cleaning up resources...")


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


# Middleware ghi log request dạng JSON (tiêu chí 10)
@app.middleware("http")
async def json_logging_middleware(request: Request, call_next):
    start_time = time.time()
    try:
        response = await call_next(request)
        duration_ms = round((time.time() - start_time) * 1000, 2)
        log_data = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": "INFO",
            "event": "request",
            "path": request.url.path,
            "status": response.status_code,
            "ms": duration_ms,
        }
        print(json.dumps(log_data), flush=True)
        return response
    except Exception as exc:
        duration_ms = round((time.time() - start_time) * 1000, 2)
        log_data = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": "ERROR",
            "event": "request_error",
            "path": request.url.path,
            "error": str(exc),
            "ms": duration_ms,
        }
        print(json.dumps(log_data), flush=True)
        raise exc


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


# Liveness: luôn trả 200 khi app đang chạy (tiêu chí 4)
@app.get("/health")
def health():
    return {"status": "healthy"}


# Readiness: trả 200 khi Redis kết nối được, 503 khi Redis mất kết nối (tiêu chí 5)
@app.get("/ready")
def ready():
    if redis_healthy():
        return {"status": "ready", "redis": "connected"}
    return JSONResponse(
        status_code=503,
        content={"status": "not_ready", "error": "Redis connection failed"},
    )


# Main endpoint (tiêu chí 6, 7, 8)
@app.post("/ask")
def ask(
    body: AskRequest,
    api_key: str = Depends(verify_api_key),
):
    # Check rate limit (tiêu chí 7) -> 429
    check_rate_limit(api_key)

    # Check cost budget (tiêu chí 8) -> 402
    check_budget()

    # Call LLM
    answer = llm_ask(body.question)

    # Approximate token calculation and record cost
    input_tokens = max(1, len(body.question) // 4)
    output_tokens = max(1, len(answer) // 4)
    record_cost(input_tokens, output_tokens)

    return {"question": body.question, "answer": answer}
