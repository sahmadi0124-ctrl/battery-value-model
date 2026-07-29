"""Tests for physical limits and separation in the reusable battery block."""

from collections.abc import Sequence
from inspect import signature
from math import inf, nan
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
        pytest.skip(
            "HiGHS is required for battery dispatch-constraint feasibility tests"
        )
    return solver


def make_battery_spec(**overrides: object) -> BatterySpec:
    """Create a small battery with limits that are convenient to exercise."""
    values = {
        "asset_id": "dispatch-constraint-battery",
        "charge_power_mw": 4.0,
        "discharge_power_mw": 3.0,
        "energy_capacity_mwh": 10.0,
        "minimum_energy_mwh": 1.0,
        "charge_efficiency": 1.0,
        "discharge_efficiency": 1.0,
        "self_discharge_per_hour": 0.0,
    }
    values.update(overrides)
    return BatterySpec(**values)


def build_model(
    *,
    durations: Sequence[float] = (1.0,),
    initial_energy_mwh: float = 5.0,
    battery_spec: BatterySpec | None = None,
    enforce_exclusive_operation: bool = False,
    block_name: str = "battery",
) -> tuple[pyo.ConcreteModel, pyo.Block]:
    """Build a battery feasibility model without solving it."""
    model = pyo.ConcreteModel()
    battery = add_battery_block(
        model,
        battery_spec=battery_spec or make_battery_spec(),
        initial_state=BatteryState(energy_mwh=initial_energy_mwh),
        interval_duration_hours=durations,
        enforce_exclusive_operation=enforce_exclusive_operation,
        block_name=block_name,
    )
    model.feasibility_objective = pyo.Objective(expr=0.0)
    return model, battery


def fix_dispatch(
    battery: pyo.Block,
    *,
    charge_mw: Sequence[float],
    discharge_mw: Sequence[float],
) -> None:
    """Fix all interval power variables to a candidate physical schedule."""
    assert len(charge_mw) == len(battery.dispatch_intervals)
    assert len(discharge_mw) == len(battery.dispatch_intervals)
    for interval in battery.dispatch_intervals:
        battery.charge_mw[interval].fix(charge_mw[interval])
        battery.discharge_mw[interval].fix(discharge_mw[interval])


def assert_optimal(highs_solver: Any, model: pyo.ConcreteModel) -> None:
    """Solve a feasible model and assert optimal termination."""
    results = highs_solver.solve(model)
    assert results.solver.termination_condition == TerminationCondition.optimal


def assert_infeasible(highs_solver: Any, model: pyo.ConcreteModel) -> None:
    """Solve without loading a solution and assert infeasible termination."""
    results = highs_solver.solve(model, load_solutions=False)
    assert results.solver.termination_condition == TerminationCondition.infeasible


def test_valid_inputs_create_attached_usable_block(highs_solver: Any) -> None:
    model, battery = build_model(durations=(1.0, 0.25))
    fix_dispatch(
        battery,
        charge_mw=(0.0, 0.0),
        discharge_mw=(0.0, 0.0),
    )

    assert model.battery is battery
    assert list(battery.dispatch_intervals) == [0, 1]
    assert list(battery.state_indices) == [0, 1, 2]
    assert battery.interval_duration_hours.mutable is False
    assert_optimal(highs_solver, model)


def test_schedule_at_charging_power_limit_is_feasible(highs_solver: Any) -> None:
    model, battery = build_model(durations=(0.5,))
    fix_dispatch(battery, charge_mw=(4.0,), discharge_mw=(0.0,))

    assert_optimal(highs_solver, model)
    assert pyo.value(battery.charge_mw[0]) == pytest.approx(4.0, abs=SOLVER_TOLERANCE)


def test_schedule_above_charging_power_limit_is_infeasible(
    highs_solver: Any,
) -> None:
    model, battery = build_model(durations=(0.5,))
    fix_dispatch(battery, charge_mw=(4.01,), discharge_mw=(0.0,))

    assert_infeasible(highs_solver, model)


def test_schedule_at_discharging_power_limit_is_feasible(
    highs_solver: Any,
) -> None:
    model, battery = build_model()
    fix_dispatch(battery, charge_mw=(0.0,), discharge_mw=(3.0,))

    assert_optimal(highs_solver, model)
    assert pyo.value(battery.discharge_mw[0]) == pytest.approx(
        3.0, abs=SOLVER_TOLERANCE
    )


def test_schedule_above_discharging_power_limit_is_infeasible(
    highs_solver: Any,
) -> None:
    model, battery = build_model()
    fix_dispatch(battery, charge_mw=(0.0,), discharge_mw=(3.01,))

    assert_infeasible(highs_solver, model)


def test_stored_energy_may_reach_exact_capacity(highs_solver: Any) -> None:
    model, battery = build_model(initial_energy_mwh=6.0)
    fix_dispatch(battery, charge_mw=(4.0,), discharge_mw=(0.0,))

    assert_optimal(highs_solver, model)
    assert pyo.value(battery.energy_mwh[1]) == pytest.approx(10.0, abs=SOLVER_TOLERANCE)


def test_schedule_exceeding_energy_capacity_is_infeasible(
    highs_solver: Any,
) -> None:
    model, battery = build_model(initial_energy_mwh=7.0)
    fix_dispatch(battery, charge_mw=(4.0,), discharge_mw=(0.0,))

    assert_infeasible(highs_solver, model)


def test_stored_energy_may_reach_exact_minimum(highs_solver: Any) -> None:
    model, battery = build_model(initial_energy_mwh=4.0)
    fix_dispatch(battery, charge_mw=(0.0,), discharge_mw=(3.0,))

    assert_optimal(highs_solver, model)
    assert pyo.value(battery.energy_mwh[1]) == pytest.approx(1.0, abs=SOLVER_TOLERANCE)


def test_schedule_below_minimum_energy_is_infeasible(highs_solver: Any) -> None:
    model, battery = build_model(initial_energy_mwh=3.0)
    fix_dispatch(battery, charge_mw=(0.0,), discharge_mw=(3.0,))

    assert_infeasible(highs_solver, model)


def test_initial_energy_equals_supplied_battery_state(highs_solver: Any) -> None:
    model, battery = build_model(initial_energy_mwh=4.25)
    fix_dispatch(battery, charge_mw=(0.0,), discharge_mw=(0.0,))

    assert_optimal(highs_solver, model)
    assert pyo.value(battery.energy_mwh[0]) == pytest.approx(4.25, abs=SOLVER_TOLERANCE)


@pytest.mark.parametrize(
    ("initial_energy_mwh", "message"),
    [
        (0.99, "minimum_energy_mwh"),
        (10.01, "energy_capacity_mwh"),
    ],
)
def test_invalid_initial_state_is_rejected(
    initial_energy_mwh: float, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        build_model(initial_energy_mwh=initial_energy_mwh)


@pytest.mark.parametrize("durations", [(), (0.0,), (-0.25,), (nan,), (inf,)])
def test_invalid_interval_durations_are_rejected(
    durations: tuple[float, ...],
) -> None:
    with pytest.raises(ValueError, match="interval|duration"):
        build_model(durations=durations)


def test_exclusive_mode_adds_binary_operating_mode() -> None:
    _, battery = build_model(enforce_exclusive_operation=True)

    assert hasattr(battery, "operating_mode")
    assert all(
        battery.operating_mode[interval].is_binary()
        for interval in battery.dispatch_intervals
    )


def test_exclusive_mode_rejects_simultaneous_operation(
    highs_solver: Any,
) -> None:
    model, battery = build_model(enforce_exclusive_operation=True)
    fix_dispatch(battery, charge_mw=(1.0,), discharge_mw=(1.0,))

    assert_infeasible(highs_solver, model)


def test_exclusive_mode_permits_charging_only(highs_solver: Any) -> None:
    model, battery = build_model(enforce_exclusive_operation=True)
    fix_dispatch(battery, charge_mw=(2.0,), discharge_mw=(0.0,))

    assert_optimal(highs_solver, model)
    assert pyo.value(battery.operating_mode[0]) == pytest.approx(0.0)


def test_exclusive_mode_permits_discharging_only(highs_solver: Any) -> None:
    model, battery = build_model(enforce_exclusive_operation=True)
    fix_dispatch(battery, charge_mw=(0.0,), discharge_mw=(2.0,))

    assert_optimal(highs_solver, model)
    assert pyo.value(battery.operating_mode[0]) == pytest.approx(1.0)


def test_relaxed_mode_has_no_binary_variables() -> None:
    _, battery = build_model(enforce_exclusive_operation=False)

    binary_variables = [
        variable
        for variable in battery.component_data_objects(
            pyo.Var, active=True, descend_into=True
        )
        if variable.is_binary()
    ]
    assert binary_variables == []
    assert not hasattr(battery, "operating_mode")


def test_relaxed_mode_permits_simultaneous_operation(highs_solver: Any) -> None:
    model, battery = build_model(enforce_exclusive_operation=False)
    fix_dispatch(battery, charge_mw=(1.0,), discharge_mw=(1.0,))

    assert_optimal(highs_solver, model)


def test_duplicate_block_name_is_rejected() -> None:
    model = pyo.ConcreteModel()
    spec = make_battery_spec()
    state = BatteryState(energy_mwh=5.0)
    add_battery_block(
        model,
        battery_spec=spec,
        initial_state=state,
        interval_duration_hours=(1.0,),
        block_name="asset",
    )

    with pytest.raises(ValueError, match="already contains.*asset"):
        add_battery_block(
            model,
            battery_spec=spec,
            initial_state=state,
            interval_duration_hours=(1.0,),
            block_name="asset",
        )


def test_physical_block_has_no_objective_price_or_terminal_policy() -> None:
    model = pyo.ConcreteModel()
    battery = add_battery_block(
        model,
        battery_spec=make_battery_spec(),
        initial_state=BatteryState(energy_mwh=5.0),
        interval_duration_hours=(1.0, 0.5),
    )

    assert (
        list(
            battery.component_data_objects(
                pyo.Objective, active=True, descend_into=True
            )
        )
        == []
    )
    assert "price" not in signature(add_battery_block).parameters
    assert all(
        "price" not in component.local_name.lower()
        for component in battery.component_objects(descend_into=True)
    )
    assert all(
        "terminal" not in component.local_name.lower()
        for component in battery.component_objects(descend_into=True)
    )
    assert battery.energy_mwh[2].fixed is False


def test_builder_does_not_call_a_solver(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_solver_call(*args: object, **kwargs: object) -> None:
        raise AssertionError("the physical battery builder must not call a solver")

    monkeypatch.setattr(pyo, "SolverFactory", unexpected_solver_call)

    model = pyo.ConcreteModel()
    battery = add_battery_block(
        model,
        battery_spec=make_battery_spec(),
        initial_state=BatteryState(energy_mwh=5.0),
        interval_duration_hours=(1.0,),
    )

    assert model.battery is battery
