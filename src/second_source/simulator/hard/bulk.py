"""The bulk of a contract file: the paperwork any real project produces, built from code.

Volume is part of what makes a file hard. These generators produce a large P6
programme, a daily site diary, monthly progress minutes, internal cost reviews,
a correspondence register, an RFI log and dozens of routine letters and emails
from a reusable pool. Planted story entries (`Plant`) are woven into them so
that key facts sit among hundreds of ordinary ones.
"""

from __future__ import annotations

import json
import random
from datetime import date, timedelta
from pathlib import Path

from ... import xer
from .stories import Plant, Spec
from .world import AREAS, CONTRACTOR, PERIOD_END, REVIEW_DATE, World, long_date, money, working_days

POOL_DIR = Path(__file__).parent / "pool"

DISCIPLINES = [
    (
        "Civils",
        (0.00, 0.38),
        ["Excavate and blind", "Pour foundations", "Backfill and compact", "Install underground drainage"],
    ),
    (
        "Structural",
        (0.15, 0.55),
        ["Erect primary steel", "Erect secondary steel", "Install grating and handrail"],
    ),
    ("Mechanical", (0.30, 0.70), ["Set equipment", "Align rotating equipment", "Install package skids"]),
    ("Piping", (0.30, 0.85), ["Fabricate spools", "Install spools", "Hydrotest", "Reinstate and box up"]),
    ("Electrical", (0.40, 0.88), ["Install cable tray", "Pull cables", "Terminate and test"]),
    ("Instrumentation", (0.50, 0.92), ["Install instruments", "Install tubing", "Loop check"]),
    ("Commissioning", (0.82, 1.00), ["Pre-commission systems", "Function test"]),
]


def _pool() -> tuple[list[dict], dict[str, list[str]]]:
    docs = json.loads((POOL_DIR / "docs.json").read_text())
    paras = json.loads((POOL_DIR / "paragraphs.json").read_text())
    return docs, paras


def fill(w: World, text: str, rng: random.Random) -> str:
    sub_co, _, sub_contact = rng.choice(w.subs)
    values = {
        "PROJECT": w.project,
        "SITE": w.site,
        "CUSTOMER": w.customer,
        "ER": w.er.name,
        "CUST_PM": w.cust_pm.name,
        "COW": w.cow.name,
        "PM": w.pm.name,
        "SITE_MGR": w.site_mgr.name,
        "PLANNER": w.planner.name,
        "QS": w.qs.name,
        "SUB": sub_co,
        "SUB_CONTACT": sub_contact.name,
        "AREA": rng.choice(AREAS),
        "CUST_QS": w.cust_qs.name,
        "CM": w.cm.name,
    }
    for k, v in values.items():
        text = text.replace(f"[{k}]", v)
    return text


# ---------------------------------------------------------------------------
# P6 programme
# ---------------------------------------------------------------------------


def schedule(
    w: World, rng: random.Random, bac: float, spi: float, forecast_finish: date, prelims_share: float
) -> xer.Tables:
    """A cost-loaded programme of a few hundred activities. Forecast finish is set exactly."""
    s0, b = w.start, w.baseline_finish
    span = (b - s0).days
    areas = AREAS[: rng.randint(4, 6)]
    rows: list[tuple[str, str, date, date, float, bool]] = []  # wbs, name, start, end, weight, loe
    for disc, (f0, f1), acts in DISCIPLINES:
        for a_i, area in enumerate(areas):
            stagger = 0.05 * a_i
            for k, act in enumerate(acts):
                parts = rng.randint(1, 3) if disc in ("Piping", "Electrical", "Civils") else 1
                for p in range(parts):
                    lo = min(f1 - 0.05, f0 + stagger + (f1 - f0) * (k + p / parts) / (len(acts) + 1) * 0.8)
                    dur = rng.uniform(0.05, 0.14)
                    st = s0 + timedelta(days=round(span * max(0.0, lo)))
                    en = min(b, st + timedelta(days=max(10, round(span * dur))))
                    if disc == "Commissioning" and k == len(acts) - 1 and a_i == len(areas) - 1:
                        en = b
                    label = f"{area} - {disc} - {act}" + (f" (part {p + 1} of {parts})" if parts > 1 else "")
                    rows.append(
                        (
                            f"{w.code}.{area.split()[1]}.{disc[:3].upper()}",
                            label,
                            st,
                            en,
                            rng.uniform(0.4, 1.6),
                            False,
                        )
                    )
    rows.insert(0, (f"{w.code}.PRE", "Site establishment, preliminaries and supervision", s0, b, 0.0, True))
    rows.insert(
        1,
        (
            f"{w.code}.ENG",
            "Detailed design and engineering",
            s0,
            s0 + timedelta(days=round(span * 0.45)),
            0.0,
            False,
        ),
    )

    work_w = sum(r[4] for r in rows if not r[5] and r[1] != "Detailed design and engineering")
    design_budget = bac * 0.07
    prelims_budget = bac * prelims_share
    work_budget = bac - design_budget - prelims_budget
    slip_total = (forecast_finish - b).days
    tasks, rsrcs = [], []
    for k, (wbs, name, st, en, wt, loe) in enumerate(rows):
        if loe:
            budget = prelims_budget
        elif name.startswith("Detailed design"):
            budget = design_budget
        else:
            budget = work_budget * wt / work_w
        planned = xer.planned_fraction(st, en, PERIOD_END)
        if loe:
            pct = planned
        else:
            pct = min(1.0, planned * spi * rng.uniform(0.96, 1.04)) if planned > 0 else 0.0
        done = pct >= 0.999
        frac = max(0.0, min(1.0, (en - s0).days / span))
        slip = round(slip_total * frac**2) if not done else 0
        early_end = (
            "" if done else xer.fmt_date(max(PERIOD_END + timedelta(days=1), en + timedelta(days=slip)))
        )
        if en == b and not loe:
            early_end = xer.fmt_date(forecast_finish)
        if loe:
            early_end = xer.fmt_date(forecast_finish)
        status = "TK_Complete" if done else ("TK_Active" if pct > 0 else "TK_NotStart")
        tasks.append(
            {
                "task_id": str(10000 + k),
                "proj_id": w.cid,
                "wbs_id": wbs,
                "task_code": f"A{1000 + 10 * k}",
                "task_name": name,
                "task_type": "TT_LOE" if loe else "TT_Task",
                "status_code": status,
                "phys_complete_pct": f"{pct * 100:.1f}",
                "target_start_date": xer.fmt_date(st),
                "target_end_date": xer.fmt_date(en),
                "act_start_date": xer.fmt_date(st) if pct > 0 else "",
                "act_end_date": xer.fmt_date(min(en, PERIOD_END)) if done else "",
                "early_end_date": early_end,
                "total_float_hr_cnt": str(rng.choice([0, 0, 40, 80, 160, 240, 400])),
            }
        )
        rsrcs.append(
            {
                "taskrsrc_id": str(50000 + k),
                "task_id": str(10000 + k),
                "proj_id": w.cid,
                "rsrc_id": rng.choice(["LAB", "SUBC", "MATL", "PLANT"]) if not loe else "PRELIMS",
                "target_cost": f"{budget:.2f}",
                "act_reg_cost": f"{budget * pct:.2f}",
            }
        )
    return {
        "PROJECT": [
            {
                "proj_id": w.cid,
                "proj_short_name": f"{w.code}-EPC",
                "last_recalc_date": xer.fmt_date(PERIOD_END),
                "plan_start_date": xer.fmt_date(s0),
                "plan_end_date": xer.fmt_date(b),
                "scd_end_date": xer.fmt_date(forecast_finish),
            }
        ],
        "TASK": tasks,
        "TASKRSRC": rsrcs,
    }


def active_on(tables: xer.Tables, d: date) -> list[str]:
    out = []
    for t in tables["TASK"]:
        st = xer.parse_date(t["target_start_date"])
        en = (
            xer.parse_date(t["early_end_date"])
            or xer.parse_date(t["act_end_date"])
            or xer.parse_date(t["target_end_date"])
        )
        if st and en and st <= d <= en and t["task_type"] == "TT_Task":
            out.append(t["task_name"])
    return out


# ---------------------------------------------------------------------------
# site diary, one document per month
# ---------------------------------------------------------------------------

WEATHER = [
    "Dry, overcast",
    "Light rain am, dry pm",
    "Heavy rain from 11:00",
    "Dry and bright",
    "Fog until 10:00",
    "Showers",
    "Strong winds, gusting 35 mph",
    "Frost early, dry",
    "Drizzle all day",
    "Dry, cold",
]
PLANT = [
    "25t excavator",
    "60t mobile crane",
    "telehandler",
    "dumper",
    "MEWP",
    "roller",
    "100t crawler crane",
    "generator",
    "welding set",
    "concrete pump",
]
DELIVERIES = [
    "pipe spool bundles",
    "cable drums",
    "ready-mix concrete",
    "rebar cages",
    "valves",
    "steel sections",
    "grating panels",
    "instrument cabinets",
    "scaffold tube",
    "aggregate",
    "fire stopping materials",
]


def diaries(
    w: World, rng: random.Random, tables: xer.Tables, plants: list[Plant], paras: dict[str, list[str]]
) -> dict[str, str]:
    first = max(w.start + timedelta(days=30), date(2026, 6, 1))
    days = working_days(first, REVIEW_DATE)
    planted: dict[date, list[str]] = {}
    for p in plants:
        if p.target == "diary":
            d = next((x for x in days if x >= p.on), days[-1])
            planted.setdefault(d, []).append(p.text)
    months: dict[str, list[str]] = {}
    for d in days:
        acts = active_on(tables, d)
        progressed = rng.sample(acts, k=min(len(acts), rng.randint(3, 5))) if acts else ["General site works"]
        own = rng.randint(8, 22)
        sub_lab = {s[0]: rng.randint(4, 30) for s in w.subs}
        lines = [
            f"### {d:%A} {long_date(d)}",
            f"**Weather:** {rng.choice(WEATHER)}. {rng.randint(-2, 17)}°C.",
            f"**Labour:** Brackmoor {own}; "
            + "; ".join(f"{k} {v}" for k, v in sub_lab.items())
            + f"; total {own + sum(sub_lab.values())}.",
            "**Plant:** " + ", ".join(f"{rng.randint(1, 3)} x {p}" for p in rng.sample(PLANT, 3)) + ".",
            "**Work progressed:**",
        ] + [f"- {a}" for a in progressed]
        if rng.random() < 0.5:
            lines.append(
                f"**Deliveries:** {rng.randint(2, 12)} x {rng.choice(DELIVERIES)}"
                + (f", {rng.randint(1, 6)} x {rng.choice(DELIVERIES)}" if rng.random() < 0.5 else "")
                + "."
            )
        if rng.random() < 0.25:
            lines.append(
                f"**Visitors:** {rng.choice([w.cow.name + ' (Clerk of Works)', w.cust_pm.name, 'HSE advisor', 'Insurer surveyor', 'Building control'])}."
            )
        notes = []
        if rng.random() < 0.35:
            notes.append(fill(w, rng.choice(paras["diary"]), rng))
        notes += planted.get(d, [])
        if notes:
            lines.append("**Notes:** " + " ".join(notes))
        lines.append(
            f"**HSE:** Toolbox talk: {rng.choice(['manual handling', 'working at height', 'slips and trips', 'lifting operations', 'hand-arm vibration', 'permits to work', 'cold weather working'])}. "
            f"{rng.choice(['No incidents.', 'No incidents.', 'One near miss reported (see HSE log).', 'First aid case: minor cut, returned to work.'])}"
        )
        months.setdefault(f"{d:%Y-%m}", []).append("\n".join(lines))
    return {
        f"{m}_site-diary.md": f"# Site diary: {w.project}\n\n**Site Manager:** {w.site_mgr.name}\n"
        f"**Month:** {date.fromisoformat(m + '-01'):%B %Y}\n\n" + "\n\n".join(entries) + "\n"
        for m, entries in months.items()
    }


# ---------------------------------------------------------------------------
# progress meetings with the customer, monthly
# ---------------------------------------------------------------------------


def meeting_dates(w: World) -> list[date]:
    out = []
    for y, m in [(2026, 7), (2026, 8), (2026, 9), (2026, 10), (2026, 11), (2026, 12), (2027, 1)]:
        d = date(y, m, 1)
        while d.weekday() != 3:
            d += timedelta(days=1)
        if m == 1:
            d += timedelta(days=7)
        if d > w.start + timedelta(days=45):
            out.append(d)
    return out


PROGRAMME_WORDS = ("programme", "productivity", "rework", "planner", "mechanical work")


def minutes(
    w: World,
    rng: random.Random,
    tables: xer.Tables,
    plants: list[Plant],
    paras: dict[str, list[str]],
    physical_now: float,
    slip_story: bool,
    forecast_finish: date,
) -> dict[str, str]:
    dates = meeting_dates(w)
    planted: dict[date, list[str]] = {d: [] for d in dates}
    for p in plants:
        if p.target == "minutes":
            d = next((x for x in dates if x >= p.on), dates[-1])
            planted[d].append(p.text)
    first_no = max(1, round((dates[0] - w.start).days / 30.44))
    out = {}
    for i, d in enumerate(dates):
        no = first_no + i
        frac = min(1.0, physical_now * (d - w.start).days / max(1, (PERIOD_END - w.start).days))
        items = planted[d]
        prog_items = [t for t in items if any(k in t.lower() for k in PROGRAMME_WORDS)]
        comm_items = [t for t in items if t not in prog_items]
        if slip_story and d >= date(2026, 11, 1):
            prog = (
                "Programme update under review following the steelwork resequencing; revised forecast to "
                "be confirmed."
            )
        else:
            finish = forecast_finish if not slip_story else w.baseline_finish
            prog = (
                f"Programme update issued. Forecast completion {long_date(finish)} against contract "
                f"completion {long_date(w.completion)}."
            )
        acts = rng.sample(active_on(tables, d) or ["General works"], k=min(4, len(active_on(tables, d)) or 1))
        actions = []
        for _ in range(rng.randint(4, 7)):
            who = rng.choice([w.pm, w.site_mgr, w.planner, w.cust_pm, w.er, w.qs])
            actions.append(
                f"| {no}.{len(actions) + 1} | {rng.choice(['Issue revised', 'Confirm', 'Close out', 'Submit', 'Review', 'Arrange'])} "
                f"{rng.choice(['lift plan', 'RFI responses', 'test pack schedule', 'access arrangements', 'drawing register', 'NCR close-out', 'commissioning procedures', 'HSE statistics'])} "
                f"| {who.initials} | {long_date(d + timedelta(days=rng.randint(7, 28)))} |"
            )
        nxt = dates[i + 1] if i + 1 < len(dates) else d + timedelta(days=35)
        sec = [
            "\n".join(
                [
                    f"# {w.project}: progress meeting no. {no}",
                    "",
                    f"**Date:** {long_date(d)}, 10:00, site offices  ",
                    f"**Present:** {w.er.name} (ER), {w.cust_pm.name}, {w.cow.name}, {w.cust_qs.name} "
                    f"({w.customer}); {w.pm.name}, {w.cm.name}, {w.site_mgr.name}, {w.planner.name} "
                    f"({CONTRACTOR})  ",
                    f"**Apologies:** {rng.choice([w.qs.name, 'none', w.site_mgr.name])}",
                ]
            ),
            "## 1. Previous minutes",
            "Agreed as a true record. Actions reviewed; see action log.",
            "## 2. Health, safety and environment",
            f"{rng.randint(18, 60) * 1000:,} hours worked in the period; no RIDDOR reportable incidents; "
            f"{rng.randint(0, 6)} near misses reported.",
            fill(w, rng.choice(paras["hse"]), rng),
            fill(w, rng.choice(paras["hse"]), rng),
            "## 3. Progress",
            f"Overall physical progress {frac * 100:.1f}%. Activities progressed this period: "
            + "; ".join(acts)
            + ".",
            *prog_items,
            "## 4. Programme",
            prog,
            "## 5. Design and technical",
            f"{rng.randint(3, 14)} RFIs open, {rng.randint(2, 10)} closed in the period.",
            fill(w, rng.choice(paras["design"]), rng),
            "## 6. Commercial and contractual",
            f"Application for payment no. {no} submitted on {long_date(d - timedelta(days=rng.randint(3, 8)))}.",
            *comm_items,
            "## 7. Quality",
            fill(w, rng.choice(paras["quality"]), rng),
            "## 8. Logistics and interfaces",
            fill(w, rng.choice(paras["logistics"]), rng),
            "## 9. Any other business",
            fill(w, rng.choice(paras["aob"]), rng),
            "## Actions",
            "| No. | Action | Owner | Due |\n|---|---|---|---|\n" + "\n".join(actions),
            f"Next meeting: {long_date(nxt)}.",
        ]
        out[f"{d.isoformat()}_minutes_PM{no:02d}.md"] = "\n\n".join(s for s in sec if s is not None) + "\n"
    return out


# ---------------------------------------------------------------------------
# internal contract reviews (cost-value reconciliations)
# ---------------------------------------------------------------------------


def cost_reviews(
    w: World,
    rng: random.Random,
    plants: list[Plant],
    paras: dict[str, list[str]],
    numbers: dict[str, float],
    register: list[str],
    eac_q3: float,
    ac_q3: float,
) -> dict[str, str]:
    out = {}
    for q, held, title in (
        ("cvr_q3", date(2026, 10, rng.randint(13, 16)), "Q3 2026 contract review"),
        ("cvr_q4", date(2027, 1, rng.randint(18, 22)), "Year-end 2026 contract review"),
    ):
        items = [p.text for p in plants if p.target == q]
        if q == "cvr_q3":
            costs = [
                f"Cost to date at 30 September {money(ac_q3)}. Forecast final cost {money(eac_q3)}; "
                f"forecast margin {(1 - eac_q3 / numbers['tp']) * 100:.1f}%."
            ]
        else:
            costs = [
                f"Cost to date at 31 December {money(numbers['ac'])}; ETC {money(numbers['etc'])}; "
                f"forecast final cost {money(numbers['eac'])}; transaction value {money(numbers['tp'])}; "
                f"forecast margin {(1 - numbers['eac'] / numbers['tp']) * 100:.1f}%."
            ]
        body = [
            "\n".join(
                [
                    f"# {w.project}: {title}",
                    "",
                    f"**Held:** {long_date(held)}  ",
                    f"**Present:** {w.fd.name} (chair), {w.gcd.name}, {w.pm.name}, {w.cm.name}, {w.qs.name}  ",
                    "**Internal: not for circulation outside Brackmoor**",
                ]
            ),
            "## 1. Valuation and cash",
            fill(w, rng.choice(paras["cvr_general"]), rng),
            "## 2. Cost and forecast",
            *costs,
            *[t for t in items if "provision" not in t.lower()],
            "## 3. Variations and claims",
            "Variation register reviewed (see cost report):\n\n" + "\n".join(f"- {r}" for r in register),
            "## 4. Risks and opportunities",
            fill(w, rng.choice(paras["cvr_general"]), rng),
            "## 5. Provision",
            *([t for t in items if "provision" in t.lower()] or ["No provision required."]),
            "## 6. Actions",
            f"- {w.qs.name} to update the risk register before the next review.",
            f"- {w.cm.name} to report on open quotations.",
        ]
        out[f"{held.isoformat()}_minutes_contract-review.md"] = "\n\n".join(body) + "\n"
    return out


# ---------------------------------------------------------------------------
# registers and logs
# ---------------------------------------------------------------------------

ROUTINE_SUBJECTS = [
    "Application for payment no. {n}",
    "Monthly progress report no. {n}",
    "HSE statistics: {m}",
    "Programme update {n}",
    "Design submission package {n}",
    "Site access arrangements",
    "Insurance certificates",
    "Interim payment certificate no. {n}",
    "Quality audit report",
    "Christmas shutdown arrangements",
    "Commissioning plan revision {n}",
    "Key personnel",
]


def correspondence_register(
    w: World, rng: random.Random, letters: list[tuple[date, str, str, str, str]]
) -> str:
    rows = list(letters)
    d = max(w.start, date(2026, 6, 1))
    while d < REVIEW_DATE:
        d += timedelta(days=rng.randint(2, 6))
        incoming = rng.random() < 0.5
        ref = w.ref("in" if incoming else "out")
        subj = rng.choice(ROUTINE_SUBJECTS).format(n=rng.randint(3, 30), m=f"{d:%B %Y}")
        rows.append(
            (d, ref, w.er.name if incoming else w.pm.name, w.pm.name if incoming else w.er.name, subj)
        )
    rows.sort(key=lambda r: (r[0], r[1]))
    lines = [
        f"# Correspondence register: {w.project}",
        "",
        "Formal letters between the Employer and Brackmoor. Emails are not registered.",
        "",
        "| Date | Ref | From | To | Subject |",
        "|---|---|---|---|---|",
    ]
    lines += [f"| {r[0].isoformat()} | {r[1]} | {r[2]} | {r[3]} | {r[4]} |" for r in rows]
    return "\n".join(lines) + "\n"


RFI_SUBJECTS = [
    "Clarify nozzle orientation on {a} vessels",
    "Confirm cable tray loading for {a}",
    "Missing dimensions on foundation drawing for {a}",
    "Tie-in point coordinates at {a}",
    "Paint colour for {a} handrails",
    "Confirm earthing details at {a}",
    "Clash between drainage and cable route at {a}",
    "Valve tag numbering in {a}",
    "Grating opening sizes in {a}",
    "Instrument air supply location at {a}",
    "Confirm hydrotest pressure for {a} lines",
    "Door hardware schedule for {a}",
]


def rfi_log(w: World, rng: random.Random, plants: list[Plant]) -> str:
    rows = []
    for _ in range(rng.randint(50, 110)):
        raised = w.start + timedelta(days=rng.randint(20, max(21, (PERIOD_END - w.start).days)))
        subj = rng.choice(RFI_SUBJECTS).format(a=rng.choice(AREAS))
        closed = raised + timedelta(days=rng.randint(3, 30))
        resp = rng.choice(
            [
                "Confirmed as drawn",
                "Revised drawing issued",
                "See marked-up sketch",
                "Agreed as proposed",
                "Refer to specification section 4",
                "Response by ER's designer",
            ]
        )
        rows.append((raised, subj, resp, "Closed" if closed < PERIOD_END else "Open"))
    for p in plants:
        if p.target == "rfi":
            subj, resp = p.text.split("|")
            rows.append((p.on, subj, resp, "Closed"))
    rows.sort(key=lambda r: r[0])
    lines = [
        f"# RFI log: {w.project}",
        "",
        "| RFI | Raised | Subject | Response | Status |",
        "|---|---|---|---|---|",
    ]
    lines += [
        f"| RFI-{i + 1:03d} | {r[0].isoformat()} | {r[1]} | {r[2]} | {r[3]} |" for i, r in enumerate(rows)
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# routine documents from the pool
# ---------------------------------------------------------------------------


def routine_docs(w: World, rng: random.Random, n: int) -> tuple[dict[str, str], list[tuple]]:
    pool, _ = _pool()
    roles = {
        "ER": w.er,
        "CUST_PM": w.cust_pm,
        "COW": w.cow,
        "PM": w.pm,
        "SITE_MGR": w.site_mgr,
        "PLANNER": w.planner,
        "QS": w.qs,
        "SUB_CONTACT": w.subs[0][2],
    }
    first = max(w.start + timedelta(days=30), date(2026, 6, 15))
    out: dict[str, str] = {}
    register: list[tuple] = []
    from .writer import render

    for item in rng.sample(pool, k=min(n, len(pool))):
        on = first + timedelta(days=rng.randint(0, (REVIEW_DATE - first).days - 3))
        sender = roles.get(item.get("sender"), w.pm)
        to = roles.get(item.get("recipient"), w.er)
        if to is sender:
            to = w.er if sender is not w.er else w.pm
        kind = item.get("kind") if item.get("kind") in ("letter", "email", "memo") else "email"
        ref = None
        if kind == "letter":
            ref = w.ref("in" if sender.org == w.customer else "out")
        spec = Spec(
            name="",
            on=on,
            kind=kind,
            sender=sender,
            to=[to],
            subject=fill(w, item["subject"], rng),
            purpose="",
            facts=[],
            must_include=[],
            ref=ref,
        )
        text = render(w, spec, fill(w, item["body"], rng))
        if kind == "letter":
            name = f"{on.isoformat()}_letter_{ref.replace('/', '-')}.md"
            if sender.org in (w.customer, CONTRACTOR) and to.org in (w.customer, CONTRACTOR):
                register.append((on, ref, sender.name, to.name, spec.subject))
        else:
            name = f"{on.isoformat()}_{kind}_{w.ref('email')}.md"
        out[name] = text
    return out, register
