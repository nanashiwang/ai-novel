"""应用级异常 + FastAPI 统一异常处理。

返回结构：
```
{ "error": { "code": "...", "message": "...", "details": {...} } }
```
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    """业务异常基类。"""

    code: str = "app_error"
    status_code: int = status.HTTP_400_BAD_REQUEST

    def __init__(self, message: str, *, code: str | None = None, details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code:
            self.code = code


class NotFoundError(AppError):
    code = "not_found"
    status_code = status.HTTP_404_NOT_FOUND


class PermissionDenied(AppError):
    code = "permission_denied"
    status_code = status.HTTP_403_FORBIDDEN


class QuotaInsufficient(AppError):
    code = "quota_insufficient"
    status_code = status.HTTP_402_PAYMENT_REQUIRED


def _wrap_error(code: str, message: str, details: Any = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_wrap_error(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        # 兼容老式 detail：将其作为 code
        message = exc.detail if isinstance(exc.detail, str) else "http_error"
        code = message if isinstance(exc.detail, str) else "http_error"
        return JSONResponse(
            status_code=exc.status_code,
            content=_wrap_error(code, message, None),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_wrap_error("validation_error", "request_validation_failed", exc.errors()),
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        import logging

        logging.getLogger(__name__).exception("unhandled_exception")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_wrap_error("internal_error", "服务器内部错误", None),
        )
