# Portfolios

This folder is the dataset. Every contract, document and answer is a plain file you can read and edit, and the evals score systems against exactly what's here.

[`hard/`](hard/INDEX.md) holds 20 fixed-price contracts of about 130k tokens each, with 60–80 documents per contract: several issues per contract, buried in a full project file, with traps.

### What makes it hard

**Volume.** Each file has what a real project produces: a long contract, a site diary for every working day, monthly progress minutes, internal cost reviews, a correspondence register, an RFI log, a P6 programme of a few hundred activities, and dozens of routine letters and emails about safety, access, drawings and the like. The evidence for an issue is a few sentences somewhere in all of that.

**Indirection.** The customer never uses Brackmoor's VO numbers, so a letter about `ERI-014` has to be traced back to `VO-003` through the quotation. Rejections are often oblique ("the work forms part of the Contractor's obligations under clause 2.3"). Some answers need a clause plus two dates (a notification sent 14 weeks after the diary records the problem, against an 8-week time bar).

**Traps.** Plenty of things look wrong but aren't: a stroppy letter that rejects an extension of time but accepts the price; an acceptance stated including VAT; a rejection of "VO-003" that turns out to be about a different project; poor CPI explained by materials bought early; a subcontractor claim that the ETC already provides for; a loss-making contract whose provision is correct.

**Escalations.** Some items can't be concluded from the file: a covering email whose attached letter is missing, a quotation the customer is still "reviewing", an oral instruction whose price is unagreed.

**Several issues per contract**, so a system can't stop at the first one, and some clean contracts full of red herrings.

The files were bootstrapped once by a generator: a scenario catalogue of stories, code for the bulk paperwork, and key letters drafted by a model from fact sheets and checked. The generator has since been removed (it's in the git history), and the files are now maintained by hand.

## Layout

```
hard/
  portfolio.yaml           name, period end, where it came from
  INDEX.md                 overview of every contract and its answers (generated)
  contracts/C009/          everything a system may see
    terms.yaml             contract summary: price, dates, LD rate and cap
    cost_report.yaml       management's numbers, ETC build-up and the variation register
    schedule.xer           Primavera P6 export
    ledger.csv             actual cost by month and cost code
    docs/                  contract, letters, emails, memos, minutes, site diaries, registers
  answers/C009.yaml        the answer key, which no system ever sees
```

## Editing

Edit any file, then run:

```bash
uv run second-source check        # catches broken edits; CI runs it too
uv run second-source show C009    # the contract's numbers, what the triggers raise, and its answers
uv run second-source index        # refresh INDEX.md
```

**Facts live in one place.** The cost report and variation register are one file (`cost_report.yaml`), so they can't disagree. The only deliberate overlap is `terms.yaml` against the wording in `docs/contract.md`; `check` warns if the price, LD terms or completion date drift apart.

**Answers say what's right, not what it costs.** An answer key records the verdict and the corrected inputs, in domain terms:

```yaml
  - check: T1
    ref: VO-002
    verdict: misstated
    correction:
      variations: {VO-002: 0}      # VO-002 should carry 0 in TP
    why: "Customer letter rejects it as within the original scope."
```

The engine computes the profit effect from the cost report every time, so editing a number in `cost_report.yaml` never leaves a stale effect in the answers. A correction can set `variations` (value per variation in TP), `etc`, `claims_in_tp` or `ld_deduction`; anything left out stays as reported.

| Verdict | What to give |
|---|---|
| `supported` | Nothing else |
| `misstated` | A `correction` (M1 needs none: the engine computes the provision shortfall) |
| `judgement_call` | A `range` with `low` and `high` corrections (`{}` means as reported); optionally a `correction` as the best estimate, otherwise the midpoint is used |
| `insufficient_evidence` | A `request` naming the document that would settle it; optionally a `correction` and `range` |

Every variation in TP needs one T1 judgement, and every contract needs an E2 `ETC` and an M1 `PROVISION` judgement. `tag` names the scenario for the score breakdowns; leave it out for unremarkable items.

**Keep answers out of contract files.** Systems read everything under `contracts/`. Comments in `terms.yaml` and `cost_report.yaml` are stripped before a system sees them, but documents are read as written, so never put hints in `docs/`.

**Adding a contract.** Copy a contract folder and its answer key, rename both (say to `C021`), update the `contract_id` in all three YAML files, edit, then run `check`.

**Editing the schedule.** `schedule.xer` is tab-separated text. The fields that matter are in the `TASK` table (`phys_complete_pct`, `target_start_date`, `target_end_date`, `early_end_date` for the forecast finish) and the `TASKRSRC` table (`target_cost`, each activity's budget). Use `show` to see the earned value your edit produces.

## Changing the dataset changes the results

Scores are only comparable on the same version of a portfolio. When you edit it, commit the edit on its own and re-run the systems you're comparing. When you want a held-out test set, set some contracts aside in their own folder (say `portfolios/test/`) and stop looking at them until the final runs.
