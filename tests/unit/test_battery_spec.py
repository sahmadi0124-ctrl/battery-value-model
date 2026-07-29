"""Tests for battery specification and operating-state domain models."""

import pytest
from pydantic import ValidationError

from grid_storage.domain.battery import BatterySpec, BatteryState


def make_battery(**overrides: object) -> BatterySpec:
    values = {
        "asset_id": "battery-1",
        "charge_power_mw": 50.0,
        "discharge_power_mw": 45.0,
        "energy_capacity_mwh": 200.0,
        "minimum_energy_mwh": 20.0,
        "charge_efficiency": 0.95,
        "discharge_efficiency": 0.94,
        "self_discharge_per_hour": 0.001,
    }
    values.update(overrides)
    return BatterySpec(**values)


def test_valid_battery_and_state() -> None:
    battery = make_battery()
    state = BatteryState(energy_mwh=100.0)

    assert battery.validate_state(state) is state
    assert battery.asset_id == "battery-1"
    assert state.energy_mwh == 100.0


@pytest.mark.parametrize("asset_id", ["", "   "])
def test_empty_asset_id_is_invalid(asset_id: str) -> None:
    with pytest.raises(ValidationError):
        make_battery(asset_id=asset_id)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("charge_power_mw", 0.0),
        ("charge_power_mw", -1.0),
        ("discharge_power_mw", 0.0),
        ("discharge_power_mw", -1.0),
        ("energy_capacity_mwh", 0.0),
        ("energy_capacity_mwh", -1.0),
    ],
)
def test_power_and_capacity_must_be_positive(
    field_name: str, invalid_value: float
) -> None:
    with pytest.raises(ValidationError):
        make_battery(**{field_name: invalid_value})


@pytest.mark.parametrize("field_name", ["charge_efficiency", "discharge_efficiency"])
@pytest.mark.parametrize("invalid_value", [0.0, -0.1, 1.01])
def test_efficiencies_must_be_in_valid_range(
    field_name: str, invalid_value: float
) -> None:
    with pytest.raises(ValidationError):
        make_battery(**{field_name: invalid_value})


def test_minimum_energy_above_capacity_is_invalid() -> None:
    with pytest.raises(ValidationError):
        make_battery(energy_capacity_mwh=100.0, minimum_energy_mwh=100.1)


@pytest.mark.parametrize("invalid_value", [-0.001, 1.0, 1.1])
def test_self_discharge_must_be_in_valid_range(invalid_value: float) -> None:
    with pytest.raises(ValidationError):
        make_battery(self_discharge_per_hour=invalid_value)


def test_state_below_minimum_is_invalid_for_battery() -> None:
    battery = make_battery()

    with pytest.raises(ValueError, match="minimum_energy_mwh"):
        battery.validate_state(BatteryState(energy_mwh=19.999))


def test_state_above_capacity_is_invalid_for_battery() -> None:
    battery = make_battery()

    with pytest.raises(ValueError, match="energy_capacity_mwh"):
        battery.validate_state(BatteryState(energy_mwh=200.001))


@pytest.mark.parametrize("energy_mwh", [20.0, 200.0])
def test_state_at_exact_energy_boundary_is_valid(energy_mwh: float) -> None:
    battery = make_battery()
    state = BatteryState(energy_mwh=energy_mwh)

    assert battery.validate_state(state) == state
