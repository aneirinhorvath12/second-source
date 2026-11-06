"""Tools the investigator agent can call, over one contract file.

Design choices that matter for the evals:
- Errors tell the model what to do next instead of failing silently.
- The model never supplies numbers for effects. It supplies input overrides and
  the engine computes the effect, so arithmetic can't leak into findings.
- Citations are verified: a quote must appear in the cited document.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, replace
from typing import Any

from .. import engine
from ..models import Citation, Finding
from ..store import ContractFile
from ..triggers import schedule_numbers

OVERRIDABLE = ["variations_in_tp", "claims_in_tp", "ld_deduction", "etc"]

_OVERRIDES_SCHEMA = {
    "type": "object",
    "description": "Inputs to change, e.g. {\"variations_in_tp\": 1200000} or {\"etc\": 54000000}. "
                   "Omitted inputs keep management's reported values.",
    "properties": {k: {"type": "number"} for k in OVERRIDABLE},
    "additionalProperties": False,
}

DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "list_documents",
        "description": "List the documents in this contract's file.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "read_document",
        "description": "Read one document in full. Also accepts 'cost_report.json' and 'schedule.xer'.",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "search_documents",
        "description": "Case-insensitive search across all documents. Returns matching lines with "
                       "their document names. Use short terms; references may be written "
                       "inconsistently (e.g. 'VO-002' vs 'VO 2').",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "get_position",
        "description": "Management's reported position computed by the engine: TP, EAC, POC, "
                       "revenue to date, margin, expected loss, provision required and booked.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_schedule_metrics",
        "description": "Earned value from the P6 schedule: BAC, EV, PV, CPI, SPI, EVM EAC, divergence "
                       "from management's EAC, physical progress, progress gap, slip and LD exposure.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_scenario",
        "description": "Recompute the position with some inputs changed. Returns the new position "
                       "and the effect on cumulative profit to date versus management's numbers.",
        "input_schema": {
            "type": "object",
            "properties": {"overrides": _OVERRIDES_SCHEMA},
            "required": ["overrides"],
        },
    },
    {
        "name": "record_finding",
        "description": "Record your one finding and finish. For misstated, give low_case as the "
                       "corrected inputs. For judgement_call, give low_case (least favourable "
                       "supportable inputs) and high_case (most favourable; {} means as reported). "
                       "For M1 the engine computes the provision shortfall itself.",
        "input_schema": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["supported", "misstated", "judgement_call",
                                                       "insufficient_evidence"]},
                "low_case": _OVERRIDES_SCHEMA,
                "high_case": _OVERRIDES_SCHEMA,
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "evidence": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"doc_id": {"type": "string"}, "quote": {"type": "string"}},
                        "required": ["doc_id", "quote"],
                    },
                },
                "question": {"type": "string", "description": "For judgement_call: the question "
                                                              "and who should answer it."},
                "document_request": {"type": "string", "description": "For insufficient_evidence: "
                                                                      "the document that would settle it."},
                "rationale": {"type": "string"},
            },
            "required": ["verdict", "confidence", "evidence", "rationale"],
        },
    },
]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("*", "")).strip().lower()


class Toolbox:
    def __init__(self, cf: ContractFile, check: str, ref: str, max_citation_retries: int = 2):
        self.cf, self.check, self.ref = cf, check, ref
        self.citation_failures = 0
        self.max_citation_retries = max_citation_retries
        self.sources = dict(cf.docs)
        self.sources["cost_report.json"] = cf.report.model_dump_json(indent=2)
        self.sources["schedule.xer"] = cf.schedule_text

    # -- dispatch -------------------------------------------------------------
    def call(self, name: str, args: dict[str, Any]) -> tuple[str, Finding | None]:
        try:
            if name == "record_finding":
                return self._record(args)
            handler = getattr(self, f"_{name}", None)
            if handler is None:
                return f"Unknown tool '{name}'.", None
            return handler(**args), None
        except (TypeError, ValueError) as err:
            return f"Error: {err}. Check the arguments against the tool schema and retry.", None

    # -- read tools -----------------------------------------------------------
    def _list_documents(self) -> str:
        return "\n".join(self.sources)

    def _read_document(self, name: str) -> str:
        if name in self.sources:
            return self.sources[name]
        close = [d for d in self.sources if name.lower().split(".")[0] in d.lower()]
        hint = f" Did you mean: {', '.join(close)}?" if close else " Use list_documents."
        return f"No document named '{name}'.{hint}"

    def _search_documents(self, query: str) -> str:
        q = query.lower()
        hits = [f"{doc}: {line.strip()}" for doc, text in self.cf.docs.items()
                for line in text.splitlines() if q in line.lower()]
        if not hits:
            return (f"No lines match '{query}'. Try a shorter term or another spelling "
                    "of the reference.")
        return "\n".join(hits[:40])

    def _get_position(self) -> str:
        return json.dumps(asdict(self.cf.position()), indent=2)

    def _get_schedule_metrics(self) -> str:
        n = schedule_numbers(self.cf)
        n["bac"], n["ev"], n["pv"] = self.cf.schedule.bac, self.cf.schedule.ev, self.cf.schedule.pv
        return json.dumps({k: round(v, 4) for k, v in n.items()}, indent=2)

    def _run_scenario(self, overrides: dict[str, float]) -> str:
        rep = self.cf.inputs()
        corrected = self._apply(rep, overrides)
        return json.dumps({"position": asdict(engine.position(corrected)),
                           "profit_effect_vs_reported": engine.profit_effect(rep, corrected)},
                          indent=2)

    # -- record -----------------------------------------------------------------
    def _apply(self, rep: engine.Inputs, overrides: dict[str, float] | None) -> engine.Inputs:
        overrides = overrides or {}
        bad = set(overrides) - set(OVERRIDABLE)
        if bad:
            raise ValueError(f"cannot override {sorted(bad)}; allowed: {OVERRIDABLE}")
        return replace(rep, **{k: float(v) for k, v in overrides.items()})

    def _effect(self, case: dict[str, float] | None) -> float:
        rep = self.cf.inputs()
        return engine.profit_effect(rep, self._apply(rep, case))

    def _record(self, args: dict[str, Any]) -> tuple[str, Finding | None]:
        evidence = [Citation(**e) for e in args.get("evidence", [])]
        bad = [e for e in evidence
               if e.doc_id not in self.sources or _norm(e.quote) not in _norm(self.sources[e.doc_id])]
        if bad and self.citation_failures < self.max_citation_retries:
            self.citation_failures += 1
            return ("These quotes were not found verbatim in the cited documents: "
                    + "; ".join(f"{e.doc_id}: '{e.quote[:80]}'" for e in bad)
                    + ". Quote exact words, then call record_finding again."), None

        verdict = args["verdict"]
        low = high = None
        if self.check == "M1" and verdict == "misstated":
            low = high = -engine.position(self.cf.inputs()).provision_shortfall
        elif verdict == "misstated":
            low = high = self._effect(args.get("low_case"))
        elif verdict in ("judgement_call", "insufficient_evidence") and args.get("low_case"):
            low, high = self._effect(args.get("low_case")), self._effect(args.get("high_case"))

        rationale = args.get("rationale", "")
        if bad:
            rationale += f" [Unverified citations dropped: {len(bad)}]"
            evidence = [e for e in evidence if e not in bad]
        finding = Finding(
            contract_id=self.cf.contract_id, check=self.check, ref=self.ref, verdict=verdict,
            profit_effect_low=low, profit_effect_high=high,
            confidence=float(args.get("confidence", 0.5)), evidence=evidence,
            question=args.get("question"), document_request=args.get("document_request"),
            rationale=rationale,
        )
        return "Recorded.", finding
