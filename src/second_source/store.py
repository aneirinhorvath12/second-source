"""Loads a contract file from disk: everything a system under test may see.

Systems get a `ContractFile` and nothing else. Labels live in a sibling folder
and are only read by the evals.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from . import engine, xer
from .models import ContractLabel, CostReport, Terms


@dataclass
class ContractFile:
    contract_id: str
    terms: Terms
    report: CostReport
    schedule: xer.ScheduleMetrics
    schedule_text: str
    ledger_total: float
    docs: dict[str, str]

    def inputs(self) -> engine.Inputs:
        return self.report.inputs()

    def position(self) -> engine.Position:
        return engine.position(self.inputs())

    def earned_value(self) -> engine.EarnedValue:
        s = self.schedule
        return engine.earned_value(s.bac, s.ev, s.pv, self.report.cost_to_date)

    def ld_exposure(self) -> float:
        t = self.terms
        return engine.ld_exposure(t.ld_rate_per_day, t.ld_cap, self.schedule.forecast_finish,
                                  t.completion_date)


def load_contract(cdir: Path) -> ContractFile:
    xer_path = cdir / "schedule.xer"
    with (cdir / "ledger.csv").open() as f:
        ledger_total = sum(float(r["amount"]) for r in csv.DictReader(f))
    return ContractFile(
        contract_id=cdir.name,
        terms=Terms.model_validate_json((cdir / "terms.json").read_text()),
        report=CostReport.model_validate_json((cdir / "cost_report.json").read_text()),
        schedule=xer.metrics(xer.read(xer_path)),
        schedule_text=xer_path.read_text(),
        ledger_total=ledger_total,
        docs={p.name: p.read_text() for p in sorted((cdir / "docs").glob("*.md"))},
    )


def load_portfolio(root: Path) -> list[ContractFile]:
    ids = json.loads((root / "manifest.json").read_text())["contracts"]
    return [load_contract(root / "contracts" / cid) for cid in ids]


def load_labels(root: Path) -> list[ContractLabel]:
    return [ContractLabel.model_validate_json(p.read_text())
            for p in sorted((root / "labels").glob("*.json"))]
