"""Tools for working on a hand-edited portfolio: check it, index it, inspect a contract.

    second-source check            catch broken edits before they reach an eval
    second-source index            rewrite INDEX.md, the one-page overview
    second-source show C009        numbers, triggers and answers for one contract
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from .answers import compile_key, read_key
from .store import contract_dirs, ledger_total, load_contract
from .triggers import candidates, schedule_numbers


@dataclass
class Problem:
    level: str  # "error" breaks scoring; "warning" is probably a mistake
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper():8} {self.where:22} {self.message}"


def _money(x: float) -> str:
    return f"-£{-x:,.0f}" if x < -0.5 else f"£{abs(x):,.0f}"


def check_contract(root: Path, cdir: Path) -> list[Problem]:
    cid = cdir.name
    out: list[Problem] = []

    def err(where: str, msg: str) -> None:
        out.append(Problem("error", f"{cid}/{where}", msg))

    def warn(where: str, msg: str) -> None:
        out.append(Problem("warning", f"{cid}/{where}", msg))

    for name in ("terms.yaml", "cost_report.yaml", "schedule.xer", "ledger.csv", "docs"):
        if not (cdir / name).exists():
            err(name, "missing")
    if out:
        return out

    try:
        cf = load_contract(cdir)
    except (ValidationError, ValueError, KeyError, yaml.YAMLError, AssertionError) as e:
        err("load", f"can't load the contract: {str(e).splitlines()[0]}")
        return out

    if cf.terms.contract_id != cid:
        err("terms.yaml", f"contract_id is {cf.terms.contract_id}, folder is {cid}")
    if cf.report.contract_id != cid:
        err("cost_report.yaml", f"contract_id is {cf.report.contract_id}, folder is {cid}")
    if cf.terms.contract_price != cf.report.contract_price:
        err("cost_report.yaml", f"contract_price {_money(cf.report.contract_price)} differs from "
                                f"terms.yaml {_money(cf.terms.contract_price)}")
    ids = [v.id for v in cf.report.variations]
    if len(ids) != len(set(ids)):
        err("cost_report.yaml", "duplicate variation ids")
    if cf.report.etc_breakdown:
        built = sum(e.amount for e in cf.report.etc_breakdown)
        if abs(built - cf.report.etc) > 1:
            warn("cost_report.yaml",
                 f"etc_breakdown sums to {_money(built)} but etc is {_money(cf.report.etc)}")
    if abs(ledger_total(cdir) - cf.report.cost_to_date) > 1:
        warn("ledger.csv", f"totals {_money(ledger_total(cdir))} but cost_to_date is "
                           f"{_money(cf.report.cost_to_date)}")

    contract_md = cf.docs.get("contract.md", "")
    if not contract_md:
        warn("docs", "no contract.md")
    else:
        for label, value in (("contract price", cf.terms.contract_price),
                             ("LD rate", cf.terms.ld_rate_per_day), ("LD cap", cf.terms.ld_cap)):
            if _money(value) not in contract_md:
                warn("docs/contract.md", f"doesn't mention the {label} in terms.yaml ({_money(value)})")
        if f"{cf.terms.completion_date:%d %B %Y}" not in contract_md:
            warn("docs/contract.md", "doesn't mention the completion date in terms.yaml")

    for doc_name, text in cf.docs.items():
        if re.search(r"\b(answer key|seeded|ground truth|synthetic)\b", text, re.IGNORECASE):
            warn(f"docs/{doc_name}", "mentions answers or seeding: systems can read this file")

    key_path = root / "answers" / f"{cid}.yaml"
    if not key_path.exists():
        err("answers", f"no answer key at answers/{cid}.yaml")
        return out
    try:
        key = read_key(key_path)
    except (ValidationError, yaml.YAMLError) as e:
        err("answers", f"can't read the answer key: {str(e).splitlines()[0]}")
        return out
    if key.contract_id != cid:
        err("answers", f"contract_id is {key.contract_id}, expected {cid}")

    seen: dict[tuple[str, str], int] = {}
    for j in key.judgements:
        seen[(j.check, j.ref)] = seen.get((j.check, j.ref), 0) + 1
    for (chk, ref), n in seen.items():
        if n > 1:
            err("answers", f"{chk} {ref} is judged {n} times")
    included = {v.id for v in cf.report.variations if v.included_in_tp}
    t1_refs = {ref for chk, ref in seen if chk == "T1"}
    for ref in sorted(included - t1_refs):
        err("answers", f"no T1 judgement for {ref}, which is in TP")
    for ref in sorted(t1_refs - included):
        err("answers", f"T1 judgement for {ref}, which isn't in TP")
    for chk, ref in (("E2", "ETC"), ("M1", "PROVISION")):
        if (chk, ref) not in seen:
            err("answers", f"no {chk} {ref} judgement")

    for j in key.judgements:
        where = f"answers {j.check} {j.ref}"
        if j.verdict == "misstated" and j.check != "M1" and j.correction is None:
            err(where, "misstated needs a correction")
        if j.verdict == "supported" and (j.correction is not None or j.range is not None):
            warn(where, "supported, but has a correction or range")
        if j.verdict == "judgement_call" and j.range is None:
            warn(where, "judgement call without a range")
        if j.verdict == "insufficient_evidence" and not j.request:
            warn(where, "insufficient evidence without a document request")
    try:
        label = compile_key(key, cf.report)
    except ValueError as e:
        err("answers", str(e))
        return out
    for issue in label.issues:
        if issue.expected_verdict == "misstated" and abs(issue.true_profit_effect) < 1:
            warn(f"answers {issue.check} {issue.ref}", "misstated, but the correction changes nothing")

    position = cf.position()
    m1 = next((j for j in key.judgements if j.check == "M1"), None)
    if m1 and m1.verdict == "supported" and position.provision_shortfall > 10_000:
        short = _money(position.provision_shortfall)
        warn("answers M1 PROVISION", f"supported, but the numbers need {short} more provision")
    if m1 and m1.verdict == "misstated" and position.provision_shortfall <= 1:
        err("answers M1 PROVISION", "misstated, but the provision booked already covers the loss")
    return out


def check_portfolio(root: Path) -> list[Problem]:
    problems: list[Problem] = []
    dirs = contract_dirs(root)
    names = {d.name for d in dirs}
    for d in dirs:
        problems.extend(check_contract(root, d))
    for path in sorted((root / "answers").glob("*.yaml")):
        if path.stem not in names:
            problems.append(Problem("error", f"answers/{path.name}", "no matching contract folder"))
    index = root / "INDEX.md"
    if index.exists() and not any(p.level == "error" for p in problems):
        if index.read_text() != index_markdown(root):
            problems.append(Problem("warning", "INDEX.md", "out of date: run second-source index"))
    return problems


def index_markdown(root: Path) -> str:
    """One-page overview of a portfolio: what each contract is and what its answer key says."""
    rows = []
    totals = {"supported": 0, "misstated": 0, "judgement_call": 0, "insufficient_evidence": 0}
    for d in contract_dirs(root):
        cf = load_contract(d)
        key = read_key(root / "answers" / f"{d.name}.yaml")
        label = compile_key(key, cf.report)
        flagged = []
        for i in label.issues:
            totals[i.expected_verdict] += 1
            if i.expected_verdict != "supported":
                flagged.append(f"{i.check} {i.ref}: {i.expected_verdict.replace('_', ' ')} "
                               f"({_money(i.true_profit_effect)})")
        p = cf.position()
        answers = "; ".join(flagged) or "all supported"
        price = _money(cf.terms.contract_price)
        rows.append(f"| [{d.name}](contracts/{d.name}/) | {cf.terms.name} | {price} "
                    f"| {p.margin_pct:.1%} | `{key.scenario}` | {answers} |")
    summary = ", ".join(f"{n} {v.replace('_', ' ')}" for v, n in totals.items())
    return (
        f"# {root.name} portfolio\n\n"
        "Generated by `second-source index` from the contract files and answer keys. "
        "Don't edit by hand.\n\n"
        f"{len(rows)} contracts; {sum(totals.values())} judgements: {summary}.\n\n"
        "| Contract | Name | Price | Reported margin | Scenario | Answer key (effect on profit to date) |\n"
        "|---|---|---|---|---|---|\n" + "\n".join(rows) + "\n"
    )


def show_contract(root: Path, cid: str) -> str:
    cdir = root / "contracts" / cid
    cf = load_contract(cdir)
    p, n = cf.position(), schedule_numbers(cf)
    lines = [
        f"{cid}: {cf.terms.name} for {cf.terms.customer}",
        "",
        "Management's position (engine)",
        f"  TP {_money(p.tp)}   EAC {_money(p.eac)}   POC {p.poc:.1%}   margin {p.margin_pct:.1%}",
        f"  revenue to date {_money(p.revenue_to_date)}   profit to date {_money(p.profit_to_date)}",
        f"  provision required {_money(p.provision_required)}, booked {_money(p.provision_booked)}",
        "",
        "Schedule evidence (P6)",
        f"  physical {n['physical_pct']:.1%} vs POC {n['poc']:.1%} (gap {n['progress_gap']:+.1%})",
        f"  CPI {n['cpi']:.2f}   SPI {n['spi']:.2f}   EVM EAC {n['eac_divergence']:+.1%} vs management",
        f"  slip {n['forecast_slip_days']:.0f} days   LD exposure {_money(n['ld_exposure'])}",
        "",
        "Triggers raise",
    ]
    lines += [f"  {c.check} {c.ref}: {c.reason}" for c in candidates(cf)] or ["  nothing"]
    key_path = root / "answers" / f"{cid}.yaml"
    if key_path.exists():
        key = read_key(key_path)
        label = compile_key(key, cf.report)
        lines += ["", f"Answer key ({key.scenario})"]
        for i in label.issues:
            effect = "" if i.expected_verdict == "supported" else f"  effect {_money(i.true_profit_effect)}"
            rng = "" if i.effect_range is None else \
                f"  range {_money(i.effect_range[0])} to {_money(i.effect_range[1])}"
            lines.append(f"  {i.check} {i.ref}: {i.expected_verdict}{effect}{rng}")
    return "\n".join(lines)
