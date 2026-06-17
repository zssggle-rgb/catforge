# CatForge Goal 1 — Core Analysis Engine

This pack is for the first Codex Goal run after the MVP scaffold/UI is already working.

## Goal
Turn the MVP from a UI/scaffold into a real deterministic analysis engine vertical slice for the TV category.

## Scope
Implement:
1. Configurable rule DSL engine, replacing hard-coded heuristics.
2. Feature extraction and evidence model for parameters, claims, comments, tasks, battlefields, and market facts.
3. Real competitor engine with candidate pool, component scores, ranking, competitor type classification, and evidence cards.
4. Gold Set import, evaluation metrics, and simple calibration/grid-search for weights and thresholds.
5. Tests and sample TV fixture proving the end-to-end pipeline.

## Explicit non-goals for Goal 1
Do not focus on UI redesign, production job hardening, audit lifecycle, export boundary hardening, cross-category generation, Prompt Lab, external LLM calls, or enterprise SSO. Those belong to Goal 2 or later.

## Recommended branch
`goal-1-core-engine`

## Run order
Run Goal 1 before Goal 2. Goal 2 assumes Goal 1 has a working rule engine, competitor engine, and evaluation pipeline.
