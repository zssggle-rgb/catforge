# 00. Business Context

CatForge / 品铸 is an internal category asset production tool.

It converts observable market data into category assets used by a third-party competitive-analysis intelligent agent. Observable inputs include SKU master data, standard parameters, marketing claims, prices, sales volume, channels, time windows, and user comments.

The system should produce:

- Standard parameter library
- Standard claim library
- Comment topic library
- User task library
- Target customer group library
- Value battlefield library
- Parameter-to-claim mappings
- Claim-to-task-and-battlefield mappings
- Claim value-layer rules
- Competitor identification rules
- Human review queue
- Evaluation cases / Gold Set records
- Runtime asset package for authorized categories

The product must preserve a strict boundary:

- Internal factory: generation, clustering, calibration, evaluation, release.
- Runtime deliverable: approved single-category asset pack and runtime configuration.

For MVP, implement the vertical slice for TV only.

## Source analytical chain

Input data → SKU fact store → parameter normalization → claim extraction and mapping → comment topic recognition → claim activation → user task scoring → target group inference → battlefield scoring → claim value layering → competitor rule generation → review → evaluation → runtime asset export.
