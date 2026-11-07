"""The controller review: one contract file in, one model's figures and confidence out.

    second-source review C002 C021 --runs 3 --out runs/scratch --dry-run
    second-source review C002 C021 --runs 3 --out results/run2

Each call sends the prompt in prompts/controller.md as the system prompt, then every
document in the contract file, then the layout in prompts/output_format.md. There are no
tools, no engine and no agent loop. The model reads the file and answers.

Cost control:
- the documents block is cached, so repeat runs of a contract read it at a tenth of the price;
- a call is skipped if the same prompt, layout, file and model already have a complete answer
  for that run number, so changing one contract only re-runs that contract;
- every call's tokens and cost are logged to calls.jsonl.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .store import ContractFile, load_contract

PROMPTS = Path(__file__).resolve().parents[2] / "prompts"
DEFAULT_MODEL = "claude-haiku-5-5"
MAX_TOKENS = 64_000  # Haiku 5.5 thinks for 13k-32k tokens before answering

# $ per million tokens: (input, 5-minute cache write, cache read, output).
# Haiku 5.5 charges more for any request whose prompt (input + cache reads + cache writes)
# is over 100,000 tokens. Source: https://platform.claude.com/docs/en/about-claude/pricing
PRICES: dict[str, list[tuple[int | None, tuple[float, float, float, float]]]] = {
    "claude-haiku-5-5": [(100_000, (0.10, 0.125, 0.01, 0.50)), (None, (0.50, 0.625, 0.05, 2.50))],
    "claude-sonnet-5-5": [(None, (2.00, 2.50, 0.10, 10.00))],
    "claude-opus-5-5": [(None, (4.00, 5.00, 0.20, 20.00))],
}


def cost_usd(model: str, inp: int, cache_write: int, cache_read: int, out: int) -> float:
    prompt = inp + cache_write + cache_read
    for limit, (p_in, p_cw, p_cr, p_out) in PRICES[model]:
        if limit is None or prompt <= limit:
            return (inp * p_in + cache_write * p_cw + cache_read * p_cr + out * p_out) / 1e6
    raise AssertionError("unreachable")


def render_file(cf: ContractFile) -> str:
    """Every file in the contract folder, each wrapped in a <document> tag."""
    parts = [f"<document name='{n}'>\n{t}\n</document>" for n, t in cf.sources().items()]
    parts.append(f"<document name='ledger_summary'>\nTotal actual cost per ledger: "
                 f"{cf.ledger_total:,.2f}\n</document>")
    return "\n\n".join(parts)


@dataclass
class Request:
    contract_id: str
    system: list[dict[str, Any]]
    messages: list[dict[str, Any]]
    key: str
    """Hash of everything that decides the answer, bar the run number."""


def build_request(cdir: Path, model: str) -> Request:
    cf = load_contract(cdir)
    system_text = (PROMPTS / "controller.md").read_text()
    layout = (PROMPTS / "output_format.md").read_text()
    documents = render_file(cf)
    system = [{"type": "text", "text": system_text}]
    messages = [{"role": "user", "content": [
        {"type": "text", "text": documents, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": f"Review contract {cf.contract_id}.\n\n{layout}"},
    ]}]
    key = hashlib.sha256("\x00".join([model, system_text, layout, documents]).encode()).hexdigest()[:16]
    return Request(cf.contract_id, system, messages, key)


ROWS = {"transaction_price": "Transaction price", "etc": "Estimated cost to complete",
        "revenue_to_date": "Revenue recognised to date", "provision": "Onerous contract provision"}


def _number(cell: str) -> float | None:
    m = re.search(r"-?\d[\d,]*(?:\.\d+)?", cell.replace("£", ""))
    if not m:
        return 0.0 if re.search(r"\b(nil|none|n/a)\b", cell, re.IGNORECASE) else None
    value = float(m.group(0).replace(",", ""))
    return value * 1e6 if re.search(r"\d\s*m\b", cell) else value


def parse_figures(text: str) -> dict[str, float] | None:
    """The JSON block the layout asks for; failing that, the table and the confidence line."""
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if blocks:
        try:
            return json.loads(blocks[-1])
        except json.JSONDecodeError:
            pass
    out: dict[str, float] = {}
    for key, label in ROWS.items():
        row = re.search(rf"^\|\s*\**{label}\**\s*\|([^|]*)\|([^|]*)\|", text, re.MULTILINE)
        if row and (n := _number(row.group(2))) is not None:
            out[key] = n
    conf = re.search(r"##\s*Confidence\s*\n+\W*(\d{1,3})\s*%", text)
    if conf:
        out["confidence"] = float(conf.group(1))
    return out or None


def _done(out: Path) -> set[tuple[str, int, str]]:
    log = out / "calls.jsonl"
    if not log.exists():
        return set()
    rows = map(json.loads, log.read_text().splitlines())
    return {(r["contract_id"], r["run"], r["key"]) for r in rows if r.get("stop_reason") == "end_turn"}


def review(cdirs: list[Path], out: Path, runs: int = 1, model: str = DEFAULT_MODEL,
           client: Any = None, dry_run: bool = False) -> list[dict[str, Any]]:
    out.mkdir(parents=True, exist_ok=True)
    done = _done(out)
    records = []
    for cdir in cdirs:
        req = build_request(cdir, model)
        (out / f"{req.contract_id}.request.json").write_text(
            json.dumps({"model": model, "max_tokens": MAX_TOKENS, "system": req.system,
                        "messages": req.messages}, indent=1))
        if dry_run:
            if client is not None:
                n = client.messages.count_tokens(model=model, system=req.system,
                                                 messages=req.messages).input_tokens
                first = cost_usd(model, 0, n, 0, 18_000)
                repeat = cost_usd(model, 0, 0, n, 18_000)
                print(f"{req.contract_id}: {n:,} prompt tokens; about ${first:.3f} for the first run "
                      f"and ${repeat:.3f} for each repeat, if thinking plus answer is ~18k tokens")
            continue
        for run in range(1, runs + 1):
            if (req.contract_id, run, req.key) in done:
                print(f"{req.contract_id} run {run}: unchanged, skipped")
                continue
            t0 = time.time()
            kwargs = {"model": model, "max_tokens": MAX_TOKENS, "system": req.system,
                      "messages": req.messages}
            if hasattr(client.messages, "stream"):  # long answers must stream (SDK rule)
                with client.messages.stream(**kwargs) as stream:
                    resp = stream.get_final_message()
            else:
                resp = client.messages.create(**kwargs)
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            u = resp.usage
            cw = getattr(u, "cache_creation_input_tokens", 0) or 0
            cr = getattr(u, "cache_read_input_tokens", 0) or 0
            details = getattr(u, "output_tokens_details", None)
            record = {
                "contract_id": req.contract_id, "run": run, "key": req.key, "model": model,
                "input_tokens": u.input_tokens, "cache_write": cw, "cache_read": cr,
                "output_tokens": u.output_tokens,
                "thinking_tokens": getattr(details, "thinking_tokens", None) if details else None,
                "stop_reason": getattr(resp, "stop_reason", None),
                "cost_usd": round(cost_usd(model, u.input_tokens, cw, cr, u.output_tokens), 4),
                "seconds": round(time.time() - t0, 1),
                "figures": parse_figures(text),
            }
            (out / f"{req.contract_id}_run{run}.md").write_text(text)
            with (out / "calls.jsonl").open("a") as f:
                f.write(json.dumps(record) + "\n")
            records.append(record)
            conf = (record["figures"] or {}).get("confidence")
            print(f"{req.contract_id} run {run}: confidence {conf}, {record['output_tokens']:,} tokens out, "
                  f"${record['cost_usd']:.3f}")
    return records
