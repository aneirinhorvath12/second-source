"""The agent loop and tools, exercised with a scripted fake client (no API calls)."""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from second_source.agent.investigator import investigate
from second_source.agent.tools import Toolbox
from second_source.answers import best_estimate, read_key
from second_source.store import load_contract, load_labels
from second_source.triggers import Candidate

HARD = Path(__file__).resolve().parents[1] / "portfolios" / "hard"


@pytest.fixture(scope="module")
def labels():
    return {lbl.contract_id: lbl for lbl in load_labels(HARD)}


def _find(labels, tag):
    """The first contract whose answer key has a judgement with this tag, and that judgement."""
    lbl = next(lbl for lbl in labels.values() if any(i.scenario == tag for i in lbl.issues))
    issue = next(i for i in lbl.issues if i.scenario == tag)
    return load_contract(HARD / "contracts" / lbl.contract_id), issue


def test_misstated_variation_effect_comes_from_engine(labels):
    cf, issue = _find(labels, "t1_rejected_oblique")
    vo = next(v for v in cf.report.variations if v.id == issue.ref)
    doc = re.search(r"\S+\.md", issue.note).group(0)  # the answer key names the letter that settles it
    quote = next(line for line in cf.docs[doc].splitlines() if "clause 2.3" in line)
    box = Toolbox(cf, "T1", vo.id)
    msg, finding = box.call("record_finding", {
        "verdict": "misstated", "confidence": 0.9, "rationale": "Customer says it is our design.",
        "low_case": {"variations_in_tp": cf.inputs().variations_in_tp - vo.amount},
        "evidence": [{"doc_id": doc, "quote": quote.strip()[:60]}],
    })
    assert finding is not None, msg
    assert finding.evidence, "the quote should verify"
    assert finding.profit_effect_low == pytest.approx(issue.true_profit_effect)


def test_fabricated_quote_is_bounced_back(labels):
    cf = load_contract(HARD / "contracts" / "C001")
    box = Toolbox(cf, "E2", "ETC")
    msg, finding = box.call("record_finding", {
        "verdict": "supported", "confidence": 0.8, "rationale": "x",
        "evidence": [{"doc_id": "contract.md", "quote": "the employer guarantees our margin"}],
    })
    assert finding is None
    assert "not found verbatim" in msg


def test_m1_effect_is_the_provision_on_the_best_estimate(labels):
    cf, issue = _find(labels, "m1_no_provision")
    best = best_estimate(read_key(HARD / "answers" / f"{cf.contract_id}.yaml")).settled.apply(cf.report)
    box = Toolbox(cf, "M1", "PROVISION")
    _, finding = box.call("record_finding", {
        "verdict": "misstated", "confidence": 0.9, "rationale": "Onerous once corrected.", "evidence": [],
        "low_case": {"variations_in_tp": best.variations_in_tp, "etc": best.etc},
    })
    assert finding.profit_effect_low == pytest.approx(issue.true_profit_effect)


def test_m1_with_no_case_tests_managements_own_numbers(labels):
    cf, _ = _find(labels, "m1_no_provision")
    _, finding = Toolbox(cf, "M1", "PROVISION").call("record_finding", {
        "verdict": "misstated", "confidence": 0.9, "rationale": "Own EAC exceeds TP.", "evidence": [],
    })
    assert finding.profit_effect_low == pytest.approx(-cf.position().provision_shortfall)


def test_bad_override_returns_a_recoverable_error():
    cf = load_contract(HARD / "contracts" / "C001")
    msg, finding = Toolbox(cf, "E2", "ETC").call("run_scenario", {"overrides": {"price": 1}})
    assert finding is None and msg.startswith("Error")


class FakeClient:
    """Plays back a fixed sequence of assistant turns."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.messages = self

    def create(self, **_):
        content = self.turns.pop(0)
        return SimpleNamespace(content=content, usage=SimpleNamespace(input_tokens=10, output_tokens=5))


def tool_use(i, name, args):
    return SimpleNamespace(type="tool_use", id=f"t{i}", name=name, input=args)


def test_investigate_loop_reads_then_records(labels):
    cf, issue = _find(labels, "t1_no_response")
    client = FakeClient([
        [tool_use(1, "search_documents", {"query": issue.ref})],
        [tool_use(2, "record_finding", {
            "verdict": "insufficient_evidence", "confidence": 0.7,
            "rationale": "Quotation still under review; no acceptance on file.",
            "document_request": f"The ER's written acceptance for {issue.ref}",
            "evidence": [{"doc_id": "cost_report.yaml", "quote": issue.ref}],
        })],
    ])
    finding = investigate(cf, Candidate(cf.contract_id, "T1", issue.ref, "test"), client=client)
    assert finding.verdict == "insufficient_evidence"
    assert finding.document_request


def test_investigate_budget_exhaustion_never_guesses():
    cf = load_contract(HARD / "contracts" / "C001")
    client = FakeClient([[tool_use(i, "list_documents", {})] for i in range(3)])
    finding = investigate(cf, Candidate(cf.contract_id, "E2", "ETC", "test"), client=client,
                          max_turns=3)
    assert finding.verdict == "insufficient_evidence"
    assert finding.confidence == 0.0
