# Week 1 Battery Dispatch Model Specification

## 1. Purpose

The Week 1 model establishes the reusable physical and optimization foundation for a grid-connected battery energy-storage system.

The model optimizes the operation of one price-taking battery at one location over a deterministic time horizon. It uses synthetic energy prices and represents a simplified, single-settlement energy market.

The purpose is not to reproduce the complete California ISO market during Week 1. The purpose is to verify the battery’s physical equations, units, optimization behavior, software interfaces, and result-validation process before introducing real market data and additional market rules.

The battery formulation developed here must later be reusable within:

- Historical CAISO market backtests.
- Rolling-horizon dispatch.
- Stochastic price and renewable-generation scenarios.
- Ancillary-service co-optimization.
- Interconnection-queue scenarios.
- Endogenous market-clearing models.
- Nodal transmission models.
- Battery siting and investment optimization.

## 2. Week 1 Scope

The Week 1 model includes:

- One grid-connected battery.
- One location or pricing point.
- One deterministic market scenario.
- One energy price per interval.
- Charging and discharging decisions.
- Charging and discharging efficiencies.
- Stored-energy limits.
- Charging and discharging power limits.
- Initial stored energy.
- A configurable terminal stored-energy requirement.
- Optional linear degradation cost based on discharged energy.
- Optional prevention of simultaneous charging and discharging.
- Synthetic hourly or subhourly prices.
- Structured optimization results and solver metadata.

The Week 1 model excludes:

- CAISO OASIS data ingestion.
- Separate day-ahead, fifteen-minute, and five-minute settlements.
- Bids and market awards.
- Ancillary services.
- Regulation mileage or activation.
- Bid cost recovery.
- Resource adequacy.
- Forecast uncertainty.
- Strategic bidding.
- Endogenous market prices.
- Transmission constraints.
- Interconnection-queue uncertainty.
- Capacity-expansion decisions.
- Detailed electrochemical degradation.
- Battery augmentation and replacement.

These exclusions are deliberate. Later modules may add these capabilities without redefining the core battery physics.

## 3. Architectural Boundaries

The project separates four responsibilities.

### 3.1 Domain layer

The domain layer defines validated data structures that describe:

- The battery.
- Its current state.
- External market conditions.
- Optimization results.

Domain modules must not import Pyomo, construct optimization variables, call solvers, or download market data.

### 3.2 Optimization layer

The optimization layer:

- Constructs the Pyomo model.
- Adds decision variables.
- Adds physical constraints.
- Defines the objective.
- Calls the selected solver.
- Extracts a structured result.

### 3.3 Degradation layer

The degradation layer supplies a replaceable degradation-cost formulation.

Week 1 uses either zero degradation cost or a constant cost per MWh discharged. Later versions may introduce piecewise depth-sensitive degradation, rainflow validation, calendar aging, and state-of-health transitions.

### 3.4 Evaluation layer

The evaluation layer:

- Checks physical feasibility.
- Calculates performance metrics.
- Compares modeled behavior with expected behavior.
- Produces tables and visualizations.

Evaluation code must consume structured results rather than access Pyomo variables directly.

## 4. Modeling Assumptions

The Week 1 model makes the following assumptions:

1. The battery is a price taker. Its dispatch does not affect the supplied energy prices.
2. Prices are known perfectly over the optimization horizon.
3. One energy price applies to charging and discharging during each interval.
4. Charging power is measured at the grid connection.
5. Discharging power is measured at the grid connection.
6. Stored energy is represented in MWh.
7. Charging and discharging efficiencies are constant.
8. Power and energy limits are constant during the horizon.
9. The battery is continuously available.
10. There are no ramp-rate or minimum-operating-time constraints.
11. There are no network or transmission constraints.
12. There are no taxes, fees, uplift payments, or settlement adjustments.
13. Calendar degradation is ignored.
14. Self-discharge is configurable but may initially be set to zero.
15. The model begins from a supplied battery state.
16. The default terminal condition returns the battery to its initial stored energy.

Perfect foresight is a benchmark assumption. It will later be replaced by rolling-horizon decisions using forecast information.

## 5. Units and Sign Conventions

The model uses the following units:

| Quantity | Unit |
|---|---|
| Charging power | MW |
| Discharging power | MW |
| Net grid injection | MW |
| Stored energy | MWh |
| Energy capacity | MWh |
| Interval duration | hours |
| Energy price | USD/MWh |
| Energy-market revenue | USD |
| Degradation cost | USD |
| Efficiency | dimensionless |
| Self-discharge rate | fraction per hour |

The relationship between power and energy is:

\[
\text{Energy [MWh]}
=
\text{Power [MW]}
\times
\text{interval duration [hours]}.
\]

The sign convention is:

- Charging power is stored as a nonnegative quantity.
- Discharging power is stored as a nonnegative quantity.
- Positive net injection means electricity is supplied to the grid.
- Negative net injection means electricity is consumed from the grid.

For interval \(t\):

\[
p_t^{\mathrm{net}}=d_t-c_t.
\]

Here, \(c_t\) is charging power and \(d_t\) is discharging power.

## 6. Time Indexing

Let the optimization contain \(T\) operating intervals.

The dispatch interval set is:

\[
\mathcal{T}=\{0,1,\ldots,T-1\}.
\]

Charging, discharging, price, duration, net injection, and interval revenue are indexed over \(\mathcal{T}\).

Stored energy is defined at interval boundaries. Its state index is:

\[
\mathcal{S}=\{0,1,\ldots,T\}.
\]

There are therefore:

- \(T\) charging decisions.
- \(T\) discharging decisions.
- \(T\) market prices.
- \(T\) interval durations.
- \(T+1\) stored-energy states.

Stored energy \(e_t\) represents energy available at the beginning of interval \(t\). Stored energy \(e_{t+1}\) represents energy after the charging and discharging decisions in interval \(t\).

The model must not assume that every interval is one hour. Each interval has an explicit duration \(\Delta t_t\).

## 7. Domain Input Contracts

### 7.1 Battery specification

`BatterySpec` describes the battery’s fixed physical characteristics:

- `asset_id`
- `charge_power_mw`
- `discharge_power_mw`
- `energy_capacity_mwh`
- `minimum_energy_mwh`
- `charge_efficiency`
- `discharge_efficiency`
- `self_discharge_per_hour`

The battery specification does not contain current stored energy. Current operating state changes between optimization runs and is represented separately.

### 7.2 Battery state

`BatteryState` contains:

- `energy_mwh`

The supplied battery state must satisfy:

\[
E^{\min}
\leq
E^{\mathrm{initial}}
\leq
E^{\max}.
\]

A future state-of-health model may expand `BatteryState` to contain usable capacity, resistance, efficiency, or accumulated degradation.

### 7.3 Market scenario

`MarketScenario` describes the external conditions faced by the battery:

- `scenario_id`
- `node_id`
- `interval_start`
- `interval_duration_hours`
- `energy_price_per_mwh`
- `probability`

Every operating interval must have exactly one timestamp, duration, and energy price.

Prices may be positive, zero, or negative.

Timestamps must be unique, strictly increasing, and time-zone-aware. Real CAISO data will later be stored using UTC timestamps while retaining relevant Pacific market labels.

## 8. Model Parameters

For each interval \(t\), the model receives:

\[
\pi_t
\]

Energy price in USD/MWh.

\[
\Delta t_t
\]

Interval duration in hours.

Battery parameters are:

\[
P^c
\]

Maximum charging power in MW.

\[
P^d
\]

Maximum discharging power in MW.

\[
E^{\min}
\]

Minimum usable stored energy in MWh.

\[
E^{\max}
\]

Maximum usable stored energy in MWh.

\[
\eta_c
\]

Charging efficiency.

\[
\eta_d
\]

Discharging efficiency.

\[
\lambda
\]

Self-discharge fraction per hour.

\[
E^{\mathrm{initial}}
\]

Stored energy at the beginning of the horizon.

\[
E^{\mathrm{terminal}}
\]

Required stored energy at the end of the horizon.

\[
k^{\mathrm{deg}}
\]

Linear degradation cost in USD per MWh discharged.

## 9. Decision Variables

For every interval \(t\):

\[
c_t\geq0
\]

Charging power in MW.

\[
d_t\geq0
\]

Discharging power in MW.

For every state index \(s\):

\[
e_s
\]

Stored energy in MWh.

When exclusive operation is enabled:

\[
u_t\in\{0,1\}.
\]

The binary variable identifies the permitted operating direction in interval \(t\).

## 10. Physical Constraints

### 10.1 Charging-power limit

\[
0\leq c_t\leq P^c
\qquad \forall t\in\mathcal{T}.
\]

### 10.2 Discharging-power limit

\[
0\leq d_t\leq P^d
\qquad \forall t\in\mathcal{T}.
\]

### 10.3 Stored-energy limits

\[
E^{\min}\leq e_s\leq E^{\max}
\qquad \forall s\in\mathcal{S}.
\]

### 10.4 Initial stored energy

\[
e_0=E^{\mathrm{initial}}.
\]

### 10.5 Energy transition

Without self-discharge, the transition is:

\[
e_{t+1}
=
e_t
+
\eta_c c_t\Delta t_t
-
\frac{d_t\Delta t_t}{\eta_d}.
\]

With self-discharge, the transition is:

\[
e_{t+1}
=
e_t(1-\lambda\Delta t_t)
+
\eta_c c_t\Delta t_t
-
\frac{d_t\Delta t_t}{\eta_d}.
\]

Charging efficiency multiplies charging energy because only a fraction of grid energy becomes stored energy.

Discharging energy is divided by discharging efficiency because delivering one MWh to the grid requires removing more than one MWh from storage when efficiency is below one.

### 10.6 Terminal stored energy

The default Week 1 policy is:

\[
e_T=E^{\mathrm{terminal}}.
\]

Initially:

\[
E^{\mathrm{terminal}}
=
E^{\mathrm{initial}}.
\]

This prevents the optimizer from treating the battery’s initial inventory as free energy and prevents artificial depletion at the end of the horizon.

Future terminal policies may include a target with a penalty or an estimated continuation value.

## 11. Exclusive Charging and Discharging

The initial model may be solved as a linear program without a binary operating-mode variable.

When exclusive operation is enabled:

\[
c_t\leq P^c(1-u_t)
\]

and

\[
d_t\leq P^d u_t,
\]

where:

\[
u_t\in\{0,1\}.
\]

This prevents simultaneous charging and discharging.

The linear relaxation should be retained as a configurable option because it is faster and often produces physically sensible solutions under ordinary energy prices. However, negative prices can make simultaneous charging and discharging mathematically profitable because the battery can be paid to consume energy through conversion losses.

The project must test and document this behavior rather than assuming it cannot occur.

## 12. Energy-Market Revenue

Net grid injection is:

\[
p_t^{\mathrm{net}}=d_t-c_t.
\]

Interval energy-market revenue is:

\[
R_t^{\mathrm{energy}}
=
\pi_t(d_t-c_t)\Delta t_t.
\]

Total energy-market revenue is:

\[
R^{\mathrm{energy}}
=
\sum_{t\in\mathcal{T}}
\pi_t(d_t-c_t)\Delta t_t.
\]

When the battery charges, net injection is negative. At a positive price, charging therefore produces a negative revenue contribution.

When the battery discharges, net injection is positive and produces positive revenue at a positive price.

At a negative price, charging can produce positive revenue because the battery is paid to consume energy.

## 13. Week 1 Degradation Cost

The optional linear degradation cost is:

\[
C^{\mathrm{deg}}
=
k^{\mathrm{deg}}
\sum_{t\in\mathcal{T}}
d_t\Delta t_t.
\]

This represents a constant economic cost for each MWh discharged.

The coefficient may be set to zero in initial tests.

This formulation does not attempt to capture:

- Cycle depth.
- C-rate.
- Temperature.
- Calendar aging.
- SOC dwell time.
- Capacity fade.
- Resistance growth.
- Rainflow-counted cycles.

The degradation interface must be replaceable so more detailed formulations can be added without changing the battery’s physical constraints.

## 14. Objective Function

The Week 1 model maximizes energy-market revenue minus degradation cost:

\[
\max
\left[
\sum_{t\in\mathcal{T}}
\pi_t(d_t-c_t)\Delta t_t
-
k^{\mathrm{deg}}
\sum_{t\in\mathcal{T}}
d_t\Delta t_t
\right].
\]

The result must report separately:

- Gross energy-market revenue.
- Degradation cost.
- Net objective value.

These values must not be combined into one unexplained profit field.

## 15. Result Contract

`DispatchResult` contains:

- Battery identifier.
- Scenario identifier.
- Node identifier.
- Interval timestamps.
- Interval durations.
- Charging power.
- Discharging power.
- Net injection.
- Stored-energy trajectory.
- Interval energy revenue.
- Total energy revenue.
- Degradation cost.
- Objective value.
- Solver name.
- Solver status.
- Termination condition.
- Solve time.

For \(T\) intervals:

- Charge, discharge, net injection, duration, and interval revenue have length \(T\).
- Stored energy has length \(T+1\).

The structured result must not expose Pyomo variables or constraints.

## 16. Solution Validation

Every solved result must be checked for:

### 16.1 Solver success

The solver must report an acceptable optimal termination condition before values are interpreted as a valid solution.

### 16.2 Energy-balance residual

For each interval:

\[
r_t
=
e_{t+1}
-
e_t(1-\lambda\Delta t_t)
-
\eta_c c_t\Delta t_t
+
\frac{d_t\Delta t_t}{\eta_d}.
\]

The validation condition is:

\[
|r_t|\leq\epsilon.
\]

### 16.3 Power limits

\[
0\leq c_t\leq P^c+\epsilon
\]

and

\[
0\leq d_t\leq P^d+\epsilon.
\]

### 16.4 Stored-energy limits

\[
E^{\min}-\epsilon
\leq e_s
\leq E^{\max}+\epsilon.
\]

### 16.5 Initial and terminal states

The initial and terminal values must satisfy their required conditions within numerical tolerance.

### 16.6 Net-injection identity

\[
p_t^{\mathrm{net}}
=
d_t-c_t.
\]

### 16.7 Revenue identity

Reported interval revenue must equal:

\[
\pi_t p_t^{\mathrm{net}}\Delta t_t.
\]

Total revenue must equal the sum of interval revenue.

### 16.8 Simultaneous operation

The evaluation layer must report intervals in which both charging and discharging exceed numerical tolerance.

When exclusive operation is enabled, the number of such intervals must be zero.

## 17. Required Week 1 Tests

### 17.1 Flat-price test

Given constant positive prices, efficiency losses, nonnegative degradation cost, and equal initial and terminal energy:

Expected result:

- No economically meaningful cycling.
- Zero or numerically negligible market revenue.
- Initial and terminal energy are equal.

### 17.2 Profitable-arbitrage test

Given one sufficiently low price and one sufficiently high price:

Expected result:

- Charging occurs during the low-price interval.
- Discharging occurs during the high-price interval.
- The energy transition reflects efficiency losses.
- Market revenue is positive.

### 17.3 Insufficient-spread test

A complete cycle is not profitable unless approximately:

\[
\pi^{\mathrm{sell}}
>
\frac{\pi^{\mathrm{buy}}+k^{\mathrm{deg}}}
{\eta_c\eta_d},
\]

subject to the degradation-cost convention.

When the spread is below the break-even level:

Expected result:

- No economically meaningful cycle.

### 17.4 Power-limited test

A short low-price period must not allow charging above the battery’s MW limit.

### 17.5 Energy-limited test

A long low-price period must not allow stored energy above the battery’s MWh limit.

### 17.6 Subhourly-interval test

For a 30-minute interval:

\[
1\text{ MW}\times0.5\text{ h}=0.5\text{ MWh}
\]

before efficiency.

The model must not treat 1 MW during a 30-minute interval as 1 MWh.

### 17.7 Terminal-energy test

The optimizer must not obtain artificial profit by permanently emptying initial stored energy.

### 17.8 Negative-price test

Construct a case where the relaxed linear model may charge and discharge simultaneously to consume energy through efficiency losses.

Expected result:

- The behavior is detected by validation.
- Enabling exclusive operation removes it.

### 17.9 Invalid-input tests

Domain validation must reject:

- Negative capacities.
- Invalid efficiencies.
- Inconsistent time-series lengths.
- Nonpositive durations.
- NaN or infinite prices.
- Unordered timestamps.
- Battery states outside physical bounds.

## 18. Week 1 Completion Criteria

Week 1 is complete when:

- Domain objects validate all required inputs.
- The model uses \(T\) dispatch intervals and \(T+1\) energy states.
- All power-to-energy conversions use interval duration.
- Energy-balance residuals are within tolerance.
- Charging and discharging power limits are respected.
- Stored-energy limits are respected.
- Initial and terminal conditions are respected.
- Flat-price and insufficient-spread tests produce no cycling.
- Profitable-spread tests produce sensible arbitrage.
- Subhourly interval tests pass.
- Negative-price simultaneity is understood and controllable.
- Gross revenue, degradation cost, and objective value are reported separately.
- Solver failures are not returned as valid dispatch results.
- A complete run is reproducible from a configuration file.
- Optimization equations do not live in a notebook.
- No real CAISO data is required for the test suite.

## 19. Future Extension Interfaces

The initial architecture preserves the following extensions.

### Queue model

A queue model may generate scenario-dependent project completion dates, capacities, locations, and probabilities. These will be translated into market or investment scenarios without changing the battery physics.

### Market-feedback model

Historical prices may be replaced by prices produced by a market-clearing model. The physical battery constraints should be reusable as a battery block inside that model.

### Investment optimizer

The investment model may vary charging power, discharging power, energy capacity, location, and commissioning date. It should construct alternative `BatterySpec` objects and call the operational model.

### Locational expansion

The `node_id` field allows scenarios and results to be associated with hubs, pricing nodes, substations, or network buses. A future network model may add power-flow and transmission constraints without redefining storage-energy transitions.

### Stochastic operation

A future scenario collection may contain multiple `MarketScenario` objects and probabilities. The deterministic Week 1 scenario is the one-scenario special case.

### Advanced degradation

The linear degradation component may be replaced with piecewise depth-sensitive costs, rainflow validation, calendar aging, and state-of-health transitions.

## 20. Known Limitations

Week 1 results are engineering and software validation results, not forecasts of realizable CAISO battery revenue.

In particular, the model does not yet account for:

- Information unavailable at the time of dispatch.
- Separate market schedules and settlements.
- Ancillary-service opportunity costs.
- Battery bidding rules.
- Network congestion caused by the modeled battery.
- Price feedback from additional storage.
- Resource outages or derates.
- Detailed battery degradation.
- Project financing and capital costs.

All Week 1 outputs must therefore be labeled as deterministic, synthetic, perfect-foresight dispatch results.