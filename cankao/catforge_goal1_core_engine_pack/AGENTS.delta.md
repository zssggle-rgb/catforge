# AGENTS Delta for Goal 1

Apply these instructions in addition to the repository AGENTS.md.

## Do
- Preserve the existing MVP app and UI.
- Add deterministic backend engine capabilities first.
- Use config-driven YAML/JSON rule files; avoid new hard-coded category heuristics.
- Every analytical output must include: `evidence_ids`, `confidence`, `rule_version`, `asset_version`, and `review_status`.
- Treat missing values as `unknown`, not `false`.
- Implement tests for every engine module.
- Keep external LLM calls optional and disabled by default.

## Do not
- Do not redesign the frontend as the main deliverable.
- Do not implement cross-category factory automation.
- Do not export factory-only logic.
- Do not produce final business conclusions without evidence references.
- Do not hide errors behind generic success states.
