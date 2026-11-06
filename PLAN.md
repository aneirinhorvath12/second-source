# Build plan

The aim of the weekend: one honest, specific result. *"A frontier model with the whole file catches X; the agent with the engine and the schedule catches Y, escalates Z correctly, at £N per contract."*

## Done (scaffold)

- [x] Engine with property tests (full loss identity, POC bounds, scenario re-runs)
- [x] XER writer/reader and schedule metrics
- [x] Simulator v0: 9 scenarios, labels in code, withheld documents, reference-format mess
- [x] Triggers for T1, E2, M1
- [x] `null` and `rules` systems, scored offline
- [x] Investigator agent loop with verified citations and engine-computed effects (tested with a fake client)
- [x] One-prompt baseline (B0)
- [x] Eval harness: catch rate, false alarms, under/over-escalation, £ caught, quantification error, range coverage
- [x] MCP server, CI

## Saturday

- [ ] Run `agent` and `one_prompt` on 5 contracts; read every transcript
- [ ] Fix the biggest failure bucket (missed evidence, misapplied standard, concluded too early, bad citation)
- [ ] Model-rendered documents: rewrite each template from the same fact sheet so facts are buried in longer, messier text; check every fact survives
- [ ] Freeze a held-out portfolio (`--seed 1`) and don't look at it until Sunday

## Sunday

- [ ] Full runs: null, rules, B0, agent on the held-out set
- [ ] Ablation: agent without schedule metrics (shows what P6 adds on E2)
- [ ] Fill in model pricing in `agent/usage.py`; report cost per contract
- [ ] Per-contract HTML report: verdicts, evidence, questions, document requests
- [ ] README headline + chart; 2-minute demo video

## Later

- [ ] Checks T3 (LDs from forecast slip), E1 (savings with no plan), E4 (prolongation), E5 (margin held flat over periods)
- [ ] Multi-period history in the simulator (margin fade, estimate smoothing)
- [ ] Devil's-advocate pass on adverse findings above materiality
- [ ] Model routing and prompt caching measured on the cost-accuracy curve
- [ ] Prompt-injection cases in documents
- [ ] Blind realism review of simulated files by qualified accountants
