"""Cheap rules over computed numbers that raise candidate issues.

Triggers are tuned for recall: a candidate is a question worth asking, not a
finding. Investigators (or the rule baseline) turn candidates into verdicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import engine
from .store import ContractFile

CPI_FLOOR = 0.95
EAC_DIVERGENCE_TOL = 0.02
PROGRESS_GAP_TOL = 0.03
PROVISION_TOL = 10_000.0


@dataclass
class Candidate:
    contract_id: str
    check: str
    ref: str
    reason: str
    numbers: dict[str, float] = field(default_factory=dict)


def schedule_numbers(cf: ContractFile) -> dict[str, float]:
    p, ev = cf.position(), cf.earned_value()
    return {
        "poc": p.poc,
        "physical_pct": ev.physical_pct,
        "progress_gap": engine.progress_gap(p.poc, ev.physical_pct),
        "cpi": ev.cpi,
        "spi": ev.spi,
        "eac_management": p.eac,
        "eac_evm": ev.eac_evm,
        "eac_divergence": engine.eac_divergence(ev.eac_evm, p.eac),
        "forecast_slip_days": float(cf.schedule.forecast_slip_days),
        "ld_exposure": cf.ld_exposure(),
    }


def candidates(cf: ContractFile) -> list[Candidate]:
    out: list[Candidate] = []
    cid = cf.contract_id

    for v in cf.report.variations:
        if v.included_in_tp:
            out.append(Candidate(cid, "T1", v.id,
                                 f"{v.id} ({v.amount:,.0f}) is in TP; register status '{v.reported_status}'.",
                                 {"amount": v.amount}))

    n = schedule_numbers(cf)
    reasons = []
    if n["cpi"] < CPI_FLOOR:
        reasons.append(f"CPI {n['cpi']:.2f}")
    if n["eac_divergence"] > EAC_DIVERGENCE_TOL:
        reasons.append(f"EVM EAC {n['eac_divergence']:+.1%} above management EAC")
    if n["progress_gap"] > PROGRESS_GAP_TOL:
        reasons.append(f"cost progress {n['progress_gap']:+.1%} ahead of physical progress")
    if reasons:
        out.append(Candidate(cid, "E2", "ETC", "; ".join(reasons), n))

    p = cf.position()
    if p.provision_shortfall > PROVISION_TOL:
        out.append(Candidate(cid, "M1", "PROVISION",
                             f"EAC exceeds TP by {p.expected_loss:,.0f}; provision short by "
                             f"{p.provision_shortfall:,.0f}.",
                             {"expected_loss": p.expected_loss, "shortfall": p.provision_shortfall}))
    return out
