"""The investigator agent: one sub-agent per candidate issue, fresh context each time.

Triggers raise candidates; each candidate gets its own short-lived conversation
with the check's guidance, the tools in `tools.py`, and a budget. The agent must
finish by calling record_finding; running out of budget yields
insufficient_evidence, never a guess.
"""

from __future__ import annotations

import os
from typing import Any

from ..models import Finding
from ..store import ContractFile
from ..triggers import Candidate, candidates
from .guidance import CHECKS, SYSTEM_PROMPT
from .tools import DEFINITIONS, Toolbox
from .usage import USAGE

DEFAULT_MODEL = os.environ.get("SECOND_SOURCE_MODEL", "claude-sonnet-5-5")
MAX_TURNS = int(os.environ.get("SECOND_SOURCE_MAX_TURNS", "12"))


def _client() -> Any:
    try:
        import anthropic
    except ImportError as err:  # pragma: no cover
        raise SystemExit("Install the agent extra: uv sync --extra agent") from err
    return anthropic.Anthropic()


def brief(cf: ContractFile, cand: Candidate) -> str:
    t = cf.terms
    return (
        f"Contract {cf.contract_id}: {t.name} for {t.customer}. Period end {cf.report.period_end}.\n"
        f"Candidate: check {cand.check}, ref {cand.ref}.\n"
        f"Why it was raised: {cand.reason}\n"
        "Investigate using the tools, then call record_finding."
    )


def _cache_tail(messages: list[dict[str, Any]]) -> None:
    """Move the one rolling cache breakpoint to the end of the conversation.

    Each turn re-sends everything before it, so caching the prefix makes long
    investigations roughly ten times cheaper without changing what the model sees.
    """
    for m in messages:
        if isinstance(m["content"], list):
            for b in m["content"]:
                if isinstance(b, dict):
                    b.pop("cache_control", None)
    last = messages[-1]
    if isinstance(last["content"], str):
        last["content"] = [{"type": "text", "text": last["content"]}]
    block = last["content"][-1]
    if isinstance(block, dict):
        block["cache_control"] = {"type": "ephemeral"}


def investigate(cf: ContractFile, cand: Candidate, client: Any = None,
                model: str = DEFAULT_MODEL, max_turns: int = MAX_TURNS) -> Finding:
    client = client or _client()
    box = Toolbox(cf, cand.check, cand.ref)
    system = [
        {"type": "text", "text": SYSTEM_PROMPT},
        {"type": "text", "text": CHECKS[cand.check], "cache_control": {"type": "ephemeral"}},
    ]
    messages: list[dict[str, Any]] = [{"role": "user", "content": brief(cf, cand)}]

    for _ in range(max_turns):
        _cache_tail(messages)
        resp = client.messages.create(model=model, max_tokens=2048, system=system,
                                      tools=DEFINITIONS, messages=messages)
        USAGE.add(model, resp.usage)
        messages.append({"role": "assistant", "content": resp.content})
        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        if not tool_uses:
            messages.append({"role": "user", "content": "Record your conclusion with record_finding."})
            continue
        results = []
        for tu in tool_uses:
            text, finding = box.call(tu.name, dict(tu.input))
            if finding is not None:
                return finding
            results.append({"type": "tool_result", "tool_use_id": tu.id, "content": text})
        messages.append({"role": "user", "content": results})

    return Finding(contract_id=cf.contract_id, check=cand.check, ref=cand.ref,
                   verdict="insufficient_evidence", confidence=0.0,
                   rationale=f"Investigation budget of {max_turns} turns exhausted without a finding.")


def agent_system(cf: ContractFile) -> list[Finding]:
    client = _client()
    return [investigate(cf, c, client) for c in candidates(cf)]
