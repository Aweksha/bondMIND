import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import errors
from app.api.v1.routes import router
from app.core.config import get_settings

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
    allow_methods=["GET"],
    allow_headers=["*"],
    expose_headers=["x-request-id"],
)
errors.install(app)
app.include_router(router)
