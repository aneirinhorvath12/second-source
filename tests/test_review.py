"""The controller review runner, with a fake client (no API calls)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from second_source.review import build_request, cost_usd, parse_figures, review

HARD = Path(__file__).resolve().parents[1] / "portfolios" / "hard"

ANSWER = """## Figures
...
```json
{"transaction_price": 148300000, "etc": 120750000, "revenue_to_date": 30962000,
 "provision": 3412000, "confidence": 70}
```"""


class FakeClient:
    def __init__(self):
        self.calls = 0
        self.messages = self

    def create(self, **kwargs):
        self.calls += 1
        usage = SimpleNamespace(input_tokens=50, cache_creation_input_tokens=0 if self.calls > 1 else 130_000,
                                cache_read_input_tokens=130_000 if self.calls > 1 else 0, output_tokens=4_000)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=ANSWER)], usage=usage,
                               stop_reason="end_turn")


def test_haiku_charges_the_higher_tier_over_100k_prompt_tokens():
    assert cost_usd("claude-haiku-5-5", 90_000, 0, 0, 0) == pytest.approx(0.009)
    assert cost_usd("claude-haiku-5-5", 0, 0, 130_000, 0) == pytest.approx(130_000 * 0.05 / 1e6)


def test_request_caches_the_documents_and_never_includes_the_answer_key():
    req = build_request(HARD / "contracts" / "C021", "claude-haiku-5-5")
    docs, ask = req.messages[0]["content"]
    assert docs["cache_control"] == {"type": "ephemeral"}
    assert "Answer key" not in docs["text"] and "answers/" not in docs["text"]
    assert "Review contract C021" in ask["text"]


def test_repeat_runs_are_skipped_when_nothing_changed(tmp_path):
    client = FakeClient()
    cdirs = [HARD / "contracts" / "C021"]
    first = review(cdirs, tmp_path, runs=2, client=client)
    assert len(first) == 2 and client.calls == 2
    assert first[0]["figures"]["confidence"] == 70
    again = review(cdirs, tmp_path, runs=2, client=client)
    assert again == [] and client.calls == 2
    logged = [json.loads(x) for x in (tmp_path / "calls.jsonl").read_text().splitlines()]
    assert [r["run"] for r in logged] == [1, 2]


def test_parse_figures_takes_the_last_json_block():
    assert parse_figures("no block") is None
    assert parse_figures(ANSWER)["provision"] == 3412000
