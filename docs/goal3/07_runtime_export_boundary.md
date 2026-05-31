# 07 Runtime Export Boundary

Goal 3 uses the Goal 2 runtime export boundary in `docs/goal2/04_runtime_export_boundary_spec.md`.

Runtime export is a bounded asset-pack preview and release gate. It may include only:

- TV category semantic asset pack
- TV SKU analysis result pack
- TV market calibration report
- runtime scoring rules
- competitor runtime rules
- evidence cards
- release manifest

It must not include factory-only content:

- prompt templates
- Gold Set builders
- rule generators
- semantic clustering internals
- category generation scripts
- cross-category migration tools
- raw expert annotations
- factory run logs

The export preview page must describe CatForge as an internal category asset production line and must not present the workbench as a customer-facing terminal product.
