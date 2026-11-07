import random
from dataclasses import replace
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


def test_removing_unaccepted_variation_moves_revenue_only_on_a_profitable_contract():
    reported = e.Inputs(contract_price=100, variations_in_tp=10, cost_to_date=40, etc=40)
    corrected = e.Inputs(contract_price=100, variations_in_tp=0, cost_to_date=40, etc=40)
    # POC = 0.5, so revenue to date falls by 0.5 x 10; still profitable, so no provision
    assert e.revenue_effect(reported, corrected) == pytest.approx(-5.0)
    assert e.provision_effect(reported, corrected) == 0.0


def test_understated_etc_that_tips_onerous_splits_between_revenue_and_provision():
    reported = e.Inputs(contract_price=100, cost_to_date=50, etc=40)  # EAC 90, margin 10
    corrected = e.Inputs(contract_price=100, cost_to_date=50, etc=60)  # EAC 110, loss 10
    # E2 owns revenue: 50/110 x 100 - 50/90 x 100
    assert e.revenue_effect(reported, corrected) == pytest.approx(5000 / 110 - 5000 / 90)
    # M1 owns the provision: (1 - 50/110) x 10, none booked
    assert e.provision_effect(reported, corrected) == pytest.approx(-(1 - 50 / 110) * 10)
    # together they move profit to the full expected loss
    assert e.profit_effect(reported, corrected) == pytest.approx(-10 - (5000 / 90 - 50))


def test_revenue_and_provision_effects_add_up_to_the_profit_change():
    rng = random.Random(11)
    for _ in range(500):
        rep = e.Inputs(contract_price=rng.uniform(50, 500), variations_in_tp=rng.uniform(0, 50),
                       cost_to_date=rng.uniform(1, 300), etc=rng.uniform(0, 300),
                       provision_booked=rng.uniform(0, 20))
        cor = e.Inputs(contract_price=rep.contract_price, variations_in_tp=rng.uniform(0, 50),
                       cost_to_date=rep.cost_to_date, etc=rng.uniform(0, 300),
                       provision_booked=rep.provision_booked)
        booked_profit = e.position(rep).profit_to_date
        true_profit = e.correct_profit_to_date(cor)
        assert e.profit_effect(rep, cor) == pytest.approx(true_profit - booked_profit)


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


def test_uninstalled_materials_follow_ifrs15_example_19():
    # IFRS 15 IE Example 19: price 5.0m, expected cost 4.0m including elevators of 1.5m.
    # Cost to date 2.0m includes the elevators, delivered but not installed.
    i = e.Inputs(contract_price=5_000_000, cost_to_date=2_000_000, etc=2_000_000,
                 uninstalled_materials=1_500_000)
    p = e.position(i)
    assert p.poc == pytest.approx(0.2)  # 0.5m of 2.5m, elevators excluded
    assert p.revenue_to_date == pytest.approx(2_200_000)  # 0.2 x 3.5m + 1.5m at zero margin
    # without the adjustment, progress is 50% and revenue 2.5m
    assert e.revenue_effect(replace(i, uninstalled_materials=0), i) == pytest.approx(-300_000)


def test_uninstalled_materials_cannot_exceed_cost_to_date():
    with pytest.raises(ValueError):
        e.position(e.Inputs(contract_price=10, cost_to_date=1, etc=1, uninstalled_materials=2))
