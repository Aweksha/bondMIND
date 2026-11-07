import logging
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

log = logging.getLogger("bondmind.api")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        self.status, self.code, self.message, self.details = status, code, message, details


def _body(request: Request, code: str, message: str, details=None) -> dict:
    return {
        "code": code,
        "message": message,
        "details": details,
        "request_id": getattr(request.state, "request_id", None),
    }


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_id(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["x-request-id"] = rid
        return response

    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError):
        return JSONResponse(_body(request, exc.code, exc.message, exc.details), exc.status)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse(_body(request, "http_error", str(exc.detail)), exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        details = [{"loc": e["loc"], "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse(_body(request, "validation_error", "Invalid request", details), 422)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        log.exception("unhandled error request_id=%s", getattr(request.state, "request_id", ""))
        return JSONResponse(_body(request, "internal_error", "Internal server error"), 500)
