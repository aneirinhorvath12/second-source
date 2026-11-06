"""Generates starter contract portfolios with ground truth set in code.

The committed portfolios in `portfolios/` are the dataset; this generator only
bootstraps new ones. Each contract has a true execution (costs, physical
progress, slip) and a management view that equals the truth plus at most one
seeded issue. The answer key records, for every judgement a system could
raise, the verdict a careful reviewer should reach and the corrected inputs.

`write_portfolio` writes the hand-editable layout described in `store.py`.
Once written, edit the files directly; don't regenerate over your edits.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from .. import engine, xer
from ..answers import AnswerKey, Correction, EffectRange, Judgement, compile_key
from ..formats import answers_yaml, cost_report_yaml, terms_yaml
from ..models import ContractLabel, CostReport, Terms, Variation
from . import render

GENERATOR_VERSION = "0.1.0"
PERIOD_END = date(2026, 12, 31)
CONTRACTOR = "Brackmoor Engineering Ltd"

# Scenario mix per 30 contracts. Ground truth for each is set in `build_contract`.
SCENARIO_WEIGHTS: dict[str, int] = {
    "clean": 4,
    "t1_unaccepted": 5,  # rejected or unapproved variation booked in TP -> misstated
    "t1_in_principle": 3,  # scope agreed, value disputed -> judgement call
    "t1_no_evidence": 3,  # register says approved, no customer letter -> insufficient evidence
    "e2_etc_understated": 4,  # remaining work assumed at budget despite poor CPI -> misstated
    "e2_hard_negative": 2,  # poor CPI, but ETC already reflects it -> supported
    "e2_one_off_overrun": 2,  # EVM says optimistic, but the overrun was a documented one-off -> supported
    "e2_recovery_plan": 3,  # ETC assumes an unagreed recovery plan -> judgement call
    "m1_no_provision": 4,  # management's own EAC exceeds TP, no provision -> misstated
}

POOR_PERFORMERS = {"e2_etc_understated", "e2_hard_negative", "e2_one_off_overrun", "e2_recovery_plan"}

SCENARIO_NOTES: dict[str, str] = {
    "clean": "Nothing seeded: every judgement is supported.",
    "t1_unaccepted": "A variation the customer rejected or disowned is booked in TP.",
    "t1_in_principle": "Customer accepts the scope of a variation but disputes its value.",
    "t1_no_evidence": "Register says a variation is approved, but no customer letter exists.",
    "e2_etc_understated": "CPI well below 1, yet remaining work is forecast at budget.",
    "e2_hard_negative": "Poor CPI, honestly reflected in a bottom-up reforecast.",
    "e2_one_off_overrun": "Poor CPI to date from a documented one-off; remaining work back to plan.",
    "e2_recovery_plan": "ETC relies on recovery savings a subcontractor has not agreed.",
    "m1_no_provision": "Management's own EAC exceeds TP, but no onerous provision is booked.",
}

PROJECTS = [
    "Halden Ridge Gas Compression", "Northmoor Water Treatment Upgrade", "Kessock Substation",
    "Arden Valley Biomass Plant", "Tarrow Estuary Jetty", "Fennick Hydrogen Pilot",
    "Corran Point Desalination", "Ashby Fell Pumping Station", "Merrow Bay Terminal Expansion",
    "Glenwick Pipeline Spur", "Saltby Carbon Capture Unit", "Rothwell Grid Reinforcement",
    "Kilbrae Offshore Module", "Hartfield Process Control Retrofit", "Dunmere Tank Farm",
    "Linford Chemical Storage", "Brenfield Flare System", "Ovington LNG Loading Arm",
    "Pellow Wind Substation", "Strathcorr Compressor Station", "Weybury Effluent Plant",
    "Harrowgate Gas Metering", "Calder Moss Battery Storage", "Ennerby Steam Network",
]
CUSTOMERS = [
    "Norvale Energy plc", "Ardent Water Ltd", "Caledon Power Networks", "Tamsin Petrochemicals",
    "Eastmarch Utilities", "Blythe Industrial Holdings",
]
VARIATION_TEXTS = [
    "Additional pipe supports required by revised stress analysis",
    "Relocation of the control room following employer's layout change",
    "Upgraded fire and gas detection to the employer's revised standard",
    "Extra civil works for unforeseen ground conditions at the north pad",
    "Acceleration of mechanical completion at the employer's request",
    "Additional instrumentation loops added in design freeze 2",
    "Temporary power supply extended beyond the agreed period",
]


@dataclass
class SimContract:
    terms: Terms
    report: CostReport
    xer_tables: xer.Tables
    ledger: list[dict[str, str]]
    docs: dict[str, str]
    answers: AnswerKey
    label: ContractLabel


def scenario_sequence(n: int, rng: random.Random) -> list[str]:
    base = [s for s, w in SCENARIO_WEIGHTS.items() for _ in range(w)]
    seq: list[str] = []
    while len(seq) < n:
        chunk = base[:]
        rng.shuffle(chunk)
        seq.extend(chunk)
    return seq[:n]


def _round_k(x: float) -> float:
    return float(round(x / 1000.0) * 1000)


def build_contract(idx: int, scenario: str, seed: int, period_end: date = PERIOD_END) -> SimContract:
    rng = random.Random(seed * 10_007 + idx)
    cid = f"C{idx:03d}"
    customer = rng.choice(CUSTOMERS)

    # --- the contract -----------------------------------------------------------
    price = _round_k(rng.uniform(20, 180) * 1e6)
    bid_margin = rng.uniform(0.06, 0.14)
    bac = price * (1 - bid_margin)
    total_days = round(rng.randint(18, 36) * 30.44)
    f_plan = rng.uniform(0.35, 0.75)
    start = period_end - timedelta(days=round(f_plan * total_days))
    completion = start + timedelta(days=total_days)
    terms = Terms(
        contract_id=cid,
        name=PROJECTS[(idx - 1) % len(PROJECTS)],
        customer=customer,
        contract_price=price,
        start_date=start,
        completion_date=completion,
        ld_rate_per_day=_round_k(price * rng.uniform(0.0003, 0.0008)),
        ld_cap=_round_k(price * rng.choice([0.05, 0.1, 0.15])),
    )

    # --- true performance -------------------------------------------------------
    if scenario == "e2_one_off_overrun":
        cpi, spi = rng.uniform(0.82, 0.88), rng.uniform(0.88, 0.95)
        cpi_fwd = rng.uniform(0.98, 1.02)  # the overrun is behind them
    elif scenario in POOR_PERFORMERS:
        cpi, spi = rng.uniform(0.80, 0.90), rng.uniform(0.80, 0.92)
        cpi_fwd = cpi + rng.uniform(0.0, 0.03)
    elif scenario == "m1_no_provision":
        cpi, spi = rng.uniform(0.76, 0.82), rng.uniform(0.85, 0.95)
        cpi_fwd = cpi
    else:
        cpi, spi = rng.uniform(0.97, 1.04), rng.uniform(0.95, 1.03)
        cpi_fwd = cpi + rng.uniform(-0.02, 0.02)

    # --- schedule: cost-loaded activities ---------------------------------------
    n_act = rng.randint(20, 36)
    weights = [rng.uniform(0.5, 1.5) for _ in range(n_act)]
    wsum = sum(weights)
    slip_days = max(0, round(total_days * (1 / spi - 1) * 0.6))
    tasks, rsrcs = [], []
    ev = pv = 0.0
    for k in range(n_act):
        budget = bac * weights[k] / wsum
        s = start + timedelta(days=round(total_days * 0.85 * k / n_act))
        e = s + timedelta(days=round(total_days * rng.uniform(0.12, 0.25)))
        if k == n_act - 1 or e > completion:
            e = completion
        planned = xer.planned_fraction(s, e, period_end)
        pct = min(1.0, planned * spi * rng.uniform(0.97, 1.03))
        ev += budget * pct
        pv += budget * planned
        done = pct >= 0.999
        tasks.append(
            {
                "task_id": str(1000 + k),
                "proj_id": cid,
                "task_code": f"A{k + 1:03d}",
                "task_name": f"Work package {k + 1}",
                "phys_complete_pct": f"{pct * 100:.1f}",
                "target_start_date": xer.fmt_date(s),
                "target_end_date": xer.fmt_date(e),
                "early_end_date": "" if done
                else xer.fmt_date(max(period_end + timedelta(days=1), e + timedelta(days=slip_days))),
                "act_end_date": xer.fmt_date(min(e, period_end)) if done else "",
            }
        )
        rsrcs.append(
            {
                "taskrsrc_id": str(5000 + k),
                "task_id": str(1000 + k),
                "proj_id": cid,
                "target_cost": f"{budget:.2f}",
                "act_reg_cost": f"{budget * pct / cpi:.2f}",
            }
        )
    xer_tables: xer.Tables = {
        "PROJECT": [
            {
                "proj_id": cid,
                "proj_short_name": cid,
                "last_recalc_date": xer.fmt_date(period_end),
                "plan_start_date": xer.fmt_date(start),
                "plan_end_date": xer.fmt_date(completion),
                "scd_end_date": xer.fmt_date(completion + timedelta(days=slip_days)),
            }
        ],
        "TASK": tasks,
        "TASKRSRC": rsrcs,
    }

    ac = _round_k(ev / cpi)
    true_etc = _round_k((bac - ev) / cpi_fwd)

    # --- variations ---------------------------------------------------------------
    texts = rng.sample(VARIATION_TEXTS, k=len(VARIATION_TEXTS))
    variations: list[Variation] = []
    letters: dict[str, tuple[str, float | None]] = {}  # vo id -> (letter kind, counter offer)

    def new_vo(kind: str, included: bool, reported: str) -> Variation:
        n = len(variations) + 1
        v = Variation(
            id=f"VO-{n:03d}",
            description=texts[n - 1],
            amount=_round_k(price * rng.uniform(0.01, 0.05)),
            included_in_tp=included,
            reported_status=reported,
        )
        variations.append(v)
        if kind != "none":
            counter = _round_k(v.amount * rng.uniform(0.4, 0.7)) if kind == "in_principle" else None
            letters[v.id] = (kind, counter)
        return v

    for _ in range(rng.randint(0, 2)):  # approved and booked: the natural hard negatives for T1
        new_vo("approved", True, "Approved")
    if rng.random() < 0.3:  # submitted, rightly left out of TP: no judgement to make
        new_vo("pending", False, "Submitted")

    if scenario == "t1_unaccepted":
        new_vo(rng.choice(["rejected", "pending"]), True, "Approved (commercial view)")
    elif scenario == "t1_in_principle":
        new_vo("in_principle", True, "Agreed in principle")
    elif scenario == "t1_no_evidence":
        new_vo("none", True, "Approved")

    # --- management's view ----------------------------------------------------------
    commentary = "Project performing in line with forecast."
    minutes = [
        "Safety: no reportable incidents in the period.",
        "Progress reviewed against the P6 programme update.",
    ]
    mgmt_etc = true_etc
    if scenario == "e2_etc_understated":
        mgmt_etc = _round_k(bac - ev)
        commentary = "ETC reflects remaining budget. Team confident of recovering productivity."
        minutes.append("Commercial Manager noted productivity below plan; no change to forecast agreed.")
    elif scenario == "e2_recovery_plan":
        assumed = (cpi + 1.0) / 2
        mgmt_etc = _round_k((bac - ev) / assumed)
        commentary = "ETC assumes recovery plan savings (resequencing and subcontract renegotiation)."
        minutes.append(
            "Recovery plan presented: resequence piping and renegotiate the mechanical subcontract. "
            "Subcontractor has not yet agreed revised rates. Savings included in ETC pending agreement."
        )
    elif scenario == "e2_one_off_overrun":
        commentary = ("Overrun to date reflects one-off pipe rack rework after a supplier defect, now "
                      "complete. Remaining work forecast at current productivity, which is back to plan.")
        minutes.append(
            "Project controls confirmed the pipe rack rework is complete and closed out. Productivity "
            "on remaining work has been at or above plan for the last three months. The supplier has "
            "accepted liability for the defect; recovery is being pursued separately and is not in TP."
        )
    elif scenario in POOR_PERFORMERS or scenario == "m1_no_provision":
        commentary = "Productivity below plan; ETC reforecast to reflect current performance."
        minutes.append("ETC reforecast bottom-up by project controls to reflect actual productivity.")

    def make_report(etc: float, vos: list[Variation], provision: float, text: str) -> CostReport:
        return CostReport(
            contract_id=cid, period_end=period_end, contract_price=price,
            variations=[v.model_copy() for v in vos], cost_to_date=ac, etc=etc,
            provision_booked=provision, commentary=text,
        )

    # provision management books on its own numbers
    draft = make_report(mgmt_etc, variations, 0.0, commentary)
    own_required = _round_k(engine.position(draft.inputs()).provision_required)
    provision = 0.0 if scenario == "m1_no_provision" else own_required
    if scenario == "m1_no_provision":
        minutes.append("Finance to consider whether a loss provision is required. Deferred to next review.")
    report = make_report(mgmt_etc, variations, provision, commentary)

    # --- ground truth: an answer key, compiled by the same code that reads hand-edited keys ---
    judgements: list[Judgement] = []
    for v in [v for v in variations if v.included_in_tp]:
        kind = letters.get(v.id, ("none", None))[0]
        remove = Correction(variations={v.id: 0.0})
        if kind == "approved":
            judgements.append(Judgement(check="T1", ref=v.id, verdict="supported",
                                        why=f"Customer accepted in writing (letter_{v.id}.md)."))
        elif kind in ("rejected", "pending"):
            judgements.append(Judgement(
                check="T1", ref=v.id, verdict="misstated", correction=remove, tag=f"t1_{kind}",
                why=f"Customer letter ({kind}) shows no agreement, so it is not a valid modification."))
        elif kind == "in_principle":
            counter = letters[v.id][1] or 0.0
            judgements.append(Judgement(
                check="T1", ref=v.id, verdict="judgement_call", tag="t1_in_principle",
                range=EffectRange(low=Correction(variations={v.id: counter})),
                why="Scope agreed in principle, value disputed: an estimate subject to the constraint, "
                    "between the customer's counter-offer and our valuation."))
        else:  # no customer correspondence in the file
            judgements.append(Judgement(
                check="T1", ref=v.id, verdict="insufficient_evidence", correction=remove,
                range=EffectRange(low=remove), tag="t1_no_evidence",
                request=f"Customer written agreement to {v.id}",
                why="Register says approved, but there is no customer agreement in the file."))

    true_etc_fix = Correction(etc=true_etc)
    if scenario == "e2_etc_understated":
        judgements.append(Judgement(
            check="E2", ref="ETC", verdict="misstated", correction=true_etc_fix, tag=scenario,
            why="Remaining work forecast at budget despite CPI well below 1."))
    elif scenario == "e2_recovery_plan":
        judgements.append(Judgement(
            check="E2", ref="ETC", verdict="judgement_call", correction=true_etc_fix,
            range=EffectRange(low=true_etc_fix), tag=scenario,
            why="ETC relies on recovery savings the subcontractor has not agreed."))
    elif scenario in POOR_PERFORMERS:
        judgements.append(Judgement(
            check="E2", ref="ETC", verdict="supported", tag=scenario,
            why="Earned value looks poor, but the minutes and ETC explain it."))
    else:
        judgements.append(Judgement(check="E2", ref="ETC", verdict="supported"))

    if scenario == "m1_no_provision":
        judgements.append(Judgement(
            check="M1", ref="PROVISION", verdict="misstated", tag=scenario,
            why="Management's own EAC exceeds TP and no onerous provision is booked."))
    else:
        judgements.append(Judgement(check="M1", ref="PROVISION", verdict="supported"))

    answers = AnswerKey(contract_id=cid, scenario=scenario, notes=SCENARIO_NOTES[scenario],
                        judgements=judgements)

    # --- documents ------------------------------------------------------------------
    docs: dict[str, str] = {
        "contract.md": render.contract_doc(terms, CONTRACTOR),
        f"minutes_{period_end:%Y-%m}.md": render.minutes_doc(cid, period_end, minutes),
    }
    for v in variations:
        sub_date = start + timedelta(days=rng.randint(60, max(61, (period_end - start).days - 30)))
        docs[f"submission_{v.id}.md"] = render.submission_doc(cid, v, CONTRACTOR, customer, sub_date)
        if v.id in letters:
            kind, counter = letters[v.id]
            # a little realistic mess: customers don't always use our reference format
            ref = v.id if rng.random() < 0.7 else v.id.replace("VO-0", "VO ").replace("VO-", "VO ")
            docs[f"letter_{v.id}.md"] = render.letter_doc(
                cid, ref, kind, v.amount, customer, sub_date + timedelta(days=rng.randint(14, 45)), counter
            )

    # --- ledger -----------------------------------------------------------------------
    months = max(1, (period_end.year - start.year) * 12 + period_end.month - start.month)
    shape = [(m + 1) ** 1.3 for m in range(months)]
    ssum = sum(shape)
    ledger: list[dict[str, str]] = []
    running = 0.0
    for m in range(months):
        y, mo = divmod(start.month - 1 + m + 1, 12)
        month_end = date(start.year + y, mo + 1, 1) - timedelta(days=1)
        month_total = ac - running if m == months - 1 else round(ac * shape[m] / ssum, 2)
        running += month_total
        split = [0.55, 0.30, 0.15]
        for code, share in zip(["CC-10 Labour", "CC-20 Subcontract", "CC-30 Materials"], split, strict=True):
            ledger.append({"period_end": month_end.isoformat(), "cost_code": code,
                           "amount": f"{month_total * share:.2f}"})

    return SimContract(terms, report, xer_tables, ledger, docs, answers, compile_key(answers, report))


def generate(n: int = 30, seed: int = 0, period_end: date = PERIOD_END) -> list[SimContract]:
    rng = random.Random(seed)
    return [build_contract(i + 1, s, seed, period_end)
            for i, s in enumerate(scenario_sequence(n, rng))]


def write_portfolio(out: Path, n: int = 30, seed: int = 0, name: str | None = None) -> list[SimContract]:
    """Write a fresh portfolio in the hand-editable layout described in store.py."""
    contracts = generate(n, seed)
    (out / "answers").mkdir(parents=True, exist_ok=True)
    for c in contracts:
        cdir = out / "contracts" / c.terms.contract_id
        (cdir / "docs").mkdir(parents=True, exist_ok=True)
        (cdir / "terms.yaml").write_text(terms_yaml(c.terms))
        (cdir / "cost_report.yaml").write_text(cost_report_yaml(c.report))
        xer.write(cdir / "schedule.xer", c.xer_tables, PERIOD_END)
        with (cdir / "ledger.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["period_end", "cost_code", "amount"])
            w.writeheader()
            w.writerows(c.ledger)
        for doc_name, text in c.docs.items():
            (cdir / "docs" / doc_name).write_text(text)
        (out / "answers" / f"{c.terms.contract_id}.yaml").write_text(answers_yaml(c.answers))
    (out / "portfolio.yaml").write_text(
        f"name: {name or out.name}\n"
        f"period_end: {PERIOD_END.isoformat()}\n"
        f"origin: generated by second-source simulator v{GENERATOR_VERSION}, seed {seed}\n"
    )
    return contracts
