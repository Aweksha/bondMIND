from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, PlainSerializer

T = TypeVar("T")

# Financial values are stored as exact decimals and serialized as JSON numbers.
Num = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DataContext(ApiModel):
    """Attached to every data response so the UI can always show provenance."""

    is_synthetic: bool
    as_of: date | None
    generated_at: datetime


class Page(ApiModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    context: DataContext


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict | list | None = None
    request_id: str | None = None
