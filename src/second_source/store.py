"""Loads a contract file from disk: everything a system under test may see.

A portfolio is a folder you can read and edit by hand:

    portfolios/hard/
      portfolio.yaml            name, period end, where it came from
      contracts/C009/
        terms.yaml              contract summary
        cost_report.yaml        management's numbers and variation register
        schedule.xer            P6 export
        ledger.csv              actual cost by month and cost code
        docs/*.md               contract, submissions, letters, minutes
      answers/C009.yaml         answer key: never shown to a system

Systems get a `ContractFile` and nothing else. YAML comments are stripped
before a system sees a file, so notes you write there can't leak answers.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import yaml

from . import engine, xer
from .models import CostReport, Terms


@dataclass
class ContractFile:
    contract_id: str
    terms: Terms
    report: CostReport
    schedule: xer.ScheduleMetrics
    schedule_text: str
    ledger_total: float
    docs: dict[str, str]
    terms_text: str
    """terms.yaml as systems see it: comments stripped."""
    report_text: str
    """cost_report.yaml as systems see it: comments stripped."""

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

    def sources(self) -> dict[str, str]:
        """Every file a system may read, by name."""
        return {"terms.yaml": self.terms_text, "cost_report.yaml": self.report_text,
                "schedule.xer": self.schedule_text, **self.docs}


def _load_yaml(path: Path) -> tuple[dict, str]:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path} should contain a YAML mapping")
    stripped = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)
    return data, stripped


def read_cost_report(cdir: Path) -> CostReport:
    return CostReport.model_validate(_load_yaml(cdir / "cost_report.yaml")[0])


def ledger_total(cdir: Path) -> float:
    with (cdir / "ledger.csv").open() as f:
        return sum(float(r["amount"]) for r in csv.DictReader(f))


def load_contract(cdir: Path) -> ContractFile:
    terms, terms_text = _load_yaml(cdir / "terms.yaml")
    report, report_text = _load_yaml(cdir / "cost_report.yaml")
    xer_path = cdir / "schedule.xer"
    return ContractFile(
        contract_id=cdir.name,
        terms=Terms.model_validate(terms),
        report=CostReport.model_validate(report),
        schedule=xer.metrics(xer.read(xer_path)),
        schedule_text=xer_path.read_text(),
        ledger_total=ledger_total(cdir),
        docs={p.name: p.read_text() for p in sorted((cdir / "docs").glob("*.md"))},
        terms_text=terms_text,
        report_text=report_text,
    )


def contract_dirs(root: Path) -> list[Path]:
    """Every contract folder in a portfolio, in name order. Add a contract by adding a folder."""
    return sorted(p for p in (root / "contracts").iterdir() if p.is_dir())


def load_portfolio(root: Path) -> list[ContractFile]:
    return [load_contract(d) for d in contract_dirs(root)]


def load_labels(root: Path):
    """Compiled answer keys. Only the evals call this."""
    from .answers import load_answers

    return load_answers(root)
