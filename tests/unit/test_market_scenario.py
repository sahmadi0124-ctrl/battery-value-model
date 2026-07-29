"""Tests for the external market scenario domain model."""

from datetime import datetime, timedelta, timezone
from math import inf, nan

import pytest
from pydantic import ValidationError

from grid_storage.domain.scenarios import MarketScenario


START = datetime(2025, 1, 1, tzinfo=timezone.utc)


def make_scenario(**overrides: object) -> MarketScenario:
    values = {
        "scenario_id": "base",
        "node_id": "NODE_A",
        "interval_start": (START, START + timedelta(hours=1)),
        "interval_duration_hours": (1.0, 1.0),
        "energy_price_per_mwh": (25.0, 50.0),
        "probability": 1.0,
    }
    values.update(overrides)
    return MarketScenario(**values)


def test_valid_hourly_scenario() -> None:
    scenario = make_scenario()

    assert scenario.number_of_intervals == 2
    assert scenario.horizon_hours == pytest.approx(2.0)


def test_valid_fifteen_minute_scenario() -> None:
    starts = tuple(START + timedelta(minutes=15 * index) for index in range(4))
    scenario = make_scenario(
        interval_start=starts,
        interval_duration_hours=(0.25,) * 4,
        energy_price_per_mwh=(10.0, 20.0, 30.0, 40.0),
    )

    assert scenario.number_of_intervals == 4
    assert scenario.horizon_hours == pytest.approx(1.0)


def test_negative_energy_prices_are_valid() -> None:
    scenario = make_scenario(energy_price_per_mwh=(-30.0, 0.0))

    assert scenario.energy_price_per_mwh == (-30.0, 0.0)


@pytest.mark.parametrize(
    ("field_name", "values"),
    [
        ("interval_duration_hours", (1.0,)),
        ("energy_price_per_mwh", (25.0,)),
    ],
)
def test_mismatched_collection_lengths_are_invalid(
    field_name: str, values: tuple[float, ...]
) -> None:
    with pytest.raises(ValidationError, match="same length"):
        make_scenario(**{field_name: values})


@pytest.mark.parametrize("duration", [0.0, -0.25])
def test_nonpositive_interval_duration_is_invalid(duration: float) -> None:
    with pytest.raises(ValidationError):
        make_scenario(interval_duration_hours=(duration, 1.0))


@pytest.mark.parametrize("price", [nan, inf, -inf])
def test_nonfinite_energy_price_is_invalid(price: float) -> None:
    with pytest.raises(ValidationError):
        make_scenario(energy_price_per_mwh=(price, 10.0))


def test_naive_timestamp_is_invalid() -> None:
    naive_start = datetime(2025, 1, 1)

    with pytest.raises(ValidationError, match="timezone-aware"):
        make_scenario(
            interval_start=(naive_start, naive_start + timedelta(hours=1))
        )


@pytest.mark.parametrize(
    "timestamps",
    [
        (START, START),
        (START + timedelta(hours=1), START),
    ],
)
def test_duplicate_or_unsorted_timestamps_are_invalid(
    timestamps: tuple[datetime, ...]
) -> None:
    with pytest.raises(ValidationError, match="strictly increasing"):
        make_scenario(interval_start=timestamps)


@pytest.mark.parametrize("probability", [0.0, -0.1, 1.01])
def test_invalid_probability_is_rejected(probability: float) -> None:
    with pytest.raises(ValidationError):
        make_scenario(probability=probability)


def test_interval_count_and_nonhourly_horizon_are_correct() -> None:
    starts = tuple(START + timedelta(minutes=5 * index) for index in range(3))
    scenario = make_scenario(
        interval_start=starts,
        interval_duration_hours=(1.0 / 12.0,) * 3,
        energy_price_per_mwh=(1.0, 2.0, 3.0),
    )

    assert scenario.number_of_intervals == 3
    assert scenario.horizon_hours == pytest.approx(0.25)
