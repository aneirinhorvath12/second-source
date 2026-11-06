import random
from datetime import date

import pytest

from second_source import engine as e


def test_profitable_contract_position():
    p = e.position(e.Inputs(contract_price=100.0, cost_to_date=45.0, etc=45.0))
    assert p.tp == 100.0
    assert p.eac == 90.0
    assert p.poc == pytest.approx(0.5)
    assert p.revenue_to_date == pytest.approx(50.0)
    assert p.lifetime_margin == pytest.approx(10.0)
    assert p.provision_required == 0.0
    assert p.profit_to_date == pytest.approx(5.0)


def test_onerous_contract_books_full_loss_now():
    i = e.Inputs(contract_price=100.0, cost_to_date=60.0, etc=60.0)
    p = e.position(i)
    assert p.expected_loss == pytest.approx(20.0)
    assert p.provision_required == pytest.approx(10.0)
    # with the provision booked, cumulative profit is the whole expected loss
    assert e.correct_profit_to_date(i) == pytest.approx(-20.0)
    # without it, only POC x L has been recognised
    assert p.profit_to_date == pytest.approx(-10.0)
    assert p.provision_shortfall == pytest.approx(10.0)


def test_full_loss_identity_holds_across_random_contracts():
    rng = random.Random(7)
    for _ in range(500):
        price = rng.uniform(1, 500)
        c = rng.uniform(0.1, 400)
        etc = rng.uniform(0, 400)
        i = e.Inputs(contract_price=price, cost_to_date=c, etc=etc)
        p = e.position(i)
        assert 0.0 <= p.poc <= 1.0
        assert p.provision_required >= 0.0
        if p.expected_loss > 0:
            assert e.correct_profit_to_date(i) == pytest.approx(-p.expected_loss)


def test_transaction_price_components():
    i = e.Inputs(contract_price=100, variations_in_tp=12, claims_in_tp=5, ld_deduction=3)
    assert e.transaction_price(i) == 114


def test_scenario_rejects_unknown_inputs():
    with pytest.raises(ValueError):
        e.scenario(e.Inputs(contract_price=1), etcc=5)


def test_profit_effect_of_removing_unaccepted_variation():
    reported = e.Inputs(contract_price=100, variations_in_tp=10, cost_to_date=40, etc=40)
    corrected = e.Inputs(contract_price=100, variations_in_tp=0, cost_to_date=40, etc=40)
    # POC = 0.5, so revenue to date falls by 0.5 x 10
    assert e.profit_effect(reported, corrected) == pytest.approx(-5.0)


def test_profit_effect_of_understated_etc_that_tips_onerous():
    reported = e.Inputs(contract_price=100, cost_to_date=50, etc=40)  # EAC 90, margin 10
    corrected = e.Inputs(contract_price=100, cost_to_date=50, etc=60)  # EAC 110, loss 10
    # reported profit = 50/90*100 - 50 = 5.56; corrected = -10 (full loss)
    assert e.profit_effect(reported, corrected) == pytest.approx(-10 - (5000 / 90 - 50))


def test_earned_value():
    ev = e.earned_value(bac=100, ev=40, pv=50, ac=50)
    assert ev.cpi == pytest.approx(0.8)
    assert ev.spi == pytest.approx(0.8)
    assert ev.eac_evm == pytest.approx(50 + 60 / 0.8)
    assert ev.physical_pct == pytest.approx(0.4)


def test_divergence_and_gap_signs():
    assert e.eac_divergence(eac_evm=125, eac_management=100) == pytest.approx(0.25)
    assert e.progress_gap(poc=0.55, physical_pct=0.40) == pytest.approx(0.15)


def test_ld_exposure_capped_and_net_of_eot():
    assert e.days_late(date(2027, 3, 31), date(2027, 3, 1), eot_days=10) == 20
    assert e.ld_exposure(1000, 50_000, date(2027, 3, 31), date(2027, 3, 1)) == 30_000
    assert e.ld_exposure(1000, 10_000, date(2027, 3, 31), date(2027, 3, 1)) == 10_000
    assert e.ld_exposure(1000, 10_000, date(2027, 2, 1), date(2027, 3, 1)) == 0
