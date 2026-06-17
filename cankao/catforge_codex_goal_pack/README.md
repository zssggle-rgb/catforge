# CatForge Codex Goal Pack

This pack is prepared for using Codex Goal Mode to generate the first runnable implementation of **CatForge / 品铸**, an internal category asset production tool.

Recommended usage:

1. Create a GitHub repository named `catforge`.
2. Copy this pack into the repository root.
3. Add the two upstream design documents:
   - `docs/source/品类生产工具_PRD_v0.1.docx` or markdown export
   - `docs/source/品类生产工具_产品开发详细设计_v0.1.docx` or markdown export
4. Open Codex Goal Mode and paste `prompts/goal_prompt_full.md`.
5. Ask Codex to implement the vertical-slice MVP, not the full production system in one pass.

Important boundary:

- CatForge is the internal category factory.
- Runtime deliverables are generated asset packs and runtime services for authorized categories.
- Do not export factory-only logic, prompt templates, benchmark builders, cross-category migration tools, or internal generation scripts into the runtime deliverable.
