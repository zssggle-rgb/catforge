# Goal 3 Prompt: TV Asset Workbench + 1000-SKU Production Deliverables

We already have a CatForge MVP with a running dashboard. The dashboard only shows coarse pipeline cards and is insufficient for production delivery.

Goal:
Implement the missing production workbench for TV category assets and 1000-SKU deliverables.

Read:
- docs/01_tv_1000sku_asset_outputs.md
- docs/02_asset_generation_lineage.md
- docs/03_required_pages.md
- docs/04_api_contracts.md
- docs/05_acceptance_tests.md
- docs/06_data_model_additions.md
- schemas/*.json

Implement:
1. TV asset library pages:
   - Standard Parameter Library
   - Standard Claim Library
   - Comment Topic Library
   - User Task Library
   - Target Group Library
   - Value Battlefield Library
   - Mapping Rules Workbench
2. 1000-SKU production result pages:
   - SKU Analysis Result Table
   - Single SKU Analysis Detail
   - Competitor Result and Evidence Cards
   - Market Calibration Report
3. Data lineage:
   - Every asset row must show how it was generated:
     raw source fields, derived features, mappings, metrics, evidence_ids, confidence, review_status, version.
4. API endpoints and persistence required by docs/04 and docs/06.
5. Runtime asset export preview:
   - Show exactly what will be exported in the TV runtime asset pack.
   - Do not export factory-only tools, prompt templates, raw expert annotation files, or category-generation scripts.
6. Acceptance tests in docs/05.

Constraints:
- Do not focus on visual decoration. Production usefulness matters.
- Do not hardcode demo-only rows. Use imported source data and generated/persisted assets.
- If no real 1000-SKU file is present, provide fixture-driven behavior and clear empty states.
- Preserve existing UI routes and pipeline buttons.
- Do not remove Goal 1/Goal 2 behavior.
- Every analytical result must include evidence_ids, confidence, rule_version, asset_version, and review_status.
- Missing values are unknown, not false.

Acceptance:
- A user can import SKU/model, market fact, parameter, claim, and comment datasets.
- The system can show candidate and released TV asset libraries.
- Each asset library row shows source basis and review status.
- The 1000-SKU result table shows SKU task scores, target groups, battlefield assignments, claim value layers, competitor counts, and review flags.
- A single SKU detail page shows signal card, normalized parameters, activated claims, comment evidence, tasks, target groups, battlefields, claim value layers, competitors, and evidence cards.
- Calibration report shows coverage, PSI, SSI, CPI, sample sufficiency, review queue summary, and quality metrics.
- Tests pass.
