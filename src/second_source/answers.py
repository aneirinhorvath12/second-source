"""Answer keys: what a careful reviewer should conclude about each judgement.

Answer keys are hand-editable YAML, one file per contract, kept outside the
contract folder so no system can read them. They record verdicts and
corrections in domain terms ("VO-002 should be 0 in TP", "ETC should be
45,120,000"), never pre-computed profit effects. The engine computes effects
from the contract's reported numbers each time, so editing a cost report
can't leave a stale number in the answers.

    contract_id: C005
    scenario: t1_unaccepted
    notes: Healthy contract carrying one rejected variation.
    judgements:
      - check: T1
        ref: VO-002
        verdict: misstated
        correction:
          variations: {VO-002: 0}
        why: Customer letter rejects it as within the original scope.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict

from . import engine
from .models import Check, ContractLabel, CostReport, LabelIssue, Verdict

ROUTINE_TAG = "routine"


class Correction(BaseModel):
    """Inputs as they should be. Anything left out keeps management's reported value."""

    model_config = ConfigDict(extra="forbid")

    variations: dict[str, float] = {}
    """Value each listed variation should carry in TP (0 removes it)."""
    etc: float | None = None
    claims_in_tp: float | None = None
    ld_deduction: float | None = None

    def apply(self, report: CostReport) -> engine.Inputs:
        rep = report.inputs()
        known = {v.id for v in report.variations}
        unknown = set(self.variations) - known
        if unknown:
            raise ValueError(f"correction names unknown variations {sorted(unknown)}")
        variations_in_tp = sum(
            self.variations.get(v.id, v.amount if v.included_in_tp else 0.0) for v in report.variations
        )
        changes: dict[str, float] = {"variations_in_tp": variations_in_tp}
        for field in ("etc", "claims_in_tp", "ld_deduction"):
            value = getattr(self, field)
            if value is not None:
                changes[field] = value
        return replace(rep, **changes)

    def is_empty(self) -> bool:
        return not self.variations and self.etc is None and self.claims_in_tp is None \
            and self.ld_deduction is None


class EffectRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    low: Correction = Correction()
    """Least favourable supportable treatment."""
    high: Correction = Correction()
    """Most favourable supportable treatment. Empty means as reported."""


class Judgement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check: Check
    ref: str
    verdict: Verdict
    correction: Correction | None = None
    """For misstated: the corrected inputs. For escalations: the best point estimate."""
    range: EffectRange | None = None
    """For judgement calls (and optionally insufficient evidence): the supportable range."""
    request: str | None = None
    """For insufficient evidence: the document that would settle it."""
    tag: str = ROUTINE_TAG
    """Scenario label for score breakdowns; leave as routine for unremarkable items."""
    why: str = ""


class AnswerKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_id: str
    scenario: str = "custom"
    notes: str = ""
    judgements: list[Judgement]


def _effect(report: CostReport, correction: Correction) -> float:
    return engine.profit_effect(report.inputs(), correction.apply(report))


def compile_judgement(j: Judgement, contract_id: str, report: CostReport) -> LabelIssue:
    """Turn one judgement into a label with engine-computed effects."""
    effect_range: tuple[float, float] | None = None
    if j.range is not None:
        effect_range = (_effect(report, j.range.low), _effect(report, j.range.high))

    if j.check == "M1" and j.verdict == "misstated":
        point = -engine.position(report.inputs()).provision_shortfall
    elif j.correction is not None:
        point = _effect(report, j.correction)
    elif effect_range is not None:
        point = sum(effect_range) / 2
    else:
        point = 0.0

    return LabelIssue(
        contract_id=contract_id, check=j.check, ref=j.ref, expected_verdict=j.verdict,
        true_profit_effect=point, effect_range=effect_range, scenario=j.tag,
        withheld_document=j.request, note=j.why,
    )


def compile_key(key: AnswerKey, report: CostReport) -> ContractLabel:
    return ContractLabel(
        contract_id=key.contract_id, scenario=key.scenario,
        issues=[compile_judgement(j, key.contract_id, report) for j in key.judgements],
    )


def read_key(path: Path) -> AnswerKey:
    return AnswerKey.model_validate(yaml.safe_load(path.read_text()))


def load_answers(root: Path) -> list[ContractLabel]:
    """Compile every answer key in a portfolio against its contract's reported numbers."""
    from .store import read_cost_report  # local import: store imports nothing from here

    labels = []
    for path in sorted((root / "answers").glob("*.yaml")):
        key = read_key(path)
        report = read_cost_report(root / "contracts" / key.contract_id)
        labels.append(compile_key(key, report))
    return labels
