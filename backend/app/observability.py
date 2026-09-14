from __future__ import annotations

import hmac
import re
import time
import uuid
from collections.abc import Callable

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings
from app.db.session import SessionLocal
from app.models.domain import RequestMetric

PUBLIC_PATHS = {"/health", "/docs", "/docs/oauth2-redirect", "/openapi.json", "/redoc"}
_UUID_PATH_PART = re.compile(
    r"(?i)(?<![0-9a-f])[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}(?![0-9a-f])"
)


def _error_code(response: Response) -> str | None:
    if response.status_code < 400:
        return None
    return f"http_{response.status_code}"


class RequestObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        started = time.perf_counter()
        response: Response
        try:
            if self._requires_token(request) and not self._valid_token(request):
                response = JSONResponse(
                    status_code=401,
                    content={
                        "error": {
                            "code": "local_token_required",
                            "message": "a valid local access token is required",
                        }
                    },
                )
            else:
                response = await call_next(request)
        except Exception:
            response = JSONResponse(
                status_code=500,
                content={"error": {"code": "internal_error", "message": "internal server error"}},
            )
        latency_ms = max(0, round((time.perf_counter() - started) * 1000))
        response.headers["X-Request-ID"] = request_id
        self._record(request, request_id, response.status_code, latency_ms)
        return response

    @staticmethod
    def _requires_token(request: Request) -> bool:
        if not settings.local_token:
            return False
        if request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS:
            return False
        return request.url.path.startswith("/api/v1") and not request.url.path.startswith(
            "/api/v1/auth"
        )

    @staticmethod
    def _valid_token(request: Request) -> bool:
        supplied = request.headers.get("x-novel-workbench-token", "")
        return bool(supplied) and hmac.compare_digest(supplied, settings.local_token)

    @staticmethod
    def _record(request: Request, request_id: str, status_code: int, latency_ms: int) -> None:
        db = SessionLocal()
        try:
            db.add(
                RequestMetric(
                    request_id=request_id,
                    method=request.method,
                    path=_UUID_PATH_PART.sub(":id", request.url.path)[:300],
                    status_code=status_code,
                    latency_ms=latency_ms,
                    error_code=_error_code(Response(status_code=status_code)),
                )
            )
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
