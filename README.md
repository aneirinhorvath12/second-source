# Second Source

**A judgement-heavy financial-controller eval for long-term contract accounting, and the harness engineering to make a small model (Claude Haiku 5.5) pass it.**

A financial controller at an engineering contractor signs off revenue on many long-term fixed-price contracts each period and can only review a few in detail. Second Source asks whether a model can do the first pass. It reads a contract file and gives the figures it would book, with a confidence that decides whether the controller needs to look, justified from the documents.

> **Status, 7 November 2026:** baseline measured. Haiku 5.5 with one prompt finds the planted issues, but it never clears a contract, even a clean one. Next: rubric grading, a cleaner development set, a held-out test set of 10 contracts, then harness iterations. See [PLAN.md](PLAN.md).

## The task

**Input.** One contract file at 31 December 2026, about 130k tokens:
- the contract;
- a cost report with its variation register and ETC build-up;
- a ledger;
- a P6 schedule;
- 60 to 90 documents: site diaries, progress minutes, internal cost reviews, correspondence, registers.

The folder is everything available at the review date.

**Output.**
- Transaction price, estimated cost to complete, revenue to date and onerous provision.
- One confidence that the figures are fair, banded:
  - **over 90%:** no review;
  - **75 to 90%:** cursory review;
  - **below 75%:** detailed investigation.
  
  Any adjustment to the project team's figures caps the confidence at 90%.
- A justification for each figure, citing documents by file name.

The prompt is [`prompts/controller.md`](prompts/controller.md), written by Aneirin, and the answer layout is [`prompts/output_format.md`](prompts/output_format.md).

## Grading

Each contract has an answer key in [`portfolios/hard/answers/`](portfolios/hard/answers/). It records a verdict and a correction for each judgement, and the engine compiles these into the figures the key expects. Grading is moving to rubrics: pass/fail criteria per contract, written by the domain expert. The criteria cover figures within materiality, specific treatments, no false adjustments, and the right review decision for the right reasons. Results will be reported like [APEX-Accounting](https://www.mercor.com/blog/introducing-the-ai-productivity-index-for-accounting/): mean criteria met, full passes, and consistency across runs. Alongside that comes the trade-off a controller cares about: misstatement £ that slips through against the share of contracts sent for review.

## Baseline: run 1

Haiku 5.5, one call per contract, five contracts with three runs each. The total cost was $1.63. Outputs are in [`results/run1-haiku-baseline/`](results/run1-haiku-baseline/).

- **Figures:**
  - **transaction price:** matched the answer key on all 15 runs;
  - **ETC:** within £0.5m on 12;
  - **revenue to date:** within £0.5m on 11.
- **Strict grading** (all four figures within £0.1m of the key): 7 of 15 runs fully right, and no contract was right on all three of its runs.
- **Triage failed.** Every confidence was below 90%, including the clean control (65% to 85%), and one contract scored 30%, 80% and 60% on near-identical figures.
- **It found defects in the generated documents:** fake red flags that are now being removed.

This is a small sample and a baseline, not a result.

## The dataset

[`portfolios/hard/`](portfolios/hard/INDEX.md) holds 21 synthetic contracts, which form the development set. A generator built C001 to C020 from templates. C021 was written by hand from Aneirin's scenario: a ten-year contract kept profitable by an efficiency target. Aneirin's rulings are recorded in the answer keys. See [`portfolios/README.md`](portfolios/README.md) for how to edit contracts and keys, and `second-source check` to validate an edit.

Known limitations:
- **Model-written documents.** The evidence is more explicit than in real files.
- **Few issue types.** The planted issues come from a small set of templates.
- **Almost every contract has a problem.** 20 of 21 need revision or a flag.

The held-out test set will be 10 contracts written to a stricter standard, built from Aneirin's briefs by a separate agent and run once.

## Code

```
prompts/              the controller prompt and the answer layout
portfolios/hard/      contracts and answer keys, as editable files
results/              committed run outputs
src/second_source/
  review.py           the controller review: prompt + documents -> model -> figures and confidence
  engine.py           contract accounting: POC, revenue, onerous provision, uninstalled
                      materials (IFRS 15 Example 19), earned value, LDs
  answers.py          answer keys: verdicts and corrections, compiled by the engine
  portfolio.py        check, index and show for hand-edited contracts
  store.py            loads a contract folder (what a model may see)
  models.py           shared data shapes
  xer.py              minimal P6 XER reader/writer and schedule metrics
  agent/, triggers.py, systems.py, evals/score.py
                      harness v0, from the earlier design: one sub-agent per check
                      (T1 variations, E2 ETC, M1 provision), with document tools and
                      engine-computed effects, scored per check. Kept as a harness
                      candidate; its scoring moves to rubrics.
  cli.py              check | index | show | review | run | eval | demo
```

`review.py` caches each contract's documents, so repeat runs read them at a tenth of the price. It skips a run whose prompt, file and model are unchanged since a complete answer, and logs every call's tokens and cost. Answers stream, because Haiku thinks for 13k to 32k tokens before answering.

## Quickstart

```bash
uv sync --extra agent
uv run pytest
uv run second-source check           # validate the contracts and answer keys
uv run second-source show C021       # management's numbers, the answer key's best estimate

export ANTHROPIC_API_KEY=...
uv run second-source review C002 C021 --out runs/scratch --dry-run   # exact requests and token counts
uv run second-source review C002 C021 --runs 3 --out runs/scratch    # about $0.10 a call on Haiku

uv run second-source demo            # offline harness-v0 baselines (null, rules), no API calls
```

## Ground rules

Everything here is synthetic. Contractors, customers and projects are fictional, and nothing comes from any client engagement. Guidance notes paraphrase the standards and cite paragraph numbers rather than reproducing IFRS text.
