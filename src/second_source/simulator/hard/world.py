"""The world one hard contract lives in: parties, people, references, dates and the contract itself.

Everything here is fictional. One contractor (Brackmoor) runs many contracts for
different employers; each contract has its own people and reference formats.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

PERIOD_END = date(2026, 12, 31)
REVIEW_DATE = date(2027, 1, 29)  # the file as handed over: documents run to here
CONTRACTOR = "Brackmoor Engineering Ltd"
CONTRACTOR_CODE = "BRK"
GROUP_FD = "Martin Ellery"
GROUP_COMMERCIAL_DIRECTOR = "Sian Pryce"

FIRST = [
    "James",
    "Priya",
    "Tom",
    "Aisha",
    "Callum",
    "Hannah",
    "Owen",
    "Grace",
    "Rhys",
    "Fatima",
    "Daniel",
    "Chloe",
    "Marcus",
    "Isla",
    "Kieran",
    "Sophie",
    "Ade",
    "Ruth",
    "Liam",
    "Megan",
    "Gareth",
    "Nadia",
    "Euan",
    "Laura",
    "Simon",
    "Bethan",
    "Ravi",
    "Claire",
    "Neil",
    "Joanna",
    "Ian",
    "Zoe",
    "Graham",
    "Amira",
    "Stuart",
    "Holly",
    "Dev",
    "Fiona",
    "Craig",
    "Lucy",
]
LAST = [
    "Hartley",
    "Okafor",
    "Brennan",
    "Patel",
    "McLeod",
    "Thornton",
    "Walsh",
    "Iqbal",
    "Davies",
    "Fraser",
    "Kowalski",
    "Bryant",
    "Lindqvist",
    "Morgan",
    "Achebe",
    "Sinclair",
    "Doyle",
    "Ferris",
    "Haddad",
    "Rowe",
    "Pemberton",
    "Yates",
    "Gallagher",
    "Nair",
    "Whitlock",
    "Carver",
    "Ashworth",
    "Mensah",
    "Quigley",
    "Rees",
    "Talbot",
    "Varga",
    "Ellison",
    "Moffat",
    "Sutherland",
    "Kerr",
    "Lowther",
    "Dunmore",
    "Hale",
    "Strachan",
]

PROJECTS = [  # name, code, site
    ("Halden Ridge Gas Compression", "HRG", "Halden Ridge, Northumberland"),
    ("Northmoor Water Treatment Upgrade", "NWT", "Northmoor, North Yorkshire"),
    ("Kessock Substation", "KSS", "North Kessock, Highland"),
    ("Arden Valley Biomass Plant", "AVB", "Arden Valley, Warwickshire"),
    ("Tarrow Estuary Jetty", "TEJ", "Tarrow, Tyne and Wear"),
    ("Fennick Hydrogen Pilot", "FHP", "Fennick, Cheshire"),
    ("Corran Point Desalination", "CPD", "Corran Point, Argyll"),
    ("Ashby Fell Pumping Station", "AFP", "Ashby Fell, Cumbria"),
    ("Merrow Bay Terminal Expansion", "MBT", "Merrow Bay, Pembrokeshire"),
    ("Glenwick Pipeline Spur", "GPS", "Glenwick, Fife"),
    ("Saltby Carbon Capture Unit", "SCC", "Saltby, Teesside"),
    ("Rothwell Grid Reinforcement", "RGR", "Rothwell, West Yorkshire"),
    ("Hartfield Process Control Retrofit", "HPC", "Hartfield, Lancashire"),
    ("Dunmere Tank Farm", "DTF", "Dunmere, Cornwall"),
    ("Linford Chemical Storage", "LCS", "Linford, Essex"),
    ("Brenfield Flare System", "BFS", "Brenfield, Lincolnshire"),
    ("Ovington LNG Loading Arm", "OLA", "Ovington, Kent"),
    ("Pellow Wind Substation", "PWS", "Pellow, Ceredigion"),
    ("Strathcorr Compressor Station", "SCS", "Strathcorr, Aberdeenshire"),
    ("Weybury Effluent Plant", "WEP", "Weybury, Hampshire"),
    ("Calder Moss Battery Storage", "CMB", "Calder Moss, West Lothian"),
    ("Ennerby Steam Network", "ESN", "Ennerby, Humberside"),
    ("Kilbrae Offshore Module Yard", "KOM", "Kilbrae, Ayrshire"),
    ("Harrowgate Gas Metering", "HGM", "Harrowgate, County Durham"),
]
CUSTOMERS = [
    ("Norvale Energy plc", "NVE"),
    ("Ardent Water Ltd", "AWL"),
    ("Caledon Power Networks", "CPN"),
    ("Tamsin Petrochemicals", "TPC"),
    ("Eastmarch Utilities", "EMU"),
    ("Blythe Industrial Holdings", "BIH"),
    ("Sorrel Renewables", "SRL"),
    ("Hexley Chemicals", "HXC"),
]
SUBCONTRACTORS = [
    ("Hallam Steel Erectors", "structural steel"),
    ("Corvan Piping Services", "piping installation"),
    ("Dalgety Electrical", "electrical installation"),
    ("Ridgeway Civils", "civil works"),
    ("Pennant Instrumentation", "instrumentation and controls"),
    ("Ashlar Scaffolding", "scaffolding and access"),
    ("Marlow Insulation", "insulation and cladding"),
    ("Tregarth Groundworks", "groundworks and drainage"),
    ("Kestrel Cranes", "heavy lifting"),
    ("Orrin Commissioning", "pre-commissioning"),
]

AREAS = [
    "Area 100 Inlet",
    "Area 200 Process",
    "Area 300 Utilities",
    "Area 400 Storage",
    "Area 500 Export",
    "Area 600 Control Building",
]


def money(x: float) -> str:
    return f"£{x:,.0f}"


def long_date(d: date) -> str:
    return f"{d:%d %B %Y}"


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    day = min(d.day, [31, 29 if (d.year + y) % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m])
    return date(d.year + y, m + 1, day)


@dataclass
class Person:
    name: str
    role: str
    org: str

    @property
    def initials(self) -> str:
        return "".join(p[0] for p in self.name.split())

    def sig(self) -> str:
        return f"{self.name}, {self.role}, {self.org}"


@dataclass
class World:
    cid: str
    project: str
    code: str
    site: str
    customer: str
    cust_code: str
    start: date
    baseline_finish: date
    completion: date
    price: float
    ld_rate: float
    ld_cap: float
    er: Person
    cust_pm: Person
    cow: Person
    cust_qs: Person
    pm: Person
    cm: Person
    qs: Person
    site_mgr: Person
    planner: Person
    fd: Person
    gcd: Person
    subs: list[tuple[str, str, Person]]
    rng: random.Random
    counters: dict[str, int] = field(default_factory=dict)

    # --- references ------------------------------------------------------------
    def ref(self, kind: str) -> str:
        start = {
            "out": self.rng.randint(180, 420),
            "in": self.rng.randint(60, 160),
            "quote": self.rng.randint(12, 40),
            "eri": self.rng.randint(8, 30),
            "email": self.rng.randint(1000, 4000),
        }
        n = self.counters.get(kind, start[kind]) + self.rng.randint(1, 4)
        self.counters[kind] = n
        return {
            "out": f"{CONTRACTOR_CODE}/{self.code}/L/{n:04d}",
            "in": f"{self.cust_code}/{self.code}/{n:03d}",
            "quote": f"{CONTRACTOR_CODE}/{self.code}/Q/{n:03d}",
            "eri": f"ERI-{n:03d}",
            "email": f"{n}",
        }[kind]

    def people(self) -> list[Person]:
        return [
            self.er,
            self.cust_pm,
            self.cow,
            self.cust_qs,
            self.pm,
            self.cm,
            self.qs,
            self.site_mgr,
            self.planner,
            self.fd,
            self.gcd,
        ] + [s[2] for s in self.subs]

    def bible(self) -> str:
        """Background every document writer gets, so names and roles stay consistent."""
        lines = [
            f"Project: {self.project} ({self.code}), at {self.site}.",
            f"Employer (customer): {self.customer}. Contractor: {CONTRACTOR}.",
            f"Contract: lump-sum fixed-price EPC contract dated {long_date(self.start)}; "
            f"contract completion date {long_date(self.completion)}.",
            "Key clauses: 2.3 Contractor's design responsibility (development of the Contractor's design is "
            "not a Variation); 3.2 only the Employer's Representative may instruct Variations, and other "
            "Employer staff (including the Clerk of Works) have no authority to do so; 3.3 an oral "
            "instruction of the Employer's Representative takes effect if the Contractor confirms it in "
            "writing within 2 days and the Employer's Representative does not dissent within 7 days; 14 "
            "Variations (quotations, acceptance, valuation; 14.5 withdrawal of an instruction for work "
            "not yet started); 15 notification within 8 weeks of becoming aware of an event, failing "
            "which no entitlement; 4.2 all sums exclusive of VAT; 16 interim payment certificates are not "
            "evidence of agreement of value.",
            "People:",
        ]
        lines += [f"- {p.name}: {p.role}, {p.org}" for p in self.people()]
        lines += ["Subcontractors: " + "; ".join(f"{c} ({pkg})" for c, pkg, _ in self.subs) + "."]
        lines.append(
            f"Reference formats: {CONTRACTOR} letters {CONTRACTOR_CODE}/{self.code}/L/nnnn; "
            f"quotations {CONTRACTOR_CODE}/{self.code}/Q/nnn; {self.customer} letters "
            f"{self.cust_code}/{self.code}/nnn; Employer's Representative's Instructions ERI-nnn. "
            "Brackmoor's own variation register uses VO-nnn, which the Employer does not use."
        )
        return "\n".join(lines)


def make_world(
    cid: str, idx: int, rng: random.Random, price: float, start: date, baseline_finish: date, completion: date
) -> World:
    project, code, site = PROJECTS[(idx - 1) % len(PROJECTS)]
    customer, cust_code = rng.choice(CUSTOMERS)
    names = [f"{f} {la}" for f, la in zip(rng.sample(FIRST, 20), rng.sample(LAST, 20), strict=True)]
    it = iter(names)

    def p(role: str, org: str) -> Person:
        return Person(next(it), role, org)

    subs = [(c, pkg, Person(next(it), "Contracts Manager", c)) for c, pkg in rng.sample(SUBCONTRACTORS, 3)]
    return World(
        cid=cid,
        project=project,
        code=code,
        site=site,
        customer=customer,
        cust_code=cust_code,
        start=start,
        baseline_finish=baseline_finish,
        completion=completion,
        price=price,
        ld_rate=round(price * rng.uniform(0.0003, 0.0008), -2),
        ld_cap=round(price * rng.choice([0.05, 0.1]), -3),
        er=p("Employer's Representative", customer),
        cust_pm=p("Project Manager", customer),
        cow=p("Clerk of Works", customer),
        cust_qs=p("Quantity Surveyor", customer),
        pm=p("Project Manager", CONTRACTOR),
        cm=p("Commercial Manager", CONTRACTOR),
        qs=p("Senior Quantity Surveyor", CONTRACTOR),
        site_mgr=p("Site Manager", CONTRACTOR),
        planner=p("Planning Manager", CONTRACTOR),
        fd=Person(GROUP_FD, "Group Finance Director", CONTRACTOR),
        gcd=Person(GROUP_COMMERCIAL_DIRECTOR, "Group Commercial Director", CONTRACTOR),
        subs=subs,
        rng=rng,
    )


def working_days(first: date, last: date) -> list[date]:
    out, d = [], first
    while d <= last:
        shutdown = (d.month == 12 and d.day >= 24) or (d.month == 1 and d.day <= 3)
        if d.weekday() < 5 and not shutdown:
            out.append(d)
        d += timedelta(days=1)
    return out


def contract_md(w: World) -> str:
    """The contract: long, mostly boilerplate, with the clauses the stories turn on."""
    scope = "\n".join(
        f"{i}. {a}: civil, structural, mechanical, piping, electrical and instrumentation "
        "works, testing and pre-commissioning, as shown on the Employer's Requirements drawings."
        for i, a in enumerate(AREAS[: w.rng.randint(4, 6)], start=1)
    )
    defs = [
        (
            "Contract",
            "this agreement, the Conditions, the Employer's Requirements, the Contractor's Proposals "
            "and the Schedules, read together as one document",
        ),
        ("Contract Price", "the sum stated in clause 4.1, as adjusted in accordance with the Contract"),
        (
            "Employer's Representative",
            f"{w.er.name}, or such other person as the Employer notifies to the Contractor in writing",
        ),
        ("Clerk of Works", "the person appointed by the Employer to inspect the Works on its behalf"),
        ("Variation", "a change to the Works instructed or agreed under clause 14"),
        ("Works", "the works described in Schedule 1, including all temporary works"),
        ("Site", f"the land at {w.site} shown edged red on drawing {w.code}-GA-0001"),
        (
            "Completion",
            "the stage at which the Works are complete, save for minor defects, and have passed "
            "the Tests on Completion",
        ),
        ("Programme", "the Contractor's programme accepted under clause 8.2, as revised"),
        ("Working Day", "any day other than a Saturday, Sunday or public holiday in England and Wales"),
    ]
    definitions = "\n".join(f"**{k}** means {v}." for k, v in defs)
    return f"""# Engineering, Procurement and Construction Contract

**Project:** {w.project}
**Contract reference:** {w.code}-EPC-001
**Employer:** {w.customer}
**Contractor:** {CONTRACTOR}
**Form:** Lump-sum fixed-price EPC agreement with bespoke Conditions
**Date of agreement:** {long_date(w.start)}

## Articles of agreement

This agreement is made between {w.customer} (the "Employer") and {CONTRACTOR} (the "Contractor"). The
Contractor shall design, procure, construct, test and pre-commission the Works in accordance with the
Contract, and the Employer shall pay the Contractor the Contract Price at the times and in the manner
set out in the Contract.

## 1. Definitions and interpretation

{definitions}

1.2 Headings are for convenience only. Words in the singular include the plural. A reference to a
clause is to a clause of these Conditions.

1.3 Communications under the Contract shall be in writing and delivered by hand, post or email to the
addresses in Schedule 4. A communication takes effect when received.

## 2. Contractor's general obligations

2.1 The Contractor shall carry out and complete the Works with the skill, care and diligence of a
competent contractor experienced in works of a similar size, scope and complexity.

2.2 The Contractor shall comply with all applicable laws, consents and the Employer's site rules.

2.3 The Contractor is responsible for the design of the Works, including the development and
completion of the design from the Employer's Requirements. No development, completion or correction
of the Contractor's design, and no work needed to meet the Employer's Requirements, shall constitute
a Variation or entitle the Contractor to any adjustment of the Contract Price.

2.4 The Contractor shall be deemed to have inspected the Site and satisfied itself as to the ground
conditions so far as reasonably ascertainable from the site investigation report in Schedule 5.

## 3. Employer's Representative

3.1 The Employer appoints the Employer's Representative to act on its behalf under the Contract.

3.2 Only the Employer's Representative may issue instructions, instruct or agree Variations, or agree
any adjustment to the Contract Price. No other employee or agent of the Employer, including the Clerk
of Works and any site engineer, has authority to instruct or agree any change to the Works.

3.3 If the Employer's Representative gives an instruction other than in writing, the Contractor shall
confirm it in writing to the Employer's Representative within 2 Working Days. If the Employer's
Representative does not dissent in writing within 7 days of receiving the confirmation, the
instruction shall take effect from the expiry of that period.

## 4. Contract Price and payment

4.1 The Contract Price is {money(w.price)}, fixed and not subject to adjustment except as expressly
provided in the Contract.

4.2 All sums stated in or under the Contract are exclusive of VAT, which shall be added at the
applicable rate.

## 8. Programme and time for completion

8.1 The Contractor shall commence the Works on the date of this agreement and proceed regularly and
diligently.

8.2 The Contractor shall submit a programme within 28 days. The Contractor shall submit a revised
programme each month showing actual progress and forecast completion.

8.3 The Contractor shall achieve Completion by {long_date(w.completion)}.

8.4 If the Contractor fails to achieve Completion by that date, it shall pay the Employer delay damages
of {money(w.ld_rate)} per day, up to a maximum of {money(w.ld_cap)}.

## 14. Variations

14.1 No change to the Works shall constitute a Variation unless instructed or agreed in writing by the
Employer's Representative.

14.2 Before carrying out a Variation, or within 14 days of an instruction, the Contractor shall
submit a quotation stating the proposed adjustment to the Contract Price and any effect on the
Programme.

14.3 The Employer's Representative shall, within 28 days of receiving a quotation, accept it, accept it
in part, or reject it. A quotation accepted in part is accepted only to the extent stated.

14.4 Failing agreement, the value of a Variation shall be determined under clause 20.

14.5 The Employer's Representative may withdraw an instruction for a Variation, by notice, at any time
before work under it has started. Where work has not started, no sum is payable in respect of the
withdrawn instruction or any quotation for it.

## 15. Notification of events

15.1 The Contractor shall notify the Employer's Representative of any event that it considers entitles
it to an adjustment of the Contract Price or the time for completion within 8 weeks of becoming aware
of the event.

15.2 If the Contractor does not notify an event within the period in clause 15.1, it is not entitled to
any adjustment of the Contract Price or the time for completion in respect of that event.

## 16. Payment

16.1 The Contractor shall submit an application for payment at the end of each month. The Employer's
Representative shall issue an interim payment certificate within 14 days.

16.2 An interim payment certificate is not evidence that any work, or the value of any Variation, has
been accepted or agreed.

## 17. Insurance

17.1 The Contractor shall maintain contractor's all risks insurance for the full reinstatement value
of the Works, and employer's and public liability insurance of not less than £10,000,000 per event.

## 18. Health, safety and environment

18.1 The Contractor is the principal contractor for the purposes of the Construction (Design and
Management) Regulations 2015 and shall comply with the Employer's site HSE rules.

## 19. Quality

19.1 The Contractor shall operate a quality management system certified to ISO 9001 and shall give
the Employer's Representative 5 Working Days' notice of each witness and hold point.

## 20. Disputes

20.1 Either party may refer a dispute to adjudication at any time. The adjudicator's decision is
binding until finally determined by agreement or by the courts of England and Wales.

## Schedule 1: Scope of the Works

{scope}

## Schedule 4: Addresses for notices

Employer: {w.er.name}, Employer's Representative, {w.customer}.
Contractor: {w.pm.name}, Project Manager, {CONTRACTOR}.
"""
