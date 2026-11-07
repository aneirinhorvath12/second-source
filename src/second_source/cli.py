"""Command line. Every command works on the committed portfolio unless you pass --portfolio.

    second-source check                       validate the portfolio after editing it
    second-source show C009                   numbers, triggers and answers for one contract
    second-source index                       rewrite the portfolio's INDEX.md
    second-source run --system rules          run a system; findings go to runs/rules.jsonl
    second-source eval runs/null.jsonl runs/rules.jsonl
    second-source demo                        run null and rules, then score them (offline)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .evals import markdown, score
from .models import Finding
from .portfolio import check_portfolio, index_markdown, show_contract
from .store import load_labels, load_portfolio
from .systems import get_system

DEFAULT_PORTFOLIO = "portfolios/hard"


def cmd_check(args: argparse.Namespace) -> None:
    problems = check_portfolio(Path(args.portfolio))
    for p in problems:
        print(p)
    errors = sum(p.level == "error" for p in problems)
    warnings = len(problems) - errors
    print(f"\n{args.portfolio}: {errors} errors, {warnings} warnings")
    if errors:
        raise SystemExit(1)


def cmd_index(args: argparse.Namespace) -> None:
    root = Path(args.portfolio)
    (root / "INDEX.md").write_text(index_markdown(root))
    print(f"Wrote {root / 'INDEX.md'}")


def cmd_show(args: argparse.Namespace) -> None:
    print(show_contract(Path(args.portfolio), args.contract))


def cmd_run(args: argparse.Namespace) -> Path:
    system = get_system(args.system)
    contracts = load_portfolio(Path(args.portfolio))
    if args.contracts:
        wanted = set(args.contracts.split(","))
        contracts = [c for c in contracts if c.contract_id in wanted]
    if args.limit:
        contracts = contracts[: args.limit]

    out = Path(args.out or f"runs/{args.system}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    started = time.time()
    n = 0
    with out.open("w") as f:
        for cf in contracts:
            for finding in system(cf):
                f.write(finding.model_dump_json() + "\n")
                n += 1
            print(f"  {cf.contract_id} done", file=sys.stderr)
    meta = {"system": args.system, "portfolio": args.portfolio, "contracts": len(contracts),
            "contract_ids": [c.contract_id for c in contracts], "findings": n,
            "seconds": round(time.time() - started, 1)}
    if args.system in {"agent", "one_prompt"}:
        from .agent.usage import USAGE
        meta["usage"] = USAGE.summary()
    out.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
    print(f"{args.system}: {n} findings on {len(contracts)} contracts -> {out}")
    return out


def _load_findings(path: Path) -> list[Finding]:
    return [Finding.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()]


def cmd_eval(args: argparse.Namespace) -> None:
    root = Path(args.portfolio)
    labels = load_labels(root)
    run_files = [Path(p) for p in args.runs]
    results = {}
    for p in run_files:
        findings = _load_findings(p)
        # score only the contracts the run covered, so partial runs (--limit) are fair
        meta_path = p.with_suffix(".meta.json")
        covered = None
        if meta_path.exists():
            covered = set(json.loads(meta_path.read_text()).get("contract_ids", [])) or None
        lbls = [lbl for lbl in labels if covered is None or lbl.contract_id in covered]
        results[p.stem] = score(lbls, findings)
    md = markdown(results)
    print(md)
    if args.report:
        Path(args.report).write_text(md)
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2, default=str))


def cmd_demo(args: argparse.Namespace) -> None:
    runs = []
    for name in ("null", "rules"):
        ns = argparse.Namespace(system=name, portfolio=args.portfolio, out=f"{args.runs}/{name}.jsonl",
                                contracts=None, limit=None)
        runs.append(str(cmd_run(ns)))
    cmd_eval(argparse.Namespace(portfolio=args.portfolio, runs=runs, report=f"{args.runs}/report.md",
                                json=f"{args.runs}/report.json"))


def cmd_review(args: argparse.Namespace) -> None:
    import anthropic

    from .review import review
    root = Path(args.portfolio)
    cdirs = [root / "contracts" / c for c in args.contracts]
    client = anthropic.Anthropic(max_retries=6)
    records = review(cdirs, Path(args.out), runs=args.runs, model=args.model, client=client,
                     dry_run=args.dry_run)
    if records:
        print(f"{len(records)} calls, ${sum(r['cost_usd'] for r in records):.2f}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="second-source")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name: str, help_text: str, func) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help_text)
        sp.add_argument("--portfolio", default=DEFAULT_PORTFOLIO)
        sp.set_defaults(func=func)
        return sp

    add("check", "validate a portfolio after editing it", cmd_check)
    add("index", "rewrite a portfolio's INDEX.md", cmd_index)
    add("show", "numbers, triggers and answers for one contract", cmd_show).add_argument("contract")

    r = add("run", "run a system over a portfolio", cmd_run)
    r.add_argument("--system", required=True, help="null | rules | agent | one_prompt")
    r.add_argument("--out")
    r.add_argument("--contracts", help="comma-separated contract ids")
    r.add_argument("--limit", type=int)

    e = add("eval", "score one or more runs against the answer keys", cmd_eval)
    e.add_argument("runs", nargs="+")
    e.add_argument("--report")
    e.add_argument("--json")

    v = add("review", "the controller review: contract file in, figures and confidence out", cmd_review)
    v.add_argument("contracts", nargs="+")
    v.add_argument("--out", required=True)
    v.add_argument("--runs", type=int, default=1)
    v.add_argument("--model", default="claude-haiku-5-5")
    v.add_argument("--dry-run", action="store_true", help="write the requests and count tokens; no answers")

    d = add("demo", "run the offline systems over a portfolio and score them", cmd_demo)
    d.add_argument("--runs", default="runs/demo")

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
