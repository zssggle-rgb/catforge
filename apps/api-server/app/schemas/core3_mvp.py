from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Core3SeedBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Core3RunRequest(BaseModel):
    target_sku_code: str | None = None
    target_model: str | None = None
    batch: bool = False
    force_recompute: bool = False

    @model_validator(mode="after")
    def require_single_target(self) -> "Core3RunRequest":
        if self.batch:
            return self
        has_sku = bool((self.target_sku_code or "").strip())
        has_model = bool((self.target_model or "").strip())
        if not has_sku and not has_model:
            raise ValueError("batch=false 时必须提供 target_sku_code 或 target_model")
        return self


class Core3SkuIdentity(BaseModel):
    sku_code: str
    brand: str | None = None
    model_name: str | None = None
    series: str | None = None


class Core3EvidenceRef(BaseModel):
    evidence_id: str
    source_type: str
    field_name: str | None = None
    raw_value: Any = None
    normalized_value: Any = None
    confidence: float


class Core3SkuCandidate(BaseModel):
    sku_code: str
    brand: str | None = None
    model_name: str | None = None
    series: str | None = None
    match_type: str


class Core3SkuResolveOut(BaseModel):
    input: str
    sku_code: str
    brand: str | None = None
    model_name: str | None = None
    series: str | None = None
    match_type: str
    candidates: list[Core3SkuCandidate] = Field(default_factory=list)


class Core3DataStatusOut(BaseModel):
    project_id: str
    category_code: str
    status: str
    sku_count: int
    brand_count: int
    channel_count: int
    market_fact_count: int
    param_row_count: int
    claim_row_count: int
    comment_row_count: int
    missing_summary: dict[str, int]
    latest_run: dict[str, Any] | None = None


class Core3RunOut(BaseModel):
    run_id: str
    status: str
    scope: str
    target_sku_code: str | None = None
    counts: dict[str, int | float]
    warnings: list[str]
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    latest_report_ref: str | None = None


class Core3SkuReportOut(BaseModel):
    project_id: str
    run_id: str
    target_sku: Core3SkuIdentity
    derivation_summary: dict[str, Any] = Field(default_factory=dict)
    market_profile: dict[str, Any]
    standard_params: dict[str, Any]
    activated_claims: list[dict[str, Any]]
    comment_topics: list[dict[str, Any]]
    tasks: list[dict[str, Any]]
    target_groups: list[dict[str, Any]]
    battlefields: list[dict[str, Any]]
    core_competitors: list[dict[str, Any]]
    extraction_diagnostics: dict[str, Any] = Field(default_factory=dict)
    confidence_level: str
    review_flag: bool
    insufficient_reasons: list[str]


class Core3StandardParamSeed(Core3SeedBaseModel):
    param_code: str
    param_name: str
    definition: str
    param_group: str
    data_type: str
    unit: str | None = None
    aliases: list[str]
    keywords: list[str]
    source_types: list[str]
    source_priority: list[str]
    evidence_requirement: list[str]
    value_parsers: list[str]
    enum_values: list[str] = Field(default_factory=list)
    thresholds: dict[str, Any] = Field(default_factory=dict)
    mapped_claim_codes: list[str] = Field(default_factory=list)
    mapped_task_codes: list[str] = Field(default_factory=list)
    mapped_battlefield_codes: list[str] = Field(default_factory=list)


class Core3StandardClaimSeed(Core3SeedBaseModel):
    claim_code: str
    claim_name: str
    definition: str
    claim_group: str
    aliases: list[str]
    keywords: list[str]
    promo_keywords: list[str]
    source_types: list[str]
    evidence_requirement: list[str]
    supporting_param_codes: list[str] = Field(default_factory=list)
    comment_topic_codes: list[str] = Field(default_factory=list)
    activation_rule: dict[str, Any] = Field(default_factory=dict)
    activation_weights: dict[str, float] = Field(default_factory=dict)
    mapped_param_codes: list[str] = Field(default_factory=list)
    mapped_task_codes: list[str] = Field(default_factory=list)
    mapped_battlefield_codes: list[str] = Field(default_factory=list)


class Core3CommentTopicSeed(Core3SeedBaseModel):
    topic_code: str
    topic_name: str
    definition: str
    topic_group: str
    aliases: list[str]
    keywords: list[str]
    positive_keywords: list[str] = Field(default_factory=list)
    negative_keywords: list[str] = Field(default_factory=list)
    source_types: list[str]
    evidence_requirement: list[str]
    mapped_claim_codes: list[str] = Field(default_factory=list)
    mapped_task_codes: list[str] = Field(default_factory=list)
    mapped_battlefield_codes: list[str] = Field(default_factory=list)
    activates_product_claim: bool = True


class Core3UserTaskSeed(Core3SeedBaseModel):
    task_code: str
    task_name: str
    definition: str
    aliases: list[str]
    keywords: list[str]
    source_types: list[str]
    evidence_requirement: list[str]
    positive_claim_codes: list[str] = Field(default_factory=list)
    positive_param_codes: list[str] = Field(default_factory=list)
    comment_topic_codes: list[str] = Field(default_factory=list)
    market_signals: list[str] = Field(default_factory=list)
    score_rule: dict[str, float] = Field(default_factory=dict)
    default_target_group_codes: list[str] = Field(default_factory=list)
    battlefield_codes: list[str] = Field(default_factory=list)
    mapped_claim_codes: list[str] = Field(default_factory=list)
    mapped_param_codes: list[str] = Field(default_factory=list)
    mapped_topic_codes: list[str] = Field(default_factory=list)
    mapped_target_group_codes: list[str] = Field(default_factory=list)
    mapped_battlefield_codes: list[str] = Field(default_factory=list)


class Core3TargetGroupSeed(Core3SeedBaseModel):
    target_group_code: str
    target_group_name: str
    definition: str
    aliases: list[str]
    keywords: list[str]
    source_types: list[str]
    evidence_requirement: list[str]
    source_task_codes: list[str]
    market_fit_rule: dict[str, Any] = Field(default_factory=dict)
    mapped_task_codes: list[str] = Field(default_factory=list)
    mapped_battlefield_codes: list[str] = Field(default_factory=list)


class Core3BattlefieldSeed(Core3SeedBaseModel):
    battlefield_code: str
    battlefield_name: str
    definition: str
    aliases: list[str]
    keywords: list[str]
    source_types: list[str]
    evidence_requirement: list[str]
    core_task_codes: list[str]
    core_claim_codes: list[str]
    core_param_codes: list[str]
    comment_topic_codes: list[str] = Field(default_factory=list)
    required_signal_rule: dict[str, Any] = Field(default_factory=dict)
    semantic_market_weights: dict[str, float] = Field(default_factory=dict)
    market_score_rule: dict[str, Any] = Field(default_factory=dict)
    entry_thresholds: dict[str, float] = Field(default_factory=dict)
    mapped_task_codes: list[str] = Field(default_factory=list)
    mapped_claim_codes: list[str] = Field(default_factory=list)
    mapped_param_codes: list[str] = Field(default_factory=list)
    mapped_topic_codes: list[str] = Field(default_factory=list)


class Core3SeedCatalog(Core3SeedBaseModel):
    version: str
    category_code: str
    standard_params: list[Core3StandardParamSeed]
    standard_claims: list[Core3StandardClaimSeed]
    comment_topics: list[Core3CommentTopicSeed]
    user_tasks: list[Core3UserTaskSeed]
    target_groups: list[Core3TargetGroupSeed]
    battlefields: list[Core3BattlefieldSeed]


class Core3ParsedValue(BaseModel):
    parser: str
    value: Any = None
    unit: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class Core3ParamFieldProfile(BaseModel):
    raw_param_name: str
    row_count: int
    sku_count: int
    coverage: float
    non_empty_rate: float
    top_values: list[str]
    contains_numeric: bool
    matched_param_code: str | None = None
    match_type: str | None = None
    match_confidence: float = 0.0
    status: str


class Core3CandidateParamAlias(BaseModel):
    raw_param_name: str
    coverage: float
    examples: list[str]
    suggested_param_code: str | None = None
    confidence: float
    review_status: str = "pending"


class Core3CandidateClaim(BaseModel):
    raw_phrase: str
    coverage: float
    example_skus: list[str]
    sample_sentences: list[str]
    suggested_group: str
    confidence: float
    review_status: str = "pending"


class Core3CandidateCommentTopic(BaseModel):
    raw_phrase: str
    coverage: float
    sample_sentences: list[str]
    suggested_topic_group: str
    sentiment_hint: str
    confidence: float
    review_status: str = "pending"


class Core3ExtractionDiagnostics(BaseModel):
    field_mappings: list[Core3ParamFieldProfile] = Field(default_factory=list)
    param_conflicts: list[dict[str, Any]] = Field(default_factory=list)
    candidate_param_aliases: list[Core3CandidateParamAlias] = Field(default_factory=list)
    candidate_claims: list[Core3CandidateClaim] = Field(default_factory=list)
    candidate_comment_topics: list[Core3CandidateCommentTopic] = Field(default_factory=list)
    missing_signals: list[str] = Field(default_factory=list)
