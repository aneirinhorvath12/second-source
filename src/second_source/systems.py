"""Systems under test that need no model, plus the registry the CLI uses.

- `null`:  trusts management completely. The floor.
- `rules`: triggers plus deterministic verdicts. It trusts the commercial team's
           variation register, treats any EVM divergence as a misstatement, and
           tests the provision on the EVM estimate, which is roughly what
           analytics without judgement can do.

These are harness v0's baselines. The investigator agent lives in
`second_source.agent` and registers itself here when imported. The controller
review (review.py) is separate: it returns figures and a confidence, not findings.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import replace

from . import engine
from .models import Finding
from .store import ContractFile
from .triggers import EAC_DIVERGENCE_TOL, PROVISION_TOL, candidates

System = Callable[[ContractFile], list[Finding]]


def null_system(cf: ContractFile) -> list[Finding]:
    return []


def rules_system(cf: ContractFile) -> list[Finding]:
    out: list[Finding] = []
    rep = cf.inputs()
    best = rep  # the rules' own best estimate, for M1
    for c in candidates(cf):
        if c.check == "T1":
            v = next(v for v in cf.report.variations if v.id == c.ref)
            if v.reported_status.startswith("Approved"):
                continue  # trusts the register
            corrected = replace(rep, variations_in_tp=rep.variations_in_tp - v.amount)
            out.append(Finding(contract_id=cf.contract_id, check="T1", ref=v.id,
                               verdict="judgement_call",
                               profit_effect_low=engine.revenue_effect(rep, corrected),
                               profit_effect_high=0.0, confidence=0.5,
                               question=f"Is {v.id} agreed with the customer?",
                               rationale=f"Register status '{v.reported_status}'."))
        elif c.check == "E2":
            if c.numbers["eac_divergence"] <= EAC_DIVERGENCE_TOL:
                continue
            best = replace(rep, etc=c.numbers["eac_evm"] - cf.report.cost_to_date)
            effect = engine.revenue_effect(rep, best)
            out.append(Finding(contract_id=cf.contract_id, check="E2", ref="ETC", verdict="misstated",
                               profit_effect_low=effect, profit_effect_high=effect, confidence=0.6,
                               rationale=c.reason))
        elif c.check == "M1":
            effect = engine.provision_effect(rep, best)
            if effect >= -PROVISION_TOL:
                continue
            out.append(Finding(contract_id=cf.contract_id, check="M1", ref="PROVISION",
                               verdict="misstated", profit_effect_low=effect,
                               profit_effect_high=effect, confidence=0.9, rationale=c.reason))
    return out


SYSTEMS: dict[str, System] = {"null": null_system, "rules": rules_system}


def get_system(name: str) -> System:
    if name not in SYSTEMS and name == "agent":
        from . import agent  # noqa: F401  registers the model-based systems
    try:
        return SYSTEMS[name]
    except KeyError as err:
        raise SystemExit(f"unknown system '{name}'; choose from {sorted(SYSTEMS)}") from err


def run_system(system: System, contracts: Iterable[ContractFile]) -> list[Finding]:
    findings: list[Finding] = []
    for cf in contracts:
        findings.extend(system(cf))
    return findings
