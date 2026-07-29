"""Domain models describing a battery's fixed specification and current state.

The models in this module contain physical data only.  Operating state is kept
separate from the fixed battery specification so it can be updated between
rolling-horizon optimization runs.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class BatteryState(BaseModel):
    """Energy state supplied at the start of an optimization run."""

    model_config = ConfigDict(frozen=True, allow_inf_nan=False)

    energy_mwh: float = Field(
        description="Stored energy at the start of the optimization run, in MWh."
    )


class BatterySpec(BaseModel):
    """Fixed physical properties of one grid-connected battery asset."""

    model_config = ConfigDict(frozen=True, allow_inf_nan=False)

    asset_id: str = Field(description="Nonempty identifier for the battery asset.")
    charge_power_mw: float = Field(
        gt=0.0,
        description="Maximum electrical charging power, in MW.",
    )
    discharge_power_mw: float = Field(
        gt=0.0,
        description="Maximum electrical discharging power, in MW.",
    )
    energy_capacity_mwh: float = Field(
        gt=0.0,
        description="Maximum stored energy, in MWh.",
    )
    minimum_energy_mwh: float = Field(
        default=0.0,
        ge=0.0,
        description="Minimum permitted stored energy, in MWh.",
    )
    charge_efficiency: float = Field(
        gt=0.0,
        le=1.0,
        description="Fraction of charging energy retained by the battery.",
    )
    discharge_efficiency: float = Field(
        gt=0.0,
        le=1.0,
        description="Fraction of withdrawn battery energy delivered to the grid.",
    )
    self_discharge_per_hour: float = Field(
        default=0.0,
        ge=0.0,
        lt=1.0,
        description="Fraction of stored energy lost to self-discharge per hour.",
    )

    @field_validator("asset_id")
    @classmethod
    def validate_asset_id(cls, value: str) -> str:
        """Reject empty identifiers, including strings containing only spaces."""
        if not value.strip():
            raise ValueError("asset_id must be nonempty")
        return value

    @model_validator(mode="after")
    def validate_energy_limits(self) -> BatterySpec:
        """Ensure the minimum energy does not exceed physical capacity."""
        if self.minimum_energy_mwh > self.energy_capacity_mwh:
            raise ValueError(
                "minimum_energy_mwh must not exceed energy_capacity_mwh"
            )
        return self

    def validate_state(self, state: BatteryState) -> BatteryState:
        """Validate and return a state that lies within this battery's limits.

        Args:
            state: Operating state to check before an optimization run.

        Raises:
            ValueError: If stored energy is below the minimum or above capacity.
        """
        if state.energy_mwh < self.minimum_energy_mwh:
            raise ValueError(
                "state energy_mwh must be greater than or equal to "
                "minimum_energy_mwh"
            )
        if state.energy_mwh > self.energy_capacity_mwh:
            raise ValueError(
                "state energy_mwh must be less than or equal to "
                "energy_capacity_mwh"
            )
        return state
