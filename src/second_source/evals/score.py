"""Scores a system's findings against simulator ground truth.

Every labelled judgement is an item. A system that says nothing about an item
is taken to have called it `supported`. Findings on items that don't exist are
counted as spurious.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from typing import Any

from ..models import ContractLabel, Finding, LabelIssue

VERDICTS = ["supported", "misstated", "judgement_call", "insufficient_evidence"]
FLAGGED = {"misstated", "judgement_call", "insufficient_evidence"}
ESCALATE = {"judgement_call", "insufficient_evidence"}
CONCLUDE = {"supported", "misstated"}
ROUTINE = {"routine"}  # unremarkable supported items, left out of the scenario table


def _rate(num: int, den: int) -> float | None:
    return None if den == 0 else num / den


def _metrics(pairs: list[tuple[LabelIssue, Finding | None]]) -> dict[str, Any]:
    def verdict(f: Finding | None) -> str:
        return f.verdict if f else "supported"

    exp_flag = [(i, f) for i, f in pairs if i.expected_verdict in FLAGGED]
    exp_ok = [(i, f) for i, f in pairs if i.expected_verdict == "supported"]
    exp_mis = [(i, f) for i, f in pairs if i.expected_verdict == "misstated"]
    exp_esc = [(i, f) for i, f in pairs if i.expected_verdict in ESCALATE]
    exp_con = [(i, f) for i, f in pairs if i.expected_verdict in CONCLUDE]
    pred_mis = [(i, f) for i, f in pairs if verdict(f) == "misstated"]

    total_value = sum(abs(i.true_profit_effect) for i, _ in exp_flag)
    caught_value = sum(abs(i.true_profit_effect) for i, f in exp_flag if verdict(f) in FLAGGED)

    rel_errors = [abs(f.point_effect - i.true_profit_effect) / abs(i.true_profit_effect)
                  for i, f in exp_mis
                  if verdict(f) == "misstated" and f.profit_effect_low is not None
                  and i.true_profit_effect != 0]

    covered = 0
    ranged = 0
    for i, f in pairs:
        if i.expected_verdict in ESCALATE and verdict(f) in ESCALATE and f.profit_effect_low is not None:
            ranged += 1
            lo, hi = sorted([f.profit_effect_low, f.profit_effect_high or 0.0])
            tol = 0.01 * max(1.0, abs(i.true_profit_effect))
            covered += lo - tol <= i.true_profit_effect <= hi + tol

    return {
        "items": len(pairs),
        "verdict_accuracy": _rate(sum(verdict(f) == i.expected_verdict for i, f in pairs), len(pairs)),
        "catch_rate": _rate(sum(verdict(f) in FLAGGED for _, f in exp_flag), len(exp_flag)),
        "false_alarm_rate": _rate(sum(verdict(f) in FLAGGED for _, f in exp_ok), len(exp_ok)),
        "misstatement_precision": _rate(sum(i.expected_verdict == "misstated" for i, _ in pred_mis),
                                        len(pred_mis)),
        "misstatement_recall": _rate(sum(verdict(f) == "misstated" for _, f in exp_mis), len(exp_mis)),
        "under_escalation": _rate(sum(verdict(f) in CONCLUDE for _, f in exp_esc), len(exp_esc)),
        "over_escalation": _rate(sum(verdict(f) in ESCALATE for _, f in exp_con), len(exp_con)),
        "value_caught": _rate_f(caught_value, total_value),
        "quantification_error": None if not rel_errors else sum(rel_errors) / len(rel_errors),
        "range_coverage": _rate(covered, ranged),
    }


def _rate_f(num: float, den: float) -> float | None:
    return None if den == 0 else num / den


def score(labels: Iterable[ContractLabel], findings: Iterable[Finding]) -> dict[str, Any]:
    items = [i for lbl in labels for i in lbl.issues]
    keys = {i.key for i in items}
    preds: dict[tuple[str, str, str], Finding] = {}
    for f in findings:
        preds[f.key] = f
    pairs = [(i, preds.get(i.key)) for i in items]

    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    for i, f in pairs:
        confusion[i.expected_verdict][f.verdict if f else "supported"] += 1

    by_check = {chk: _metrics([(i, f) for i, f in pairs if i.check == chk])
                for chk in sorted({i.check for i in items})}
    by_scenario: dict[str, dict[str, int]] = defaultdict(lambda: {"right": 0, "total": 0})
    for i, f in pairs:
        if i.expected_verdict != "supported" or i.scenario not in ROUTINE:
            s = by_scenario[i.scenario]
            s["total"] += 1
            s["right"] += (f.verdict if f else "supported") == i.expected_verdict

    return {
        "overall": _metrics(pairs),
        "by_check": by_check,
        "by_scenario": dict(by_scenario),
        "confusion": {k: dict(v) for k, v in confusion.items()},
        "spurious_findings": sum(1 for k in preds if k not in keys),
    }


ROWS = [
    ("catch_rate", "Issues flagged (catch rate)"),
    ("value_caught", "Share of misstated £ flagged"),
    ("false_alarm_rate", "False alarms on clean items"),
    ("misstatement_precision", "Misstatement precision"),
    ("misstatement_recall", "Misstatement recall"),
    ("under_escalation", "Concluded when it should ask"),
    ("over_escalation", "Asked when it could conclude"),
    ("verdict_accuracy", "Verdict accuracy"),
    ("quantification_error", "Mean error on misstated £"),
    ("range_coverage", "Judgement ranges covering truth"),
]


def _fmt(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.0%}"


def markdown(results: dict[str, dict[str, Any]]) -> str:
    names = list(results)
    out = ["| Metric | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for key, label in ROWS:
        out.append(f"| {label} | " + " | ".join(_fmt(results[n]["overall"][key]) for n in names) + " |")
    out.append("")
    out.append("**Catch rate by check**")
    out.append("")
    checks = sorted({c for r in results.values() for c in r["by_check"]})
    out.append("| Check | " + " | ".join(names) + " |")
    out.append("|---|" + "---|" * len(names))
    for c in checks:
        out.append(f"| {c} | " + " | ".join(
            f"{_fmt(results[n]['by_check'][c]['catch_rate'])} caught, "
            f"{_fmt(results[n]['by_check'][c]['false_alarm_rate'])} false alarms" for n in names) + " |")
    out.append("")
    out.append("**Right verdict by seeded scenario**")
    out.append("")
    scenarios = sorted({s for r in results.values() for s in r["by_scenario"]})
    out.append("| Scenario | " + " | ".join(names) + " |")
    out.append("|---|" + "---|" * len(names))
    for s in scenarios:
        cells = []
        for n in names:
            d = results[n]["by_scenario"].get(s, {"right": 0, "total": 0})
            cells.append(f"{d['right']}/{d['total']}")
        out.append(f"| {s} | " + " | ".join(cells) + " |")
    return "\n".join(out) + "\n"
