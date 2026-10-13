# Vision

Status: draft for alignment. Nothing here is built unless marked "exists".

## The promise

Anyone building a feature that uses a model gets a reliable way to judge its quality and robustness before shipping. When a prompt, model, config or code path changes, the change runs against an eval the coding agent cannot grade for itself.

We do not promise "100% safe". An eval gives evidence, bounded by its goldens. The honest output is: "no regressions across N cases; here is what is not covered."

## Decisions made

| Topic | Decision |
|---|---|
| Audience | Open source, any developer |
| Product shape | Claude Code plugin (skills + hooks) over a CLI engine |
| Languages | Python and TypeScript first; the adapter contract is language-neutral |
| Goldens | Agent drafts (from code, tests, logs, synthetic generation); human approves before they count. When unsure, the agent asks |
| Enforcement | Configurable per feature: block or advisory |
| Judge | Separate headless Claude Code process (`claude -p`) launched by the engine: no tools, no session history, no repo access, only the sealed bundle |
| Judge fallback | In-session subagent mode allowed, labeled "judge not isolated" in the report; the gate never passes on it |
| Judge model | User-configurable; defaults dev `sonnet`, gate `fable`. Non-Claude judges: not now |
| Storage | Local markdown reports + jsonl sidecars in git; no hosted platform |

## Principles (unchanged)

1. Scorers can only veto; only the blind judge can pass.
2. The judge never learns who or what produced the output, how, or why.
3. Canaries prove the judge can fail things.
4. Holdout goldens, graders and the judge prompt are protected from the coding agent.
5. Every run states a hypothesis first and links to its parent run.

## User experience

1. **Setup.** The user invokes the skill (or it auto-triggers when an AI feature is being built). It maps the codebase for AI surfaces, shows the map, and lets the user choose. For each chosen surface it writes an adapter, drafts goldens and edge cases, writes the spec, rubric and canaries, and runs a baseline.
2. **Change.** A hook notices edits to covered paths and runs the eval. Strictness is per feature.
3. **Result.** A short report: verdict counts, failed cases with the judge's quoted evidence, change from the parent run, cost. Details are one level down.
4. **Decide.** Accept, fix, or revert via the parent chain.

## Architecture

- **Skills** teach the agent when and how: setup and mapping, golden writing, run-and-interpret.
- **Hooks** make it unavoidable: run on covered changes, block or warn, protect the eval surface.
- **CLI engine** (exists, Python): adapter calls, scorers, sealed bundles, judge, canaries, gate, reports, chain.
- An MCP wrapper may come later if agents misuse the CLI.

## What exists (Phase 1)

Engine, CLI (`run`, `diff`, `verify`, `annotate`, `override`, `promote`), blind judge, canaries, gate, reports, protect-paths hook, three skills, demo project. 46 tests.

## Planned changes to what exists

- Short default report; move stats detail, findings catalog and facts-hash verification behind flags or remove them.
- Simplify promote/override and the separate dev/gate chain heads.
- Wire the hook that runs evals on covered changes, with per-feature strictness.
- Add `edd init`, `edd revert`.

## New work

1. Brownfield mapper skill: find AI surfaces (SDK calls, prompt files, agent loops, classifiers, RAG steps, output parsers), group into features, rate risk, report what it may have missed.
2. Adapter generation for Python and TypeScript, asking early what is safe to call (credentials, databases, services).
3. Golden and edge-case generation with an approval step and a coverage-gaps summary.
4. Judge fallback mode and report labeling.

## Open questions

- Scope of "AI feature" for v1: model calls only, or also tool-using agents, RAG pipelines and multi-step workflows?
- How strong the public claims should be.
- How much of the existing report/stats layer to keep after the trim.
- Which real project hosts the first dogfood (the reply classifier code path).

## Risks

- Static scanning misses dynamic prompts, wrapped model calls and database-configured behavior; the skill must report uncertainty.
- Adapters need the real code to run, which may need credentials or services; setup can stall there.
- Agents may misuse the CLI (skip hypotheses, retry until pass, edit goldens). Test with a fresh Claude Code session before trusting it.
- Scrubbing removes metadata leakage, not stylistic fingerprints; canaries and calibration are the backstop.
