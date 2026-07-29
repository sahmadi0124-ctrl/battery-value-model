"""Reusable Pyomo block containing the battery's physical formulation.

All time-dependent parameters, variables, and constraints are local to the
returned block.  Economic terms, terminal-energy policy, solver calls, and
result extraction belong to optimization-problem assembly layers.
"""

from __future__ import annotations

from collections.abc import Sequence
from math import isfinite

import pyomo.environ as pyo

from grid_storage.domain.battery import BatterySpec, BatteryState


def add_battery_block(
    model: pyo.ConcreteModel,
    *,
    battery_spec: BatterySpec,
    initial_state: BatteryState,
    interval_duration_hours: Sequence[float],
    enforce_exclusive_operation: bool = False,
    block_name: str = "battery",
) -> pyo.Block:
    """Attach and return a reusable physical battery block.

    Dispatch intervals are indexed from ``0`` through ``T - 1`` and stored
    energy states are indexed at interval boundaries from ``0`` through ``T``.
    Power variables use MW, energy variables use MWh, and interval durations
    use hours.

    Args:
        model: Concrete Pyomo model that will own the block.
        battery_spec: Validated fixed physical properties of the battery.
        initial_state: Stored energy at the beginning of state index zero.
        interval_duration_hours: Positive, finite duration of each dispatch
            interval, in hours.
        enforce_exclusive_operation: Whether to add a binary operating mode
            that prevents simultaneous charging and discharging.
        block_name: Component name used to attach the block to ``model``.

    Returns:
        The physical battery block attached to ``model``.

    Raises:
        ValueError: If the initial state violates the battery limits, no
            intervals are supplied, an interval duration is invalid, or
            ``block_name`` is already attached to the model.
    """
    battery_spec.validate_state(initial_state)

    durations = tuple(float(duration) for duration in interval_duration_hours)
    if not durations:
        raise ValueError("interval_duration_hours must contain at least one interval")
    if any(not isfinite(duration) or duration <= 0.0 for duration in durations):
        raise ValueError("every interval duration must be finite and strictly positive")
    if model.component(block_name) is not None:
        raise ValueError(f"model already contains a component named {block_name!r}")

    number_of_intervals = len(durations)
    block = pyo.Block(
        concrete=True,
        doc="Physical battery variables and constraints for one dispatch horizon.",
    )

    block.dispatch_intervals = pyo.RangeSet(
        0,
        number_of_intervals - 1,
        doc="Dispatch interval indices t = 0, ..., T - 1.",
    )
    block.state_indices = pyo.RangeSet(
        0,
        number_of_intervals,
        doc="Stored-energy boundary indices s = 0, ..., T.",
    )
    block.interval_duration_hours = pyo.Param(
        block.dispatch_intervals,
        initialize=dict(enumerate(durations)),
        within=pyo.PositiveReals,
        mutable=False,
        doc="Duration of dispatch interval t, in hours.",
    )

    block.charge_mw = pyo.Var(
        block.dispatch_intervals,
        domain=pyo.NonNegativeReals,
        doc="Nonnegative grid-side charging power in interval t, in MW.",
    )
    block.discharge_mw = pyo.Var(
        block.dispatch_intervals,
        domain=pyo.NonNegativeReals,
        doc="Nonnegative grid-side discharging power in interval t, in MW.",
    )
    block.energy_mwh = pyo.Var(
        block.state_indices,
        domain=pyo.NonNegativeReals,
        doc="Stored energy at state boundary s, in MWh.",
    )

    block.charge_power_limit = pyo.Constraint(
        block.dispatch_intervals,
        rule=lambda battery, interval: (
            battery.charge_mw[interval] <= battery_spec.charge_power_mw
        ),
        doc="Maximum charging-power constraint for each interval t, in MW.",
    )
    block.discharge_power_limit = pyo.Constraint(
        block.dispatch_intervals,
        rule=lambda battery, interval: (
            battery.discharge_mw[interval] <= battery_spec.discharge_power_mw
        ),
        doc="Maximum discharging-power constraint for each interval t, in MW.",
    )
    block.minimum_energy_limit = pyo.Constraint(
        block.state_indices,
        rule=lambda battery, state: (
            battery.energy_mwh[state] >= battery_spec.minimum_energy_mwh
        ),
        doc="Minimum stored-energy constraint at each state boundary s, in MWh.",
    )
    block.maximum_energy_limit = pyo.Constraint(
        block.state_indices,
        rule=lambda battery, state: (
            battery.energy_mwh[state] <= battery_spec.energy_capacity_mwh
        ),
        doc="Maximum stored-energy constraint at each state boundary s, in MWh.",
    )
    block.initial_energy = pyo.Constraint(
        expr=block.energy_mwh[0] == initial_state.energy_mwh,
        doc="Initial stored energy at state boundary zero, in MWh.",
    )

    def energy_transition_rule(battery: pyo.Block, interval: int) -> pyo.Constraint:
        """Return the MWh energy-balance equality for dispatch interval ``t``."""
        duration = battery.interval_duration_hours[interval]
        return battery.energy_mwh[interval + 1] == (
            battery.energy_mwh[interval]
            * (1.0 - battery_spec.self_discharge_per_hour * duration)
            + battery_spec.charge_efficiency * battery.charge_mw[interval] * duration
            - battery.discharge_mw[interval]
            * duration
            / battery_spec.discharge_efficiency
        )

    block.energy_transition = pyo.Constraint(
        block.dispatch_intervals,
        rule=energy_transition_rule,
        doc=(
            "Stored-energy transition for each interval t, linking state "
            "boundaries t and t + 1 in MWh."
        ),
    )

    if enforce_exclusive_operation:
        block.operating_mode = pyo.Var(
            block.dispatch_intervals,
            domain=pyo.Binary,
            doc=(
                "Binary direction in interval t: zero permits charging and one "
                "permits discharging."
            ),
        )
        block.exclusive_charge_limit = pyo.Constraint(
            block.dispatch_intervals,
            rule=lambda battery, interval: (
                battery.charge_mw[interval]
                <= battery_spec.charge_power_mw
                * (1.0 - battery.operating_mode[interval])
            ),
            doc="Charging-mode constraint for each interval t, in MW.",
        )
        block.exclusive_discharge_limit = pyo.Constraint(
            block.dispatch_intervals,
            rule=lambda battery, interval: (
                battery.discharge_mw[interval]
                <= battery_spec.discharge_power_mw * battery.operating_mode[interval]
            ),
            doc="Discharging-mode constraint for each interval t, in MW.",
        )

    model.add_component(block_name, block)
    return block
