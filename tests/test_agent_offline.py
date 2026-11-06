"""The agent loop and tools, exercised with a scripted fake client (no API calls)."""

from types import SimpleNamespace

import pytest

from second_source.agent.investigator import investigate
from second_source.agent.tools import Toolbox
from second_source.simulator import write_portfolio
from second_source.store import load_labels, load_portfolio
from second_source.triggers import Candidate


@pytest.fixture(scope="module")
def portfolio(tmp_path_factory):
    root = tmp_path_factory.mktemp("p")
    write_portfolio(root, n=30, seed=0)
    contracts = {cf.contract_id: cf for cf in load_portfolio(root)}
    labels = {lbl.contract_id: lbl for lbl in load_labels(root)}
    return contracts, labels


def _find(portfolio, scenario):
    contracts, labels = portfolio
    lbl = next(lbl for lbl in labels.values() if lbl.scenario == scenario)
    return contracts[lbl.contract_id], lbl


def test_misstated_variation_effect_comes_from_engine(portfolio):
    cf, lbl = _find(portfolio, "t1_unaccepted")
    issue = next(i for i in lbl.issues if i.check == "T1" and i.expected_verdict == "misstated")
    vo = next(v for v in cf.report.variations if v.id == issue.ref)
    letter = cf.docs[f"letter_{vo.id}.md"]
    quote = next(line for line in letter.splitlines() if "reject" in line or "not instructed" in line)
    box = Toolbox(cf, "T1", vo.id)
    msg, finding = box.call("record_finding", {
        "verdict": "misstated", "confidence": 0.9, "rationale": "Customer has not accepted.",
        "low_case": {"variations_in_tp": cf.inputs().variations_in_tp - vo.amount},
        "evidence": [{"doc_id": f"letter_{vo.id}.md", "quote": quote[:60]}],
    })
    assert finding is not None, msg
    assert finding.profit_effect_low == pytest.approx(issue.true_profit_effect)


def test_fabricated_quote_is_bounced_back(portfolio):
    cf, _ = _find(portfolio, "clean")
    box = Toolbox(cf, "E2", "ETC")
    msg, finding = box.call("record_finding", {
        "verdict": "supported", "confidence": 0.8, "rationale": "x",
        "evidence": [{"doc_id": "contract.md", "quote": "the employer guarantees our margin"}],
    })
    assert finding is None
    assert "not found verbatim" in msg


def test_m1_effect_is_the_engine_shortfall(portfolio):
    cf, lbl = _find(portfolio, "m1_no_provision")
    issue = next(i for i in lbl.issues if i.check == "M1")
    box = Toolbox(cf, "M1", "PROVISION")
    _, finding = box.call("record_finding", {
        "verdict": "misstated", "confidence": 0.9, "rationale": "Own EAC exceeds TP.", "evidence": [],
    })
    assert finding.profit_effect_low == pytest.approx(issue.true_profit_effect)


def test_bad_override_returns_a_recoverable_error(portfolio):
    cf, _ = _find(portfolio, "clean")
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


def test_investigate_loop_reads_then_records(portfolio):
    cf, lbl = _find(portfolio, "t1_no_evidence")
    issue = next(i for i in lbl.issues if i.expected_verdict == "insufficient_evidence")
    client = FakeClient([
        [tool_use(1, "search_documents", {"query": issue.ref})],
        [tool_use(2, "record_finding", {
            "verdict": "insufficient_evidence", "confidence": 0.7,
            "rationale": "Register says approved but there is no customer agreement on file.",
            "document_request": f"Customer written agreement to {issue.ref}",
            "evidence": [{"doc_id": "variation_register.md", "quote": issue.ref}],
        })],
    ])
    finding = investigate(cf, Candidate(cf.contract_id, "T1", issue.ref, "test"), client=client)
    assert finding.verdict == "insufficient_evidence"
    assert finding.document_request


def test_investigate_budget_exhaustion_never_guesses(portfolio):
    cf, _ = _find(portfolio, "clean")
    client = FakeClient([[tool_use(i, "list_documents", {})] for i in range(3)])
    finding = investigate(cf, Candidate(cf.contract_id, "E2", "ETC", "test"), client=client,
                          max_turns=3)
    assert finding.verdict == "insufficient_evidence"
    assert finding.confidence == 0.0
