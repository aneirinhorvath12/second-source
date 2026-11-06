"""Writes contract data as tidy, commented YAML that's pleasant to read and edit by hand.

PyYAML can read these files but would write them without comments or digit
grouping, so the writers here are hand-rolled. Free text is written as JSON
strings, which are always valid YAML.
"""

from __future__ import annotations

import json

from .answers import AnswerKey, Correction
from .models import CostReport, Terms


def num(x: float) -> str:
    """60871000.0 -> 60_871_000; keeps decimals only when there are some."""
    if float(x).is_integer():
        return f"{int(x):_}"
    return f"{x:_.2f}"


def text(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def terms_yaml(t: Terms) -> str:
    return f"""# Contract terms for {t.contract_id}: the summary finance holds in its systems.
# The legal wording is in docs/contract.md; keep the two consistent.
contract_id: {t.contract_id}
name: {text(t.name)}
customer: {text(t.customer)}
contract_price: {num(t.contract_price)}
start_date: {t.start_date.isoformat()}
completion_date: {t.completion_date.isoformat()}
ld_rate_per_day: {num(t.ld_rate_per_day)}
ld_cap: {num(t.ld_cap)}
"""


def cost_report_yaml(r: CostReport) -> str:
    lines = [
        f"# Management's cost report and variation register for {r.contract_id} at {r.period_end:%d %B %Y}.",
        "# Every system sees this file (with comments stripped). Never put answers here.",
        f"contract_id: {r.contract_id}",
        f"period_end: {r.period_end.isoformat()}",
        f"contract_price: {num(r.contract_price)}",
        f"claims_in_tp: {num(r.claims_in_tp)}",
        f"ld_deduction: {num(r.ld_deduction)}",
        f"cost_to_date: {num(r.cost_to_date)}",
        f"etc: {num(r.etc)}  # estimate to complete",
    ]
    if r.etc_breakdown:
        lines.append("etc_breakdown:  # management's build-up; should sum to etc")
        for e in r.etc_breakdown:
            lines += [f"  - item: {text(e.item)}", f"    amount: {num(e.amount)}"]
            if e.basis:
                lines.append(f"    basis: {text(e.basis)}")
    lines += [
        f"provision_booked: {num(r.provision_booked)}  # onerous contract provision",
        f"commentary: {text(r.commentary)}",
    ]
    if r.variations:
        lines.append("variations:  # the variation register")
        for v in r.variations:
            lines += [
                f"  - id: {v.id}",
                f"    description: {text(v.description)}",
                f"    amount: {num(v.amount)}",
                f"    included_in_tp: {str(v.included_in_tp).lower()}",
                f"    reported_status: {text(v.reported_status)}",
            ]
    else:
        lines.append("variations: []")
    return "\n".join(lines) + "\n"


def _correction(c: Correction, indent: str) -> list[str]:
    out = []
    if c.variations:
        inner = ", ".join(f"{k}: {num(v)}" for k, v in c.variations.items())
        out.append(f"{indent}variations: {{{inner}}}")
    for field in ("etc", "claims_in_tp", "ld_deduction"):
        value = getattr(c, field)
        if value is not None:
            out.append(f"{indent}{field}: {num(value)}")
    return out or [f"{indent}{{}}"]


def answers_yaml(key: AnswerKey) -> str:
    lines = [
        f"# Answer key for {key.contract_id}. Systems never see this file.",
        "# Corrections say what the inputs should be; the engine computes the profit effects.",
        f"contract_id: {key.contract_id}",
        f"scenario: {key.scenario}",
        f"notes: {text(key.notes)}",
        "judgements:",
    ]
    for j in key.judgements:
        lines += [f"  - check: {j.check}", f"    ref: {j.ref}", f"    verdict: {j.verdict}"]
        if j.tag != "routine":
            lines.append(f"    tag: {j.tag}")
        if j.correction is not None:
            body = _correction(j.correction, "      ")
            if body == ["      {}"]:
                lines.append("    correction: {}")
            else:
                lines += ["    correction:", *body]
        if j.range is not None:
            lines.append("    range:")
            for end in ("low", "high"):
                body = _correction(getattr(j.range, end), "        ")
                if body == ["        {}"]:
                    lines.append(f"      {end}: {{}}  # as reported")
                else:
                    lines += [f"      {end}:", *body]
        if j.request:
            lines.append(f"    request: {text(j.request)}")
        if j.why:
            lines.append(f"    why: {text(j.why)}")
    return "\n".join(lines) + "\n"
