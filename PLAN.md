# Build plan

The aim of the weekend: one honest, specific result. *"A frontier model with the whole file catches X; the agent with the engine and the schedule catches Y, escalates Z correctly, at £N per contract."*

## Done (scaffold)

- [x] Engine with property tests (full loss identity, POC bounds, scenario re-runs)
- [x] XER writer/reader and schedule metrics
- [x] Triggers for T1, E2, M1
- [x] `null` and `rules` systems, scored offline
- [x] Investigator agent loop with verified citations and engine-computed effects (tested with a fake client)
- [x] One-prompt baseline (B0)
- [x] Eval harness: catch rate, false alarms, under/over-escalation, £ caught, quantification error, range coverage
- [x] MCP server, CI
- [x] Portfolio committed as editable files, with answer keys in domain terms and a `check` command
- [x] Hard portfolio: 20 contracts at ~130k tokens, 16 T1 stories, 11 E2, 4 M1, committed as files
- [x] Pilot runs (Sonnet 5.5): B0 88% verdict accuracy on 14 contracts; agent 25 of 27 on 5; rules 51%
- [x] Stripped down: generators and the easy portfolio removed; models default to Haiku 5.5

## Next

- [ ] Finish the B0 run (6 contracts left) and run the agent on all 20 (roughly $0.25 per contract with caching, at third-party list prices)
- [ ] Decide on the E2 trigger blind spot: ETC problems that don't show in earned value (prelims vs P6 finish, unbooked claims, smoothing) are never investigated. Always investigate E2, or add triggers for them?
- [ ] Read B0's and the agent's transcripts on the cases they miss; are the misses model failures or unfair cases?
- [ ] Review the hard answer keys as an auditor: do you agree with every verdict? (especially time bars, value disputes, oral instructions)
- [ ] Harder still: a variant whose files exceed the context window (whole-project diaries and minutes, monthly P6 updates), where one-prompt can't read everything and retrieval matters

## Saturday

- [ ] Run `agent` and `one_prompt` on 5 contracts; read every transcript
- [ ] Fix the biggest failure bucket (missed evidence, misapplied standard, concluded too early, bad citation)
- [ ] Edit the portfolio: disagree with the answer keys where you'd rule differently, and rewrite letters and minutes so the key facts are buried in realistic, messier text (re-run `check` after each edit)
- [ ] Set aside a held-out group of contracts and don't look at it until Sunday

## Sunday

- [ ] Full runs: null, rules, B0, agent on the held-out set
- [ ] Ablation: agent without schedule metrics (shows what P6 adds on E2)
- [ ] Fill in model pricing in `agent/usage.py`; report cost per contract
- [ ] Per-contract HTML report: verdicts, evidence, questions, document requests
- [ ] README headline + chart; 2-minute demo video

## Later

- [ ] Checks T3 (LDs from forecast slip), E1 (savings with no plan), E4 (prolongation), E5 (margin held flat over periods)
- [ ] Multi-period history in the files (margin fade, estimate smoothing)
- [ ] Devil's-advocate pass on adverse findings above materiality
- [ ] Model routing and prompt caching measured on the cost-accuracy curve
- [ ] Prompt-injection cases in documents
- [ ] Blind realism review of the files by qualified accountants
