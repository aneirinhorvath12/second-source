"""The committed portfolio is valid, and the checks catch the edits that would break scoring."""

import shutil
from pathlib import Path

import pytest
import yaml

from second_source import engine
from second_source.answers import best_estimate, compile_key, read_key
from second_source.portfolio import check_portfolio
from second_source.store import load_contract, read_cost_report

HARD = Path(__file__).resolve().parents[1] / "portfolios" / "hard"


def errors(root):
    return [p for p in check_portfolio(root) if p.level == "error"]


def test_committed_portfolio_has_no_errors():
    found = errors(HARD)
    assert not found, "\n".join(map(str, found))


@pytest.fixture
def one_contract(tmp_path):
    """A one-contract portfolio copied from the committed set, safe to break."""
    shutil.copytree(HARD / "contracts" / "C009", tmp_path / "contracts" / "C009")
    (tmp_path / "answers").mkdir()
    shutil.copy(HARD / "answers" / "C009.yaml", tmp_path / "answers" / "C009.yaml")
    return tmp_path


def edit_yaml(path, change):
    data = yaml.safe_load(path.read_text())
    change(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def test_copy_starts_clean(one_contract):
    assert errors(one_contract) == []


def test_missing_t1_judgement_is_an_error(one_contract):
    key = one_contract / "answers" / "C009.yaml"
    edit_yaml(key, lambda d: d["judgements"].pop(0))
    assert any("no T1 judgement for VO-001" in p.message for p in errors(one_contract))


def test_misstated_without_correction_is_an_error(one_contract):
    key = one_contract / "answers" / "C009.yaml"
    edit_yaml(key, lambda d: d["judgements"][1].pop("correction"))
    assert any("needs a correction" in p.message for p in errors(one_contract))


def test_price_mismatch_is_an_error(one_contract):
    report = one_contract / "contracts" / "C009" / "cost_report.yaml"
    edit_yaml(report, lambda d: d.update(contract_price=1))
    assert any("differs from terms.yaml" in p.message for p in errors(one_contract))


def test_unknown_variation_in_correction_is_an_error(one_contract):
    key = one_contract / "answers" / "C009.yaml"
    edit_yaml(key, lambda d: d["judgements"][1].update(correction={"variations": {"VO-999": 0}}))
    assert any("unknown variations" in p.message for p in errors(one_contract))


def test_effects_follow_edits_to_the_cost_report(one_contract):
    cdir = one_contract / "contracts" / "C009"
    key = read_key(one_contract / "answers" / "C009.yaml")

    def vo2_effect():
        label = compile_key(key, read_cost_report(cdir))
        return next(i for i in label.issues if i.ref == "VO-002").true_profit_effect

    before = vo2_effect()

    def halve_vo2(d):
        d["variations"][1]["amount"] /= 2

    edit_yaml(cdir / "cost_report.yaml", halve_vo2)
    assert vo2_effect() == pytest.approx(before / 2, rel=0.02)


def test_yaml_comments_never_reach_a_system(one_contract):
    report = one_contract / "contracts" / "C009" / "cost_report.yaml"
    report.write_text(report.read_text() + "# answer: VO-002 was rejected\n")
    cf = load_contract(one_contract / "contracts" / "C009")
    assert all("rejected" not in text for name, text in cf.sources().items() if name.endswith(".yaml"))


def test_m1_is_tested_on_the_corrected_numbers(one_contract):
    """C009's M1 effect is the provision its corrected numbers need, not management's own shortfall."""
    cdir = one_contract / "contracts" / "C009"
    cf = load_contract(cdir)
    key = read_key(one_contract / "answers" / "C009.yaml")
    m1 = next(i for i in compile_key(key, cf.report).issues if i.check == "M1")
    best = best_estimate(key).settled.apply(cf.report)
    assert m1.true_profit_effect == pytest.approx(cf.report.provision_booked
                                                  - engine.position(best).provision_required)
    assert m1.true_profit_effect < -cf.position().provision_shortfall


def test_m1_with_a_correction_of_its_own_is_an_error(one_contract):
    key = one_contract / "answers" / "C009.yaml"

    def give_m1_a_correction(d):
        next(j for j in d["judgements"] if j["check"] == "M1")["correction"] = {"etc": 1}

    edit_yaml(key, give_m1_a_correction)
    assert any("M1 takes no correction" in p.message for p in errors(one_contract))


def test_supported_m1_that_corrections_make_onerous_is_flagged(one_contract):
    key = one_contract / "answers" / "C009.yaml"

    def m1_supported(d):
        m1 = next(j for j in d["judgements"] if j["check"] == "M1")
        m1["verdict"] = "supported"

    edit_yaml(key, m1_supported)
    assert any("corrected numbers need" in p.message for p in check_portfolio(one_contract))
