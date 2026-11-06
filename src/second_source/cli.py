"""Command line: simulate a portfolio, run a system over it, score the results.

    second-source simulate --out data/dev --n 30 --seed 0
    second-source run --system rules --portfolio data/dev --out runs/rules.jsonl
    second-source eval --portfolio data/dev runs/null.jsonl runs/rules.jsonl
    second-source demo                      # all of the above, offline
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .evals import markdown, score
from .models import Finding
from .simulator import write_portfolio
from .store import load_labels, load_portfolio
from .systems import get_system


def cmd_simulate(args: argparse.Namespace) -> None:
    contracts = write_portfolio(Path(args.out), n=args.n, seed=args.seed)
    print(f"Wrote {len(contracts)} contracts to {args.out}")


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
    meta = {"system": args.system, "contracts": len(contracts),
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
    root = Path(args.out)
    write_portfolio(root, n=args.n, seed=args.seed)
    runs = []
    for name in ("null", "rules"):
        ns = argparse.Namespace(system=name, portfolio=str(root), out=f"{args.runs}/{name}.jsonl",
                                contracts=None, limit=None)
        runs.append(str(cmd_run(ns)))
    cmd_eval(argparse.Namespace(portfolio=str(root), runs=runs, report=f"{args.runs}/report.md",
                                json=f"{args.runs}/report.json"))


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="second-source")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("simulate", help="generate a synthetic portfolio with ground truth")
    s.add_argument("--out", default="data/dev")
    s.add_argument("--n", type=int, default=30)
    s.add_argument("--seed", type=int, default=0)
    s.set_defaults(func=cmd_simulate)

    r = sub.add_parser("run", help="run a system over a portfolio")
    r.add_argument("--system", required=True, help="null | rules | agent | one_prompt")
    r.add_argument("--portfolio", default="data/dev")
    r.add_argument("--out")
    r.add_argument("--contracts", help="comma-separated contract ids")
    r.add_argument("--limit", type=int)
    r.set_defaults(func=cmd_run)

    e = sub.add_parser("eval", help="score one or more runs against ground truth")
    e.add_argument("runs", nargs="+")
    e.add_argument("--portfolio", default="data/dev")
    e.add_argument("--report")
    e.add_argument("--json")
    e.set_defaults(func=cmd_eval)

    d = sub.add_parser("demo", help="simulate, run the offline systems and score them")
    d.add_argument("--out", default="data/demo")
    d.add_argument("--runs", default="runs/demo")
    d.add_argument("--n", type=int, default=30)
    d.add_argument("--seed", type=int, default=0)
    d.set_defaults(func=cmd_demo)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
