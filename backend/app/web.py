"""Production extras: serve the built frontend, security headers, and a simple rate limit."""

import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


def install_security_headers(app: FastAPI) -> None:
    @app.middleware("http")
    async def headers(request: Request, call_next):
        response: Response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        return response


def install_rate_limit(app: FastAPI, per_minute: int) -> None:
    """Sliding one-minute window per client IP, API routes only. In-memory: fine for a
    single small instance; resets on restart."""
    hits: dict[str, deque[float]] = defaultdict(deque)

    @app.middleware("http")
    async def limit(request: Request, call_next):
        if not request.url.path.startswith("/api/"):
            return await call_next(request)
        forwarded = request.headers.get("x-forwarded-for", "")
        client = forwarded.split(",")[0].strip() or (request.client.host if request.client else "?")
        now = time.monotonic()
        window = hits[client]
        while window and now - window[0] > 60:
            window.popleft()
        if len(window) >= per_minute:
            return JSONResponse(
                {
                    "code": "rate_limited",
                    "message": "Too many requests; try again in a minute.",
                    "details": None,
                    "request_id": getattr(request.state, "request_id", None),
                },
                status_code=429,
                headers={"Retry-After": "60"},
            )
        window.append(now)
        if len(hits) > 10_000:  # bound memory
            hits.clear()
        return await call_next(request)


def install_frontend(app: FastAPI, static_dir: Path) -> None:
    """Serve built files; any other non-API path returns index.html (client-side routing)."""
    root = static_dir.resolve()
    index = root / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse(
                {"code": "not_found", "message": "Not found", "details": None, "request_id": None},
                status_code=404,
            )
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            cache = "public, max-age=31536000, immutable" if "-" in candidate.stem else "no-cache"
            return FileResponse(candidate, headers={"Cache-Control": cache})
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
