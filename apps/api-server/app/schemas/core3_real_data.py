"""Pydantic schemas for Core3 real-data v2."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.services.core3_real_data.constants import (
    CORE3_DEFAULT_RULESET_VERSION,
    CORE3_M00_MODULE_VERSION,
    CORE3_M00_ROW_HASH_VERSION,
    CORE3_M01_CLEAN_HASH_VERSION,
    CORE3_M01_CLEAN_VERSION,
    CORE3_M02_CONFIDENCE_RULE_VERSION,
    CORE3_M02_EVIDENCE_VERSION,
    CORE3_M02_MODULE_VERSION,
    CORE3_M03_PARSER_VERSION,
    CORE3_M03_RULE_VERSION,
    CORE3_M03_SEED_VERSION,
    CORE3_M04A_RULE_VERSION,
    CORE3_M04A_SEED_VERSION,
    CORE3_M04B_MODULE_VERSION,
    CORE3_M04B_RULE_VERSION,
    CORE3_M04B_SEED_VERSION,
    CORE3_M07_MODULE_VERSION,
    CORE3_M07_POOL_RULE_VERSION,
    CORE3_M07_PRICE_BAND_RULE_VERSION,
    CORE3_M07_RULE_VERSION,
    CORE3_M08_FEATURE_VERSION,
    CORE3_M08_4_MODULE_VERSION,
    CORE3_M08_4_RULE_VERSION,
    CORE3_M08_4_SEED_VERSION,
    CORE3_M08_5_MODULE_VERSION,
    CORE3_M08_5_RULE_VERSION,
    CORE3_M08_5_SEED_VERSION,
    CORE3_M08_MODULE_VERSION,
    CORE3_M08_RULE_VERSION,
    CORE3_M08_VIEW_SCHEMA_VERSION,
    CORE3_M09_MODULE_VERSION,
    CORE3_M09_RULE_VERSION,
    CORE3_M09_SEED_VERSION,
    CORE3_M10_MODULE_VERSION,
    CORE3_M10_RULE_VERSION,
    CORE3_M10_SEED_VERSION,
    CORE3_M11_MODULE_VERSION,
    CORE3_M11_RULE_VERSION,
    CORE3_M11_SEED_VERSION,
    CORE3_M11_5_BATTLEFIELD_SEED_VERSION,
    CORE3_M11_5_CLAIM_SEED_VERSION,
    CORE3_M11_5_MODULE_VERSION,
    CORE3_M11_5_RULE_VERSION,
    CORE3_M11_6_MODULE_VERSION,
    CORE3_M11_6_RULE_VERSION,
    CORE3_M11_7_MODULE_VERSION,
    CORE3_M11_7_RULE_VERSION,
    CORE3_M12_MODULE_VERSION,
    CORE3_M12_RULE_VERSION,
    CORE3_M13_COMPONENT_RULE_VERSION,
    CORE3_M13_MODULE_VERSION,
    CORE3_M13_ROLE_RULE_VERSION,
    CORE3_M13_RULE_VERSION,
    CORE3_M14_MODULE_VERSION,
    CORE3_M14_RULE_VERSION,
    CORE3_M15_MODULE_VERSION,
    CORE3_M15_RULE_VERSION,
    CORE3_M05_MODULE_VERSION,
    CORE3_M05_RULE_VERSION,
    CORE3_M05_SEED_VERSION,
    CORE3_M06_MODULE_VERSION,
    CORE3_M06_RULE_VERSION,
    CORE3_M06_SEED_VERSION,
    CORE3_RAW_SOURCE_TABLES,
    CommentDedupStrategy,
    CommentDomainHint,
    CommentLowValueReason,
    CommentReviewReasonCode,
    CommentSampleStatus,
    CommentSentimentHint,
    CommentSentimentSource,
    CommentHardSpecPolicy,
    CommentSignalCueBasis,
    CommentSignalPolarity,
    CommentSignalStrengthLevel,
    CommentSignalType,
    CommentTopicHintStatus,
    CommentTopicMatchMethod,
    CommentUnitStatus,
    ClaimCommentActivationBasis,
    ClaimCommentActivationLevel,
    ClaimCommentEffect,
    ClaimCommentEnhancedType,
    ClaimCommentIssueSeverity,
    ClaimCommentIssueStatus,
    ClaimCommentIssueType,
    ClaimPerceptionStatus,
    Core3CategoryCode,
    Core3ConfidenceLevel,
    Core3DataDomain,
    Core3ModuleCode,
    Core3ReleaseGateStatus,
    Core3ReviewStatus,
    Core3ReviewSeverity,
    Core3RunMode,
    Core3RunStatus,
    Core3SourceBatchStatus,
    Core3SourceBatchType,
    Core3SourceImpactLevel,
    Core3SourceOperationType,
    Core3SourcePkStrategy,
    Core3TargetScopeType,
    M07AnalysisWindow,
    M07MarketSignalCode,
    M07Polarity,
    M07PoolType,
    M07PriceBand,
    M07SampleStatus,
    M07SignalLevel,
    M08CoverageStatus,
    M08ForModule,
    M08ProfileScope,
    M08ProfileStatus,
    M08SignalDomain,
    M08ViewRole,
    M09TaskCandidateStatus,
    M09TaskEvidenceDomain,
    M09TaskRelationLevel,
    M09TaskSupportLevel,
    M10TargetGroupCandidateStatus,
    M10TargetGroupEvidenceDomain,
    M10TargetGroupRelationLevel,
    M10TargetGroupSupportLevel,
    M11BattlefieldCandidateStatus,
    M11BattlefieldEvidenceDomain,
    M11BattlefieldRelationLevel,
    M11BattlefieldSupportLevel,
    M11CompetitorSelectionRole,
    M115BattlefieldRelevanceRole,
    M115ClaimCandidateStatus,
    M115ClaimValueEvidenceDomain,
    M115ClaimValueLayer,
    M115ClaimValueSupportLevel,
    M115SampleSufficiency,
    M12PriceRelation,
    M12RecallSource,
    M12RecallStatus,
    M12RecallStrength,
    M12RelationType,
    M12SampleStatus,
    M12SizeRelation,
    M12SupportLevel,
    M13ComponentCode,
    M13IssueLevel,
    M13IssueScope,
    M13RoleCode,
    M13SampleStatus,
    M13SupportLevel,
    M14AuditDecision,
    M14IssueLevel,
    M14IssueScope,
    M14PressureLevel,
    M14SelectionSlot,
    M14SelectionStatus,
    M14SlotDecisionStatus,
    M15ReadinessLevel,
    M15ReportExportStatus,
    M15ReportExportType,
    M15ReportIssueLevel,
    M15ReportIssueScope,
    M15ReportSectionCode,
    M15ReportSectionDisplayStatus,
)
from app.services.core3_real_data.cleaning_schemas import (
    CleanAttributeRead,
    CleanClaimRead,
    CleanCommentRead,
    CleanCoverageSummary,
    CleanMarketRead,
    CleanQualityIssueRead,
    CleanQualityStatus,
    CleanRecordStatus,
    CleanSkuSummary,
    CleaningCounts,
    CleaningRunRequest,
    CleaningRunResult,
    QualityIssueCounts,
    QualityIssueSeverity,
    QualityIssueType,
    ReviewStatus,
    ValuePresence,
)
from app.services.core3_real_data.evidence_atom_schemas import (
    ConfidenceLevel,
    EvidenceAtomListItem,
    EvidenceAtomRead,
    EvidenceCounts,
    EvidenceGrain,
    EvidenceInactiveReason,
    EvidenceLinkRead,
    EvidenceLinkStatus,
    EvidenceLinkType,
    EvidenceRunRequest,
    EvidenceRunResult,
    EvidenceStatus,
    EvidenceSummary,
    EvidenceTraceResponse,
    EvidenceType,
    SkuEvidenceQuery,
    SkuEvidenceResponse,
)
from app.services.core3_real_data.param_extraction_schemas import (
    ExtractParamValueRead,
    ParamAliasCandidateRead,
    ParamCandidateStatus,
    ParamConfidenceLevel,
    ParamConflictType,
    ParamDataType,
    ParamExtractionRunRequest,
    ParamExtractionRunResult,
    ParamFieldProfileRead,
    ParamGroup,
    ParamMatchType,
    ParamParserStatus,
    ParamReviewStatus,
    ParamSourceType,
    ParamValueConflictRead,
    SkuParamProfileRead,
    SkuParamQuery,
    StdParamDefinition,
    StdParamSeed,
)
from app.services.core3_real_data.base_claim_activation_schemas import (
    BaseClaimActivationRunRequest,
    BaseClaimActivationRunResult,
    ClaimActivationBaseRead,
    ClaimActivationBasis,
    ClaimActivationLevel,
    ClaimConfidenceLevel,
    ClaimGroup,
    ClaimHitQuery,
    ClaimHitRead,
    ClaimHitSourceType,
    ClaimMatchMethod,
    ClaimReviewStatus,
    ClaimSeedSourceType,
    ClaimSourceStatus,
    ClaimSourceStatusQuery,
    ClaimSourceStatusRead,
    ClaimType,
    SkuClaimBaseResponse,
    StdClaimDefinition,
    StdClaimSeed,
)
from app.services.core3_real_data.comment_evidence_schemas import (
    CommentEvidenceAtomRecord,
    CommentQualityProfileRecord,
    CommentSentenceCandidate,
    CommentTopicSeed,
    CommentTopicSeedIndex,
    CommentUnitCandidate,
    CommentUnitEvidenceLinkRecord,
    CommentUnitRecord,
    DomainHint,
    M05DownstreamImpact,
    M05EvidenceInput,
    M05ReviewIssue,
    M05RunRequest,
    M05RunResult,
    M05SkuInputBundle,
    SentimentHint,
    TopicHintRecord,
)
from app.services.core3_real_data.comment_downstream_signal_schemas import (
    M06RunRequest,
    M06RunResult,
)


class Core3RealDataBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


COMMENT_SAMPLE_STATUS_LABEL_CN: dict[str, str] = {
    CommentSampleStatus.SUFFICIENT.value: "样本充足",
    CommentSampleStatus.LIMITED.value: "样本有限",
    CommentSampleStatus.INSUFFICIENT.value: "样本不足",
    CommentSampleStatus.UNKNOWN.value: "样本未知",
}

COMMENT_DOMAIN_HINT_LABEL_CN: dict[str, str] = {
    CommentDomainHint.PRODUCT_EXPERIENCE.value: "产品体验",
    CommentDomainHint.PRODUCT_RISK.value: "产品风险",
    CommentDomainHint.MARKET_PERCEPTION.value: "市场感知",
    CommentDomainHint.SERVICE_EXPERIENCE.value: "服务体验",
    CommentDomainHint.LOGISTICS_INSTALLATION.value: "物流安装",
    CommentDomainHint.UNKNOWN.value: "领域待识别",
}

COMMENT_SENTIMENT_HINT_LABEL_CN: dict[str, str] = {
    CommentSentimentHint.POSITIVE.value: "正向",
    CommentSentimentHint.NEGATIVE.value: "负向",
    CommentSentimentHint.NEUTRAL.value: "中性",
    CommentSentimentHint.UNKNOWN.value: "情感未知",
    CommentSentimentHint.CONFLICT.value: "情感冲突",
}

COMMENT_TOPIC_HINT_STATUS_LABEL_CN: dict[str, str] = {
    CommentTopicHintStatus.MATCHED.value: "已命中",
    CommentTopicHintStatus.LOW_CONFIDENCE.value: "弱提示，需谨慎使用",
    CommentTopicHintStatus.BLOCKED_LOW_VALUE.value: "低价值评论，不下游使用",
    CommentTopicHintStatus.BLOCKED_SERVICE_GUARDRAIL.value: "服务/物流线索，不直接证明产品卖点",
}

COMMENT_SIGNAL_TYPE_LABEL_CN: dict[str, str] = {
    CommentSignalType.CLAIM_VALIDATION.value: "卖点体验验证",
    CommentSignalType.TASK_CUE.value: "用户任务线索",
    CommentSignalType.TARGET_GROUP_CUE.value: "目标客群线索",
    CommentSignalType.BATTLEFIELD_SUPPORT.value: "战场体验支撑",
    CommentSignalType.PAIN_POINT.value: "痛点风险信号",
    CommentSignalType.PRICE_PERCEPTION.value: "价格价值感信号",
    CommentSignalType.SERVICE_SIGNAL.value: "服务保障信号",
}

COMMENT_SIGNAL_POLARITY_LABEL_CN: dict[str, str] = {
    CommentSignalPolarity.SUPPORT.value: "支撑证据",
    CommentSignalPolarity.WEAKEN.value: "削弱证据",
    CommentSignalPolarity.MIXED.value: "正负混合",
    CommentSignalPolarity.NEUTRAL.value: "中性证据",
    CommentSignalPolarity.UNKNOWN.value: "方向未知",
}

COMMENT_HARD_SPEC_POLICY_LABEL_CN: dict[str, str] = {
    CommentHardSpecPolicy.EXPERIENCE_ONLY.value: "仅证明体验感知",
    CommentHardSpecPolicy.HARD_SPEC_NOT_PROVEN.value: "不能证明硬规格",
    CommentHardSpecPolicy.SERVICE_ONLY.value: "仅可用于服务保障",
    CommentHardSpecPolicy.MARKET_FACT_REQUIRED.value: "需要价格事实复核",
}

COMMENT_UNIT_STATUS_LABEL_CN: dict[str, str] = {
    CommentUnitStatus.USABLE.value: "可用于评论分析",
    CommentUnitStatus.LOW_VALUE.value: "低信息量评论",
    CommentUnitStatus.DUPLICATE_ONLY.value: "仅重复保留",
    CommentUnitStatus.BLOCKED.value: "不可下游使用",
}

COMMENT_LOW_VALUE_REASON_LABEL_CN: dict[str, str] = {
    CommentLowValueReason.DEFAULT_POSITIVE.value: "泛泛好评",
    CommentLowValueReason.EMPTY_TEXT.value: "评论为空",
    CommentLowValueReason.PUNCTUATION_ONLY.value: "仅有标点",
    CommentLowValueReason.TOO_SHORT.value: "内容过短",
    CommentLowValueReason.TOO_SHORT_GENERIC.value: "过短泛化评价",
    CommentLowValueReason.DUPLICATE_ONLY.value: "重复内容",
    CommentLowValueReason.TEMPLATE_DUPLICATE.value: "模板化重复",
    CommentLowValueReason.SERVICE_ONLY.value: "仅服务体验",
    CommentLowValueReason.SERVICE_ONLY_FOR_PRODUCT_USE.value: "仅服务体验，不能证明产品卖点",
    CommentLowValueReason.NO_PRODUCT_SIGNAL.value: "缺少产品信号",
    CommentLowValueReason.QUALITY_ISSUE_FLAGGED.value: "上游质量规则已标记",
}


def _label_cn(value: Any, labels: dict[str, str], fallback: str = "待识别") -> str:
    return labels.get(str(value), fallback)


class Core3TargetScopeSchema(Core3RealDataBaseModel):
    scope_type: Core3TargetScopeType
    sku_codes: list[str] = Field(default_factory=list)
    include_related_targets: bool = False
    related_target_reason: str | None = None
    data_domains: list[Core3DataDomain] = Field(default_factory=list)
    note_cn: str | None = None


class Core3RunContextSchema(Core3RealDataBaseModel):
    run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str | None = None
    run_mode: Core3RunMode
    ruleset_version: str = CORE3_DEFAULT_RULESET_VERSION
    module_versions: dict[str, str] = Field(default_factory=dict)
    seed_versions: dict[str, str] = Field(default_factory=dict)
    target_scope: Core3TargetScopeSchema
    input_watermarks: dict[str, Any] = Field(default_factory=dict)
    triggered_by: str = "system"
    created_at: datetime | None = None


class Core3ReviewIssueSchema(Core3RealDataBaseModel):
    issue_code: str = Field(min_length=1)
    issue_type: str = Field(min_length=1)
    severity: Core3ReviewSeverity
    source_module: Core3ModuleCode
    object_type: str
    object_id: str | None = None
    target_sku_code: str | None = None
    candidate_sku_code: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    message_cn: str = Field(min_length=1)
    suggestion_cn: str | None = None
    review_required: bool = True
    confidence: float | None = Field(default=None, ge=0, le=1)


class Core3ModuleRunResultSchema(Core3RealDataBaseModel):
    module_code: Core3ModuleCode
    status: Core3RunStatus
    input_count: int = Field(default=0, ge=0)
    changed_input_count: int = Field(default=0, ge=0)
    output_count: int = Field(default=0, ge=0)
    output_hash: str | None = None
    warnings: list[str] = Field(default_factory=list)
    review_issues: list[Core3ReviewIssueSchema] = Field(default_factory=list)
    downstream_impacts: list[dict[str, Any]] = Field(default_factory=list)
    summary_json: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class Core3PipelineInitializationModuleStatus(Core3RealDataBaseModel):
    module_code: Core3ModuleCode
    module_name_cn: str
    stage_name_cn: str
    stage_description_cn: str
    execution_status: str = Field(min_length=1)
    execution_status_cn: str = Field(min_length=1)
    can_execute: bool = True
    can_skip: bool = False
    skip_reason_cn: str | None = None
    blocked_reason_cn: str | None = None
    expected_target_count: int = Field(default=0, ge=0)
    processed_target_count: int = Field(default=0, ge=0)
    output_count: int = Field(default=0, ge=0)
    current_output_count: int = Field(default=0, ge=0)
    review_issue_count: int = Field(default=0, ge=0)
    warning_count: int = Field(default=0, ge=0)
    latest_run_id: str | None = None
    latest_module_run_id: str | None = None
    latest_status: str | None = None
    latest_started_at: datetime | None = None
    latest_finished_at: datetime | None = None
    latest_summary_cn: str | None = None
    latest_summary_json: dict[str, Any] = Field(default_factory=dict)
    result_entry_url: str | None = None


class Core3PipelineInitializationStatusResponse(Core3RealDataBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str | None = None
    batch_status_cn: str = Field(min_length=1)
    source_row_count: int = Field(default=0, ge=0)
    impacted_sku_count: int = Field(default=0, ge=0)
    clean_sku_count: int = Field(default=0, ge=0)
    latest_pipeline_run_id: str | None = None
    modules: list[Core3PipelineInitializationModuleStatus] = Field(default_factory=list)
    summary_cn: str = Field(min_length=1)


class Core3PipelineInitializationRunApiRequest(Core3RealDataBaseModel):
    module_code: Core3ModuleCode
    batch_id: str | None = None
    force_rebuild: bool = False
    run_id: str | None = None
    triggered_by: str = "factory-web"


class Core3PipelineInitializationRunResponse(Core3RealDataBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str | None = None
    module: Core3PipelineInitializationModuleStatus
    result: Core3ModuleRunResultSchema
    skipped: bool = False
    message_cn: str = Field(min_length=1)
    next_action_cn: str | None = None


class Core3ReleaseGateSchema(Core3RealDataBaseModel):
    target_sku_code: str
    gate_status: Core3ReleaseGateStatus
    reason_cn: str
    blocking_issue_codes: list[str] = Field(default_factory=list)
    checked_at: datetime | None = None


class Core3SourceBatchRegisterRequest(Core3RealDataBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    run_id: str | None = None
    module_run_id: str | None = None
    batch_type: Core3SourceBatchType = Core3SourceBatchType.FULL
    source_system: str = Field(default="postgresql_205", min_length=1)
    source_database: str = Field(default="catforge_dev", min_length=1)
    source_schema: str | None = "public"
    source_tables: list[str] = Field(default_factory=lambda: list(CORE3_RAW_SOURCE_TABLES))
    ruleset_version: str = CORE3_DEFAULT_RULESET_VERSION
    module_version: str = CORE3_M00_MODULE_VERSION
    hash_version: str = CORE3_M00_ROW_HASH_VERSION
    triggered_by: str = "system"
    note_cn: str | None = None

    @field_validator("source_tables")
    @classmethod
    def validate_source_tables(cls, source_tables: list[str]) -> list[str]:
        if not source_tables:
            raise ValueError("source_tables must not be empty")
        unknown_tables = sorted(set(source_tables) - set(CORE3_RAW_SOURCE_TABLES))
        if unknown_tables:
            raise ValueError(f"unknown source_tables: {', '.join(unknown_tables)}")
        return source_tables


class Core3SourceBatchRegisterApiRequest(Core3RealDataBaseModel):
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    run_id: str | None = None
    module_run_id: str | None = None
    batch_type: Core3SourceBatchType = Core3SourceBatchType.FULL
    source_system: str = Field(default="postgresql_205", min_length=1)
    source_database: str = Field(default="catforge_dev", min_length=1)
    source_schema: str | None = "public"
    source_tables: list[str] = Field(default_factory=lambda: list(CORE3_RAW_SOURCE_TABLES))
    ruleset_version: str = CORE3_DEFAULT_RULESET_VERSION
    module_version: str = CORE3_M00_MODULE_VERSION
    hash_version: str = CORE3_M00_ROW_HASH_VERSION
    triggered_by: str = "system"
    note_cn: str | None = None

    @field_validator("source_tables")
    @classmethod
    def validate_source_tables(cls, source_tables: list[str]) -> list[str]:
        if not source_tables:
            raise ValueError("source_tables must not be empty")
        unknown_tables = sorted(set(source_tables) - set(CORE3_RAW_SOURCE_TABLES))
        if unknown_tables:
            raise ValueError(f"unknown source_tables: {', '.join(unknown_tables)}")
        return source_tables


class Core3SourceBatchOut(Core3RealDataBaseModel):
    batch_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    run_id: str | None = None
    module_run_id: str | None = None
    batch_type: Core3SourceBatchType
    source_system: str
    source_database: str
    source_schema: str | None = None
    source_tables: list[str]
    ruleset_version: str
    module_version: str
    hash_version: str
    scan_started_at: datetime
    scan_finished_at: datetime | None = None
    input_watermark_json: dict[str, Any] = Field(default_factory=dict)
    row_counts_json: dict[str, Any] = Field(default_factory=dict)
    write_time_range_json: dict[str, Any] = Field(default_factory=dict)
    source_pk_range_json: dict[str, Any] = Field(default_factory=dict)
    schema_snapshot_json: dict[str, Any] = Field(default_factory=dict)
    impacted_sku_count: int = Field(default=0, ge=0)
    affected_module_summary_json: dict[str, Any] = Field(default_factory=dict)
    quality_summary_json: dict[str, Any] = Field(default_factory=dict)
    status: Core3SourceBatchStatus
    review_required: bool = False
    review_status: Core3ReviewStatus = Core3ReviewStatus.AUTO_PASS
    review_reason: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class Core3SourceRowRegistryOut(Core3RealDataBaseModel):
    row_registry_id: str = Field(min_length=1)
    batch_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    source_table: str = Field(min_length=1)
    source_pk: str | None = None
    source_pk_strategy: Core3SourcePkStrategy = Core3SourcePkStrategy.ID_COLUMN
    source_row_id: str | None = None
    row_hash: str | None = None
    hash_version: str = CORE3_M00_ROW_HASH_VERSION
    previous_batch_id: str | None = None
    previous_row_hash: str | None = None
    previous_operation_type: Core3SourceOperationType | None = None
    sku_code_candidate: str | None = None
    model_name_raw: str | None = None
    brand_raw: str | None = None
    category_raw: str | None = None
    write_time: datetime | None = None
    business_key_json: dict[str, Any] = Field(default_factory=dict)
    source_field_presence_json: dict[str, Any] = Field(default_factory=dict)
    operation_type: Core3SourceOperationType
    change_reason: str | None = None
    affected_modules: list[Core3ModuleCode] = Field(default_factory=list)
    quality_hint: dict[str, Any] = Field(default_factory=dict)
    review_required: bool = False
    review_status: Core3ReviewStatus = Core3ReviewStatus.AUTO_PASS
    created_at: datetime

    @field_validator("source_table")
    @classmethod
    def validate_source_table(cls, source_table: str) -> str:
        if source_table not in CORE3_RAW_SOURCE_TABLES:
            raise ValueError(f"unknown source_table: {source_table}")
        return source_table


class Core3SourceImpactedSkuOut(Core3RealDataBaseModel):
    impacted_sku_id: str = Field(min_length=1)
    batch_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    sku_code_candidate: str = Field(min_length=1)
    model_name_raw: str | None = None
    brand_raw: str | None = None
    source_tables: list[str] = Field(default_factory=list)
    operation_summary_json: dict[str, Any] = Field(default_factory=dict)
    affected_modules: list[Core3ModuleCode] = Field(default_factory=list)
    impact_reason: str = Field(min_length=1)
    impact_level: Core3SourceImpactLevel
    needs_recompute: bool = True
    review_required: bool = False
    review_status: Core3ReviewStatus = Core3ReviewStatus.AUTO_PASS
    review_reason: dict[str, Any] | None = None
    created_at: datetime

    @field_validator("source_tables")
    @classmethod
    def validate_source_tables(cls, source_tables: list[str]) -> list[str]:
        unknown_tables = sorted(set(source_tables) - set(CORE3_RAW_SOURCE_TABLES))
        if unknown_tables:
            raise ValueError(f"unknown source_tables: {', '.join(unknown_tables)}")
        return source_tables


class Core3SourceBatchListOut(Core3RealDataBaseModel):
    items: list[Core3SourceBatchOut] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class Core3SourceRowRegistryListOut(Core3RealDataBaseModel):
    items: list[Core3SourceRowRegistryOut] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class Core3SourceImpactedSkuListOut(Core3RealDataBaseModel):
    items: list[Core3SourceImpactedSkuOut] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class Core3CleaningRunApiRequest(Core3RealDataBaseModel):
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    run_id: str | None = None
    module_run_id: str | None = None
    include_no_change: bool = False
    target_sku_codes: list[str] = Field(default_factory=list)
    clean_version: str = CORE3_M01_CLEAN_VERSION
    hash_version: str = CORE3_M01_CLEAN_HASH_VERSION


class Core3EvidenceRunApiRequest(Core3RealDataBaseModel):
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    run_id: str | None = None
    module_run_id: str | None = None
    target_sku_codes: list[str] = Field(default_factory=list)
    evidence_version: str = CORE3_M02_EVIDENCE_VERSION
    confidence_rule_version: str = CORE3_M02_CONFIDENCE_RULE_VERSION

    @field_validator("target_sku_codes")
    @classmethod
    def validate_target_sku_codes(cls, target_sku_codes: list[str]) -> list[str]:
        if any(not sku_code.strip() for sku_code in target_sku_codes):
            raise ValueError("target_sku_codes must not contain empty values")
        return target_sku_codes


class Core3ParamExtractionRunApiRequest(Core3RealDataBaseModel):
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    run_id: str | None = None
    module_run_id: str | None = None
    target_sku_codes: list[str] = Field(default_factory=list)
    seed_version: str = CORE3_M03_SEED_VERSION
    parser_version: str = CORE3_M03_PARSER_VERSION
    rule_version: str = CORE3_M03_RULE_VERSION
    force_rebuild: bool = False

    @field_validator("target_sku_codes")
    @classmethod
    def validate_target_sku_codes(cls, target_sku_codes: list[str]) -> list[str]:
        if any(not sku_code.strip() for sku_code in target_sku_codes):
            raise ValueError("target_sku_codes must not contain empty values")
        return target_sku_codes


class Core3BaseClaimActivationRunApiRequest(Core3RealDataBaseModel):
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    run_id: str | None = None
    module_run_id: str | None = None
    target_sku_codes: list[str] = Field(default_factory=list)
    seed_version: str = CORE3_M04A_SEED_VERSION
    rule_version: str = CORE3_M04A_RULE_VERSION
    include_param_only_claims: bool = True
    force_rebuild: bool = False
    triggered_by: str = "system"

    @field_validator("target_sku_codes")
    @classmethod
    def validate_target_sku_codes(cls, target_sku_codes: list[str]) -> list[str]:
        if any(not sku_code.strip() for sku_code in target_sku_codes):
            raise ValueError("target_sku_codes must not contain empty values")
        return target_sku_codes


class Core3CommentEvidenceRunApiRequest(Core3RealDataBaseModel):
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    run_id: str | None = None
    module_run_id: str | None = None
    sku_scope: list[str] = Field(default_factory=list)
    module_version: str = CORE3_M05_MODULE_VERSION
    seed_version: str = CORE3_M05_SEED_VERSION
    rule_version: str = CORE3_M05_RULE_VERSION
    force_rebuild: bool = False
    triggered_by: str = "system"

    @field_validator("sku_scope")
    @classmethod
    def validate_sku_scope(cls, sku_scope: list[str]) -> list[str]:
        if any(not sku_code.strip() for sku_code in sku_scope):
            raise ValueError("sku_scope must not contain empty values")
        return sku_scope


class Core3CleanSummaryOut(Core3RealDataBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    clean_counts: CleaningCounts = Field(default_factory=CleaningCounts)
    issue_counts: QualityIssueCounts = Field(default_factory=QualityIssueCounts)
    review_required: bool = False
    quality_summary_cn: str = Field(min_length=1)


class Core3CleanSkuListOut(Core3RealDataBaseModel):
    items: list[CleanSkuSummary] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class Core3QualityIssueListOut(Core3RealDataBaseModel):
    items: list[CleanQualityIssueRead] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    quality_summary_cn: str = Field(min_length=1)


class Core3ParamFieldProfileListOut(Core3RealDataBaseModel):
    items: list[ParamFieldProfileRead] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class Core3ParamAliasCandidateListOut(Core3RealDataBaseModel):
    items: list[ParamAliasCandidateRead] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class Core3ParamValueConflictListOut(Core3RealDataBaseModel):
    items: list[ParamValueConflictRead] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class Core3SkuParamOut(Core3RealDataBaseModel):
    profile: SkuParamProfileRead
    values: list[ExtractParamValueRead] = Field(default_factory=list)
    conflicts: list[ParamValueConflictRead] = Field(default_factory=list)


class Core3ClaimHitListOut(Core3RealDataBaseModel):
    items: list[ClaimHitRead] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class Core3ClaimSourceStatusListOut(Core3RealDataBaseModel):
    items: list[ClaimSourceStatusRead] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class Core3ClaimActivationBaseListOut(Core3RealDataBaseModel):
    items: list[ClaimActivationBaseRead] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class CommentQualityProfileResponse(Core3RealDataBaseModel):
    comment_quality_profile_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    raw_comment_row_count: int = Field(default=0, ge=0)
    comment_unit_count: int = Field(default=0, ge=0)
    sentence_count: int = Field(default=0, ge=0)
    usable_sentence_count: int = Field(default=0, ge=0)
    duplicate_text_rate: float = Field(default=0, ge=0, le=1)
    sentiment_distribution_json: dict[str, int] = Field(default_factory=dict)
    domain_distribution_json: dict[str, int] = Field(default_factory=dict)
    topic_distribution_json: dict[str, int] = Field(default_factory=dict)
    sample_status: CommentSampleStatus = CommentSampleStatus.UNKNOWN
    sample_status_label_cn: str | None = None
    comment_usability_score: float = Field(default=0, ge=0, le=1)
    warning_flags: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    downstream_ready: bool = False
    downstream_ready_label_cn: str | None = None
    quality_summary_cn: str | None = None
    review_required: bool = False
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def fill_business_labels(self) -> "CommentQualityProfileResponse":
        self.sample_status_label_cn = self.sample_status_label_cn or _label_cn(
            self.sample_status,
            COMMENT_SAMPLE_STATUS_LABEL_CN,
            "样本待识别",
        )
        self.downstream_ready_label_cn = self.downstream_ready_label_cn or (
            "可进入评论信号抽取" if self.downstream_ready else "暂不进入评论信号抽取"
        )
        return self


class CommentQualityProfileListResponse(Core3RealDataBaseModel):
    items: list[CommentQualityProfileResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class CommentEvidenceAtomResponse(Core3RealDataBaseModel):
    comment_evidence_id: str = Field(min_length=1)
    comment_unit_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    sentence_text: str = Field(min_length=1)
    representative_phrase: str | None = None
    primary_domain_hint: CommentDomainHint = CommentDomainHint.UNKNOWN
    primary_domain_hint_label_cn: str | None = None
    sentiment_hint: CommentSentimentHint = CommentSentimentHint.UNKNOWN
    sentiment_hint_label_cn: str | None = None
    specificity_score: float = Field(default=0, ge=0, le=1)
    usable_for_downstream: bool = True
    downstream_usage_label_cn: str | None = None
    low_value_flag: bool = False
    low_value_reasons: list[CommentLowValueReason] = Field(default_factory=list)
    low_value_reason_labels_cn: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    source_evidence_count: int = Field(default=0, ge=0)
    review_required: bool = False

    @model_validator(mode="after")
    def fill_business_labels(self) -> "CommentEvidenceAtomResponse":
        self.primary_domain_hint_label_cn = self.primary_domain_hint_label_cn or _label_cn(
            self.primary_domain_hint,
            COMMENT_DOMAIN_HINT_LABEL_CN,
        )
        self.sentiment_hint_label_cn = self.sentiment_hint_label_cn or _label_cn(
            self.sentiment_hint,
            COMMENT_SENTIMENT_HINT_LABEL_CN,
        )
        self.downstream_usage_label_cn = self.downstream_usage_label_cn or (
            "可作为后续评论信号" if self.usable_for_downstream else "仅保留为原始证据"
        )
        if not self.low_value_reason_labels_cn:
            self.low_value_reason_labels_cn = [
                _label_cn(reason, COMMENT_LOW_VALUE_REASON_LABEL_CN, "低价值原因待识别")
                for reason in self.low_value_reasons
            ]
        return self


class CommentEvidenceAtomListResponse(Core3RealDataBaseModel):
    items: list[CommentEvidenceAtomResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class CommentTopicHintResponse(Core3RealDataBaseModel):
    topic_hint_id: str = Field(min_length=1)
    comment_evidence_id: str = Field(min_length=1)
    comment_unit_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    topic_code: str = Field(min_length=1)
    topic_name: str = Field(min_length=1)
    topic_group: str = Field(min_length=1)
    match_method: CommentTopicMatchMethod
    matched_terms: list[str] = Field(default_factory=list)
    polarity_hint: CommentSentimentHint = CommentSentimentHint.UNKNOWN
    topic_confidence: float = Field(default=0, ge=0, le=1)
    is_weak_hint: bool = True
    hint_type_label_cn: str | None = None
    activates_product_claim: bool = False
    service_guardrail_flag: bool = False
    topic_hint_status: CommentTopicHintStatus = CommentTopicHintStatus.MATCHED
    topic_hint_status_label_cn: str | None = None
    review_required: bool = False

    @model_validator(mode="after")
    def fill_business_labels(self) -> "CommentTopicHintResponse":
        self.hint_type_label_cn = self.hint_type_label_cn or ("基础线索" if self.is_weak_hint else "已确认主题")
        self.topic_hint_status_label_cn = self.topic_hint_status_label_cn or _label_cn(
            self.topic_hint_status,
            COMMENT_TOPIC_HINT_STATUS_LABEL_CN,
        )
        return self


class CommentTopicHintListResponse(Core3RealDataBaseModel):
    items: list[CommentTopicHintResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class CommentUnitSourceResponse(Core3RealDataBaseModel):
    comment_unit_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    canonical_comment_text: str | None = None
    source_row_count: int = Field(default=0, ge=0)
    source_sentence_count: int = Field(default=0, ge=0)
    sentiment_hint: CommentSentimentHint = CommentSentimentHint.UNKNOWN
    sentiment_hint_label_cn: str | None = None
    low_value_flag: bool = False
    low_value_reasons: list[CommentLowValueReason] = Field(default_factory=list)
    low_value_reason_labels_cn: list[str] = Field(default_factory=list)
    comment_unit_status: CommentUnitStatus = CommentUnitStatus.USABLE
    comment_unit_status_label_cn: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    source_evidence_count: int = Field(default=0, ge=0)
    review_required: bool = False

    @model_validator(mode="after")
    def fill_business_labels(self) -> "CommentUnitSourceResponse":
        self.sentiment_hint_label_cn = self.sentiment_hint_label_cn or _label_cn(
            self.sentiment_hint,
            COMMENT_SENTIMENT_HINT_LABEL_CN,
        )
        self.comment_unit_status_label_cn = self.comment_unit_status_label_cn or _label_cn(
            self.comment_unit_status,
            COMMENT_UNIT_STATUS_LABEL_CN,
        )
        if not self.low_value_reason_labels_cn:
            self.low_value_reason_labels_cn = [
                _label_cn(reason, COMMENT_LOW_VALUE_REASON_LABEL_CN, "低价值原因待识别")
                for reason in self.low_value_reasons
            ]
        return self


class CommentUnitSourceListResponse(Core3RealDataBaseModel):
    items: list[CommentUnitSourceResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class M05RunResponse(Core3RealDataBaseModel):
    result: M05RunResult
    summary_cn: str = Field(min_length=1)
    can_enter_next_stage: bool = False
    next_stage_note_cn: str | None = None


class Core3CommentSignalRunApiRequest(Core3RealDataBaseModel):
    run_id: str | None = None
    module_run_id: str | None = None
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    mode: Core3SourceBatchType = Core3SourceBatchType.INCREMENTAL
    module_version: str = CORE3_M06_MODULE_VERSION
    seed_version: str = CORE3_M06_SEED_VERSION
    rule_version: str = CORE3_M06_RULE_VERSION
    sku_scope: list[str] = Field(default_factory=list)
    signal_types: list[CommentSignalType] = Field(default_factory=list)
    sku_batch_size: int = Field(default=1, ge=1, le=20)
    force_rebuild: bool = False
    triggered_by: str = "system"


class Core3ClaimCommentEnhancementRunApiRequest(Core3RealDataBaseModel):
    run_id: str | None = None
    module_run_id: str | None = None
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    mode: Core3SourceBatchType = Core3SourceBatchType.INCREMENTAL
    module_version: str = CORE3_M04B_MODULE_VERSION
    seed_version: str = CORE3_M04B_SEED_VERSION
    rule_version: str = CORE3_M04B_RULE_VERSION
    sku_scope: list[str] = Field(default_factory=list)
    claim_scope: list[str] = Field(default_factory=list)
    force_rebuild: bool = False
    triggered_by: str = "system"

    @field_validator("sku_scope", "claim_scope")
    @classmethod
    def validate_scope(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("scope values must not contain empty strings")
        return values


class Core3MarketProfileRunApiRequest(Core3RealDataBaseModel):
    run_id: str | None = None
    module_run_id: str | None = None
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    mode: Core3SourceBatchType = Core3SourceBatchType.INCREMENTAL
    module_version: str = CORE3_M07_MODULE_VERSION
    rule_version: str = CORE3_M07_RULE_VERSION
    price_band_rule_version: str = CORE3_M07_PRICE_BAND_RULE_VERSION
    pool_rule_version: str = CORE3_M07_POOL_RULE_VERSION
    sku_scope: list[str] = Field(default_factory=list)
    analysis_windows: list[M07AnalysisWindow] = Field(default_factory=list)
    force_rebuild: bool = False
    triggered_by: str = "system"

    @field_validator("sku_scope")
    @classmethod
    def validate_scope(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("sku_scope must not contain empty strings")
        return values


class Core3SkuSignalProfileRunApiRequest(Core3RealDataBaseModel):
    run_id: str | None = None
    module_run_id: str | None = None
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    mode: Core3SourceBatchType = Core3SourceBatchType.INCREMENTAL
    module_version: str = CORE3_M08_MODULE_VERSION
    rule_version: str = CORE3_M08_RULE_VERSION
    feature_version: str = CORE3_M08_FEATURE_VERSION
    view_schema_version: str = CORE3_M08_VIEW_SCHEMA_VERSION
    sku_scope: list[str] = Field(default_factory=list)
    force_rebuild: bool = False
    triggered_by: str = "system"

    @field_validator("sku_scope")
    @classmethod
    def validate_scope(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("sku_scope must not contain empty strings")
        return values


class Core3CommentNativeDimensionRunApiRequest(Core3RealDataBaseModel):
    run_id: str | None = None
    module_run_id: str | None = None
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    mode: Core3SourceBatchType = Core3SourceBatchType.INCREMENTAL
    module_version: str = CORE3_M08_4_MODULE_VERSION
    rule_version: str = CORE3_M08_4_RULE_VERSION
    seed_version: str = CORE3_M08_4_SEED_VERSION
    force_rebuild: bool = False
    triggered_by: str = "system"


class Core3DimensionOntologyRunApiRequest(Core3RealDataBaseModel):
    run_id: str | None = None
    module_run_id: str | None = None
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    mode: Core3SourceBatchType = Core3SourceBatchType.INCREMENTAL
    module_version: str = CORE3_M08_5_MODULE_VERSION
    rule_version: str = CORE3_M08_5_RULE_VERSION
    seed_version: str = CORE3_M08_5_SEED_VERSION
    force_rebuild: bool = False
    force_new_version: bool = False
    triggered_by: str = "system"


class Core3UserTaskRunApiRequest(Core3RealDataBaseModel):
    run_id: str | None = None
    module_run_id: str | None = None
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    mode: Core3SourceBatchType = Core3SourceBatchType.INCREMENTAL
    module_version: str = CORE3_M09_MODULE_VERSION
    rule_version: str = CORE3_M09_RULE_VERSION
    seed_version: str = CORE3_M09_SEED_VERSION
    sku_scope: list[str] = Field(default_factory=list)
    force_rebuild: bool = False
    triggered_by: str = "system"

    @field_validator("sku_scope")
    @classmethod
    def validate_scope(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("sku_scope must not contain empty strings")
        return values


class Core3TargetGroupRunApiRequest(Core3RealDataBaseModel):
    run_id: str | None = None
    module_run_id: str | None = None
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    mode: Core3SourceBatchType = Core3SourceBatchType.INCREMENTAL
    module_version: str = CORE3_M10_MODULE_VERSION
    rule_version: str = CORE3_M10_RULE_VERSION
    seed_version: str = CORE3_M10_SEED_VERSION
    sku_scope: list[str] = Field(default_factory=list)
    force_rebuild: bool = False
    triggered_by: str = "system"

    @field_validator("sku_scope")
    @classmethod
    def validate_scope(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("sku_scope must not contain empty strings")
        return values


class Core3BattlefieldRunApiRequest(Core3RealDataBaseModel):
    run_id: str | None = None
    module_run_id: str | None = None
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    mode: Core3SourceBatchType = Core3SourceBatchType.INCREMENTAL
    module_version: str = CORE3_M11_MODULE_VERSION
    rule_version: str = CORE3_M11_RULE_VERSION
    seed_version: str = CORE3_M11_SEED_VERSION
    sku_scope: list[str] = Field(default_factory=list)
    force_rebuild: bool = False
    triggered_by: str = "system"

    @field_validator("sku_scope")
    @classmethod
    def validate_scope(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("sku_scope must not contain empty strings")
        return values


class Core3ClaimValueLayerRunApiRequest(Core3RealDataBaseModel):
    run_id: str | None = None
    module_run_id: str | None = None
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    mode: Core3SourceBatchType = Core3SourceBatchType.INCREMENTAL
    module_version: str = CORE3_M11_5_MODULE_VERSION
    rule_version: str = CORE3_M11_5_RULE_VERSION
    claim_seed_version: str = CORE3_M11_5_CLAIM_SEED_VERSION
    battlefield_seed_version: str = CORE3_M11_5_BATTLEFIELD_SEED_VERSION
    sku_scope: list[str] = Field(default_factory=list)
    force_rebuild: bool = False
    triggered_by: str = "system"

    @field_validator("sku_scope")
    @classmethod
    def validate_scope(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("sku_scope must not contain empty strings")
        return values


class Core3CandidateRecallRunApiRequest(Core3RealDataBaseModel):
    run_id: str | None = None
    module_run_id: str | None = None
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    mode: Core3SourceBatchType = Core3SourceBatchType.INCREMENTAL
    module_version: str = CORE3_M12_MODULE_VERSION
    rule_version: str = CORE3_M12_RULE_VERSION
    sku_scope: list[str] = Field(default_factory=list)
    force_rebuild: bool = False
    triggered_by: str = "system"

    @field_validator("sku_scope")
    @classmethod
    def validate_scope(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("sku_scope must not contain empty strings")
        return values


class Core3SkuBusinessProfileRunApiRequest(Core3RealDataBaseModel):
    run_id: str | None = None
    module_run_id: str | None = None
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    mode: Core3SourceBatchType = Core3SourceBatchType.INCREMENTAL
    module_version: str = CORE3_M11_6_MODULE_VERSION
    rule_version: str = CORE3_M11_6_RULE_VERSION
    sku_scope: list[str] = Field(default_factory=list)
    force_rebuild: bool = False
    triggered_by: str = "system"

    @field_validator("sku_scope")
    @classmethod
    def validate_scope(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("sku_scope must not contain empty strings")
        return values


class Core3DimensionSalesReconciliationRunApiRequest(Core3RealDataBaseModel):
    run_id: str | None = None
    module_run_id: str | None = None
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    mode: Core3SourceBatchType = Core3SourceBatchType.INCREMENTAL
    module_version: str = CORE3_M11_7_MODULE_VERSION
    rule_version: str = CORE3_M11_7_RULE_VERSION
    sku_scope: list[str] = Field(default_factory=list)
    force_rebuild: bool = False
    triggered_by: str = "system"

    @field_validator("sku_scope")
    @classmethod
    def validate_scope(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("sku_scope must not contain empty strings")
        return values


class Core3ComponentScoringRunApiRequest(Core3RealDataBaseModel):
    run_id: str | None = None
    module_run_id: str | None = None
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    mode: Core3SourceBatchType = Core3SourceBatchType.INCREMENTAL
    module_version: str = CORE3_M13_MODULE_VERSION
    rule_version: str = CORE3_M13_RULE_VERSION
    component_rule_version: str = CORE3_M13_COMPONENT_RULE_VERSION
    role_rule_version: str = CORE3_M13_ROLE_RULE_VERSION
    sku_scope: list[str] = Field(default_factory=list)
    max_pairs: int = Field(default=250, ge=1, le=2000)
    resume_unscored_only: bool = True
    force_rebuild: bool = False
    triggered_by: str = "system"

    @field_validator("sku_scope")
    @classmethod
    def validate_scope(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("sku_scope must not contain empty strings")
        return values


class Core3SelectionRunApiRequest(Core3RealDataBaseModel):
    run_id: str | None = None
    module_run_id: str | None = None
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    mode: Core3SourceBatchType = Core3SourceBatchType.INCREMENTAL
    module_version: str = CORE3_M14_MODULE_VERSION
    rule_version: str = CORE3_M14_RULE_VERSION
    sku_scope: list[str] = Field(default_factory=list)
    max_targets: int = Field(default=5, ge=1, le=50)
    resume_unselected_only: bool = True
    force_rebuild: bool = False
    triggered_by: str = "system"

    @field_validator("sku_scope")
    @classmethod
    def validate_scope(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("sku_scope must not contain empty strings")
        return values


class Core3EvidenceReportRunApiRequest(Core3RealDataBaseModel):
    run_id: str | None = None
    module_run_id: str | None = None
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    mode: Core3SourceBatchType = Core3SourceBatchType.INCREMENTAL
    module_version: str = CORE3_M15_MODULE_VERSION
    rule_version: str = CORE3_M15_RULE_VERSION
    sku_scope: list[str] = Field(default_factory=list)
    max_targets: int = Field(default=5, ge=1, le=50)
    resume_unreported_only: bool = True
    force_rebuild: bool = False
    triggered_by: str = "system"

    @field_validator("sku_scope")
    @classmethod
    def validate_scope(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("sku_scope must not contain empty strings")
        return values


M07_PRICE_BAND_LABEL_CN: dict[str, str] = {
    M07PriceBand.LOW.value: "低价位",
    M07PriceBand.MID_LOW.value: "中低价位",
    M07PriceBand.MID.value: "主流价位",
    M07PriceBand.MID_HIGH.value: "中高价位",
    M07PriceBand.HIGH.value: "高价位",
    M07PriceBand.UNKNOWN.value: "价位待识别",
}

M07_SAMPLE_STATUS_LABEL_CN: dict[str, str] = {
    M07SampleStatus.SUFFICIENT.value: "市场样本充足",
    M07SampleStatus.LIMITED.value: "市场样本有限",
    M07SampleStatus.INSUFFICIENT.value: "市场样本不足",
    M07SampleStatus.UNKNOWN.value: "市场样本未知",
}

M07_POOL_TYPE_LABEL_CN: dict[str, str] = {
    M07PoolType.SAME_SIZE.value: "同尺寸可比池",
    M07PoolType.ADJACENT_SIZE.value: "相邻尺寸可比池",
    M07PoolType.SAME_PRICE_BAND.value: "同价位可比池",
    M07PoolType.SIZE_PRICE_BAND.value: "尺寸价位可比池",
    M07PoolType.PLATFORM_OVERLAP.value: "平台重合可比池",
    M07PoolType.MARKET_ACTIVE.value: "活跃市场可比池",
}

M07_SIGNAL_LABEL_CN: dict[str, str] = {
    M07MarketSignalCode.PRICE_PERCENTILE_HIGH.value: "价格分位高",
    M07MarketSignalCode.PRICE_PERCENTILE_LOW.value: "价格分位低",
    M07MarketSignalCode.SALES_VOLUME_STRONG.value: "销量强",
    M07MarketSignalCode.SALES_AMOUNT_STRONG.value: "销额强",
    M07MarketSignalCode.PRICE_PER_INCH_VALUE.value: "每英寸价格效率好",
    M07MarketSignalCode.RECENT_PRICE_DROP.value: "近期价格下探",
    M07MarketSignalCode.RECENT_SALES_UP.value: "近期销量上升",
    M07MarketSignalCode.PLATFORM_OVERLAP_STRONG.value: "平台集中度高",
    M07MarketSignalCode.SAMPLE_INSUFFICIENT.value: "样本不足",
}

M07_SIZE_RELATION_LABEL_CN: dict[str, str] = {
    "same": "同尺寸",
    "adjacent": "相邻尺寸",
    "different": "尺寸差异较大",
    "unknown": "尺寸关系待确认",
}

M07_PRICE_RELATION_LABEL_CN: dict[str, str] = {
    "same": "同价位",
    "adjacent": "相邻价位",
    "higher": "价格更高",
    "lower": "价格更低",
    "unknown": "价位关系待确认",
}


class Core3SkuMarketProfileResponse(Core3RealDataBaseModel):
    sku_market_profile_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    analysis_window: M07AnalysisWindow
    period_start_raw: str | None = None
    period_end_raw: str | None = None
    active_week_count: int = Field(default=0, ge=0)
    market_row_count: int = Field(default=0, ge=0)
    screen_size_inch: float | None = None
    size_segment: str = "unknown"
    sales_volume_total: float | None = None
    sales_amount_total: float | None = None
    price_wavg: float | None = None
    price_latest: float | None = None
    price_median: float | None = None
    price_per_inch: float | None = None
    main_channel_type: str | None = None
    main_platform: str | None = None
    platform_share_json: dict[str, Any] = Field(default_factory=dict)
    channel_share_json: dict[str, Any] = Field(default_factory=dict)
    price_change_recent_4w: float | None = None
    sales_growth_recent_4w: float | None = None
    amount_growth_recent_4w: float | None = None
    price_band_category: M07PriceBand = M07PriceBand.UNKNOWN
    price_band_size: M07PriceBand = M07PriceBand.UNKNOWN
    price_band_label_cn: str | None = None
    price_percentile_in_category: float | None = None
    volume_percentile_in_category: float | None = None
    amount_percentile_in_category: float | None = None
    price_percentile_in_size: float | None = None
    volume_percentile_in_size: float | None = None
    amount_percentile_in_size: float | None = None
    market_confidence: float = Field(default=0, ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    sample_status: M07SampleStatus = M07SampleStatus.UNKNOWN
    sample_status_label_cn: str | None = None
    quality_flags: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    business_note_cn: str | None = None
    review_required: bool = False

    @model_validator(mode="after")
    def fill_labels(self) -> "Core3SkuMarketProfileResponse":
        self.price_band_label_cn = self.price_band_label_cn or _label_cn(self.price_band_category, M07_PRICE_BAND_LABEL_CN)
        self.sample_status_label_cn = self.sample_status_label_cn or _label_cn(
            self.sample_status,
            M07_SAMPLE_STATUS_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or _market_profile_business_note(self)
        return self


class Core3SkuMarketProfileListResponse(Core3RealDataBaseModel):
    items: list[Core3SkuMarketProfileResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3MarketSignalResponse(Core3RealDataBaseModel):
    market_signal_id: str = Field(min_length=1)
    sku_market_profile_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    analysis_window: M07AnalysisWindow
    signal_code: M07MarketSignalCode
    signal_name: str = Field(min_length=1)
    signal_label_cn: str | None = None
    signal_value: float | None = None
    signal_strength: float = Field(default=0, ge=0, le=1)
    signal_level: M07SignalLevel
    basis_metric: str = Field(min_length=1)
    basis_value_json: dict[str, Any] = Field(default_factory=dict)
    comparison_scope: str = Field(min_length=1)
    comparison_scope_key: str | None = None
    polarity: M07Polarity
    downstream_usage_json: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0, ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    sample_status: M07SampleStatus = M07SampleStatus.UNKNOWN
    evidence_ids: list[str] = Field(default_factory=list)
    business_note_cn: str | None = None
    review_required: bool = False

    @model_validator(mode="after")
    def fill_labels(self) -> "Core3MarketSignalResponse":
        self.signal_label_cn = self.signal_label_cn or _label_cn(self.signal_code, M07_SIGNAL_LABEL_CN)
        self.business_note_cn = self.business_note_cn or _market_signal_business_note(self)
        return self


class Core3MarketSignalListResponse(Core3RealDataBaseModel):
    items: list[Core3MarketSignalResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3ComparablePoolResponse(Core3RealDataBaseModel):
    pool_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    target_model_name: str | None = None
    target_brand_name: str | None = None
    analysis_window: M07AnalysisWindow
    pool_type: M07PoolType
    pool_type_label_cn: str | None = None
    pool_condition_json: dict[str, Any] = Field(default_factory=dict)
    candidate_sku_codes: list[str] = Field(default_factory=list)
    pool_sku_count: int = Field(default=0, ge=0)
    valid_member_count: int = Field(default=0, ge=0)
    target_included: bool = False
    target_size_segment: str = "unknown"
    target_price_band: M07PriceBand = M07PriceBand.UNKNOWN
    median_price: float | None = None
    median_volume: float | None = None
    median_amount: float | None = None
    price_distribution_json: dict[str, Any] = Field(default_factory=dict)
    volume_distribution_json: dict[str, Any] = Field(default_factory=dict)
    amount_distribution_json: dict[str, Any] = Field(default_factory=dict)
    platform_distribution_json: dict[str, Any] = Field(default_factory=dict)
    pool_confidence: float = Field(default=0, ge=0, le=1)
    sample_status: M07SampleStatus = M07SampleStatus.UNKNOWN
    sample_status_label_cn: str | None = None
    basis: str = Field(min_length=1)
    quality_flags: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    business_note_cn: str | None = None
    review_required: bool = False

    @model_validator(mode="after")
    def fill_labels(self) -> "Core3ComparablePoolResponse":
        self.pool_type_label_cn = self.pool_type_label_cn or _label_cn(self.pool_type, M07_POOL_TYPE_LABEL_CN)
        self.sample_status_label_cn = self.sample_status_label_cn or _label_cn(
            self.sample_status,
            M07_SAMPLE_STATUS_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or _comparable_pool_business_note(self)
        return self


class Core3ComparablePoolListResponse(Core3RealDataBaseModel):
    items: list[Core3ComparablePoolResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3MarketPoolMemberResponse(Core3RealDataBaseModel):
    pool_member_id: str = Field(min_length=1)
    pool_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    member_sku_code: str = Field(min_length=1)
    analysis_window: M07AnalysisWindow
    member_model_name: str | None = None
    member_brand_name: str | None = None
    is_target_self: bool = False
    size_relation: str = "unknown"
    price_band_relation: str = "unknown"
    platform_overlap_score: float = Field(default=0, ge=0, le=1)
    channel_overlap_score: float = Field(default=0, ge=0, le=1)
    price_gap_to_target: float | None = None
    price_gap_pct_to_target: float | None = None
    volume_gap_to_target: float | None = None
    amount_gap_to_target: float | None = None
    member_price_percentile_in_pool: float | None = None
    member_volume_percentile_in_pool: float | None = None
    member_amount_percentile_in_pool: float | None = None
    member_market_confidence: float = Field(default=0, ge=0, le=1)
    relation_strength: float = Field(default=0, ge=0, le=1)
    quality_flags: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    business_note_cn: str | None = None
    review_required: bool = False

    @model_validator(mode="after")
    def fill_note(self) -> "Core3MarketPoolMemberResponse":
        self.business_note_cn = self.business_note_cn or _pool_member_business_note(self)
        return self


class Core3MarketPoolMemberListResponse(Core3RealDataBaseModel):
    items: list[Core3MarketPoolMemberResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


M08_PROFILE_STATUS_LABEL_CN: dict[str, str] = {
    M08ProfileStatus.READY.value: "可支撑后续分析",
    M08ProfileStatus.LIMITED.value: "可用但需带限制说明",
    M08ProfileStatus.REVIEW_REQUIRED.value: "需业务复核后使用",
    M08ProfileStatus.INSUFFICIENT.value: "证据不足",
    M08ProfileStatus.BLOCKED.value: "暂不可用",
    M08ProfileStatus.FAILED.value: "生成失败",
}

M08_COVERAGE_STATUS_LABEL_CN: dict[str, str] = {
    M08CoverageStatus.COVERED.value: "已有证据",
    M08CoverageStatus.PARTIALLY_COVERED.value: "证据不完整",
    M08CoverageStatus.MISSING.value: "缺少证据",
    M08CoverageStatus.UNKNOWN.value: "状态待确认",
    M08CoverageStatus.CONFLICT.value: "证据冲突",
    M08CoverageStatus.NOT_APPLICABLE.value: "不适用",
}

M08_SIGNAL_DOMAIN_LABEL_CN: dict[str, str] = {
    M08SignalDomain.SKU_MASTER.value: "商品主数据",
    M08SignalDomain.PARAM.value: "参数证据",
    M08SignalDomain.CLAIM.value: "卖点证据",
    M08SignalDomain.CLAIM_COMMENT_VALIDATION.value: "卖点体验验证",
    M08SignalDomain.COMMENT.value: "评论信号",
    M08SignalDomain.MARKET.value: "市场表现",
    M08SignalDomain.POOL.value: "市场对照池",
    M08SignalDomain.QUALITY.value: "质量风险",
    M08SignalDomain.DOWNSTREAM_VIEW.value: "下游特征视图",
}

M08_FOR_MODULE_LABEL_CN: dict[str, str] = {
    M08ForModule.M08_4.value: "评论原生业务维度发现",
    M08ForModule.M08_5.value: "业务维度本体校准",
    M08ForModule.M09.value: "用户任务候选",
    M08ForModule.M10.value: "目标客群候选",
    M08ForModule.M11.value: "价值战场候选",
    M08ForModule.M11_5.value: "卖点价值层判断",
    M08ForModule.M12.value: "候选 SKU 召回输入",
    M08ForModule.M13.value: "候选解释与复核输入",
    M08ForModule.M14.value: "排序前约束输入",
    M08ForModule.M15.value: "业务展示证据素材",
}


class Core3SkuSignalProfileResponse(Core3RealDataBaseModel):
    sku_signal_profile_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    profile_scope: M08ProfileScope = M08ProfileScope.SKU_DEFAULT
    analysis_window: str = "full_observed_window"
    source_coverage_json: dict[str, Any] = Field(default_factory=dict)
    sku_master_json: dict[str, Any] = Field(default_factory=dict)
    core_params_json: dict[str, Any] = Field(default_factory=dict)
    param_profile_json: dict[str, Any] = Field(default_factory=dict)
    claim_activation_summary_json: dict[str, Any] = Field(default_factory=dict)
    claim_evidence_breakdown_json: dict[str, Any] = Field(default_factory=dict)
    comment_signal_summary_json: dict[str, Any] = Field(default_factory=dict)
    comment_quality_json: dict[str, Any] = Field(default_factory=dict)
    market_summary_json: dict[str, Any] = Field(default_factory=dict)
    market_signal_summary_json: dict[str, Any] = Field(default_factory=dict)
    comparable_pool_summary_json: dict[str, Any] = Field(default_factory=dict)
    business_signal_index_json: dict[str, Any] = Field(default_factory=dict)
    missing_signals_json: list[dict[str, Any]] = Field(default_factory=list)
    risk_signals_json: list[dict[str, Any]] = Field(default_factory=list)
    domain_completeness_json: dict[str, Any] = Field(default_factory=dict)
    data_completeness_score: float = Field(default=0, ge=0, le=1)
    domain_confidence_json: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0, ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    profile_status: M08ProfileStatus = M08ProfileStatus.LIMITED
    profile_status_label_cn: str | None = None
    downstream_ready_json: dict[str, Any] = Field(default_factory=dict)
    evidence_summary_json: dict[str, Any] = Field(default_factory=dict)
    representative_evidence_ids: list[str] = Field(default_factory=list)
    profile_hash: str
    review_required: bool = False
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_profile_note(self) -> "Core3SkuSignalProfileResponse":
        self.profile_status_label_cn = self.profile_status_label_cn or _label_cn(
            self.profile_status,
            M08_PROFILE_STATUS_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or _sku_signal_profile_business_note(self)
        return self


class Core3SkuSignalProfileListResponse(Core3RealDataBaseModel):
    items: list[Core3SkuSignalProfileResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3SkuSignalEvidenceMatrixResponse(Core3RealDataBaseModel):
    sku_signal_evidence_matrix_id: str = Field(min_length=1)
    sku_signal_profile_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    domain: M08SignalDomain
    domain_label_cn: str | None = None
    sub_domain: str = Field(min_length=1)
    feature_code: str | None = None
    evidence_role: str = "representative"
    coverage_status: M08CoverageStatus = M08CoverageStatus.UNKNOWN
    coverage_status_label_cn: str | None = None
    evidence_count: int = Field(default=0, ge=0)
    high_confidence_count: int = Field(default=0, ge=0)
    medium_confidence_count: int = Field(default=0, ge=0)
    low_confidence_count: int = Field(default=0, ge=0)
    representative_evidence_ids: list[str] = Field(default_factory=list)
    source_record_refs_json: dict[str, Any] = Field(default_factory=dict)
    missing_flag: bool = False
    missing_reason_code: str | None = None
    risk_flags_json: list[str] = Field(default_factory=list)
    domain_confidence: float = Field(default=0, ge=0, le=1)
    review_required: bool = False
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_matrix_note(self) -> "Core3SkuSignalEvidenceMatrixResponse":
        self.domain_label_cn = self.domain_label_cn or _label_cn(self.domain, M08_SIGNAL_DOMAIN_LABEL_CN)
        self.coverage_status_label_cn = self.coverage_status_label_cn or _label_cn(
            self.coverage_status,
            M08_COVERAGE_STATUS_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or _sku_signal_matrix_business_note(self)
        return self


class Core3SkuSignalEvidenceMatrixListResponse(Core3RealDataBaseModel):
    items: list[Core3SkuSignalEvidenceMatrixResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3SkuDownstreamFeatureViewResponse(Core3RealDataBaseModel):
    sku_downstream_feature_view_id: str = Field(min_length=1)
    sku_signal_profile_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    for_module: M08ForModule
    for_module_label_cn: str | None = None
    view_role: M08ViewRole = M08ViewRole.PRIMARY_INPUT
    view_schema_version: str = CORE3_M08_VIEW_SCHEMA_VERSION
    required_feature_codes_json: list[str] = Field(default_factory=list)
    optional_feature_codes_json: list[str] = Field(default_factory=list)
    feature_payload_json: dict[str, Any] = Field(default_factory=dict)
    feature_quality_flags_json: list[str] = Field(default_factory=list)
    required_missing_fields_json: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_matrix_refs_json: list[str] = Field(default_factory=list)
    ready_for_module: bool = False
    block_reason_json: list[str] = Field(default_factory=list)
    review_required: bool = False
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_view_note(self) -> "Core3SkuDownstreamFeatureViewResponse":
        self.for_module_label_cn = self.for_module_label_cn or _label_cn(self.for_module, M08_FOR_MODULE_LABEL_CN)
        self.business_note_cn = self.business_note_cn or _sku_signal_view_business_note(self)
        return self


class Core3SkuDownstreamFeatureViewListResponse(Core3RealDataBaseModel):
    items: list[Core3SkuDownstreamFeatureViewResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3DimensionOntologyVersionResponse(Core3RealDataBaseModel):
    ontology_version_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    ontology_version: str = Field(min_length=1)
    base_seed_version: str = Field(min_length=1)
    base_seed_hash: str = Field(min_length=1)
    source_profile_batch_hash: str = Field(min_length=1)
    calibration_scope: str = "project_batch"
    status: str = "active"
    dimension_count_json: dict[str, Any] = Field(default_factory=dict)
    quality_summary_json: dict[str, Any] = Field(default_factory=dict)
    review_required: bool = False
    review_status: str = "auto_pass"
    rule_version: str = CORE3_M08_5_RULE_VERSION
    input_fingerprint: str = Field(min_length=1)
    result_hash: str = Field(min_length=1)
    is_current: bool = True
    summary_cn: str | None = None

    @model_validator(mode="after")
    def fill_summary(self) -> "Core3DimensionOntologyVersionResponse":
        self.summary_cn = self.summary_cn or (
            f"当前本体版本包含 {sum(int(v) for v in self.dimension_count_json.values())} 个业务维度，"
            f"复核状态为 {self.review_status}。"
        )
        return self


class Core3DimensionDefinitionResponse(Core3RealDataBaseModel):
    dimension_definition_id: str = Field(min_length=1)
    ontology_version_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    dimension_type: str = Field(min_length=1)
    dimension_code: str = Field(min_length=1)
    base_dimension_code: str | None = None
    dimension_name_cn: str = Field(min_length=1)
    definition_cn: str = Field(min_length=1)
    business_question_cn: str = Field(min_length=1)
    include_rule_json: dict[str, Any] = Field(default_factory=dict)
    exclude_rule_json: dict[str, Any] = Field(default_factory=dict)
    required_evidence_json: dict[str, Any] = Field(default_factory=dict)
    optional_evidence_json: dict[str, Any] = Field(default_factory=dict)
    negative_evidence_json: dict[str, Any] = Field(default_factory=dict)
    boundary_policy: str = Field(min_length=1)
    allocation_policy: str = Field(min_length=1)
    candidate_trigger_policy_json: dict[str, Any] = Field(default_factory=dict)
    profile_eligibility_policy_json: dict[str, Any] = Field(default_factory=dict)
    downstream_policy_json: dict[str, Any] = Field(default_factory=dict)
    distinctiveness_score: float = Field(default=0, ge=0, le=1)
    support_score: float = Field(default=0, ge=0, le=1)
    sku_coverage_count: int = Field(default=0, ge=0)
    strong_sku_coverage_count: int = Field(default=0, ge=0)
    definition_status: str = Field(min_length=1)
    review_required: bool = False
    review_reason_json: dict[str, Any] = Field(default_factory=dict)
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_note(self) -> "Core3DimensionDefinitionResponse":
        self.business_note_cn = self.business_note_cn or (
            f"{self.dimension_name_cn} 用于回答“{self.business_question_cn}”，"
            f"边界为 {self.boundary_policy}，分配策略为 {self.allocation_policy}。"
        )
        return self


class Core3DimensionDefinitionListResponse(Core3RealDataBaseModel):
    items: list[Core3DimensionDefinitionResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3DimensionCandidateSnapshotResponse(Core3RealDataBaseModel):
    candidate_snapshot_id: str = Field(min_length=1)
    ontology_version_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    snapshot_type: str = Field(min_length=1)
    signal_type: str = Field(min_length=1)
    signal_code: str = Field(min_length=1)
    signal_name_cn: str = Field(min_length=1)
    sentence_count: int = Field(default=0, ge=0)
    sku_count: int = Field(default=0, ge=0)
    strong_sentence_count: int = Field(default=0, ge=0)
    service_sentence_count: int = Field(default=0, ge=0)
    low_value_sentence_count: int = Field(default=0, ge=0)
    avg_signal_score: float = Field(default=0, ge=0, le=1)
    coverage_ratio: float = Field(default=0, ge=0, le=1)
    specificity_score: float = Field(default=0, ge=0, le=1)
    distribution_json: dict[str, Any] = Field(default_factory=dict)
    representative_evidence_ids: list[str] = Field(default_factory=list)


class Core3DimensionCandidateSnapshotListResponse(Core3RealDataBaseModel):
    items: list[Core3DimensionCandidateSnapshotResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3DimensionMappingRuleResponse(Core3RealDataBaseModel):
    dimension_mapping_rule_id: str = Field(min_length=1)
    ontology_version_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    source_type: str = Field(min_length=1)
    source_code: str = Field(min_length=1)
    source_name_cn: str | None = None
    target_dimension_type: str = Field(min_length=1)
    target_dimension_code: str = Field(min_length=1)
    mapping_level: str = Field(min_length=1)
    mapping_strength: float = Field(default=0, ge=0, le=1)
    requires_product_anchor: bool = False
    requires_market_anchor: bool = False
    service_guardrail_flag: bool = False
    low_value_guardrail_flag: bool = False
    rule_expr_json: dict[str, Any] = Field(default_factory=dict)
    reason_cn: str = ""
    active: bool = True


class Core3DimensionMappingRuleListResponse(Core3RealDataBaseModel):
    items: list[Core3DimensionMappingRuleResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3DimensionCalibrationIssueResponse(Core3RealDataBaseModel):
    calibration_issue_id: str = Field(min_length=1)
    ontology_version_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    issue_scope: str = Field(min_length=1)
    dimension_type: str | None = None
    dimension_code: str | None = None
    source_type: str | None = None
    source_code: str | None = None
    issue_code: str = Field(min_length=1)
    severity: str = Field(min_length=1)
    issue_message_cn: str = Field(min_length=1)
    evidence_json: dict[str, Any] = Field(default_factory=dict)
    suggested_action_cn: str = Field(min_length=1)
    review_status: str = "open"


class Core3DimensionCalibrationIssueListResponse(Core3RealDataBaseModel):
    items: list[Core3DimensionCalibrationIssueResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


M09_TASK_RELATION_LABEL_CN: dict[str, str] = {
    M09TaskRelationLevel.MAIN.value: "主任务",
    M09TaskRelationLevel.SECONDARY.value: "次任务",
    M09TaskRelationLevel.WEAK.value: "弱相关任务",
    M09TaskRelationLevel.INSUFFICIENT.value: "证据不足",
    M09TaskRelationLevel.BLOCKED.value: "输入阻塞",
}

M09_TASK_CANDIDATE_STATUS_LABEL_CN: dict[str, str] = {
    M09TaskCandidateStatus.ACTIVE.value: "已进入候选",
    M09TaskCandidateStatus.REVIEW_REQUIRED.value: "需复核后使用",
    M09TaskCandidateStatus.REJECTED.value: "证据不足未采用",
    M09TaskCandidateStatus.BLOCKED.value: "输入阻塞",
}

M09_TASK_EVIDENCE_DOMAIN_LABEL_CN: dict[str, str] = {
    M09TaskEvidenceDomain.PARAM.value: "能力基础",
    M09TaskEvidenceDomain.CLAIM.value: "价值表达",
    M09TaskEvidenceDomain.COMMENT.value: "用户反馈",
    M09TaskEvidenceDomain.MARKET.value: "市场验证",
    M09TaskEvidenceDomain.RISK.value: "待复核点",
    M09TaskEvidenceDomain.SEED.value: "任务本体",
    M09TaskEvidenceDomain.PROFILE.value: "画像可信度",
}

M09_TASK_SUPPORT_LEVEL_LABEL_CN: dict[str, str] = {
    M09TaskSupportLevel.STRONG.value: "强支撑",
    M09TaskSupportLevel.MEDIUM.value: "中等支撑",
    M09TaskSupportLevel.WEAK.value: "弱支撑",
    M09TaskSupportLevel.MISSING.value: "缺少证据",
    M09TaskSupportLevel.CONFLICT.value: "存在冲突",
    M09TaskSupportLevel.NOT_APPLICABLE.value: "不适用",
}


class Core3SkuTaskCandidateResponse(Core3RealDataBaseModel):
    sku_task_candidate_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    task_code: str = Field(min_length=1)
    task_name_cn: str = Field(min_length=1)
    task_definition_cn: str = Field(min_length=1)
    candidate_status: M09TaskCandidateStatus = M09TaskCandidateStatus.ACTIVE
    candidate_status_label_cn: str | None = None
    candidate_sources_json: list[str] = Field(default_factory=list)
    candidate_source_count: int = Field(default=0, ge=0)
    initial_candidate_score: float = Field(default=0, ge=0, le=1)
    candidate_reason_cn: str
    candidate_reason_parts_json: dict[str, Any] = Field(default_factory=dict)
    candidate_evidence_refs_json: list[str] = Field(default_factory=list)
    review_required: bool = False
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_candidate_note(self) -> "Core3SkuTaskCandidateResponse":
        self.candidate_status_label_cn = self.candidate_status_label_cn or _label_cn(
            self.candidate_status,
            M09_TASK_CANDIDATE_STATUS_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or _sku_task_candidate_business_note(self)
        return self


class Core3SkuTaskCandidateListResponse(Core3RealDataBaseModel):
    items: list[Core3SkuTaskCandidateResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3SkuTaskScoreResponse(Core3RealDataBaseModel):
    sku_task_score_id: str = Field(min_length=1)
    sku_task_candidate_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    task_code: str = Field(min_length=1)
    task_name_cn: str = Field(min_length=1)
    task_score: float = Field(default=0, ge=0, le=1)
    raw_task_score: float = Field(default=0, ge=0, le=1)
    relation_level: M09TaskRelationLevel = M09TaskRelationLevel.INSUFFICIENT
    relation_level_label_cn: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)
    param_signal_score: float = Field(default=0, ge=0, le=1)
    claim_signal_score: float = Field(default=0, ge=0, le=1)
    comment_signal_score: float = Field(default=0, ge=0, le=1)
    market_signal_score: float = Field(default=0, ge=0, le=1)
    risk_penalty: float = Field(default=0, ge=0, le=1)
    cap_applied_json: list[dict[str, Any]] = Field(default_factory=list)
    evidence_domain_coverage_json: dict[str, Any] = Field(default_factory=dict)
    business_reason_cn: str
    business_reason_parts_json: dict[str, Any] = Field(default_factory=dict)
    next_module_payload_json: dict[str, Any] = Field(default_factory=dict)
    review_required: bool = False
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_score_note(self) -> "Core3SkuTaskScoreResponse":
        self.relation_level_label_cn = self.relation_level_label_cn or _label_cn(
            self.relation_level,
            M09_TASK_RELATION_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or _sku_task_score_business_note(self)
        return self


class Core3SkuTaskScoreListResponse(Core3RealDataBaseModel):
    items: list[Core3SkuTaskScoreResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3SkuTaskEvidenceBreakdownResponse(Core3RealDataBaseModel):
    sku_task_evidence_breakdown_id: str = Field(min_length=1)
    sku_task_score_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    task_code: str = Field(min_length=1)
    task_name_cn: str = Field(min_length=1)
    evidence_domain: M09TaskEvidenceDomain
    evidence_domain_label_cn: str | None = None
    support_level: M09TaskSupportLevel = M09TaskSupportLevel.MISSING
    support_level_label_cn: str | None = None
    domain_score: float = Field(default=0, ge=0, le=1)
    domain_weight: float = Field(default=0, ge=0, le=1)
    weighted_score: float = Field(default=0, ge=0, le=1)
    evidence_count: int = Field(default=0, ge=0)
    dedup_comment_count: int = Field(default=0, ge=0)
    effective_sentence_count: int = Field(default=0, ge=0)
    evidence_refs_json: list[str] = Field(default_factory=list)
    source_feature_refs_json: list[dict[str, Any]] = Field(default_factory=list)
    domain_reason_cn: str
    domain_risk_json: dict[str, Any] = Field(default_factory=dict)
    review_required: bool = False
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_breakdown_note(self) -> "Core3SkuTaskEvidenceBreakdownResponse":
        self.evidence_domain_label_cn = self.evidence_domain_label_cn or _label_cn(
            self.evidence_domain,
            M09_TASK_EVIDENCE_DOMAIN_LABEL_CN,
        )
        self.support_level_label_cn = self.support_level_label_cn or _label_cn(
            self.support_level,
            M09_TASK_SUPPORT_LEVEL_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or _sku_task_breakdown_business_note(self)
        return self


class Core3SkuTaskEvidenceBreakdownListResponse(Core3RealDataBaseModel):
    items: list[Core3SkuTaskEvidenceBreakdownResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3SkuTaskReviewIssueResponse(Core3RealDataBaseModel):
    sku_task_review_issue_id: str = Field(min_length=1)
    sku_task_score_id: str | None = None
    sku_task_candidate_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    task_code: str | None = None
    task_name_cn: str | None = None
    issue_type: str
    issue_severity: str = "warning"
    issue_status: str = "open"
    issue_reason_cn: str
    issue_detail_json: dict[str, Any] = Field(default_factory=dict)
    affected_output_json: dict[str, Any] = Field(default_factory=dict)
    evidence_refs_json: list[str] = Field(default_factory=list)
    suggested_action_cn: str
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_issue_note(self) -> "Core3SkuTaskReviewIssueResponse":
        self.business_note_cn = self.business_note_cn or self.issue_reason_cn
        return self


class Core3SkuTaskReviewIssueListResponse(Core3RealDataBaseModel):
    items: list[Core3SkuTaskReviewIssueResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


M10_TARGET_GROUP_RELATION_LABEL_CN: dict[str, str] = {
    M10TargetGroupRelationLevel.MAIN.value: "主客群",
    M10TargetGroupRelationLevel.SECONDARY.value: "次客群",
    M10TargetGroupRelationLevel.WEAK.value: "弱相关客群",
    M10TargetGroupRelationLevel.INSUFFICIENT.value: "证据不足",
    M10TargetGroupRelationLevel.BLOCKED.value: "输入阻塞",
}

M10_TARGET_GROUP_CANDIDATE_STATUS_LABEL_CN: dict[str, str] = {
    M10TargetGroupCandidateStatus.ACTIVE.value: "已进入客群候选",
    M10TargetGroupCandidateStatus.REVIEW_REQUIRED.value: "需复核后使用",
    M10TargetGroupCandidateStatus.REJECTED.value: "证据不足未采用",
    M10TargetGroupCandidateStatus.BLOCKED.value: "输入阻塞",
}

M10_TARGET_GROUP_EVIDENCE_DOMAIN_LABEL_CN: dict[str, str] = {
    M10TargetGroupEvidenceDomain.TASK.value: "购买任务",
    M10TargetGroupEvidenceDomain.COMMENT.value: "用户线索",
    M10TargetGroupEvidenceDomain.PRICE_CHANNEL.value: "价格渠道",
    M10TargetGroupEvidenceDomain.MARKET.value: "市场验证",
    M10TargetGroupEvidenceDomain.SERVICE.value: "服务侧面",
    M10TargetGroupEvidenceDomain.RISK.value: "待复核点",
    M10TargetGroupEvidenceDomain.SEED.value: "客群本体",
    M10TargetGroupEvidenceDomain.PROFILE.value: "画像可信度",
}

M10_TARGET_GROUP_SUPPORT_LEVEL_LABEL_CN: dict[str, str] = {
    M10TargetGroupSupportLevel.STRONG.value: "强支撑",
    M10TargetGroupSupportLevel.MEDIUM.value: "中等支撑",
    M10TargetGroupSupportLevel.WEAK.value: "弱支撑",
    M10TargetGroupSupportLevel.MISSING.value: "缺少证据",
    M10TargetGroupSupportLevel.CONFLICT.value: "存在冲突",
    M10TargetGroupSupportLevel.NOT_APPLICABLE.value: "不适用",
}


class Core3SkuTargetGroupCandidateResponse(Core3RealDataBaseModel):
    sku_target_group_candidate_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    target_group_code: str = Field(min_length=1)
    target_group_name_cn: str = Field(min_length=1)
    target_group_definition_cn: str = Field(min_length=1)
    candidate_source_json: list[str] = Field(default_factory=list)
    candidate_source_count: int = Field(default=0, ge=0)
    source_task_codes_json: list[str] = Field(default_factory=list)
    candidate_initial_score: float = Field(default=0, ge=0, le=1)
    candidate_reason_cn: str
    candidate_status: M10TargetGroupCandidateStatus = M10TargetGroupCandidateStatus.ACTIVE
    candidate_status_label_cn: str | None = None
    missing_signals_json: list[dict[str, Any] | str] = Field(default_factory=list)
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    review_required: bool = False
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_candidate_note(self) -> "Core3SkuTargetGroupCandidateResponse":
        self.candidate_status_label_cn = self.candidate_status_label_cn or _label_cn(
            self.candidate_status,
            M10_TARGET_GROUP_CANDIDATE_STATUS_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or _sku_target_group_candidate_business_note(self)
        return self


class Core3SkuTargetGroupCandidateListResponse(Core3RealDataBaseModel):
    items: list[Core3SkuTargetGroupCandidateResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3SkuTargetGroupScoreResponse(Core3RealDataBaseModel):
    sku_target_group_score_id: str = Field(min_length=1)
    sku_target_group_candidate_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    target_group_code: str = Field(min_length=1)
    target_group_name_cn: str = Field(min_length=1)
    target_group_definition_cn: str = Field(min_length=1)
    task_support_score: float = Field(default=0, ge=0, le=1)
    comment_group_signal_score: float = Field(default=0, ge=0, le=1)
    price_channel_fit_score: float = Field(default=0, ge=0, le=1)
    market_validation_score: float = Field(default=0, ge=0, le=1)
    service_side_score: float = Field(default=0, ge=0, le=1)
    raw_target_group_score: float = Field(default=0, ge=0, le=1)
    risk_penalty: float = Field(default=0, ge=0, le=1)
    target_group_score: float = Field(default=0, ge=0, le=1)
    relation_level: M10TargetGroupRelationLevel = M10TargetGroupRelationLevel.INSUFFICIENT
    relation_level_label_cn: str | None = None
    relation_reason_json: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0, ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    evidence_domain_count: int = Field(default=0, ge=0)
    effective_domain_json: dict[str, Any] = Field(default_factory=dict)
    source_task_scores_json: list[dict[str, Any]] = Field(default_factory=list)
    score_breakdown_json: dict[str, Any] = Field(default_factory=dict)
    cap_rule_applied_json: list[dict[str, Any]] = Field(default_factory=list)
    missing_signals_json: list[dict[str, Any] | str] = Field(default_factory=list)
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    business_reason_cn: str
    business_reason_parts_json: dict[str, Any] = Field(default_factory=dict)
    review_required: bool = False
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_score_note(self) -> "Core3SkuTargetGroupScoreResponse":
        self.relation_level_label_cn = self.relation_level_label_cn or _label_cn(
            self.relation_level,
            M10_TARGET_GROUP_RELATION_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or _sku_target_group_score_business_note(self)
        return self


class Core3SkuTargetGroupScoreListResponse(Core3RealDataBaseModel):
    items: list[Core3SkuTargetGroupScoreResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3SkuTargetGroupEvidenceBreakdownResponse(Core3RealDataBaseModel):
    sku_target_group_evidence_breakdown_id: str = Field(min_length=1)
    sku_target_group_score_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    target_group_code: str = Field(min_length=1)
    target_group_name_cn: str = Field(min_length=1)
    evidence_domain: M10TargetGroupEvidenceDomain
    evidence_domain_label_cn: str | None = None
    support_level: M10TargetGroupSupportLevel = M10TargetGroupSupportLevel.MISSING
    support_level_label_cn: str | None = None
    domain_score: float = Field(default=0, ge=0, le=1)
    domain_weight: float = Field(default=0, ge=0, le=1)
    weighted_score: float = Field(default=0, ge=0, le=1)
    evidence_count: int = Field(default=0, ge=0)
    evidence_ids: list[str] = Field(default_factory=list)
    source_feature_refs_json: list[dict[str, Any]] = Field(default_factory=list)
    domain_reason_cn: str
    domain_risk_json: dict[str, Any] = Field(default_factory=dict)
    review_required: bool = False
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_breakdown_note(self) -> "Core3SkuTargetGroupEvidenceBreakdownResponse":
        self.evidence_domain_label_cn = self.evidence_domain_label_cn or _label_cn(
            self.evidence_domain,
            M10_TARGET_GROUP_EVIDENCE_DOMAIN_LABEL_CN,
        )
        self.support_level_label_cn = self.support_level_label_cn or _label_cn(
            self.support_level,
            M10_TARGET_GROUP_SUPPORT_LEVEL_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or _sku_target_group_breakdown_business_note(self)
        return self


class Core3SkuTargetGroupEvidenceBreakdownListResponse(Core3RealDataBaseModel):
    items: list[Core3SkuTargetGroupEvidenceBreakdownResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3SkuTargetGroupReviewIssueResponse(Core3RealDataBaseModel):
    sku_target_group_review_issue_id: str = Field(min_length=1)
    sku_target_group_score_id: str | None = None
    sku_target_group_candidate_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    target_group_code: str | None = None
    target_group_name_cn: str | None = None
    issue_type: str
    issue_severity: str = "warning"
    issue_status: str = "open"
    issue_reason_cn: str
    issue_detail_json: dict[str, Any] = Field(default_factory=dict)
    affected_output_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    suggested_action_cn: str
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_issue_note(self) -> "Core3SkuTargetGroupReviewIssueResponse":
        self.business_note_cn = self.business_note_cn or self.issue_reason_cn
        return self


class Core3SkuTargetGroupReviewIssueListResponse(Core3RealDataBaseModel):
    items: list[Core3SkuTargetGroupReviewIssueResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


M11_BATTLEFIELD_RELATION_LABEL_CN: dict[str, str] = {
    M11BattlefieldRelationLevel.MAIN.value: "主战场",
    M11BattlefieldRelationLevel.SECONDARY.value: "次战场",
    M11BattlefieldRelationLevel.OPPORTUNITY.value: "机会战场",
    M11BattlefieldRelationLevel.WEAK.value: "弱相关战场",
    M11BattlefieldRelationLevel.INSUFFICIENT.value: "证据不足",
    M11BattlefieldRelationLevel.BLOCKED.value: "输入阻塞",
}

M11_BATTLEFIELD_CANDIDATE_STATUS_LABEL_CN: dict[str, str] = {
    M11BattlefieldCandidateStatus.ACTIVE.value: "已进入战场候选",
    M11BattlefieldCandidateStatus.REVIEW_REQUIRED.value: "需复核后使用",
    M11BattlefieldCandidateStatus.REJECTED.value: "证据不足未采用",
    M11BattlefieldCandidateStatus.BLOCKED.value: "输入阻塞",
}

M11_BATTLEFIELD_EVIDENCE_DOMAIN_LABEL_CN: dict[str, str] = {
    M11BattlefieldEvidenceDomain.TASK.value: "用户任务",
    M11BattlefieldEvidenceDomain.TARGET_GROUP.value: "目标客群",
    M11BattlefieldEvidenceDomain.CLAIM.value: "核心卖点",
    M11BattlefieldEvidenceDomain.PARAM.value: "关键参数",
    M11BattlefieldEvidenceDomain.COMMENT.value: "用户评论",
    M11BattlefieldEvidenceDomain.MARKET.value: "市场验证",
    M11BattlefieldEvidenceDomain.SERVICE.value: "服务侧面",
    M11BattlefieldEvidenceDomain.RISK.value: "待复核点",
    M11BattlefieldEvidenceDomain.SEED.value: "战场本体",
    M11BattlefieldEvidenceDomain.PROFILE.value: "画像可信度",
}

M11_BATTLEFIELD_SUPPORT_LEVEL_LABEL_CN: dict[str, str] = {
    M11BattlefieldSupportLevel.STRONG.value: "强支撑",
    M11BattlefieldSupportLevel.MEDIUM.value: "中等支撑",
    M11BattlefieldSupportLevel.WEAK.value: "弱支撑",
    M11BattlefieldSupportLevel.MISSING.value: "缺少证据",
    M11BattlefieldSupportLevel.CONFLICT.value: "存在冲突",
    M11BattlefieldSupportLevel.NOT_APPLICABLE.value: "不适用",
}

M11_COMPETITOR_SELECTION_ROLE_LABEL_CN: dict[str, str] = {
    M11CompetitorSelectionRole.PRIMARY_SEARCH_CONTEXT.value: "主召回语境",
    M11CompetitorSelectionRole.SECONDARY_SEARCH_CONTEXT.value: "辅助召回语境",
    M11CompetitorSelectionRole.OPPORTUNITY_MONITORING.value: "机会监控语境",
    M11CompetitorSelectionRole.RISK_OR_SERVICE_CONTEXT.value: "服务/风险语境",
    M11CompetitorSelectionRole.NOT_FOR_CORE_SEARCH.value: "不进入核心召回",
}


class Core3SkuBattlefieldCandidateResponse(Core3RealDataBaseModel):
    sku_battlefield_candidate_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    battlefield_code: str = Field(min_length=1)
    battlefield_name_cn: str = Field(min_length=1)
    battlefield_definition_cn: str = Field(min_length=1)
    candidate_source_json: list[str] = Field(default_factory=list)
    candidate_source_count: int = Field(default=0, ge=0)
    source_task_codes_json: list[str] = Field(default_factory=list)
    source_target_group_codes_json: list[str] = Field(default_factory=list)
    source_claim_codes_json: list[str] = Field(default_factory=list)
    source_param_codes_json: list[str] = Field(default_factory=list)
    source_topic_codes_json: list[str] = Field(default_factory=list)
    candidate_initial_score: float = Field(default=0, ge=0, le=1)
    candidate_reason_cn: str
    candidate_status: M11BattlefieldCandidateStatus = M11BattlefieldCandidateStatus.ACTIVE
    candidate_status_label_cn: str | None = None
    missing_signals_json: list[dict[str, Any] | str] = Field(default_factory=list)
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    review_required: bool = False
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_candidate_note(self) -> "Core3SkuBattlefieldCandidateResponse":
        self.candidate_status_label_cn = self.candidate_status_label_cn or _label_cn(
            self.candidate_status,
            M11_BATTLEFIELD_CANDIDATE_STATUS_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or _sku_battlefield_candidate_business_note(self)
        return self


class Core3SkuBattlefieldCandidateListResponse(Core3RealDataBaseModel):
    items: list[Core3SkuBattlefieldCandidateResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3SkuBattlefieldScoreResponse(Core3RealDataBaseModel):
    sku_battlefield_score_id: str = Field(min_length=1)
    sku_battlefield_candidate_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    battlefield_code: str = Field(min_length=1)
    battlefield_name_cn: str = Field(min_length=1)
    battlefield_definition_cn: str = Field(min_length=1)
    semantic_score: float = Field(default=0, ge=0, le=1)
    market_score: float = Field(default=0, ge=0, le=1)
    core_task_score: float = Field(default=0, ge=0, le=1)
    target_group_score: float = Field(default=0, ge=0, le=1)
    core_claim_combo_score: float = Field(default=0, ge=0, le=1)
    core_param_capability_score: float = Field(default=0, ge=0, le=1)
    comment_support_score: float = Field(default=0, ge=0, le=1)
    price_position_fit: float = Field(default=0, ge=0, le=1)
    sales_validation_score: float = Field(default=0, ge=0, le=1)
    sales_amount_validation_score: float = Field(default=0, ge=0, le=1)
    comparable_pool_strength: float = Field(default=0, ge=0, le=1)
    raw_battlefield_score: float = Field(default=0, ge=0, le=1)
    risk_penalty: float = Field(default=0, ge=0, le=1)
    battlefield_score: float = Field(default=0, ge=0, le=1)
    relation_level: M11BattlefieldRelationLevel = M11BattlefieldRelationLevel.INSUFFICIENT
    relation_level_label_cn: str | None = None
    competitor_selection_role: M11CompetitorSelectionRole = M11CompetitorSelectionRole.NOT_FOR_CORE_SEARCH
    competitor_selection_role_label_cn: str | None = None
    competitor_selection_role_cn: str | None = None
    sample_sufficiency: str = "unknown"
    relation_reason_json: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0, ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    evidence_domain_count: int = Field(default=0, ge=0)
    effective_domain_json: dict[str, Any] = Field(default_factory=dict)
    score_breakdown_json: dict[str, Any] = Field(default_factory=dict)
    cap_rule_applied_json: list[dict[str, Any]] = Field(default_factory=list)
    missing_signals_json: list[dict[str, Any] | str] = Field(default_factory=list)
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    business_reason_cn: str
    business_reason_parts_json: dict[str, Any] = Field(default_factory=dict)
    next_module_payload_json: dict[str, Any] = Field(default_factory=dict)
    review_required: bool = False
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_score_note(self) -> "Core3SkuBattlefieldScoreResponse":
        self.relation_level_label_cn = self.relation_level_label_cn or _label_cn(
            self.relation_level,
            M11_BATTLEFIELD_RELATION_LABEL_CN,
        )
        self.competitor_selection_role_label_cn = self.competitor_selection_role_label_cn or _label_cn(
            self.competitor_selection_role,
            M11_COMPETITOR_SELECTION_ROLE_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or _sku_battlefield_score_business_note(self)
        return self


class Core3SkuBattlefieldScoreListResponse(Core3RealDataBaseModel):
    items: list[Core3SkuBattlefieldScoreResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3SkuBattlefieldEvidenceBreakdownResponse(Core3RealDataBaseModel):
    sku_battlefield_evidence_breakdown_id: str = Field(min_length=1)
    sku_battlefield_score_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    battlefield_code: str = Field(min_length=1)
    battlefield_name_cn: str = Field(min_length=1)
    evidence_domain: M11BattlefieldEvidenceDomain
    evidence_domain_label_cn: str | None = None
    support_level: M11BattlefieldSupportLevel = M11BattlefieldSupportLevel.MISSING
    support_level_label_cn: str | None = None
    domain_score: float = Field(default=0, ge=0, le=1)
    domain_weight: float = Field(default=0, ge=0, le=1)
    weighted_score: float = Field(default=0, ge=0, le=1)
    evidence_count: int = Field(default=0, ge=0)
    evidence_ids: list[str] = Field(default_factory=list)
    source_feature_refs_json: list[dict[str, Any]] = Field(default_factory=list)
    domain_reason_cn: str
    domain_risk_json: dict[str, Any] = Field(default_factory=dict)
    review_required: bool = False
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_breakdown_note(self) -> "Core3SkuBattlefieldEvidenceBreakdownResponse":
        self.evidence_domain_label_cn = self.evidence_domain_label_cn or _label_cn(
            self.evidence_domain,
            M11_BATTLEFIELD_EVIDENCE_DOMAIN_LABEL_CN,
        )
        self.support_level_label_cn = self.support_level_label_cn or _label_cn(
            self.support_level,
            M11_BATTLEFIELD_SUPPORT_LEVEL_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or _sku_battlefield_breakdown_business_note(self)
        return self


class Core3SkuBattlefieldEvidenceBreakdownListResponse(Core3RealDataBaseModel):
    items: list[Core3SkuBattlefieldEvidenceBreakdownResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3SkuBattlefieldPortfolioResponse(Core3RealDataBaseModel):
    sku_battlefield_portfolio_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    main_battlefields_json: list[dict[str, Any]] = Field(default_factory=list)
    secondary_battlefields_json: list[dict[str, Any]] = Field(default_factory=list)
    opportunity_battlefields_json: list[dict[str, Any]] = Field(default_factory=list)
    weak_battlefields_json: list[dict[str, Any]] = Field(default_factory=list)
    insufficient_battlefields_json: list[dict[str, Any]] = Field(default_factory=list)
    primary_competitor_search_context_cn: str
    primary_search_battlefield_codes_json: list[str] = Field(default_factory=list)
    secondary_search_battlefield_codes_json: list[str] = Field(default_factory=list)
    opportunity_monitoring_codes_json: list[str] = Field(default_factory=list)
    risk_or_service_context_json: list[dict[str, Any]] = Field(default_factory=list)
    portfolio_confidence: float = Field(default=0, ge=0, le=1)
    portfolio_risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    battlefield_score_refs_json: list[dict[str, Any]] = Field(default_factory=list)
    review_required: bool = False
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_portfolio_note(self) -> "Core3SkuBattlefieldPortfolioResponse":
        self.business_note_cn = self.business_note_cn or self.primary_competitor_search_context_cn
        return self


class Core3SkuBattlefieldPortfolioListResponse(Core3RealDataBaseModel):
    items: list[Core3SkuBattlefieldPortfolioResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3SkuBattlefieldReviewIssueResponse(Core3RealDataBaseModel):
    sku_battlefield_review_issue_id: str = Field(min_length=1)
    sku_battlefield_score_id: str | None = None
    sku_battlefield_candidate_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    battlefield_code: str | None = None
    battlefield_name_cn: str | None = None
    issue_type: str
    issue_severity: str = "warning"
    issue_status: str = "open"
    issue_reason_cn: str
    issue_detail_json: dict[str, Any] = Field(default_factory=dict)
    affected_output_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    suggested_action_cn: str
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_issue_note(self) -> "Core3SkuBattlefieldReviewIssueResponse":
        self.business_note_cn = self.business_note_cn or self.issue_reason_cn
        return self


class Core3SkuBattlefieldReviewIssueListResponse(Core3RealDataBaseModel):
    items: list[Core3SkuBattlefieldReviewIssueResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


M11_5_CLAIM_CANDIDATE_STATUS_LABEL_CN: dict[str, str] = {
    M115ClaimCandidateStatus.ACTIVE.value: "已进入卖点价值分层",
    M115ClaimCandidateStatus.REVIEW_REQUIRED.value: "需复核后使用",
    M115ClaimCandidateStatus.REJECTED.value: "证据不足未采用",
    M115ClaimCandidateStatus.BLOCKED.value: "输入阻塞",
}

M11_5_RELEVANCE_ROLE_LABEL_CN: dict[str, str] = {
    M115BattlefieldRelevanceRole.CORE.value: "战场核心卖点",
    M115BattlefieldRelevanceRole.AUXILIARY.value: "战场辅助卖点",
    M115BattlefieldRelevanceRole.SERVICE.value: "服务保障卖点",
    M115BattlefieldRelevanceRole.RISK.value: "边界风险卖点",
    M115BattlefieldRelevanceRole.NOT_APPLICABLE.value: "不适用于该战场",
}

M11_5_LAYER_LABEL_CN: dict[str, str] = {
    M115ClaimValueLayer.BASIC_THRESHOLD.value: "基础门槛",
    M115ClaimValueLayer.COMPETITIVE_PERFORMANCE.value: "竞争绩效",
    M115ClaimValueLayer.PREMIUM_TENDENCY.value: "溢价倾向",
    M115ClaimValueLayer.WEAK_PERCEPTION.value: "弱感知",
    M115ClaimValueLayer.INSUFFICIENT_SAMPLE.value: "样本不足",
    M115ClaimValueLayer.NOT_APPLICABLE.value: "不适用",
    M115ClaimValueLayer.BLOCKED.value: "输入阻塞",
}

M11_5_SAMPLE_SUFFICIENCY_LABEL_CN: dict[str, str] = {
    M115SampleSufficiency.SUFFICIENT.value: "样本充分",
    M115SampleSufficiency.LIMITED.value: "样本有限",
    M115SampleSufficiency.INSUFFICIENT.value: "样本不足",
    M115SampleSufficiency.UNKNOWN.value: "样本未知",
}

M11_5_EVIDENCE_DOMAIN_LABEL_CN: dict[str, str] = {
    M115ClaimValueEvidenceDomain.ACTIVATION.value: "卖点激活",
    M115ClaimValueEvidenceDomain.PARAM.value: "参数支撑",
    M115ClaimValueEvidenceDomain.PROMO.value: "宣传支撑",
    M115ClaimValueEvidenceDomain.COMMENT.value: "评论感知",
    M115ClaimValueEvidenceDomain.PRICE.value: "价格表现",
    M115ClaimValueEvidenceDomain.SALES.value: "销量表现",
    M115ClaimValueEvidenceDomain.POOL.value: "可比池样本",
    M115ClaimValueEvidenceDomain.MARKET.value: "市场画像",
    M115ClaimValueEvidenceDomain.SERVICE.value: "服务边界",
    M115ClaimValueEvidenceDomain.RISK.value: "待复核点",
    M115ClaimValueEvidenceDomain.SEED.value: "卖点本体",
    M115ClaimValueEvidenceDomain.PROFILE.value: "画像可信度",
}

M11_5_SUPPORT_LEVEL_LABEL_CN: dict[str, str] = {
    M115ClaimValueSupportLevel.STRONG.value: "强支撑",
    M115ClaimValueSupportLevel.MEDIUM.value: "中等支撑",
    M115ClaimValueSupportLevel.WEAK.value: "弱支撑",
    M115ClaimValueSupportLevel.MISSING.value: "缺少证据",
    M115ClaimValueSupportLevel.CONFLICT.value: "存在冲突",
    M115ClaimValueSupportLevel.NOT_APPLICABLE.value: "不适用",
}


class Core3SkuBattlefieldClaimCandidateResponse(Core3RealDataBaseModel):
    sku_battlefield_claim_candidate_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    battlefield_code: str = Field(min_length=1)
    battlefield_name_cn: str = Field(min_length=1)
    battlefield_relation_level: str
    claim_code: str = Field(min_length=1)
    claim_name_cn: str = Field(min_length=1)
    claim_group: str | None = None
    candidate_source_json: list[str] = Field(default_factory=list)
    candidate_source_count: int = Field(default=0, ge=0)
    candidate_initial_score: float = Field(default=0, ge=0, le=1)
    candidate_reason_cn: str
    candidate_status: M115ClaimCandidateStatus = M115ClaimCandidateStatus.ACTIVE
    candidate_status_label_cn: str | None = None
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    review_required: bool = False
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_candidate_note(self) -> "Core3SkuBattlefieldClaimCandidateResponse":
        self.candidate_status_label_cn = self.candidate_status_label_cn or _label_cn(
            self.candidate_status,
            M11_5_CLAIM_CANDIDATE_STATUS_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or _sku_claim_value_candidate_business_note(self)
        return self


class Core3SkuBattlefieldClaimCandidateListResponse(Core3RealDataBaseModel):
    items: list[Core3SkuBattlefieldClaimCandidateResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3SkuClaimValueLayerResponse(Core3RealDataBaseModel):
    sku_claim_value_layer_id: str = Field(min_length=1)
    sku_battlefield_claim_candidate_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    battlefield_code: str = Field(min_length=1)
    battlefield_name_cn: str = Field(min_length=1)
    battlefield_relation_level: str
    claim_code: str = Field(min_length=1)
    claim_name_cn: str = Field(min_length=1)
    claim_group: str | None = None
    claim_activation_score: float = Field(default=0, ge=0, le=1)
    activation_basis_json: dict[str, Any] = Field(default_factory=dict)
    battlefield_relevance_role: M115BattlefieldRelevanceRole = M115BattlefieldRelevanceRole.NOT_APPLICABLE
    battlefield_relevance_role_label_cn: str | None = None
    comparable_pool_id: str | None = None
    pool_type: str | None = None
    pool_sku_count: int = Field(default=0, ge=0)
    with_claim_count: int = Field(default=0, ge=0)
    without_claim_count: int = Field(default=0, ge=0)
    coverage_rate: float | None = None
    psi: float | None = None
    ssi: float | None = None
    sai: float | None = None
    cpi: float | None = None
    price_support_score: float = Field(default=0, ge=0, le=1)
    sales_support_score: float = Field(default=0, ge=0, le=1)
    comment_perception_score: float = Field(default=0, ge=0, le=1)
    risk_penalty: float = Field(default=0, ge=0, le=1)
    claim_value_score: float = Field(default=0, ge=0, le=1)
    layer: M115ClaimValueLayer = M115ClaimValueLayer.INSUFFICIENT_SAMPLE
    layer_label_cn: str | None = None
    layer_reason_json: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0, ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    sample_sufficiency: M115SampleSufficiency = M115SampleSufficiency.UNKNOWN
    sample_sufficiency_label_cn: str | None = None
    sample_sufficiency_json: dict[str, Any] = Field(default_factory=dict)
    missing_signals_json: list[dict[str, Any] | str] = Field(default_factory=list)
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    business_reason_cn: str
    business_reason_parts_json: dict[str, Any] = Field(default_factory=dict)
    next_module_payload_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    review_required: bool = False
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_layer_note(self) -> "Core3SkuClaimValueLayerResponse":
        self.battlefield_relevance_role_label_cn = self.battlefield_relevance_role_label_cn or _label_cn(
            self.battlefield_relevance_role,
            M11_5_RELEVANCE_ROLE_LABEL_CN,
        )
        self.layer_label_cn = self.layer_label_cn or _label_cn(self.layer, M11_5_LAYER_LABEL_CN)
        self.sample_sufficiency_label_cn = self.sample_sufficiency_label_cn or _label_cn(
            self.sample_sufficiency,
            M11_5_SAMPLE_SUFFICIENCY_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or _sku_claim_value_layer_business_note(self)
        return self


class Core3SkuClaimValueLayerListResponse(Core3RealDataBaseModel):
    items: list[Core3SkuClaimValueLayerResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3SkuClaimValueEvidenceBreakdownResponse(Core3RealDataBaseModel):
    sku_claim_value_evidence_breakdown_id: str = Field(min_length=1)
    sku_claim_value_layer_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    battlefield_code: str = Field(min_length=1)
    battlefield_name_cn: str = Field(min_length=1)
    claim_code: str = Field(min_length=1)
    claim_name_cn: str = Field(min_length=1)
    evidence_domain: M115ClaimValueEvidenceDomain
    evidence_domain_label_cn: str | None = None
    support_level: M115ClaimValueSupportLevel = M115ClaimValueSupportLevel.MISSING
    support_level_label_cn: str | None = None
    support_score: float = Field(default=0, ge=0, le=1)
    domain_weight: float = Field(default=0, ge=0, le=1)
    weighted_contribution: float = Field(default=0, ge=0, le=1)
    support_summary_cn: str
    source_signal_codes_json: list[str] = Field(default_factory=list)
    source_values_json: dict[str, Any] = Field(default_factory=dict)
    representative_evidence_ids: list[str] = Field(default_factory=list)
    missing_reason_code: str | None = None
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_breakdown_note(self) -> "Core3SkuClaimValueEvidenceBreakdownResponse":
        self.evidence_domain_label_cn = self.evidence_domain_label_cn or _label_cn(
            self.evidence_domain,
            M11_5_EVIDENCE_DOMAIN_LABEL_CN,
        )
        self.support_level_label_cn = self.support_level_label_cn or _label_cn(
            self.support_level,
            M11_5_SUPPORT_LEVEL_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or _sku_claim_value_breakdown_business_note(self)
        return self


class Core3SkuClaimValueEvidenceBreakdownListResponse(Core3RealDataBaseModel):
    items: list[Core3SkuClaimValueEvidenceBreakdownResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3SkuBattlefieldClaimValueSummaryResponse(Core3RealDataBaseModel):
    sku_battlefield_claim_value_summary_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    battlefield_code: str = Field(min_length=1)
    battlefield_name_cn: str = Field(min_length=1)
    battlefield_relation_level: str
    premium_claims_json: list[dict[str, Any]] = Field(default_factory=list)
    performance_claims_json: list[dict[str, Any]] = Field(default_factory=list)
    threshold_claims_json: list[dict[str, Any]] = Field(default_factory=list)
    weak_claims_json: list[dict[str, Any]] = Field(default_factory=list)
    insufficient_claims_json: list[dict[str, Any]] = Field(default_factory=list)
    not_applicable_claims_json: list[dict[str, Any]] = Field(default_factory=list)
    claim_value_profile_cn: str
    comparison_focus_claims_json: list[dict[str, Any]] = Field(default_factory=list)
    summary_confidence: float = Field(default=0, ge=0, le=1)
    summary_risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    claim_value_layer_refs_json: list[dict[str, Any]] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    review_required: bool = False
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_summary_note(self) -> "Core3SkuBattlefieldClaimValueSummaryResponse":
        self.business_note_cn = self.business_note_cn or self.claim_value_profile_cn
        return self


class Core3SkuBattlefieldClaimValueSummaryListResponse(Core3RealDataBaseModel):
    items: list[Core3SkuBattlefieldClaimValueSummaryResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3SkuClaimValueReviewIssueResponse(Core3RealDataBaseModel):
    sku_claim_value_review_issue_id: str = Field(min_length=1)
    related_layer_id: str | None = None
    related_candidate_id: str | None = None
    related_battlefield_score_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    battlefield_code: str | None = None
    battlefield_name_cn: str | None = None
    claim_code: str | None = None
    claim_name_cn: str | None = None
    issue_type: str
    issue_level: str = "warning"
    issue_message_cn: str
    issue_context_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    resolved_status: str = "open"
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_issue_note(self) -> "Core3SkuClaimValueReviewIssueResponse":
        self.business_note_cn = self.business_note_cn or self.issue_message_cn
        return self


class Core3SkuClaimValueReviewIssueListResponse(Core3RealDataBaseModel):
    items: list[Core3SkuClaimValueReviewIssueResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


M11_6_DIMENSION_TYPE_LABEL_CN: dict[str, str] = {
    "claim": "卖点价值",
    "task": "用户任务",
    "target_group": "目标客群",
    "battlefield": "价值战场",
}


class Core3SkuBusinessProfileResponse(Core3RealDataBaseModel):
    sku_business_profile_id: str = Field(min_length=1)
    sku_signal_profile_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    model_code: str | None = None
    model_name: str | None = None
    brand_name: str | None = None
    series_name: str | None = None
    screen_size_inch: float | None = None
    size_segment: str = "unknown"
    price_band: str = "unknown"
    main_platform: str | None = None
    sales_volume_total: float | None = None
    sales_amount_total: float | None = None
    price_wavg: float | None = None
    price_latest: float | None = None
    price_percentile_in_pool: float | None = None
    sales_percentile_in_pool: float | None = None
    amount_percentile_in_pool: float | None = None
    price_gap_to_pool_median: float | None = None
    market_sample_status: str = "unknown"
    market_source: str = "M08"
    primary_task_code: str | None = None
    primary_task_name: str | None = None
    primary_task_score: float = Field(default=0, ge=0, le=1)
    primary_task_evidence_level: str = "unknown"
    primary_task_confidence: float = Field(default=0, ge=0, le=1)
    primary_target_group_code: str | None = None
    primary_target_group_name: str | None = None
    primary_target_group_score: float = Field(default=0, ge=0, le=1)
    primary_target_group_evidence_level: str = "unknown"
    primary_target_group_confidence: float = Field(default=0, ge=0, le=1)
    primary_battlefield_code: str | None = None
    primary_battlefield_name: str | None = None
    primary_battlefield_score: float = Field(default=0, ge=0, le=1)
    primary_battlefield_evidence_level: str = "unknown"
    primary_battlefield_confidence: float = Field(default=0, ge=0, le=1)
    secondary_tasks_json: list[dict[str, Any]] = Field(default_factory=list)
    secondary_target_groups_json: list[dict[str, Any]] = Field(default_factory=list)
    secondary_battlefields_json: list[dict[str, Any]] = Field(default_factory=list)
    core_claims_json: list[dict[str, Any]] = Field(default_factory=list)
    claim_value_summary_json: dict[str, Any] = Field(default_factory=dict)
    claim_value_strength: float = Field(default=0, ge=0, le=1)
    premium_position: str = "unknown"
    premium_type: str = "unknown"
    premium_support_level: str = "unknown"
    premium_score: float = Field(default=0, ge=0, le=1)
    premium_reason_cn: str
    premium_risk_json: list[dict[str, Any] | str] = Field(default_factory=list)
    market_role: str = "unknown"
    market_role_reason_cn: str
    competitive_role_hints_json: list[dict[str, Any]] = Field(default_factory=list)
    candidate_recall_priority_json: dict[str, Any] = Field(default_factory=dict)
    same_brand_competition_policy: str = "allow"
    sales_allocation_summary_json: dict[str, Any] = Field(default_factory=dict)
    evidence_strength: str = "unknown"
    confidence: float = Field(default=0, ge=0, le=1)
    confidence_level: str = "unknown"
    missing_signals_json: list[dict[str, Any] | str] = Field(default_factory=list)
    risk_signals_json: list[dict[str, Any] | str] = Field(default_factory=list)
    representative_evidence_ids: list[str] = Field(default_factory=list)
    business_summary_cn: str
    rule_version: str = CORE3_M11_6_RULE_VERSION
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_business_profile_note(self) -> "Core3SkuBusinessProfileResponse":
        self.business_note_cn = self.business_note_cn or _sku_business_profile_note(self)
        return self


class Core3SkuBusinessProfileListResponse(Core3RealDataBaseModel):
    items: list[Core3SkuBusinessProfileResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3SkuBusinessProfileDimensionResponse(Core3RealDataBaseModel):
    profile_dimension_id: str = Field(min_length=1)
    sku_business_profile_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    dimension_type: str = Field(min_length=1)
    dimension_type_label_cn: str | None = None
    dimension_code: str = Field(min_length=1)
    dimension_name: str = Field(min_length=1)
    dimension_rank: int = Field(default=0, ge=0)
    dimension_score: float = Field(default=0, ge=0, le=1)
    normalized_weight: float = Field(default=0, ge=0, le=1)
    evidence_level: str = "unknown"
    relation_level: str = "unknown"
    value_layer: str | None = None
    source_module: str = Field(min_length=1)
    source_record_refs_json: list[dict[str, Any]] = Field(default_factory=list)
    support_breakdown_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)
    business_reason_cn: str
    rule_version: str = CORE3_M11_6_RULE_VERSION
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_dimension_note(self) -> "Core3SkuBusinessProfileDimensionResponse":
        self.dimension_type_label_cn = self.dimension_type_label_cn or M11_6_DIMENSION_TYPE_LABEL_CN.get(
            self.dimension_type,
            self.dimension_type,
        )
        self.business_note_cn = self.business_note_cn or (
            f"{self.dimension_type_label_cn}“{self.dimension_name}”权重 {self.normalized_weight:.2f}，"
            f"分数 {self.dimension_score:.2f}；{self.business_reason_cn}"
        )
        return self


class Core3SkuBusinessProfileDimensionListResponse(Core3RealDataBaseModel):
    items: list[Core3SkuBusinessProfileDimensionResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3SkuBusinessProfileSalesAllocationResponse(Core3RealDataBaseModel):
    sales_allocation_id: str = Field(min_length=1)
    sku_business_profile_id: str | None = None
    profile_dimension_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    dimension_type: str = Field(min_length=1)
    dimension_type_label_cn: str | None = None
    dimension_code: str = Field(min_length=1)
    dimension_name: str = Field(min_length=1)
    allocation_method: str = "score_normalized_with_market_volume"
    allocation_weight: float = Field(default=0, ge=0, le=1)
    allocated_sales_volume: float | None = None
    allocated_sales_amount: float | None = None
    allocation_confidence: float = Field(default=0, ge=0, le=1)
    allocation_basis_json: dict[str, Any] = Field(default_factory=dict)
    rule_version: str = CORE3_M11_6_RULE_VERSION
    is_current: bool = True
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_allocation_note(self) -> "Core3SkuBusinessProfileSalesAllocationResponse":
        self.dimension_type_label_cn = self.dimension_type_label_cn or M11_6_DIMENSION_TYPE_LABEL_CN.get(
            self.dimension_type,
            self.dimension_type,
        )
        volume = "销量未知" if self.allocated_sales_volume is None else f"估算销量 {self.allocated_sales_volume:.2f}"
        amount = "销额未知" if self.allocated_sales_amount is None else f"估算销额 {self.allocated_sales_amount:.2f}"
        self.business_note_cn = self.business_note_cn or (
            f"{self.dimension_type_label_cn}“{self.dimension_name}”承担 {self.allocation_weight:.2%} 的 SKU 权重，"
            f"{volume}，{amount}。"
        )
        return self


class Core3SkuBusinessProfileSalesAllocationListResponse(Core3RealDataBaseModel):
    items: list[Core3SkuBusinessProfileSalesAllocationResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3SkuBusinessProfileReviewIssueResponse(Core3RealDataBaseModel):
    sku_business_profile_review_issue_id: str = Field(min_length=1)
    sku_business_profile_id: str | None = None
    profile_dimension_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    sku_code: str = Field(min_length=1)
    dimension_type: str = ""
    dimension_code: str = ""
    issue_type: str
    issue_level: str = "warning"
    issue_message_cn: str
    suggested_action_cn: str
    issue_context_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    rule_version: str = CORE3_M11_6_RULE_VERSION
    resolved_status: str = "open"
    processing_status: str = "warning"
    review_required: bool = True
    review_status: str = "review_required"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_issue_note(self) -> "Core3SkuBusinessProfileReviewIssueResponse":
        self.business_note_cn = self.business_note_cn or self.issue_message_cn
        return self


class Core3SkuBusinessProfileReviewIssueListResponse(Core3RealDataBaseModel):
    items: list[Core3SkuBusinessProfileReviewIssueResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3BusinessDimensionSalesSummaryResponse(Core3RealDataBaseModel):
    dimension_sales_summary_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    source_m11_6_module_run_id: str | None = None
    dimension_type: str = Field(min_length=1)
    dimension_type_label_cn: str | None = None
    dimension_code: str = Field(min_length=1)
    dimension_name: str = Field(min_length=1)
    standard_dimension_rank: int = Field(default=0, ge=0)
    sku_count: int = Field(default=0, ge=0)
    primary_sku_count: int = Field(default=0, ge=0)
    estimated_sales_volume: float = 0
    estimated_sales_amount: float = 0
    total_market_sales_volume: float = 0
    total_market_sales_amount: float = 0
    sales_volume_share: float = Field(default=0, ge=0, le=1)
    sales_amount_share: float = Field(default=0, ge=0, le=1)
    avg_allocation_confidence: float = Field(default=0, ge=0, le=1)
    evidence_quality_summary_json: dict[str, Any] = Field(default_factory=dict)
    top_sku_contribution_json: list[dict[str, Any]] = Field(default_factory=list)
    reconciliation_status: str = "matched"
    business_summary_cn: str
    rule_version: str = CORE3_M11_7_RULE_VERSION
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_summary_note(self) -> "Core3BusinessDimensionSalesSummaryResponse":
        self.dimension_type_label_cn = self.dimension_type_label_cn or M11_6_DIMENSION_TYPE_LABEL_CN.get(
            self.dimension_type,
            self.dimension_type,
        )
        self.business_note_cn = self.business_note_cn or (
            f"{self.dimension_type_label_cn}“{self.dimension_name}”由 {self.sku_count} 个 SKU 贡献，"
            f"估算销量 {self.estimated_sales_volume:.2f}，占全量 {self.sales_volume_share:.2%}；"
            f"对账状态：{'通过' if self.reconciliation_status == 'matched' else '需复核'}。"
        )
        return self


class Core3BusinessDimensionSalesSummaryListResponse(Core3RealDataBaseModel):
    items: list[Core3BusinessDimensionSalesSummaryResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3BusinessDimensionSkuContributionResponse(Core3RealDataBaseModel):
    dimension_sku_contribution_id: str = Field(min_length=1)
    dimension_sales_summary_id: str | None = None
    sku_business_profile_id: str | None = None
    sales_allocation_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    dimension_type: str = Field(min_length=1)
    dimension_type_label_cn: str | None = None
    dimension_code: str = Field(min_length=1)
    dimension_name: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    brand_name: str | None = None
    model_name: str | None = None
    allocation_weight: float = Field(default=0, ge=0, le=1)
    allocated_sales_volume: float = 0
    allocated_sales_amount: float = 0
    sku_share_in_dimension_volume: float = Field(default=0, ge=0, le=1)
    sku_share_in_dimension_amount: float = Field(default=0, ge=0, le=1)
    is_primary_dimension: bool = False
    allocation_confidence: float = Field(default=0, ge=0, le=1)
    evidence_level: str = "unknown"
    contribution_reason_cn: str
    evidence_ids: list[str] = Field(default_factory=list)
    rule_version: str = CORE3_M11_7_RULE_VERSION
    processing_status: str = "success"
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_contribution_note(self) -> "Core3BusinessDimensionSkuContributionResponse":
        self.dimension_type_label_cn = self.dimension_type_label_cn or M11_6_DIMENSION_TYPE_LABEL_CN.get(
            self.dimension_type,
            self.dimension_type,
        )
        self.business_note_cn = self.business_note_cn or (
            f"{self.model_name or self.sku_code} 对“{self.dimension_name}”贡献估算销量 "
            f"{self.allocated_sales_volume:.2f}，占该维度 {self.sku_share_in_dimension_volume:.2%}。"
        )
        return self


class Core3BusinessDimensionSkuContributionListResponse(Core3RealDataBaseModel):
    items: list[Core3BusinessDimensionSkuContributionResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3BusinessSalesReconciliationCheckResponse(Core3RealDataBaseModel):
    reconciliation_check_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    source_m11_6_module_run_id: str | None = None
    check_type: str = Field(min_length=1)
    sku_code: str = ""
    dimension_type: str = ""
    dimension_code: str = ""
    expected_value: float = 0
    actual_value: float = 0
    gap_value: float = 0
    gap_ratio: float = 0
    tolerance_value: float = 0
    status: str = "passed"
    failure_reason_code: str = ""
    failure_reason_cn: str = ""
    check_payload_json: dict[str, Any] = Field(default_factory=dict)
    rule_version: str = CORE3_M11_7_RULE_VERSION
    processing_status: str = "success"
    review_required: bool = False
    review_status: str = "auto_pass"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_check_note(self) -> "Core3BusinessSalesReconciliationCheckResponse":
        self.business_note_cn = self.business_note_cn or (
            "对账通过"
            if self.status == "passed"
            else f"对账未通过：{self.failure_reason_cn or self.failure_reason_code}，差异 {self.gap_value:.4f}。"
        )
        return self


class Core3BusinessSalesReconciliationCheckListResponse(Core3RealDataBaseModel):
    items: list[Core3BusinessSalesReconciliationCheckResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3BusinessSalesReconciliationIssueResponse(Core3RealDataBaseModel):
    reconciliation_issue_id: str = Field(min_length=1)
    reconciliation_check_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    module_run_id: str | None = None
    issue_scope: str = "global"
    sku_code: str = ""
    dimension_type: str = ""
    dimension_code: str = ""
    issue_code: str
    severity: str = "warning"
    issue_message_cn: str
    suggested_action_cn: str
    issue_context_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    rule_version: str = CORE3_M11_7_RULE_VERSION
    resolved_status: str = "open"
    processing_status: str = "warning"
    review_required: bool = True
    review_status: str = "review_required"
    review_reason_json: dict[str, Any] = Field(default_factory=dict)
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_reconciliation_issue_note(self) -> "Core3BusinessSalesReconciliationIssueResponse":
        self.business_note_cn = self.business_note_cn or self.issue_message_cn
        return self


class Core3BusinessSalesReconciliationIssueListResponse(Core3RealDataBaseModel):
    items: list[Core3BusinessSalesReconciliationIssueResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


M12_RECALL_SOURCE_LABEL_CN: dict[str, str] = {
    M12RecallSource.COMPARABLE_POOL.value: "可比池",
    M12RecallSource.BATTLEFIELD.value: "价值战场",
    M12RecallSource.TASK.value: "用户任务",
    M12RecallSource.AUDIENCE.value: "目标客群",
    M12RecallSource.CLAIM_VALUE.value: "战场内卖点价值",
    M12RecallSource.MARKET_PRESSURE.value: "市场压力",
    M12RecallSource.SCENARIO_SERVICE.value: "服务/场景参照",
}

M12_RELATION_TYPE_LABEL_CN: dict[str, str] = {
    M12RelationType.DIRECT_FIGHT.value: "正面对打",
    M12RelationType.PRICE_VOLUME_PRESSURE.value: "价格销量压力",
    M12RelationType.CONFIGURATION_PRESSURE.value: "配置压力",
    M12RelationType.PREMIUM_BENCHMARK.value: "高端标杆",
    M12RelationType.POTENTIAL_DOWNWARD_PRESSURE.value: "下探拦截",
    M12RelationType.UPGRADE_SUBSTITUTE.value: "升级替代",
    M12RelationType.DOWNGRADE_SUBSTITUTE.value: "降级替代",
    M12RelationType.SCENARIO_SUBSTITUTE.value: "场景替代",
    M12RelationType.SERVICE_REFERENCE.value: "服务参照",
}

M12_RECALL_STRENGTH_LABEL_CN: dict[str, str] = {
    M12RecallStrength.STRONG.value: "强召回",
    M12RecallStrength.MEDIUM.value: "中等召回",
    M12RecallStrength.WEAK.value: "弱召回",
    M12RecallStrength.REVIEW_ONLY.value: "仅复核",
}

M12_PRICE_RELATION_LABEL_CN: dict[str, str] = {
    M12PriceRelation.LOWER.value: "候选更低价",
    M12PriceRelation.SIMILAR.value: "价格接近",
    M12PriceRelation.HIGHER.value: "候选更高价",
    M12PriceRelation.UNKNOWN.value: "价格待识别",
}

M12_SIZE_RELATION_LABEL_CN: dict[str, str] = {
    M12SizeRelation.SAME.value: "同尺寸",
    M12SizeRelation.ADJACENT_LARGER.value: "邻近更大尺寸",
    M12SizeRelation.ADJACENT_SMALLER.value: "邻近更小尺寸",
    M12SizeRelation.LARGER_CROSS.value: "跨段更大尺寸",
    M12SizeRelation.SMALLER_CROSS.value: "跨段更小尺寸",
    M12SizeRelation.UNKNOWN.value: "尺寸待识别",
}

M12_SAMPLE_STATUS_LABEL_CN: dict[str, str] = {
    M12SampleStatus.SUFFICIENT.value: "样本充分",
    M12SampleStatus.LIMITED.value: "样本有限",
    M12SampleStatus.INSUFFICIENT.value: "样本不足",
    M12SampleStatus.UNKNOWN.value: "样本未知",
}

M12_SUPPORT_LEVEL_LABEL_CN: dict[str, str] = {
    M12SupportLevel.STRONG.value: "强支撑",
    M12SupportLevel.MEDIUM.value: "中等支撑",
    M12SupportLevel.WEAK.value: "弱支撑",
    M12SupportLevel.MISSING.value: "缺少证据",
    M12SupportLevel.CONFLICT.value: "存在冲突",
    M12SupportLevel.NOT_APPLICABLE.value: "不适用",
}

M12_RECALL_STATUS_LABEL_CN: dict[str, str] = {
    M12RecallStatus.SUCCESS.value: "已完成",
    M12RecallStatus.LIMITED.value: "有限完成",
    M12RecallStatus.REVIEW_REQUIRED.value: "需复核",
    M12RecallStatus.BLOCKED.value: "输入阻塞",
    M12RecallStatus.FAILED.value: "运行失败",
}


class Core3CandidateRecallRunResponse(Core3RealDataBaseModel):
    candidate_recall_run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    run_id: str | None = None
    run_key: str = Field(min_length=1)
    target_sku_count: int = Field(default=0, ge=0)
    candidate_pair_count: int = Field(default=0, ge=0)
    reason_count: int = Field(default=0, ge=0)
    feature_snapshot_count: int = Field(default=0, ge=0)
    review_issue_count: int = Field(default=0, ge=0)
    strong_pair_count: int = Field(default=0, ge=0)
    medium_pair_count: int = Field(default=0, ge=0)
    weak_pair_count: int = Field(default=0, ge=0)
    review_only_pair_count: int = Field(default=0, ge=0)
    recall_status: M12RecallStatus = M12RecallStatus.SUCCESS
    recall_status_label_cn: str | None = None
    target_scope_json: list[str] = Field(default_factory=list)
    source_module_versions_json: dict[str, Any] = Field(default_factory=dict)
    summary_json: dict[str, Any] = Field(default_factory=dict)
    warning_json: list[str] = Field(default_factory=list)
    boundary_note_cn: str
    review_required: bool = False
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_run_note(self) -> "Core3CandidateRecallRunResponse":
        self.recall_status_label_cn = self.recall_status_label_cn or _label_cn(
            self.recall_status,
            M12_RECALL_STATUS_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or (
            f"M12 已为 {self.target_sku_count} 个目标 SKU 生成 {self.candidate_pair_count} 个候选 pair，"
            f"保留 {self.reason_count} 条入池理由和 {self.feature_snapshot_count} 条评分快照；该层不输出最终三竞品。"
        )
        return self


class Core3CandidateRecallRunListResponse(Core3RealDataBaseModel):
    items: list[Core3CandidateRecallRunResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3CandidatePoolResponse(Core3RealDataBaseModel):
    candidate_pool_id: str = Field(min_length=1)
    candidate_recall_run_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    target_model_name: str | None = None
    target_brand_name: str | None = None
    candidate_sku_code: str = Field(min_length=1)
    candidate_model_name: str | None = None
    candidate_brand_name: str | None = None
    same_brand_flag: bool = False
    primary_relation_type: M12RelationType = M12RelationType.SCENARIO_SUBSTITUTE
    primary_relation_label_cn: str | None = None
    relation_types_json: list[str] = Field(default_factory=list)
    relation_type_labels_cn: list[str] = Field(default_factory=list)
    recall_sources_json: list[str] = Field(default_factory=list)
    recall_source_labels_cn: list[str] = Field(default_factory=list)
    source_count: int = Field(default=0, ge=0)
    recall_strength: M12RecallStrength = M12RecallStrength.WEAK
    recall_strength_label_cn: str | None = None
    recall_priority_score: float = Field(default=0, ge=0, le=1)
    evidence_quality_score: float = Field(default=0, ge=0, le=1)
    price_relation: M12PriceRelation = M12PriceRelation.UNKNOWN
    price_relation_label_cn: str | None = None
    size_relation: M12SizeRelation = M12SizeRelation.UNKNOWN
    size_relation_label_cn: str | None = None
    sample_status: M12SampleStatus = M12SampleStatus.UNKNOWN
    sample_status_label_cn: str | None = None
    role_hints_json: list[dict[str, Any]] = Field(default_factory=list)
    business_reason_cn: str
    score_parts_json: dict[str, Any] = Field(default_factory=dict)
    missing_signals_json: list[dict[str, Any] | str] = Field(default_factory=list)
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    target_profile_hash: str | None = None
    candidate_profile_hash: str | None = None
    feature_snapshot_hash: str | None = None
    review_required: bool = False
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_pool_note(self) -> "Core3CandidatePoolResponse":
        self.primary_relation_label_cn = self.primary_relation_label_cn or _label_cn(
            self.primary_relation_type,
            M12_RELATION_TYPE_LABEL_CN,
        )
        self.relation_type_labels_cn = self.relation_type_labels_cn or [
            _label_cn(item, M12_RELATION_TYPE_LABEL_CN) for item in self.relation_types_json
        ]
        self.recall_source_labels_cn = self.recall_source_labels_cn or [
            _label_cn(item, M12_RECALL_SOURCE_LABEL_CN) for item in self.recall_sources_json
        ]
        self.recall_strength_label_cn = self.recall_strength_label_cn or _label_cn(
            self.recall_strength,
            M12_RECALL_STRENGTH_LABEL_CN,
        )
        self.price_relation_label_cn = self.price_relation_label_cn or _label_cn(
            self.price_relation,
            M12_PRICE_RELATION_LABEL_CN,
        )
        self.size_relation_label_cn = self.size_relation_label_cn or _label_cn(
            self.size_relation,
            M12_SIZE_RELATION_LABEL_CN,
        )
        self.sample_status_label_cn = self.sample_status_label_cn or _label_cn(
            self.sample_status,
            M12_SAMPLE_STATUS_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or _candidate_pool_business_note(self)
        return self


class Core3CandidatePoolListResponse(Core3RealDataBaseModel):
    items: list[Core3CandidatePoolResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3CandidateRecallReasonResponse(Core3RealDataBaseModel):
    candidate_recall_reason_id: str = Field(min_length=1)
    candidate_pool_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    candidate_sku_code: str = Field(min_length=1)
    recall_source: M12RecallSource
    recall_source_label_cn: str | None = None
    relation_type: M12RelationType
    relation_type_label_cn: str | None = None
    reason_code: str
    support_level: M12SupportLevel = M12SupportLevel.WEAK
    support_level_label_cn: str | None = None
    support_score: float = Field(default=0, ge=0, le=1)
    confidence: float = Field(default=0, ge=0, le=1)
    reason_summary_cn: str
    source_payload_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_reason_note(self) -> "Core3CandidateRecallReasonResponse":
        self.recall_source_label_cn = self.recall_source_label_cn or _label_cn(
            self.recall_source,
            M12_RECALL_SOURCE_LABEL_CN,
        )
        self.relation_type_label_cn = self.relation_type_label_cn or _label_cn(
            self.relation_type,
            M12_RELATION_TYPE_LABEL_CN,
        )
        self.support_level_label_cn = self.support_level_label_cn or _label_cn(
            self.support_level,
            M12_SUPPORT_LEVEL_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or (
            f"{self.recall_source_label_cn}支撑{self.relation_type_label_cn}，支撑分 {self.support_score:.2f}，"
            f"置信度 {self.confidence:.2f}。"
        )
        return self


class Core3CandidateRecallReasonListResponse(Core3RealDataBaseModel):
    items: list[Core3CandidateRecallReasonResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3CandidateFeatureSnapshotResponse(Core3RealDataBaseModel):
    candidate_feature_snapshot_id: str = Field(min_length=1)
    candidate_pool_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    candidate_sku_code: str = Field(min_length=1)
    size_feature_json: dict[str, Any] = Field(default_factory=dict)
    price_feature_json: dict[str, Any] = Field(default_factory=dict)
    channel_feature_json: dict[str, Any] = Field(default_factory=dict)
    market_feature_json: dict[str, Any] = Field(default_factory=dict)
    param_feature_json: dict[str, Any] = Field(default_factory=dict)
    battlefield_overlap_json: dict[str, Any] = Field(default_factory=dict)
    task_overlap_json: dict[str, Any] = Field(default_factory=dict)
    audience_overlap_json: dict[str, Any] = Field(default_factory=dict)
    claim_value_overlap_json: dict[str, Any] = Field(default_factory=dict)
    quality_feature_json: dict[str, Any] = Field(default_factory=dict)
    m13_component_input_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    feature_snapshot_hash: str = Field(min_length=1)
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_snapshot_note(self) -> "Core3CandidateFeatureSnapshotResponse":
        self.business_note_cn = self.business_note_cn or (
            "该快照固定了 M13 评分所需的价格、渠道、参数、任务、客群、战场、卖点价值和质量特征；"
            "M13 默认消费本快照，不回读原始表重建候选。"
        )
        return self


class Core3CandidateFeatureSnapshotListResponse(Core3RealDataBaseModel):
    items: list[Core3CandidateFeatureSnapshotResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3CandidateRecallReviewIssueResponse(Core3RealDataBaseModel):
    candidate_recall_review_issue_id: str = Field(min_length=1)
    candidate_pool_id: str | None = None
    candidate_feature_snapshot_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    candidate_sku_code: str | None = None
    issue_type: str
    issue_level: str = "warning"
    issue_message_cn: str
    suggested_action_cn: str
    issue_context_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    resolved_status: str = "open"
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_issue_note(self) -> "Core3CandidateRecallReviewIssueResponse":
        self.business_note_cn = self.business_note_cn or self.issue_message_cn
        return self


class Core3CandidateRecallReviewIssueListResponse(Core3RealDataBaseModel):
    items: list[Core3CandidateRecallReviewIssueResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


M13_COMPONENT_LABEL_CN: dict[str, str] = {
    M13ComponentCode.BASE_COMPARABILITY.value: "同场可比基础",
    M13ComponentCode.BATTLEFIELD_FIT.value: "价值战场重合",
    M13ComponentCode.TASK_OVERLAP.value: "用户任务重合",
    M13ComponentCode.AUDIENCE_OVERLAP.value: "目标客群重合",
    M13ComponentCode.PRICE_POSITION.value: "价位接近度",
    M13ComponentCode.PRICE_ADVANTAGE.value: "价格拦截力度",
    M13ComponentCode.SIZE_FIT.value: "尺寸形态匹配",
    M13ComponentCode.CHANNEL_OVERLAP.value: "渠道平台重合",
    M13ComponentCode.PARAM_SIMILARITY.value: "参数相似度",
    M13ComponentCode.PARAM_SUPERIORITY.value: "参数优势压力",
    M13ComponentCode.CLAIM_CONFRONTATION.value: "卖点价值对打",
    M13ComponentCode.CLAIM_SUPERIORITY.value: "卖点优势压力",
    M13ComponentCode.CLAIM_THRESHOLD_SUFFICIENCY.value: "门槛卖点满足",
    M13ComponentCode.MARKET_THREAT.value: "市场压力",
    M13ComponentCode.SALES_AMOUNT_STRENGTH.value: "销额强度",
    M13ComponentCode.COMMENT_PERCEPTION.value: "评论感知支撑",
    M13ComponentCode.PRICE_TREND.value: "价格趋势压力",
    M13ComponentCode.EVIDENCE_COMPLETENESS.value: "证据完整度",
}

M13_ROLE_LABEL_CN: dict[str, str] = {
    M13RoleCode.DIRECT_FIGHT.value: "正面对打",
    M13RoleCode.PRICE_VOLUME_PRESSURE.value: "价格销量挤压",
    M13RoleCode.BENCHMARK_POTENTIAL.value: "高端标杆/潜在下探",
    M13RoleCode.CONFIGURATION_PRESSURE.value: "配置拦截",
    M13RoleCode.SERVICE_REFERENCE.value: "服务参照",
}

M13_SUPPORT_LEVEL_LABEL_CN: dict[str, str] = {
    M13SupportLevel.STRONG.value: "强支撑",
    M13SupportLevel.MEDIUM.value: "中等支撑",
    M13SupportLevel.WEAK.value: "弱支撑",
    M13SupportLevel.MISSING.value: "缺少证据",
    M13SupportLevel.CONFLICT.value: "存在冲突",
    M13SupportLevel.NOT_APPLICABLE.value: "不适用",
}

M13_SAMPLE_STATUS_LABEL_CN: dict[str, str] = {
    M13SampleStatus.SUFFICIENT.value: "样本充分",
    M13SampleStatus.LIMITED.value: "样本有限",
    M13SampleStatus.INSUFFICIENT.value: "样本不足",
    M13SampleStatus.UNKNOWN.value: "样本未知",
}

M13_ISSUE_LEVEL_LABEL_CN: dict[str, str] = {
    M13IssueLevel.WARNING.value: "提示",
    M13IssueLevel.REVIEW.value: "需复核",
    M13IssueLevel.BLOCKER.value: "阻断",
}

M13_ISSUE_SCOPE_LABEL_CN: dict[str, str] = {
    M13IssueScope.PAIR.value: "候选关系",
    M13IssueScope.COMPONENT.value: "评分组件",
    M13IssueScope.ROLE.value: "竞品角色",
    M13IssueScope.EVIDENCE.value: "证据完整度",
}


class Core3CandidateComponentScoreResponse(Core3RealDataBaseModel):
    candidate_component_score_id: str = Field(min_length=1)
    candidate_pool_id: str = Field(min_length=1)
    feature_snapshot_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    target_model_name: str | None = None
    candidate_sku_code: str = Field(min_length=1)
    candidate_model_name: str | None = None
    candidate_brand_name: str | None = None
    same_brand_flag: bool = False
    candidate_relation_types_json: list[str] = Field(default_factory=list)
    candidate_role_hints_json: list[dict[str, Any]] = Field(default_factory=list)
    recall_strength: str = "weak"
    base_comparability_score: float = Field(default=0, ge=0, le=1)
    battlefield_fit_score: float = Field(default=0, ge=0, le=1)
    task_overlap_score: float = Field(default=0, ge=0, le=1)
    audience_overlap_score: float = Field(default=0, ge=0, le=1)
    price_position_score: float = Field(default=0, ge=0, le=1)
    price_advantage_score: float = Field(default=0, ge=0, le=1)
    size_fit_score: float = Field(default=0, ge=0, le=1)
    channel_overlap_score: float = Field(default=0, ge=0, le=1)
    param_similarity_score: float = Field(default=0, ge=0, le=1)
    param_superiority_score: float = Field(default=0, ge=0, le=1)
    claim_confrontation_score: float = Field(default=0, ge=0, le=1)
    claim_superiority_score: float = Field(default=0, ge=0, le=1)
    claim_threshold_sufficiency_score: float = Field(default=0, ge=0, le=1)
    market_threat_score: float = Field(default=0, ge=0, le=1)
    sales_amount_strength_score: float = Field(default=0, ge=0, le=1)
    comment_perception_score: float = Field(default=0, ge=0, le=1)
    price_trend_score: float = Field(default=0, ge=0, le=1)
    evidence_completeness_score: float = Field(default=0, ge=0, le=1)
    component_scores_json: dict[str, Any] = Field(default_factory=dict)
    component_total_score: float = Field(default=0, ge=0, le=1)
    direct_fight_score: float = Field(default=0, ge=0, le=1)
    price_volume_pressure_score: float = Field(default=0, ge=0, le=1)
    benchmark_potential_score: float = Field(default=0, ge=0, le=1)
    configuration_pressure_score: float = Field(default=0, ge=0, le=1)
    service_reference_score: float = Field(default=0, ge=0, le=1)
    confidence: float = Field(default=0, ge=0, le=1)
    sample_status: M13SampleStatus = M13SampleStatus.UNKNOWN
    sample_status_label_cn: str | None = None
    main_strengths_json: list[dict[str, Any] | str] = Field(default_factory=list)
    main_gaps_json: list[dict[str, Any] | str] = Field(default_factory=list)
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    review_required: bool = False
    review_reason: str | None = None
    positive_evidence_ids: list[str] = Field(default_factory=list)
    weakening_evidence_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    component_rule_version: str
    role_rule_version: str
    rule_version: str
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_component_note(self) -> "Core3CandidateComponentScoreResponse":
        self.sample_status_label_cn = self.sample_status_label_cn or _label_cn(
            self.sample_status,
            M13_SAMPLE_STATUS_LABEL_CN,
        )
        top_role = max(
            (
                ("正面对打", self.direct_fight_score),
                ("价格销量挤压", self.price_volume_pressure_score),
                ("高端标杆/潜在下探", self.benchmark_potential_score),
            ),
            key=lambda item: item[1],
        )
        review_text = "需要复核" if self.review_required else "可供下游选择模块消费"
        self.business_note_cn = self.business_note_cn or (
            f"{self.candidate_model_name or self.candidate_sku_code} 相对 {self.target_model_name or self.target_sku_code}"
            f" 的组件总分为 {self.component_total_score:.2f}，置信度 {self.confidence:.2f}，"
            f"当前最突出的候选角色是{top_role[0]}（{top_role[1]:.2f}）；{review_text}。"
            "该分数不是最终核心竞品结论。"
        )
        return self


class Core3CandidateComponentScoreListResponse(Core3RealDataBaseModel):
    items: list[Core3CandidateComponentScoreResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3CandidateRoleScoreResponse(Core3RealDataBaseModel):
    candidate_role_score_id: str = Field(min_length=1)
    candidate_component_score_id: str = Field(min_length=1)
    candidate_pool_id: str = Field(min_length=1)
    feature_snapshot_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    candidate_sku_code: str = Field(min_length=1)
    role_code: M13RoleCode
    role_name_cn: str
    role_score: float = Field(default=0, ge=0, le=1)
    role_confidence: float = Field(default=0, ge=0, le=1)
    role_rank_hint: int | None = None
    auto_select_eligible: bool = False
    auto_select_block_reason: str | None = None
    role_business_reason_cn: str
    role_business_reason_short_cn: str
    formula_version: str
    component_contribution_json: dict[str, Any] = Field(default_factory=dict)
    positive_evidence_ids: list[str] = Field(default_factory=list)
    weakening_evidence_ids: list[str] = Field(default_factory=list)
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    review_required: bool = False
    review_reason: str | None = None
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_role_note(self) -> "Core3CandidateRoleScoreResponse":
        self.role_name_cn = self.role_name_cn or _label_cn(self.role_code, M13_ROLE_LABEL_CN)
        self.business_note_cn = self.business_note_cn or (
            f"{self.role_name_cn}角色分 {self.role_score:.2f}，置信度 {self.role_confidence:.2f}。"
            "角色分用于 M14 分槽选择，不是最终排名。"
        )
        return self


class Core3CandidateRoleScoreListResponse(Core3RealDataBaseModel):
    items: list[Core3CandidateRoleScoreResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3CandidateComponentExplanationResponse(Core3RealDataBaseModel):
    candidate_component_explanation_id: str = Field(min_length=1)
    candidate_component_score_id: str = Field(min_length=1)
    candidate_pool_id: str = Field(min_length=1)
    feature_snapshot_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    candidate_sku_code: str = Field(min_length=1)
    component_code: M13ComponentCode
    component_name_cn: str
    score: float = Field(default=0, ge=0, le=1)
    confidence: float = Field(default=0, ge=0, le=1)
    support_level: M13SupportLevel = M13SupportLevel.WEAK
    support_level_label_cn: str | None = None
    business_explanation_cn: str
    positive_summary_cn: str | None = None
    gap_summary_cn: str | None = None
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    weakening_evidence_ids: list[str] = Field(default_factory=list)
    missing_evidence_reasons_json: list[dict[str, Any] | str] = Field(default_factory=list)
    source_payload_json: dict[str, Any] = Field(default_factory=dict)
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_explanation_note(self) -> "Core3CandidateComponentExplanationResponse":
        self.component_name_cn = self.component_name_cn or _label_cn(self.component_code, M13_COMPONENT_LABEL_CN)
        self.support_level_label_cn = self.support_level_label_cn or _label_cn(
            self.support_level,
            M13_SUPPORT_LEVEL_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or (
            f"{self.component_name_cn}为{self.support_level_label_cn}，组件分 {self.score:.2f}。"
        )
        return self


class Core3CandidateComponentExplanationListResponse(Core3RealDataBaseModel):
    items: list[Core3CandidateComponentExplanationResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3CandidateScoreReviewIssueResponse(Core3RealDataBaseModel):
    candidate_score_review_issue_id: str = Field(min_length=1)
    candidate_component_score_id: str | None = None
    candidate_role_score_id: str | None = None
    candidate_pool_id: str | None = None
    feature_snapshot_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    candidate_sku_code: str | None = None
    issue_scope: M13IssueScope = M13IssueScope.PAIR
    issue_scope_label_cn: str | None = None
    component_code: str = ""
    role_code: str = ""
    issue_type: str
    issue_level: M13IssueLevel = M13IssueLevel.WARNING
    issue_level_label_cn: str | None = None
    issue_message_cn: str
    suggested_action_cn: str | None = None
    source_payload_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    resolved_status: str = "open"
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_score_issue_note(self) -> "Core3CandidateScoreReviewIssueResponse":
        self.issue_scope_label_cn = self.issue_scope_label_cn or _label_cn(self.issue_scope, M13_ISSUE_SCOPE_LABEL_CN)
        self.issue_level_label_cn = self.issue_level_label_cn or _label_cn(self.issue_level, M13_ISSUE_LEVEL_LABEL_CN)
        self.business_note_cn = self.business_note_cn or self.issue_message_cn
        return self


class Core3CandidateScoreReviewIssueListResponse(Core3RealDataBaseModel):
    items: list[Core3CandidateScoreReviewIssueResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


M14_SLOT_LABEL_CN: dict[str, str] = {
    M14SelectionSlot.DIRECT_FIGHT.value: "正面对打竞品",
    M14SelectionSlot.PRICE_VOLUME_PRESSURE.value: "价格/销量挤压竞品",
    M14SelectionSlot.BENCHMARK_POTENTIAL.value: "高端标杆/潜在下探竞品",
}

M14_SELECTION_STATUS_LABEL_CN: dict[str, str] = {
    M14SelectionStatus.SUCCESS.value: "三槽位已完成",
    M14SelectionStatus.LIMITED.value: "有槽位为空",
    M14SelectionStatus.REVIEW_REQUIRED.value: "需要复核",
    M14SelectionStatus.BLOCKED.value: "阻断",
    M14SelectionStatus.FAILED.value: "失败",
}

M14_SLOT_DECISION_STATUS_LABEL_CN: dict[str, str] = {
    M14SlotDecisionStatus.SELECTED.value: "已选",
    M14SlotDecisionStatus.EMPTY.value: "空槽",
    M14SlotDecisionStatus.REVIEW_REQUIRED.value: "需复核",
    M14SlotDecisionStatus.BLOCKED.value: "阻断",
}

M14_AUDIT_DECISION_LABEL_CN: dict[str, str] = {
    M14AuditDecision.SELECTED.value: "入选",
    M14AuditDecision.REJECTED.value: "未选",
    M14AuditDecision.REVIEW.value: "待复核",
    M14AuditDecision.BLOCKED.value: "阻断",
}

M14_PRESSURE_LEVEL_LABEL_CN: dict[str, str] = {
    M14PressureLevel.HIGH.value: "高压力",
    M14PressureLevel.MEDIUM_HIGH.value: "中高压力",
    M14PressureLevel.MEDIUM.value: "中等压力",
    M14PressureLevel.REVIEW_REQUIRED.value: "需复核",
}

M14_ISSUE_LEVEL_LABEL_CN: dict[str, str] = {
    M14IssueLevel.WARNING.value: "提示",
    M14IssueLevel.REVIEW.value: "需复核",
    M14IssueLevel.BLOCKER.value: "阻断",
}

M14_ISSUE_SCOPE_LABEL_CN: dict[str, str] = {
    M14IssueScope.RUN.value: "整次选择",
    M14IssueScope.SLOT.value: "槽位",
    M14IssueScope.CANDIDATE.value: "候选",
    M14IssueScope.SELECTION.value: "入选结果",
}


class Core3CompetitorSelectionRunResponse(Core3RealDataBaseModel):
    selection_run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    target_model_name: str | None = None
    target_brand_name: str | None = None
    candidate_count: int = Field(default=0, ge=0)
    scored_candidate_count: int = Field(default=0, ge=0)
    selected_count: int = Field(default=0, ge=0, le=3)
    empty_slot_count: int = Field(default=0, ge=0, le=3)
    review_candidate_count: int = Field(default=0, ge=0)
    blocked_candidate_count: int = Field(default=0, ge=0)
    selection_status: M14SelectionStatus = M14SelectionStatus.SUCCESS
    selection_status_label_cn: str | None = None
    selection_summary_cn: str
    empty_slots_json: list[dict[str, Any]] = Field(default_factory=list)
    selection_policy_json: dict[str, Any] = Field(default_factory=dict)
    rule_version: str
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_selection_run_note(self) -> "Core3CompetitorSelectionRunResponse":
        self.selection_status_label_cn = self.selection_status_label_cn or _label_cn(
            self.selection_status,
            M14_SELECTION_STATUS_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or self.selection_summary_cn
        return self


class Core3CompetitorSelectionRunListResponse(Core3RealDataBaseModel):
    items: list[Core3CompetitorSelectionRunResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3CompetitorSelectionResponse(Core3RealDataBaseModel):
    competitor_selection_id: str = Field(min_length=1)
    selection_run_id: str = Field(min_length=1)
    candidate_pool_id: str = Field(min_length=1)
    candidate_component_score_id: str = Field(min_length=1)
    candidate_role_score_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    target_model_name: str | None = None
    target_brand_name: str | None = None
    candidate_sku_code: str = Field(min_length=1)
    candidate_model_name: str | None = None
    candidate_brand_name: str | None = None
    same_brand_flag: bool = False
    slot_code: M14SelectionSlot
    slot_name_cn: str
    slot_label_cn: str | None = None
    selection_rank: int = Field(default=1, ge=1, le=3)
    primary_battlefield_code: str | None = None
    primary_battlefield_name: str | None = None
    slot_selection_score: float = Field(default=0, ge=0, le=1)
    role_score: float = Field(default=0, ge=0, le=1)
    component_total_score: float = Field(default=0, ge=0, le=1)
    confidence: float = Field(default=0, ge=0, le=1)
    evidence_completeness_score: float = Field(default=0, ge=0, le=1)
    pressure_level: M14PressureLevel = M14PressureLevel.MEDIUM
    pressure_level_label_cn: str | None = None
    selection_reason_cn: str
    selection_reason_short_cn: str
    business_conclusion_cn: str
    strategy_hint_cn: str | None = None
    risk_summary_cn: str | None = None
    component_scores_json: dict[str, Any] = Field(default_factory=dict)
    role_scores_json: dict[str, Any] = Field(default_factory=dict)
    selection_evidence_json: dict[str, Any] = Field(default_factory=dict)
    selected_by_rules_json: list[dict[str, Any] | str] = Field(default_factory=list)
    review_required: bool = False
    review_reason: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_selection_note(self) -> "Core3CompetitorSelectionResponse":
        self.slot_label_cn = self.slot_label_cn or _label_cn(self.slot_code, M14_SLOT_LABEL_CN)
        self.pressure_level_label_cn = self.pressure_level_label_cn or _label_cn(
            self.pressure_level,
            M14_PRESSURE_LEVEL_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or self.selection_reason_short_cn
        return self


class Core3CompetitorSelectionListResponse(Core3RealDataBaseModel):
    items: list[Core3CompetitorSelectionResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3CompetitorSlotDecisionResponse(Core3RealDataBaseModel):
    slot_decision_id: str = Field(min_length=1)
    selection_run_id: str = Field(min_length=1)
    selected_competitor_selection_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    target_model_name: str | None = None
    candidate_sku_code: str | None = None
    candidate_model_name: str | None = None
    slot_code: M14SelectionSlot
    slot_name_cn: str
    slot_label_cn: str | None = None
    decision_status: M14SlotDecisionStatus = M14SlotDecisionStatus.EMPTY
    decision_status_label_cn: str | None = None
    selected_candidate_count: int = Field(default=0, ge=0, le=1)
    slot_candidate_count: int = Field(default=0, ge=0)
    empty_reason_code: str | None = None
    empty_reason_cn: str | None = None
    review_reason: str | None = None
    top_candidate_sku_code: str | None = None
    top_candidate_model_name: str | None = None
    top_candidate_score: float = Field(default=0, ge=0, le=1)
    decision_confidence: float = Field(default=0, ge=0, le=1)
    decision_summary_cn: str
    decision_payload_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_slot_note(self) -> "Core3CompetitorSlotDecisionResponse":
        self.slot_label_cn = self.slot_label_cn or _label_cn(self.slot_code, M14_SLOT_LABEL_CN)
        self.decision_status_label_cn = self.decision_status_label_cn or _label_cn(
            self.decision_status,
            M14_SLOT_DECISION_STATUS_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or self.decision_summary_cn
        return self


class Core3CompetitorSlotDecisionListResponse(Core3RealDataBaseModel):
    items: list[Core3CompetitorSlotDecisionResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3CompetitorSelectionAuditResponse(Core3RealDataBaseModel):
    selection_audit_id: str = Field(min_length=1)
    selection_run_id: str = Field(min_length=1)
    candidate_pool_id: str = Field(min_length=1)
    candidate_component_score_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    target_model_name: str | None = None
    candidate_sku_code: str = Field(min_length=1)
    candidate_model_name: str | None = None
    candidate_brand_name: str | None = None
    evaluated_slot_codes_json: list[str] = Field(default_factory=list)
    audit_decision: M14AuditDecision = M14AuditDecision.REJECTED
    audit_decision_label_cn: str | None = None
    selected_slot_code: str | None = None
    best_slot_code: str | None = None
    decision_reason_cn: str
    failed_conditions_json: list[dict[str, Any] | str] = Field(default_factory=list)
    slot_scores_json: dict[str, Any] = Field(default_factory=dict)
    candidate_total_score: float = Field(default=0, ge=0, le=1)
    best_role_score: float = Field(default=0, ge=0, le=1)
    evidence_completeness_score: float = Field(default=0, ge=0, le=1)
    confidence: float = Field(default=0, ge=0, le=1)
    risk_flags_json: list[dict[str, Any] | str] = Field(default_factory=list)
    duplicate_with_candidate_sku_code: str | None = None
    business_distinctiveness_score: float = Field(default=0, ge=0, le=1)
    strategic_value_score: float = Field(default=0, ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_audit_note(self) -> "Core3CompetitorSelectionAuditResponse":
        self.audit_decision_label_cn = self.audit_decision_label_cn or _label_cn(
            self.audit_decision,
            M14_AUDIT_DECISION_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or self.decision_reason_cn
        return self


class Core3CompetitorSelectionAuditListResponse(Core3RealDataBaseModel):
    items: list[Core3CompetitorSelectionAuditResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3CompetitorSelectionReviewIssueResponse(Core3RealDataBaseModel):
    selection_review_issue_id: str = Field(min_length=1)
    selection_run_id: str | None = None
    competitor_selection_id: str | None = None
    slot_decision_id: str | None = None
    selection_audit_id: str | None = None
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    slot_code: str = ""
    candidate_sku_code: str = ""
    issue_scope: M14IssueScope = M14IssueScope.CANDIDATE
    issue_scope_label_cn: str | None = None
    issue_type: str
    issue_level: M14IssueLevel = M14IssueLevel.WARNING
    issue_level_label_cn: str | None = None
    issue_message_cn: str
    suggested_action_cn: str | None = None
    source_payload_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    resolved_status: str = "open"
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_selection_issue_note(self) -> "Core3CompetitorSelectionReviewIssueResponse":
        self.issue_scope_label_cn = self.issue_scope_label_cn or _label_cn(self.issue_scope, M14_ISSUE_SCOPE_LABEL_CN)
        self.issue_level_label_cn = self.issue_level_label_cn or _label_cn(self.issue_level, M14_ISSUE_LEVEL_LABEL_CN)
        self.business_note_cn = self.business_note_cn or self.issue_message_cn
        return self


class Core3CompetitorSelectionReviewIssueListResponse(Core3RealDataBaseModel):
    items: list[Core3CompetitorSelectionReviewIssueResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


M15_READINESS_LABEL_CN: dict[str, str] = {
    M15ReadinessLevel.READY.value: "可展示",
    M15ReadinessLevel.REVIEW_REQUIRED.value: "需复核",
    M15ReadinessLevel.INSUFFICIENT.value: "证据不足",
}

M15_SECTION_DISPLAY_STATUS_LABEL_CN: dict[str, str] = {
    M15ReportSectionDisplayStatus.VISIBLE.value: "首屏展示",
    M15ReportSectionDisplayStatus.COLLAPSED.value: "折叠展示",
    M15ReportSectionDisplayStatus.HIDDEN.value: "默认隐藏",
}

M15_EXPORT_STATUS_LABEL_CN: dict[str, str] = {
    M15ReportExportStatus.READY.value: "可导出",
    M15ReportExportStatus.REVIEW_REQUIRED.value: "需复核",
    M15ReportExportStatus.FAILED.value: "生成失败",
}

M15_ISSUE_SCOPE_LABEL_CN: dict[str, str] = {
    M15ReportIssueScope.REPORT.value: "整份报告",
    M15ReportIssueScope.CARD.value: "竞品证据卡",
    M15ReportIssueScope.SECTION.value: "报告章节",
    M15ReportIssueScope.EXPORT.value: "导出内容",
    M15ReportIssueScope.LANGUAGE.value: "展示语言",
    M15ReportIssueScope.EVIDENCE.value: "证据引用",
}

M15_ISSUE_LEVEL_LABEL_CN: dict[str, str] = {
    M15ReportIssueLevel.WARNING.value: "提示",
    M15ReportIssueLevel.REVIEW.value: "需复核",
    M15ReportIssueLevel.BLOCKER.value: "阻断",
}


class Core3TargetReportPayloadResponse(Core3RealDataBaseModel):
    target_sku_code: str = Field(min_length=1)
    target_display_name_cn: str = Field(min_length=1)
    report_title_cn: str = Field(min_length=1)
    executive_conclusion_cn: str = Field(min_length=1)
    readiness_level: M15ReadinessLevel = M15ReadinessLevel.REVIEW_REQUIRED
    readiness_label_cn: str | None = None
    confidence_label_cn: str = Field(min_length=1)
    data_scope_note_cn: str = Field(min_length=1)
    target_profile_summary_cn: str = Field(min_length=1)
    selected_count: int = Field(default=0, ge=0, le=3)
    empty_slot_count: int = Field(default=0, ge=0, le=3)
    battlefield_summary_json: dict[str, Any] = Field(default_factory=dict)
    task_group_summary_json: dict[str, Any] = Field(default_factory=dict)
    target_signal_cards_json: list[dict[str, Any]] = Field(default_factory=list)
    core_competitors_json: list[dict[str, Any]] = Field(default_factory=list)
    empty_slots_json: list[dict[str, Any]] = Field(default_factory=list)
    why_competitor_logic_json: list[dict[str, Any]] = Field(default_factory=list)
    evidence_matrix_json: list[dict[str, Any]] = Field(default_factory=list)
    key_difference_json: list[dict[str, Any]] = Field(default_factory=list)
    strategy_hint_json: list[dict[str, Any]] = Field(default_factory=list)
    sop_trace_json: list[dict[str, Any]] = Field(default_factory=list)
    candidate_pool_summary_json: dict[str, Any] = Field(default_factory=dict)
    review_questions_json: list[dict[str, Any]] = Field(default_factory=list)
    data_quality_note_cn: str = Field(min_length=1)
    short_evidence_map_json: list[dict[str, Any]] = Field(default_factory=list)
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_report_note(self) -> "Core3TargetReportPayloadResponse":
        self.readiness_label_cn = self.readiness_label_cn or _label_cn(self.readiness_level, M15_READINESS_LABEL_CN)
        self.business_note_cn = self.business_note_cn or self.executive_conclusion_cn
        return self


class Core3TargetReportPayloadListResponse(Core3RealDataBaseModel):
    items: list[Core3TargetReportPayloadResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3EvidenceCardResponse(Core3RealDataBaseModel):
    target_sku_code: str = Field(min_length=1)
    target_display_name_cn: str = Field(min_length=1)
    competitor_sku_code: str = Field(min_length=1)
    competitor_display_name_cn: str = Field(min_length=1)
    slot_code: str = Field(min_length=1)
    slot_name_cn: str = Field(min_length=1)
    primary_battlefield_name_cn: str = Field(min_length=1)
    pressure_level_cn: str = Field(min_length=1)
    readiness_level: M15ReadinessLevel = M15ReadinessLevel.READY
    readiness_label_cn: str | None = None
    confidence_label_cn: str = Field(min_length=1)
    headline_cn: str = Field(min_length=1)
    summary_cn: str = Field(min_length=1)
    one_sentence_reason_cn: str = Field(min_length=1)
    price_evidence_cn: str | None = None
    channel_evidence_cn: str | None = None
    param_evidence_cn: str | None = None
    claim_value_evidence_cn: str | None = None
    task_audience_evidence_cn: str | None = None
    market_evidence_cn: str | None = None
    comment_evidence_cn: str | None = None
    evidence_matrix_json: list[dict[str, Any]] = Field(default_factory=list)
    key_difference_cn: str = Field(min_length=1)
    target_advantage_cn: str = Field(min_length=1)
    competitor_advantage_cn: str = Field(min_length=1)
    strategy_implication_cn: str = Field(min_length=1)
    risk_note_cn: str | None = None
    short_evidence_refs_json: list[dict[str, Any]] = Field(default_factory=list)
    display_payload_json: dict[str, Any] = Field(default_factory=dict)
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_card_note(self) -> "Core3EvidenceCardResponse":
        self.readiness_label_cn = self.readiness_label_cn or _label_cn(self.readiness_level, M15_READINESS_LABEL_CN)
        self.business_note_cn = self.business_note_cn or self.one_sentence_reason_cn
        return self


class Core3EvidenceCardListResponse(Core3RealDataBaseModel):
    items: list[Core3EvidenceCardResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3ReportSectionResponse(Core3RealDataBaseModel):
    target_sku_code: str = Field(min_length=1)
    section_code: M15ReportSectionCode
    section_title_cn: str = Field(min_length=1)
    section_order: int = Field(ge=1)
    section_payload_json: dict[str, Any] = Field(default_factory=dict)
    display_status: M15ReportSectionDisplayStatus = M15ReportSectionDisplayStatus.VISIBLE
    display_status_label_cn: str | None = None
    readiness_level: M15ReadinessLevel = M15ReadinessLevel.READY
    readiness_label_cn: str | None = None
    short_evidence_refs_json: list[dict[str, Any]] = Field(default_factory=list)
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_section_note(self) -> "Core3ReportSectionResponse":
        self.display_status_label_cn = self.display_status_label_cn or _label_cn(
            self.display_status,
            M15_SECTION_DISPLAY_STATUS_LABEL_CN,
        )
        self.readiness_label_cn = self.readiness_label_cn or _label_cn(self.readiness_level, M15_READINESS_LABEL_CN)
        self.business_note_cn = self.business_note_cn or self.section_title_cn
        return self


class Core3ReportSectionListResponse(Core3RealDataBaseModel):
    items: list[Core3ReportSectionResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3ReportExportResponse(Core3RealDataBaseModel):
    target_sku_code: str = Field(min_length=1)
    export_type: M15ReportExportType
    export_title_cn: str = Field(min_length=1)
    export_payload: str = Field(min_length=1)
    export_payload_json: dict[str, Any] = Field(default_factory=dict)
    data_scope_note_cn: str = Field(min_length=1)
    readiness_level: M15ReadinessLevel = M15ReadinessLevel.READY
    readiness_label_cn: str | None = None
    export_status: M15ReportExportStatus = M15ReportExportStatus.READY
    export_status_label_cn: str | None = None
    failure_reason: str | None = None
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_export_note(self) -> "Core3ReportExportResponse":
        self.readiness_label_cn = self.readiness_label_cn or _label_cn(self.readiness_level, M15_READINESS_LABEL_CN)
        self.export_status_label_cn = self.export_status_label_cn or _label_cn(
            self.export_status,
            M15_EXPORT_STATUS_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or self.export_title_cn
        return self


class Core3ReportExportListResponse(Core3RealDataBaseModel):
    items: list[Core3ReportExportResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3ReportReviewIssueResponse(Core3RealDataBaseModel):
    report_review_issue_id: str = Field(min_length=1)
    target_report_payload_id: str | None = None
    evidence_card_id: str | None = None
    report_section_id: str | None = None
    report_export_id: str | None = None
    target_sku_code: str = Field(min_length=1)
    issue_scope: M15ReportIssueScope = M15ReportIssueScope.REPORT
    issue_scope_label_cn: str | None = None
    section_code: str = ""
    issue_type: str = Field(min_length=1)
    issue_level: M15ReportIssueLevel = M15ReportIssueLevel.WARNING
    issue_level_label_cn: str | None = None
    issue_message_cn: str = Field(min_length=1)
    suggested_action_cn: str | None = None
    source_payload_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    resolved_status: str = "open"
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_report_issue_note(self) -> "Core3ReportReviewIssueResponse":
        self.issue_scope_label_cn = self.issue_scope_label_cn or _label_cn(self.issue_scope, M15_ISSUE_SCOPE_LABEL_CN)
        self.issue_level_label_cn = self.issue_level_label_cn or _label_cn(self.issue_level, M15_ISSUE_LEVEL_LABEL_CN)
        self.business_note_cn = self.business_note_cn or self.issue_message_cn
        return self


class Core3ReportReviewIssueListResponse(Core3RealDataBaseModel):
    items: list[Core3ReportReviewIssueResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3EvidenceShortRefTraceResponse(Core3RealDataBaseModel):
    short_ref: str = Field(min_length=1)
    target_sku_code: str = Field(min_length=1)
    evidence_domain_cn: str | None = None
    evidence_title_cn: str | None = None
    source_cn: str | None = None
    snippet_cn: str | None = None
    source_table: str | None = None
    clean_table: str | None = None
    evidence_field: str | None = None
    business_note_cn: str = "技术追溯接口，仅供内部复核使用；业务页面只展示证据短号。"


CLAIM_COMMENT_EFFECT_LABEL_CN: dict[str, str] = {
    ClaimCommentEffect.ENHANCE.value: "评论增强体验可信度",
    ClaimCommentEffect.WEAKEN.value: "评论削弱体验可信度",
    ClaimCommentEffect.NEUTRAL.value: "评论暂不改变基础判断",
    ClaimCommentEffect.CONTRADICT.value: "评论与基础判断冲突",
    ClaimCommentEffect.COMMENT_ONLY_HINT.value: "仅评论线索，待复核",
    ClaimCommentEffect.BLOCKED.value: "评论信号不允许用于该卖点",
}

CLAIM_PERCEPTION_STATUS_LABEL_CN: dict[str, str] = {
    ClaimPerceptionStatus.VALIDATED.value: "用户体验已感知",
    ClaimPerceptionStatus.WEAK_PERCEPTION.value: "用户感知偏弱",
    ClaimPerceptionStatus.CONTRADICTED.value: "用户反馈存在冲突",
    ClaimPerceptionStatus.INSUFFICIENT_COMMENT.value: "评论证据不足",
    ClaimPerceptionStatus.NOT_APPLICABLE.value: "该卖点不适合评论验证",
    ClaimPerceptionStatus.SERVICE_GUARDED.value: "服务评论隔离",
    ClaimPerceptionStatus.COMMENT_ONLY_PENDING.value: "评论线索待复核",
}

CLAIM_TYPE_LABEL_CN: dict[str, str] = {
    ClaimCommentEnhancedType.TECHNICAL_HARD.value: "硬规格技术型",
    ClaimCommentEnhancedType.TECHNICAL_EXPERIENCE_MIXED.value: "技术体验混合型",
    ClaimCommentEnhancedType.EXPERIENCE_SCENARIO.value: "体验场景型",
    ClaimCommentEnhancedType.SERVICE.value: "服务型",
    ClaimCommentEnhancedType.VALUE.value: "价值型",
    ClaimCommentEnhancedType.UNKNOWN.value: "类型待识别",
}


class ClaimCommentValidationResponse(Core3RealDataBaseModel):
    claim_comment_validation_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    claim_code: str = Field(min_length=1)
    claim_name: str = Field(min_length=1)
    claim_group: str = Field(min_length=1)
    m04b_claim_type: ClaimCommentEnhancedType
    claim_type_label_cn: str | None = None
    base_activation_score: float = Field(default=0, ge=0, le=1)
    comment_validation_score: float = Field(default=0, ge=0, le=1)
    comment_risk_score: float = Field(default=0, ge=0, le=1)
    mention_count: int = Field(default=0, ge=0)
    mention_rate: float = Field(default=0, ge=0, le=1)
    positive_rate: float = Field(default=0, ge=0, le=1)
    negative_rate: float = Field(default=0, ge=0, le=1)
    comment_effect: ClaimCommentEffect
    comment_effect_label_cn: str | None = None
    perception_status: ClaimPerceptionStatus
    perception_status_label_cn: str | None = None
    hard_spec_protection_flag: bool = False
    service_guardrail_flag: bool = False
    comment_only_flag: bool = False
    weak_perception_flag: bool = False
    contradiction_flag: bool = False
    representative_phrases: list[dict[str, Any] | str] = Field(default_factory=list)
    comment_signal_ids: list[str] = Field(default_factory=list)
    comment_evidence_ids: list[str] = Field(default_factory=list)
    base_evidence_ids: list[str] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    review_required: bool = False
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_labels(self) -> "ClaimCommentValidationResponse":
        self.claim_type_label_cn = self.claim_type_label_cn or _label_cn(self.m04b_claim_type, CLAIM_TYPE_LABEL_CN)
        self.comment_effect_label_cn = self.comment_effect_label_cn or _label_cn(self.comment_effect, CLAIM_COMMENT_EFFECT_LABEL_CN)
        self.perception_status_label_cn = self.perception_status_label_cn or _label_cn(
            self.perception_status,
            CLAIM_PERCEPTION_STATUS_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or _claim_comment_business_note(self)
        return self


class ClaimCommentValidationListResponse(Core3RealDataBaseModel):
    items: list[ClaimCommentValidationResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class SkuClaimActivationResponse(Core3RealDataBaseModel):
    claim_activation_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    claim_code: str = Field(min_length=1)
    claim_name: str = Field(min_length=1)
    claim_group: str = Field(min_length=1)
    m04b_claim_type: ClaimCommentEnhancedType
    claim_type_label_cn: str | None = None
    param_score: float = Field(default=0, ge=0, le=1)
    promo_score: float = Field(default=0, ge=0, le=1)
    base_activation_score: float = Field(default=0, ge=0, le=1)
    comment_validation_score: float = Field(default=0, ge=0, le=1)
    comment_risk_score: float = Field(default=0, ge=0, le=1)
    final_activation_score: float = Field(default=0, ge=0, le=1)
    activation_level: ClaimCommentActivationLevel
    activation_basis: ClaimCommentActivationBasis
    perception_status: ClaimPerceptionStatus
    perception_status_label_cn: str | None = None
    claim_source_status: str = "claim_data_insufficient"
    comment_effect: ClaimCommentEffect
    comment_effect_label_cn: str | None = None
    hard_spec_protection_flag: bool = False
    service_guardrail_flag: bool = False
    missing_structured_claim_flag: bool = False
    param_only_flag: bool = False
    promo_only_flag: bool = False
    comment_only_flag: bool = False
    weak_perception_flag: bool = False
    contradiction_flag: bool = False
    value_requires_market_validation: bool = False
    downstream_usage_policy_json: dict[str, Any] = Field(default_factory=dict)
    score_breakdown_json: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    param_evidence_ids: list[str] = Field(default_factory=list)
    promo_evidence_ids: list[str] = Field(default_factory=list)
    comment_evidence_ids: list[str] = Field(default_factory=list)
    comment_signal_ids: list[str] = Field(default_factory=list)
    representative_phrases: list[dict[str, Any] | str] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    review_required: bool = False
    business_note_cn: str | None = None

    @model_validator(mode="after")
    def fill_labels(self) -> "SkuClaimActivationResponse":
        self.claim_type_label_cn = self.claim_type_label_cn or _label_cn(self.m04b_claim_type, CLAIM_TYPE_LABEL_CN)
        self.comment_effect_label_cn = self.comment_effect_label_cn or _label_cn(self.comment_effect, CLAIM_COMMENT_EFFECT_LABEL_CN)
        self.perception_status_label_cn = self.perception_status_label_cn or _label_cn(
            self.perception_status,
            CLAIM_PERCEPTION_STATUS_LABEL_CN,
        )
        self.business_note_cn = self.business_note_cn or _claim_activation_business_note(self)
        return self


class SkuClaimActivationListResponse(Core3RealDataBaseModel):
    items: list[SkuClaimActivationResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class ClaimCommentReviewIssueResponse(Core3RealDataBaseModel):
    issue_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    claim_code: str = Field(min_length=1)
    claim_name: str = Field(min_length=1)
    issue_type: ClaimCommentIssueType
    severity: ClaimCommentIssueSeverity
    business_note: str = Field(min_length=1)
    suggested_action: str = Field(min_length=1)
    downstream_policy: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    comment_signal_ids: list[str] = Field(default_factory=list)
    issue_status: ClaimCommentIssueStatus = ClaimCommentIssueStatus.OPEN
    review_required: bool = True


class ClaimCommentReviewIssueListResponse(Core3RealDataBaseModel):
    items: list[ClaimCommentReviewIssueResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class ClaimActivationEvidenceResponse(Core3RealDataBaseModel):
    claim_activation: SkuClaimActivationResponse
    param_evidence_ids: list[str] = Field(default_factory=list)
    promo_evidence_ids: list[str] = Field(default_factory=list)
    comment_evidence_ids: list[str] = Field(default_factory=list)
    comment_signal_ids: list[str] = Field(default_factory=list)
    evidence_boundary_note_cn: str = "评论只验证体验感知，不能证明亮度、分区、接口数量、面板等硬规格。"


def _market_profile_business_note(item: Core3SkuMarketProfileResponse) -> str:
    parts: list[str] = []
    if item.price_wavg is not None:
        parts.append(f"观察期加权均价约 {item.price_wavg:.0f} 元")
    if item.sales_volume_total is not None:
        parts.append(f"销量 {item.sales_volume_total:.0f}")
    if item.screen_size_inch is not None:
        parts.append(f"尺寸 {item.screen_size_inch:.0f} 英寸")
    if item.main_platform:
        parts.append(f"主销平台为 {item.main_platform}")
    parts.append(item.sample_status_label_cn or _label_cn(item.sample_status, M07_SAMPLE_STATUS_LABEL_CN))
    return "；".join(parts)


def _market_signal_business_note(item: Core3MarketSignalResponse) -> str:
    signal_label = item.signal_label_cn or _label_cn(item.signal_code, M07_SIGNAL_LABEL_CN)
    return f"{signal_label}，强度 {item.signal_strength:.2f}；该信号只能作为市场证据，不能单独决定任务、客群、战场或竞品。"


def _comparable_pool_business_note(item: Core3ComparablePoolResponse) -> str:
    return (
        f"{item.pool_type_label_cn or _label_cn(item.pool_type, M07_POOL_TYPE_LABEL_CN)}包含 "
        f"{item.pool_sku_count} 个 SKU；这是市场可比基线，不等同最终竞品列表。"
    )


def _pool_member_business_note(item: Core3MarketPoolMemberResponse) -> str:
    if item.is_target_self:
        return "目标 SKU 本身参与池内分布计算，后续候选召回会再排除自身。"
    size_relation = M07_SIZE_RELATION_LABEL_CN.get(item.size_relation, item.size_relation)
    price_relation = M07_PRICE_RELATION_LABEL_CN.get(item.price_band_relation, item.price_band_relation)
    return (
        f"与目标的尺寸关系为 {size_relation}，价位关系为 {price_relation}，"
        f"平台重合度 {item.platform_overlap_score:.2f}。"
    )


def _sku_signal_profile_business_note(item: Core3SkuSignalProfileResponse) -> str:
    missing_count = len(item.missing_signals_json)
    risk_count = len(item.risk_signals_json)
    status_label = item.profile_status_label_cn or _label_cn(item.profile_status, M08_PROFILE_STATUS_LABEL_CN)
    return (
        f"综合画像完整度 {item.data_completeness_score:.2f}，置信度 {item.confidence:.2f}，"
        f"当前状态：{status_label}；缺口 {missing_count} 项，风险 {risk_count} 项。"
    )


def _sku_signal_matrix_business_note(item: Core3SkuSignalEvidenceMatrixResponse) -> str:
    domain_label = item.domain_label_cn or _label_cn(item.domain, M08_SIGNAL_DOMAIN_LABEL_CN)
    coverage_label = item.coverage_status_label_cn or _label_cn(item.coverage_status, M08_COVERAGE_STATUS_LABEL_CN)
    return f"{domain_label}/{item.sub_domain}：{coverage_label}，代表证据 {item.evidence_count} 条。"


def _sku_signal_view_business_note(item: Core3SkuDownstreamFeatureViewResponse) -> str:
    module_label = item.for_module_label_cn or _label_cn(item.for_module, M08_FOR_MODULE_LABEL_CN)
    if item.ready_for_module:
        return f"已准备好作为{module_label}输入；仍需由后续模块生成业务结论。"
    missing = "、".join(item.required_missing_fields_json) if item.required_missing_fields_json else "必要输入"
    return f"暂不建议直接进入{module_label}；缺少 {missing}。"


def _sku_task_candidate_business_note(item: Core3SkuTaskCandidateResponse) -> str:
    status = item.candidate_status_label_cn or _label_cn(item.candidate_status, M09_TASK_CANDIDATE_STATUS_LABEL_CN)
    source_count = len(item.candidate_sources_json)
    return f"{item.task_name_cn}：{status}，候选分 {item.initial_candidate_score:.2f}，来自 {source_count} 类证据。"


def _sku_task_score_business_note(item: Core3SkuTaskScoreResponse) -> str:
    relation = item.relation_level_label_cn or _label_cn(item.relation_level, M09_TASK_RELATION_LABEL_CN)
    return (
        f"{item.task_name_cn}为{relation}，任务分 {item.task_score:.2f}，置信度 {item.confidence:.2f}；"
        f"能力 {item.param_signal_score:.2f}、卖点 {item.claim_signal_score:.2f}、评论 {item.comment_signal_score:.2f}、市场 {item.market_signal_score:.2f}。"
    )


def _sku_task_breakdown_business_note(item: Core3SkuTaskEvidenceBreakdownResponse) -> str:
    domain = item.evidence_domain_label_cn or _label_cn(item.evidence_domain, M09_TASK_EVIDENCE_DOMAIN_LABEL_CN)
    support = item.support_level_label_cn or _label_cn(item.support_level, M09_TASK_SUPPORT_LEVEL_LABEL_CN)
    return f"{domain}：{support}，分域得分 {item.domain_score:.2f}，证据 {item.evidence_count} 条。"


def _sku_target_group_candidate_business_note(item: Core3SkuTargetGroupCandidateResponse) -> str:
    status = item.candidate_status_label_cn or _label_cn(
        item.candidate_status,
        M10_TARGET_GROUP_CANDIDATE_STATUS_LABEL_CN,
    )
    source_count = len(item.candidate_source_json)
    return f"{item.target_group_name_cn}：{status}，候选分 {item.candidate_initial_score:.2f}，来自 {source_count} 类证据。"


def _sku_target_group_score_business_note(item: Core3SkuTargetGroupScoreResponse) -> str:
    relation = item.relation_level_label_cn or _label_cn(
        item.relation_level,
        M10_TARGET_GROUP_RELATION_LABEL_CN,
    )
    return (
        f"{item.target_group_name_cn}为{relation}，客群分 {item.target_group_score:.2f}，置信度 {item.confidence:.2f}；"
        f"购买任务 {item.task_support_score:.2f}、用户线索 {item.comment_group_signal_score:.2f}、"
        f"价格渠道 {item.price_channel_fit_score:.2f}、市场验证 {item.market_validation_score:.2f}。"
    )


def _sku_target_group_breakdown_business_note(item: Core3SkuTargetGroupEvidenceBreakdownResponse) -> str:
    domain = item.evidence_domain_label_cn or _label_cn(
        item.evidence_domain,
        M10_TARGET_GROUP_EVIDENCE_DOMAIN_LABEL_CN,
    )
    support = item.support_level_label_cn or _label_cn(
        item.support_level,
        M10_TARGET_GROUP_SUPPORT_LEVEL_LABEL_CN,
    )
    return f"{domain}：{support}，分域得分 {item.domain_score:.2f}，证据 {item.evidence_count} 条。"


def _sku_battlefield_candidate_business_note(item: Core3SkuBattlefieldCandidateResponse) -> str:
    status = item.candidate_status_label_cn or _label_cn(
        item.candidate_status,
        M11_BATTLEFIELD_CANDIDATE_STATUS_LABEL_CN,
    )
    source_count = len(item.candidate_source_json)
    return f"{item.battlefield_name_cn}：{status}，候选分 {item.candidate_initial_score:.2f}，来自 {source_count} 类证据。"


def _sku_battlefield_score_business_note(item: Core3SkuBattlefieldScoreResponse) -> str:
    relation = item.relation_level_label_cn or _label_cn(
        item.relation_level,
        M11_BATTLEFIELD_RELATION_LABEL_CN,
    )
    role = item.competitor_selection_role_label_cn or _label_cn(
        item.competitor_selection_role,
        M11_COMPETITOR_SELECTION_ROLE_LABEL_CN,
    )
    return (
        f"{item.battlefield_name_cn}为{relation}，战场分 {item.battlefield_score:.2f}，置信度 {item.confidence:.2f}，{role}；"
        f"任务 {item.core_task_score:.2f}、客群 {item.target_group_score:.2f}、卖点 {item.core_claim_combo_score:.2f}、"
        f"参数 {item.core_param_capability_score:.2f}、评论 {item.comment_support_score:.2f}、市场 {item.market_score:.2f}。"
    )


def _sku_battlefield_breakdown_business_note(item: Core3SkuBattlefieldEvidenceBreakdownResponse) -> str:
    domain = item.evidence_domain_label_cn or _label_cn(
        item.evidence_domain,
        M11_BATTLEFIELD_EVIDENCE_DOMAIN_LABEL_CN,
    )
    support = item.support_level_label_cn or _label_cn(
        item.support_level,
        M11_BATTLEFIELD_SUPPORT_LEVEL_LABEL_CN,
    )
    return f"{domain}：{support}，分域得分 {item.domain_score:.2f}，证据 {item.evidence_count} 条。"


def _sku_claim_value_candidate_business_note(item: Core3SkuBattlefieldClaimCandidateResponse) -> str:
    status = item.candidate_status_label_cn or _label_cn(
        item.candidate_status,
        M11_5_CLAIM_CANDIDATE_STATUS_LABEL_CN,
    )
    source_count = len(item.candidate_source_json)
    return (
        f"{item.claim_name_cn}在「{item.battlefield_name_cn}」中{status}，候选分 {item.candidate_initial_score:.2f}，"
        f"来自 {source_count} 类证据；该结果只说明卖点进入战场内价值判断，不代表竞品结论。"
    )


def _sku_claim_value_layer_business_note(item: Core3SkuClaimValueLayerResponse) -> str:
    role = item.battlefield_relevance_role_label_cn or _label_cn(
        item.battlefield_relevance_role,
        M11_5_RELEVANCE_ROLE_LABEL_CN,
    )
    layer = item.layer_label_cn or _label_cn(item.layer, M11_5_LAYER_LABEL_CN)
    sample = item.sample_sufficiency_label_cn or _label_cn(
        item.sample_sufficiency,
        M11_5_SAMPLE_SUFFICIENCY_LABEL_CN,
    )
    return (
        f"{item.claim_name_cn}在「{item.battlefield_name_cn}」中属于{role}，分层为{layer}，"
        f"价值分 {item.claim_value_score:.2f}，置信度 {item.confidence:.2f}，可比池{sample}；"
        f"后续只能作为 M12-M15 的卖点价值证据。"
    )


def _sku_claim_value_breakdown_business_note(item: Core3SkuClaimValueEvidenceBreakdownResponse) -> str:
    domain = item.evidence_domain_label_cn or _label_cn(
        item.evidence_domain,
        M11_5_EVIDENCE_DOMAIN_LABEL_CN,
    )
    support = item.support_level_label_cn or _label_cn(
        item.support_level,
        M11_5_SUPPORT_LEVEL_LABEL_CN,
    )
    return f"{domain}：{support}，分域得分 {item.support_score:.2f}，贡献 {item.weighted_contribution:.2f}。"


def _sku_business_profile_note(item: Core3SkuBusinessProfileResponse) -> str:
    sku_name = item.model_name or item.sku_code
    primary_parts: list[str] = []
    if item.primary_battlefield_name:
        primary_parts.append(f"主战场是「{item.primary_battlefield_name}」")
    if item.primary_task_name:
        primary_parts.append(f"主任务是「{item.primary_task_name}」")
    if item.primary_target_group_name:
        primary_parts.append(f"主客群是「{item.primary_target_group_name}」")
    if not primary_parts:
        primary_parts.append("主战场、主任务和主客群仍需补充证据")
    claim_part = f"卖点价值强度 {item.claim_value_strength:.2f}"
    premium_part = f"溢价判断：{item.premium_reason_cn}"
    role_part = f"市场角色：{item.market_role_reason_cn}"
    return f"{sku_name}：{'，'.join(primary_parts)}；{claim_part}；{premium_part}；{role_part}"


def _candidate_pool_business_note(item: Core3CandidatePoolResponse) -> str:
    target_name = item.target_model_name or item.target_sku_code
    candidate_name = item.candidate_model_name or item.candidate_sku_code
    brand_relation = "同品牌" if item.same_brand_flag else "跨品牌"
    relation = item.primary_relation_label_cn or _label_cn(
        item.primary_relation_type,
        M12_RELATION_TYPE_LABEL_CN,
    )
    strength = item.recall_strength_label_cn or _label_cn(
        item.recall_strength,
        M12_RECALL_STRENGTH_LABEL_CN,
    )
    source_labels = item.recall_source_labels_cn or [
        _label_cn(source, M12_RECALL_SOURCE_LABEL_CN) for source in item.recall_sources_json
    ]
    source_text = "、".join(source_labels) if source_labels else "召回依据待补充"
    return (
        f"{candidate_name} 是 {target_name} 的{brand_relation}{relation}候选，"
        f"召回强度为{strength}，入池依据来自{source_text}；"
        "M12 只说明为什么进入候选池，不代表最终核心三竞品。"
    )


def _claim_comment_business_note(item: ClaimCommentValidationResponse) -> str:
    notes: list[str] = []
    if item.hard_spec_protection_flag:
        notes.append("评论仅验证体验，不能证明硬规格")
    if item.service_guardrail_flag:
        notes.append("服务评论只进入服务保障口径")
    if item.comment_only_flag:
        notes.append("该卖点只有评论线索，需复核")
    if item.weak_perception_flag:
        notes.append("基础卖点存在但用户感知偏弱")
    if item.contradiction_flag:
        notes.append("评论反馈与基础卖点存在冲突")
    if not notes:
        notes.append("评论验证用于补充体验感知")
    return "；".join(notes)


def _claim_activation_business_note(item: SkuClaimActivationResponse) -> str:
    notes: list[str] = []
    if item.missing_structured_claim_flag:
        notes.append("缺结构化宣传卖点数据")
    if item.param_only_flag:
        notes.append("参数支撑，宣传卖点缺失")
    if item.promo_only_flag:
        notes.append("宣传支撑，参数证据不足")
    if item.comment_only_flag:
        notes.append("仅评论线索，待复核")
    if item.hard_spec_protection_flag:
        notes.append("评论不能证明硬规格")
    if item.value_requires_market_validation:
        notes.append("价值感需结合市场价格验证")
    if not notes:
        notes.append("参数、宣传与评论体验形成当前卖点判断")
    return "；".join(notes)


class CommentSignalCandidateResponse(Core3RealDataBaseModel):
    signal_candidate_id: str = Field(min_length=1)
    comment_unit_id: str = Field(min_length=1)
    comment_evidence_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    sentence_text: str = Field(min_length=1)
    signal_type: CommentSignalType
    signal_type_label_cn: str | None = None
    target_code_hint: str = Field(min_length=1)
    target_name_hint: str = Field(min_length=1)
    polarity: CommentSignalPolarity
    polarity_label_cn: str | None = None
    signal_strength: float = Field(default=0, ge=0, le=1)
    signal_strength_level: CommentSignalStrengthLevel
    confidence: float = Field(default=0, ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    cue_basis: CommentSignalCueBasis
    hard_spec_policy: CommentHardSpecPolicy
    hard_spec_policy_label_cn: str | None = None
    service_guardrail_flag: bool = False
    downstream_usage_note_cn: str | None = None
    matched_entities_json: dict[str, Any] = Field(default_factory=dict)
    topic_hints_json: list[dict[str, Any]] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)
    source_m05_evidence_ids: list[str] = Field(default_factory=list)
    source_m02_evidence_ids: list[str] = Field(default_factory=list)
    review_required: bool = False

    @model_validator(mode="after")
    def fill_business_labels(self) -> "CommentSignalCandidateResponse":
        self.signal_type_label_cn = self.signal_type_label_cn or _label_cn(
            self.signal_type,
            COMMENT_SIGNAL_TYPE_LABEL_CN,
        )
        self.polarity_label_cn = self.polarity_label_cn or _label_cn(
            self.polarity,
            COMMENT_SIGNAL_POLARITY_LABEL_CN,
        )
        self.hard_spec_policy_label_cn = self.hard_spec_policy_label_cn or _label_cn(
            self.hard_spec_policy,
            COMMENT_HARD_SPEC_POLICY_LABEL_CN,
        )
        self.downstream_usage_note_cn = self.downstream_usage_note_cn or (
            "仅可用于服务保障或安装相关分析"
            if self.service_guardrail_flag
            else "仅作为后续模块的评论体验信号，不是最终业务结论"
        )
        return self


class CommentSignalCandidateListResponse(Core3RealDataBaseModel):
    items: list[CommentSignalCandidateResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class CommentDownstreamSignalResponse(Core3RealDataBaseModel):
    signal_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    signal_type: CommentSignalType
    signal_type_label_cn: str | None = None
    target_code_hint: str = Field(min_length=1)
    target_name_hint: str = Field(min_length=1)
    polarity: CommentSignalPolarity
    polarity_label_cn: str | None = None
    mention_count: int = Field(default=0, ge=0)
    sentence_count: int = Field(default=0, ge=0)
    valid_comment_unit_count: int = Field(default=0, ge=0)
    mention_rate: float = Field(default=0, ge=0, le=1)
    positive_rate: float = Field(default=0, ge=0, le=1)
    negative_rate: float = Field(default=0, ge=0, le=1)
    signal_score: float = Field(default=0, ge=0, le=1)
    signal_level: CommentSignalStrengthLevel
    representative_phrases: list[str] = Field(default_factory=list)
    service_guardrail_flag: bool = False
    hard_spec_policy: CommentHardSpecPolicy
    hard_spec_policy_label_cn: str | None = None
    quality_summary: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    review_required: bool = False

    @model_validator(mode="after")
    def fill_business_labels(self) -> "CommentDownstreamSignalResponse":
        self.signal_type_label_cn = self.signal_type_label_cn or _label_cn(
            self.signal_type,
            COMMENT_SIGNAL_TYPE_LABEL_CN,
        )
        self.polarity_label_cn = self.polarity_label_cn or _label_cn(
            self.polarity,
            COMMENT_SIGNAL_POLARITY_LABEL_CN,
        )
        self.hard_spec_policy_label_cn = self.hard_spec_policy_label_cn or _label_cn(
            self.hard_spec_policy,
            COMMENT_HARD_SPEC_POLICY_LABEL_CN,
        )
        return self


class CommentDownstreamSignalListResponse(Core3RealDataBaseModel):
    items: list[CommentDownstreamSignalResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class SkuCommentSignalProfileResponse(Core3RealDataBaseModel):
    sku_comment_signal_profile_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    category_code: Core3CategoryCode = Core3CategoryCode.TV
    batch_id: str = Field(min_length=1)
    sku_code: str = Field(min_length=1)
    model_name: str | None = None
    brand_name: str | None = None
    comment_signal_summary_json: dict[str, Any] = Field(default_factory=dict)
    claim_validation_summary_json: dict[str, Any] = Field(default_factory=dict)
    task_cue_summary_json: dict[str, Any] = Field(default_factory=dict)
    target_group_cue_summary_json: dict[str, Any] = Field(default_factory=dict)
    battlefield_support_summary_json: dict[str, Any] = Field(default_factory=dict)
    pain_risk_summary_json: dict[str, Any] = Field(default_factory=dict)
    price_perception_summary_json: dict[str, Any] = Field(default_factory=dict)
    service_signal_summary_json: dict[str, Any] = Field(default_factory=dict)
    strong_signal_count: int = Field(default=0, ge=0)
    medium_signal_count: int = Field(default=0, ge=0)
    weak_signal_count: int = Field(default=0, ge=0)
    blocked_signal_count: int = Field(default=0, ge=0)
    claim_validation_ready: bool = False
    task_cue_ready: bool = False
    target_group_cue_ready: bool = False
    battlefield_support_ready: bool = False
    comment_signal_confidence: float = Field(default=0, ge=0, le=1)
    confidence_level: Core3ConfidenceLevel = Core3ConfidenceLevel.UNKNOWN
    quality_flags: list[str] = Field(default_factory=list)
    review_required: bool = False
    summary_cn: str | None = None

    @model_validator(mode="after")
    def fill_summary_cn(self) -> "SkuCommentSignalProfileResponse":
        if self.summary_cn is None:
            self.summary_cn = (
                f"该 SKU 已形成 {self.strong_signal_count} 个强信号、"
                f"{self.medium_signal_count} 个中信号、{self.weak_signal_count} 个弱信号；"
                "这些内容只作为评论体验信号，供后续模块综合推导。"
            )
        return self


class SkuCommentSignalProfileListResponse(Core3RealDataBaseModel):
    items: list[SkuCommentSignalProfileResponse] = Field(default_factory=list)
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    summary_cn: str | None = None


class Core3SourceTableWatermarkOut(Core3RealDataBaseModel):
    source_table: str = Field(min_length=1)
    row_count: int = Field(ge=0)
    min_source_pk: str | None = None
    max_source_pk: str | None = None
    min_write_time: datetime | None = None
    max_write_time: datetime | None = None
    distinct_sku_count: int = Field(default=0, ge=0)
    schema_hash: str | None = None
    schema_status: str | None = None
    previous_success_batch_id: str | None = None
    candidate_rule: str | None = None

    @field_validator("source_table")
    @classmethod
    def validate_source_table(cls, source_table: str) -> str:
        if source_table not in CORE3_RAW_SOURCE_TABLES:
            raise ValueError(f"unknown source_table: {source_table}")
        return source_table
