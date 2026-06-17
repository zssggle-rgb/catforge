# Asset and Rule Version Governance

## Versioned objects
- rule_set
- asset_package
- standard parameter library
- standard claim library
- comment topic library
- user task library
- battlefield library
- competitor rules
- scoring configuration

## Lifecycle
- `draft`: editable.
- `in_review`: editable only by reviewer or admin, with comments.
- `released`: immutable and used by production analysis/export.
- `archived`: read-only, not used for new jobs.

## Immutability
Released versions must never be modified in place. Any change creates a new draft version.

## Release manifest
Each release must have:
- `asset_version`
- `rule_versions`
- `input_dataset_fingerprint`
- `evaluation_report_id`
- `quality_gates`
- `created_by`
- `approved_by`
- `release_time`
- `content_hash`

## Diff
Support diff between two versions at least at file/table row level:
- added/removed/changed parameters
- added/removed/changed claims
- changed thresholds/weights
- changed competitor rules

## Rollback
Rollback creates a new release that references a prior released manifest. It does not mutate old versions.
