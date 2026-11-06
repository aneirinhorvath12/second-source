"""Drafts documents with a model, from fact sheets, and checks every draft before it is accepted.

The model writes prose only. Headers, names, dates and references come from
code, and each draft is validated: required strings present, banned strings
absent, and no sum of money over £10,000 that the fact sheet didn't allow.
Failed drafts are retried with the errors fed back. Accepted drafts are cached
on disk, so re-running the generator doesn't pay twice.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .stories import BANNED_EVERYWHERE, Spec
from .world import World, long_date

KEY_MODEL = os.environ.get("SECOND_SOURCE_WRITER_MODEL", "claude-sonnet-5-5")
POOL_MODEL = os.environ.get("SECOND_SOURCE_POOL_MODEL", "claude-haiku-5-5")
CACHE = Path(os.environ.get("SECOND_SOURCE_WRITER_CACHE", ".cache/writer"))
PROMPT_VERSION = "2"

USAGE: dict[str, list[int]] = {}
_lock = threading.Lock()

SYSTEM = """You write single documents for the project file of a fictional UK engineering contract.
The file will be read by experienced reviewers, so the writing must be realistic: specific, plausible,
professional, British English, with the texture of real correspondence (practical detail, references
to site matters, the occasional aside). Never be cartoonish or melodramatic.

Rules:
- Write ONLY the body of the document, in Markdown. The header block (from, to, date, subject),
  salutation and sign-off are added automatically: do not write them.
- Convey every fact in the fact sheet, in natural words. Include each "exact string" verbatim.
- Do not invent other facts about prices, variations, claims, costs, forecasts, the contract sum or
  money. Mention no sum of money that the fact sheet doesn't list.
- Don't add analysis, reasons or conclusions beyond the fact sheet. In particular, don't spell out
  the contractual position (which clause applies, who has authority, whether something is valid)
  unless a fact tells you to. Real correspondence leaves a lot unsaid, and readers must work it out.
- Never mention accounting standards, audits, auditors, revenue, or that this is fictional.
- Keep to roughly the length asked for."""


def _client() -> Any:
    import anthropic

    return anthropic.Anthropic(max_retries=8)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("*", "").replace("’", "'")).lower()


MONEY = re.compile(r"£\s?(\d[\d,]*(?:\.\d+)?)\s?(m\b|million|k\b|bn)?", re.IGNORECASE)


def amounts(text: str) -> list[float]:
    out = []
    for num, unit in MONEY.findall(text):
        x = float(num.replace(",", ""))
        unit = (unit or "").lower()
        x *= {"m": 1e6, "million": 1e6, "k": 1e3, "bn": 1e9}.get(unit, 1)
        out.append(x)
    return out


def check_text(
    text: str, must: list[str], must_not: list[str], money_ok: list[float] | None, min_words: int
) -> list[str]:
    """Problems with a draft; empty means accepted. money_ok=None skips the money check."""
    t = _norm(text)
    errs = [f"missing the exact string '{s}'" for s in must if _norm(s) not in t]
    errs += [f"must not contain '{s}'" for s in must_not + BANNED_EVERYWHERE if _norm(s) in t]
    if money_ok is not None:
        bad = [x for x in amounts(text) if x >= 10_000 and not any(abs(x - y) <= 1 for y in money_ok)]
        if bad:
            errs.append(
                "mentions sums of money not in the fact sheet (write amounts exactly as given, "
                "and mention no others): " + ", ".join(f"£{x:,.0f}" for x in bad)
            )
    if "{" in text or "}" in text:
        errs.append("contains curly braces; write plain prose")
    if len(text.split()) < min_words:
        errs.append(f"too short ({len(text.split())} words)")
    return errs


def _call(client: Any, model: str, system: str, prompt: str, max_tokens: int = 4000) -> str:
    resp = client.messages.create(
        model=model, max_tokens=max_tokens, system=system, messages=[{"role": "user", "content": prompt}]
    )
    with _lock:
        u = USAGE.setdefault(model, [0, 0])
        u[0] += resp.usage.input_tokens
        u[1] += resp.usage.output_tokens
    return "".join(b.text for b in resp.content if b.type == "text").strip()


def _cached(key: str) -> str | None:
    p = CACHE / f"{key}.txt"
    return p.read_text() if p.exists() else None


def _store(key: str, text: str) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / f"{key}.txt").write_text(text)


# ---------------------------------------------------------------------------
# key documents
# ---------------------------------------------------------------------------


def _spec_prompt(w: World, s: Spec) -> str:
    facts = "\n".join(f"- {f}" for f in s.facts)
    must = "\n".join(f"- {m}" for m in s.must_include) or "- (none)"
    must_not = "\n".join(f"- {m}" for m in s.must_not_include) or "- (none)"
    money_ok = ", ".join(f"£{x:,.0f}" for x in s.money_ok) or "none"
    to = "; ".join(p.sig() for p in s.to)
    return f"""Background (for consistency; don't recite it):
{w.bible()}

Document: a {s.kind} dated {long_date(s.on)}, from {s.sender.sig()} to {to}.
Subject: {s.subject}
Purpose: {s.purpose}

Facts to convey:
{facts}

Exact strings that must appear verbatim:
{must}

Must NOT appear anywhere:
{must_not}

Sums of money you may mention: {money_ok}
Length: about {s.words} words."""


def write_spec(client: Any, w: World, s: Spec, attempts: int = 4) -> str:
    prompt = _spec_prompt(w, s)
    key = hashlib.sha256(f"{PROMPT_VERSION}|{KEY_MODEL}|{prompt}".encode()).hexdigest()[:24]
    hit = _cached(key)
    if hit is not None:
        return hit
    feedback = ""
    for _ in range(attempts):
        body = _call(client, KEY_MODEL, SYSTEM, prompt + feedback)
        full = render(w, s, body)
        errs = check_text(full, s.must_include, s.must_not_include, s.money_ok, max(40, s.words // 3))
        if not errs:
            _store(key, body)
            return body
        feedback = (
            "\n\nYour previous draft was rejected for these reasons; fix them all:\n- "
            + "\n- ".join(errs)
            + "\n\nPrevious draft:\n"
            + body
        )
    raise RuntimeError(f"{w.cid} {s.name}: could not produce a valid draft: {errs}")


def _email(p) -> str:
    domain = (
        "brackmoor.co.uk"
        if p.org.startswith("Brackmoor")
        else re.sub(r"[^a-z]", "", p.org.lower().split()[0]) + ".co.uk"
    )
    return f"{p.name.lower().replace(' ', '.')}@{domain}"


_SIGN_OFF = re.compile(r"^(yours (sincerely|faithfully)|kind regards|best regards|regards|many thanks)[,.]?$",
                       re.IGNORECASE)


def clean_body(body: str, kind: str) -> str:
    """Drop the salutation, repeated subject line and sign-off a writer sometimes adds anyway."""
    lines = body.strip().splitlines()
    while lines and (not lines[0].strip() or lines[0].lstrip("*# ").lower().startswith(("dear ", "subject", "re:"))
                     or (lines[0].startswith("**") and lines[0].endswith("**") and len(lines[0]) < 120)):
        lines.pop(0)
    if kind in ("letter", "memo"):
        for i, line in enumerate(lines):
            if _SIGN_OFF.match(line.strip()):
                lines = lines[:i]
                break
        while lines and (not lines[-1].strip() or lines[-1].lower().startswith(("cc:", "cc "))):
            lines.pop()
    return "\n".join(lines).strip()


def render(w: World, s: Spec, body: str) -> str:
    """Header and sign-off from code, body from the writer."""
    body = clean_body(body, s.kind)
    to = "; ".join(f"{p.name}, {p.role}, {p.org}" for p in s.to)
    cc = "; ".join(f"{p.name}, {p.role}" for p in s.cc)
    if s.kind == "email":
        head = [
            f"**From:** {s.sender.name} <{_email(s.sender)}>",
            "**To:** " + "; ".join(f"{p.name} <{_email(p)}>" for p in s.to),
        ]
        if s.cc:
            head.append("**Cc:** " + "; ".join(f"{p.name} <{_email(p)}>" for p in s.cc))
        head += [f"**Sent:** {s.on:%A} {long_date(s.on)}", f"**Subject:** {s.subject}", ""]
        return "\n".join(head) + "\n" + body + f"\n\n{s.sender.name}\n{s.sender.role} | {s.sender.org}\n"
    if s.kind == "memo":
        return (
            f"# Internal memo\n\n**To:** {to}\n**From:** {s.sender.name}, {s.sender.role}\n"
            f"**Date:** {long_date(s.on)}\n**Subject:** {s.subject}\n\n{body}\n"
        )
    org = s.sender.org
    head = [f"# {org}", "", f"**To:** {to}"]
    if cc:
        head.append(f"**Cc:** {cc}")
    head += [f"**Date:** {long_date(s.on)}"]
    if s.ref:
        head.append(f"**Our ref:** {s.ref}")
    head += [
        f"**Project:** {w.project}" if s.sender.org in (w.customer, "Brackmoor Engineering Ltd") else "",
        f"**Subject:** {s.subject}",
        "",
        f"Dear {s.to[0].name.split()[0]},",
        "",
    ]
    return (
        "\n".join(h for h in head if h is not None)
        + "\n"
        + body
        + f"\n\nYours sincerely,\n\n{s.sender.name}\n{s.sender.role}\n{org}\n"
    )


def write_all(jobs: list[tuple[World, Spec]], workers: int = 8) -> dict[tuple[str, str], str]:
    """Draft every spec in parallel. Returns {(contract id, file name): full document}."""
    client = _client()
    out: dict[tuple[str, str], str] = {}
    failures: list[str] = []

    def one(job: tuple[World, Spec]) -> None:
        w, s = job
        try:
            out[(w.cid, s.name)] = render(w, s, write_spec(client, w, s))
        except Exception as e:  # noqa: BLE001 - report every failure at the end
            failures.append(str(e)[:300])

    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(one, jobs))
    if failures:
        raise RuntimeError(f"{len(failures)} documents failed:\n" + "\n".join(failures))
    return out


# ---------------------------------------------------------------------------
# the reusable pool of routine documents and meeting paragraphs
# ---------------------------------------------------------------------------

PLACEHOLDERS = [
    "PROJECT",
    "SITE",
    "CUSTOMER",
    "ER",
    "CUST_PM",
    "COW",
    "PM",
    "SITE_MGR",
    "PLANNER",
    "QS",
    "SUB",
    "SUB_CONTACT",
    "AREA",
]

POOL_SYSTEM = """You write routine documents for the files of UK industrial EPC projects: process plants,
gas compression, water treatment, substations, jetties, tank farms and pipelines. Not buildings: no
interior finishes, plasterboard, decorating, brickwork, lifts or reception areas. The documents are
filler: realistic, specific and varied, but about everyday matters only. Use these
placeholders instead of names, exactly as written: [PROJECT], [SITE], [CUSTOMER], [ER] (the customer's
Employer's Representative), [CUST_PM] (customer's project manager), [COW] (customer's clerk of works),
[PM] (contractor's project manager), [SITE_MGR], [PLANNER], [QS], [SUB] (a subcontractor company),
[SUB_CONTACT] (its contracts manager), [AREA] (a plant area). The contractor is Brackmoor Engineering
Ltd. Never mention money above £5,000, variations, quotations, claims, compensation, extensions of
time, delay damages, disputes, cost overruns, forecasts of cost, or anything about the contract sum.
Never use curly braces. British English. Output only what is asked, as JSON."""

POOL_TOPICS = [
    "near-miss report: dropped object from scaffold",
    "noise complaint from a neighbouring resident",
    "traffic management plan revision for the site entrance",
    "request for information on cable tray routing",
    "query on drawing revision status for the pipe rack",
    "visitor induction arrangements for the customer's board",
    "format of operation and maintenance manuals",
    "non-conformance report close-out: weld repair documentation",
    "amber weather warning and high-wind lifting restrictions",
    "welfare facilities inspection findings",
    "permit-to-work audit results",
    "CDM principal designer coordination meeting",
    "crane lift plan review",
    "dust monitoring results at the site boundary",
    "archaeological watching brief update",
    "utility company coordination for a planned outage",
    "security incident: attempted theft of copper cable",
    "temporary works design check certificate",
    "commissioning sequence workshop invitation",
    "training records for confined space entry",
    "customer branding on site hoardings",
    "car parking arrangements",
    "bank holiday working hours",
    "waste transfer notes and skip segregation",
    "fire drill report",
    "document control procedure update",
    "3D model update and clash detection status",
    "change of invoicing address",
    "insurance certificate renewal",
    "subcontractor induction completion",
    "IT access to the common data environment",
    "monthly KPI submission",
    "carbon reporting return",
    "community liaison newsletter",
    "material test certificates for reinforcement steel",
    "approval of paint samples",
    "invitation to witness a pressure test",
    "snagging walk-down arrangements",
    "progress photography schedule",
    "site cleanliness and housekeeping",
    "ecology: nesting bird checks",
    "drug and alcohol testing results",
    "quarterly HSE award nominations",
    "first aid cover over holidays",
    "lessons learned from a minor plant collision",
    "survey control point re-establishment",
    "concrete cube test results",
    "lightning protection inspection",
    "PPE standards reminder",
    "night working notification to neighbours",
]

PARAGRAPH_CATEGORIES = {
    "hse": "health, safety and environment items in a progress meeting (incidents, inspections, campaigns)",
    "design": "design and technical items (RFIs, drawing issues, model reviews, technical queries)",
    "quality": "quality items (inspections, NCRs, test packs, certificates)",
    "logistics": "logistics and interface items (deliveries, access, laydown, neighbours, utilities)",
    "aob": "any other business items in a progress meeting",
    "cvr_general": "routine items in an internal contract cost review (cash, applications, staffing, "
    "procurement status) without stating any cost forecast or margin",
    "diary": "one-line notes in a site manager's daily diary (inspections, minor issues, visitors, plant)",
}


def _json_call(client: Any, prompt: str) -> Any:
    text = _call(client, POOL_MODEL, POOL_SYSTEM, prompt, max_tokens=16000)
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    return json.loads(text)


def _pool_ok(text: str) -> bool:
    return not check_text(
        text.replace("[", "").replace("]", ""),
        [],
        [
            "variation",
            "quotation",
            "claim",
            "extension of time",
            "delay damages",
            "dispute",
            "overrun",
            "contract sum",
        ],
        [],
        0,
    )


def build_pool(out_dir: Path, workers: int = 6) -> None:
    """Write pool/docs.json and pool/paragraphs.json (run once; the results are committed)."""
    client = _client()
    out_dir.mkdir(parents=True, exist_ok=True)
    docs: list[dict] = []
    paras: dict[str, list[str]] = {}

    def doc_batch(topics: list[str]) -> list[dict]:
        prompt = (
            "Write one routine project document for each topic below. Vary the type (letter from the "
            "customer, letter from Brackmoor, email, internal memo, subcontractor email) and length "
            "(150 to 600 words). For each, return an object with: kind (letter|email|memo), "
            "sender (one of ER, CUST_PM, COW, PM, SITE_MGR, PLANNER, QS, SUB_CONTACT), recipient (same "
            "choices), subject, body (Markdown, no header, no salutation or sign-off). Return a JSON "
            "array only.\n\nTopics:\n" + "\n".join(f"- {t}" for t in topics)
        )
        for _ in range(3):
            try:
                got = _json_call(client, prompt)
                return [d for d in got if _pool_ok(d.get("body", "") + d.get("subject", ""))]
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
        return []

    def para_batch(cat: str) -> tuple[str, list[str]]:
        prompt = (
            f"Write 30 varied, realistic paragraphs of 30 to 90 words each, for: "
            f"{PARAGRAPH_CATEGORIES[cat]}. Return a JSON array of strings only."
        )
        for _ in range(3):
            try:
                return cat, [p for p in _json_call(client, prompt) if _pool_ok(p)]
            except (json.JSONDecodeError, TypeError):
                continue
        return cat, []

    batches = [POOL_TOPICS[i : i + 5] for i in range(0, len(POOL_TOPICS), 5)] * 2
    with ThreadPoolExecutor(workers) as ex:
        for got in ex.map(doc_batch, batches):
            docs += got
        for cat, got in ex.map(para_batch, PARAGRAPH_CATEGORIES):
            paras[cat] = got
    (out_dir / "docs.json").write_text(json.dumps(docs, indent=1, ensure_ascii=False))
    (out_dir / "paragraphs.json").write_text(json.dumps(paras, indent=1, ensure_ascii=False))
