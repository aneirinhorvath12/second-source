import json

from second_source import engine, xer
from second_source.simulator import generate, write_portfolio
from second_source.simulator.generate import SCENARIO_WEIGHTS


def test_generation_is_deterministic():
    a = generate(12, seed=3)
    b = generate(12, seed=3)
    assert [c.report.model_dump() for c in a] == [c.report.model_dump() for c in b]
    assert [c.label.model_dump() for c in a] == [c.label.model_dump() for c in b]


def test_scenario_mix_matches_weights_for_30():
    scenarios = [c.label.scenario for c in generate(30, seed=0)]
    for s, w in SCENARIO_WEIGHTS.items():
        assert scenarios.count(s) == w


def test_every_contract_is_labelled_on_every_judgement():
    for c in generate(30, seed=1):
        keys = {(i.check, i.ref) for i in c.label.issues}
        assert ("E2", "ETC") in keys
        assert ("M1", "PROVISION") in keys
        included = {v.id for v in c.report.variations if v.included_in_tp}
        assert {ref for chk, ref in keys if chk == "T1"} == included


def test_misstatements_overstate_profit():
    for c in generate(30, seed=2):
        for i in c.label.issues:
            if i.expected_verdict == "misstated":
                assert i.true_profit_effect < 0, (c.label.scenario, i)


def test_m1_label_matches_managements_own_numbers():
    for c in generate(30, seed=4):
        p = engine.position(c.report.inputs())
        m1 = next(i for i in c.label.issues if i.check == "M1")
        if m1.expected_verdict == "misstated":
            assert p.provision_shortfall > 0
        else:
            assert p.provision_shortfall < 1_000  # rounding only


def test_understated_etc_is_visible_in_earned_value():
    for c in generate(30, seed=5):
        if c.label.scenario != "e2_etc_understated":
            continue
        m = xer.metrics(c.xer_tables)
        evm = engine.earned_value(m.bac, m.ev, m.pv, c.report.cost_to_date)
        mgmt_eac = c.report.cost_to_date + c.report.etc
        assert engine.eac_divergence(evm.eac_evm, mgmt_eac) > 0.02


def test_portfolio_keeps_labels_out_of_contract_folders(tmp_path):
    write_portfolio(tmp_path, n=6, seed=0)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert len(manifest["contracts"]) == 6
    for cid in manifest["contracts"]:
        cdir = tmp_path / "contracts" / cid
        assert (cdir / "schedule.xer").exists()
        assert (cdir / "docs" / "contract.md").exists()
        assert not any("label" in p.name for p in cdir.rglob("*"))
        assert (tmp_path / "labels" / f"{cid}.json").exists()


def test_withheld_documents_are_really_withheld(tmp_path):
    write_portfolio(tmp_path, n=30, seed=0)
    for c in generate(30, seed=0):
        for i in c.label.issues:
            if i.expected_verdict == "insufficient_evidence":
                docs = tmp_path / "contracts" / c.terms.contract_id / "docs"
                assert not (docs / f"letter_{i.ref}.md").exists()


def test_one_off_overruns_look_bad_on_evm_but_are_supported():
    seen = 0
    for c in generate(30, seed=6):
        if c.label.scenario != "e2_one_off_overrun":
            continue
        seen += 1
        m = xer.metrics(c.xer_tables)
        evm = engine.earned_value(m.bac, m.ev, m.pv, c.report.cost_to_date)
        mgmt_eac = c.report.cost_to_date + c.report.etc
        assert engine.eac_divergence(evm.eac_evm, mgmt_eac) > 0.05
        e2 = next(i for i in c.label.issues if i.check == "E2")
        assert e2.expected_verdict == "supported"
    assert seen == 2
