"""Turns simulated facts into the documents a finance team would actually hold.

v0 uses templates so the whole pipeline runs offline and deterministically.
Weekend upgrade: have a model rewrite each document from the same fact sheet
for realism (longer, messier, facts buried), then check every fact still
appears. The facts, not the wording, are the ground truth.
"""

from __future__ import annotations

from datetime import date

from ..models import Terms, Variation


def gbp(x: float) -> str:
    return f"£{x:,.0f}"


def contract_doc(t: Terms, contractor: str) -> str:
    return f"""# Contract {t.contract_id}: {t.name}

**Employer:** {t.customer}
**Contractor:** {contractor}
**Form:** Lump-sum fixed-price EPC agreement
**Date of agreement:** {t.start_date:%d %B %Y}

## 4. Contract price
4.1 The Contract Price is {gbp(t.contract_price)}, fixed and not subject to adjustment
except by Variation under clause 14.

## 8. Time for completion
8.1 The Contractor shall achieve Completion by {t.completion_date:%d %B %Y}.
8.4 If the Contractor fails to achieve Completion by that date, it shall pay delay damages
of {gbp(t.ld_rate_per_day)} per day, up to a maximum of {gbp(t.ld_cap)}.

## 14. Variations
14.1 No change to the Works shall constitute a Variation unless instructed or agreed in
writing by the Employer's Representative.
14.3 The value of a Variation shall be agreed between the parties or, failing agreement,
determined under clause 20 (Disputes).
"""


def submission_doc(cid: str, v: Variation, contractor: str, customer: str, on: date) -> str:
    return f"""# Variation submission {v.id}
**Contract:** {cid}
**From:** {contractor}
**To:** {customer}, Employer's Representative
**Date:** {on:%d %B %Y}

We give notice that the following constitutes a Variation under clause 14:
{v.description}.

We value this Variation at {gbp(v.amount)} and request your written agreement.
"""


def letter_doc(
    cid: str,
    vo_ref: str,
    kind: str,
    amount: float,
    customer: str,
    on: date,
    counter: float | None = None,
) -> str:
    body = {
        "approved": (
            f"We confirm acceptance of Variation {vo_ref} in the sum of {gbp(amount)}. "
            "This letter constitutes written agreement under clause 14.1."
        ),
        "rejected": (
            f"We have reviewed your submission {vo_ref}. In our view the work described falls "
            "within the original scope of the Works and does not constitute a Variation under "
            "clause 14. We therefore reject the submission in full."
        ),
        "pending": (
            f"We acknowledge receipt of {vo_ref}. We have not instructed this work and do not "
            "accept any liability for it at this stage. We will respond once our review is complete."
        ),
        "in_principle": (
            f"We accept in principle that the change described in {vo_ref} is a Variation under "
            f"clause 14. We do not accept your valuation of {gbp(amount)}. Our assessment of a "
            f"fair value is {gbp(counter or 0)}, and we propose to meet to agree the final sum."
        ),
    }[kind]
    return f"""# Letter from {customer}
**Re:** Contract {cid}, {vo_ref}
**Date:** {on:%d %B %Y}

{body}

Yours faithfully,
Employer's Representative
"""


def minutes_doc(cid: str, period_end: date, notes: list[str]) -> str:
    items = "\n".join(f"{i}. {n}" for i, n in enumerate(notes, 1))
    return f"""# Project review minutes: {cid}
**Date:** {period_end:%d %B %Y}
**Attendees:** Project Director, Commercial Manager, Project Controls Lead, Finance Business Partner

{items}
"""
