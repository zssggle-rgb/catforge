# Goal 2 Data Model Additions

## job_run
- job_id
- job_type
- project_id
- idempotency_key
- input_fingerprint
- status
- attempt_count
- max_attempts
- checkpoint_json
- result_ref
- error_code
- error_message
- created_by
- created_at
- started_at
- finished_at

Unique index:
- project_id, job_type, idempotency_key, input_fingerprint

## job_attempt
- attempt_id
- job_id
- attempt_no
- worker_id
- started_at
- finished_at
- status
- error_code
- error_message

## asset_version
- asset_version_id
- asset_type
- category
- version
- lifecycle_status
- content_hash
- manifest_json
- created_by
- approved_by
- released_at

## asset_diff
- diff_id
- from_version
- to_version
- diff_json
- created_at

## audit_event
- audit_id
- actor_id
- action
- object_type
- object_id
- project_id
- before_hash
- after_hash
- metadata_json
- created_at

## runtime_export
- export_id
- project_id
- asset_version_id
- status
- manifest_json
- file_path
- content_hash
- created_by
- created_at
