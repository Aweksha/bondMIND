import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import errors
from app.api.v1.routes import router
from app.api.v2.routes import router as router_v2
from app.core.config import get_settings
from app.web import install_frontend, install_rate_limit, install_security_headers

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

settings = get_settings()
app = FastAPI(
    title="bondMIND AI API",
    version="0.1.0",
    description=(
        "Fixed-income research API. Decision-support research tool; not investment advice. "
        "Responses carry `context.is_synthetic`; synthetic demo data is not market data. "
        "Yields are percent, prices are clean per 100 face, dates are ISO-8601, "
        "timestamps UTC."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
    expose_headers=["x-request-id"],
)
errors.install(app)
app.include_router(router)
app.include_router(router_v2)
install_security_headers(app)
if settings.rate_limit_per_minute > 0:
    install_rate_limit(app, settings.rate_limit_per_minute)
if settings.static_dir and (settings.static_dir / "index.html").exists():
    install_frontend(app, settings.static_dir)  # must be last: catch-all route
