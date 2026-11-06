"""MCP server exposing the read and scenario tools over a portfolio.

Lets a controller question a contract from Claude ("why is C011 flagged?",
"what if VO-002 settles at the customer's figure?"). Write tools stay inside
the pipeline.

    uv sync --extra mcp
    SECOND_SOURCE_PORTFOLIO=portfolios/hard uv run python -m second_source.mcp_server
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import engine
from .agent.tools import OVERRIDABLE
from .store import ContractFile, load_portfolio
from .triggers import candidates, schedule_numbers

server = FastMCP("second-source")


@lru_cache(maxsize=1)
def _portfolio() -> dict[str, ContractFile]:
    root = Path(os.environ.get("SECOND_SOURCE_PORTFOLIO", "portfolios/hard"))
    return {cf.contract_id: cf for cf in load_portfolio(root)}


def _get(contract_id: str) -> ContractFile:
    try:
        return _portfolio()[contract_id]
    except KeyError as err:
        raise ValueError(f"Unknown contract {contract_id}; known: {sorted(_portfolio())}") from err


@server.tool()
def list_contracts() -> str:
    """List contracts with reported margin and the candidate issues raised on each."""
    rows = []
    for cid, cf in _portfolio().items():
        p = cf.position()
        rows.append({"contract": cid, "name": cf.terms.name, "margin_pct": round(p.margin_pct, 4),
                     "candidates": [f"{c.check}:{c.ref}" for c in candidates(cf)]})
    return json.dumps(rows, indent=2)


@server.tool()
def get_position(contract_id: str) -> str:
    """Management's reported position for a contract, computed by the engine."""
    return json.dumps(asdict(_get(contract_id).position()), indent=2)


@server.tool()
def get_schedule_metrics(contract_id: str) -> str:
    """Earned value, progress gap, slip and LD exposure from the P6 schedule."""
    return json.dumps(schedule_numbers(_get(contract_id)), indent=2)


@server.tool()
def run_scenario(contract_id: str, overrides: dict[str, float]) -> str:
    """Recompute a contract's position with inputs changed (variations_in_tp, claims_in_tp,
    ld_deduction, etc) and return the effect on cumulative profit to date."""
    bad = set(overrides) - set(OVERRIDABLE)
    if bad:
        raise ValueError(f"Cannot override {sorted(bad)}; allowed: {OVERRIDABLE}")
    cf = _get(contract_id)
    rep = cf.inputs()
    corrected = engine.Inputs(**{**asdict(rep), **{k: float(v) for k, v in overrides.items()}})
    return json.dumps({"position": asdict(engine.position(corrected)),
                       "profit_effect_vs_reported": engine.profit_effect(rep, corrected)}, indent=2)


@server.tool()
def read_document(contract_id: str, name: str) -> str:
    """Read one file from a contract: a document, terms.yaml, cost_report.yaml or schedule.xer."""
    sources = _get(contract_id).sources()
    if name not in sources:
        raise ValueError(f"No file '{name}'; available: {sorted(sources)}")
    return sources[name]


if __name__ == "__main__":
    server.run()
