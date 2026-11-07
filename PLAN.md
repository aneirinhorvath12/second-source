# Plan

> **Second Source:** a judgement-heavy financial-controller eval for long-term contract accounting, and a harness that lifts Haiku 5.5 from X to Y on held-out contracts at £Z per contract.

## Decided (7 November 2026)

- **The model is fixed at Haiku 5.5; only the harness changes.** One-prompt Sonnet 5.5 and Opus 5.5 are reference points.
- **The task:** transaction price, ETC, revenue to date and provision, plus one confidence banded at 90% and 75% ([`prompts/controller.md`](prompts/controller.md)).
- **Scoring:** Aneirin's rubrics, graded strictly, with consistency measured across runs and misstatement £ that slips through set against review load.
- **The file is everything available at the review date.** A document that's referred to but missing doesn't exist for anyone reviewing the accounts.
- **Test set:** 10 high-quality contracts built from Aneirin's briefs by a separate agent, and run once after the harness is frozen.
- **Development set:** the existing 21 contracts, cleaned. All harness work happens on these.

## Steps

1. **Freeze the eval spec:** outputs, rubric format and metrics. *Needs Aneirin's materiality threshold.*
2. **Rubrics** for C002, C007, C012, C017 and C021 from the rulings so far, then re-score run 1 strictly as the baseline.
3. **Clean up the development set:**
   - remove the generator's fake red flags: the "Area 600 Control Building", invoicing-address letters, theft reports with dates that don't fit, cube-test dates, duplicated diary entries;
   - reconcile the P6 schedule, ledger and cost report, and show variation costs in each ETC build-up;
   - add consistency checks to `second-source check`;
   - add scary-but-fine twins.
4. **Open rulings:**
   - C003 (£35k);
   - C006 and C011: whether the rework cost comes out of progress (IFRS 15.B19(a));
   - sign-offs: the C006 and C018 M1 re-rulings, and C021;
   - from run 1: C007's rectification cost in the ETC, C021's bunker wall repairs, C002's VO-005.
5. **Baselines on the development set:** Haiku, Sonnet and Opus, one prompt each.
6. **Harness iterations, on the development set only:**
   - a structured review procedure, by IFRS area;
   - document search and a calculator (the engine), so judgement is separate from arithmetic;
   - a verifier pass that challenges each adjustment against materiality and evidence;
   - triage by agreement across runs;
   - confidence calibration;
   - context handling for files longer than the window;
   - harness v0, the check-based agent.
7. **Freeze the harness,** build the test set from the briefs with a separate agent, run it once, and write up with a failure analysis.

Open question: a second qualified marker for a blind sample, to report agreement with Aneirin's marking.

## Proposed test set

| # | Problem contract | Its twin (looks similar, is fine) |
|---|---|---|
| 1–2 | Progress can't be measured reliably, so revenue is limited to cost (IFRS 15.45) | Volatile estimates with a credible basis |
| 3–4 | Output method, with fulfilment costs wrongly carried on the balance sheet | A legitimate deferral of recoverable costs (15.95) |
| 5–6 | A bundled performance obligation that should be split | Integrated maintenance, so one obligation is right |
| 7–8 | A loss-maker netted against a healthy contract | A genuine package deal, so combining is right (15.17) |
| 9 | Onerous only on a best estimate, with a plausible but unagreed claim | — |
| 10 | Clean, long and noisy | — |

Every contract also carries routine judgements: variations and events after the period.

## Done

- Engine with property tests, including uninstalled materials (IFRS 15 Example 19) tested against the standard's own numbers
- 21-contract development set with answer keys, `check`, `index` and `show`
- M1 tested on the best estimate; each check owns one line of the accounts
- C021 (scenario 2) written by hand
- First dataset review with Aneirin's rulings; two decoy-letter bugs and the C009 register bug fixed
- The controller review runner (`review.py`) and run 1: Haiku baseline, 5 contracts × 3 runs, $1.63
