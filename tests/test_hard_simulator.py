"""The hard generator's planning and validation, without calling a model."""

from pathlib import Path

import pytest

from second_source.answers import compile_key
from second_source.portfolio import check_portfolio
from second_source.simulator.hard.build import plan_portfolio
from second_source.simulator.hard.writer import amounts, check_text

HARD = Path(__file__).resolve().parents[1] / "portfolios" / "hard"


@pytest.fixture(scope="module")
def plans():
    return plan_portfolio(6, seed=3)


def test_every_variation_in_tp_has_one_judgement(plans):
    for p in plans:
        in_tp = {v.id for v in p.report.variations if v.included_in_tp}
        t1 = [j.ref for j in p.answers.judgements if j.check == "T1"]
        assert sorted(t1) == sorted(in_tp)
        assert [j.check for j in p.answers.judgements].count("E2") == 1


def test_answer_keys_compile_and_misstatements_move_profit(plans):
    for p in plans:
        label = compile_key(p.answers, p.report)
        for issue in label.issues:
            if issue.expected_verdict == "misstated":
                assert abs(issue.true_profit_effect) > 1, (p.world.cid, issue.ref, issue.scenario)


def test_etc_breakdown_sums_to_etc(plans):
    for p in plans:
        assert sum(e.amount for e in p.report.etc_breakdown) == pytest.approx(p.report.etc, abs=1)


def test_files_are_large_and_names_unique(plans):
    for p in plans:
        names = list(p.docs) + [s.name for s in p.specs]
        assert len(names) == len(set(names))
        assert sum(len(t) for t in p.docs.values()) > 150_000


def test_ledger_matches_cost_to_date(plans):
    for p in plans:
        assert sum(float(r["amount"]) for r in p.ledger) == pytest.approx(p.report.cost_to_date, abs=1)


def test_money_parsing():
    assert amounts("£1,253,000 and £2.5m and £40k") == [1_253_000, 2_500_000, 40_000]


def test_validator_catches_missing_banned_and_invented_money():
    errs = check_text(
        "We accept the quotation for £1,250,000. Under IFRS 15 this is fine.",
        must=["BRK/X/Q/001"],
        must_not=["reject"],
        money_ok=[1_253_000],
        min_words=1,
    )
    joined = " ".join(errs)
    assert "BRK/X/Q/001" in joined and "IFRS" in joined and "£1,250,000" in joined


@pytest.mark.skipif(not (HARD / "contracts").exists(), reason="hard portfolio not generated")
def test_committed_hard_portfolio_has_no_errors():
    found = [p for p in check_portfolio(HARD) if p.level == "error"]
    assert not found, "\n".join(map(str, found))
