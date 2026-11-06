"""Data shapes shared by the simulator, the systems under test and the evals."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from . import engine

Verdict = Literal["supported", "misstated", "judgement_call", "insufficient_evidence"]
Check = Literal["T1", "E2", "M1"]

CHECKS: dict[str, str] = {
    "T1": "Variation in TP without customer acceptance or an enforceable right (IFRS 15.18-21)",
    "E2": "Management EAC optimistic against earned value and physical progress",
    "M1": "Loss-making contract without the onerous provision management's own numbers require",
}

# Every contract is assessed on these refs; T1 adds one ref per variation in TP.
FIXED_REFS: dict[str, str] = {"E2": "ETC", "M1": "PROVISION"}


class Variation(BaseModel):
    id: str
    description: str
    amount: float
    included_in_tp: bool = True
    reported_status: str = "Approved"


class Terms(BaseModel):
    contract_id: str
    name: str
    customer: str
    contract_price: float
    start_date: date
    completion_date: date
    ld_rate_per_day: float
    ld_cap: float


class CostReport(BaseModel):
    """Management's reported position for one contract at one period end."""

    contract_id: str
    period_end: date
    contract_price: float
    variations: list[Variation] = Field(default_factory=list)
    claims_in_tp: float = 0.0
    ld_deduction: float = 0.0
    cost_to_date: float
    etc: float
    provision_booked: float = 0.0
    commentary: str = ""

    def inputs(self) -> engine.Inputs:
        return engine.Inputs(
            contract_price=self.contract_price,
            variations_in_tp=sum(v.amount for v in self.variations if v.included_in_tp),
            claims_in_tp=self.claims_in_tp,
            ld_deduction=self.ld_deduction,
            cost_to_date=self.cost_to_date,
            etc=self.etc,
            provision_booked=self.provision_booked,
        )


class Citation(BaseModel):
    doc_id: str
    quote: str


class Finding(BaseModel):
    """What a system under test says about one judgement."""

    contract_id: str
    check: Check
    ref: str
    verdict: Verdict
    profit_effect_low: float | None = None
    profit_effect_high: float | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    evidence: list[Citation] = Field(default_factory=list)
    question: str | None = None
    document_request: str | None = None
    rationale: str = ""

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.contract_id, self.check, self.ref)

    @property
    def point_effect(self) -> float:
        lo = self.profit_effect_low or 0.0
        hi = self.profit_effect_high if self.profit_effect_high is not None else lo
        return (lo + hi) / 2


class LabelIssue(BaseModel):
    """Ground truth for one judgement, set by the simulator in code."""

    contract_id: str
    check: Check
    ref: str
    expected_verdict: Verdict
    true_profit_effect: float = 0.0
    effect_range: tuple[float, float] | None = None
    scenario: str = "clean"
    withheld_document: str | None = None
    note: str = ""

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.contract_id, self.check, self.ref)


class ContractLabel(BaseModel):
    """All labels for one contract, compiled from its answer key (see answers.py)."""

    contract_id: str
    scenario: str
    issues: list[LabelIssue]
