"""External market conditions supplied to a battery optimization model.

Scenarios may later be populated from synthetic data, historical observations,
forecasts, or an endogenous market model.  This module only defines the pure
domain contract for those external conditions.
"""

from __future__ import annotations

from datetime import datetime
from math import fsum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MarketScenario(BaseModel):
    """Immutable time series of external market conditions for optimization."""

    model_config = ConfigDict(frozen=True, allow_inf_nan=False)

    scenario_id: str = Field(description="Nonempty identifier for the scenario.")
    node_id: str = Field(description="Nonempty identifier for the market node.")
    interval_start: tuple[datetime, ...] = Field(
        min_length=1,
        description="Timezone-aware start timestamp for each market interval.",
    )
    interval_duration_hours: tuple[float, ...] = Field(
        description="Duration of each market interval, in hours."
    )
    energy_price_per_mwh: tuple[float, ...] = Field(
        description="Energy price in each interval, in currency units per MWh."
    )
    probability: float = Field(
        default=1.0,
        gt=0.0,
        le=1.0,
        description="Probability assigned to this scenario.",
    )

    @field_validator("scenario_id", "node_id")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        """Reject empty identifiers, including strings containing only spaces."""
        if not value.strip():
            raise ValueError("identifier must be nonempty")
        return value

    @field_validator("interval_duration_hours")
    @classmethod
    def validate_durations(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        """Require every market interval to have a positive duration."""
        if any(duration <= 0.0 for duration in value):
            raise ValueError("every interval duration must be strictly positive")
        return value

    @field_validator("interval_start")
    @classmethod
    def validate_timestamps(
        cls, value: tuple[datetime, ...]
    ) -> tuple[datetime, ...]:
        """Require timezone-aware, unique, and strictly increasing timestamps."""
        if any(
            timestamp.tzinfo is None or timestamp.utcoffset() is None
            for timestamp in value
        ):
            raise ValueError("every interval_start timestamp must be timezone-aware")
        if any(current >= following for current, following in zip(value, value[1:])):
            raise ValueError(
                "interval_start timestamps must be unique and strictly increasing"
            )
        return value

    @model_validator(mode="after")
    def validate_collection_lengths(self) -> MarketScenario:
        """Ensure duration and price series align with the timestamp series."""
        number_of_intervals = len(self.interval_start)
        if len(self.interval_duration_hours) != number_of_intervals:
            raise ValueError(
                "interval_duration_hours must have the same length as interval_start"
            )
        if len(self.energy_price_per_mwh) != number_of_intervals:
            raise ValueError(
                "energy_price_per_mwh must have the same length as interval_start"
            )
        return self

    @property
    def number_of_intervals(self) -> int:
        """Number of market intervals in the scenario."""
        return len(self.interval_start)

    @property
    def horizon_hours(self) -> float:
        """Total scenario horizon, in hours."""
        return fsum(self.interval_duration_hours)
