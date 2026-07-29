"""Tests for the stable battery dispatch result contract."""

from datetime import datetime, timedelta, timezone
from math import inf

import pytest
from pydantic import ValidationError

from grid_storage.domain.results import DispatchResult


START = datetime(2025, 1, 1, tzinfo=timezone.utc)


def make_result(**overrides: object) -> DispatchResult:
    values = {
        "asset_id": "battery-1",
        "scenario_id": "base",
        "node_id": "NODE_A",
        "interval_start": (START, START + timedelta(hours=1)),
        "interval_duration_hours": (1.0, 1.0),
        "charge_mw": (2.0, 0.0),
        "discharge_mw": (0.0, 3.0),
        "net_injection_mw": (-2.0, 3.0),
        "energy_mwh": (5.0, 6.8, 3.5),
        "interval_energy_revenue_usd": (-40.0, 150.0),
        "total_energy_revenue_usd": 110.0,
        "degradation_cost_usd": 10.0,
        "objective_value_usd": 100.0,
        "solver_name": "highs",
        "solver_status": "ok",
        "termination_condition": "optimal",
        "solve_time_seconds": 0.25,
    }
    values.update(overrides)
    return DispatchResult(**values)


def test_valid_result() -> None:
    result = make_result()

    assert result.number_of_intervals == 2
    assert result.total_charge_energy_mwh == pytest.approx(2.0)
    assert result.total_discharge_energy_mwh == pytest.approx(3.0)


@pytest.mark.parametrize(
    "energy_mwh",
    [
        (5.0, 4.0),
        (5.0, 4.0, 3.0, 2.0),
    ],
)
def test_stored_energy_requires_t_plus_one_values(
    energy_mwh: tuple[float, ...]
) -> None:
    with pytest.raises(ValidationError, match=r"T \+ 1"):
        make_result(energy_mwh=energy_mwh)


def test_interval_series_require_t_values() -> None:
    with pytest.raises(ValidationError, match="exactly T=2"):
        make_result(charge_mw=(2.0,))


def test_inconsistent_net_injection_is_invalid() -> None:
    with pytest.raises(ValidationError, match="discharge_mw - charge_mw"):
        make_result(net_injection_mw=(-2.0, 2.5))


def test_inconsistent_total_revenue_is_invalid() -> None:
    with pytest.raises(ValidationError, match="sum"):
        make_result(total_energy_revenue_usd=109.0, objective_value_usd=99.0)


def test_inconsistent_objective_value_is_invalid() -> None:
    with pytest.raises(ValidationError, match="minus degradation_cost_usd"):
        make_result(objective_value_usd=99.0)


@pytest.mark.parametrize("field_name", ["charge_mw", "discharge_mw"])
def test_negative_power_beyond_tolerance_is_invalid(field_name: str) -> None:
    values = (-2.0e-6, 0.0)
    with pytest.raises(ValidationError, match="nonnegative"):
        make_result(**{field_name: values})


def test_tolerance_sized_negative_power_is_accepted() -> None:
    result = make_result(
        charge_mw=(-5.0e-7, 0.0),
        discharge_mw=(0.0, 3.0),
        net_injection_mw=(5.0e-7, 3.0),
    )

    assert result.charge_mw[0] == pytest.approx(-5.0e-7)


def test_nonhourly_energy_totals_multiply_power_by_duration() -> None:
    starts = tuple(START + timedelta(minutes=15 * index) for index in range(3))
    result = make_result(
        interval_start=starts,
        interval_duration_hours=(0.25, 0.25, 0.5),
        charge_mw=(4.0, 0.0, 2.0),
        discharge_mw=(0.0, 8.0, 2.0),
        net_injection_mw=(-4.0, 8.0, 0.0),
        energy_mwh=(5.0, 6.0, 4.0, 4.0),
        interval_energy_revenue_usd=(-10.0, 40.0, 0.0),
        total_energy_revenue_usd=30.0,
        degradation_cost_usd=5.0,
        objective_value_usd=25.0,
    )

    assert result.total_charge_energy_mwh == pytest.approx(2.0)
    assert result.total_discharge_energy_mwh == pytest.approx(3.0)


@pytest.mark.parametrize(
    "field_name",
    [
        "asset_id",
        "scenario_id",
        "node_id",
        "solver_name",
        "solver_status",
        "termination_condition",
    ],
)
def test_identifier_and_solver_metadata_must_be_nonempty(field_name: str) -> None:
    with pytest.raises(ValidationError, match="nonempty"):
        make_result(**{field_name: "  "})


def test_solve_time_must_be_nonnegative_when_provided() -> None:
    with pytest.raises(ValidationError):
        make_result(solve_time_seconds=-0.01)


def test_all_numerical_results_must_be_finite() -> None:
    with pytest.raises(ValidationError):
        make_result(objective_value_usd=inf)
