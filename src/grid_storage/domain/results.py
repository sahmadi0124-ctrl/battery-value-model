"""Stable, solver-independent output contract for battery dispatch results.

This module packages numerical values already extracted from a solved dispatch
problem. It intentionally exposes no optimization-library objects and does not
perform optimization or degradation calculations.
"""

from __future__ import annotations

from datetime import datetime
from math import fsum, isclose
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DispatchResult(BaseModel):
    """Immutable interval-level and aggregate results from a dispatch solve."""

    model_config = ConfigDict(frozen=True, allow_inf_nan=False)

    numerical_tolerance: ClassVar[float] = 1e-6
    """Configurable absolute tolerance used for numerical consistency checks."""

    asset_id: str = Field(description="Nonempty identifier for the battery asset.")
    scenario_id: str = Field(description="Nonempty identifier for the scenario.")
    node_id: str = Field(description="Nonempty identifier for the market node.")
    interval_start: tuple[datetime, ...] = Field(
        min_length=1,
        description="Start timestamp for each dispatch interval.",
    )
    interval_duration_hours: tuple[float, ...] = Field(
        description="Duration of each dispatch interval, in hours."
    )
    charge_mw: tuple[float, ...] = Field(
        description="Battery charging power in each interval, in MW."
    )
    discharge_mw: tuple[float, ...] = Field(
        description="Battery discharging power in each interval, in MW."
    )
    net_injection_mw: tuple[float, ...] = Field(
        description="Net grid injection in each interval, in MW."
    )
    energy_mwh: tuple[float, ...] = Field(
        description="Stored energy at all T + 1 interval boundaries, in MWh."
    )
    interval_energy_revenue_usd: tuple[float, ...] = Field(
        description="Energy-market revenue for each interval, in USD."
    )
    total_energy_revenue_usd: float = Field(
        description="Sum of interval energy-market revenue, in USD."
    )
    degradation_cost_usd: float = Field(
        description="Extracted battery degradation cost, in USD."
    )
    objective_value_usd: float = Field(
        description="Extracted Week 1 optimization objective value, in USD."
    )
    solver_name: str = Field(description="Nonempty name of the solver used.")
    solver_status: str = Field(description="Nonempty status reported by the solver.")
    termination_condition: str = Field(
        description="Nonempty solver termination condition."
    )
    solve_time_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description="Solver elapsed time in seconds, when available.",
    )

    @field_validator(
        "asset_id",
        "scenario_id",
        "node_id",
        "solver_name",
        "solver_status",
        "termination_condition",
    )
    @classmethod
    def validate_nonempty_text(cls, value: str) -> str:
        """Reject empty identifier and solver metadata fields."""
        if not value.strip():
            raise ValueError("identifier and solver metadata fields must be nonempty")
        return value

    @field_validator("interval_duration_hours")
    @classmethod
    def validate_durations(cls, value: tuple[float, ...]) -> tuple[float, ...]:
        """Require every dispatch interval to have a positive duration."""
        if any(duration <= 0.0 for duration in value):
            raise ValueError("every interval duration must be strictly positive")
        return value

    @field_validator("charge_mw", "discharge_mw")
    @classmethod
    def validate_nonnegative_power(
        cls, value: tuple[float, ...]
    ) -> tuple[float, ...]:
        """Allow only tolerance-sized negative numerical solver artifacts."""
        if any(power < -cls.numerical_tolerance for power in value):
            raise ValueError(
                "charge_mw and discharge_mw must be nonnegative within "
                "numerical_tolerance"
            )
        return value

    @model_validator(mode="after")
    def validate_result_consistency(self) -> DispatchResult:
        """Validate dimensions and Week 1 numerical accounting identities."""
        number_of_intervals = len(self.interval_start)
        interval_fields = {
            "interval_duration_hours": self.interval_duration_hours,
            "charge_mw": self.charge_mw,
            "discharge_mw": self.discharge_mw,
            "net_injection_mw": self.net_injection_mw,
            "interval_energy_revenue_usd": self.interval_energy_revenue_usd,
        }
        for field_name, values in interval_fields.items():
            if len(values) != number_of_intervals:
                raise ValueError(
                    f"{field_name} must contain exactly T={number_of_intervals} values"
                )

        if len(self.energy_mwh) != number_of_intervals + 1:
            raise ValueError(
                "energy_mwh must contain exactly T + 1 "
                f"({number_of_intervals + 1}) values"
            )

        for interval, (charge, discharge, net_injection) in enumerate(
            zip(self.charge_mw, self.discharge_mw, self.net_injection_mw)
        ):
            expected_net_injection = discharge - charge
            if not self._values_are_close(net_injection, expected_net_injection):
                raise ValueError(
                    "net_injection_mw must equal discharge_mw - charge_mw; "
                    f"values differ at interval {interval}"
                )

        expected_total_revenue = fsum(self.interval_energy_revenue_usd)
        if not self._values_are_close(
            self.total_energy_revenue_usd, expected_total_revenue
        ):
            raise ValueError(
                "total_energy_revenue_usd must equal the sum of "
                "interval_energy_revenue_usd"
            )

        expected_objective_value = (
            self.total_energy_revenue_usd - self.degradation_cost_usd
        )
        if not self._values_are_close(
            self.objective_value_usd, expected_objective_value
        ):
            raise ValueError(
                "objective_value_usd must equal total_energy_revenue_usd "
                "minus degradation_cost_usd"
            )
        return self

    @classmethod
    def _values_are_close(cls, actual: float, expected: float) -> bool:
        """Compare extracted values using the configured numerical tolerance."""
        return isclose(
            actual,
            expected,
            rel_tol=0.0,
            abs_tol=cls.numerical_tolerance,
        )

    @property
    def number_of_intervals(self) -> int:
        """Number of dispatch intervals in the result."""
        return len(self.interval_start)

    @property
    def total_charge_energy_mwh(self) -> float:
        """Total grid energy consumed while charging, in MWh."""
        return fsum(
            power * duration
            for power, duration in zip(
                self.charge_mw, self.interval_duration_hours
            )
        )

    @property
    def total_discharge_energy_mwh(self) -> float:
        """Total grid energy supplied while discharging, in MWh."""
        return fsum(
            power * duration
            for power, duration in zip(
                self.discharge_mw, self.interval_duration_hours
            )
        )
