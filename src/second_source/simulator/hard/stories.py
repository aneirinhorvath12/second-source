"""The scenario catalogue for the hard portfolio.

Each story fixes, for one judgement:
- what management's records say (register entry, ETC build-up, provision),
- what the evidence says, as documents for the writer (`Spec`) and short planted
  entries in bulk documents like diaries and minutes (`Plant`),
- the answer a careful reviewer should reach (`Judgement`).

Hard cases come in three kinds: issues hidden by indirection (customer
references, oblique wording, a clause plus two dates), traps that look like
issues but aren't (grudging acceptances, VAT-inclusive sums, misfiled letters,
front-loaded materials), and items that need escalation rather than a verdict.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from ...answers import Correction, EffectRange, Judgement
from ...models import EtcLine, Variation
from .world import PERIOD_END, Person, World, add_months, long_date, money

# ---------------------------------------------------------------------------
# shapes
# ---------------------------------------------------------------------------


@dataclass
class Spec:
    """A document the writer drafts from a fact sheet."""

    name: str
    on: date
    kind: str  # letter | email | memo
    sender: Person
    to: list[Person]
    subject: str
    purpose: str
    facts: list[str]
    must_include: list[str]
    must_not_include: list[str] = field(default_factory=list)
    money_ok: list[float] = field(default_factory=list)
    ref: str | None = None
    cc: list[Person] = field(default_factory=list)
    words: int = 320
    in_register: bool = True


@dataclass
class Plant:
    """A short entry planted in a bulk document."""

    target: str  # diary | minutes | cvr_q3 | cvr_q4 | rfi
    on: date
    text: str


@dataclass
class Out:
    judgement: Judgement | None = None
    variations: list[Variation] = field(default_factory=list)
    specs: list[Spec] = field(default_factory=list)
    plants: list[Plant] = field(default_factory=list)
    register_only: list[tuple[date, str, str, str, str]] = field(default_factory=list)
    """Letters that exist (listed in the correspondence register) but aren't in the file."""
    breakdown: list[EtcLine] = field(default_factory=list)
    commentary: list[str] = field(default_factory=list)


VARIATION_POOL = [
    ("Additional pipe supports required by the Employer's revised stress analysis", "extra pipe supports"),
    ("Relocation of the control room following the Employer's layout change", "control room relocation"),
    ("Upgraded fire and gas detection to the Employer's revised standard", "fire and gas upgrade"),
    ("Extra civil works for ground conditions at the north pad", "north pad civils"),
    ("Acceleration of mechanical completion at the Employer's request", "acceleration"),
    ("Additional instrumentation loops added at design freeze 2", "extra instrument loops"),
    ("Temporary power supply extended beyond the agreed period", "temporary power extension"),
    ("Additional access road and turning head for the Employer's operations team", "access road extension"),
    ("Replacement of carbon steel spools with duplex in the export line", "duplex export spools"),
    ("Second cable route to the substation for redundancy", "second cable route"),
    ("Enlarged foundations for the Employer's future compressor", "future compressor foundations"),
    ("Additional CCTV and access control at the perimeter", "perimeter CCTV"),
    ("Diversion of the existing foul drain under the tank bund", "foul drain diversion"),
    ("Upgrade of the HVAC in the control building to N+1", "HVAC upgrade"),
    ("Extra noise attenuation enclosures for the compressors", "noise enclosures"),
    ("Additional sampling points and analyser house", "analyser house"),
    ("Change of paint system to the Employer's revised specification", "paint system change"),
    ("Extended scaffold hire for the Employer's inspection campaign", "scaffold extension"),
    ("Additional earthing and lightning protection to the new standard", "earthing upgrade"),
    ("Relocation of the site welfare cabins at the Employer's request", "welfare relocation"),
    ("Extra piling at grid line C following the revised loading", "grid C piling"),
    ("Additional leak detection on the storage tanks", "tank leak detection"),
    ("Out-of-hours working to suit the Employer's shutdown window", "shutdown working"),
    ("Extra drainage to the laydown area after the Employer's change of use", "laydown drainage"),
    ("Removal of asbestos-containing lagging found in the existing pipe rack", "asbestos removal"),
    ("Upgrade of the PLC to the Employer's newly selected platform", "PLC upgrade"),
    ("Additional bridge crane in the maintenance workshop", "workshop crane"),
    ("Widened pipe rack to accommodate the Employer's future lines", "pipe rack widening"),
]

OBSTRUCTIONS = [
    "an abandoned brick culvert",
    "a live 11kV cable not shown on the utility records",
    "a buried concrete slab from the former works",
    "pockets of contaminated made ground",
    "an uncharted water main",
    "old timber piles from a demolished jetty",
]

BANNED_EVERYWHERE = [
    "IFRS",
    "IAS ",
    "auditor",
    "misstat",
    "answer key",
    "seeded",
    "synthetic",
    "ground truth",
    "revenue recognition",
    "transaction price",
]


def _name(on: date, kind: str, ref: str) -> str:
    return f"{on.isoformat()}_{kind}_{ref.replace('/', '-')}.md"


@dataclass
class Var:
    """Context for one variation story."""

    vo: str
    desc: str
    short: str
    amount: float
    quote: str
    eri: str
    d0: date

    @property
    def m(self) -> str:
        return money(self.amount)


def _register(v: Var, status: str, amount: float | None = None, included: bool = True) -> Variation:
    return Variation(
        id=v.vo,
        description=v.desc,
        amount=amount if amount is not None else v.amount,
        included_in_tp=included,
        reported_status=status,
    )


def _submission(
    w: World,
    v: Var,
    on: date,
    *,
    mention_vo: bool = True,
    mention_eri: bool = True,
    extra_facts: list[str] | None = None,
) -> Spec:
    ref = w.ref("out")
    facts = [
        f"Brackmoor submits quotation {v.quote} for: {v.desc}.",
        f"The quotation is {v.m}, exclusive of VAT, with a breakdown summarised in a short table "
        "(labour, plant, materials, subcontract, overheads) whose total is the quotation sum.",
        "Asks the Employer's Representative to accept the quotation under clause 14.3.",
    ]
    must = [v.quote, v.m]
    if mention_eri:
        facts.insert(0, f"The work was instructed by the Employer's Representative's Instruction {v.eri}.")
        must.append(v.eri)
    if mention_vo:
        facts.append(f'Gives Brackmoor\'s internal variation number as {v.vo} ("our ref {v.vo}").')
        must.append(v.vo)
    return Spec(
        name=_name(on, "letter", ref),
        on=on,
        kind="letter",
        sender=w.pm,
        to=[w.er],
        cc=[w.cm],
        subject=f"Quotation {v.quote}",
        ref=ref,
        purpose="Contractor's quotation for a Variation.",
        facts=facts + (extra_facts or []),
        must_include=must,
        money_ok=[v.amount],
        words=380,
    )


def _eri(w: World, v: Var, on: date) -> Spec:
    ref = w.ref("in")
    return Spec(
        name=_name(on, "letter", ref),
        on=on,
        kind="letter",
        sender=w.er,
        to=[w.pm],
        ref=ref,
        subject=f"Employer's Representative's Instruction {v.eri}",
        purpose="A formal instruction from the Employer's Representative.",
        facts=[
            f"Issues instruction {v.eri} under clause 14 for: {v.desc}.",
            "Asks for a quotation under clause 14.2 within 14 days.",
            "Includes two or three lines of technical detail about the change.",
        ],
        must_include=[v.eri],
        must_not_include=[v.vo, "£"],
        words=220,
    )


def _accept(w: World, v: Var, on: date, **kw) -> Spec:
    ref = w.ref("in")
    facts = kw.pop("facts", None) or [
        f"Accepts quotation {v.quote} ({v.short}) in the sum of {v.m} under clause 14.3.",
        "Asks Brackmoor to include it in the next application for payment.",
    ]
    return Spec(
        name=_name(on, "letter", ref),
        on=on,
        kind="letter",
        sender=w.er,
        to=[w.pm],
        ref=ref,
        subject=kw.pop("subject", f"Your quotation {v.quote}"),
        purpose=kw.pop("purpose", "The Employer's Representative's response to a quotation."),
        facts=facts,
        must_include=kw.pop("must_include", [v.quote, v.m]),
        must_not_include=kw.pop("must_not_include", [v.vo]),
        money_ok=kw.pop("money_ok", [v.amount]),
        words=kw.pop("words", 260),
        **kw,
    )


def _internal_email(
    w: World,
    on: date,
    sender: Person,
    to: list[Person],
    subject: str,
    facts: list[str],
    must: list[str],
    money_ok: list[float] | None = None,
    **kw,
) -> Spec:
    n = w.ref("email")
    return Spec(
        name=f"{on.isoformat()}_email_{n}.md",
        on=on,
        kind="email",
        sender=sender,
        to=to,
        subject=subject,
        purpose="An internal Brackmoor email: brief and informal, written by someone busy. "
        "It doesn't explain the contract or argue the position.",
        facts=facts,
        must_include=must,
        money_ok=money_ok or [],
        in_register=False,
        words=kw.pop("words", 120),
        **kw,
    )


def _remove(v: Var) -> Correction:
    return Correction(variations={v.vo: 0.0})


# ---------------------------------------------------------------------------
# T1: variations in TP
# ---------------------------------------------------------------------------


def t1_ok_plain(w: World, rng: random.Random, v: Var) -> Out:
    sub = _submission(w, v, v.d0, mention_eri=False)
    acc = _accept(w, v, v.d0 + timedelta(days=rng.randint(12, 30)))
    return Out(
        judgement=Judgement(
            check="T1", ref=v.vo, verdict="supported", why=f"Accepted at {v.m} in {acc.name}."
        ),
        variations=[_register(v, "Approved")],
        specs=[sub, acc],
        plants=[Plant("minutes", acc.on, f"{v.quote} ({v.short}): accepted by the ER, letter {acc.ref}.")],
    )


def t1_ok_customer_ref(w: World, rng: random.Random, v: Var) -> Out:
    eri = _eri(w, v, v.d0)
    sub = _submission(w, v, v.d0 + timedelta(days=rng.randint(5, 12)))
    acc = _accept(
        w,
        v,
        sub.on + timedelta(days=rng.randint(15, 35)),
        subject=f"Instruction {v.eri}",
        facts=[
            f"Confirms that the Employer accepts Brackmoor's price for the works under {v.eri}, "
            f"in the sum of {v.m}.",
            f"Describes the works (which are: {v.desc}) in different words, without repeating that "
            "wording or changing what the works are.",
            "Does not mention Brackmoor's quotation reference at all.",
        ],
        must_include=[v.eri, v.m],
        must_not_include=[v.vo, v.quote],
    )
    return Out(
        judgement=Judgement(
            check="T1",
            ref=v.vo,
            verdict="supported",
            tag="t1_ok_customer_ref",
            why=f"{acc.name} accepts {v.eri} at {v.m}; {sub.name} links {v.eri} to {v.vo}.",
        ),
        variations=[_register(v, "Approved")],
        specs=[eri, sub, acc],
    )


def t1_ok_grudging(w: World, rng: random.Random, v: Var) -> Out:
    eri = _eri(w, v, v.d0 - timedelta(days=rng.randint(6, 14)))
    sub = _submission(
        w,
        v,
        v.d0,
        extra_facts=["Also asks for an extension of time of 3 weeks in connection with the change."],
    )
    acc = _accept(
        w,
        v,
        v.d0 + timedelta(days=rng.randint(20, 40)),
        facts=[
            "Opens by criticising the late submission of the quotation and Brackmoor's progress generally.",
            "States that the Employer does not accept that the change entitles Brackmoor to any extension "
            "of time, and reserves its rights on delay damages.",
            f"Nonetheless, accepts quotation {v.quote} in the sum of {v.m} under clause 14.3, "
            "in a single sentence in the middle of the letter.",
            "Closes by asking for an improved recovery programme.",
        ],
        must_include=[v.quote, v.m, "does not accept"],
        words=340,
    )
    return Out(
        judgement=Judgement(
            check="T1",
            ref=v.vo,
            verdict="supported",
            tag="t1_ok_grudging",
            why=f"{acc.name} rejects the extension of time but accepts the price {v.m}.",
        ),
        variations=[_register(v, "Approved")],
        specs=[eri, sub, acc],
    )


def t1_ok_vat(w: World, rng: random.Random, v: Var) -> Out:
    gross = round(v.amount * 1.2)
    sub = _submission(w, v, v.d0, mention_eri=False)
    acc = _accept(
        w,
        v,
        v.d0 + timedelta(days=rng.randint(12, 30)),
        facts=[
            f"Accepts quotation {v.quote} ({v.short}).",
            f"States the accepted sum only as {money(gross)} inclusive of VAT; never states the net figure.",
        ],
        must_include=[v.quote, money(gross), "inclusive of VAT"],
        must_not_include=[v.vo, v.m],
        money_ok=[gross],
    )
    return Out(
        judgement=Judgement(
            check="T1",
            ref=v.vo,
            verdict="supported",
            tag="t1_ok_vat",
            why=f"{acc.name} accepts {money(gross)} including VAT, which is {v.m} net "
            "(clause 4.2: contract sums exclude VAT).",
        ),
        variations=[_register(v, "Approved")],
        specs=[sub, acc],
    )


def t1_ok_after_query(w: World, rng: random.Random, v: Var) -> Out:
    sub = _submission(w, v, v.d0, mention_eri=False)
    q1 = _accept(
        w,
        v,
        v.d0 + timedelta(days=rng.randint(14, 25)),
        facts=[
            f"States the Employer is not in a position to accept quotation {v.quote} as submitted.",
            "Asks for a detailed breakdown of labour hours, plant and materials, with supplier quotes.",
            "Says the Employer will respond within 28 days of receiving the breakdown.",
        ],
        must_include=[v.quote],
        must_not_include=[v.vo, "£"],
        money_ok=[],
    )
    parts = [round(v.amount * s) for s in (0.42, 0.21, 0.29)]
    parts.append(round(v.amount) - sum(parts))
    ref = w.ref("out")
    on = q1.on + timedelta(days=rng.randint(7, 15))
    reply = Spec(
        name=_name(on, "letter", ref),
        on=on,
        kind="letter",
        sender=w.qs,
        to=[w.er],
        ref=ref,
        subject=f"Quotation {v.quote}: breakdown",
        purpose="Contractor's supporting breakdown.",
        facts=[
            f"Provides the breakdown requested for quotation {v.quote}, total {v.m}.",
            "Breakdown: labour "
            + money(parts[0])
            + ", plant "
            + money(parts[1])
            + ", materials "
            + money(parts[2])
            + ", overheads and profit "
            + money(parts[3])
            + ".",
        ],
        must_include=[v.quote, v.m] + [money(p) for p in parts],
        money_ok=[v.amount, *parts],
    )
    acc = _accept(
        w,
        v,
        min(on + timedelta(days=rng.randint(14, 26)), PERIOD_END - timedelta(days=6)),
        facts=[
            f"Thanks Brackmoor for the breakdown in letter {ref}.",
            f"Accepts quotation {v.quote} in the sum of {v.m} under clause 14.3.",
        ],
    )
    return Out(
        judgement=Judgement(
            check="T1",
            ref=v.vo,
            verdict="supported",
            tag="t1_ok_after_query",
            why=f"Initially queried ({q1.name}) but accepted at {v.m} in {acc.name}, before the period end.",
        ),
        variations=[_register(v, "Approved")],
        specs=[sub, q1, reply, acc],
    )


def t1_ok_misfiled(w: World, rng: random.Random, v: Var) -> Out:
    from .world import CUSTOMERS, FIRST, LAST, PROJECTS

    sub = _submission(w, v, v.d0, mention_eri=False)
    acc = _accept(w, v, v.d0 + timedelta(days=rng.randint(12, 30)))
    other_project, other_code, _ = rng.choice([p for p in PROJECTS if p[0] != w.project])
    other_cust, other_cc = rng.choice([c for c in CUSTOMERS if c[0] != w.customer])
    other_er = Person(f"{rng.choice(FIRST)} {rng.choice(LAST)}", "Employer's Representative", other_cust)
    on = acc.on + timedelta(days=rng.randint(5, 30))
    other_amount = round(v.amount * rng.uniform(0.6, 1.4))
    letter = Spec(
        name=_name(on, "letter", f"{other_cc}-{other_code}-{rng.randint(40, 200):03d}"),
        on=on,
        kind="letter",
        sender=other_er,
        to=[Person(f"{rng.choice(FIRST)} {rng.choice(LAST)}", "Commercial Manager", "Brackmoor Engineering Ltd")],
        subject=f"{other_project}: your variation {v.vo}",
        in_register=False,
        purpose=f"A letter about a DIFFERENT contract ({other_project}, for {other_cust}) that has been "
        "misfiled in this project's file. The header must clearly name that other project.",
        facts=[
            f"Header and first line make clear this concerns the {other_project} contract.",
            f"Rejects Brackmoor's variation {v.vo} on {other_project} (a different scope: replacement "
            f"of the security fencing) valued at {money(other_amount)}, as the works are within the "
            "original scope of that contract.",
            "States that the variation is not accepted.",
        ],
        must_include=[other_project, v.vo, "not accepted", money(other_amount)],
        must_not_include=[w.project, w.customer, v.quote],
        money_ok=[other_amount],
    )
    return Out(
        judgement=Judgement(
            check="T1",
            ref=v.vo,
            verdict="supported",
            tag="t1_ok_misfiled",
            why=f"Accepted in {acc.name}. The rejection of a '{v.vo}' in {letter.name} is "
            f"about {other_project}, a different contract.",
        ),
        variations=[_register(v, "Approved")],
        specs=[sub, acc, letter],
    )


def t1_rejected_oblique(w: World, rng: random.Random, v: Var) -> Out:
    sub = _submission(w, v, v.d0, mention_eri=False)
    resp = _accept(
        w,
        v,
        v.d0 + timedelta(days=rng.randint(15, 35)),
        facts=[
            f"Responds to quotation {v.quote}.",
            "Explains, with some technical reasoning, that the work arises from developing Brackmoor's own "
            "design to meet the Employer's Requirements.",
            "Concludes that under clause 2.3 the work forms part of the Contractor's obligations and no "
            "adjustment to the Contract Price is due.",
            "Never uses the words 'reject', 'rejected', 'decline' or 'not accepted'.",
        ],
        must_include=[v.quote, "clause 2.3"],
        must_not_include=[v.vo, "reject", "not accept", "declin", "£"],
        money_ok=[],
        words=300,
    )
    return Out(
        judgement=Judgement(
            check="T1",
            ref=v.vo,
            verdict="misstated",
            tag="t1_rejected_oblique",
            correction=_remove(v),
            why=f"{resp.name} says the work is Contractor's design under clause 2.3 and no "
            "adjustment is due: a rejection, though it never says so.",
        ),
        variations=[_register(v, "Approved")],
        specs=[sub, resp],
        plants=[
            Plant(
                "minutes",
                resp.on,
                f"{v.quote}: Brackmoor does not agree with the ER's letter "
                f"{resp.ref} and will respond in due course.",
            ),
            Plant(
                "rfi",
                v.d0 - timedelta(days=rng.randint(10, 30)),
                f"Clarify design basis for {v.short}|Design development within Contractor's "
                "scope; see clause 2.3",
            ),
        ],
    )


def t1_partial(w: World, rng: random.Random, v: Var) -> Out:
    x = round(v.amount * rng.uniform(0.45, 0.8), -2)
    eri = _eri(w, v, v.d0 - timedelta(days=rng.randint(6, 14)))
    sub = _submission(w, v, v.d0)
    resp = _accept(
        w,
        v,
        v.d0 + timedelta(days=rng.randint(15, 35)),
        facts=[
            f"Has assessed quotation {v.quote} against the Contract rates.",
            f"Accepts the quotation in part, in the sum of {money(x)}, under clause 14.3.",
            "Gives two reasons for the reduction (excessive labour hours; overheads double-counted).",
            "States that the balance of the quotation is not accepted.",
        ],
        must_include=[v.quote, money(x)],
        must_not_include=[v.vo],
        money_ok=[x, v.amount, v.amount - x],
    )
    return Out(
        judgement=Judgement(
            check="T1",
            ref=v.vo,
            verdict="misstated",
            tag="t1_partial",
            correction=Correction(variations={v.vo: x}),
            why=f"{resp.name} accepts {money(x)} of {v.m}; the register carries the full sum.",
        ),
        variations=[_register(v, "Agreed")],
        specs=[eri, sub, resp],
    )


def t1_withdrawn(w: World, rng: random.Random, v: Var) -> Out:
    eri = _eri(w, v, v.d0)
    sub = _submission(w, v, v.d0 + timedelta(days=rng.randint(5, 12)))
    acc = _accept(w, v, sub.on + timedelta(days=rng.randint(10, 20)))
    on = min(acc.on + timedelta(days=rng.randint(25, 50)), PERIOD_END - timedelta(days=10))
    ref = w.ref("in")
    wd = Spec(
        name=_name(on, "letter", ref),
        on=on,
        kind="letter",
        sender=w.er,
        to=[w.pm],
        ref=ref,
        subject=f"Instruction {v.eri}",
        purpose="Notice withdrawing an instruction.",
        facts=[
            f"Gives notice under clause 14.5 that instruction {v.eri} is withdrawn, because the "
            "Employer has decided not to proceed with that change.",
            "Notes that work under the instruction has not started.",
            "Asks Brackmoor to confirm it has stood down any orders.",
        ],
        must_include=[v.eri, "14.5"],
        must_not_include=[v.vo, v.quote, "£"],
        words=200,
    )
    return Out(
        judgement=Judgement(
            check="T1",
            ref=v.vo,
            verdict="misstated",
            tag="t1_withdrawn",
            correction=_remove(v),
            why=f"Accepted in {acc.name}, then {v.eri} withdrawn before work started "
            f"({wd.name}); clause 14.5 means nothing is payable.",
        ),
        variations=[_register(v, "Approved")],
        specs=[eri, sub, acc, wd],
        plants=[
            Plant(
                "diary",
                on + timedelta(days=2),
                f"{v.eri} works ({v.short}): stood down per ER notice, no work had started.",
            )
        ],
    )


def t1_wrong_authority(w: World, rng: random.Random, v: Var) -> Out:
    n = w.ref("email")
    em = Spec(
        name=f"{v.d0.isoformat()}_email_{n}.md",
        on=v.d0,
        kind="email",
        sender=w.cow,
        to=[w.site_mgr],
        subject=f"RE: {v.short}",
        purpose="A short, friendly email from the Employer's Clerk of Works.",
        facts=[
            f"Says he is happy for Brackmoor to go ahead with: {v.desc}.",
            "Says 'consider this approved from our side' and asks them to crack on.",
        ],
        must_include=["approved"],
        must_not_include=[v.vo, "£", "Employer's Representative"],
        in_register=False,
        words=90,
    )
    sub = _submission(
        w,
        v,
        v.d0 + timedelta(days=rng.randint(4, 10)),
        mention_eri=False,
        extra_facts=[f"Refers to the approval given by {w.cow.name} (Clerk of Works) on {long_date(v.d0)}."],
    )
    later = sub.on + timedelta(days=rng.randint(20, 40))
    cm_mail = _internal_email(
        w,
        later + timedelta(days=rng.randint(2, 8)),
        w.cm,
        [w.pm],
        f"{v.short}",
        [
            f"Says the Clerk of Works email isn't going to get them there on {v.short}, contractually.",
            "Suggests keeping it in the forecast for now and seeing where the final account goes.",
        ],
        [w.cow.name.split()[0]],
    )
    return Out(
        judgement=Judgement(
            check="T1",
            ref=v.vo,
            verdict="misstated",
            tag="t1_wrong_authority",
            correction=_remove(v),
            why=f"Only approval is from the Clerk of Works ({em.name}), who has no authority "
            "(clause 3.2); the ER disowned it at the progress meeting.",
        ),
        variations=[_register(v, "Approved")],
        specs=[em, sub, cm_mail],
        plants=[
            Plant(
                "minutes",
                later,
                f"{v.short.capitalize()}: {w.er.name} confirmed that no instruction "
                "has been issued by the Employer's Representative and that site staff "
                "have no authority to instruct changes (clause 3.2). The Employer "
                "will not accept the cost. Brackmoor reserved its position.",
            )
        ],
    )


def t1_time_barred(w: World, rng: random.Random, v: Var) -> Out:
    obstruction = rng.choice(OBSTRUCTIONS)
    aware = v.d0
    on = aware + timedelta(weeks=rng.randint(12, 17))
    ref = w.ref("out")
    note = Spec(
        name=_name(on, "letter", ref),
        on=on,
        kind="letter",
        sender=w.pm,
        to=[w.er],
        cc=[w.cm],
        ref=ref,
        subject=f"Notification under clause 15.1 and quotation {v.quote}",
        purpose="Contractor's notification of an event and its quotation.",
        facts=[
            f"Notifies, under clause 15.1, that during excavation Brackmoor encountered {obstruction}.",
            f"States plainly that Brackmoor first became aware of it on {long_date(aware)}.",
            f"Encloses quotation {v.quote} for the additional work, in the sum of {v.m}.",
            f"Gives Brackmoor's internal reference {v.vo}.",
        ],
        must_include=[long_date(aware), v.quote, v.m, v.vo, "15.1"],
        money_ok=[v.amount],
        words=380,
    )
    ack = _accept(
        w,
        v,
        on + timedelta(days=rng.randint(10, 25)),
        subject=f"Your letter {ref}",
        facts=[
            f"Acknowledges receipt of Brackmoor's letter {ref}.",
            "States only that the Employer's position on the matter is reserved under the Contract.",
        ],
        must_include=[ref],
        must_not_include=[v.vo, "£", "time bar", "time-bar", "clause 15", "late", "accept"],
        money_ok=[],
        words=110,
    )
    cm_mail = _internal_email(
        w,
        ack.on + timedelta(days=rng.randint(3, 12)),
        w.cm,
        [w.pm, w.qs],
        f"{obstruction} at the north end",
        [
            "Mentions the ER has only acknowledged the notification.",
            "Says, informally, 'fingers crossed the ER doesn't look too hard at the dates on that one'.",
            "Says to keep the quotation in at full value for the year-end CVR.",
        ],
        ["fingers crossed"],
    )
    return Out(
        judgement=Judgement(
            check="T1",
            ref=v.vo,
            verdict="misstated",
            tag="t1_time_barred",
            correction=_remove(v),
            why=f"{note.name} says Brackmoor knew on {long_date(aware)} but notified "
            f"{(on - aware).days // 7} weeks later; clause 15.2 bars any adjustment.",
        ),
        variations=[_register(v, "Approved (commercial view)")],
        specs=[note, ack, cm_mail],
        plants=[
            Plant(
                "diary",
                aware,
                f"Excavation encountered {obstruction}; work in that area stopped. "
                f"{w.site_mgr.name} informed {w.pm.name}.",
            )
        ],
    )


def t1_post_period(w: World, rng: random.Random, v: Var) -> Out:
    sub = _submission(w, v, v.d0, mention_eri=False)
    inspect = date(2026, 12, rng.randint(7, 11))
    on = date(2027, 1, rng.randint(12, 22))
    ref = w.ref("in")
    resp = Spec(
        name=_name(on, "letter", ref),
        on=on,
        kind="letter",
        sender=w.er,
        to=[w.pm],
        ref=ref,
        subject=f"Your quotation {v.quote}",
        purpose="The ER's response, sent after the year end.",
        facts=[
            f"Refers to the joint inspection on {long_date(inspect)}.",
            f"States that the inspection showed the work in quotation {v.quote} was needed to put "
            "right Brackmoor's own defective workmanship, so it is not a Variation.",
            "States that the quotation is therefore not accepted and no sum is payable.",
        ],
        must_include=[v.quote, long_date(inspect), "not accepted"],
        must_not_include=[v.vo, "£"],
        words=280,
    )
    return Out(
        judgement=Judgement(
            check="T1",
            ref=v.vo,
            verdict="misstated",
            tag="t1_post_period",
            correction=_remove(v),
            why=f"{resp.name}, after the period end, rejects it based on the {long_date(inspect)} "
            "inspection: evidence of conditions at the period end (an adjusting event).",
        ),
        variations=[_register(v, "Agreed")],
        specs=[sub, resp],
        plants=[
            Plant(
                "minutes",
                date(2026, 12, 15),
                f"{v.quote}: {w.er.name} said he expected to be in a "
                "position to agree the quotation following the joint "
                f"inspection on {long_date(inspect)}.",
            )
        ],
    )


def t1_value_disputed(w: World, rng: random.Random, v: Var) -> Out:
    x = round(v.amount * rng.uniform(0.5, 0.8), -2)
    eri = _eri(w, v, v.d0 - timedelta(days=rng.randint(6, 14)))
    sub = _submission(w, v, v.d0)
    resp = _accept(
        w,
        v,
        v.d0 + timedelta(days=rng.randint(15, 30)),
        facts=[
            f"Accepts that the works under {v.eri} are a Variation under clause 14.1.",
            f"Does not accept the sum in quotation {v.quote}, and assesses the Variation at {money(x)}.",
            "Invites a revised quotation.",
        ],
        must_include=[v.quote, money(x)],
        must_not_include=[v.vo],
        money_ok=[x, v.amount],
    )
    ref = w.ref("out")
    on = resp.on + timedelta(days=rng.randint(10, 20))
    reply = Spec(
        name=_name(on, "letter", ref),
        on=on,
        kind="letter",
        sender=w.cm,
        to=[w.er],
        ref=ref,
        subject=f"Quotation {v.quote}",
        purpose="Contractor maintains its valuation.",
        facts=[
            f"Maintains Brackmoor's valuation of {v.m} for quotation {v.quote}, because the ER's "
            "assessment applies contract rates for simpler work and under-measures the quantities "
            "actually installed.",
            "Proposes a meeting to resolve the valuation.",
        ],
        must_include=[v.quote, v.m],
        money_ok=[v.amount, x],
    )
    return Out(
        judgement=Judgement(
            check="T1",
            ref=v.vo,
            verdict="judgement_call",
            tag="t1_value_disputed",
            range=EffectRange(low=Correction(variations={v.vo: x})),
            why=f"Scope agreed ({resp.name}) but value disputed: {money(x)} offered vs {v.m} "
            "claimed; an estimate subject to the constraint.",
        ),
        variations=[_register(v, "Agreed")],
        specs=[eri, sub, resp, reply],
        plants=[
            Plant(
                "minutes",
                date(2026, 12, 15),
                f"{v.quote}: valuation still not agreed; the parties "
                "will meet in February to try to close it out.",
            )
        ],
    )


def t1_oral_instruction(w: World, rng: random.Random, v: Var) -> Out:
    x = round(v.amount * rng.uniform(0.55, 0.85), -3)
    ref = w.ref("out")
    on = v.d0 + timedelta(days=1)
    conf = Spec(
        name=_name(on, "letter", ref),
        on=on,
        kind="letter",
        sender=w.pm,
        to=[w.er],
        ref=ref,
        subject="Confirmation of oral instruction",
        purpose="Contractor confirms an oral instruction.",
        facts=[
            f"Confirms, under clause 3.3, the oral instruction {w.er.name} gave on site on "
            f"{long_date(v.d0)} to proceed with: {v.desc}.",
            "States that a quotation will follow.",
        ],
        must_include=["3.3", long_date(v.d0)],
        must_not_include=["£"],
        words=180,
    )
    sub = _submission(
        w,
        v,
        v.d0 + timedelta(days=rng.randint(14, 25)),
        mention_eri=False,
        extra_facts=[f"Refers to Brackmoor's letter {ref} confirming the oral instruction."],
    )
    qs_mail = Spec(
        name=f"{(sub.on + timedelta(days=rng.randint(12, 25))).isoformat()}_email_{w.ref('email')}.md",
        on=sub.on + timedelta(days=20),
        kind="email",
        sender=w.cust_qs,
        to=[w.qs],
        subject=f"{v.quote}",
        purpose="Informal email from the Employer's QS.",
        in_register=False,
        facts=[
            f"Says the Employer hasn't formally responded on {v.quote} yet.",
            f"Gives an informal early view that it will probably land nearer {money(x)} once they "
            "have been through the rates, but says not to hold him to that.",
        ],
        must_include=[v.quote, money(x)],
        money_ok=[x, v.amount],
        words=120,
    )
    return Out(
        judgement=Judgement(
            check="T1",
            ref=v.vo,
            verdict="judgement_call",
            tag="t1_oral_instruction",
            range=EffectRange(low=Correction(variations={v.vo: x})),
            why=f"Oral instruction confirmed in {conf.name} with no dissent, so effective under "
            f"clause 3.3; price unagreed, Employer's QS indicates about {money(x)}.",
        ),
        variations=[_register(v, "Approved")],
        specs=[conf, sub, qs_mail],
        plants=[
            Plant(
                "diary",
                v.d0,
                f"{w.er.name} on site. Instructed verbally that {v.short} proceed; "
                "Brackmoor to confirm in writing.",
            )
        ],
    )


def t1_no_response(w: World, rng: random.Random, v: Var) -> Out:
    eri = _eri(w, v, v.d0 - timedelta(days=rng.randint(6, 14)))
    sub = _submission(w, v, v.d0)
    mail = _internal_email(
        w,
        sub.on + timedelta(days=rng.randint(30, 60)),
        w.cm,
        [w.fd],
        f"{w.code} year end: {v.short}",
        [
            f"Says the ER has been positive about {v.quote} in meetings and he is confident it will be signed off.",
            "Says he has kept it in the forecast as approved.",
        ],
        [v.quote],
    )
    plants = [
        Plant(
            "minutes", sub.on + timedelta(days=d), f"{v.quote} ({v.short}): ER reviewing; response awaited."
        )
        for d in (20, 50, 80)
    ]
    return Out(
        judgement=Judgement(
            check="T1",
            ref=v.vo,
            verdict="insufficient_evidence",
            tag="t1_no_response",
            correction=_remove(v),
            range=EffectRange(low=_remove(v)),
            request=f"The ER's written acceptance of quotation {v.quote}",
            why="Quotation submitted; minutes show it is still awaited; no acceptance anywhere.",
        ),
        variations=[_register(v, "Approved")],
        specs=[eri, sub, mail],
        plants=plants,
    )


def t1_missing_attachment(w: World, rng: random.Random, v: Var, other: Var) -> Out:
    sub = _submission(w, v, v.d0, mention_eri=False)
    sub2 = _submission(w, other, v.d0 + timedelta(days=rng.randint(2, 8)), mention_eri=False)
    on = sub2.on + timedelta(days=rng.randint(18, 35))
    letter_ref = w.ref("in")
    mail = Spec(
        name=f"{on.isoformat()}_email_{w.ref('email')}.md",
        on=on,
        kind="email",
        sender=w.er,
        to=[w.pm],
        cc=[w.cm],
        subject=f"Quotations {v.quote} and {other.quote}",
        in_register=False,
        purpose="Covering email from the ER. The attachment itself is NOT part of this document.",
        facts=[
            f"Says: please find attached letter {letter_ref} setting out the Employer's response to "
            f"quotations {v.quote} and {other.quote}.",
            "Gives no hint of what the response is.",
            f"Ends with an attachment line: [Attachment: {letter_ref.replace('/', '-')}.pdf]",
        ],
        must_include=[letter_ref, v.quote, other.quote],
        must_not_include=[v.vo, "£", "accept", "reject"],
        words=90,
    )
    return Out(
        judgement=Judgement(
            check="T1",
            ref=v.vo,
            verdict="insufficient_evidence",
            tag="t1_missing_attachment",
            correction=_remove(v),
            range=EffectRange(low=_remove(v)),
            request=f"Letter {letter_ref} (the ER's response to {v.quote})",
            why=f"The ER's response exists ({mail.name} covers letter {letter_ref}) but the "
            "letter itself is not in the file.",
        ),
        variations=[_register(v, "Approved"), _register(other, "Submitted", included=False)],
        specs=[sub, sub2, mail],
        register_only=[(on, letter_ref, w.er.name, w.pm.name, f"Quotations {v.quote} and {other.quote}")],
    )


T1_STORIES = {
    "t1_ok_plain": (t1_ok_plain, 7),
    "t1_ok_customer_ref": (t1_ok_customer_ref, 4),
    "t1_ok_grudging": (t1_ok_grudging, 3),
    "t1_ok_vat": (t1_ok_vat, 2),
    "t1_ok_after_query": (t1_ok_after_query, 2),
    "t1_ok_misfiled": (t1_ok_misfiled, 2),
    "t1_rejected_oblique": (t1_rejected_oblique, 3),
    "t1_partial": (t1_partial, 3),
    "t1_withdrawn": (t1_withdrawn, 2),
    "t1_wrong_authority": (t1_wrong_authority, 2),
    "t1_time_barred": (t1_time_barred, 2),
    "t1_post_period": (t1_post_period, 2),
    "t1_value_disputed": (t1_value_disputed, 3),
    "t1_oral_instruction": (t1_oral_instruction, 2),
    "t1_no_response": (t1_no_response, 2),
    "t1_missing_attachment": (t1_missing_attachment, 2),
}
ROUTINE_T1 = {"t1_ok_plain"}


# ---------------------------------------------------------------------------
# E2: the estimate to complete
# ---------------------------------------------------------------------------


@dataclass
class Numbers:
    """Everything the E2 and M1 stories need to know about one contract's numbers."""

    bac: float
    ev: float
    ac: float
    cpi_shown: float
    cpi_fwd: float
    mgmt_etc: float
    true_etc: float
    prelims_rate: float
    baseline_finish: date
    forecast_finish: date
    extra: dict[str, float] = field(default_factory=dict)


# Performance and programme shape each E2 story needs: (cpi range, forward cpi rule, slip months)
E2_PARAMS: dict[str, dict] = {
    "e2_routine": {"cpi": (0.97, 1.04), "fwd": "same", "slip": 0},
    "e2_one_off": {"cpi": (0.82, 0.88), "fwd": "plan", "slip": 0},
    "e2_reflected": {"cpi": (0.80, 0.90), "fwd": "same", "slip": 0},
    "e2_front_loaded": {"cpi": (0.99, 1.02), "fwd": "plan", "slip": 0},
    "e2_claim_provided": {"cpi": (0.96, 1.02), "fwd": "same", "slip": 0},
    "e2_slip_covered": {"cpi": (0.95, 1.01), "fwd": "same", "slip": (3, 5)},
    "e2_cpi_trend": {"cpi": (0.82, 0.88), "fwd": "same", "slip": 0},
    "e2_unbooked_claim": {"cpi": (0.96, 1.02), "fwd": "same", "slip": 0},
    "e2_prelims_slip": {"cpi": (0.96, 1.02), "fwd": "same", "slip": (3, 5)},
    "e2_smoothing": {"cpi": (0.94, 0.97), "fwd": "same", "slip": 0},
    "e2_recovery": {"cpi": (0.82, 0.90), "fwd": "same", "slip": 0},
}
E2_WEIGHTS = {
    "e2_routine": 4,
    "e2_one_off": 2,
    "e2_reflected": 2,
    "e2_front_loaded": 2,
    "e2_claim_provided": 1,
    "e2_slip_covered": 1,
    "e2_cpi_trend": 2,
    "e2_unbooked_claim": 2,
    "e2_prelims_slip": 2,
    "e2_smoothing": 1,
    "e2_recovery": 1,
}


def months_between(a: date, b: date) -> int:
    return round((b - a).days / 30.44)


def e2_etc(
    story: str, rng: random.Random, rem: float, cpi_fwd: float, rate: float, slip_m: int, ac_true: float
) -> tuple[float, float, dict[str, float]]:
    """(management ETC, true ETC, story amounts) for one E2 story."""
    base = round(rem / cpi_fwd)
    extra: dict[str, float] = {}
    if story == "e2_front_loaded":
        m = round(rem * rng.uniform(0.10, 0.16), -3)
        extra["materials"] = m
        return base - m, base - m, extra
    if story in ("e2_claim_provided", "e2_unbooked_claim"):
        z = round(rem * rng.uniform(0.04, 0.07), -3)
        s = round(z * rng.uniform(0.6, 0.85), -3)
        extra.update(claim=z, settle=s)
        return (base + s if story == "e2_claim_provided" else base), base + s, extra
    if story in ("e2_slip_covered", "e2_prelims_slip"):
        add = slip_m * rate
        extra["slip_cost"] = add
        return (base + add if story == "e2_slip_covered" else base), base + add, extra
    if story == "e2_cpi_trend":
        return round(rem), base, extra
    if story == "e2_smoothing":
        x = round(base * rng.uniform(0.04, 0.07), -3)
        extra["held_back"] = x
        return base - x, base, extra
    if story == "e2_recovery":
        assumed = (1 / cpi_fwd + 1) / 2
        mgmt = round(rem * assumed)
        extra["savings"] = base - mgmt
        return mgmt, base, extra
    return base, base, extra


def e2_story(story: str, w: World, rng: random.Random, n: Numbers) -> Out:
    sub_co, sub_pkg, sub_contact = w.subs[0]
    out = Out()
    pe = PERIOD_END
    assumed_finish = n.forecast_finish if story == "e2_slip_covered" else n.baseline_finish
    months = max(1, months_between(pe, assumed_finish))
    prelims = round(n.prelims_rate * months)
    risk = round(n.mgmt_etc * rng.uniform(0.015, 0.03), -3)
    allowances: list[EtcLine] = []
    if story == "e2_claim_provided":
        allowances.append(
            EtcLine(
                item=f"Allowance: {sub_co} final account",
                amount=n.extra["settle"],
                basis="QS assessment of likely settlement",
            )
        )
    rest = n.mgmt_etc - prelims - risk - sum(a.amount for a in allowances)
    direct = round(rest * 0.58)
    out.breakdown = [
        EtcLine(
            item="Direct works: remaining packages",
            amount=direct,
            basis="P6 remaining budget, adjusted to current productivity"
            if story not in ("e2_cpi_trend",)
            else "P6 remaining budget",
        ),
        EtcLine(
            item="Subcontract packages: committed balance and forecast",
            amount=rest - direct,
            basis="Subcontract ledger and package forecasts",
        ),
        EtcLine(
            item="Preliminaries and site overheads",
            amount=prelims,
            basis=f"{months} months to {long_date(assumed_finish)} at {money(n.prelims_rate)} per month",
        ),
        *allowances,
        EtcLine(item="Risk and contingency", amount=risk, basis="Quantified risk register, P50"),
    ]
    true = n.true_etc
    fix = Correction(etc=true)

    if story == "e2_routine":
        out.judgement = Judgement(check="E2", ref="ETC", verdict="supported")
        out.commentary.append("Project performing broadly in line with budget; ETC re-forecast monthly.")
    elif story == "e2_one_off":
        memo_on = date(2026, rng.randint(9, 10), rng.randint(5, 25))
        out.specs.append(
            Spec(
                name=f"{memo_on.isoformat()}_memo_rework-close-out.md",
                on=memo_on,
                kind="memo",
                sender=w.pm,
                to=[w.cm, w.qs],
                subject="Pipe rack rework: close-out",
                in_register=False,
                purpose="Internal close-out note on a one-off rework episode.",
                facts=[
                    "Records that the pipe rack rework caused by a supplier's defective steel is complete and "
                    "closed out.",
                    "Productivity on the remaining work has been at or above plan since.",
                    "The supplier has accepted liability; Brackmoor will pursue recovery separately, and it is "
                    "not in the forecast.",
                ],
                must_include=["closed out", "accepted liability"],
                words=280,
            )
        )
        out.plants += [
            Plant(
                "cvr_q4",
                pe,
                "Cost performance to date reflects the one-off pipe rack rework "
                "(closed out). Productivity on remaining work at or above plan for "
                "the last three months; remaining work forecast at plan rates.",
            ),
            Plant(
                "minutes",
                date(2026, 11, 12),
                "Rework on the pipe rack is complete. Remaining "
                "mechanical work progressing at planned rates.",
            ),
        ]
        out.commentary.append(
            "Cumulative CPI depressed by the closed-out pipe rack rework; remaining work at plan rates."
        )
        out.judgement = Judgement(
            check="E2",
            ref="ETC",
            verdict="supported",
            tag=story,
            why="EVM looks poor, but the overrun was a documented one-off; productivity is back to plan.",
        )
    elif story == "e2_reflected":
        out.plants.append(
            Plant(
                "cvr_q4",
                pe,
                f"ETC re-forecast bottom-up in November at current productivity "
                f"(CPI {n.cpi_fwd:.2f}); no recovery assumed.",
            )
        )
        out.commentary.append("Productivity below plan; ETC reforecast bottom-up at current rates.")
        out.judgement = Judgement(
            check="E2",
            ref="ETC",
            verdict="supported",
            tag=story,
            why="Poor CPI, already reflected in a bottom-up reforecast.",
        )
    elif story == "e2_front_loaded":
        m = n.extra["materials"]
        on = date(2026, 12, rng.randint(14, 21))
        out.specs.append(
            Spec(
                name=f"{on.isoformat()}_memo_procurement-status.md",
                on=on,
                kind="memo",
                sender=w.qs,
                to=[w.cm, w.pm],
                subject="Procurement status: materials on site",
                in_register=False,
                purpose="Internal procurement status report.",
                facts=[
                    f"Brackmoor bought structural steel, pipe spools and valves early to secure prices; "
                    f"{money(m)} of materials are on site or in the bonded store, not yet installed.",
                    "These are costed to the job on receipt, so cost to date includes them.",
                    "Physical progress (and so earned value) only counts them once installed.",
                    "The remaining budget in the ETC has been reduced by the same amount, since they are "
                    "already paid for.",
                ],
                must_include=[money(m)],
                money_ok=[m],
                words=320,
            )
        )
        out.plants += [
            Plant(
                "diary",
                date(2026, 11, rng.randint(2, 20)),
                "Large delivery of structural steel "
                "and pipe spools to the laydown "
                "area; stored for later erection.",
            ),
            Plant(
                "cvr_q4",
                pe,
                f"Cost to date includes {money(m)} of materials on site not yet "
                "installed; CPI understated accordingly.",
            ),
        ]
        out.commentary.append("Cost to date includes early procurement of materials held on site.")
        out.judgement = Judgement(
            check="E2",
            ref="ETC",
            verdict="supported",
            tag=story,
            why="CPI looks poor because cost to date includes materials bought but not "
            "yet installed; the ETC already nets them off.",
        )
    elif story in ("e2_claim_provided", "e2_unbooked_claim"):
        z, s = n.extra["claim"], n.extra["settle"]
        on = date(2026, 11, rng.randint(3, 20))
        out.specs.append(
            Spec(
                name=f"{on.isoformat()}_letter_{sub_co.split()[0].upper()}-FA.md",
                on=on,
                kind="letter",
                sender=sub_contact,
                to=[w.cm],
                subject=f"{sub_pkg.capitalize()} package: final account claim",
                purpose="A subcontractor's claim letter.",
                in_register=False,
                facts=[
                    f"{sub_co} submits a claim for disruption and prolongation on the {sub_pkg} package, "
                    f"in the sum of {money(z)}.",
                    "Blames late access to work faces and resequencing by Brackmoor.",
                    "Says it will refer the matter to adjudication if not resolved within 60 days.",
                ],
                must_include=[money(z)],
                money_ok=[z],
                words=330,
            )
        )
        mail_on = on + timedelta(days=rng.randint(10, 30))
        if story == "e2_unbooked_claim":
            out.specs.append(
                _internal_email(
                    w,
                    mail_on,
                    w.cm,
                    [w.pm],
                    f"{sub_co} claim",
                    [
                        f"Says that realistically Brackmoor will end up settling the {sub_co} claim at around "
                        f"{money(s)}.",
                        "Says he hasn't put anything in the CVR for it yet; wants to see if they come down first.",
                    ],
                    [money(s), "CVR"],
                    money_ok=[s, z],
                )
            )
            out.judgement = Judgement(
                check="E2",
                ref="ETC",
                verdict="misstated",
                tag=story,
                correction=fix,
                why=f"{sub_co} claim of {money(z)}; commercial manager expects to settle at "
                f"{money(s)}, but nothing is in the ETC build-up.",
            )
        else:
            out.specs.append(
                _internal_email(
                    w,
                    mail_on,
                    w.qs,
                    [w.cm],
                    f"{sub_co} claim",
                    [
                        f"Says the QS assessment is that the {sub_co} claim settles at around {money(s)}.",
                        "Confirms that amount is in the ETC as a specific allowance.",
                    ],
                    [money(s)],
                    money_ok=[s, z],
                )
            )
            out.judgement = Judgement(
                check="E2",
                ref="ETC",
                verdict="supported",
                tag=story,
                why=f"The {sub_co} claim is provided for at {money(s)} in the ETC build-up.",
            )
    elif story in ("e2_slip_covered", "e2_prelims_slip"):
        if story == "e2_slip_covered":
            out.plants.append(
                Plant(
                    "cvr_q4",
                    pe,
                    f"Forecast completion now {long_date(n.forecast_finish)} per "
                    "the December P6 update; preliminaries in the ETC extended "
                    "to match.",
                )
            )
            out.judgement = Judgement(
                check="E2",
                ref="ETC",
                verdict="supported",
                tag=story,
                why="P6 shows a slip, but the preliminaries line runs to the new forecast finish.",
            )
        else:
            out.plants.append(
                Plant(
                    "minutes",
                    date(2026, 12, 15),
                    "Planner tabled the December programme "
                    "update; key dates under review following "
                    "the steelwork resequencing.",
                )
            )
            out.judgement = Judgement(
                check="E2",
                ref="ETC",
                verdict="misstated",
                tag=story,
                correction=fix,
                why=f"ETC preliminaries run to {long_date(n.baseline_finish)}, but P6 "
                f"forecasts finish on {long_date(n.forecast_finish)}: "
                f"{money(n.extra['slip_cost'])} of site overheads missing.",
            )
        out.commentary.append("Programme under pressure from steelwork resequencing; ETC reviewed.")
    elif story == "e2_cpi_trend":
        out.plants += [
            Plant(
                "minutes",
                date(2026, 11, 12),
                f"Brackmoor reported productivity on piping and "
                f"steel at around {n.cpi_shown:.2f} of plan in "
                "October.",
            ),
            Plant(
                "minutes",
                date(2026, 12, 15),
                "Productivity remains below plan; new supervision team mobilised.",
            ),
            Plant(
                "cvr_q4",
                pe,
                "PM confident productivity will return to plan with the new "
                "supervision team; no change to ETC.",
            ),
        ]
        out.commentary.append(
            "ETC reflects remaining budget. New supervision team expected to restore productivity to plan."
        )
        out.judgement = Judgement(
            check="E2",
            ref="ETC",
            verdict="misstated",
            tag=story,
            correction=fix,
            why=f"Remaining work at budget rates despite CPI around {n.cpi_shown:.2f} for "
            "months and no evidence of improvement.",
        )
    elif story == "e2_smoothing":
        x = n.extra["held_back"]
        on = date(2027, 1, rng.randint(8, 14))
        out.specs.append(
            _internal_email(
                w,
                on,
                w.fd,
                [w.cm, w.pm],
                f"RE: FW: {w.code} site re-forecast",
                [
                    f"Written as a short email chain. First, {w.qs.name} sends the site team's year-end re-forecast, "
                    f"which puts the ETC {money(x)} above the Q3 figure.",
                    f"{w.cm.name} forwards it to {w.fd.name} asking how to treat it.",
                    f"{w.fd.name} replies: keep the year-end ETC at the Q3 figure; we'll look at the site's number "
                    "after the board meeting in February.",
                ],
                [money(x), "Q3"],
                money_ok=[x],
                words=300,
            )
        )
        out.plants.append(Plant("cvr_q4", pe, "ETC held at Q3 level pending board review."))
        out.commentary.append("ETC unchanged from Q3; project broadly on budget.")
        out.judgement = Judgement(
            check="E2",
            ref="ETC",
            verdict="misstated",
            tag=story,
            correction=fix,
            why=f"The site's re-forecast is {money(x)} higher, but the FD held the ETC at the Q3 figure.",
        )
    elif story == "e2_recovery":
        v = n.extra["savings"]
        on = date(2026, 12, rng.randint(4, 18))
        out.specs.append(
            Spec(
                name=f"{on.isoformat()}_email_{w.ref('email')}.md",
                on=on,
                kind="email",
                sender=sub_contact,
                to=[w.cm],
                subject="Revised rates proposal",
                in_register=False,
                purpose="A subcontractor's reply to Brackmoor's request for lower rates.",
                facts=[
                    f"{sub_co} says it is open to discussing resequencing but cannot commit to the rate "
                    "reductions Brackmoor has proposed.",
                    "Says its own costs are up and it will come back in the new year.",
                ],
                must_include=["cannot commit"],
                must_not_include=["£"],
                words=150,
            )
        )
        out.plants.append(
            Plant(
                "cvr_q4",
                pe,
                f"ETC includes {money(v)} of recovery-plan savings (resequencing "
                f"and renegotiated {sub_pkg} rates), not yet agreed with {sub_co}.",
            )
        )
        out.commentary.append(
            "ETC assumes recovery plan savings from resequencing and subcontract renegotiation."
        )
        out.judgement = Judgement(
            check="E2",
            ref="ETC",
            verdict="judgement_call",
            tag=story,
            correction=fix,
            range=EffectRange(low=fix),
            why=f"ETC relies on {money(v)} of savings that {sub_co} hasn't agreed.",
        )
    return out


# ---------------------------------------------------------------------------
# M1: onerous contracts on management's own numbers
# ---------------------------------------------------------------------------

M1_WEIGHTS = {"m1_routine": 12, "m1_ok_provided": 3, "m1_no_provision": 3, "m1_stale": 2}
LOSS_STORIES = {"m1_ok_provided", "m1_no_provision", "m1_stale"}


def m1_story(story: str, w: World, required: float, booked: float, loss: float) -> Out:
    out = Out()
    if story == "m1_routine":
        out.judgement = Judgement(check="M1", ref="PROVISION", verdict="supported")
    elif story == "m1_ok_provided":
        out.commentary.append(
            f"Forecast loss of {money(loss)} at completion. Loss to date recognised through "
            f"margin; provision of {money(booked)} held for the remaining loss."
        )
        out.plants.append(
            Plant(
                "cvr_q4",
                PERIOD_END,
                f"Forecast loss {money(loss)}; provision for remaining "
                f"loss {money(booked)} (loss to date already through "
                "margin).",
            )
        )
        out.judgement = Judgement(
            check="M1",
            ref="PROVISION",
            verdict="supported",
            tag=story,
            why="Loss-making on management's own numbers, and the provision for the "
            "remaining loss is booked in full.",
        )
    elif story == "m1_no_provision":
        out.commentary.append(
            "Forecast shows a shortfall at completion, which the board expects to recover "
            "through the prolongation claim in preparation. No provision considered "
            "necessary."
        )
        out.plants.append(
            Plant(
                "cvr_q4",
                PERIOD_END,
                "Shortfall at completion expected to be recovered through "
                "the prolongation claim (not yet submitted); no provision.",
            )
        )
        out.judgement = Judgement(
            check="M1",
            ref="PROVISION",
            verdict="misstated",
            tag=story,
            why="Management's own EAC exceeds TP, no provision booked; an unsubmitted "
            "claim is not in TP and can't offset it.",
        )
    elif story == "m1_stale":
        out.commentary.append(
            f"Loss provision of {money(booked)} established at Q3 and reviewed at year end: "
            "considered adequate."
        )
        out.plants.append(
            Plant("cvr_q4", PERIOD_END, f"Loss provision unchanged from Q3 at {money(booked)}.")
        )
        out.judgement = Judgement(
            check="M1",
            ref="PROVISION",
            verdict="misstated",
            tag=story,
            why=f"Provision {money(booked)} is the Q3 figure; on year-end numbers "
            f"{money(required)} is required.",
        )
    return out


def scenario_name(t1: list[str], e2: str, m1: str) -> str:
    """One-line label for the answer key's scenario field."""
    issues = (
        [s for s in t1 if s not in ROUTINE_T1]
        + ([e2] if e2 != "e2_routine" else [])
        + ([m1] if m1 != "m1_routine" else [])
    )
    return "+".join(issues) or "clean"


def deck(weights: dict[str, int], n: int, rng: random.Random) -> list[str]:
    base = [s for s, k in weights.items() for _ in range(k)]
    out: list[str] = []
    while len(out) < n:
        chunk = base[:]
        rng.shuffle(chunk)
        out += chunk
    return out[:n]


def add_months_safe(d: date, n: int) -> date:
    return add_months(d, n)
