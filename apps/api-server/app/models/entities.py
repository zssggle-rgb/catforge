from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def new_id() -> str:
    return str(uuid4())


def now_utc() -> datetime:
    return datetime.utcnow()


class AuditMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=now_utc, onupdate=now_utc, nullable=False
    )


class CategoryProject(Base, AuditMixin):
    __tablename__ = "category_project"

    project_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    description: Mapped[str | None] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active")


class SourceFile(Base, AuditMixin):
    __tablename__ = "source_file"

    source_file_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(60), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="uploaded")
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ImportBatch(Base, AuditMixin):
    __tablename__ = "import_batch"

    import_batch_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    source_file_id: Mapped[str] = mapped_column(ForeignKey("source_file.source_file_id"))
    file_type: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="completed")
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class RawBaseMixin(AuditMixin):
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    source_file_id: Mapped[str] = mapped_column(ForeignKey("source_file.source_file_id"))
    import_batch_id: Mapped[str] = mapped_column(ForeignKey("import_batch.import_batch_id"))
    raw_row_id: Mapped[str] = mapped_column(String(80), nullable=False)


class RawSkuMaster(Base, RawBaseMixin):
    __tablename__ = "raw_sku_master"

    sku_code: Mapped[str | None] = mapped_column(String(120), index=True)
    brand: Mapped[str | None] = mapped_column(String(120))
    model_name: Mapped[str | None] = mapped_column(String(160))
    series: Mapped[str | None] = mapped_column(String(120))
    category_name: Mapped[str | None] = mapped_column(String(120))
    launch_date: Mapped[str | None] = mapped_column(String(80))
    product_url: Mapped[str | None] = mapped_column(Text)


class RawSkuParam(Base, RawBaseMixin):
    __tablename__ = "raw_sku_param"

    sku_code: Mapped[str | None] = mapped_column(String(120), index=True)
    raw_param_name: Mapped[str | None] = mapped_column(String(160))
    raw_param_value: Mapped[str | None] = mapped_column(Text)
    raw_unit: Mapped[str | None] = mapped_column(String(60))
    source_channel: Mapped[str | None] = mapped_column(String(80))
    observed_at: Mapped[str | None] = mapped_column(String(80))


class RawSkuClaim(Base, RawBaseMixin):
    __tablename__ = "raw_sku_claim"

    sku_code: Mapped[str | None] = mapped_column(String(120), index=True)
    claim_title: Mapped[str | None] = mapped_column(String(160))
    claim_text: Mapped[str | None] = mapped_column(Text)
    claim_order: Mapped[int | None] = mapped_column(Integer)
    source_channel: Mapped[str | None] = mapped_column(String(80))
    observed_at: Mapped[str | None] = mapped_column(String(80))


class RawSkuComment(Base, RawBaseMixin):
    __tablename__ = "raw_sku_comment"

    sku_code: Mapped[str | None] = mapped_column(String(120), index=True)
    platform: Mapped[str | None] = mapped_column(String(80))
    comment_id: Mapped[str | None] = mapped_column(String(120))
    comment_text: Mapped[str | None] = mapped_column(Text)
    rating: Mapped[float | None] = mapped_column(Float)
    comment_time: Mapped[str | None] = mapped_column(String(80))
    dimension_1: Mapped[str | None] = mapped_column(String(120))
    dimension_2: Mapped[str | None] = mapped_column(String(120))
    dimension_3: Mapped[str | None] = mapped_column(String(120))


class RawMarketFact(Base, RawBaseMixin):
    __tablename__ = "raw_market_fact"

    sku_code: Mapped[str | None] = mapped_column(String(120), index=True)
    period: Mapped[str | None] = mapped_column(String(80))
    period_type: Mapped[str | None] = mapped_column(String(40))
    channel_group: Mapped[str | None] = mapped_column(String(80))
    channel_type: Mapped[str | None] = mapped_column(String(120))
    channel_name: Mapped[str | None] = mapped_column(String(120))
    sales_volume: Mapped[float | None] = mapped_column(Float)
    sales_amount: Mapped[float | None] = mapped_column(Float)
    avg_price: Mapped[float | None] = mapped_column(Float)
    promotion_flag: Mapped[bool | None] = mapped_column(Boolean)


class DataQualityIssue(Base, AuditMixin):
    __tablename__ = "data_quality_issue"

    issue_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    source_file_id: Mapped[str | None] = mapped_column(String(36), index=True)
    import_batch_id: Mapped[str | None] = mapped_column(String(36), index=True)
    raw_row_id: Mapped[str | None] = mapped_column(String(80))
    table_name: Mapped[str] = mapped_column(String(80), nullable=False)
    field_name: Mapped[str | None] = mapped_column(String(120))
    issue_code: Mapped[str] = mapped_column(String(80), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), nullable=False, default="warning")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[dict | list | None] = mapped_column(JSON)


class EvidenceItem(Base, AuditMixin):
    __tablename__ = "evidence_item"

    evidence_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    sku_code: Mapped[str | None] = mapped_column(String(120), index=True)
    source_type: Mapped[str] = mapped_column(String(60), nullable=False)
    source_file_id: Mapped[str | None] = mapped_column(String(36))
    raw_row_id: Mapped[str | None] = mapped_column(String(80))
    field_name: Mapped[str | None] = mapped_column(String(160))
    raw_value: Mapped[str | None] = mapped_column(Text)
    normalized_value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSON)
    source_ref: Mapped[dict | list | None] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)


class RuleSet(Base, AuditMixin):
    __tablename__ = "rule_set"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    rule_set_id: Mapped[str] = mapped_column(String(160), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    rule_type: Mapped[str | None] = mapped_column(String(80), index=True)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft")
    source_format: Mapped[str] = mapped_column(String(40), nullable=False, default="yaml")
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    validation_errors: Mapped[list] = mapped_column(JSON, default=list)


class StdParamDef(Base, AuditMixin):
    __tablename__ = "std_param_def"

    param_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    param_code: Mapped[str] = mapped_column(String(120), index=True)
    param_name: Mapped[str] = mapped_column(String(160), nullable=False)
    param_group: Mapped[str] = mapped_column(String(80), nullable=False)
    data_type: Mapped[str] = mapped_column(String(40), nullable=False)
    unit: Mapped[str | None] = mapped_column(String(40))
    raw_aliases: Mapped[list] = mapped_column(JSON, default=list)
    normalize_rule: Mapped[dict] = mapped_column(JSON, default=dict)
    level_rule: Mapped[dict | None] = mapped_column(JSON)
    business_meaning: Mapped[str | None] = mapped_column(Text)
    mapped_claim_codes: Mapped[list] = mapped_column(JSON, default=list)
    evidence_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="candidate")
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")


class StdClaimDef(Base, AuditMixin):
    __tablename__ = "std_claim_def"

    claim_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    claim_code: Mapped[str] = mapped_column(String(140), index=True)
    claim_name: Mapped[str] = mapped_column(String(160), nullable=False)
    claim_group: Mapped[str] = mapped_column(String(80), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    activation_rule: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_keywords: Mapped[list] = mapped_column(JSON, default=list)
    supporting_param_codes: Mapped[list] = mapped_column(JSON, default=list)
    comment_topic_codes: Mapped[list] = mapped_column(JSON, default=list)
    mapped_task_codes: Mapped[list] = mapped_column(JSON, default=list)
    mapped_battlefield_codes: Mapped[list] = mapped_column(JSON, default=list)
    default_layer_hint: Mapped[str | None] = mapped_column(String(80))
    confidence_rule: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="candidate")
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")


class CommentTopicDef(Base, AuditMixin):
    __tablename__ = "comment_topic_def"

    topic_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    topic_code: Mapped[str] = mapped_column(String(140), index=True)
    topic_name: Mapped[str] = mapped_column(String(160), nullable=False)
    topic_group: Mapped[str] = mapped_column(String(80), nullable=False)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    sentiment_hint: Mapped[str | None] = mapped_column(String(40))
    mapped_claim_codes: Mapped[list] = mapped_column(JSON, default=list)
    mapped_task_codes: Mapped[list] = mapped_column(JSON, default=list)
    activates_product_claim: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="candidate")
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")


class UserTaskDef(Base, AuditMixin):
    __tablename__ = "user_task_def"

    task_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    task_code: Mapped[str] = mapped_column(String(140), index=True)
    task_name: Mapped[str] = mapped_column(String(160), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    positive_claim_codes: Mapped[list] = mapped_column(JSON, default=list)
    positive_param_codes: Mapped[list] = mapped_column(JSON, default=list)
    comment_topic_codes: Mapped[list] = mapped_column(JSON, default=list)
    default_target_group_codes: Mapped[list] = mapped_column(JSON, default=list)
    battlefield_codes: Mapped[list] = mapped_column(JSON, default=list)
    score_rule: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="candidate")
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")


class TargetGroupDef(Base, AuditMixin):
    __tablename__ = "target_group_def"

    target_group_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    target_group_code: Mapped[str] = mapped_column(String(140), index=True)
    target_group_name: Mapped[str] = mapped_column(String(160), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="candidate")
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")


class BattlefieldDef(Base, AuditMixin):
    __tablename__ = "battlefield_def"

    battlefield_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    battlefield_code: Mapped[str] = mapped_column(String(140), index=True)
    battlefield_name: Mapped[str] = mapped_column(String(160), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    required_signal_rule: Mapped[dict | None] = mapped_column(JSON)
    score_rule: Mapped[dict] = mapped_column(JSON, default=dict)
    entry_thresholds: Mapped[dict] = mapped_column(JSON, default=dict)
    competitor_rule_ref: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="candidate")
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")


class SkuParamNormalized(Base, AuditMixin):
    __tablename__ = "sku_param_normalized"

    result_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    sku_code: Mapped[str] = mapped_column(String(120), index=True)
    param_code: Mapped[str] = mapped_column(String(140), index=True)
    normalized_value: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_numeric: Mapped[float | None] = mapped_column(Float)
    normalized_bool: Mapped[bool | None] = mapped_column(Boolean)
    unit: Mapped[str | None] = mapped_column(String(40))
    raw_value: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    review_status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="candidate")
    rule_version: Mapped[str] = mapped_column(String(40), nullable=False, default="1.0.0")
    asset_version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")


class SkuClaimResult(Base, AuditMixin):
    __tablename__ = "sku_claim_result"

    result_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    sku_code: Mapped[str] = mapped_column(String(120), index=True)
    claim_code: Mapped[str] = mapped_column(String(140), index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    activation_source: Mapped[str] = mapped_column(String(80), nullable=False, default="rule")
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    extracted_values: Mapped[dict] = mapped_column(JSON, default=dict)
    review_status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="candidate")
    rule_version: Mapped[str] = mapped_column(String(40), nullable=False, default="1.0.0")
    asset_version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")


class SkuCommentTopicResult(Base, AuditMixin):
    __tablename__ = "sku_comment_topic_result"

    result_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    sku_code: Mapped[str] = mapped_column(String(120), index=True)
    topic_code: Mapped[str] = mapped_column(String(140), index=True)
    sentiment: Mapped[str] = mapped_column(String(40), nullable=False, default="neutral")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.75)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    activates_product_claim: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    review_status: Mapped[str] = mapped_column(String(40), nullable=False, default="auto_pass")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="candidate")
    rule_version: Mapped[str] = mapped_column(String(40), nullable=False, default="1.0.0")
    asset_version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")


class SkuTaskScore(Base, AuditMixin):
    __tablename__ = "sku_task_score"

    score_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    sku_code: Mapped[str] = mapped_column(String(120), index=True)
    task_code: Mapped[str] = mapped_column(String(140), index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    relation_level: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.75)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    reason: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="candidate")
    rule_version: Mapped[str] = mapped_column(String(40), nullable=False, default="1.0.0")
    asset_version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")


class SkuBattlefieldScore(Base, AuditMixin):
    __tablename__ = "sku_battlefield_score"

    score_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    sku_code: Mapped[str] = mapped_column(String(120), index=True)
    battlefield_code: Mapped[str] = mapped_column(String(140), index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    relation_level: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.75)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    reason: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="candidate")
    rule_version: Mapped[str] = mapped_column(String(40), nullable=False, default="1.0.0")
    asset_version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")


class AnalysisRun(Base, AuditMixin):
    __tablename__ = "analysis_run"

    analysis_run_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="completed")
    target_sku_code: Mapped[str | None] = mapped_column(String(120), index=True)
    fixture_path: Mapped[str | None] = mapped_column(Text)
    rule_versions: Mapped[dict] = mapped_column(JSON, default=dict)
    asset_version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")
    counts: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)


class SkuCompetitorResult(Base, AuditMixin):
    __tablename__ = "sku_competitor_result"

    result_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    target_sku_code: Mapped[str] = mapped_column(String(120), index=True)
    competitor_sku_code: Mapped[str] = mapped_column(String(120), index=True)
    battlefield_code: Mapped[str | None] = mapped_column(String(140), index=True)
    competitor_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    component_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    evidence_card: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    rule_version: Mapped[str] = mapped_column(String(40), nullable=False, default="1.0.0")
    asset_version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")
    review_status: Mapped[str] = mapped_column(String(40), nullable=False, default="auto_pass")
    insufficient_reasons: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="candidate")


class GoldLabel(Base, AuditMixin):
    __tablename__ = "gold_label"

    label_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    label_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    target_sku_code: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    candidate_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    expected_label: Mapped[str] = mapped_column(String(80), nullable=False)
    expected_score_class: Mapped[str | None] = mapped_column(String(60))
    expert_id: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    asset_version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")


class EvaluationRun(Base, AuditMixin):
    __tablename__ = "evaluation_run"

    evaluation_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="completed")
    gold_label_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    report: Mapped[dict] = mapped_column(JSON, default=dict)
    rule_versions: Mapped[dict] = mapped_column(JSON, default=dict)
    asset_version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")


class CalibrationRun(Base, AuditMixin):
    __tablename__ = "calibration_run"

    calibration_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft_candidate")
    target_metric: Mapped[str] = mapped_column(String(80), nullable=False, default="macro_f1")
    before_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    after_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    candidate_rule_patch: Mapped[dict] = mapped_column(JSON, default=dict)
    rule_versions: Mapped[dict] = mapped_column(JSON, default=dict)
    asset_version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")


class JobRun(Base, AuditMixin):
    __tablename__ = "job_run"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "job_type",
            "idempotency_key",
            "input_fingerprint",
            name="uq_job_run_idempotency",
        ),
    )

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="queued", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    checkpoint_json: Mapped[dict] = mapped_column(JSON, default=dict)
    result_ref: Mapped[dict | None] = mapped_column(JSON)
    diagnostics_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(Text)
    lock_key: Mapped[str | None] = mapped_column(String(240), index=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False, default="system")
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class JobAttempt(Base, AuditMixin):
    __tablename__ = "job_attempt"

    attempt_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("job_run.job_id"), index=True)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    worker_id: Mapped[str] = mapped_column(String(120), nullable=False, default="local-sync")
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="running")
    error_code: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_after_seconds: Mapped[int | None] = mapped_column(Integer)
    diagnostics_json: Mapped[dict] = mapped_column(JSON, default=dict)


class AssetVersion(Base, AuditMixin):
    __tablename__ = "asset_version"

    asset_version_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    asset_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    version: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    lifecycle_status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    content_hash: Mapped[str] = mapped_column(String(120), nullable=False)
    manifest_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False, default="system")
    approved_by: Mapped[str | None] = mapped_column(String(120))
    released_at: Mapped[datetime | None] = mapped_column(DateTime)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime)
    rollback_from_version_id: Mapped[str | None] = mapped_column(String(36), index=True)
    rollback_reason: Mapped[str | None] = mapped_column(Text)


class AssetDiff(Base, AuditMixin):
    __tablename__ = "asset_diff"

    diff_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    from_version: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    to_version: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    diff_json: Mapped[dict] = mapped_column(JSON, default=dict)


class AuditEvent(Base):
    __tablename__ = "audit_event"

    audit_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    actor_id: Mapped[str] = mapped_column(String(120), nullable=False, default="system")
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    object_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    object_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(String(36), index=True)
    before_hash: Mapped[str | None] = mapped_column(String(120))
    after_hash: Mapped[str | None] = mapped_column(String(120))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, nullable=False)


class RuntimeExport(Base, AuditMixin):
    __tablename__ = "runtime_export"

    export_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    asset_version_id: Mapped[str] = mapped_column(ForeignKey("asset_version.asset_version_id"), index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="completed")
    manifest_json: Mapped[dict] = mapped_column(JSON, default=dict)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(120), nullable=False)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False, default="system")


class ClaimValueLayerResult(Base, AuditMixin):
    __tablename__ = "claim_value_layer_result"

    result_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    claim_code: Mapped[str] = mapped_column(String(140), index=True)
    coverage_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    psi: Mapped[float | None] = mapped_column(Float)
    ssi: Mapped[float | None] = mapped_column(Float)
    cpi: Mapped[float | None] = mapped_column(Float)
    comparable_sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    layer: Mapped[str] = mapped_column(String(80), nullable=False, default="pending_validation")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="candidate")
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")


class ReviewQueue(Base, AuditMixin):
    __tablename__ = "review_queue"

    review_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    item_type: Mapped[str] = mapped_column(String(60), nullable=False)
    item_key: Mapped[str] = mapped_column(String(180), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    candidate_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    priority: Mapped[str] = mapped_column(String(40), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    reviewer: Mapped[str | None] = mapped_column(String(120))
    decision_payload: Mapped[dict | None] = mapped_column(JSON)


class AssetPackage(Base, AuditMixin):
    __tablename__ = "asset_package"

    package_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="exported")
    file_list: Mapped[list] = mapped_column(JSON, default=list)
    package_path: Mapped[str] = mapped_column(Text, nullable=False)
    package_metadata: Mapped[dict] = mapped_column(JSON, default=dict)
