"""Shared constants for Core3 real-data v2."""

from __future__ import annotations

from enum import StrEnum


class Core3CategoryCode(StrEnum):
    TV = "TV"


class Core3ModuleCode(StrEnum):
    M00 = "M00"
    M01 = "M01"
    M02 = "M02"
    M03 = "M03"
    M03B = "M03B"
    M04A = "M04a"
    M04C = "M04C"
    M05 = "M05"
    M05C = "M05C"
    M06 = "M06"
    M04B = "M04b"
    M07 = "M07"
    M08 = "M08"
    M08_4 = "M08.4"
    M08_5 = "M08.5"
    M09 = "M09"
    M09C = "M09C"
    M10 = "M10"
    M10C = "M10C"
    M11 = "M11"
    M11C = "M11C"
    M11D = "M11D"
    M11_5 = "M11.5"
    M11_6 = "M11.6"
    M11_7 = "M11.7"
    M12C = "M12C"
    M12 = "M12"
    M13 = "M13"
    M14 = "M14"
    M15 = "M15"
    M16 = "M16"


class Core3RunMode(StrEnum):
    BOOTSTRAP_FULL = "bootstrap_full"
    DAILY_INCREMENTAL = "daily_incremental"
    RULESET_REPLAY = "ruleset_replay"
    SINGLE_TARGET_REFRESH = "single_target_refresh"
    REVIEW_REWORK = "review_rework"
    ACCEPTANCE_ONLY = "acceptance_only"


class Core3RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    WARNING = "warning"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"
    FAILED = "failed"
    SKIPPED_REUSED = "skipped_reused"
    SKIPPED_BY_DEPENDENCY = "skipped_by_dependency"
    RELEASED = "released"
    DEPRECATED = "deprecated"


class Core3PipelineTriggerType(StrEnum):
    DATA_CHANGE = "data_change"
    RULE_CHANGE = "rule_change"
    MANUAL = "manual"
    REVIEW = "review"
    EXPORT_ACCEPTANCE = "export_acceptance"


class Core3PipelinePlannedAction(StrEnum):
    RUN = "run"
    REUSE = "reuse"
    BLOCK = "block"
    SKIP = "skip"


class Core3PipelineDependencyStatus(StrEnum):
    VALID = "valid"
    CURRENT = "current"
    REUSED = "reused"
    MISSING = "missing"
    FAILED = "failed"
    INVALID = "invalid"


class Core3PipelineReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    WAIVED = "waived"
    RESOLVED = "resolved"


class Core3PipelineReviewDecisionType(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    WAIVE = "waive"
    REQUEST_DATA = "request_data"
    REWORK_RULE = "rework_rule"


class Core3PipelineAcceptanceStatus(StrEnum):
    PASSED = "passed"
    PASSED_WITH_WARNING = "passed_with_warning"
    FAILED = "failed"


class Core3PipelineWatermarkScope(StrEnum):
    SOURCE_TABLE = "source_table"
    MODULE = "module"
    TARGET_SKU = "target_sku"


class Core3ReleaseGateStatus(StrEnum):
    NOT_READY = "not_ready"
    REVIEW_REQUIRED = "review_required"
    RELEASABLE = "releasable"
    RELEASED = "released"
    BLOCKED = "blocked"


class Core3DataDomain(StrEnum):
    SKU = "sku"
    MARKET = "market"
    PARAM = "param"
    CLAIM = "claim"
    COMMENT = "comment"
    QUALITY = "quality"
    PROFILE = "profile"
    ONTOLOGY = "ontology"
    TASK = "task"
    TARGET_GROUP = "target_group"
    BATTLEFIELD = "battlefield"
    CLAIM_VALUE = "claim_value"
    CANDIDATE = "candidate"
    SCORE = "score"
    SELECTION = "selection"
    REPORT = "report"


class Core3EvidenceType(StrEnum):
    SKU_FACT = "sku_fact"
    MARKET_FACT = "market_fact"
    PARAM_RAW = "param_raw"
    PROMO_RAW = "promo_raw"
    PROMO_SENTENCE = "promo_sentence"
    COMMENT_RAW = "comment_raw"
    COMMENT_SENTENCE = "comment_sentence"
    COMMENT_DIMENSION = "comment_dimension"
    QUALITY_ISSUE = "quality_issue"


class Core3EvidenceGrain(StrEnum):
    SKU = "sku"
    ROW = "row"
    FIELD = "field"
    SENTENCE = "sentence"
    DIMENSION = "dimension"
    QUALITY = "quality"


class Core3EvidenceStatus(StrEnum):
    CURRENT = "current"
    INACTIVE = "inactive"
    SUPERSEDED = "superseded"
    SKIPPED = "skipped"


class Core3EvidenceInactiveReason(StrEnum):
    CLEAN_RECORD_INACTIVE = "clean_record_inactive"
    SOURCE_ROW_NOT_SEEN = "source_row_not_seen"
    QUALITY_ISSUE_RESOLVED = "quality_issue_resolved"
    SUPERSEDED_BY_CLEAN_HASH = "superseded_by_clean_hash"
    LOW_VALUE_SKIPPED = "low_value_skipped"
    SERVICE_FULFILLMENT_SKIPPED = "service_fulfillment_skipped"
    DUPLICATE_REPRESENTATIVE_SKIPPED = "duplicate_representative_skipped"
    COMMENT_TEMPLATE_SKIPPED = "comment_template_skipped"
    MANUAL_REJECTED = "manual_rejected"


class Core3EvidenceLinkType(StrEnum):
    SAME_SOURCE_ROW = "same_source_row"
    SAME_CLEAN_RECORD = "same_clean_record"
    HAS_SENTENCE = "has_sentence"
    HAS_DIMENSION = "has_dimension"
    HAS_QUALITY_ISSUE = "has_quality_issue"
    SAME_COMMENT = "same_comment"
    SAME_COMMENT_TEXT = "same_comment_text"
    SAME_SEGMENT = "same_segment"
    SUPERSEDES = "supersedes"


class Core3EvidenceLinkStatus(StrEnum):
    CURRENT = "current"
    INACTIVE = "inactive"
    SUPERSEDED = "superseded"


class Core3ConfidenceLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class Core3TargetScopeType(StrEnum):
    ALL_SKU = "all_sku"
    TARGET_SKU_LIST = "target_sku_list"
    CHANGED_SKU = "changed_sku"
    DEMO_TARGET = "demo_target"


class Core3ReviewSeverity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKER = "blocker"


class Core3ModuleTargetScope(StrEnum):
    BATCH = "batch"
    SKU = "sku"
    TARGET_SKU = "target_sku"
    CANDIDATE = "candidate"
    REPORT = "report"


class Core3SourceBatchType(StrEnum):
    FULL = "full"
    INCREMENTAL = "incremental"


class Core3SourceBatchStatus(StrEnum):
    RUNNING = "running"
    REGISTERED = "registered"
    REGISTERED_WITH_WARNING = "registered_with_warning"
    FAILED = "failed"


class Core3SourceOperationType(StrEnum):
    INSERT = "insert"
    UPDATE = "update"
    NO_CHANGE = "no_change"
    NOT_SEEN_IN_CURRENT_SCAN = "not_seen_in_current_scan"
    SKIPPED = "skipped"


class Core3SourceImpactLevel(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Core3SourcePkStrategy(StrEnum):
    ID_COLUMN = "id_column"
    BUSINESS_KEY_HASH = "business_key_hash"
    COMPOSITE_KEY = "composite_key"


class Core3ReviewStatus(StrEnum):
    AUTO_PASS = "auto_pass"
    REVIEW_REQUIRED = "review_required"
    APPROVED = "approved"
    REJECTED = "rejected"
    WAIVED = "waived"


class Core3FieldPresenceStatus(StrEnum):
    PRESENT = "present"
    NULL = "null"
    EMPTY_STRING = "empty_string"
    DASH = "dash"
    UNKNOWN_LITERAL = "unknown_literal"
    MISSING_COLUMN = "missing_column"


class Core3ValuePresenceStatus(StrEnum):
    PRESENT = "present"
    NULL = "null"
    EMPTY = "empty"
    DASH = "dash"
    UNKNOWN_LITERAL = "unknown_literal"
    MISSING_COLUMN = "missing_column"


class Core3CleanRecordStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE_CANDIDATE = "inactive_candidate"
    SKIPPED = "skipped"


class Core3CleanQualityStatus(StrEnum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


class Core3QualityIssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class Core3QualityIssueType(StrEnum):
    MISSING_REQUIRED_FIELD = "missing_required_field"
    INVALID_NUMBER = "invalid_number"
    NEGATIVE_NUMBER = "negative_number"
    PRICE_CHECK_MISMATCH = "price_check_mismatch"
    UNKNOWN_VALUE = "unknown_value"
    CROSS_TABLE_CONFLICT = "cross_table_conflict"
    CLAIM_COVERAGE_MISSING = "claim_coverage_missing"
    CLAIM_SEQ_PARSE_FAILED = "claim_seq_parse_failed"
    LOW_VALUE_COMMENT = "low_value_comment"
    DUPLICATE_COMMENT_TEXT = "duplicate_comment_text"
    COMMENT_DIMENSION_MISSING = "comment_dimension_missing"
    COMMENT_SPLIT_ROW_SUSPECTED = "comment_split_row_suspected"
    SCHEMA_CHANGED = "schema_changed"
    CLEAN_HASH_CHANGED_HIGH = "clean_hash_changed_high"


CORE3_REAL_DATA_VERSION = "real-data-v2-mvp-0.1.0"
CORE3_DEFAULT_RULESET_VERSION = "tv-core3-real-data-v2-0.1.0"
CORE3_M00_MODULE_VERSION = "m00-source-registry-0.1.0"
CORE3_M00_ROW_HASH_VERSION = "m00_row_hash_v1"
CORE3_M01_MODULE_VERSION = "m01-cleaning-quality-0.1.0"
CORE3_M01_CLEAN_VERSION = "m01_clean_v1"
CORE3_M01_CLEAN_HASH_VERSION = "m01_clean_hash_v1"
CORE3_M02_MODULE_VERSION = "m02-evidence-atom-0.1.0"
CORE3_M02_EVIDENCE_VERSION = "m02_evidence_v1"
CORE3_M02_CONFIDENCE_RULE_VERSION = "m02_confidence_v1"
CORE3_M03_MODULE_VERSION = "m03-param-extraction-0.1.0"
CORE3_M03_SEED_VERSION = "tv_core3_mvp_seed_v0_2"
CORE3_M03_PARSER_VERSION = "m03_parser_v1"
CORE3_M03_RULE_VERSION = "m03_param_v1"
CORE3_M03B_MODULE_VERSION = "m03b-sku-param-profile-0.1.0"
CORE3_M03B_TAXONOMY_VERSION = "tv_param_taxonomy_manual_v0.1"
CORE3_M03B_PARSER_VERSION = "m03b_tv_parser_v0.1"
CORE3_M03B_RULE_VERSION = "m03b_tv_param_profile_v0.1"
CORE3_M03B_AC_TAXONOMY_VERSION = "ac_param_taxonomy_manual_v0.1"
CORE3_M03B_AC_PARSER_VERSION = "m03b_ac_parser_v0.1"
CORE3_M03B_AC_RULE_VERSION = "m03b_ac_param_profile_v0.1"
CORE3_M04A_MODULE_VERSION = "m04a-base-claim-activation-0.1.0"
CORE3_M04A_SEED_VERSION = "tv_core3_mvp_seed_v0_2"
CORE3_M04A_RULE_VERSION = "m04a_claim_activation_v1"
CORE3_M04C_MODULE_VERSION = "m04c-claim-fact-profile-0.1.0"
CORE3_M04C_TV_TAXONOMY_VERSION = "tv_claim_taxonomy_manual_v0.1"
CORE3_M04C_TV_RULE_VERSION = "m04c_tv_claim_fact_profile_v0.1"
CORE3_M05_MODULE_VERSION = "m05-comment-evidence-0.1.0"
CORE3_M05_SEED_VERSION = "tv_core3_mvp_seed_v0_2"
CORE3_M05_RULE_VERSION = "m05_comment_evidence_v1"
CORE3_M05C_MODULE_VERSION = "m05c-comment-fact-profile-0.1.0"
CORE3_M05C_TV_TAXONOMY_VERSION = "tv_comment_fact_taxonomy_manual_v0.1"
CORE3_M05C_TV_RULE_VERSION = "m05c_tv_comment_fact_profile_v0.1"
CORE3_M06_MODULE_VERSION = "m06-comment-downstream-signal-0.1.0"
CORE3_M06_SEED_VERSION = "tv_core3_mvp_seed_v0_2"
CORE3_M06_RULE_VERSION = "m06_comment_downstream_signal_v1"
CORE3_M04B_MODULE_VERSION = "m04b-claim-comment-enhancement-0.1.0"
CORE3_M04B_SEED_VERSION = "tv_core3_mvp_seed_v0_2"
CORE3_M04B_RULE_VERSION = "m04b_claim_comment_enhancement_v1"
CORE3_M07_MODULE_VERSION = "m07-market-profile-0.1.0"
CORE3_M07_RULE_VERSION = "m07_market_profile_v1"
CORE3_M07_PRICE_BAND_RULE_VERSION = "m07_price_band_v1"
CORE3_M07_POOL_RULE_VERSION = "m07_pool_v1"
CORE3_M09C_MODULE_VERSION = "m09c-user-task-profile-0.1.0"
CORE3_M09C_TV_TAXONOMY_VERSION = "m09c_tv_user_task_taxonomy_v0.1"
CORE3_M09C_TV_RULE_VERSION = "m09c_tv_user_task_profile_v0.2"
CORE3_M10C_MODULE_VERSION = "m10c-target-group-profile-0.1.0"
CORE3_M10C_TV_TAXONOMY_VERSION = "m10c_tv_target_group_taxonomy_v0.1"
CORE3_M10C_TV_RULE_VERSION = "m10c_tv_target_group_profile_v0.2"
CORE3_M11C_MODULE_VERSION = "m11c-value-battlefield-profile-0.1.0"
CORE3_M11C_TV_TAXONOMY_VERSION = "m11c_tv_value_battlefield_taxonomy_v0.2"
CORE3_M11C_TV_RULE_VERSION = "m11c_tv_value_battlefield_profile_v0.2"
CORE3_M08_MODULE_VERSION = "m08-sku-signal-profile-0.1.0"
CORE3_M08_RULE_VERSION = "m08_sku_signal_profile_v1"
CORE3_M08_FEATURE_VERSION = "core3_mvp_real_data_v2_m08_v1"
CORE3_M08_VIEW_SCHEMA_VERSION = "m08_downstream_feature_view_v1"
CORE3_M08_4_MODULE_VERSION = "m08-4-comment-native-dimension-0.1.0"
CORE3_M08_4_RULE_VERSION = "core3_mvp_real_data_v2_m08_4_v1"
CORE3_M08_4_SEED_VERSION = "tv_core3_mvp_seed_v0_2"
CORE3_M08_5_MODULE_VERSION = "m08-5-dimension-ontology-0.1.0"
CORE3_M08_5_RULE_VERSION = "core3_mvp_real_data_v2_m08_5_v1"
CORE3_M08_5_SEED_VERSION = "tv_core3_mvp_seed_v0_2"
CORE3_M08_5_SERVICE_GUARDRAIL_VERSION = "service_guardrail_v1"
CORE3_M08_5_THRESHOLD_VERSION = "ontology_threshold_v1"
CORE3_M09_MODULE_VERSION = "m09-user-task-0.1.0"
CORE3_M09_RULE_VERSION = "core3_mvp_real_data_v2_m09_v1"
CORE3_M09_SEED_VERSION = "tv_core3_mvp_seed_v0_2"
CORE3_M10_MODULE_VERSION = "m10-target-group-0.1.0"
CORE3_M10_RULE_VERSION = "core3_mvp_real_data_v2_m10_v1"
CORE3_M10_SEED_VERSION = "tv_core3_mvp_seed_v0_2"
CORE3_M11_MODULE_VERSION = "m11-battlefield-0.1.0"
CORE3_M11_RULE_VERSION = "core3_mvp_real_data_v2_m11_v1"
CORE3_M11_SEED_VERSION = "tv_core3_mvp_seed_v0_2"
CORE3_M11_5_MODULE_VERSION = "m11-5-claim-value-layer-0.1.0"
CORE3_M11_5_RULE_VERSION = "core3_mvp_real_data_v2_m11_5_v1"
CORE3_M11_5_CLAIM_SEED_VERSION = "tv_core3_mvp_seed_v0_2"
CORE3_M11_5_BATTLEFIELD_SEED_VERSION = "tv_core3_mvp_seed_v0_2"
CORE3_M11_6_MODULE_VERSION = "m11-6-sku-business-profile-0.1.0"
CORE3_M11_6_RULE_VERSION = "core3_mvp_real_data_v2_m11_6_v2"
CORE3_M11_7_MODULE_VERSION = "m11-7-dimension-sales-reconciliation-0.1.0"
CORE3_M11_7_RULE_VERSION = "core3_mvp_real_data_v2_m11_7_v1"
CORE3_M11D_MODULE_VERSION = "m11d-semantic-market-graph-allocation-0.1.0"
CORE3_M11D_RULE_VERSION = "m11d_semantic_market_allocation_v0.1"
CORE3_M12C_MODULE_VERSION = "m12c-claim-value-quantification-0.1.0"
CORE3_M12C_RULE_VERSION = "m12c_claim_value_quantification_v0.1"
CORE3_M12_MODULE_VERSION = "m12-candidate-recall-0.1.0"
CORE3_M12_RULE_VERSION = "core3_mvp_real_data_v2_m12_v1"
CORE3_M13_MODULE_VERSION = "m13-component-scoring-0.1.0"
CORE3_M13_RULE_VERSION = "core3_mvp_real_data_v2_m13_v1"
CORE3_M13_COMPONENT_RULE_VERSION = "m13_component_formula_v1"
CORE3_M13_ROLE_RULE_VERSION = "m13_role_formula_v1"
CORE3_M14_MODULE_VERSION = "m14-core3-selection-0.1.0"
CORE3_M14_RULE_VERSION = "core3_mvp_real_data_v2_m14_v1"
CORE3_M15_MODULE_VERSION = "m15-evidence-report-0.1.0"
CORE3_M15_RULE_VERSION = "core3_mvp_real_data_v2_m15_v1"
CORE3_M16_MODULE_VERSION = "m16-pipeline-governance-0.1.0"
CORE3_M16_RULE_VERSION = "core3_mvp_real_data_v2_m16_v1"

CORE3_M09_EXPECTED_TASK_CODES: tuple[str, ...] = (
    "TASK_LIVING_ROOM_CINEMA",
    "TASK_PREMIUM_PICTURE_AV",
    "TASK_GAMING_ENTERTAINMENT",
    "TASK_SPORTS_WATCHING",
    "TASK_LARGE_SCREEN_REPLACEMENT",
    "TASK_CHILD_EYE_CARE",
    "TASK_SENIOR_EASY_USE",
    "TASK_VALUE_PURCHASE",
    "TASK_NEW_HOME_DECORATION",
    "TASK_BEDROOM_SECOND_TV",
)


class M09TaskCandidateStatus(StrEnum):
    ACTIVE = "active"
    REJECTED = "rejected"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"


class M09TaskCandidateSource(StrEnum):
    PARAM = "param"
    CLAIM = "claim"
    COMMENT = "comment"
    MARKET = "market"
    PRICE_PERCEPTION = "price_perception"
    SERVICE_SIGNAL = "service_signal"
    SEED_GAP = "seed_gap"


class M09TaskRelationLevel(StrEnum):
    MAIN = "main"
    SECONDARY = "secondary"
    WEAK = "weak"
    INSUFFICIENT = "insufficient"
    BLOCKED = "blocked"


class M09TaskEvidenceDomain(StrEnum):
    PARAM = "param"
    CLAIM = "claim"
    COMMENT = "comment"
    MARKET = "market"
    RISK = "risk"
    SEED = "seed"
    PROFILE = "profile"


class M09TaskSupportLevel(StrEnum):
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"
    MISSING = "missing"
    CONFLICT = "conflict"
    NOT_APPLICABLE = "not_applicable"


class M09TaskReviewIssueType(StrEnum):
    MISSING_FEATURE_VIEW = "missing_feature_view"
    MISSING_FEATURE = "missing_feature"
    CONFLICT = "conflict"
    COMMENT_ONLY = "comment_only"
    SERVICE_ONLY = "service_only"
    SINGLE_PARAM_ONLY = "single_param_only"
    MARKET_LIMITED = "market_limited"
    CLAIM_MISSING = "claim_missing"
    COMMENT_QUALITY_RISK = "comment_quality_risk"
    SEED_GAP = "seed_gap"
    HIGH_SCORE_CONTRADICTION = "high_score_contradiction"
    PROFILE_BLOCKED = "profile_blocked"
    MISSING_STRUCTURED_CLAIM = "missing_structured_claim"
    PARAM_ONLY = "param_only"
    UNKNOWN_INPUT = "unknown_input"


CORE3_M09_EVIDENCE_DOMAINS: tuple[M09TaskEvidenceDomain, ...] = (
    M09TaskEvidenceDomain.PARAM,
    M09TaskEvidenceDomain.CLAIM,
    M09TaskEvidenceDomain.COMMENT,
    M09TaskEvidenceDomain.MARKET,
    M09TaskEvidenceDomain.RISK,
    M09TaskEvidenceDomain.SEED,
    M09TaskEvidenceDomain.PROFILE,
)

CORE3_M09_FORBIDDEN_OUTPUT_FIELDS: tuple[str, ...] = (
    "target_group_code",
    "battlefield_code",
    "claim_value_layer",
    "candidate_sku_code",
    "competitor_sku_code",
    "component_score",
    "competitor_role",
    "selection_slot",
    "core3_rank",
    "business_conclusion",
    "report_payload",
    "price_wavg_12m",
    "sales_volume_12m",
    "sales_amount_12m",
)

CORE3_M10_EXPECTED_TARGET_GROUP_CODES: tuple[str, ...] = (
    "TG_FAMILY_UPGRADE",
    "TG_AV_QUALITY_SEEKER",
    "TG_GAMER",
    "TG_SPORTS_FAN",
    "TG_SENIOR_FAMILY",
    "TG_CHILD_FAMILY",
    "TG_VALUE_BUYER",
    "TG_NEW_HOME_DECORATOR",
    "TG_BEDROOM_SECOND_TV",
)


class M10TargetGroupCandidateStatus(StrEnum):
    ACTIVE = "active"
    REJECTED = "rejected"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"


class M10TargetGroupCandidateSource(StrEnum):
    TASK = "task"
    COMMENT = "comment"
    PRICE_CHANNEL = "price_channel"
    MARKET = "market"
    SERVICE = "service"
    SEED_HINT = "seed_hint"
    SEED_GAP = "seed_gap"


class M10TargetGroupRelationLevel(StrEnum):
    MAIN = "main"
    SECONDARY = "secondary"
    WEAK = "weak"
    INSUFFICIENT = "insufficient"
    BLOCKED = "blocked"


class M10TargetGroupEvidenceDomain(StrEnum):
    TASK = "task"
    COMMENT = "comment"
    PRICE_CHANNEL = "price_channel"
    MARKET = "market"
    SERVICE = "service"
    RISK = "risk"
    SEED = "seed"
    PROFILE = "profile"


class M10TargetGroupSupportLevel(StrEnum):
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"
    MISSING = "missing"
    CONFLICT = "conflict"
    NOT_APPLICABLE = "not_applicable"


class M10TargetGroupReviewIssueType(StrEnum):
    MISSING_FEATURE_VIEW = "missing_feature_view"
    MISSING_TASK_SCORE = "missing_task_score"
    ONLY_COMMENT = "only_comment"
    ONLY_SERVICE = "only_service"
    PRICE_MISMATCH = "price_mismatch"
    MARKET_LIMITED = "market_limited"
    TASK_CONFLICT = "task_conflict"
    TASK_REVIEW_INHERITED = "task_review_inherited"
    COMMENT_QUALITY_RISK = "comment_quality_risk"
    SEED_GAP = "seed_gap"
    PROFILE_BLOCKED = "profile_blocked"
    HIGH_SCORE_CONTRADICTION = "high_score_contradiction"


CORE3_M10_EVIDENCE_DOMAINS: tuple[M10TargetGroupEvidenceDomain, ...] = (
    M10TargetGroupEvidenceDomain.TASK,
    M10TargetGroupEvidenceDomain.COMMENT,
    M10TargetGroupEvidenceDomain.PRICE_CHANNEL,
    M10TargetGroupEvidenceDomain.MARKET,
    M10TargetGroupEvidenceDomain.SERVICE,
    M10TargetGroupEvidenceDomain.RISK,
    M10TargetGroupEvidenceDomain.SEED,
    M10TargetGroupEvidenceDomain.PROFILE,
)

CORE3_M10_FORBIDDEN_OUTPUT_FIELDS: tuple[str, ...] = (
    "battlefield_code",
    "claim_value_layer",
    "candidate_sku_code",
    "competitor_sku_code",
    "component_score",
    "competitor_role",
    "selection_slot",
    "core3_rank",
    "business_conclusion",
    "report_payload",
    "price_wavg_12m",
    "sales_volume_12m",
    "sales_amount_12m",
)

CORE3_M11_EXPECTED_BATTLEFIELD_CODES: tuple[str, ...] = (
    "BF_PREMIUM_PICTURE",
    "BF_FAMILY_VIEWING_UPGRADE",
    "BF_GAMING_SPORTS",
    "BF_LARGE_SCREEN_VALUE",
    "BF_FAMILY_EYE_CARE",
    "BF_SENIOR_EASE_OF_USE",
    "BF_SMART_SYSTEM_EXPERIENCE",
    "BF_CINEMA_AUDIO_IMMERSION",
    "BF_DESIGN_HOME_FIT",
    "BF_SERVICE_ASSURANCE",
)


class M11BattlefieldCandidateStatus(StrEnum):
    ACTIVE = "active"
    REJECTED = "rejected"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"


class M11BattlefieldCandidateSource(StrEnum):
    TASK = "task"
    TARGET_GROUP = "target_group"
    CLAIM = "claim"
    PARAM = "param"
    COMMENT = "comment"
    MARKET = "market"
    SERVICE = "service"
    SEED_HINT = "seed_hint"
    SEED_GAP = "seed_gap"


class M11BattlefieldRelationLevel(StrEnum):
    MAIN = "main"
    SECONDARY = "secondary"
    OPPORTUNITY = "opportunity"
    WEAK = "weak"
    INSUFFICIENT = "insufficient"
    BLOCKED = "blocked"


class M11BattlefieldEvidenceDomain(StrEnum):
    TASK = "task"
    TARGET_GROUP = "target_group"
    CLAIM = "claim"
    PARAM = "param"
    COMMENT = "comment"
    MARKET = "market"
    SERVICE = "service"
    RISK = "risk"
    SEED = "seed"
    PROFILE = "profile"


class M11BattlefieldSupportLevel(StrEnum):
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"
    MISSING = "missing"
    CONFLICT = "conflict"
    NOT_APPLICABLE = "not_applicable"


class M11CompetitorSelectionRole(StrEnum):
    PRIMARY_SEARCH_CONTEXT = "primary_search_context"
    SECONDARY_SEARCH_CONTEXT = "secondary_search_context"
    OPPORTUNITY_MONITORING = "opportunity_monitoring"
    RISK_OR_SERVICE_CONTEXT = "risk_or_service_context"
    NOT_FOR_CORE_SEARCH = "not_for_core_search"


class M11BattlefieldSampleSufficiency(StrEnum):
    SUFFICIENT = "sufficient"
    LIMITED = "limited"
    INSUFFICIENT = "insufficient"
    UNKNOWN = "unknown"


class M11BattlefieldReviewIssueType(StrEnum):
    MISSING_FEATURE_VIEW = "missing_feature_view"
    MISSING_TASK_SCORE = "missing_task_score"
    MISSING_TARGET_GROUP_SCORE = "missing_target_group_score"
    ONLY_COMMENT = "only_comment"
    ONLY_SERVICE = "only_service"
    MARKET_MISSING = "market_missing"
    MARKET_LIMITED = "market_limited"
    CLAIM_MISSING = "claim_missing"
    PARAM_CONFLICT = "param_conflict"
    UPSTREAM_REVIEW = "upstream_review"
    SEED_GAP = "seed_gap"
    PROFILE_BLOCKED = "profile_blocked"
    HIGH_SCORE_CONTRADICTION = "high_score_contradiction"
    SERVICE_AS_CORE_BATTLEFIELD = "service_as_core_battlefield"
    SEED_HINT_ONLY = "seed_hint_only"
    UNKNOWN_INPUT = "unknown_input"
    COMPARABLE_POOL_INSUFFICIENT = "comparable_pool_insufficient"


CORE3_M11_EVIDENCE_DOMAINS: tuple[M11BattlefieldEvidenceDomain, ...] = (
    M11BattlefieldEvidenceDomain.TASK,
    M11BattlefieldEvidenceDomain.TARGET_GROUP,
    M11BattlefieldEvidenceDomain.CLAIM,
    M11BattlefieldEvidenceDomain.PARAM,
    M11BattlefieldEvidenceDomain.COMMENT,
    M11BattlefieldEvidenceDomain.MARKET,
    M11BattlefieldEvidenceDomain.SERVICE,
    M11BattlefieldEvidenceDomain.RISK,
    M11BattlefieldEvidenceDomain.SEED,
    M11BattlefieldEvidenceDomain.PROFILE,
)

CORE3_M11_FORBIDDEN_OUTPUT_FIELDS: tuple[str, ...] = (
    "claim_value_layer",
    "candidate_sku_code",
    "competitor_sku_code",
    "component_score",
    "competitor_role",
    "selection_slot",
    "core3_rank",
    "business_conclusion",
    "report_payload",
    "price_wavg_12m",
    "sales_volume_12m",
    "sales_amount_12m",
)

CORE3_M11_5_EXPECTED_CLAIM_CODES: tuple[str, ...] = (
    "CLAIM_LARGE_SCREEN_IMMERSION",
    "CLAIM_MINI_LED_BACKLIGHT",
    "CLAIM_OLED_SELF_LIT",
    "CLAIM_QLED_WIDE_COLOR",
    "CLAIM_HIGH_BRIGHTNESS_HDR",
    "CLAIM_FINE_LOCAL_DIMMING",
    "CLAIM_HIGH_REFRESH_RATE",
    "CLAIM_GAMING_LOW_LATENCY",
    "CLAIM_HDMI_2_1_GAMING",
    "CLAIM_SPORTS_MOTION_SMOOTH",
    "CLAIM_EYE_CARE_COMFORT",
    "CLAIM_ELDER_FRIENDLY_SMART",
    "CLAIM_SMART_VOICE_EASE",
    "CLAIM_NO_AD_OR_CLEAN_SYSTEM",
    "CLAIM_IMMERSIVE_AUDIO",
    "CLAIM_DOLBY_CINEMA_AUDIO",
    "CLAIM_THIN_DESIGN",
    "CLAIM_ENERGY_SAVING",
    "CLAIM_VALUE_FOR_MONEY",
    "CLAIM_INSTALLATION_SERVICE_ASSURANCE",
)


class M115ClaimCandidateStatus(StrEnum):
    ACTIVE = "active"
    REJECTED = "rejected"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"


class M115ClaimCandidateSource(StrEnum):
    BATTLEFIELD_CORE_CLAIM = "battlefield_core_claim"
    CLAIM_BATTLEFIELD_MAPPING = "claim_battlefield_mapping"
    CLAIM_ACTIVATION = "claim_activation"
    PARAM = "param"
    COMMENT = "comment"
    MARKET = "market"
    SERVICE = "service"
    SEED_GAP = "seed_gap"


class M115BattlefieldRelevanceRole(StrEnum):
    CORE = "core"
    AUXILIARY = "auxiliary"
    SERVICE = "service"
    RISK = "risk"
    NOT_APPLICABLE = "not_applicable"


class M115ClaimValueLayer(StrEnum):
    BASIC_THRESHOLD = "basic_threshold"
    COMPETITIVE_PERFORMANCE = "competitive_performance"
    PREMIUM_TENDENCY = "premium_tendency"
    WEAK_PERCEPTION = "weak_perception"
    INSUFFICIENT_SAMPLE = "insufficient_sample"
    NOT_APPLICABLE = "not_applicable"
    BLOCKED = "blocked"


class M115SampleSufficiency(StrEnum):
    SUFFICIENT = "sufficient"
    LIMITED = "limited"
    INSUFFICIENT = "insufficient"
    UNKNOWN = "unknown"


class M115ClaimValueEvidenceDomain(StrEnum):
    ACTIVATION = "activation"
    PARAM = "param"
    PROMO = "promo"
    COMMENT = "comment"
    PRICE = "price"
    SALES = "sales"
    POOL = "pool"
    MARKET = "market"
    SERVICE = "service"
    RISK = "risk"
    SEED = "seed"
    PROFILE = "profile"


class M115ClaimValueSupportLevel(StrEnum):
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"
    MISSING = "missing"
    CONFLICT = "conflict"
    NOT_APPLICABLE = "not_applicable"


class M115ClaimValueReviewIssueType(StrEnum):
    MISSING_FEATURE_VIEW = "missing_feature_view"
    MISSING_BATTLEFIELD_RESULT = "missing_battlefield_result"
    MISSING_CLAIM_ACTIVATION = "missing_claim_activation"
    INSUFFICIENT_POOL = "insufficient_pool"
    INSUFFICIENT_WITH_CLAIM = "insufficient_with_claim"
    INSUFFICIENT_WITHOUT_CLAIM = "insufficient_without_claim"
    PROMO_MISSING = "promo_missing"
    COMMENT_MISSING = "comment_missing"
    MARKET_MISSING = "market_missing"
    PARAM_CONFLICT = "param_conflict"
    SERVICE_MISUSE = "service_misuse"
    SEED_GAP = "seed_gap"
    PROFILE_BLOCKED = "profile_blocked"
    UPSTREAM_REVIEW = "upstream_review"


CORE3_M11_5_EVIDENCE_DOMAINS: tuple[M115ClaimValueEvidenceDomain, ...] = (
    M115ClaimValueEvidenceDomain.ACTIVATION,
    M115ClaimValueEvidenceDomain.PARAM,
    M115ClaimValueEvidenceDomain.PROMO,
    M115ClaimValueEvidenceDomain.COMMENT,
    M115ClaimValueEvidenceDomain.PRICE,
    M115ClaimValueEvidenceDomain.SALES,
    M115ClaimValueEvidenceDomain.POOL,
    M115ClaimValueEvidenceDomain.MARKET,
    M115ClaimValueEvidenceDomain.SERVICE,
    M115ClaimValueEvidenceDomain.RISK,
    M115ClaimValueEvidenceDomain.SEED,
    M115ClaimValueEvidenceDomain.PROFILE,
)

CORE3_M11_5_FORBIDDEN_OUTPUT_FIELDS: tuple[str, ...] = (
    "candidate_sku_code",
    "competitor_sku_code",
    "component_score",
    "competitor_role",
    "selection_slot",
    "core3_rank",
    "business_conclusion",
    "report_payload",
    "price_wavg_12m",
    "sales_volume_12m",
    "sales_amount_12m",
)


class M12RecallSource(StrEnum):
    COMPARABLE_POOL = "comparable_pool"
    BATTLEFIELD = "battlefield"
    TASK = "task"
    AUDIENCE = "audience"
    CLAIM_VALUE = "claim_value"
    MARKET_PRESSURE = "market_pressure"
    SCENARIO_SERVICE = "scenario_service"


class M12RelationType(StrEnum):
    DIRECT_FIGHT = "direct_fight"
    PRICE_VOLUME_PRESSURE = "price_volume_pressure"
    CONFIGURATION_PRESSURE = "configuration_pressure"
    PREMIUM_BENCHMARK = "premium_benchmark"
    POTENTIAL_DOWNWARD_PRESSURE = "potential_downward_pressure"
    UPGRADE_SUBSTITUTE = "upgrade_substitute"
    DOWNGRADE_SUBSTITUTE = "downgrade_substitute"
    SCENARIO_SUBSTITUTE = "scenario_substitute"
    SERVICE_REFERENCE = "service_reference"


class M12RecallStrength(StrEnum):
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"
    REVIEW_ONLY = "review_only"


class M12RecallStatus(StrEnum):
    SUCCESS = "success"
    LIMITED = "limited"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"
    FAILED = "failed"


class M12PriceRelation(StrEnum):
    LOWER = "lower"
    SIMILAR = "similar"
    HIGHER = "higher"
    UNKNOWN = "unknown"


class M12SizeRelation(StrEnum):
    SAME = "same"
    ADJACENT_LARGER = "adjacent_larger"
    ADJACENT_SMALLER = "adjacent_smaller"
    LARGER_CROSS = "larger_cross"
    SMALLER_CROSS = "smaller_cross"
    UNKNOWN = "unknown"


class M12SampleStatus(StrEnum):
    SUFFICIENT = "sufficient"
    LIMITED = "limited"
    INSUFFICIENT = "insufficient"
    UNKNOWN = "unknown"


class M12SupportLevel(StrEnum):
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"
    MISSING = "missing"
    CONFLICT = "conflict"
    NOT_APPLICABLE = "not_applicable"


class M12ReviewIssueType(StrEnum):
    MISSING_PROFILE = "missing_profile"
    MISSING_FEATURE_VIEW = "missing_feature_view"
    MISSING_BATTLEFIELD_RESULT = "missing_battlefield_result"
    MISSING_CANDIDATE_REASON = "missing_candidate_reason"
    SMALL_CANDIDATE_POOL = "small_candidate_pool"
    SINGLE_SOURCE_CANDIDATE = "single_source_candidate"
    ONLY_SERVICE_SIGNAL = "only_service_signal"
    MARKET_EVIDENCE_MISSING = "market_evidence_missing"
    SEMANTIC_EVIDENCE_MISSING = "semantic_evidence_missing"
    CLAIM_VALUE_MISSING = "claim_value_missing"
    UPSTREAM_REVIEW = "upstream_review"
    INPUT_BLOCKED = "input_blocked"


CORE3_M12_RECALL_SOURCES: tuple[M12RecallSource, ...] = (
    M12RecallSource.COMPARABLE_POOL,
    M12RecallSource.BATTLEFIELD,
    M12RecallSource.TASK,
    M12RecallSource.AUDIENCE,
    M12RecallSource.CLAIM_VALUE,
    M12RecallSource.MARKET_PRESSURE,
    M12RecallSource.SCENARIO_SERVICE,
)

CORE3_M12_FORBIDDEN_OUTPUT_FIELDS: tuple[str, ...] = (
    "competitor_sku_code",
    "competitor_role",
    "selection_slot",
    "core3_rank",
    "final_rank",
    "final_score",
    "competitor_score",
    "business_conclusion",
    "report_payload",
    "report_content",
    "price_wavg_12m",
    "sales_volume_12m",
    "sales_amount_12m",
)


class M13ComponentCode(StrEnum):
    BASE_COMPARABILITY = "base_comparability"
    BATTLEFIELD_FIT = "battlefield_fit"
    TASK_OVERLAP = "task_overlap"
    AUDIENCE_OVERLAP = "audience_overlap"
    PRICE_POSITION = "price_position"
    PRICE_ADVANTAGE = "price_advantage"
    SIZE_FIT = "size_fit"
    CHANNEL_OVERLAP = "channel_overlap"
    PARAM_SIMILARITY = "param_similarity"
    PARAM_SUPERIORITY = "param_superiority"
    CLAIM_CONFRONTATION = "claim_confrontation"
    CLAIM_SUPERIORITY = "claim_superiority"
    CLAIM_THRESHOLD_SUFFICIENCY = "claim_threshold_sufficiency"
    MARKET_THREAT = "market_threat"
    SALES_AMOUNT_STRENGTH = "sales_amount_strength"
    COMMENT_PERCEPTION = "comment_perception"
    PRICE_TREND = "price_trend"
    EVIDENCE_COMPLETENESS = "evidence_completeness"


class M13RoleCode(StrEnum):
    DIRECT_FIGHT = "direct_fight"
    PRICE_VOLUME_PRESSURE = "price_volume_pressure"
    BENCHMARK_POTENTIAL = "benchmark_potential"
    CONFIGURATION_PRESSURE = "configuration_pressure"
    SERVICE_REFERENCE = "service_reference"


class M13SupportLevel(StrEnum):
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"
    MISSING = "missing"
    CONFLICT = "conflict"
    NOT_APPLICABLE = "not_applicable"


class M13SampleStatus(StrEnum):
    SUFFICIENT = "sufficient"
    LIMITED = "limited"
    INSUFFICIENT = "insufficient"
    UNKNOWN = "unknown"


class M13IssueLevel(StrEnum):
    WARNING = "warning"
    REVIEW = "review"
    BLOCKER = "blocker"


class M13IssueScope(StrEnum):
    PAIR = "pair"
    COMPONENT = "component"
    ROLE = "role"
    EVIDENCE = "evidence"


class M13ReviewIssueType(StrEnum):
    MISSING_FEATURE_SNAPSHOT = "missing_feature_snapshot"
    MISSING_CANDIDATE_PROFILE = "missing_candidate_profile"
    NO_MARKET_EVIDENCE = "no_market_evidence"
    NO_SEMANTIC_EVIDENCE = "no_semantic_evidence"
    ONLY_SERVICE_SIGNAL = "only_service_signal"
    HIGH_SCORE_LOW_CONFIDENCE = "high_score_low_confidence"
    PARAM_CONFLICT = "param_conflict"
    CLAIM_MISSING = "claim_missing"
    SAMPLE_INSUFFICIENT = "sample_insufficient"
    COMPONENT_MISSING = "component_missing"
    ROLE_SCORE_MISSING = "role_score_missing"
    SERVICE_OVER_WEIGHTED = "service_over_weighted"
    SAME_FAMILY_DUPLICATE_HIGH_SCORE = "same_family_duplicate_high_score"
    INPUT_BLOCKED = "input_blocked"


CORE3_M13_COMPONENT_CODES: tuple[M13ComponentCode, ...] = tuple(M13ComponentCode)
CORE3_M13_ROLE_CODES: tuple[M13RoleCode, ...] = tuple(M13RoleCode)

CORE3_M13_FORBIDDEN_OUTPUT_FIELDS: tuple[str, ...] = (
    "competitor_sku_code",
    "competitor_role",
    "selection_slot",
    "core3_rank",
    "final_rank",
    "final_score",
    "business_conclusion",
    "report_payload",
    "report_content",
    "price_wavg_12m",
    "sales_volume_12m",
    "sales_amount_12m",
)


class M14SelectionSlot(StrEnum):
    DIRECT_FIGHT = "direct_fight"
    PRICE_VOLUME_PRESSURE = "price_volume_pressure"
    BENCHMARK_POTENTIAL = "benchmark_potential"


class M14SelectionStatus(StrEnum):
    SUCCESS = "success"
    LIMITED = "limited"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"
    FAILED = "failed"


class M14SlotDecisionStatus(StrEnum):
    SELECTED = "selected"
    EMPTY = "empty"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"


class M14AuditDecision(StrEnum):
    SELECTED = "selected"
    REJECTED = "rejected"
    REVIEW = "review"
    BLOCKED = "blocked"


class M14EmptyReasonCode(StrEnum):
    NO_CANDIDATE = "no_candidate"
    LOW_CONFIDENCE = "low_confidence"
    INSUFFICIENT_MARKET_EVIDENCE = "insufficient_market_evidence"
    INSUFFICIENT_SEMANTIC_EVIDENCE = "insufficient_semantic_evidence"
    DUPLICATE_WITH_SELECTED = "duplicate_with_selected"
    SERVICE_ONLY = "service_only"
    SAMPLE_LIMITED = "sample_limited"
    BLOCKED_BY_REVIEW_ISSUE = "blocked_by_review_issue"


class M14PressureLevel(StrEnum):
    HIGH = "high"
    MEDIUM_HIGH = "medium_high"
    MEDIUM = "medium"
    REVIEW_REQUIRED = "review_required"


class M14IssueScope(StrEnum):
    RUN = "run"
    SLOT = "slot"
    CANDIDATE = "candidate"
    SELECTION = "selection"


class M14IssueLevel(StrEnum):
    WARNING = "warning"
    REVIEW = "review"
    BLOCKER = "blocker"


class M14ReviewIssueType(StrEnum):
    EMPTY_CANDIDATE_POOL = "empty_candidate_pool"
    MISSING_ROLE_SCORE = "missing_role_score"
    ALL_SLOTS_EMPTY = "all_slots_empty"
    LOW_CONFIDENCE_TOP_CANDIDATE = "low_confidence_top_candidate"
    HIGH_SCORE_LOW_EVIDENCE = "high_score_low_evidence"
    INSUFFICIENT_MARKET_EVIDENCE = "insufficient_market_evidence"
    SERVICE_ONLY_CANDIDATE = "service_only_candidate"
    SELECTION_CONFLICT = "selection_conflict"
    DUPLICATE_CANDIDATE = "duplicate_candidate"
    MISSING_DIRECT_BATTLEFIELD = "missing_direct_battlefield"
    MISSING_PRESSURE_SIGNAL = "missing_pressure_signal"
    MISSING_BENCHMARK_SIGNAL = "missing_benchmark_signal"


CORE3_M14_SELECTION_SLOTS: tuple[M14SelectionSlot, ...] = tuple(M14SelectionSlot)

CORE3_M14_FORBIDDEN_OUTPUT_FIELDS: tuple[str, ...] = (
    "report_payload",
    "report_content",
    "price_wavg_12m",
    "sales_volume_12m",
    "sales_amount_12m",
)


class M15ReadinessLevel(StrEnum):
    READY = "ready"
    REVIEW_REQUIRED = "review_required"
    INSUFFICIENT = "insufficient"


class M15ConfidenceLabel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    REVIEW_REQUIRED = "review_required"


class M15ReportSectionCode(StrEnum):
    EXECUTIVE = "executive"
    TARGET_PROFILE = "target_profile"
    COMPETITOR_CARDS = "competitor_cards"
    BATTLEFIELD_CONTEXT = "battlefield_context"
    WHY_COMPETITOR = "why_competitor"
    EVIDENCE_MATRIX = "evidence_matrix"
    STRATEGY = "strategy"
    CANDIDATE_AUDIT = "candidate_audit"
    SOP_TRACE = "sop_trace"
    DATA_QUALITY = "data_quality"
    EXPORT = "export"


class M15ReportSectionDisplayStatus(StrEnum):
    VISIBLE = "visible"
    COLLAPSED = "collapsed"
    HIDDEN = "hidden"


class M15ReportExportType(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"
    REPORT_SUMMARY = "report_summary"
    EVIDENCE_CARDS = "evidence_cards"


class M15ReportExportStatus(StrEnum):
    READY = "ready"
    REVIEW_REQUIRED = "review_required"
    FAILED = "failed"


class M15ReportIssueScope(StrEnum):
    REPORT = "report"
    CARD = "card"
    SECTION = "section"
    EXPORT = "export"
    LANGUAGE = "language"
    EVIDENCE = "evidence"


class M15ReportIssueLevel(StrEnum):
    WARNING = "warning"
    REVIEW = "review"
    BLOCKER = "blocker"


class M15ReportReviewIssueType(StrEnum):
    MISSING_SELECTION_RUN = "missing_selection_run"
    ALL_SLOTS_EMPTY = "all_slots_empty"
    MISSING_EVIDENCE_CARD_FIELD = "missing_evidence_card_field"
    MISSING_EVIDENCE = "missing_evidence"
    INTERNAL_FIELD_EXPOSED = "internal_field_exposed"
    UUID_EXPOSED = "uuid_exposed"
    TONE_CONFIDENCE_MISMATCH = "tone_confidence_mismatch"
    MISSING_DATA_SCOPE_NOTE = "missing_data_scope_note"
    CLAIM_GAP_NOT_DISCLOSED = "claim_gap_not_disclosed"
    SERVICE_AS_CORE_CLAIM = "service_as_core_claim"
    MISSING_CANDIDATE_AUDIT = "missing_candidate_audit"
    EXPORT_PAYLOAD_MISMATCH = "export_payload_mismatch"
    SOP_TRACE_TOO_TECHNICAL = "sop_trace_too_technical"
    REPORT_PAYLOAD_INCOMPLETE = "report_payload_incomplete"
    UNKNOWN = "unknown"


CORE3_M15_REPORT_SECTION_ORDER: tuple[M15ReportSectionCode, ...] = (
    M15ReportSectionCode.EXECUTIVE,
    M15ReportSectionCode.TARGET_PROFILE,
    M15ReportSectionCode.COMPETITOR_CARDS,
    M15ReportSectionCode.BATTLEFIELD_CONTEXT,
    M15ReportSectionCode.WHY_COMPETITOR,
    M15ReportSectionCode.EVIDENCE_MATRIX,
    M15ReportSectionCode.STRATEGY,
    M15ReportSectionCode.CANDIDATE_AUDIT,
    M15ReportSectionCode.SOP_TRACE,
    M15ReportSectionCode.DATA_QUALITY,
    M15ReportSectionCode.EXPORT,
)

CORE3_M15_FORBIDDEN_OUTPUT_FIELDS: tuple[str, ...] = (
    "core3_",
    "candidate_",
    "_score",
    "_json",
    "_id",
    "uuid",
    "SQL",
    "AI 认为",
    "模型判断",
    "生成过程",
    "正在思考",
)


class M08ProfileScope(StrEnum):
    SKU_DEFAULT = "sku_default"


class M08ProfileStatus(StrEnum):
    READY = "ready"
    LIMITED = "limited"
    REVIEW_REQUIRED = "review_required"
    INSUFFICIENT = "insufficient"
    BLOCKED = "blocked"
    FAILED = "failed"


class M08SignalDomain(StrEnum):
    SKU_MASTER = "sku_master"
    PARAM = "param"
    CLAIM = "claim"
    CLAIM_COMMENT_VALIDATION = "claim_comment_validation"
    COMMENT = "comment"
    MARKET = "market"
    POOL = "pool"
    QUALITY = "quality"
    DOWNSTREAM_VIEW = "downstream_view"


class M08CoverageStatus(StrEnum):
    COVERED = "covered"
    PARTIALLY_COVERED = "partially_covered"
    MISSING = "missing"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"
    NOT_APPLICABLE = "not_applicable"


class M08ForModule(StrEnum):
    M08_4 = "M08_4"
    M08_5 = "M08_5"
    M09 = "M09"
    M10 = "M10"
    M11 = "M11"
    M11_5 = "M11_5"
    M12 = "M12"
    M13 = "M13"
    M14 = "M14"
    M15 = "M15"
    M16 = "M16"


class M08ViewRole(StrEnum):
    PRIMARY_INPUT = "primary_input"
    CANDIDATE_INPUT = "candidate_input"
    SCORING_INPUT = "scoring_input"
    REPORT_INPUT = "report_input"
    AUDIT_INPUT = "audit_input"


class M085DimensionType(StrEnum):
    TASK = "task"
    TARGET_GROUP = "target_group"
    BATTLEFIELD = "battlefield"
    CLAIM_VALUE = "claim_value"
    SERVICE_CONTEXT = "service_context"
    PURCHASE_MOTIVE = "purchase_motive"
    RISK_CONTEXT = "risk_context"


class M085DefinitionStatus(StrEnum):
    ACTIVE = "active"
    ACTIVE_WITH_WARNING = "active_with_warning"
    REVIEW_REQUIRED = "review_required"
    DISABLED = "disabled"
    BLOCKED = "blocked"


class M085OntologyVersionStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ACTIVE_WITH_WARNING = "active_with_warning"
    SUPERSEDED = "superseded"
    BLOCKED = "blocked"


class M085BoundaryPolicy(StrEnum):
    PRODUCT_VALUE = "product_value"
    PURCHASE_CONTEXT = "purchase_context"
    SERVICE_CONTEXT = "service_context"
    RISK_CONTEXT = "risk_context"
    DIAGNOSTIC_ONLY = "diagnostic_only"


class M085AllocationPolicy(StrEnum):
    ELIGIBLE_WHEN_MAIN_OR_SECONDARY = "eligible_when_main_or_secondary"
    ELIGIBLE_WHEN_PROFILE_ELIGIBLE = "eligible_when_profile_eligible"
    ELIGIBLE_WHEN_PRODUCT_ANCHOR_PRESENT = "eligible_when_product_anchor_present"
    CANDIDATE_ONLY = "candidate_only"
    NEVER_ALLOCATE = "never_allocate"
    REVIEW_REQUIRED = "review_required"


class M085MappingLevel(StrEnum):
    CANDIDATE_TRIGGER = "candidate_trigger"
    PROFILE_ELIGIBLE = "profile_eligible"
    ALLOCATION_ELIGIBLE = "allocation_eligible"
    NEGATIVE = "negative"
    EXCLUDE = "exclude"


class M085CalibrationIssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


M08_DOWNSTREAM_MODULES: tuple[M08ForModule, ...] = (
    M08ForModule.M08_4,
    M08ForModule.M08_5,
    M08ForModule.M09,
    M08ForModule.M10,
    M08ForModule.M11,
    M08ForModule.M11_5,
    M08ForModule.M12,
    M08ForModule.M13,
    M08ForModule.M14,
    M08ForModule.M15,
)

M08_REQUIRED_MATRIX_ROWS: tuple[tuple[M08SignalDomain, str], ...] = (
    (M08SignalDomain.SKU_MASTER, "identity"),
    (M08SignalDomain.PARAM, "core_params"),
    (M08SignalDomain.PARAM, "param_quality"),
    (M08SignalDomain.CLAIM, "structured_claim"),
    (M08SignalDomain.CLAIM, "final_claim_activation"),
    (M08SignalDomain.CLAIM_COMMENT_VALIDATION, "perception_validation"),
    (M08SignalDomain.COMMENT, "claim_validation"),
    (M08SignalDomain.COMMENT, "task_cue"),
    (M08SignalDomain.COMMENT, "target_group_cue"),
    (M08SignalDomain.COMMENT, "battlefield_support"),
    (M08SignalDomain.COMMENT, "pain_point"),
    (M08SignalDomain.COMMENT, "price_perception"),
    (M08SignalDomain.COMMENT, "service_signal"),
    (M08SignalDomain.MARKET, "price"),
    (M08SignalDomain.MARKET, "sales"),
    (M08SignalDomain.MARKET, "platform"),
    (M08SignalDomain.MARKET, "trend"),
    (M08SignalDomain.POOL, "same_size"),
    (M08SignalDomain.POOL, "adjacent_size"),
    (M08SignalDomain.POOL, "same_price_band"),
    (M08SignalDomain.QUALITY, "profile_risk"),
)

CORE3_M08_FORBIDDEN_OUTPUT_FIELDS: tuple[str, ...] = (
    "task_code",
    "target_group_code",
    "battlefield_code",
    "claim_value_layer",
    "candidate_sku_code",
    "competitor_sku_code",
    "component_score",
    "competitor_role",
    "selection_slot",
    "core3_rank",
    "business_conclusion",
    "report_payload",
    "price_wavg_12m",
    "sales_volume_12m",
    "sales_amount_12m",
)


class M07AnalysisWindow(StrEnum):
    FULL_OBSERVED_WINDOW = "full_observed_window"
    LATEST_WEEK = "latest_week"
    RECENT_4W = "recent_4w"
    RECENT_8W = "recent_8w"
    RECENT_12W = "recent_12w"


class M07PriceBand(StrEnum):
    LOW = "low"
    MID_LOW = "mid_low"
    MID = "mid"
    MID_HIGH = "mid_high"
    HIGH = "high"
    UNKNOWN = "unknown"


class M07PoolType(StrEnum):
    SAME_SIZE = "same_size"
    ADJACENT_SIZE = "adjacent_size"
    SAME_PRICE_BAND = "same_price_band"
    SIZE_PRICE_BAND = "size_price_band"
    PLATFORM_OVERLAP = "platform_overlap"
    MARKET_ACTIVE = "market_active"


class M07SampleStatus(StrEnum):
    SUFFICIENT = "sufficient"
    LIMITED = "limited"
    INSUFFICIENT = "insufficient"
    UNKNOWN = "unknown"


class M07MarketSignalCode(StrEnum):
    PRICE_PERCENTILE_HIGH = "PRICE_PERCENTILE_HIGH"
    PRICE_PERCENTILE_LOW = "PRICE_PERCENTILE_LOW"
    SALES_VOLUME_STRONG = "SALES_VOLUME_STRONG"
    SALES_AMOUNT_STRONG = "SALES_AMOUNT_STRONG"
    PRICE_PER_INCH_VALUE = "PRICE_PER_INCH_VALUE"
    RECENT_PRICE_DROP = "RECENT_PRICE_DROP"
    RECENT_SALES_UP = "RECENT_SALES_UP"
    PLATFORM_OVERLAP_STRONG = "PLATFORM_OVERLAP_STRONG"
    SAMPLE_INSUFFICIENT = "SAMPLE_INSUFFICIENT"


class M07SignalLevel(StrEnum):
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"
    BLOCKED = "blocked"


class M07Polarity(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    RISK = "risk"


M07_ANALYSIS_WINDOWS: tuple[M07AnalysisWindow, ...] = (
    M07AnalysisWindow.FULL_OBSERVED_WINDOW,
    M07AnalysisWindow.LATEST_WEEK,
    M07AnalysisWindow.RECENT_4W,
    M07AnalysisWindow.RECENT_8W,
    M07AnalysisWindow.RECENT_12W,
)

M07_ADJACENT_SIZE_SEGMENTS: dict[str, tuple[str, ...]] = {
    "50": ("55",),
    "55": ("50", "65"),
    "65": ("55", "75"),
    "75": ("65", "85"),
    "85": ("75", "100"),
    "100": ("85",),
}

M07_PRICE_BAND_ORDER: tuple[M07PriceBand, ...] = (
    M07PriceBand.LOW,
    M07PriceBand.MID_LOW,
    M07PriceBand.MID,
    M07PriceBand.MID_HIGH,
    M07PriceBand.HIGH,
)

CORE3_M07_FORBIDDEN_OUTPUT_FIELDS: tuple[str, ...] = (
    "task_code",
    "target_group_code",
    "battlefield_code",
    "claim_value_layer",
    "competitor_sku_code",
    "candidate_sku_code",
    "selection_slot",
    "core3_rank",
    "business_conclusion",
    "report_payload",
    "price_wavg_12m",
    "sales_volume_12m",
    "sales_amount_12m",
)


class CommentUnitStatus(StrEnum):
    USABLE = "usable"
    LOW_VALUE = "low_value"
    DUPLICATE_ONLY = "duplicate_only"
    BLOCKED = "blocked"


class CommentDedupStrategy(StrEnum):
    COMMENT_ID = "comment_id"
    TEXT_HASH = "text_hash"
    SOURCE_ROW_FALLBACK = "source_row_fallback"


class CommentDomainHint(StrEnum):
    PRODUCT_EXPERIENCE = "product_experience"
    PRODUCT_RISK = "product_risk"
    MARKET_PERCEPTION = "market_perception"
    SERVICE_EXPERIENCE = "service_experience"
    LOGISTICS_INSTALLATION = "logistics_installation"
    UNKNOWN = "unknown"


class CommentSentimentHint(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"


class CommentSentimentSource(StrEnum):
    RAW_ONLY = "raw_only"
    TEXT_RULE = "text_rule"
    RAW_TEXT_COMBINED = "raw_text_combined"
    UNKNOWN = "unknown"


class CommentLowValueReason(StrEnum):
    DEFAULT_POSITIVE = "default_positive"
    EMPTY_TEXT = "empty_text"
    PUNCTUATION_ONLY = "punctuation_only"
    TOO_SHORT = "too_short"
    TOO_SHORT_GENERIC = "too_short_generic"
    DUPLICATE_ONLY = "duplicate_only"
    TEMPLATE_DUPLICATE = "template_duplicate"
    SERVICE_ONLY = "service_only"
    SERVICE_ONLY_FOR_PRODUCT_USE = "service_only_for_product_use"
    NO_PRODUCT_SIGNAL = "no_product_signal"
    QUALITY_ISSUE_FLAGGED = "quality_issue_flagged"


class CommentTopicMatchMethod(StrEnum):
    KEYWORD = "keyword"
    POSITIVE_KEYWORD = "positive_keyword"
    NEGATIVE_KEYWORD = "negative_keyword"
    DIMENSION_PATH = "dimension_path"
    PHRASE = "phrase"
    SEED_RULE = "seed_rule"


class CommentTopicHintStatus(StrEnum):
    MATCHED = "matched"
    LOW_CONFIDENCE = "low_confidence"
    BLOCKED_LOW_VALUE = "blocked_low_value"
    BLOCKED_SERVICE_GUARDRAIL = "blocked_service_guardrail"


class CommentSampleStatus(StrEnum):
    SUFFICIENT = "sufficient"
    LIMITED = "limited"
    INSUFFICIENT = "insufficient"
    UNKNOWN = "unknown"


class CommentReviewReasonCode(StrEnum):
    LOW_CONFIDENCE = "low_confidence"
    LOW_VALUE = "low_value"
    SERVICE_GUARDRAIL = "service_guardrail"
    INSUFFICIENT_SAMPLE = "insufficient_sample"
    SENTIMENT_CONFLICT = "sentiment_conflict"
    DOMAIN_CONFLICT = "domain_conflict"
    MISSING_SOURCE_EVIDENCE = "missing_source_evidence"
    TOPIC_SEED_MISSING = "topic_seed_missing"


class CommentSignalType(StrEnum):
    CLAIM_VALIDATION = "claim_validation"
    TASK_CUE = "task_cue"
    TARGET_GROUP_CUE = "target_group_cue"
    BATTLEFIELD_SUPPORT = "battlefield_support"
    PAIN_POINT = "pain_point"
    PRICE_PERCEPTION = "price_perception"
    SERVICE_SIGNAL = "service_signal"


class CommentSignalPolarity(StrEnum):
    SUPPORT = "support"
    WEAKEN = "weaken"
    MIXED = "mixed"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


class CommentSignalStrengthLevel(StrEnum):
    STRONG = "strong"
    MEDIUM = "medium"
    WEAK = "weak"
    BLOCKED = "blocked"


class CommentSignalCueBasis(StrEnum):
    EXPLICIT_KEYWORD = "explicit_keyword"
    TOPIC_MAPPING = "topic_mapping"
    SCENARIO_ACTION_RESULT = "scenario_action_result"
    EXPLICIT_PEOPLE = "explicit_people"
    PURCHASE_MOTIVATION = "purchase_motivation"
    SCENARIO_INFERENCE = "scenario_inference"
    NEGATIVE_RISK_PATTERN = "negative_risk_pattern"
    SERVICE_PATTERN = "service_pattern"
    PRICE_PATTERN = "price_pattern"
    UPSTREAM_CLAIM_CONTEXT = "upstream_claim_context"


class CommentHardSpecPolicy(StrEnum):
    EXPERIENCE_ONLY = "experience_only"
    HARD_SPEC_NOT_PROVEN = "hard_spec_not_proven"
    SERVICE_ONLY = "service_only"
    MARKET_FACT_REQUIRED = "market_fact_required"


class CommentSignalReviewReasonCode(StrEnum):
    M05_NOT_READY = "m05_not_ready"
    NO_USABLE_COMMENT_ATOM = "no_usable_comment_atom"
    SEED_MISSING = "seed_missing"
    LOW_CONFIDENCE_SIGNAL = "low_confidence_signal"
    SERVICE_GUARDRAIL = "service_guardrail"
    HARD_SPEC_NOT_PROVEN = "hard_spec_not_proven"
    INSUFFICIENT_SIGNAL_SAMPLE = "insufficient_signal_sample"


COMMENT_SIGNAL_TARGET_PREFIX: dict[CommentSignalType, str] = {
    CommentSignalType.CLAIM_VALIDATION: "CLAIM_",
    CommentSignalType.TASK_CUE: "TASK_",
    CommentSignalType.TARGET_GROUP_CUE: "TG_",
    CommentSignalType.BATTLEFIELD_SUPPORT: "BF_",
    CommentSignalType.PAIN_POINT: "RISK_",
    CommentSignalType.PRICE_PERCEPTION: "PRICE_",
    CommentSignalType.SERVICE_SIGNAL: "SERVICE_",
}

CORE3_M06_FORBIDDEN_OUTPUT_FIELDS: tuple[str, ...] = (
    "final_task_score",
    "final_target_group_score",
    "final_battlefield_score",
    "competitor_sku_code",
    "candidate_sku_code",
    "selection_slot",
    "core3_rank",
    "business_conclusion",
    "report_payload",
)


class ClaimCommentEffect(StrEnum):
    ENHANCE = "enhance"
    WEAKEN = "weaken"
    NEUTRAL = "neutral"
    CONTRADICT = "contradict"
    COMMENT_ONLY_HINT = "comment_only_hint"
    BLOCKED = "blocked"


class ClaimPerceptionStatus(StrEnum):
    VALIDATED = "validated"
    WEAK_PERCEPTION = "weak_perception"
    CONTRADICTED = "contradicted"
    INSUFFICIENT_COMMENT = "insufficient_comment"
    NOT_APPLICABLE = "not_applicable"
    SERVICE_GUARDED = "service_guarded"
    COMMENT_ONLY_PENDING = "comment_only_pending"


class ClaimCommentEnhancedType(StrEnum):
    TECHNICAL_HARD = "technical_hard"
    TECHNICAL_EXPERIENCE_MIXED = "technical_experience_mixed"
    EXPERIENCE_SCENARIO = "experience_scenario"
    SERVICE = "service"
    VALUE = "value"
    UNKNOWN = "unknown"


class ClaimCommentActivationBasis(StrEnum):
    PARAM_AND_PROMO = "param_and_promo"
    PARAM_ONLY = "param_only"
    PROMO_ONLY = "promo_only"
    INSUFFICIENT = "insufficient"
    COMMENT_ENHANCED = "comment_enhanced"
    COMMENT_WEAKENED = "comment_weakened"
    COMMENT_ONLY_HINT = "comment_only_hint"
    SERVICE_COMMENT_VALIDATED = "service_comment_validated"


class ClaimCommentActivationLevel(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"
    REVIEW_REQUIRED = "review_required"


class ClaimCommentIssueType(StrEnum):
    COMMENT_ONLY = "comment_only"
    SPEC_CLAIMED_BY_COMMENT = "spec_claimed_by_comment"
    SERVICE_MISMATCH = "service_mismatch"
    COMMENT_CONTRADICTION = "comment_contradiction"
    WEAK_PERCEPTION = "weak_perception"
    MISSING_STRUCTURED_CLAIM_ENHANCED = "missing_structured_claim_enhanced"
    PARAM_ONLY_CORE_CLAIM = "param_only_core_claim"
    PROMO_ONLY_PARAM_MISSING = "promo_only_param_missing"
    VALUE_REQUIRES_MARKET_VALIDATION = "value_requires_market_validation"
    LOW_QUALITY_COMMENT_SIGNAL = "low_quality_comment_signal"


class ClaimCommentIssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"


class ClaimCommentDownstreamPolicy(StrEnum):
    CONTINUE_WITH_WARNING = "continue_with_warning"
    REQUIRE_APPROVAL = "require_approval"
    BLOCK_DOWNSTREAM = "block_downstream"


class ClaimCommentIssueStatus(StrEnum):
    OPEN = "open"
    APPROVED = "approved"
    REJECTED = "rejected"
    WAIVED = "waived"
    CLOSED = "closed"


CORE3_M04B_FORBIDDEN_OUTPUT_FIELDS: tuple[str, ...] = (
    "final_task_score",
    "final_target_group_score",
    "final_battlefield_score",
    "competitor_sku_code",
    "candidate_sku_code",
    "selection_slot",
    "core3_rank",
    "business_conclusion",
    "report_payload",
    "report_content",
)


CORE3_M05_ALLOWED_EVIDENCE_TYPES: tuple[Core3EvidenceType, ...] = (
    Core3EvidenceType.COMMENT_RAW,
    Core3EvidenceType.COMMENT_SENTENCE,
    Core3EvidenceType.COMMENT_DIMENSION,
    Core3EvidenceType.QUALITY_ISSUE,
)

CORE3_M05_FORBIDDEN_OUTPUT_FIELDS: tuple[str, ...] = (
    "task_code",
    "target_group_code",
    "battlefield_code",
    "competitor_sku_code",
    "candidate_sku_code",
    "selection_slot",
    "business_conclusion",
    "report_payload",
    "report_content",
    "rank",
    "score",
)

CORE3_TARGET_MODEL_85E7Q = "85E7Q"
CORE3_TARGET_SKU_85E7Q = "TV00029115"
CORE3_TARGET_BRAND_85E7Q = "海信"

CORE3_RAW_SOURCE_TABLES: tuple[str, ...] = (
    "week_sales_data",
    "attribute_data",
    "selling_points_data",
    "comment_data",
)

CORE3_M02_CLEAN_SOURCE_TABLES: tuple[str, ...] = (
    "core3_clean_sku",
    "core3_clean_market_weekly",
    "core3_clean_attribute",
    "core3_clean_claim",
    "core3_clean_claim_sentence",
    "core3_clean_comment",
    "core3_clean_comment_sentence",
    "core3_clean_comment_dimension",
    "core3_data_quality_issue",
)

CORE3_MODULE_ORDER: tuple[Core3ModuleCode, ...] = (
    Core3ModuleCode.M00,
    Core3ModuleCode.M01,
    Core3ModuleCode.M02,
    Core3ModuleCode.M03,
    Core3ModuleCode.M03B,
    Core3ModuleCode.M04A,
    Core3ModuleCode.M05,
    Core3ModuleCode.M06,
    Core3ModuleCode.M04B,
    Core3ModuleCode.M07,
    Core3ModuleCode.M08,
    Core3ModuleCode.M08_4,
    Core3ModuleCode.M08_5,
    Core3ModuleCode.M09,
    Core3ModuleCode.M10,
    Core3ModuleCode.M11,
    Core3ModuleCode.M11_5,
    Core3ModuleCode.M11_6,
    Core3ModuleCode.M11_7,
    Core3ModuleCode.M12C,
    Core3ModuleCode.M12,
    Core3ModuleCode.M13,
    Core3ModuleCode.M14,
    Core3ModuleCode.M15,
    Core3ModuleCode.M16,
)

CORE3_MODULE_DAG_EDGES: tuple[tuple[Core3ModuleCode, Core3ModuleCode], ...] = (
    (Core3ModuleCode.M00, Core3ModuleCode.M01),
    (Core3ModuleCode.M01, Core3ModuleCode.M02),
    (Core3ModuleCode.M02, Core3ModuleCode.M03),
    (Core3ModuleCode.M02, Core3ModuleCode.M03B),
    (Core3ModuleCode.M02, Core3ModuleCode.M04A),
    (Core3ModuleCode.M03, Core3ModuleCode.M04A),
    (Core3ModuleCode.M03B, Core3ModuleCode.M04A),
    (Core3ModuleCode.M02, Core3ModuleCode.M05),
    (Core3ModuleCode.M05, Core3ModuleCode.M06),
    (Core3ModuleCode.M04A, Core3ModuleCode.M04B),
    (Core3ModuleCode.M06, Core3ModuleCode.M04B),
    (Core3ModuleCode.M02, Core3ModuleCode.M07),
    (Core3ModuleCode.M03, Core3ModuleCode.M08),
    (Core3ModuleCode.M03B, Core3ModuleCode.M08),
    (Core3ModuleCode.M04B, Core3ModuleCode.M08),
    (Core3ModuleCode.M06, Core3ModuleCode.M08),
    (Core3ModuleCode.M07, Core3ModuleCode.M08),
    (Core3ModuleCode.M08, Core3ModuleCode.M08_4),
    (Core3ModuleCode.M08_4, Core3ModuleCode.M08_5),
    (Core3ModuleCode.M08_5, Core3ModuleCode.M09),
    (Core3ModuleCode.M08_5, Core3ModuleCode.M10),
    (Core3ModuleCode.M08_5, Core3ModuleCode.M11),
    (Core3ModuleCode.M08, Core3ModuleCode.M09),
    (Core3ModuleCode.M08, Core3ModuleCode.M10),
    (Core3ModuleCode.M09, Core3ModuleCode.M10),
    (Core3ModuleCode.M09, Core3ModuleCode.M11),
    (Core3ModuleCode.M10, Core3ModuleCode.M11),
    (Core3ModuleCode.M08, Core3ModuleCode.M11),
    (Core3ModuleCode.M11, Core3ModuleCode.M11_5),
    (Core3ModuleCode.M08, Core3ModuleCode.M11_5),
    (Core3ModuleCode.M04B, Core3ModuleCode.M11_5),
    (Core3ModuleCode.M07, Core3ModuleCode.M11_5),
    (Core3ModuleCode.M11_5, Core3ModuleCode.M11_6),
    (Core3ModuleCode.M07, Core3ModuleCode.M11_6),
    (Core3ModuleCode.M08, Core3ModuleCode.M11_6),
    (Core3ModuleCode.M09, Core3ModuleCode.M11_6),
    (Core3ModuleCode.M10, Core3ModuleCode.M11_6),
    (Core3ModuleCode.M11, Core3ModuleCode.M11_6),
    (Core3ModuleCode.M07, Core3ModuleCode.M11_7),
    (Core3ModuleCode.M08, Core3ModuleCode.M11_7),
    (Core3ModuleCode.M11_6, Core3ModuleCode.M11_7),
    (Core3ModuleCode.M11D, Core3ModuleCode.M12C),
    (Core3ModuleCode.M12C, Core3ModuleCode.M12),
    (Core3ModuleCode.M11_7, Core3ModuleCode.M12),
    (Core3ModuleCode.M12, Core3ModuleCode.M13),
    (Core3ModuleCode.M13, Core3ModuleCode.M14),
    (Core3ModuleCode.M14, Core3ModuleCode.M15),
    (Core3ModuleCode.M15, Core3ModuleCode.M16),
)

CORE3_DATA_DOMAIN_START_MODULE: dict[Core3DataDomain, Core3ModuleCode] = {
    Core3DataDomain.SKU: Core3ModuleCode.M01,
    Core3DataDomain.MARKET: Core3ModuleCode.M01,
    Core3DataDomain.PARAM: Core3ModuleCode.M03B,
    Core3DataDomain.CLAIM: Core3ModuleCode.M04A,
    Core3DataDomain.COMMENT: Core3ModuleCode.M05,
    Core3DataDomain.QUALITY: Core3ModuleCode.M01,
    Core3DataDomain.PROFILE: Core3ModuleCode.M08,
    Core3DataDomain.ONTOLOGY: Core3ModuleCode.M08_4,
    Core3DataDomain.TASK: Core3ModuleCode.M09,
    Core3DataDomain.TARGET_GROUP: Core3ModuleCode.M10,
    Core3DataDomain.BATTLEFIELD: Core3ModuleCode.M11,
    Core3DataDomain.CLAIM_VALUE: Core3ModuleCode.M11_5,
    Core3DataDomain.CANDIDATE: Core3ModuleCode.M12,
    Core3DataDomain.SCORE: Core3ModuleCode.M13,
    Core3DataDomain.SELECTION: Core3ModuleCode.M14,
    Core3DataDomain.REPORT: Core3ModuleCode.M15,
}

CORE3_MODULE_LABEL_CN: dict[Core3ModuleCode, str] = {
    Core3ModuleCode.M00: "原始数据批次与行登记",
    Core3ModuleCode.M01: "清洗规范化与质量诊断",
    Core3ModuleCode.M02: "Evidence 原子层",
    Core3ModuleCode.M03: "参数字段画像与标准参数抽取",
    Core3ModuleCode.M03B: "SKU 参数事实画像与参数档位覆盖",
    Core3ModuleCode.M04A: "基础卖点激活",
    Core3ModuleCode.M04C: "SKU 卖点事实画像与卖点档位覆盖",
    Core3ModuleCode.M05: "评论基础证据层",
    Core3ModuleCode.M05C: "SKU 评论事实画像与评论维度覆盖",
    Core3ModuleCode.M06: "评论下游信号抽取",
    Core3ModuleCode.M04B: "评论验证增强",
    Core3ModuleCode.M07: "市场画像与可比池基线",
    Core3ModuleCode.M08: "SKU 综合信号画像",
    Core3ModuleCode.M08_4: "评论原生业务维度发现",
    Core3ModuleCode.M08_5: "业务维度本体校准",
    Core3ModuleCode.M09: "用户任务模块",
    Core3ModuleCode.M09C: "SKU 用户任务画像与任务覆盖",
    Core3ModuleCode.M10: "目标客群模块",
    Core3ModuleCode.M10C: "SKU 目标客群画像与客群覆盖",
    Core3ModuleCode.M11: "价值战场模块",
    Core3ModuleCode.M11C: "SKU 价值战场画像与战场图谱",
    Core3ModuleCode.M11D: "语义市场图谱与销量分配",
    Core3ModuleCode.M11_5: "战场内卖点价值分层",
    Core3ModuleCode.M11_6: "SKU 业务画像聚合",
    Core3ModuleCode.M11_7: "销量分配对账与市场结构校验",
    Core3ModuleCode.M12C: "卖点价值量化与贡献归因",
    Core3ModuleCode.M12: "候选池召回",
    Core3ModuleCode.M13: "竞品组件评分",
    Core3ModuleCode.M14: "三槽位核心竞品选择",
    Core3ModuleCode.M15: "证据卡与高层报告",
    Core3ModuleCode.M16: "增量任务编排、复核和验收",
}

CORE3_DATA_DOMAIN_LABEL_CN: dict[Core3DataDomain, str] = {
    Core3DataDomain.SKU: "SKU 主数据",
    Core3DataDomain.MARKET: "量价和渠道平台",
    Core3DataDomain.PARAM: "参数",
    Core3DataDomain.CLAIM: "卖点",
    Core3DataDomain.COMMENT: "评论",
    Core3DataDomain.QUALITY: "质量问题",
    Core3DataDomain.PROFILE: "SKU 画像",
    Core3DataDomain.ONTOLOGY: "业务维度本体",
    Core3DataDomain.TASK: "用户任务",
    Core3DataDomain.TARGET_GROUP: "目标客群",
    Core3DataDomain.BATTLEFIELD: "价值战场",
    Core3DataDomain.CLAIM_VALUE: "卖点价值层",
    Core3DataDomain.CANDIDATE: "候选",
    Core3DataDomain.SCORE: "评分",
    Core3DataDomain.SELECTION: "三槽位选择",
    Core3DataDomain.REPORT: "报告",
}

CORE3_BUSINESS_DISPLAY_FORBIDDEN_PATTERNS: tuple[str, ...] = (
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    r"\bSELECT\b|\bJOIN\b|\bWHERE\b|\bINSERT\b|\bUPDATE\b|\bDELETE\b",
    r"\bcore3_[a-z0-9_]+\b",
    r"\b(price_wavg_12m|task_battlefield|comment_signal|display_payload_json)\b",
    r"\b(blocked|review_required|skipped_reused|skipped_by_dependency)\b",
    r"AI 认为|模型判断|生成过程|提示词|prompt",
)
