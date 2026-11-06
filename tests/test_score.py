import pytest

from second_source.evals import markdown, score
from second_source.models import ContractLabel, Finding, LabelIssue


def label(*issues):
    return ContractLabel(contract_id="C001", scenario="x", true_etc=0, true_cpi=1, true_spi=1,
                         issues=list(issues))


def issue(check, ref, verdict, effect=0.0, rng=None, scenario="s"):
    return LabelIssue(contract_id="C001", check=check, ref=ref, expected_verdict=verdict,
                      true_profit_effect=effect, effect_range=rng, scenario=scenario)


def finding(check, ref, verdict, lo=None, hi=None):
    return Finding(contract_id="C001", check=check, ref=ref, verdict=verdict,
                   profit_effect_low=lo, profit_effect_high=hi)


LABELS = [label(
    issue("T1", "VO-001", "misstated", -100.0),
    issue("T1", "VO-002", "supported", scenario="t1_approved"),
    issue("E2", "ETC", "judgement_call", -50.0, (-50.0, 0.0)),
    issue("M1", "PROVISION", "supported", scenario="m1_ok"),
)]


def test_silence_counts_as_supported():
    r = score(LABELS, [])["overall"]
    assert r["catch_rate"] == 0.0
    assert r["false_alarm_rate"] == 0.0
    assert r["under_escalation"] == 1.0
    assert r["verdict_accuracy"] == pytest.approx(0.5)


def test_perfect_system():
    findings = [finding("T1", "VO-001", "misstated", -100, -100),
                finding("E2", "ETC", "judgement_call", -60, 0)]
    r = score(LABELS, findings)["overall"]
    assert r["verdict_accuracy"] == 1.0
    assert r["catch_rate"] == 1.0
    assert r["value_caught"] == 1.0
    assert r["quantification_error"] == 0.0
    assert r["range_coverage"] == 1.0
    assert r["under_escalation"] == 0.0


def test_overconfident_system_is_caught_out():
    findings = [finding("T1", "VO-001", "misstated", -80, -80),
                finding("E2", "ETC", "misstated", -50, -50),
                finding("M1", "PROVISION", "misstated", -10, -10),
                finding("T1", "VO-999", "misstated", -1, -1)]
    s = score(LABELS, findings)
    r = s["overall"]
    assert r["catch_rate"] == 1.0
    assert r["false_alarm_rate"] == pytest.approx(0.5)
    assert r["under_escalation"] == 1.0
    assert r["misstatement_precision"] == pytest.approx(1 / 3)
    assert r["quantification_error"] == pytest.approx(0.2)
    assert s["spurious_findings"] == 1


def test_markdown_renders_every_system():
    md = markdown({"a": score(LABELS, []), "b": score(LABELS, [])})
    assert "| Metric | a | b |" in md
    assert "Catch rate by check" in md
