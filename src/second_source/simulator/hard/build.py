"""Builds a hard portfolio: realistic volume, indirect evidence, traps and escalations.

    uv run second-source simulate-hard --out portfolios/hard --n 20 --seed 0

Planning is deterministic (seeded). The prose of key letters and emails is
drafted by a model from fact sheets and validated (see writer.py); routine
documents come from a committed pool. Needs ANTHROPIC_API_KEY for the key
documents; accepted drafts are cached in .cache/writer.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from ... import engine, xer
from ...answers import AnswerKey, Judgement, compile_key
from ...formats import answers_yaml, cost_report_yaml, terms_yaml
from ...models import CostReport, Terms, Variation
from . import bulk, stories
from .stories import (
    E2_PARAMS,
    E2_WEIGHTS,
    LOSS_STORIES,
    T1_STORIES,
    VARIATION_POOL,
    Numbers,
    Out,
    Var,
    deck,
    e2_etc,
    e2_story,
    m1_story,
    scenario_name,
)
from .world import CONTRACTOR, PERIOD_END, World, add_months, contract_md, make_world, money

GENERATOR_VERSION = "hard-0.1"
LOSSY_E2 = {"e2_reflected", "e2_cpi_trend", "e2_one_off", "e2_recovery", "e2_smoothing"}
REGISTER_STATUSES = ["Approved"] * 5 + ["Agreed"] * 3 + ["Approved (commercial view)", "Instructed"]
M1_HARD_WEIGHTS = {"m1_routine": 14, "m1_ok_provided": 2, "m1_no_provision": 2, "m1_stale": 2}


@dataclass
class Plan:
    world: World
    terms: Terms
    report: CostReport
    tables: xer.Tables
    ledger: list[dict[str, str]]
    docs: dict[str, str]
    specs: list[stories.Spec]
    answers: AnswerKey
    stories: list[str] = field(default_factory=list)


def _d0_window(story: str, start: date) -> tuple[date, date]:
    lo = max(start + timedelta(days=30), date(2026, 6, 15))
    hi = {
        "t1_ok_after_query": date(2026, 9, 15),
        "t1_withdrawn": date(2026, 9, 15),
        "t1_time_barred": date(2026, 7, 31),
        "t1_post_period": date(2026, 11, 10),
        "t1_no_response": date(2026, 9, 30),
    }.get(story, date(2026, 10, 31))
    if story == "t1_time_barred":
        lo = max(lo - timedelta(days=10), date(2026, 6, 8))
    if story == "t1_post_period":
        lo = max(lo, date(2026, 9, 15))
    return lo, max(lo + timedelta(days=5), hi)


def _ledger(start: date, ac: float, rng: random.Random, materials_spike: float = 0.0) -> list[dict[str, str]]:
    months = max(1, (PERIOD_END.year - start.year) * 12 + PERIOD_END.month - start.month)
    shape = [(m + 1) ** 1.25 * rng.uniform(0.85, 1.15) for m in range(months)]
    base = ac - materials_spike
    ssum = sum(shape)
    rows, running = [], 0.0
    for m in range(months):
        y, mo = divmod(start.month - 1 + m + 1, 12)
        month_end = date(start.year + y, mo + 1, 1) - timedelta(days=1)
        total = round(base * shape[m] / ssum, 2)
        split = {
            "CC-10 Labour": 0.34,
            "CC-20 Subcontract": 0.38,
            "CC-30 Materials": 0.18,
            "CC-40 Preliminaries": 0.10,
        }
        for code, share in split.items():
            amt = round(total * share, 2)
            if (
                code == "CC-30 Materials"
                and materials_spike
                and month_end.month in (10, 11)
                and month_end.year == 2026
            ):
                amt += round(materials_spike / 2, 2)
            rows.append({"period_end": month_end.isoformat(), "cost_code": code, "amount": f"{amt:.2f}"})
            running += amt
    last = rows[-1]
    last["amount"] = f"{float(last['amount']) + round(ac - running, 2):.2f}"
    return rows


def _ac_at(ledger: list[dict[str, str]], d: date) -> float:
    return round(sum(float(r["amount"]) for r in ledger if date.fromisoformat(r["period_end"]) <= d))


def plan_contract(idx: int, seed: int, t1: list[str], e2: str, m1: str) -> Plan:
    rng = random.Random(seed * 7919 + idx)
    cid = f"C{idx:03d}"
    params = E2_PARAMS[e2]
    loss = m1 in LOSS_STORIES

    for _attempt in range(400):
        price = round(rng.uniform(25, 160) * 1e6, -1)
        span_m = rng.randint(22, 36)
        span = round(span_m * 30.44)
        f_plan = rng.uniform(0.38, 0.70)
        start = PERIOD_END - timedelta(days=round(f_plan * span))
        baseline = start + timedelta(days=span)
        slip_m = rng.randint(*params["slip"]) if params["slip"] else 0
        forecast = add_months(baseline, slip_m) if slip_m else baseline + timedelta(days=rng.randint(0, 18))
        completion = max(
            forecast + timedelta(days=rng.randint(20, 60)), baseline + timedelta(days=rng.randint(90, 200))
        )
        margin = rng.uniform(-0.01, 0.04) if loss else rng.uniform(0.06, 0.13)
        bac = price * (1 - margin)
        prelims_share = rng.uniform(0.08, 0.12)
        rate = round(bac * prelims_share / span_m, -2)
        cpi = rng.uniform(*params["cpi"])
        cpi_fwd = cpi + rng.uniform(0.0, 0.02) if params["fwd"] == "same" else rng.uniform(0.99, 1.02)
        spi = rng.uniform(0.86, 0.95) if cpi < 0.92 else rng.uniform(0.93, 1.02)

        w = make_world(cid, idx, rng, price, start, baseline, completion)
        tables = bulk.schedule(w, rng, bac, spi, forecast, prelims_share)
        sm = xer.metrics(tables)
        rem = sm.bac - sm.ev
        mgmt_etc, true_etc, extra = e2_etc(e2, rng, rem, cpi_fwd, rate, slip_m, sm.ev / cpi)
        ac = round(sm.ev / cpi + extra.get("materials", 0.0))

        # variations: stories for those in TP, plus a few correctly left out
        n_in = len(t1)
        amounts = [round(price * rng.uniform(0.004, 0.03)) for _ in range(n_in)]
        tp = price + sum(amounts)
        eac = ac + mgmt_etc
        if loss and eac > tp * 1.004 and eac - tp > 250_000:
            break
        if not loss and eac < tp * 0.985:
            break
    else:
        raise RuntimeError(f"{cid}: couldn't satisfy the number constraints for {e2}/{m1}")

    # --- variations and their stories ---------------------------------------------
    descs = rng.sample(VARIATION_POOL, k=n_in + 3)
    vars_: list[tuple[str, Var]] = []
    for k, story in enumerate(t1):
        lo, hi = _d0_window(story, start)
        d0 = lo + timedelta(days=rng.randint(0, (hi - lo).days))
        vars_.append(
            (
                story,
                Var(vo="", desc=descs[k][0], short=descs[k][1], amount=amounts[k], quote="", eri="", d0=d0),
            )
        )
    excluded = [
        Var(
            vo="",
            desc=descs[n_in + j][0],
            short=descs[n_in + j][1],
            amount=round(price * rng.uniform(0.003, 0.015)),
            quote="",
            eri="",
            d0=date(2026, rng.randint(8, 11), rng.randint(1, 28)),
        )
        for j in range(rng.randint(0, 2))
    ]
    needs_other = [v for s, v in vars_ if s == "t1_missing_attachment"]
    others = {
        id(v): Var(
            vo="",
            desc=descs[-1][0],
            short=descs[-1][1],
            amount=round(price * 0.006),
            quote="",
            eri="",
            d0=v.d0,
        )
        for v in needs_other
    }
    everything = [v for _, v in vars_] + excluded + list(others.values())
    for n, v in enumerate(sorted(everything, key=lambda v: v.d0), start=1):
        v.vo = f"VO-{n:03d}"
    for v in sorted(everything, key=lambda v: v.d0):
        v.quote, v.eri = w.ref("quote"), w.ref("eri")

    outs: list[Out] = []
    for story, v in vars_:
        fn = T1_STORIES[story][0]
        outs.append(fn(w, rng, v, others[id(v)]) if story == "t1_missing_attachment" else fn(w, rng, v))
    # Register statuses are drawn independently of the story, so the status column carries no answer.
    srng = random.Random(seed * 104_729 + idx)
    for o in outs:
        for reg in o.variations:
            if reg.included_in_tp:
                reg.reported_status = srng.choice(REGISTER_STATUSES)
    for v in excluded:
        o = Out(
            variations=[
                Variation(
                    id=v.vo,
                    description=v.desc,
                    amount=v.amount,
                    included_in_tp=False,
                    reported_status=rng.choice(["Submitted", "Under review"]),
                )
            ],
            specs=[stories._submission(w, v, v.d0, mention_eri=False)],
        )
        outs.append(o)

    numbers = Numbers(
        bac=sm.bac,
        ev=sm.ev,
        ac=ac,
        cpi_shown=sm.ev / ac,
        cpi_fwd=cpi_fwd,
        mgmt_etc=mgmt_etc,
        true_etc=true_etc,
        prelims_rate=rate,
        baseline_finish=baseline,
        forecast_finish=forecast,
        extra=extra,
    )
    e2_out = e2_story(e2, w, rng, numbers)

    register = sorted([v for o in outs for v in o.variations], key=lambda v: v.id)
    draft = CostReport(
        contract_id=cid,
        period_end=PERIOD_END,
        contract_price=price,
        variations=register,
        cost_to_date=ac,
        etc=mgmt_etc,
        etc_breakdown=e2_out.breakdown,
    )
    pos = engine.position(draft.inputs())
    required = round(pos.provision_required, -3)
    booked = {"m1_ok_provided": required, "m1_stale": round(required * rng.uniform(0.35, 0.7), -3)}.get(
        m1, 0.0
    )
    m1_out = m1_story(m1, w, pos.provision_required, booked, pos.expected_loss)
    commentary = " ".join(e2_out.commentary + m1_out.commentary)
    report = draft.model_copy(update={"provision_booked": booked, "commentary": commentary})

    # --- documents -------------------------------------------------------------------
    _, paras = bulk._pool()
    every = outs + [e2_out, m1_out]
    plants = [p for o in every for p in o.plants]
    specs = [s for o in every for s in o.specs]
    ledger = _ledger(start, ac, rng, extra.get("materials", 0.0))
    p_final = engine.position(report.inputs())
    eac_q3 = p_final.eac if e2 == "e2_smoothing" else round(p_final.eac * rng.uniform(0.985, 1.0))
    reg_lines = [
        f"{v.id} {v.description}: {money(v.amount)}, {v.reported_status}"
        + ("" if v.included_in_tp else " (not in forecast)")
        for v in register
    ]
    docs: dict[str, str] = {"contract.md": contract_md(w)}
    docs.update(bulk.diaries(w, rng, tables, plants, paras))
    docs.update(
        bulk.minutes(
            w,
            rng,
            tables,
            plants,
            paras,
            sm.physical_pct,
            e2 in ("e2_prelims_slip", "e2_slip_covered"),
            forecast,
        )
    )
    docs.update(
        bulk.cost_reviews(
            w,
            rng,
            plants,
            paras,
            {"ac": ac, "etc": mgmt_etc, "eac": p_final.eac, "tp": p_final.tp},
            reg_lines,
            eac_q3,
            _ac_at(ledger, date(2026, 9, 30)),
        )
    )
    routine, routine_reg = bulk.routine_docs(w, rng, rng.randint(32, 46))
    docs.update(routine)
    letters = [
        (s.on, s.ref, s.sender.name, s.to[0].name, s.subject)
        for s in specs
        if s.kind == "letter" and s.in_register and s.ref
    ]
    letters += [r for o in every for r in o.register_only] + routine_reg
    docs["correspondence-register.md"] = bulk.correspondence_register(w, rng, letters)
    docs["rfi-log.md"] = bulk.rfi_log(w, rng, plants)
    for s in specs:
        while s.name in docs or any(s.name == t.name for t in specs if t is not s):
            s.name = s.name.replace(".md", "-a.md")

    judgements: list[Judgement] = sorted([o.judgement for o in outs if o.judgement], key=lambda j: j.ref) + [
        e2_out.judgement,
        m1_out.judgement,
    ]
    answers = AnswerKey(
        contract_id=cid,
        scenario=scenario_name(t1, e2, m1),
        notes=f"{len(t1)} variations in TP; E2 {e2}; M1 {m1}.",
        judgements=judgements,
    )
    terms = Terms(
        contract_id=cid,
        name=w.project,
        customer=w.customer,
        contract_price=price,
        start_date=start,
        completion_date=completion,
        ld_rate_per_day=w.ld_rate,
        ld_cap=w.ld_cap,
    )
    return Plan(w, terms, report, tables, ledger, docs, specs, answers, stories=t1 + [e2, m1])


def plan_portfolio(n: int, seed: int) -> list[Plan]:
    rng = random.Random(seed)
    n_vars = [rng.choice([2, 3, 3, 4, 4, 5]) for _ in range(n)]
    t1_deck = deck({k: v[1] for k, v in T1_STORIES.items()}, sum(n_vars), rng)
    e2_deck = deck(E2_WEIGHTS, n, rng)
    m1_deck = deck(M1_HARD_WEIGHTS, n, rng)
    # pair loss-making M1 stories with E2 stories where a loss is plausible
    losses = [m for m in m1_deck if m in LOSS_STORIES]
    lossy = [i for i, e in enumerate(e2_deck) if e in LOSSY_E2]
    rng.shuffle(lossy)
    m1_final = ["m1_routine"] * n
    for i, m in zip(lossy, losses, strict=False):
        m1_final[i] = m
    plans, k = [], 0
    for i in range(n):
        t1 = t1_deck[k : k + n_vars[i]]
        k += n_vars[i]
        plans.append(plan_contract(i + 1, seed, t1, e2_deck[i], m1_final[i]))
    return plans


def write_portfolio(out: Path, n: int = 20, seed: int = 0, workers: int = 8) -> list[Plan]:
    from . import writer

    plans = plan_portfolio(n, seed)
    written = writer.write_all([(p.world, s) for p in plans for s in p.specs], workers=workers)
    (out / "answers").mkdir(parents=True, exist_ok=True)
    for p in plans:
        cid = p.world.cid
        cdir = out / "contracts" / cid
        (cdir / "docs").mkdir(parents=True, exist_ok=True)
        (cdir / "terms.yaml").write_text(terms_yaml(p.terms))
        (cdir / "cost_report.yaml").write_text(cost_report_yaml(p.report))
        xer.write(cdir / "schedule.xer", p.tables, PERIOD_END)
        with (cdir / "ledger.csv").open("w", newline="") as f:
            wr = csv.DictWriter(f, fieldnames=["period_end", "cost_code", "amount"])
            wr.writeheader()
            wr.writerows(p.ledger)
        for name, text in p.docs.items():
            (cdir / "docs" / name).write_text(text)
        for s in p.specs:
            (cdir / "docs" / s.name).write_text(written[(cid, s.name)])
        (out / "answers" / f"{cid}.yaml").write_text(answers_yaml(p.answers))
        compile_key(p.answers, p.report)  # fail loudly if a key doesn't compile
    (out / "portfolio.yaml").write_text(
        f"name: {out.name}\nperiod_end: {PERIOD_END.isoformat()}\n"
        f"origin: generated by second-source hard simulator {GENERATOR_VERSION}, seed {seed}; "
        f"key documents drafted by {writer.KEY_MODEL}, routine documents from the committed pool\n"
        f"contractor: {CONTRACTOR}\n"
    )
    return plans
