"""Deterministic contract accounting engine.

Every number in Second Source comes from here. Models judge the inputs and the
evidence behind them; they never do the arithmetic.

Conventions (per contract, at a period end):
    C    cost incurred to date that depicts progress
    ETC  estimated cost to complete
    EAC  estimate at completion = C + ETC
    TP   transaction price = contract price + variations in TP + claims in TP - expected LDs
    POC  C / EAC (input method, IFRS 15.B18)
    R    cumulative revenue = POC x TP
    L    expected loss = max(0, EAC - TP)
    Provision required = (1 - POC) x L  (revenue at POC already books POC x L; IAS 37.66-69)
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date


@dataclass(frozen=True)
class Inputs:
    """The numbers management reports for one contract at one period end."""

    contract_price: float
    variations_in_tp: float = 0.0
    claims_in_tp: float = 0.0
    ld_deduction: float = 0.0
    cost_to_date: float = 0.0
    etc: float = 0.0
    provision_booked: float = 0.0


@dataclass(frozen=True)
class Position:
    tp: float
    eac: float
    poc: float
    revenue_to_date: float
    lifetime_margin: float
    margin_pct: float
    expected_loss: float
    provision_required: float
    provision_booked: float
    provision_shortfall: float
    profit_to_date: float
    """Cumulative profit recognised: revenue - cost - provision booked."""


def transaction_price(i: Inputs) -> float:
    return i.contract_price + i.variations_in_tp + i.claims_in_tp - i.ld_deduction


def position(i: Inputs) -> Position:
    if i.cost_to_date < 0 or i.etc < 0:
        raise ValueError("cost_to_date and etc must be non-negative")
    tp = transaction_price(i)
    eac = i.cost_to_date + i.etc
    poc = 0.0 if eac == 0 else min(1.0, i.cost_to_date / eac)
    revenue = poc * tp
    margin = tp - eac
    loss = max(0.0, eac - tp)
    required = (1.0 - poc) * loss
    return Position(
        tp=tp,
        eac=eac,
        poc=poc,
        revenue_to_date=revenue,
        lifetime_margin=margin,
        margin_pct=0.0 if tp == 0 else margin / tp,
        expected_loss=loss,
        provision_required=required,
        provision_booked=i.provision_booked,
        provision_shortfall=max(0.0, required - i.provision_booked),
        profit_to_date=revenue - i.cost_to_date - i.provision_booked,
    )


def correct_profit_to_date(i: Inputs) -> float:
    """Profit to date if the onerous provision were booked at the required amount."""
    p = position(i)
    return p.revenue_to_date - i.cost_to_date - p.provision_required


def scenario(i: Inputs, **overrides: float) -> Position:
    """Re-run the position with some inputs changed. The agent's only route to numbers."""
    unknown = set(overrides) - set(Inputs.__dataclass_fields__)
    if unknown:
        raise ValueError(f"unknown inputs: {sorted(unknown)}")
    return position(replace(i, **overrides))


def profit_effect(reported: Inputs, corrected: Inputs) -> float:
    """Change to cumulative profit to date from correcting the inputs.

    Negative means reported profit is overstated. The provision is always taken
    at the required amount on both sides, so this isolates the input change.
    """
    return correct_profit_to_date(corrected) - correct_profit_to_date(reported)


# --- Earned value (from the P6 schedule) -------------------------------------


@dataclass(frozen=True)
class EarnedValue:
    bac: float
    ev: float
    pv: float
    ac: float
    cpi: float
    spi: float
    eac_evm: float
    physical_pct: float


def earned_value(bac: float, ev: float, pv: float, ac: float) -> EarnedValue:
    """CPI = EV/AC, SPI = EV/PV, EAC_EVM = AC + (BAC - EV) / CPI."""
    if ac <= 0 or bac <= 0:
        raise ValueError("bac and ac must be positive")
    cpi = ev / ac if ev > 0 else 0.0
    spi = ev / pv if pv > 0 else 0.0
    eac_evm = ac + (bac - ev) / cpi if cpi > 0 else float("inf")
    return EarnedValue(bac, ev, pv, ac, cpi, spi, eac_evm, ev / bac)


def eac_divergence(eac_evm: float, eac_management: float) -> float:
    """delta = (EAC_EVM - EAC_mgmt) / EAC_mgmt. Positive: management is optimistic."""
    return (eac_evm - eac_management) / eac_management


def progress_gap(poc: float, physical_pct: float) -> float:
    """Delta = POC - EV/BAC. Positive: cost progress runs ahead of physical progress."""
    return poc - physical_pct


# --- Delay consequences --------------------------------------------------------


def days_late(forecast_finish: date, contractual_completion: date, eot_days: int = 0) -> int:
    return max(0, (forecast_finish - contractual_completion).days - eot_days)


def ld_exposure(
    rate_per_day: float,
    cap: float,
    forecast_finish: date,
    contractual_completion: date,
    eot_days: int = 0,
) -> float:
    """LD = min(rate x days late, cap)."""
    return min(rate_per_day * days_late(forecast_finish, contractual_completion, eot_days), cap)
