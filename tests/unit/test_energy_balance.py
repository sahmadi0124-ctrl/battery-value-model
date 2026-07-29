"""Tests for time indexing and energy arithmetic in the physical battery block."""

from collections.abc import Sequence
from typing import Any

import pyomo.environ as pyo
import pytest
from pyomo.opt import TerminationCondition

from grid_storage.domain.battery import BatterySpec, BatteryState
from grid_storage.optimization.battery_block import add_battery_block

SOLVER_TOLERANCE = 1.0e-7


@pytest.fixture(scope="module")
def highs_solver() -> Any:
    """Return the configured HiGHS interface or clearly skip solver tests."""
    solver = pyo.SolverFactory("highs")
    if solver is None or not solver.available(exception_flag=False):
        pytest.skip("HiGHS is required for battery energy-balance feasibility tests")
    return solver


def make_battery_spec(**overrides: object) -> BatterySpec:
    """Create a compact battery specification suitable for arithmetic tests."""
    values = {
        "asset_id": "energy-balance-battery",
        "charge_power_mw": 10.0,
        "discharge_power_mw": 10.0,
        "energy_capacity_mwh": 20.0,
        "minimum_energy_mwh": 0.0,
        "charge_efficiency": 1.0,
        "discharge_efficiency": 1.0,
        "self_discharge_per_hour": 0.0,
    }
    values.update(overrides)
    return BatterySpec(**values)


def build_and_solve(
    highs_solver: Any,
    *,
    durations: Sequence[float],
    initial_energy_mwh: float = 5.0,
    charge_mw: Sequence[float] | None = None,
    discharge_mw: Sequence[float] | None = None,
    battery_spec: BatterySpec | None = None,
) -> tuple[pyo.ConcreteModel, pyo.Block]:
    """Build a feasibility model and fix its dispatch to the supplied schedule."""
    spec = battery_spec or make_battery_spec()
    charges = tuple(charge_mw or (0.0,) * len(durations))
    discharges = tuple(discharge_mw or (0.0,) * len(durations))
    assert len(charges) == len(durations)
    assert len(discharges) == len(durations)

    model = pyo.ConcreteModel()
    battery = add_battery_block(
        model,
        battery_spec=spec,
        initial_state=BatteryState(energy_mwh=initial_energy_mwh),
        interval_duration_hours=durations,
    )
    for interval in battery.dispatch_intervals:
        battery.charge_mw[interval].fix(charges[interval])
        battery.discharge_mw[interval].fix(discharges[interval])
    model.feasibility_objective = pyo.Objective(expr=0.0)

    results = highs_solver.solve(model)
    assert results.solver.termination_condition == TerminationCondition.optimal
    return model, battery


def test_dispatch_and_state_indexing() -> None:
    model = pyo.ConcreteModel()

    battery = add_battery_block(
        model,
        battery_spec=make_battery_spec(),
        initial_state=BatteryState(energy_mwh=5.0),
        interval_duration_hours=(1.0, 0.5, 0.25),
    )

    assert list(battery.dispatch_intervals) == [0, 1, 2]
    assert list(battery.state_indices) == [0, 1, 2, 3]
    assert len(battery.charge_mw) == 3
    assert len(battery.discharge_mw) == 3
    assert len(battery.energy_mwh) == 4


def test_no_operation_keeps_energy_constant(highs_solver: Any) -> None:
    _, battery = build_and_solve(
        highs_solver,
        durations=(1.0, 0.5, 0.25),
        initial_energy_mwh=7.0,
    )

    assert [
        pyo.value(battery.energy_mwh[state]) for state in battery.state_indices
    ] == (pytest.approx([7.0, 7.0, 7.0, 7.0], abs=SOLVER_TOLERANCE))


def test_charging_efficiency_increases_stored_energy(highs_solver: Any) -> None:
    spec = make_battery_spec(charge_efficiency=0.9)

    _, battery = build_and_solve(
        highs_solver,
        durations=(0.5,),
        charge_mw=(4.0,),
        battery_spec=spec,
    )

    assert pyo.value(battery.energy_mwh[1]) == pytest.approx(
        5.0 + 1.8, abs=SOLVER_TOLERANCE
    )


def test_discharging_efficiency_reduces_stored_energy(highs_solver: Any) -> None:
    spec = make_battery_spec(discharge_efficiency=0.9)

    _, battery = build_and_solve(
        highs_solver,
        durations=(0.5,),
        discharge_mw=(1.8,),
        battery_spec=spec,
    )

    assert pyo.value(battery.energy_mwh[1]) == pytest.approx(
        5.0 - 1.0, abs=SOLVER_TOLERANCE
    )


def test_fifteen_minute_interval_uses_quarter_hour(highs_solver: Any) -> None:
    _, battery = build_and_solve(
        highs_solver,
        durations=(0.25,),
        charge_mw=(4.0,),
    )

    assert pyo.value(battery.interval_duration_hours[0]) == pytest.approx(0.25)
    assert pyo.value(battery.energy_mwh[1]) == pytest.approx(6.0, abs=SOLVER_TOLERANCE)


def test_energy_state_is_continuous_across_intervals(highs_solver: Any) -> None:
    _, battery = build_and_solve(
        highs_solver,
        durations=(0.5, 1.0, 0.25),
        charge_mw=(2.0, 0.0, 0.0),
        discharge_mw=(0.0, 1.0, 0.0),
    )

    energies = [pyo.value(battery.energy_mwh[state]) for state in battery.state_indices]
    assert energies == pytest.approx([5.0, 6.0, 5.0, 5.0], abs=SOLVER_TOLERANCE)
    assert pyo.value(battery.energy_mwh[1]) == pytest.approx(
        pyo.value(battery.energy_mwh[0]) + pyo.value(battery.charge_mw[0]) * 0.5,
        abs=SOLVER_TOLERANCE,
    )
    assert pyo.value(battery.energy_mwh[2]) == pytest.approx(
        pyo.value(battery.energy_mwh[1]) - pyo.value(battery.discharge_mw[1]) * 1.0,
        abs=SOLVER_TOLERANCE,
    )


def test_relaxed_block_applies_combined_charge_discharge_arithmetic(
    highs_solver: Any,
) -> None:
    spec = make_battery_spec(
        charge_efficiency=0.9,
        discharge_efficiency=0.9,
    )

    _, battery = build_and_solve(
        highs_solver,
        durations=(0.5,),
        charge_mw=(4.0,),
        discharge_mw=(1.8,),
        battery_spec=spec,
    )

    assert pyo.value(battery.energy_mwh[1]) == pytest.approx(
        5.0 + 1.8 - 1.0, abs=SOLVER_TOLERANCE
    )


def test_self_discharge_scales_with_interval_duration(highs_solver: Any) -> None:
    spec = make_battery_spec(self_discharge_per_hour=0.02)

    _, battery = build_and_solve(
        highs_solver,
        durations=(0.5, 0.25),
        initial_energy_mwh=10.0,
        battery_spec=spec,
    )

    expected_after_first = 10.0 * (1.0 - 0.02 * 0.5)
    expected_after_second = expected_after_first * (1.0 - 0.02 * 0.25)
    assert pyo.value(battery.energy_mwh[1]) == pytest.approx(
        expected_after_first, abs=SOLVER_TOLERANCE
    )
    assert pyo.value(battery.energy_mwh[2]) == pytest.approx(
        expected_after_second, abs=SOLVER_TOLERANCE
    )


def test_energy_balance_residual_is_below_solver_tolerance(
    highs_solver: Any,
) -> None:
    spec = make_battery_spec(
        charge_efficiency=0.9,
        discharge_efficiency=0.8,
        self_discharge_per_hour=0.01,
    )
    _, battery = build_and_solve(
        highs_solver,
        durations=(0.25, 0.5, 1.0),
        charge_mw=(4.0, 0.0, 1.0),
        discharge_mw=(0.0, 1.6, 0.5),
        battery_spec=spec,
    )

    for interval in battery.dispatch_intervals:
        duration = pyo.value(battery.interval_duration_hours[interval])
        residual = pyo.value(battery.energy_mwh[interval + 1]) - (
            pyo.value(battery.energy_mwh[interval])
            * (1.0 - spec.self_discharge_per_hour * duration)
            + spec.charge_efficiency * pyo.value(battery.charge_mw[interval]) * duration
            - pyo.value(battery.discharge_mw[interval])
            * duration
            / spec.discharge_efficiency
        )
        assert abs(residual) < SOLVER_TOLERANCE
