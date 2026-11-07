"""v2 contracts. Requests accept camelCase (as in the spec) or snake_case; responses are
snake_case like v1. Units: yields/rates in percent, shocks and spreads in basis points,
prices per 100 face, durations in years."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel


class CamelIn(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class ShockNode(CamelIn):
    tenor_years: float = Field(gt=0, le=30)
    bp: float = Field(ge=-300, le=300)


class ScenarioRequest(CamelIn):
    curve_id: str = Field(default="USD-UST-PAR", max_length=32)
    base_date: date
    security_ids: list[str] = Field(min_length=1, max_length=10)
    shock_nodes: list[ShockNode] = Field(min_length=1, max_length=20)
    spread_mode: Literal["hold_constant", "shock"] = "hold_constant"
    spread_shock_bp: float = Field(default=0, ge=-500, le=500)

    @field_validator("security_ids")
    @classmethod
    def unique_ids(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("security_ids must be unique")
        return v

    @model_validator(mode="after")
    def check(self) -> "ScenarioRequest":
        tenors = [n.tenor_years for n in self.shock_nodes]
        if len(set(tenors)) != len(tenors):
            raise ValueError("shock node tenors must be unique")
        if self.spread_mode == "hold_constant" and self.spread_shock_bp != 0:
            raise ValueError("spread_shock_bp requires spread_mode='shock'")
        return self


class CurvePointV2(BaseModel):
    tenor_months: float
    yield_pct: float | None  # None = not published on that date (never filled)


class CurveObservationSet(BaseModel):
    requested_date: date
    observed_date: date | None
    status: Literal["observed", "prior_observation", "unavailable"]
    points: list[CurvePointV2]


class CurveObservationsResponse(BaseModel):
    curve_id: str
    is_synthetic: bool
    units: dict[str, str]
    observations: list[CurveObservationSet]
    vintage: dict
    generated_at: datetime


class CurveDatesResponse(BaseModel):
    curve_id: str
    first_date: date | None
    last_date: date | None
    dates: list[date]
    tenors_months: list[float]
