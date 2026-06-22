from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

JSONBCompat = JSON().with_variant(JSONB, "postgresql")


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
    evidence: Mapped[dict | list | None] = mapped_column(JSONBCompat)


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
    normalized_value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSONBCompat)
    source_ref: Mapped[dict | list | None] = mapped_column(JSONBCompat)
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
    content: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    validation_errors: Mapped[list] = mapped_column(JSONBCompat, default=list)


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
    raw_aliases: Mapped[list] = mapped_column(JSONBCompat, default=list)
    normalize_rule: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    level_rule: Mapped[dict | None] = mapped_column(JSONBCompat)
    business_meaning: Mapped[str | None] = mapped_column(Text)
    mapped_claim_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
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
    activation_rule: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    raw_keywords: Mapped[list] = mapped_column(JSONBCompat, default=list)
    supporting_param_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    comment_topic_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    mapped_task_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    mapped_battlefield_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    default_layer_hint: Mapped[str | None] = mapped_column(String(80))
    confidence_rule: Mapped[dict | None] = mapped_column(JSONBCompat)
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
    keywords: Mapped[list] = mapped_column(JSONBCompat, default=list)
    sentiment_hint: Mapped[str | None] = mapped_column(String(40))
    mapped_claim_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    mapped_task_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
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
    positive_claim_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    positive_param_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    comment_topic_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    default_target_group_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    battlefield_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    score_rule: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
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
    required_signal_rule: Mapped[dict | None] = mapped_column(JSONBCompat)
    score_rule: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    entry_thresholds: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
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
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
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
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    extracted_values: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
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
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
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
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
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
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
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
    rule_versions: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    asset_version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")
    counts: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)


class Core3PipelineRun(Base, AuditMixin):
    __tablename__ = "core3_pipeline_run"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "scope",
            "target_sku_code",
            "input_fingerprint",
            name="uq_core3_pipeline_run_input",
        ),
    )

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="created")
    scope: Mapped[str] = mapped_column(String(40), nullable=False)
    target_sku_code: Mapped[str | None] = mapped_column(String(120), index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="core3-mvp-0.1.0")
    counts: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    warnings: Mapped[list] = mapped_column(JSONBCompat, default=list)
    diagnostics: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class Core3SkuMarketProfile(Base, AuditMixin):
    __tablename__ = "core3_sku_market_profile"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "analysis_window",
            "rule_version",
            name="uq_core3_market_profile_key",
        ),
        CheckConstraint("market_confidence >= 0 and market_confidence <= 1", name="ck_m07_profile_confidence"),
        Index("ix_core3_m07_profile_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m07_profile_sku_window", "sku_code", "analysis_window"),
        Index("ix_core3_m07_profile_window_size", "analysis_window", "size_segment"),
        Index("ix_core3_m07_profile_price_band_category", "price_band_category"),
        Index("ix_core3_m07_profile_price_band_size", "price_band_size"),
        Index("ix_core3_m07_profile_sample_status", "sample_status"),
        Index("ix_core3_m07_profile_confidence", "market_confidence"),
        Index("ix_core3_m07_profile_review", "review_required"),
        Index("ix_core3_m07_profile_channel_share_gin", "channel_share_json", postgresql_using="gin"),
        Index("ix_core3_m07_profile_platform_share_gin", "platform_share_json", postgresql_using="gin"),
        Index("ix_core3_m07_profile_quality_gin", "quality_flags", postgresql_using="gin"),
        Index("ix_core3_m07_profile_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    profile_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    sku_market_profile_id: Mapped[str | None] = mapped_column(String(120), unique=True, index=True)
    run_id: Mapped[str | None] = mapped_column(String(120), index=True)
    module_run_id: Mapped[str | None] = mapped_column(String(120), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str | None] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), index=True)
    brand: Mapped[str | None] = mapped_column(String(120))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    model_name: Mapped[str | None] = mapped_column(String(160))
    series: Mapped[str | None] = mapped_column(String(120))
    category_name: Mapped[str | None] = mapped_column(String(160))
    profile_key: Mapped[str | None] = mapped_column(String(420), index=True)
    analysis_window: Mapped[str] = mapped_column(String(60), nullable=False, default="legacy", index=True)
    period_start_raw: Mapped[str | None] = mapped_column(String(80))
    period_end_raw: Mapped[str | None] = mapped_column(String(80))
    period_start_week_index: Mapped[int | None] = mapped_column(Integer)
    period_end_week_index: Mapped[int | None] = mapped_column(Integer)
    global_latest_week_index: Mapped[int | None] = mapped_column(Integer)
    sku_latest_week_index: Mapped[int | None] = mapped_column(Integer)
    latest_week_gap: Mapped[int | None] = mapped_column(Integer)
    active_week_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    market_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    platform_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    screen_size_inch: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    size_segment: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    screen_size_class: Mapped[str] = mapped_column(String(60), nullable=False, default="unknown", index=True)
    market_pool_key: Mapped[str | None] = mapped_column(String(220), index=True)
    size_param_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    sales_volume_total: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    sales_amount_total: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    price_wavg: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    price_wavg_12m: Mapped[float | None] = mapped_column(Float)
    price_latest: Mapped[float | None] = mapped_column(Float)
    price_median: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    price_min: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    price_max: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    price_per_inch: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    sales_volume_12m: Mapped[float | None] = mapped_column(Float)
    sales_amount_12m: Mapped[float | None] = mapped_column(Float)
    main_channel_type: Mapped[str | None] = mapped_column(String(80), index=True)
    main_platform: Mapped[str | None] = mapped_column(String(80), index=True)
    channel_share: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    channel_share_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    platform_share_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    price_change_recent_4w: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    sales_growth_recent_4w: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    amount_growth_recent_4w: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    price_volatility: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    sales_volatility: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    promotion_suspect_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    price_drop_rate_3m: Mapped[float | None] = mapped_column(Float)
    sales_growth_3m: Mapped[float | None] = mapped_column(Float)
    price_band_category: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    price_band_size: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    price_band_method: Mapped[str] = mapped_column(String(80), nullable=False, default="legacy")
    price_percentile: Mapped[float | None] = mapped_column(Float)
    sales_percentile: Mapped[float | None] = mapped_column(Float)
    sales_amount_percentile: Mapped[float | None] = mapped_column(Float)
    price_percentile_in_category: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    volume_percentile_in_category: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    amount_percentile_in_category: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    price_percentile_in_size: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    volume_percentile_in_size: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    amount_percentile_in_size: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    same_pool_price_percentile: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    same_pool_volume_percentile: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    same_pool_amount_percentile: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    price_per_inch_percentile: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    same_pool_sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    price_gap_to_category_median: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    price_gap_to_size_median: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    volume_gap_to_size_median: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    amount_gap_to_size_median: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    market_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    confidence_level: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    sample_status: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    market_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    param_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    missing_signals: Mapped[list] = mapped_column(JSONBCompat, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="legacy")
    price_band_rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="legacy")
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, default="legacy", index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, default="legacy", index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SkuFeatureProfile(Base, AuditMixin):
    __tablename__ = "core3_sku_feature_profile"
    __table_args__ = (UniqueConstraint("run_id", "sku_code", name="uq_core3_feature_profile_run_sku"),)

    feature_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("core3_pipeline_run.run_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    sku_code: Mapped[str] = mapped_column(String(120), index=True)
    standard_params: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    claim_activations: Mapped[list] = mapped_column(JSONBCompat, default=list)
    comment_topics: Mapped[list] = mapped_column(JSONBCompat, default=list)
    task_scores: Mapped[list] = mapped_column(JSONBCompat, default=list)
    target_group_scores: Mapped[list] = mapped_column(JSONBCompat, default=list)
    battlefield_scores: Mapped[list] = mapped_column(JSONBCompat, default=list)
    feature_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    extraction_diagnostics: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    missing_signals: Mapped[list] = mapped_column(JSONBCompat, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class Core3CompetitorCandidate(Base, AuditMixin):
    __tablename__ = "core3_competitor_candidate"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "target_sku_code",
            "candidate_sku_code",
            name="uq_core3_competitor_candidate_run_target_candidate",
        ),
    )

    candidate_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("core3_pipeline_run.run_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    target_sku_code: Mapped[str] = mapped_column(String(120), index=True)
    candidate_sku_code: Mapped[str] = mapped_column(String(120), index=True)
    battlefield_code: Mapped[str | None] = mapped_column(String(140), index=True)
    gate_status: Mapped[str] = mapped_column(String(40), nullable=False)
    gate_reasons: Mapped[list] = mapped_column(JSONBCompat, default=list)
    component_scores: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    slot_scores: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class Core3CompetitorResult(Base, AuditMixin):
    __tablename__ = "core3_competitor_result"
    __table_args__ = (
        UniqueConstraint("run_id", "target_sku_code", "role", name="uq_core3_competitor_result_run_role"),
    )

    result_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("core3_pipeline_run.run_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    target_sku_code: Mapped[str] = mapped_column(String(120), index=True)
    role: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    competitor_sku_code: Mapped[str | None] = mapped_column(String(120), index=True)
    battlefield_code: Mapped[str | None] = mapped_column(String(140), index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    component_scores: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    reason: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence_level: Mapped[str] = mapped_column(String(20), nullable=False, default="low")
    review_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    insufficient_reasons: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_card: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="core3-mvp-0.1.0")
    asset_version: Mapped[str] = mapped_column(String(80), nullable=False, default="core3-mvp-0.1.0")


class Core3EvidenceCard(Base, AuditMixin):
    __tablename__ = "core3_evidence_card"
    __table_args__ = (
        UniqueConstraint("run_id", "target_sku_code", "role", name="uq_core3_evidence_card_run_role"),
    )

    card_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    result_id: Mapped[str | None] = mapped_column(ForeignKey("core3_competitor_result.result_id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("core3_pipeline_run.run_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    target_sku_code: Mapped[str] = mapped_column(String(120), index=True)
    competitor_sku_code: Mapped[str | None] = mapped_column(String(120), index=True)
    role: Mapped[str] = mapped_column(String(60), nullable=False)
    evidence_categories: Mapped[list] = mapped_column(JSONBCompat, default=list)
    card_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)


class Core3V2PipelineRun(Base, AuditMixin):
    __tablename__ = "core3_v2_pipeline_run"

    run_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    parent_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("core3_v2_pipeline_run.run_id"), index=True
    )
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    run_mode: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    trigger_type: Mapped[str] = mapped_column(String(80), nullable=False, default="manual")
    triggered_by: Mapped[str] = mapped_column(String(120), nullable=False, default="system")
    data_batch_id: Mapped[str | None] = mapped_column(String(120), index=True)
    target_scope_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    ruleset_version: Mapped[str] = mapped_column(String(120), nullable=False)
    module_version_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    seed_version_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    input_watermark_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    status: Mapped[str] = mapped_column(String(60), nullable=False, default="pending", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    output_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    quality_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    release_status: Mapped[str] = mapped_column(String(60), nullable=False, default="not_ready", index=True)
    error_code: Mapped[str | None] = mapped_column(String(120))
    error_message_cn: Mapped[str | None] = mapped_column(Text)


class Core3V2ModuleRun(Base, AuditMixin):
    __tablename__ = "core3_v2_module_run"

    module_run_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    module_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    target_scope: Mapped[str] = mapped_column(String(80), nullable=False, default="project")
    target_id: Mapped[str | None] = mapped_column(String(160), index=True)
    batch_id: Mapped[str | None] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(60), nullable=False, default="pending", index=True)
    input_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    changed_input_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_hash: Mapped[str | None] = mapped_column(String(120), index=True)
    warnings_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    review_issue_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    downstream_impact_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    error_code: Mapped[str | None] = mapped_column(String(120))
    error_message_cn: Mapped[str | None] = mapped_column(Text)


class Core3V2ModuleDependencySnapshot(Base, AuditMixin):
    __tablename__ = "core3_v2_module_dependency_snapshot"

    dependency_snapshot_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    module_run_id: Mapped[str] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    module_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    upstream_module_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    upstream_target_id: Mapped[str | None] = mapped_column(String(160), index=True)
    upstream_output_hash: Mapped[str | None] = mapped_column(String(120), index=True)
    rule_version: Mapped[str | None] = mapped_column(String(120))
    seed_version_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    dependency_status: Mapped[str] = mapped_column(String(60), nullable=False, default="current", index=True)
    reused_from_module_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("core3_v2_module_run.module_run_id"), index=True
    )


class Core3V2PipelineWatermark(Base, AuditMixin):
    __tablename__ = "core3_v2_pipeline_watermark"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "watermark_scope",
            "source_table",
            "module_code",
            "target_id",
            name="uq_core3_v2_pipeline_watermark_scope",
        ),
    )

    watermark_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    watermark_scope: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_table: Mapped[str | None] = mapped_column(String(120), index=True)
    module_code: Mapped[str | None] = mapped_column(String(40), index=True)
    target_id: Mapped[str | None] = mapped_column(String(160), index=True)
    last_source_pk: Mapped[str | None] = mapped_column(String(180))
    last_write_time: Mapped[datetime | None] = mapped_column(DateTime)
    last_row_hash_snapshot: Mapped[str | None] = mapped_column(String(120))
    watermark_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    updated_by: Mapped[str] = mapped_column(String(120), nullable=False, default="system")


class Core3SourceBatch(Base, AuditMixin):
    __tablename__ = "core3_source_batch"
    __table_args__ = (
        Index("ix_core3_source_batch_project_category_created", "project_id", "category_code", "created_at"),
        Index("ix_core3_source_batch_project_category_status", "project_id", "category_code", "status"),
    )

    batch_id: Mapped[str] = mapped_column(String(80), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("core3_v2_module_run.module_run_id"), index=True
    )
    batch_type: Mapped[str] = mapped_column(String(40), nullable=False, default="full")
    source_system: Mapped[str] = mapped_column(String(120), nullable=False)
    source_database: Mapped[str] = mapped_column(String(120), nullable=False)
    source_schema: Mapped[str | None] = mapped_column(String(120), default="public")
    source_tables: Mapped[list] = mapped_column(JSONBCompat, default=list)
    ruleset_version: Mapped[str] = mapped_column(String(120), nullable=False)
    module_version: Mapped[str] = mapped_column(String(120), nullable=False)
    hash_version: Mapped[str] = mapped_column(String(80), nullable=False)
    scan_started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    scan_finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    input_watermark_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    row_counts_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    write_time_range_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    source_pk_range_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    schema_snapshot_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    impacted_sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    affected_module_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    quality_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    status: Mapped[str] = mapped_column(String(60), nullable=False, default="running", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason: Mapped[dict | None] = mapped_column(JSONBCompat)
    error_code: Mapped[str | None] = mapped_column(String(120))
    error_message: Mapped[str | None] = mapped_column(Text)


class Core3SourceRowRegistry(Base):
    __tablename__ = "core3_source_row_registry"
    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "source_table",
            "source_pk",
            name="uq_core3_source_row_registry_batch_table_pk",
        ),
        Index(
            "ix_core3_source_row_registry_project_category_batch",
            "project_id",
            "category_code",
            "batch_id",
        ),
    )

    row_registry_id: Mapped[str] = mapped_column(String(80), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    source_table: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    source_pk: Mapped[str | None] = mapped_column(String(180), index=True)
    source_pk_strategy: Mapped[str] = mapped_column(String(80), nullable=False, default="id_column")
    source_row_id: Mapped[str | None] = mapped_column(String(240), index=True)
    row_hash: Mapped[str | None] = mapped_column(String(120), index=True)
    hash_version: Mapped[str] = mapped_column(String(80), nullable=False)
    previous_batch_id: Mapped[str | None] = mapped_column(String(80), index=True)
    previous_row_hash: Mapped[str | None] = mapped_column(String(120))
    previous_operation_type: Mapped[str | None] = mapped_column(String(80))
    sku_code_candidate: Mapped[str | None] = mapped_column(String(160), index=True)
    model_name_raw: Mapped[str | None] = mapped_column(String(240))
    brand_raw: Mapped[str | None] = mapped_column(String(160))
    category_raw: Mapped[str | None] = mapped_column(String(160))
    write_time: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    business_key_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    source_field_presence_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    operation_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    change_reason: Mapped[str | None] = mapped_column(Text)
    affected_modules: Mapped[list] = mapped_column(JSONBCompat, default=list)
    quality_hint: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, nullable=False)


class Core3SourceImpactedSku(Base):
    __tablename__ = "core3_source_impacted_sku"
    __table_args__ = (
        UniqueConstraint("batch_id", "sku_code_candidate", name="uq_core3_source_impacted_sku_batch_sku"),
        Index(
            "ix_core3_source_impacted_sku_project_category_batch",
            "project_id",
            "category_code",
            "batch_id",
        ),
    )

    impacted_sku_id: Mapped[str] = mapped_column(String(80), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    sku_code_candidate: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name_raw: Mapped[str | None] = mapped_column(String(240))
    brand_raw: Mapped[str | None] = mapped_column(String(160))
    source_tables: Mapped[list] = mapped_column(JSONBCompat, default=list)
    operation_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    affected_modules: Mapped[list] = mapped_column(JSONBCompat, default=list)
    impact_reason: Mapped[str] = mapped_column(Text, nullable=False)
    impact_level: Mapped[str] = mapped_column(String(40), nullable=False, default="medium")
    needs_recompute: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason: Mapped[dict | None] = mapped_column(JSONBCompat)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, nullable=False)


class Core3CleanSku(Base, AuditMixin):
    __tablename__ = "core3_clean_sku"
    __table_args__ = (
        UniqueConstraint("batch_id", "sku_code", name="uq_core3_clean_sku_batch_sku"),
        Index("ix_core3_clean_sku_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_clean_sku_sku_code", "sku_code"),
        Index("ix_core3_clean_sku_quality_status", "quality_status"),
    )

    clean_sku_id: Mapped[str] = mapped_column(String(80), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False)
    sku_code_raw_values: Mapped[list] = mapped_column(JSONBCompat, default=list)
    model_name: Mapped[str | None] = mapped_column(String(240))
    model_name_raw_values: Mapped[list] = mapped_column(JSONBCompat, default=list)
    brand_name: Mapped[str | None] = mapped_column(String(160))
    brand_raw_values: Mapped[list] = mapped_column(JSONBCompat, default=list)
    category_name: Mapped[str | None] = mapped_column(String(160))
    source_tables: Mapped[list] = mapped_column(JSONBCompat, default=list)
    first_seen_source_row_id: Mapped[str | None] = mapped_column(String(240), index=True)
    representative_source_row_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    coverage_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    field_conflicts_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    missing_signals_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    clean_record_key: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    clean_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    clean_version: Mapped[str] = mapped_column(String(80), nullable=False)
    hash_version: Mapped[str] = mapped_column(String(80), nullable=False)
    quality_status: Mapped[str] = mapped_column(String(40), nullable=False, default="ok")
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)


class Core3CleanMarketWeekly(Base, AuditMixin):
    __tablename__ = "core3_clean_market_weekly"
    __table_args__ = (
        UniqueConstraint("batch_id", "source_row_id", name="uq_core3_clean_market_batch_source_row"),
        Index("ix_core3_clean_market_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_clean_market_sku_period", "sku_code", "period_raw"),
        Index("ix_core3_clean_market_channel_platform", "channel_type", "platform_type"),
        Index("ix_core3_clean_market_price_check_status", "price_check_status"),
        Index("ix_core3_clean_market_clean_hash", "clean_hash"),
    )

    clean_market_id: Mapped[str] = mapped_column(String(80), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    source_table: Mapped[str] = mapped_column(String(120), nullable=False, default="week_sales_data", index=True)
    source_pk: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    source_row_id: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    source_row_hash: Mapped[str | None] = mapped_column(String(120), index=True)
    source_operation_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    sku_code: Mapped[str | None] = mapped_column(String(160), index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    category_name_raw: Mapped[str | None] = mapped_column(String(160))
    period_raw: Mapped[str | None] = mapped_column(String(80), index=True)
    period_type: Mapped[str | None] = mapped_column(String(40), index=True)
    period_year_hint: Mapped[int | None] = mapped_column(Integer)
    period_week_index: Mapped[int | None] = mapped_column(Integer)
    period_parse_status: Mapped[str] = mapped_column(String(40), nullable=False, default="failed", index=True)
    channel_raw: Mapped[str | None] = mapped_column(String(160))
    channel_type: Mapped[str | None] = mapped_column(String(80), index=True)
    platform_raw: Mapped[str | None] = mapped_column(String(160))
    platform_type: Mapped[str | None] = mapped_column(String(80), index=True)
    sales_volume_raw: Mapped[str | None] = mapped_column(String(120))
    sales_volume: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    sales_amount_raw: Mapped[str | None] = mapped_column(String(120))
    sales_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    avg_price_raw: Mapped[str | None] = mapped_column(String(120))
    avg_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    avg_price_expected: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    price_check_status: Mapped[str] = mapped_column(String(40), nullable=False, default="uncheckable", index=True)
    price_check_delta: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    clean_record_key: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    clean_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    clean_version: Mapped[str] = mapped_column(String(80), nullable=False)
    hash_version: Mapped[str] = mapped_column(String(80), nullable=False)
    record_status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    quality_status: Mapped[str] = mapped_column(String(40), nullable=False, default="ok", index=True)
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)


class Core3CleanAttribute(Base, AuditMixin):
    __tablename__ = "core3_clean_attribute"
    __table_args__ = (
        UniqueConstraint("batch_id", "source_row_id", name="uq_core3_clean_attribute_batch_source_row"),
        Index("ix_core3_clean_attribute_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_clean_attribute_sku_attr", "sku_code", "clean_attr_name"),
        Index("ix_core3_clean_attribute_value_presence", "value_presence"),
        Index("ix_core3_clean_attribute_conflict_group", "conflict_group_key"),
    )

    clean_attribute_id: Mapped[str] = mapped_column(String(80), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    source_table: Mapped[str] = mapped_column(String(120), nullable=False, default="attribute_data", index=True)
    source_pk: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    source_row_id: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    source_row_hash: Mapped[str | None] = mapped_column(String(120), index=True)
    source_operation_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    sku_code: Mapped[str | None] = mapped_column(String(160), index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    raw_attr_name: Mapped[str | None] = mapped_column(String(240))
    clean_attr_name: Mapped[str | None] = mapped_column(String(240), index=True)
    raw_attr_value: Mapped[str | None] = mapped_column(Text)
    clean_attr_value: Mapped[str | None] = mapped_column(Text)
    value_presence: Mapped[str] = mapped_column(String(40), nullable=False, default="missing_column")
    value_number_candidates: Mapped[list] = mapped_column(JSONBCompat, default=list)
    value_unit_candidates: Mapped[list] = mapped_column(JSONBCompat, default=list)
    raw_value_token_count: Mapped[int | None] = mapped_column(Integer)
    conflict_group_key: Mapped[str | None] = mapped_column(String(320), index=True)
    clean_record_key: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    clean_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    clean_version: Mapped[str] = mapped_column(String(80), nullable=False)
    hash_version: Mapped[str] = mapped_column(String(80), nullable=False)
    record_status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    quality_status: Mapped[str] = mapped_column(String(40), nullable=False, default="ok", index=True)
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)


class Core3CleanClaim(Base, AuditMixin):
    __tablename__ = "core3_clean_claim"
    __table_args__ = (
        UniqueConstraint("batch_id", "source_row_id", name="uq_core3_clean_claim_batch_source_row"),
        Index("ix_core3_clean_claim_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_clean_claim_sku_seq", "sku_code", "claim_seq"),
        Index("ix_core3_clean_claim_text_presence", "claim_text_presence"),
    )

    clean_claim_id: Mapped[str] = mapped_column(String(80), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    source_table: Mapped[str] = mapped_column(String(120), nullable=False, default="selling_points_data", index=True)
    source_pk: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    source_row_id: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    source_row_hash: Mapped[str | None] = mapped_column(String(120), index=True)
    source_operation_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    sku_code: Mapped[str | None] = mapped_column(String(160), index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    claim_seq_raw: Mapped[str | None] = mapped_column(String(120))
    claim_seq: Mapped[int | None] = mapped_column(Integer, index=True)
    raw_claim_text: Mapped[str | None] = mapped_column(Text)
    clean_claim_text: Mapped[str | None] = mapped_column(Text)
    claim_text_presence: Mapped[str] = mapped_column(String(40), nullable=False, default="missing_column")
    title_hint: Mapped[str | None] = mapped_column(Text)
    structure_hints: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    clean_record_key: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    clean_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    clean_version: Mapped[str] = mapped_column(String(80), nullable=False)
    hash_version: Mapped[str] = mapped_column(String(80), nullable=False)
    record_status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    quality_status: Mapped[str] = mapped_column(String(40), nullable=False, default="ok", index=True)
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)


class Core3CleanClaimSentence(Base):
    __tablename__ = "core3_clean_claim_sentence"
    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "source_row_id",
            "sentence_seq",
            name="uq_core3_clean_claim_sentence_batch_source_seq",
        ),
        Index("ix_core3_clean_claim_sentence_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_clean_claim_sentence_sku_seq", "sku_code", "claim_seq"),
        Index("ix_core3_clean_claim_sentence_text_hash", "sentence_text_hash"),
    )

    claim_sentence_id: Mapped[str] = mapped_column(String(80), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    source_row_id: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    clean_claim_id: Mapped[str] = mapped_column(ForeignKey("core3_clean_claim.clean_claim_id"), index=True)
    sku_code: Mapped[str | None] = mapped_column(String(160), index=True)
    claim_seq: Mapped[int | None] = mapped_column(Integer, index=True)
    sentence_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    sentence_text: Mapped[str] = mapped_column(Text, nullable=False)
    sentence_text_hash: Mapped[str] = mapped_column(String(120), nullable=False)
    sentence_role_hint: Mapped[str | None] = mapped_column(String(80))
    split_rule: Mapped[str] = mapped_column(String(120), nullable=False)
    clean_record_key: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    clean_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    clean_version: Mapped[str] = mapped_column(String(80), nullable=False)
    hash_version: Mapped[str] = mapped_column(String(80), nullable=False)
    quality_status: Mapped[str] = mapped_column(String(40), nullable=False, default="ok", index=True)
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, nullable=False)


class Core3CleanComment(Base, AuditMixin):
    __tablename__ = "core3_clean_comment"
    __table_args__ = (
        UniqueConstraint("batch_id", "source_row_id", name="uq_core3_clean_comment_batch_source_row"),
        Index("ix_core3_clean_comment_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_clean_comment_sku_comment", "sku_code", "comment_id"),
        Index("ix_core3_clean_comment_text_hash", "comment_text_hash"),
        Index("ix_core3_clean_comment_segment_hash", "segment_text_hash"),
        Index("ix_core3_clean_comment_duplicate_group", "duplicate_group_key"),
        Index("ix_core3_clean_comment_sentiment", "sentiment_clean"),
        Index("ix_core3_clean_comment_low_value", "low_value_flag"),
    )

    clean_comment_id: Mapped[str] = mapped_column(String(80), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    source_table: Mapped[str] = mapped_column(String(120), nullable=False, default="comment_data", index=True)
    source_pk: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    source_row_id: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    source_row_hash: Mapped[str | None] = mapped_column(String(120), index=True)
    source_operation_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    sku_code: Mapped[str | None] = mapped_column(String(160), index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    platform_raw: Mapped[str | None] = mapped_column(String(160))
    url_id: Mapped[str | None] = mapped_column(String(240), index=True)
    comment_id: Mapped[str | None] = mapped_column(String(180), index=True)
    comment_time_raw: Mapped[str | None] = mapped_column(String(120))
    comment_time: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    comment_time_parse_status: Mapped[str] = mapped_column(String(40), nullable=False, default="missing", index=True)
    raw_comment_text: Mapped[str | None] = mapped_column(Text)
    clean_comment_text: Mapped[str | None] = mapped_column(Text)
    comment_text_presence: Mapped[str] = mapped_column(String(40), nullable=False, default="missing_column", index=True)
    comment_text_hash: Mapped[str | None] = mapped_column(String(120))
    segment_text_raw: Mapped[str | None] = mapped_column(Text)
    segment_text_clean: Mapped[str | None] = mapped_column(Text)
    segment_text_hash: Mapped[str | None] = mapped_column(String(120), index=True)
    sentiment_raw: Mapped[str | None] = mapped_column(String(120))
    sentiment_clean: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    low_value_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    low_value_reason: Mapped[str | None] = mapped_column(Text)
    duplicate_group_key: Mapped[str | None] = mapped_column(String(240), index=True)
    dimension_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    clean_record_key: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    clean_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    clean_version: Mapped[str] = mapped_column(String(80), nullable=False)
    hash_version: Mapped[str] = mapped_column(String(80), nullable=False)
    record_status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    quality_status: Mapped[str] = mapped_column(String(40), nullable=False, default="ok", index=True)
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)


class Core3CleanCommentSentence(Base):
    __tablename__ = "core3_clean_comment_sentence"
    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "source_row_id",
            "sentence_source",
            "sentence_seq",
            name="uq_core3_clean_comment_sentence_batch_source_seq",
        ),
        Index("ix_core3_clean_comment_sentence_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_clean_comment_sentence_sku_comment", "sku_code", "comment_id"),
        Index("ix_core3_clean_comment_sentence_text_hash", "sentence_text_hash"),
        Index("ix_core3_clean_comment_sentence_source", "sentence_source"),
    )

    comment_sentence_id: Mapped[str] = mapped_column(String(80), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    source_row_id: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    clean_comment_id: Mapped[str] = mapped_column(ForeignKey("core3_clean_comment.clean_comment_id"), index=True)
    sku_code: Mapped[str | None] = mapped_column(String(160), index=True)
    comment_id: Mapped[str | None] = mapped_column(String(180), index=True)
    sentence_source: Mapped[str] = mapped_column(String(80), nullable=False)
    sentence_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    sentence_text: Mapped[str] = mapped_column(Text, nullable=False)
    sentence_text_hash: Mapped[str] = mapped_column(String(120), nullable=False)
    source_segment_text: Mapped[str | None] = mapped_column(Text)
    is_from_existing_segment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    split_rule: Mapped[str] = mapped_column(String(120), nullable=False)
    clean_record_key: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    clean_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    clean_version: Mapped[str] = mapped_column(String(80), nullable=False)
    hash_version: Mapped[str] = mapped_column(String(80), nullable=False)
    quality_status: Mapped[str] = mapped_column(String(40), nullable=False, default="ok", index=True)
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, nullable=False)


class Core3CleanCommentDimension(Base):
    __tablename__ = "core3_clean_comment_dimension"
    __table_args__ = (
        UniqueConstraint("batch_id", "source_row_id", name="uq_core3_clean_comment_dimension_batch_source"),
        Index("ix_core3_clean_comment_dimension_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_clean_comment_dimension_sku_comment", "sku_code", "comment_id"),
        Index("ix_core3_clean_comment_dimension_available", "dimension_available"),
        Index(
            "ix_core3_clean_comment_dimension_path",
            "primary_dim_raw",
            "secondary_dim_raw",
            "third_dim_raw",
        ),
    )

    comment_dimension_id: Mapped[str] = mapped_column(String(80), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    source_row_id: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    clean_comment_id: Mapped[str] = mapped_column(ForeignKey("core3_clean_comment.clean_comment_id"), index=True)
    sku_code: Mapped[str | None] = mapped_column(String(160), index=True)
    comment_id: Mapped[str | None] = mapped_column(String(180), index=True)
    primary_dim_raw: Mapped[str | None] = mapped_column(String(160), index=True)
    secondary_dim_raw: Mapped[str | None] = mapped_column(String(160), index=True)
    third_dim_raw: Mapped[str | None] = mapped_column(String(160), index=True)
    dimension_path_raw: Mapped[str | None] = mapped_column(Text)
    dimension_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dimension_quality_flag: Mapped[str] = mapped_column(String(80), nullable=False, default="missing", index=True)
    clean_record_key: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    clean_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    clean_version: Mapped[str] = mapped_column(String(80), nullable=False)
    hash_version: Mapped[str] = mapped_column(String(80), nullable=False)
    quality_status: Mapped[str] = mapped_column(String(40), nullable=False, default="ok", index=True)
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, nullable=False)


class Core3DataQualityIssue(Base):
    __tablename__ = "core3_data_quality_issue"
    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "domain",
            "issue_type",
            "source_row_id",
            "clean_record_key",
            "sku_code",
            name="uq_core3_data_quality_issue_dedupe",
        ),
        Index("ix_core3_data_quality_issue_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_data_quality_issue_sku", "sku_code"),
        Index("ix_core3_data_quality_issue_domain_type", "domain", "issue_type"),
        Index("ix_core3_data_quality_issue_severity", "severity"),
        Index("ix_core3_data_quality_issue_review_required", "review_required"),
    )

    issue_id: Mapped[str] = mapped_column(String(80), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    module_code: Mapped[str] = mapped_column(String(40), nullable=False, default="M01", index=True)
    domain: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_table: Mapped[str | None] = mapped_column(String(120), index=True)
    source_row_id: Mapped[str | None] = mapped_column(String(240), index=True)
    clean_table: Mapped[str | None] = mapped_column(String(120), index=True)
    clean_record_key: Mapped[str | None] = mapped_column(String(320), index=True)
    sku_code: Mapped[str | None] = mapped_column(String(160), index=True)
    issue_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(40), nullable=False)
    issue_detail: Mapped[str] = mapped_column(Text, nullable=False)
    issue_payload_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    suggested_downstream_action: Mapped[str | None] = mapped_column(Text)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, nullable=False)


class Core3EvidenceAtom(Base, AuditMixin):
    __tablename__ = "core3_evidence_atom"
    __table_args__ = (
        UniqueConstraint(
            "evidence_key",
            "clean_hash",
            "evidence_version",
            name="uq_core3_evidence_atom_key_hash_version",
        ),
        Index("ix_core3_evidence_atom_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_evidence_atom_sku_type", "sku_code", "evidence_type"),
        Index("ix_core3_evidence_atom_source_row", "source_row_id"),
        Index("ix_core3_evidence_atom_clean_record", "clean_table", "clean_record_key"),
        Index("ix_core3_evidence_atom_key_current", "evidence_key", "is_current"),
        Index("ix_core3_evidence_atom_status", "evidence_status"),
        Index("ix_core3_evidence_atom_comment_id", "comment_id"),
        Index("ix_core3_evidence_atom_comment_text_hash", "comment_text_hash"),
        Index("ix_core3_evidence_atom_segment_text_hash", "segment_text_hash"),
    )

    evidence_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    evidence_key: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str | None] = mapped_column(String(160), index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    evidence_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    evidence_grain: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence_field: Mapped[str] = mapped_column(String(160), nullable=False)
    evidence_title: Mapped[str | None] = mapped_column(Text)
    source_table: Mapped[str | None] = mapped_column(String(120), index=True)
    source_pk: Mapped[str | None] = mapped_column(String(180), index=True)
    source_row_id: Mapped[str | None] = mapped_column(String(240), index=True)
    source_row_hash: Mapped[str | None] = mapped_column(String(120), index=True)
    clean_table: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    clean_record_key: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    clean_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    clean_version: Mapped[str] = mapped_column(String(80), nullable=False)
    raw_field: Mapped[str | None] = mapped_column(String(160))
    raw_value: Mapped[str | None] = mapped_column(Text)
    clean_field: Mapped[str | None] = mapped_column(String(160))
    clean_value: Mapped[str | None] = mapped_column(Text)
    value_presence: Mapped[str | None] = mapped_column(String(40), index=True)
    numeric_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    numeric_values_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    unit_value: Mapped[str | None] = mapped_column(String(80))
    text_value: Mapped[str | None] = mapped_column(Text)
    text_hash: Mapped[str | None] = mapped_column(String(120), index=True)
    evidence_time: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    period_raw: Mapped[str | None] = mapped_column(String(80), index=True)
    period_week_index: Mapped[int | None] = mapped_column(Integer)
    channel_type: Mapped[str | None] = mapped_column(String(80), index=True)
    platform_type: Mapped[str | None] = mapped_column(String(80), index=True)
    comment_id: Mapped[str | None] = mapped_column(String(160))
    comment_text_hash: Mapped[str | None] = mapped_column(String(120))
    segment_text_hash: Mapped[str | None] = mapped_column(String(120))
    sentence_seq: Mapped[int | None] = mapped_column(Integer)
    dimension_path_raw: Mapped[str | None] = mapped_column(Text)
    quality_status: Mapped[str] = mapped_column(String(40), nullable=False, default="ok", index=True)
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    base_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    confidence_level: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    sample_status: Mapped[str | None] = mapped_column(String(40), index=True)
    evidence_payload_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_status: Mapped[str] = mapped_column(String(40), nullable=False, default="current", index=True)
    inactive_reason: Mapped[str | None] = mapped_column(String(80))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    evidence_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m02_evidence_v1")
    confidence_rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m02_confidence_v1")
    asset_version: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)


class Core3EvidenceLink(Base, AuditMixin):
    __tablename__ = "core3_evidence_link"
    __table_args__ = (
        UniqueConstraint(
            "from_evidence_id",
            "to_evidence_id",
            "link_type",
            name="uq_core3_evidence_link_from_to_type",
        ),
        Index("ix_core3_evidence_link_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_evidence_link_from_evidence", "from_evidence_id"),
        Index("ix_core3_evidence_link_to_evidence", "to_evidence_id"),
        Index("ix_core3_evidence_link_type", "link_type"),
    )

    link_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    from_evidence_id: Mapped[str] = mapped_column(ForeignKey("core3_evidence_atom.evidence_id"), nullable=False)
    to_evidence_id: Mapped[str] = mapped_column(ForeignKey("core3_evidence_atom.evidence_id"), nullable=False)
    from_evidence_key: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    to_evidence_key: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    link_type: Mapped[str] = mapped_column(String(80), nullable=False)
    link_payload_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("1.0000"))
    link_status: Mapped[str] = mapped_column(String(40), nullable=False, default="current", index=True)


class Core3ParamFieldProfile(Base, AuditMixin):
    __tablename__ = "core3_param_field_profile"
    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "clean_param_name",
            "seed_version",
            "rule_version",
            name="uq_core3_param_field_profile_batch_clean_seed_rule",
        ),
        Index("ix_core3_param_field_profile_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_param_field_profile_matched_param_code", "matched_param_code"),
        Index("ix_core3_param_field_profile_candidate_status", "candidate_status"),
        Index("ix_core3_param_field_profile_review_required", "review_required"),
        Index("ix_core3_param_field_profile_top_values_gin", "top_values_json", postgresql_using="gin"),
        Index(
            "ix_core3_param_field_profile_pattern_summary_gin",
            "value_pattern_summary_json",
            postgresql_using="gin",
        ),
        Index("ix_core3_param_field_profile_evidence_ids_gin", "evidence_ids", postgresql_using="gin"),
    )

    field_profile_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    raw_param_name: Mapped[str | None] = mapped_column(String(240))
    clean_param_name: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    normalized_param_name: Mapped[str | None] = mapped_column(String(240), index=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sku_coverage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sku_coverage_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    unknown_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unknown_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    present_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    top_values_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    value_pattern_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    matched_param_code: Mapped[str | None] = mapped_column(String(160))
    matched_param_name: Mapped[str | None] = mapped_column(String(240))
    param_group: Mapped[str | None] = mapped_column(String(120), index=True)
    match_type: Mapped[str] = mapped_column(String(80), nullable=False, default="unmatched", index=True)
    alias_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    candidate_status: Mapped[str] = mapped_column(String(80), nullable=False, default="candidate")
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason: Mapped[dict | None] = mapped_column(JSONBCompat)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    field_profile_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    seed_version: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m03_param_extraction_v1")


class Core3ExtractParamValue(Base, AuditMixin):
    __tablename__ = "core3_extract_param_value"
    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "sku_code",
            "param_code",
            "source_type",
            "primary_evidence_id",
            "rule_version",
            name="uq_core3_extract_param_value_batch_sku_param_src_ev_rule",
        ),
        Index("ix_core3_extract_param_value_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_extract_param_value_sku_param", "sku_code", "param_code"),
        Index("ix_core3_extract_param_value_param_group", "param_group"),
        Index("ix_core3_extract_param_value_source_type", "source_type"),
        Index("ix_core3_extract_param_value_review_required", "review_required"),
        Index("ix_core3_extract_param_value_hash", "param_value_hash"),
        Index("ix_core3_extract_param_value_normalized_gin", "normalized_value", postgresql_using="gin"),
        Index("ix_core3_extract_param_value_evidence_ids_gin", "evidence_ids", postgresql_using="gin"),
        Index("ix_core3_extract_param_value_quality_flags_gin", "quality_flags", postgresql_using="gin"),
    )

    param_value_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    param_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    param_name: Mapped[str] = mapped_column(String(240), nullable=False)
    param_group: Mapped[str | None] = mapped_column(String(120))
    data_type: Mapped[str] = mapped_column(String(80), nullable=False, default="string")
    normalized_value: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSONBCompat)
    numeric_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    value_text: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(80))
    value_level: Mapped[str | None] = mapped_column(String(120), index=True)
    value_presence: Mapped[str | None] = mapped_column(String(40), index=True)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_priority_rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_param_name: Mapped[str | None] = mapped_column(String(240))
    raw_param_value: Mapped[str | None] = mapped_column(Text)
    match_type: Mapped[str] = mapped_column(String(80), nullable=False, default="unmatched", index=True)
    parser_type: Mapped[str | None] = mapped_column(String(120))
    parser_status: Mapped[str] = mapped_column(String(80), nullable=False, default="not_parsed", index=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    confidence_level: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    primary_evidence_id: Mapped[str] = mapped_column(ForeignKey("core3_evidence_atom.evidence_id"), index=True)
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    conflict_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    conflict_id: Mapped[str | None] = mapped_column(String(120), index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    param_value_hash: Mapped[str] = mapped_column(String(120), nullable=False)
    seed_version: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    parser_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m03_parser_v1")
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m03_param_extraction_v1")


class Core3ParamAliasCandidate(Base, AuditMixin):
    __tablename__ = "core3_param_alias_candidate"
    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "clean_param_name",
            "seed_version",
            name="uq_core3_param_alias_candidate_batch_clean_seed",
        ),
        Index("ix_core3_param_alias_candidate_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_param_alias_candidate_suggested_param_code", "suggested_param_code"),
        Index("ix_core3_param_alias_candidate_type", "candidate_type"),
        Index("ix_core3_param_alias_candidate_review_status", "review_status"),
        Index("ix_core3_param_alias_candidate_top_values_gin", "top_values_json", postgresql_using="gin"),
        Index("ix_core3_param_alias_candidate_review_decision_gin", "review_decision_json", postgresql_using="gin"),
    )

    alias_candidate_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    raw_param_name: Mapped[str | None] = mapped_column(String(240))
    clean_param_name: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    sku_coverage_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    unknown_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    top_values_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    value_pattern_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    suggested_param_code: Mapped[str | None] = mapped_column(String(160))
    suggestion_reason: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    candidate_type: Mapped[str] = mapped_column(String(80), nullable=False, default="unmatched_field")
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="review_required")
    review_decision_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    seed_version: Mapped[str] = mapped_column(String(80), nullable=False, default="default")


class Core3ParamValueConflict(Base, AuditMixin):
    __tablename__ = "core3_param_value_conflict"
    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "sku_code",
            "param_code",
            "conflict_type",
            "rule_version",
            name="uq_core3_param_value_conflict_batch_sku_param_type_rule",
        ),
        Index("ix_core3_param_value_conflict_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_param_value_conflict_sku_param", "sku_code", "param_code"),
        Index("ix_core3_param_value_conflict_type", "conflict_type"),
        Index("ix_core3_param_value_conflict_review_required", "review_required"),
        Index("ix_core3_param_value_conflict_candidate_values_gin", "candidate_values_json", postgresql_using="gin"),
        Index("ix_core3_param_value_conflict_evidence_ids_gin", "evidence_ids", postgresql_using="gin"),
        Index("ix_core3_param_value_conflict_quality_flags_gin", "quality_flags", postgresql_using="gin"),
    )

    conflict_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    param_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    conflict_type: Mapped[str] = mapped_column(String(80), nullable=False)
    candidate_values_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    preferred_value_json: Mapped[dict | list | str | int | float | bool | None] = mapped_column(JSONBCompat)
    preferred_source_type: Mapped[str | None] = mapped_column(String(80), index=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="review_required", index=True)
    review_reason: Mapped[dict | None] = mapped_column(JSONBCompat)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m03_param_extraction_v1")


class Core3SkuParamProfile(Base, AuditMixin):
    __tablename__ = "core3_sku_param_profile"
    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "sku_code",
            "seed_version",
            "rule_version",
            name="uq_core3_sku_param_profile_batch_sku_seed_rule",
        ),
        Index("ix_core3_sku_param_profile_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_sku_param_profile_sku_code", "sku_code"),
        Index("ix_core3_sku_param_profile_hash", "profile_hash"),
        Index("ix_core3_sku_param_profile_param_values_gin", "param_values_json", postgresql_using="gin"),
        Index("ix_core3_sku_param_profile_quality_summary_gin", "quality_summary_json", postgresql_using="gin"),
        Index("ix_core3_sku_param_profile_evidence_ids_gin", "evidence_ids", postgresql_using="gin"),
    )

    sku_param_profile_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(240))
    param_values_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    core_picture_params_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    core_gaming_params_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    core_system_params_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    core_eye_care_params_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    param_completeness: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    known_param_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unknown_param_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conflict_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_required_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    quality_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    profile_hash: Mapped[str] = mapped_column(String(120), nullable=False)
    seed_version: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m03_param_extraction_v1")


class Core3SkuParamDimensionTier(Base, AuditMixin):
    __tablename__ = "core3_sku_param_dimension_tier"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "taxonomy_version",
            "sku_code",
            "dimension_code",
            "is_current",
            name="uq_core3_sku_param_dimension_tier_current",
        ),
        Index("ix_core3_sku_param_dimension_tier_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_sku_param_dimension_tier_sku_dimension", "sku_code", "dimension_code"),
        Index("ix_core3_sku_param_dimension_tier_dimension_tier", "dimension_code", "tier_code"),
        Index("ix_core3_sku_param_dimension_tier_basis_values_gin", "basis_values_json", postgresql_using="gin"),
        Index("ix_core3_sku_param_dimension_tier_evidence_ids_gin", "evidence_ids", postgresql_using="gin"),
        Index("ix_core3_sku_param_dimension_tier_quality_flags_gin", "quality_flags", postgresql_using="gin"),
    )

    dimension_tier_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    dimension_code: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    tier_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    tier_name: Mapped[str] = mapped_column(String(240), nullable=False)
    tier_rank: Mapped[int | None] = mapped_column(Integer)
    basis_param_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    basis_values_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    rule_snapshot_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("1.0000"))
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    profile_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m03b_tv_param_profile_v0.1")


class Core3ParamTierCoverage(Base, AuditMixin):
    __tablename__ = "core3_param_tier_coverage"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "taxonomy_version",
            "dimension_code",
            "tier_code",
            "is_current",
            name="uq_core3_param_tier_coverage_current",
        ),
        Index("ix_core3_param_tier_coverage_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_param_tier_coverage_dimension_tier", "dimension_code", "tier_code"),
        Index("ix_core3_param_tier_coverage_sku_count", "sku_count"),
        Index("ix_core3_param_tier_coverage_status", "coverage_status"),
        Index("ix_core3_param_tier_coverage_sku_codes_gin", "sku_codes", postgresql_using="gin"),
        Index("ix_core3_param_tier_coverage_sample_sku_codes_gin", "sample_sku_codes", postgresql_using="gin"),
    )

    tier_coverage_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    dimension_code: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    tier_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    tier_name: Mapped[str] = mapped_column(String(240), nullable=False)
    tier_rank: Mapped[int | None] = mapped_column(Integer)
    rule_summary: Mapped[str] = mapped_column(Text, nullable=False)
    sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sku_ratio: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    sku_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    sample_sku_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    coverage_status: Mapped[str] = mapped_column(String(80), nullable=False, default="covered", index=True)
    coverage_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m03b_tv_param_profile_v0.1")


class Core3SkuClaimFactProfile(Base, AuditMixin):
    __tablename__ = "core3_sku_claim_fact_profile"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "taxonomy_version",
            "sku_code",
            "rule_version",
            "is_current",
            name="uq_core3_sku_claim_fact_profile_current",
        ),
        Index("ix_core3_sku_claim_fact_profile_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_sku_claim_fact_profile_claim_codes_gin", "claim_codes", postgresql_using="gin"),
        Index("ix_core3_sku_claim_fact_profile_fact_codes_gin", "fact_claim_codes", postgresql_using="gin"),
        Index("ix_core3_sku_claim_fact_profile_dimension_gin", "dimension_profile_json", postgresql_using="gin"),
        Index("ix_core3_sku_claim_fact_profile_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    claim_profile_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    product_category: Mapped[str] = mapped_column(String(40), nullable=False, default="TV", index=True)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    raw_claim_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matched_claim_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fact_claim_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unsupported_claim_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    param_unknown_claim_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    service_separate_claim_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claim_texts_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    claim_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    fact_claim_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    unsupported_claim_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    service_claim_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    dimension_profile_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    dimension_position_profile_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    claim_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    profile_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m04c_tv_claim_fact_profile_v0.1")


class Core3SkuClaimFact(Base, AuditMixin):
    __tablename__ = "core3_sku_claim_fact"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "taxonomy_version",
            "sku_code",
            "source_claim_key",
            "claim_code",
            "rule_version",
            "is_current",
            name="uq_core3_sku_claim_fact_current",
        ),
        Index("ix_core3_sku_claim_fact_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_sku_claim_fact_supporting_params_gin", "supporting_param_codes", postgresql_using="gin"),
        Index("ix_core3_sku_claim_fact_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    claim_fact_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    product_category: Mapped[str] = mapped_column(String(40), nullable=False, default="TV", index=True)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    source_claim_key: Mapped[str] = mapped_column(String(220), nullable=False, index=True)
    claim_seq: Mapped[int | None] = mapped_column(Integer)
    raw_claim_text: Mapped[str | None] = mapped_column(Text)
    clean_claim_text: Mapped[str | None] = mapped_column(Text)
    claim_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    claim_name: Mapped[str] = mapped_column(String(240), nullable=False)
    claim_dimension: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    claim_subtype: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    claim_kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    match_type: Mapped[str] = mapped_column(String(80), nullable=False, default="keyword")
    match_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("1.0000"))
    param_support_status: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    supporting_param_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    supporting_param_snapshot_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    support_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    fact_claim_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    service_separate_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    fact_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m04c_tv_claim_fact_profile_v0.1")


class Core3SkuClaimDimensionPosition(Base, AuditMixin):
    __tablename__ = "core3_sku_claim_dimension_position"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "taxonomy_version",
            "sku_code",
            "dimension_code",
            "position_source",
            "rule_version",
            "is_current",
            name="uq_core3_sku_claim_dimension_position_current",
        ),
        Index("ix_core3_sku_claim_dimension_position_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_sku_claim_dimension_position_sku_dimension", "sku_code", "dimension_code"),
        Index("ix_core3_sku_claim_dimension_position_position", "dimension_code", "position_code"),
        Index("ix_core3_sku_claim_dimension_position_basis_gin", "basis_claim_codes", postgresql_using="gin"),
        Index("ix_core3_sku_claim_dimension_position_fact_basis_gin", "basis_fact_claim_codes", postgresql_using="gin"),
    )

    dimension_position_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    product_category: Mapped[str] = mapped_column(String(40), nullable=False, default="TV", index=True)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    dimension_code: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    position_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    position_name: Mapped[str] = mapped_column(String(240), nullable=False)
    position_rank: Mapped[int | None] = mapped_column(Integer)
    position_source: Mapped[str] = mapped_column(String(40), nullable=False, default="supported", index=True)
    basis_claim_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    basis_fact_claim_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    basis_texts_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    position_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m04c_tv_claim_fact_profile_v0.1")


class Core3ClaimPositionCoverage(Base, AuditMixin):
    __tablename__ = "core3_claim_position_coverage"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "taxonomy_version",
            "dimension_code",
            "position_code",
            "position_source",
            "rule_version",
            "is_current",
            name="uq_core3_claim_position_coverage_current",
        ),
        Index("ix_core3_claim_position_coverage_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_claim_position_coverage_position", "dimension_code", "position_code"),
        Index("ix_core3_claim_position_coverage_sku_count", "sku_count"),
        Index("ix_core3_claim_position_coverage_sku_codes_gin", "sku_codes", postgresql_using="gin"),
        Index("ix_core3_claim_position_coverage_basis_gin", "basis_claim_codes", postgresql_using="gin"),
    )

    position_coverage_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    product_category: Mapped[str] = mapped_column(String(40), nullable=False, default="TV", index=True)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    dimension_code: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    position_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    position_name: Mapped[str] = mapped_column(String(240), nullable=False)
    position_rank: Mapped[int | None] = mapped_column(Integer)
    position_source: Mapped[str] = mapped_column(String(40), nullable=False, default="supported", index=True)
    rule_summary: Mapped[str] = mapped_column(Text, nullable=False)
    sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sku_ratio: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    sku_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    sample_sku_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    basis_claim_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    coverage_status: Mapped[str] = mapped_column(String(80), nullable=False, default="covered", index=True)
    coverage_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m04c_tv_claim_fact_profile_v0.1")


class Core3CommentFactAtom(Base, AuditMixin):
    __tablename__ = "core3_comment_fact_atom"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "taxonomy_version",
            "sku_code",
            "source_comment_key",
            "subdimension_code",
            "rule_version",
            "is_current",
            name="uq_core3_comment_fact_atom_current",
        ),
        Index("ix_core3_comment_fact_atom_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_comment_fact_atom_sku_dimension", "sku_code", "dimension_code"),
        Index("ix_core3_comment_fact_atom_subdimension", "dimension_code", "subdimension_code"),
        Index("ix_core3_comment_fact_atom_params_gin", "supported_param_codes", postgresql_using="gin"),
        Index("ix_core3_comment_fact_atom_claims_gin", "supported_claim_codes", postgresql_using="gin"),
        Index("ix_core3_comment_fact_atom_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    comment_fact_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    product_category: Mapped[str] = mapped_column(String(40), nullable=False, default="TV", index=True)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    source_comment_key: Mapped[str] = mapped_column(String(220), nullable=False, index=True)
    source_comment_id: Mapped[str | None] = mapped_column(String(180), index=True)
    sentence_seq: Mapped[int | None] = mapped_column(Integer)
    raw_comment_text: Mapped[str | None] = mapped_column(Text)
    clean_comment_text: Mapped[str] = mapped_column(Text, nullable=False)
    dimension_code: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    dimension_name: Mapped[str] = mapped_column(String(240), nullable=False)
    subdimension_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    subdimension_name: Mapped[str] = mapped_column(String(240), nullable=False)
    dimension_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    polarity: Mapped[str] = mapped_column(String(40), nullable=False, default="neutral", index=True)
    evidence_strength: Mapped[str] = mapped_column(String(40), nullable=False, default="medium", index=True)
    support_relation: Mapped[str] = mapped_column(String(80), nullable=False, default="comment_signal_only", index=True)
    support_target_type: Mapped[str] = mapped_column(String(80), nullable=False, default="signal", index=True)
    supported_param_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    contradicted_param_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    supported_claim_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    contradicted_claim_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    param_snapshot_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    claim_snapshot_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    signal_payload_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    extraction_payload_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    fact_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m05c_tv_comment_fact_profile_v0.1")


class Core3SkuCommentFactProfile(Base, AuditMixin):
    __tablename__ = "core3_sku_comment_fact_profile"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "taxonomy_version",
            "sku_code",
            "rule_version",
            "is_current",
            name="uq_core3_sku_comment_fact_profile_current",
        ),
        Index("ix_core3_sku_comment_profile_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_sku_comment_profile_dimension_gin", "dimension_summary_json", postgresql_using="gin"),
        Index("ix_core3_sku_comment_profile_signal_gin", "signal_summary_json", postgresql_using="gin"),
        Index("ix_core3_sku_comment_profile_param_support_gin", "supported_param_codes", postgresql_using="gin"),
        Index("ix_core3_sku_comment_profile_claim_support_gin", "supported_claim_codes", postgresql_using="gin"),
    )

    comment_profile_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    product_category: Mapped[str] = mapped_column(String(40), nullable=False, default="TV", index=True)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    comment_sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matched_sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fact_atom_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    product_fact_sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    positive_sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    negative_sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mixed_sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    neutral_sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    service_excluded_sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dimension_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    signal_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    param_comment_support_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    claim_comment_support_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    polarity_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_examples_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    supported_param_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    contradicted_param_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    unmentioned_param_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    supported_claim_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    contradicted_claim_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    unmentioned_claim_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    review_required_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    profile_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m05c_tv_comment_fact_profile_v0.1")


class Core3CommentFactCoverage(Base, AuditMixin):
    __tablename__ = "core3_comment_fact_coverage"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "product_category",
            "taxonomy_version",
            "coverage_type",
            "coverage_key",
            "rule_version",
            "is_current",
            name="uq_core3_comment_fact_coverage_current",
        ),
        Index("ix_core3_comment_fact_coverage_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_comment_fact_coverage_type_key", "coverage_type", "coverage_key"),
        Index("ix_core3_comment_fact_coverage_dimension", "dimension_code", "subdimension_code"),
        Index("ix_core3_comment_fact_coverage_sku_count", "sku_count"),
        Index("ix_core3_comment_fact_coverage_skus_gin", "sku_codes", postgresql_using="gin"),
        Index("ix_core3_comment_fact_coverage_sample_gin", "sample_evidence_json", postgresql_using="gin"),
    )

    comment_coverage_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    product_category: Mapped[str] = mapped_column(String(40), nullable=False, default="TV", index=True)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    coverage_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    coverage_key: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    coverage_name: Mapped[str] = mapped_column(String(240), nullable=False)
    dimension_code: Mapped[str | None] = mapped_column(String(120), index=True)
    subdimension_code: Mapped[str | None] = mapped_column(String(160), index=True)
    rule_summary: Mapped[str] = mapped_column(Text, nullable=False)
    fact_atom_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    positive_sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    negative_sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mixed_sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    neutral_sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    strong_evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    supported_param_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contradicted_param_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    supported_claim_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    contradicted_claim_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sku_ratio: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    sku_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    sample_sku_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    top_skus_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    supported_param_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    contradicted_param_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    supported_claim_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    contradicted_claim_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    sample_evidence_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    sample_status_counts_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    review_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    coverage_status: Mapped[str] = mapped_column(String(80), nullable=False, default="covered", index=True)
    coverage_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m05c_tv_comment_fact_profile_v0.1")


class Core3CommentFactReviewIssue(Base, AuditMixin):
    __tablename__ = "core3_comment_fact_review_issue"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "taxonomy_version",
            "sku_code",
            "issue_type",
            "issue_hash",
            "rule_version",
            "is_current",
            name="uq_core3_comment_fact_review_issue_current",
        ),
        Index("ix_core3_comment_fact_review_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_comment_fact_review_sku_type", "sku_code", "issue_type"),
    )

    review_issue_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    product_category: Mapped[str] = mapped_column(String(40), nullable=False, default="TV", index=True)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    issue_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(40), nullable=False, default="medium", index=True)
    issue_detail: Mapped[str] = mapped_column(Text, nullable=False)
    issue_payload_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="review_required", index=True)
    issue_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m05c_tv_comment_fact_profile_v0.1")


class Core3ParamTaxonomyVersion(Base, AuditMixin):
    __tablename__ = "core3_param_taxonomy_version"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "taxonomy_version",
            name="uq_core3_param_taxonomy_version_project_category_version",
        ),
        Index("ix_core3_param_taxonomy_version_project_category", "project_id", "category_code"),
        Index("ix_core3_param_taxonomy_version_hash", "taxonomy_hash"),
        Index("ix_core3_param_taxonomy_version_source_batches_gin", "source_batch_ids", postgresql_using="gin"),
    )

    taxonomy_version_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(60), nullable=False, default="draft", index=True)
    source_batch_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    source_field_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    active_param_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_required_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocking_review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_model_snapshot: Mapped[str | None] = mapped_column(String(160))
    llm_prompt_version: Mapped[str | None] = mapped_column(String(120))
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m03a_param_taxonomy_v1")
    taxonomy_hash: Mapped[str] = mapped_column(String(120), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False, default="system")


class Core3ParamRawFieldInventory(Base, AuditMixin):
    __tablename__ = "core3_param_raw_field_inventory"
    __table_args__ = (
        UniqueConstraint(
            "taxonomy_version",
            "raw_param_name",
            name="uq_core3_param_raw_field_inventory_version_raw_name",
        ),
        Index("ix_core3_param_raw_field_inventory_project_category", "project_id", "category_code"),
        Index("ix_core3_param_raw_field_inventory_top_values_gin", "top_values_json", postgresql_using="gin"),
        Index("ix_core3_param_raw_field_inventory_pattern_gin", "value_pattern_json", postgresql_using="gin"),
    )

    raw_field_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    raw_param_name: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    clean_param_name: Mapped[str] = mapped_column(String(240), nullable=False)
    normalized_param_name: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sku_coverage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sku_coverage_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    unknown_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unknown_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    top_values_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    sample_values_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    value_pattern_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    unit_candidates_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    cooccurrence_field_names: Mapped[list] = mapped_column(JSONBCompat, default=list)
    field_status: Mapped[str] = mapped_column(String(80), nullable=False, default="review_required", index=True)
    field_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)


class Core3ParamFieldCluster(Base, AuditMixin):
    __tablename__ = "core3_param_field_cluster"
    __table_args__ = (
        UniqueConstraint(
            "taxonomy_version",
            "cluster_code",
            name="uq_core3_param_field_cluster_version_code",
        ),
        Index("ix_core3_param_field_cluster_project_category", "project_id", "category_code"),
        Index("ix_core3_param_field_cluster_members_gin", "member_raw_fields", postgresql_using="gin"),
    )

    field_cluster_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    cluster_code: Mapped[str] = mapped_column(String(160), nullable=False)
    cluster_name_candidate: Mapped[str | None] = mapped_column(String(240))
    member_raw_fields: Mapped[list] = mapped_column(JSONBCompat, default=list)
    cluster_method: Mapped[str] = mapped_column(String(80), nullable=False, default="rule")
    cluster_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    cluster_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)


class Core3ParamConceptCandidate(Base, AuditMixin):
    __tablename__ = "core3_param_concept_candidate"
    __table_args__ = (
        UniqueConstraint(
            "taxonomy_version",
            "candidate_code",
            name="uq_core3_param_concept_candidate_version_code",
        ),
        Index("ix_core3_param_concept_candidate_project_category", "project_id", "category_code"),
        Index("ix_core3_param_concept_candidate_capability_tags_gin", "capability_tags", postgresql_using="gin"),
        Index("ix_core3_param_concept_candidate_source_fields_gin", "source_raw_fields", postgresql_using="gin"),
    )

    concept_candidate_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    candidate_code: Mapped[str] = mapped_column(String(160), nullable=False)
    candidate_name: Mapped[str] = mapped_column(String(240), nullable=False)
    source_cluster_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    source_raw_fields: Mapped[list] = mapped_column(JSONBCompat, default=list)
    definition_candidate: Mapped[str] = mapped_column(Text, nullable=False)
    data_type_candidate: Mapped[str] = mapped_column(String(80), nullable=False, default="string")
    unit_candidate: Mapped[str | None] = mapped_column(String(80))
    parser_candidate: Mapped[str | None] = mapped_column(String(120))
    capability_tags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    benefit_hints: Mapped[list] = mapped_column(JSONBCompat, default=list)
    scenario_hints: Mapped[list] = mapped_column(JSONBCompat, default=list)
    comparison_axis: Mapped[str] = mapped_column(String(160), nullable=False, default="not_comparable")
    evidence_role: Mapped[str] = mapped_column(String(80), nullable=False, default="weak_signal")
    risk_notes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    llm_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    rule_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="review_required", index=True)


class Core3ParamDefinition(Base, AuditMixin):
    __tablename__ = "core3_param_definition"
    __table_args__ = (
        UniqueConstraint(
            "taxonomy_version",
            "param_code",
            name="uq_core3_param_definition_version_code",
        ),
        Index("ix_core3_param_definition_project_category", "project_id", "category_code"),
        Index("ix_core3_param_definition_group", "param_group"),
        Index("ix_core3_param_definition_capability_tags_gin", "capability_tags", postgresql_using="gin"),
        Index("ix_core3_param_definition_source_fields_gin", "source_raw_fields", postgresql_using="gin"),
    )

    param_definition_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    param_code: Mapped[str] = mapped_column(String(160), nullable=False)
    param_name: Mapped[str] = mapped_column(String(240), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    param_group: Mapped[str] = mapped_column(String(120), nullable=False, default="other")
    data_type: Mapped[str] = mapped_column(String(80), nullable=False, default="string")
    unit: Mapped[str | None] = mapped_column(String(80))
    value_parser: Mapped[str] = mapped_column(String(120), nullable=False, default="string")
    parser_config_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    source_raw_fields: Mapped[list] = mapped_column(JSONBCompat, default=list)
    capability_tags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    benefit_hints: Mapped[list] = mapped_column(JSONBCompat, default=list)
    scenario_hints: Mapped[list] = mapped_column(JSONBCompat, default=list)
    comparison_axis: Mapped[str] = mapped_column(String(160), nullable=False, default="not_comparable")
    evidence_role: Mapped[str] = mapped_column(String(80), nullable=False, default="weak_signal")
    analysis_status: Mapped[str] = mapped_column(String(80), nullable=False, default="active", index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    definition_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)


class Core3ParamFieldMappingRule(Base, AuditMixin):
    __tablename__ = "core3_param_field_mapping_rule"
    __table_args__ = (
        UniqueConstraint(
            "taxonomy_version",
            "raw_param_name",
            "param_code",
            "mapping_type",
            name="uq_core3_param_field_mapping_rule_version_raw_param_type",
        ),
        Index("ix_core3_param_field_mapping_rule_project_category", "project_id", "category_code"),
        Index("ix_core3_param_field_mapping_rule_type", "mapping_type"),
    )

    mapping_rule_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    raw_param_name: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    param_code: Mapped[str | None] = mapped_column(String(160), index=True)
    mapping_type: Mapped[str] = mapped_column(String(80), nullable=False, default="review_required")
    value_policy: Mapped[str] = mapped_column(String(80), nullable=False, default="requires_rule")
    parser_type: Mapped[str | None] = mapped_column(String(120))
    parser_config_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    invalid_value_policy_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    source_priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="review_required", index=True)


class Core3ParamTaxonomyReviewItem(Base, AuditMixin):
    __tablename__ = "core3_param_taxonomy_review_item"
    __table_args__ = (
        UniqueConstraint(
            "taxonomy_version",
            "item_type",
            "raw_param_name",
            "param_code",
            name="uq_core3_param_taxonomy_review_item_version_type_raw_param",
        ),
        Index("ix_core3_param_taxonomy_review_item_project_category", "project_id", "category_code"),
        Index("ix_core3_param_taxonomy_review_item_type", "item_type"),
        Index("ix_core3_param_taxonomy_review_item_evidence_gin", "evidence_json", postgresql_using="gin"),
    )

    review_item_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), nullable=False, default="warning", index=True)
    raw_param_name: Mapped[str | None] = mapped_column(String(240), index=True)
    param_code: Mapped[str | None] = mapped_column(String(160), index=True)
    issue_summary_cn: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    suggested_action: Mapped[str] = mapped_column(String(120), nullable=False, default="review")
    review_decision_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="review_required", index=True)


class Core3ExtractClaimHit(Base, AuditMixin):
    __tablename__ = "core3_extract_claim_hit"
    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "sku_code",
            "claim_code",
            "hit_source_type",
            "source_sentence_key",
            "rule_version",
            name="uq_core3_claim_hit_batch_sku_claim_src_key_rule",
        ),
        Index("ix_core3_claim_hit_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_claim_hit_sku_claim", "sku_code", "claim_code"),
        Index("ix_core3_claim_hit_source_type", "hit_source_type"),
        Index("ix_core3_claim_hit_review_required", "review_required"),
        Index("ix_core3_claim_hit_keywords_gin", "matched_keywords", postgresql_using="gin"),
        Index("ix_core3_claim_hit_entity_gin", "extracted_entity_json", postgresql_using="gin"),
        Index("ix_core3_claim_hit_promo_ev_gin", "promo_evidence_ids", postgresql_using="gin"),
        Index("ix_core3_claim_hit_param_ev_gin", "param_evidence_ids", postgresql_using="gin"),
        Index("ix_core3_claim_hit_quality_ev_gin", "quality_evidence_ids", postgresql_using="gin"),
        Index("ix_core3_claim_hit_quality_flags_gin", "quality_flags", postgresql_using="gin"),
    )

    claim_hit_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    claim_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    claim_name: Mapped[str] = mapped_column(String(240), nullable=False)
    claim_group: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    hit_source_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_sentence_key: Mapped[str] = mapped_column(String(320), nullable=False, default="")
    claim_seq: Mapped[int | None] = mapped_column(Integer)
    sentence_seq: Mapped[int | None] = mapped_column(Integer)
    claim_fragment: Mapped[str | None] = mapped_column(Text)
    matched_keywords: Mapped[list] = mapped_column(JSONBCompat, default=list)
    title_hint: Mapped[str | None] = mapped_column(Text)
    extracted_entity_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    matched_param_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    match_method: Mapped[str] = mapped_column(String(80), nullable=False)
    promo_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    param_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    quality_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    match_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    hit_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    seed_version: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m04a_claim_activation_v1")


class Core3SkuClaimSourceStatus(Base, AuditMixin):
    __tablename__ = "core3_sku_claim_source_status"
    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "sku_code",
            "seed_version",
            "rule_version",
            name="uq_core3_claim_source_status_batch_sku_seed_rule",
        ),
        Index("ix_core3_claim_source_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_claim_source_sku_code", "sku_code"),
        Index("ix_core3_claim_source_status", "claim_source_status"),
        Index("ix_core3_claim_source_review_required", "review_required"),
        Index("ix_core3_claim_source_quality_ev_gin", "quality_evidence_ids", postgresql_using="gin"),
        Index("ix_core3_claim_source_missing_gin", "missing_signals", postgresql_using="gin"),
        Index("ix_core3_claim_source_conflict_gin", "conflict_summary_json", postgresql_using="gin"),
    )

    claim_source_status_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    claim_source_status: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    structured_claim_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claim_sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    promo_evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    param_only_claim_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quality_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    missing_signals: Mapped[list] = mapped_column(JSONBCompat, default=list)
    conflict_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    status_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    status_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    seed_version: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m04a_claim_activation_v1")


class Core3SkuClaimActivationBase(Base, AuditMixin):
    __tablename__ = "core3_sku_claim_activation_base"
    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "sku_code",
            "claim_code",
            "seed_version",
            "rule_version",
            name="uq_core3_claim_activation_base_batch_sku_claim_seed",
        ),
        Index("ix_core3_claim_base_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_claim_base_sku_claim", "sku_code", "claim_code"),
        Index("ix_core3_claim_base_group", "claim_group"),
        Index("ix_core3_claim_base_level", "activation_level"),
        Index("ix_core3_claim_base_basis", "activation_basis"),
        Index("ix_core3_claim_base_review_required", "review_required"),
        Index("ix_core3_claim_base_hash", "activation_hash"),
        Index("ix_core3_claim_base_evidence_gin", "evidence_ids", postgresql_using="gin"),
        Index("ix_core3_claim_base_missing_gin", "missing_signals", postgresql_using="gin"),
        Index("ix_core3_claim_base_conflict_gin", "conflict_flags", postgresql_using="gin"),
        Index("ix_core3_claim_base_param_support_gin", "param_support_json", postgresql_using="gin"),
        Index("ix_core3_claim_base_promo_support_gin", "promo_support_json", postgresql_using="gin"),
    )

    claim_activation_base_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    claim_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    claim_name: Mapped[str] = mapped_column(String(240), nullable=False)
    claim_group: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    claim_type: Mapped[str] = mapped_column(String(80), nullable=False, default="mixed", index=True)
    param_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    promo_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    base_activation_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    activation_level: Mapped[str] = mapped_column(String(60), nullable=False, default="unknown", index=True)
    activation_basis: Mapped[str] = mapped_column(String(80), nullable=False, default="insufficient", index=True)
    param_support_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    promo_support_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    missing_signals: Mapped[list] = mapped_column(JSONBCompat, default=list)
    conflict_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    confidence_level: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    param_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    promo_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    quality_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    claim_hit_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason: Mapped[str | None] = mapped_column(Text)
    activation_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    seed_version: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m04a_claim_activation_v1")


class Core3CommentUnit(Base, AuditMixin):
    __tablename__ = "core3_comment_unit"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "comment_unit_key",
            "rule_version",
            name="uq_core3_comment_unit_batch_key_rule",
        ),
        CheckConstraint(
            "dedup_strategy in ('comment_id', 'text_hash', 'source_row_fallback')",
            name="ck_m05_unit_dedup",
        ),
        CheckConstraint(
            "comment_unit_status in ('usable', 'low_value', 'duplicate_only', 'blocked')",
            name="ck_m05_unit_status",
        ),
        CheckConstraint(
            "sentiment_hint in ('positive', 'negative', 'neutral', 'unknown', 'conflict')",
            name="ck_m05_unit_sentiment",
        ),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_m05_unit_confidence"),
        CheckConstraint("source_row_count >= 0", name="ck_m05_unit_source_rows"),
        CheckConstraint("canonical_text_length >= 0", name="ck_m05_unit_text_len"),
        Index("ix_core3_comment_unit_project_category_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_comment_unit_sku_comment", "sku_code", "comment_id"),
        Index("ix_core3_comment_unit_sku_text_hash", "sku_code", "comment_text_hash"),
        Index("ix_core3_comment_unit_duplicate_group", "duplicate_group_id"),
        Index("ix_core3_comment_unit_status", "comment_unit_status"),
        Index("ix_core3_comment_unit_review_required", "review_required"),
        Index("ix_core3_comment_unit_raw_dimensions_gin", "raw_dimension_paths", postgresql_using="gin"),
        Index("ix_core3_comment_unit_quality_flags_gin", "quality_flags", postgresql_using="gin"),
        Index("ix_core3_comment_unit_low_value_gin", "low_value_reasons", postgresql_using="gin"),
    )

    comment_unit_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    comment_unit_key: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    dedup_strategy: Mapped[str] = mapped_column(String(80), nullable=False)
    comment_id: Mapped[str | None] = mapped_column(String(180), index=True)
    comment_text_hash: Mapped[str | None] = mapped_column(String(120), index=True)
    canonical_comment_text: Mapped[str | None] = mapped_column(Text)
    canonical_text_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_dimension_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_quality_issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_comment_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    source_sentence_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    source_dimension_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    source_quality_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    raw_dimension_paths: Mapped[list] = mapped_column(JSONBCompat, default=list)
    sentiment_raw_set: Mapped[list] = mapped_column(JSONBCompat, default=list)
    sentiment_hint: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    sentiment_conflict_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    low_value_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    low_value_reasons: Mapped[list] = mapped_column(JSONBCompat, default=list)
    duplicate_group_id: Mapped[str | None] = mapped_column(String(240), index=True)
    duplicate_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comment_unit_status: Mapped[str] = mapped_column(String(60), nullable=False, default="usable", index=True)
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    confidence_level: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m05_comment_evidence_v1")
    asset_version: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3CommentUnitEvidenceLink(Base, AuditMixin):
    __tablename__ = "core3_comment_unit_evidence_link"
    __table_args__ = (
        UniqueConstraint(
            "comment_unit_id",
            "source_evidence_id",
            "link_role",
            "rule_version",
            name="uq_core3_comment_unit_link_unit_ev_role",
        ),
        CheckConstraint(
            "source_evidence_type in ('comment_raw', 'comment_sentence', 'comment_dimension', 'quality_issue')",
            name="ck_m05_unit_link_ev_type",
        ),
        CheckConstraint(
            "link_role in ('raw_source', 'sentence_source', 'dimension_weak_label', 'quality_flag')",
            name="ck_m05_unit_link_role",
        ),
        Index("ix_core3_comment_unit_link_project_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_comment_unit_link_source_ev", "source_evidence_id"),
        Index("ix_core3_comment_unit_link_ev_type", "source_evidence_type"),
        Index("ix_core3_comment_unit_link_sku_comment", "sku_code", "comment_id"),
        Index("ix_core3_comment_unit_link_text_hash", "comment_text_hash"),
    )

    unit_link_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    comment_unit_id: Mapped[str] = mapped_column(ForeignKey("core3_comment_unit.comment_unit_id"), index=True)
    source_evidence_id: Mapped[str] = mapped_column(ForeignKey("core3_evidence_atom.evidence_id"), index=True)
    source_evidence_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    link_role: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_row_id: Mapped[str | None] = mapped_column(String(240), index=True)
    comment_id: Mapped[str | None] = mapped_column(String(180), index=True)
    comment_text_hash: Mapped[str | None] = mapped_column(String(120), index=True)
    sentence_hash: Mapped[str | None] = mapped_column(String(120), index=True)
    dimension_path_raw: Mapped[str | None] = mapped_column(Text)
    quality_issue_type: Mapped[str | None] = mapped_column(String(120), index=True)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m05_comment_evidence_v1")
    asset_version: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3CommentEvidenceAtom(Base, AuditMixin):
    __tablename__ = "core3_comment_evidence_atom"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "comment_evidence_key",
            "rule_version",
            name="uq_core3_comment_atom_batch_key_rule",
        ),
        CheckConstraint(
            "sentence_source_priority in ('system_split', 'source_segment', 'raw_fallback')",
            name="ck_m05_atom_sentence_source",
        ),
        CheckConstraint(
            "primary_domain_hint in ('product_experience', 'product_risk', 'market_perception', "
            "'service_experience', 'logistics_installation', 'unknown')",
            name="ck_m05_atom_primary_domain",
        ),
        CheckConstraint(
            "sentiment_source in ('raw_only', 'text_rule', 'raw_text_combined', 'unknown')",
            name="ck_m05_atom_sentiment_source",
        ),
        CheckConstraint("specificity_score >= 0 and specificity_score <= 1", name="ck_m05_atom_specificity"),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_m05_atom_confidence"),
        Index("ix_core3_comment_atom_project_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_comment_atom_sku_unit", "sku_code", "comment_unit_id"),
        Index("ix_core3_comment_atom_sku_sentence_hash", "sku_code", "sentence_hash"),
        Index("ix_core3_comment_atom_primary_domain", "primary_domain_hint"),
        Index("ix_core3_comment_atom_sentiment", "sentiment_hint"),
        Index("ix_core3_comment_atom_low_value", "low_value_flag"),
        Index("ix_core3_comment_atom_downstream", "usable_for_downstream"),
        Index("ix_core3_comment_atom_review_required", "review_required"),
        Index("ix_core3_comment_atom_domain_hints_gin", "domain_hints", postgresql_using="gin"),
        Index("ix_core3_comment_atom_raw_dimensions_gin", "raw_dimension_paths", postgresql_using="gin"),
        Index("ix_core3_comment_atom_low_value_gin", "low_value_reasons", postgresql_using="gin"),
        Index("ix_core3_comment_atom_block_reasons_gin", "downstream_block_reasons", postgresql_using="gin"),
    )

    comment_evidence_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    comment_evidence_key: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    comment_unit_id: Mapped[str] = mapped_column(ForeignKey("core3_comment_unit.comment_unit_id"), index=True)
    comment_id: Mapped[str | None] = mapped_column(String(180), index=True)
    comment_text_hash: Mapped[str | None] = mapped_column(String(120), index=True)
    sentence_hash: Mapped[str | None] = mapped_column(String(120), index=True)
    sentence_seq: Mapped[int | None] = mapped_column(Integer)
    sentence_source_priority: Mapped[str] = mapped_column(String(80), nullable=False, default="raw_fallback")
    sentence_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_sentence_text: Mapped[str] = mapped_column(Text, nullable=False)
    sentence_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_sentence_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    source_comment_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    source_dimension_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    source_quality_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    raw_dimension_paths: Mapped[list] = mapped_column(JSONBCompat, default=list)
    domain_hints: Mapped[list] = mapped_column(JSONBCompat, default=list)
    primary_domain_hint: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown", index=True)
    domain_conflict_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    sentiment_hint: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    sentiment_source: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown")
    sentiment_conflict_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    low_value_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    low_value_reasons: Mapped[list] = mapped_column(JSONBCompat, default=list)
    duplicate_group_id: Mapped[str | None] = mapped_column(String(240), index=True)
    sentence_duplicate_group_id: Mapped[str | None] = mapped_column(String(240), index=True)
    specificity_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    representative_phrase: Mapped[str | None] = mapped_column(Text)
    representative_phrase_rule: Mapped[str | None] = mapped_column(String(120))
    usable_for_downstream: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    downstream_block_reasons: Mapped[list] = mapped_column(JSONBCompat, default=list)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    confidence_level: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m05_comment_evidence_v1")
    asset_version: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3CommentTopicHint(Base, AuditMixin):
    __tablename__ = "core3_comment_topic_hint"
    __table_args__ = (
        UniqueConstraint(
            "comment_evidence_id",
            "topic_code",
            "match_method",
            "rule_version",
            name="uq_core3_comment_topic_hint_ev_topic_method",
        ),
        CheckConstraint(
            "match_method in ('keyword', 'positive_keyword', 'negative_keyword', 'dimension_path', "
            "'phrase', 'seed_rule')",
            name="ck_m05_topic_match_method",
        ),
        CheckConstraint(
            "polarity_hint in ('positive', 'negative', 'neutral', 'unknown')",
            name="ck_m05_topic_polarity",
        ),
        CheckConstraint(
            "topic_hint_status in ('matched', 'low_confidence', 'blocked_low_value', "
            "'blocked_service_guardrail')",
            name="ck_m05_topic_status",
        ),
        CheckConstraint("topic_confidence >= 0 and topic_confidence <= 1", name="ck_m05_topic_confidence"),
        Index("ix_core3_comment_topic_project_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_comment_topic_sku_topic", "sku_code", "topic_code"),
        Index("ix_core3_comment_topic_group", "topic_group"),
        Index("ix_core3_comment_topic_polarity", "polarity_hint"),
        Index("ix_core3_comment_topic_status", "topic_hint_status"),
        Index("ix_core3_comment_topic_matched_terms_gin", "matched_terms", postgresql_using="gin"),
        Index("ix_core3_comment_topic_match_source_gin", "match_source_json", postgresql_using="gin"),
        Index("ix_core3_comment_topic_claims_gin", "mapped_claim_codes_snapshot", postgresql_using="gin"),
        Index("ix_core3_comment_topic_tasks_gin", "mapped_task_codes_snapshot", postgresql_using="gin"),
        Index(
            "ix_core3_comment_topic_battlefields_gin",
            "mapped_battlefield_codes_snapshot",
            postgresql_using="gin",
        ),
    )

    topic_hint_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    comment_evidence_id: Mapped[str] = mapped_column(
        ForeignKey("core3_comment_evidence_atom.comment_evidence_id"),
        index=True,
    )
    comment_unit_id: Mapped[str] = mapped_column(ForeignKey("core3_comment_unit.comment_unit_id"), index=True)
    topic_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    topic_name: Mapped[str] = mapped_column(String(240), nullable=False)
    topic_group: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    topic_definition: Mapped[str | None] = mapped_column(Text)
    match_method: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    matched_terms: Mapped[list] = mapped_column(JSONBCompat, default=list)
    match_source_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    polarity_hint: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    topic_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    is_weak_hint: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    activates_product_claim: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    service_guardrail_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    mapped_claim_codes_snapshot: Mapped[list] = mapped_column(JSONBCompat, default=list)
    mapped_task_codes_snapshot: Mapped[list] = mapped_column(JSONBCompat, default=list)
    mapped_battlefield_codes_snapshot: Mapped[list] = mapped_column(JSONBCompat, default=list)
    topic_hint_status: Mapped[str] = mapped_column(String(80), nullable=False, default="matched", index=True)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m05_comment_evidence_v1")
    asset_version: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3CommentQualityProfile(Base, AuditMixin):
    __tablename__ = "core3_comment_quality_profile"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "rule_version",
            "asset_version",
            name="uq_core3_comment_quality_batch_sku_rule_asset",
        ),
        CheckConstraint(
            "sample_status in ('sufficient', 'limited', 'insufficient', 'unknown')",
            name="ck_m05_quality_sample_status",
        ),
        CheckConstraint("comment_usability_score >= 0 and comment_usability_score <= 1", name="ck_m05_quality_score"),
        CheckConstraint("duplicate_text_rate >= 0 and duplicate_text_rate <= 1", name="ck_m05_quality_dup_text"),
        CheckConstraint("duplicate_row_rate >= 0 and duplicate_row_rate <= 1", name="ck_m05_quality_dup_row"),
        Index("ix_core3_comment_quality_project_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_comment_quality_sku_sample", "sku_code", "sample_status"),
        Index("ix_core3_comment_quality_downstream_ready", "downstream_ready"),
        Index("ix_core3_comment_quality_review_required", "review_required"),
        Index("ix_core3_comment_quality_sentiment_gin", "sentiment_distribution_json", postgresql_using="gin"),
        Index("ix_core3_comment_quality_domain_gin", "domain_distribution_json", postgresql_using="gin"),
        Index("ix_core3_comment_quality_topic_gin", "topic_distribution_json", postgresql_using="gin"),
        Index("ix_core3_comment_quality_warning_gin", "warning_flags", postgresql_using="gin"),
        Index("ix_core3_comment_quality_blocked_gin", "blocked_reasons", postgresql_using="gin"),
    )

    comment_quality_profile_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    profile_key: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    raw_comment_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comment_unit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    distinct_comment_id_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    distinct_comment_text_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    usable_sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    low_value_unit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    low_value_sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_text_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    duplicate_row_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    empty_dimension_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    empty_dimension_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    sentiment_distribution_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    sentiment_unknown_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    sentiment_conflict_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    domain_distribution_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    topic_distribution_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    service_installation_share: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    product_experience_share: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    negative_sentence_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    sample_status: Mapped[str] = mapped_column(String(60), nullable=False, default="unknown", index=True)
    comment_usability_score: Mapped[Decimal] = mapped_column(
        Numeric(8, 6),
        nullable=False,
        default=Decimal("0.000000"),
    )
    quality_summary: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    warning_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    blocked_reasons: Mapped[list] = mapped_column(JSONBCompat, default=list)
    downstream_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m05_comment_evidence_v1")
    asset_version: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3CommentSignalCandidate(Base, AuditMixin):
    __tablename__ = "core3_comment_signal_candidate"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "signal_candidate_key",
            "rule_version",
            "asset_version",
            name="uq_core3_comment_signal_candidate_key",
        ),
        CheckConstraint(
            "signal_type in ('claim_validation', 'task_cue', 'target_group_cue', "
            "'battlefield_support', 'pain_point', 'price_perception', 'service_signal')",
            name="ck_m06_candidate_signal_type",
        ),
        CheckConstraint(
            "polarity in ('support', 'weaken', 'mixed', 'neutral', 'unknown')",
            name="ck_m06_candidate_polarity",
        ),
        CheckConstraint(
            "signal_strength_level in ('strong', 'medium', 'weak', 'blocked')",
            name="ck_m06_candidate_strength_level",
        ),
        CheckConstraint(
            "hard_spec_policy in ('experience_only', 'hard_spec_not_proven', 'service_only', "
            "'market_fact_required')",
            name="ck_m06_candidate_hard_spec_policy",
        ),
        CheckConstraint("signal_strength >= 0 and signal_strength <= 1", name="ck_m06_candidate_strength"),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_m06_candidate_confidence"),
        CheckConstraint("specificity_score >= 0 and specificity_score <= 1", name="ck_m06_candidate_specificity"),
        Index("ix_core3_comment_signal_candidate_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_comment_signal_candidate_sku_type", "sku_code", "signal_type"),
        Index("ix_core3_comment_signal_candidate_sku_target", "sku_code", "target_code_hint"),
        Index("ix_core3_comment_signal_candidate_atom", "comment_evidence_id"),
        Index("ix_core3_comment_signal_candidate_unit", "comment_unit_id"),
        Index("ix_core3_comment_signal_candidate_level", "signal_strength_level"),
        Index("ix_core3_comment_signal_candidate_review", "review_required"),
        Index("ix_core3_comment_signal_candidate_topic_gin", "topic_hints_json", postgresql_using="gin"),
        Index("ix_core3_comment_signal_candidate_entities_gin", "matched_entities_json", postgresql_using="gin"),
        Index("ix_core3_comment_signal_candidate_rules_gin", "matched_rules_json", postgresql_using="gin"),
        Index("ix_core3_comment_signal_candidate_quality_gin", "quality_flags", postgresql_using="gin"),
    )

    signal_candidate_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    signal_candidate_key: Mapped[str] = mapped_column(String(420), nullable=False, index=True)
    comment_unit_id: Mapped[str] = mapped_column(ForeignKey("core3_comment_unit.comment_unit_id"), index=True)
    comment_evidence_id: Mapped[str] = mapped_column(
        ForeignKey("core3_comment_evidence_atom.comment_evidence_id"),
        index=True,
    )
    comment_text_hash: Mapped[str | None] = mapped_column(String(120), index=True)
    sentence_hash: Mapped[str | None] = mapped_column(String(120), index=True)
    sentence_text: Mapped[str] = mapped_column(Text, nullable=False)
    signal_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target_code_hint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    target_name_hint: Mapped[str] = mapped_column(String(240), nullable=False)
    target_group_hint: Mapped[str | None] = mapped_column(String(160), index=True)
    polarity: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    signal_strength: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    signal_strength_level: Mapped[str] = mapped_column(String(40), nullable=False, default="blocked", index=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    confidence_level: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    specificity_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    sentiment_hint: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    domain_hints: Mapped[list] = mapped_column(JSONBCompat, default=list)
    primary_domain_hint: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown", index=True)
    topic_hints_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    matched_entities_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    matched_rules_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    cue_basis: Mapped[str] = mapped_column(String(80), nullable=False, default="explicit_keyword", index=True)
    hard_spec_policy: Mapped[str] = mapped_column(String(80), nullable=False, default="experience_only", index=True)
    service_guardrail_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    eligible_for_product_claim: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    eligible_for_service_claim: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    eligible_for_task: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    eligible_for_group: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    eligible_for_battlefield: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    low_value_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    duplicate_group_id: Mapped[str | None] = mapped_column(String(240), index=True)
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    blocked_reasons: Mapped[list] = mapped_column(JSONBCompat, default=list)
    source_m05_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    source_m02_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    optional_param_context_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    optional_claim_context_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m06_comment_downstream_signal_v1")
    asset_version: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3CommentDownstreamSignal(Base, AuditMixin):
    __tablename__ = "core3_comment_downstream_signal"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "signal_type",
            "target_code_hint",
            "polarity",
            "rule_version",
            "asset_version",
            name="uq_core3_comment_downstream_signal_key",
        ),
        CheckConstraint(
            "signal_type in ('claim_validation', 'task_cue', 'target_group_cue', "
            "'battlefield_support', 'pain_point', 'price_perception', 'service_signal')",
            name="ck_m06_signal_type",
        ),
        CheckConstraint(
            "polarity in ('support', 'weaken', 'mixed', 'neutral', 'unknown')",
            name="ck_m06_signal_polarity",
        ),
        CheckConstraint(
            "signal_level in ('strong', 'medium', 'weak', 'blocked')",
            name="ck_m06_signal_level",
        ),
        CheckConstraint("mention_count >= 0", name="ck_m06_signal_mention_count"),
        CheckConstraint("sentence_count >= 0", name="ck_m06_signal_sentence_count"),
        CheckConstraint("mention_rate >= 0 and mention_rate <= 1", name="ck_m06_signal_mention_rate"),
        CheckConstraint("signal_score >= 0 and signal_score <= 1", name="ck_m06_signal_score"),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_m06_signal_confidence"),
        Index("ix_core3_comment_downstream_signal_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_comment_downstream_signal_sku_type", "sku_code", "signal_type"),
        Index("ix_core3_comment_downstream_signal_type_target", "signal_type", "target_code_hint"),
        Index("ix_core3_comment_downstream_signal_level", "signal_level"),
        Index("ix_core3_comment_downstream_signal_confidence", "confidence_level"),
        Index("ix_core3_comment_downstream_signal_service_guardrail", "service_guardrail_flag"),
        Index("ix_core3_comment_downstream_signal_review", "review_required"),
        Index("ix_core3_comment_downstream_signal_quality_gin", "comment_quality_flags", postgresql_using="gin"),
        Index("ix_core3_comment_downstream_signal_phrases_gin", "representative_phrases", postgresql_using="gin"),
        Index("ix_core3_comment_downstream_signal_evidence_gin", "evidence_ids", postgresql_using="gin"),
        Index("ix_core3_comment_downstream_signal_policy_gin", "downstream_usage_policy_json", postgresql_using="gin"),
    )

    signal_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    signal_key: Mapped[str] = mapped_column(String(420), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target_code_hint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    target_name_hint: Mapped[str] = mapped_column(String(240), nullable=False)
    target_group_hint: Mapped[str | None] = mapped_column(String(160), index=True)
    polarity: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_comment_unit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    usable_sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mention_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    sentence_mention_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    positive_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    negative_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    neutral_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    positive_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    negative_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    mixed_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    signal_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    signal_level: Mapped[str] = mapped_column(String(40), nullable=False, default="blocked", index=True)
    specificity_avg: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    evidence_quality_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    sample_status: Mapped[str] = mapped_column(String(60), nullable=False, default="unknown", index=True)
    comment_quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    representative_phrases: Mapped[list] = mapped_column(JSONBCompat, default=list)
    top_candidate_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    service_guardrail_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    hard_spec_policy: Mapped[str] = mapped_column(String(80), nullable=False, default="experience_only", index=True)
    downstream_usage_policy_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    quality_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    confidence_level: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m06_comment_downstream_signal_v1")
    asset_version: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SkuCommentSignalProfile(Base, AuditMixin):
    __tablename__ = "core3_sku_comment_signal_profile"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "rule_version",
            "asset_version",
            name="uq_core3_sku_comment_signal_profile_key",
        ),
        CheckConstraint(
            "comment_signal_confidence >= 0 and comment_signal_confidence <= 1",
            name="ck_m06_profile_confidence",
        ),
        Index("ix_core3_sku_comment_signal_profile_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_sku_comment_signal_profile_sku", "sku_code"),
        Index("ix_core3_sku_comment_signal_profile_confidence", "comment_signal_confidence"),
        Index("ix_core3_sku_comment_signal_profile_claim_ready", "claim_validation_ready"),
        Index("ix_core3_sku_comment_signal_profile_task_ready", "task_cue_ready"),
        Index("ix_core3_sku_comment_signal_profile_battlefield_ready", "battlefield_support_ready"),
        Index("ix_core3_sku_comment_signal_profile_review", "review_required"),
        Index("ix_core3_sku_comment_signal_profile_summary_gin", "comment_signal_summary_json", postgresql_using="gin"),
        Index("ix_core3_sku_comment_signal_profile_quality_gin", "quality_flags", postgresql_using="gin"),
        Index("ix_core3_sku_comment_signal_profile_review_gin", "review_issue_summary_json", postgresql_using="gin"),
        Index("ix_core3_sku_comment_signal_profile_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    sku_comment_signal_profile_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    profile_key: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    comment_signal_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    claim_validation_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    task_cue_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    target_group_cue_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    battlefield_support_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    pain_risk_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    price_perception_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    service_signal_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    strong_signal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    medium_signal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    weak_signal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocked_signal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    claim_validation_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    task_cue_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    target_group_cue_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    battlefield_support_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    comment_signal_confidence: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        default=Decimal("0.0000"),
    )
    confidence_level: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    review_issue_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m06_comment_downstream_signal_v1")
    asset_version: Mapped[str] = mapped_column(String(80), nullable=False, default="default")
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SkuClaimCommentValidation(Base, AuditMixin):
    __tablename__ = "core3_sku_claim_comment_validation"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "claim_code",
            "rule_version",
            "seed_version",
            name="uq_core3_claim_comment_validation_key",
        ),
        CheckConstraint(
            "m04b_claim_type in ('technical_hard', 'technical_experience_mixed', "
            "'experience_scenario', 'service', 'value', 'unknown')",
            name="ck_m04b_validation_claim_type",
        ),
        CheckConstraint(
            "comment_effect in ('enhance', 'weaken', 'neutral', 'contradict', "
            "'comment_only_hint', 'blocked')",
            name="ck_m04b_validation_comment_effect",
        ),
        CheckConstraint(
            "perception_status in ('validated', 'weak_perception', 'contradicted', "
            "'insufficient_comment', 'not_applicable', 'service_guarded', 'comment_only_pending')",
            name="ck_m04b_validation_perception_status",
        ),
        CheckConstraint("mention_count >= 0", name="ck_m04b_validation_mention_count"),
        CheckConstraint("sentence_count >= 0", name="ck_m04b_validation_sentence_count"),
        CheckConstraint("valid_comment_unit_count >= 0", name="ck_m04b_validation_unit_count"),
        CheckConstraint("mention_rate >= 0 and mention_rate <= 1", name="ck_m04b_validation_mention_rate"),
        CheckConstraint("positive_rate >= 0 and positive_rate <= 1", name="ck_m04b_validation_positive_rate"),
        CheckConstraint("negative_rate >= 0 and negative_rate <= 1", name="ck_m04b_validation_negative_rate"),
        CheckConstraint("comment_validation_score >= 0 and comment_validation_score <= 1", name="ck_m04b_validation_score"),
        CheckConstraint("comment_risk_score >= 0 and comment_risk_score <= 1", name="ck_m04b_validation_risk"),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_m04b_validation_confidence"),
        Index("ix_core3_claim_comment_validation_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_claim_comment_validation_sku_claim", "sku_code", "claim_code"),
        Index("ix_core3_claim_comment_validation_effect", "claim_code", "comment_effect"),
        Index("ix_core3_claim_comment_validation_perception", "perception_status"),
        Index("ix_core3_claim_comment_validation_source_status", "claim_source_status"),
        Index("ix_core3_claim_comment_validation_type", "m04b_claim_type"),
        Index("ix_core3_claim_comment_validation_service", "service_guardrail_flag"),
        Index("ix_core3_claim_comment_validation_review", "review_required"),
        Index("ix_core3_claim_comment_validation_phrases_gin", "representative_phrases", postgresql_using="gin"),
        Index("ix_core3_claim_comment_validation_signals_gin", "comment_signal_ids", postgresql_using="gin"),
        Index("ix_core3_claim_comment_validation_evidence_gin", "comment_evidence_ids", postgresql_using="gin"),
        Index("ix_core3_claim_comment_validation_quality_gin", "quality_flags", postgresql_using="gin"),
    )

    claim_comment_validation_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    validation_key: Mapped[str] = mapped_column(String(420), nullable=False, index=True)
    claim_activation_base_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_claim_activation_base.claim_activation_base_id"), index=True)
    claim_source_status_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_claim_source_status.claim_source_status_id"), index=True)
    claim_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    claim_name: Mapped[str] = mapped_column(String(240), nullable=False)
    claim_group: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    m04b_claim_type: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown", index=True)
    base_activation_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    base_activation_level: Mapped[str] = mapped_column(String(60), nullable=False, default="unknown")
    base_activation_basis: Mapped[str] = mapped_column(String(80), nullable=False, default="insufficient", index=True)
    param_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    promo_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    claim_source_status: Mapped[str] = mapped_column(String(80), nullable=False, default="claim_data_insufficient", index=True)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    valid_comment_unit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    mention_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    positive_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    negative_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    positive_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    negative_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    specificity_avg: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    evidence_quality_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    domain_match_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    comment_validation_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    comment_risk_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    comment_effect: Mapped[str] = mapped_column(String(80), nullable=False, default="neutral", index=True)
    perception_status: Mapped[str] = mapped_column(String(80), nullable=False, default="insufficient_comment", index=True)
    hard_spec_protection_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    service_guardrail_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    comment_only_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    weak_perception_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    contradiction_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    representative_phrases: Mapped[list] = mapped_column(JSONBCompat, default=list)
    comment_signal_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    comment_candidate_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    comment_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    base_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    confidence_level: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m04b_claim_comment_enhancement_v1")
    seed_version: Mapped[str] = mapped_column(String(80), nullable=False, default="tv_core3_mvp_seed_v0_2")
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SkuClaimActivation(Base, AuditMixin):
    __tablename__ = "core3_sku_claim_activation"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "claim_code",
            "rule_version",
            "seed_version",
            name="uq_core3_sku_claim_activation_key",
        ),
        CheckConstraint("final_activation_score >= 0 and final_activation_score <= 1", name="ck_m04b_activation_final_score"),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_m04b_activation_confidence"),
        CheckConstraint(
            "activation_level in ('high', 'medium', 'low', 'unknown', 'review_required')",
            name="ck_m04b_activation_level",
        ),
        Index("ix_core3_sku_claim_activation_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_sku_claim_activation_sku_claim", "sku_code", "claim_code"),
        Index("ix_core3_sku_claim_activation_claim_level", "claim_code", "activation_level"),
        Index("ix_core3_sku_claim_activation_type", "m04b_claim_type"),
        Index("ix_core3_sku_claim_activation_basis", "activation_basis"),
        Index("ix_core3_sku_claim_activation_perception", "perception_status"),
        Index("ix_core3_sku_claim_activation_missing_claim", "missing_structured_claim_flag"),
        Index("ix_core3_sku_claim_activation_param_only", "param_only_flag"),
        Index("ix_core3_sku_claim_activation_comment_only", "comment_only_flag"),
        Index("ix_core3_sku_claim_activation_review", "review_required"),
        Index("ix_core3_sku_claim_activation_policy_gin", "downstream_usage_policy_json", postgresql_using="gin"),
        Index("ix_core3_sku_claim_activation_score_gin", "score_breakdown_json", postgresql_using="gin"),
        Index("ix_core3_sku_claim_activation_evidence_gin", "evidence_ids", postgresql_using="gin"),
        Index("ix_core3_sku_claim_activation_missing_gin", "missing_signals", postgresql_using="gin"),
        Index("ix_core3_sku_claim_activation_conflict_gin", "conflict_flags", postgresql_using="gin"),
        Index("ix_core3_sku_claim_activation_quality_gin", "quality_flags", postgresql_using="gin"),
    )

    claim_activation_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    activation_key: Mapped[str] = mapped_column(String(420), nullable=False, index=True)
    claim_activation_base_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_claim_activation_base.claim_activation_base_id"), index=True)
    claim_comment_validation_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_claim_comment_validation.claim_comment_validation_id"), index=True)
    claim_source_status_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_claim_source_status.claim_source_status_id"), index=True)
    claim_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    claim_name: Mapped[str] = mapped_column(String(240), nullable=False)
    claim_group: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    m04b_claim_type: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown", index=True)
    param_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    promo_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    base_activation_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    comment_validation_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    comment_risk_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    final_activation_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    base_activation_level: Mapped[str] = mapped_column(String(60), nullable=False, default="unknown")
    activation_level: Mapped[str] = mapped_column(String(60), nullable=False, default="unknown", index=True)
    activation_basis: Mapped[str] = mapped_column(String(80), nullable=False, default="insufficient", index=True)
    perception_status: Mapped[str] = mapped_column(String(80), nullable=False, default="insufficient_comment", index=True)
    claim_source_status: Mapped[str] = mapped_column(String(80), nullable=False, default="claim_data_insufficient", index=True)
    comment_effect: Mapped[str] = mapped_column(String(80), nullable=False, default="neutral", index=True)
    hard_spec_protection_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    service_guardrail_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    missing_structured_claim_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    param_only_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    promo_only_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    comment_only_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    weak_perception_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    contradiction_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    value_requires_market_validation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    downstream_usage_policy_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    score_breakdown_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    missing_signals: Mapped[list] = mapped_column(JSONBCompat, default=list)
    conflict_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    param_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    promo_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    comment_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    comment_signal_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    representative_phrases: Mapped[list] = mapped_column(JSONBCompat, default=list)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    confidence_level: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m04b_claim_comment_enhancement_v1")
    seed_version: Mapped[str] = mapped_column(String(80), nullable=False, default="tv_core3_mvp_seed_v0_2")
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3ClaimCommentReviewIssue(Base, AuditMixin):
    __tablename__ = "core3_claim_comment_review_issue"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "claim_code",
            "issue_type",
            "rule_version",
            "seed_version",
            name="uq_core3_claim_comment_review_issue_key",
        ),
        CheckConstraint(
            "issue_type in ('comment_only', 'spec_claimed_by_comment', 'service_mismatch', "
            "'comment_contradiction', 'weak_perception', 'missing_structured_claim_enhanced', "
            "'param_only_core_claim', 'promo_only_param_missing', 'value_requires_market_validation', "
            "'low_quality_comment_signal')",
            name="ck_m04b_review_issue_type",
        ),
        CheckConstraint(
            "severity in ('info', 'warning', 'review_required', 'blocked')",
            name="ck_m04b_review_issue_severity",
        ),
        CheckConstraint(
            "downstream_policy in ('continue_with_warning', 'require_approval', 'block_downstream')",
            name="ck_m04b_review_issue_downstream_policy",
        ),
        CheckConstraint(
            "issue_status in ('open', 'approved', 'rejected', 'waived', 'closed')",
            name="ck_m04b_review_issue_status",
        ),
        Index("ix_core3_claim_comment_issue_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_claim_comment_issue_sku_claim", "sku_code", "claim_code"),
        Index("ix_core3_claim_comment_issue_type", "issue_type"),
        Index("ix_core3_claim_comment_issue_severity", "severity"),
        Index("ix_core3_claim_comment_issue_status", "issue_status"),
        Index("ix_core3_claim_comment_issue_review", "review_required"),
        Index("ix_core3_claim_comment_issue_evidence_gin", "evidence_ids", postgresql_using="gin"),
        Index("ix_core3_claim_comment_issue_signals_gin", "comment_signal_ids", postgresql_using="gin"),
        Index("ix_core3_claim_comment_issue_quality_gin", "quality_flags", postgresql_using="gin"),
    )

    issue_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    issue_key: Mapped[str] = mapped_column(String(420), nullable=False, index=True)
    claim_activation_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_claim_activation.claim_activation_id"), index=True)
    claim_comment_validation_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_claim_comment_validation.claim_comment_validation_id"), index=True)
    claim_activation_base_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_claim_activation_base.claim_activation_base_id"), index=True)
    claim_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    claim_name: Mapped[str] = mapped_column(String(240), nullable=False)
    issue_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(40), nullable=False, default="warning", index=True)
    business_note: Mapped[str] = mapped_column(Text, nullable=False)
    technical_note: Mapped[str | None] = mapped_column(Text)
    suggested_action: Mapped[str] = mapped_column(Text, nullable=False)
    downstream_policy: Mapped[str] = mapped_column(String(80), nullable=False, default="continue_with_warning", index=True)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    comment_signal_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    issue_status: Mapped[str] = mapped_column(String(60), nullable=False, default="open", index=True)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m04b_claim_comment_enhancement_v1")
    seed_version: Mapped[str] = mapped_column(String(80), nullable=False, default="tv_core3_mvp_seed_v0_2")
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="review_required", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3MarketSignal(Base, AuditMixin):
    __tablename__ = "core3_market_signal"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "analysis_window",
            "signal_code",
            "comparison_scope",
            "rule_version",
            name="uq_core3_market_signal_key",
        ),
        CheckConstraint("signal_strength >= 0 and signal_strength <= 1", name="ck_m07_signal_strength"),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_m07_signal_confidence"),
        Index("ix_core3_m07_signal_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m07_signal_sku_code", "sku_code", "signal_code"),
        Index("ix_core3_m07_signal_window_code", "analysis_window", "signal_code"),
        Index("ix_core3_m07_signal_level", "signal_level"),
        Index("ix_core3_m07_signal_scope", "comparison_scope"),
        Index("ix_core3_m07_signal_review", "review_required"),
        Index("ix_core3_m07_signal_basis_gin", "basis_value_json", postgresql_using="gin"),
        Index("ix_core3_m07_signal_usage_gin", "downstream_usage_json", postgresql_using="gin"),
        Index("ix_core3_m07_signal_quality_gin", "quality_flags", postgresql_using="gin"),
        Index("ix_core3_m07_signal_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    market_signal_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_market_profile_id: Mapped[str] = mapped_column(
        ForeignKey("core3_sku_market_profile.sku_market_profile_id"),
        index=True,
    )
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    signal_key: Mapped[str] = mapped_column(String(480), nullable=False, index=True)
    analysis_window: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    signal_code: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    signal_name: Mapped[str] = mapped_column(String(160), nullable=False)
    signal_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6))
    signal_strength: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    signal_level: Mapped[str] = mapped_column(String(40), nullable=False, default="weak", index=True)
    basis_metric: Mapped[str] = mapped_column(String(120), nullable=False)
    basis_value_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    comparison_scope: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    comparison_scope_key: Mapped[str | None] = mapped_column(String(160), index=True)
    polarity: Mapped[str] = mapped_column(String(40), nullable=False, default="neutral", index=True)
    downstream_usage_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    confidence_level: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    sample_status: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m07_market_profile_v1")
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3ComparablePoolBaseline(Base, AuditMixin):
    __tablename__ = "core3_comparable_pool_baseline"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "target_sku_code",
            "analysis_window",
            "pool_type",
            "rule_version",
            name="uq_core3_comparable_pool_key",
        ),
        CheckConstraint("pool_confidence >= 0 and pool_confidence <= 1", name="ck_m07_pool_confidence"),
        Index("ix_core3_m07_pool_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m07_pool_target_type", "target_sku_code", "pool_type"),
        Index("ix_core3_m07_pool_window_type", "analysis_window", "pool_type"),
        Index("ix_core3_m07_pool_sample_status", "sample_status"),
        Index("ix_core3_m07_pool_sku_count", "pool_sku_count"),
        Index("ix_core3_m07_pool_condition_gin", "pool_condition_json", postgresql_using="gin"),
        Index("ix_core3_m07_pool_candidates_gin", "candidate_sku_codes", postgresql_using="gin"),
        Index("ix_core3_m07_pool_price_dist_gin", "price_distribution_json", postgresql_using="gin"),
        Index("ix_core3_m07_pool_quality_gin", "quality_flags", postgresql_using="gin"),
        Index("ix_core3_m07_pool_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    pool_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    pool_key: Mapped[str] = mapped_column(String(480), nullable=False, index=True)
    target_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    target_model_name: Mapped[str | None] = mapped_column(String(240))
    target_brand_name: Mapped[str | None] = mapped_column(String(160))
    analysis_window: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    pool_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    pool_condition_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    candidate_sku_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    pool_sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    valid_member_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_included: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    target_size_segment: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    target_price_band: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    median_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    median_volume: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    median_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    price_distribution_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    volume_distribution_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    amount_distribution_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    platform_distribution_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    pool_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    sample_status: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    basis: Mapped[str] = mapped_column(Text, nullable=False)
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m07_market_profile_v1")
    pool_rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m07_pool_v1")
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3MarketPoolMember(Base, AuditMixin):
    __tablename__ = "core3_market_pool_member"
    __table_args__ = (
        UniqueConstraint(
            "pool_id",
            "target_sku_code",
            "member_sku_code",
            "rule_version",
            name="uq_core3_market_pool_member_key",
        ),
        CheckConstraint("platform_overlap_score >= 0 and platform_overlap_score <= 1", name="ck_m07_member_platform_overlap"),
        CheckConstraint("channel_overlap_score >= 0 and channel_overlap_score <= 1", name="ck_m07_member_channel_overlap"),
        CheckConstraint("relation_strength >= 0 and relation_strength <= 1", name="ck_m07_member_relation_strength"),
        Index("ix_core3_m07_member_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m07_member_target_member", "target_sku_code", "member_sku_code"),
        Index("ix_core3_m07_member_pool", "pool_id"),
        Index("ix_core3_m07_member_size_relation", "size_relation"),
        Index("ix_core3_m07_member_price_relation", "price_band_relation"),
        Index("ix_core3_m07_member_platform_overlap", "platform_overlap_score"),
        Index("ix_core3_m07_member_quality_gin", "quality_flags", postgresql_using="gin"),
        Index("ix_core3_m07_member_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    pool_member_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    pool_id: Mapped[str] = mapped_column(ForeignKey("core3_comparable_pool_baseline.pool_id"), index=True)
    target_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    member_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    analysis_window: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    member_model_name: Mapped[str | None] = mapped_column(String(240))
    member_brand_name: Mapped[str | None] = mapped_column(String(160))
    is_target_self: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    size_relation: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    price_band_relation: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    platform_overlap_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    channel_overlap_score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    price_gap_to_target: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    price_gap_pct_to_target: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    volume_gap_to_target: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    amount_gap_to_target: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    member_price_percentile_in_pool: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    member_volume_percentile_in_pool: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    member_amount_percentile_in_pool: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    member_market_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    relation_strength: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    quality_flags: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m07_market_profile_v1")
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SkuSignalProfile(Base, AuditMixin):
    __tablename__ = "core3_sku_signal_profile"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "profile_scope",
            "feature_version",
            "profile_hash",
            name="uq_core3_sku_signal_profile_hash",
        ),
        CheckConstraint("data_completeness_score >= 0 and data_completeness_score <= 1", name="ck_m08_profile_completeness"),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_m08_profile_confidence"),
        Index("ix_core3_m08_profile_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m08_profile_sku", "project_id", "category_code", "batch_id", "sku_code"),
        Index("ix_core3_m08_profile_current", "project_id", "category_code", "batch_id", "sku_code", "profile_scope", "feature_version", "is_current"),
        Index("ix_core3_m08_profile_status", "project_id", "category_code", "batch_id", "profile_status", "review_required"),
        Index("ix_core3_m08_profile_hash", "project_id", "category_code", "batch_id", "profile_hash"),
        Index("ix_core3_m08_profile_signal_index_gin", "business_signal_index_json", postgresql_using="gin"),
        Index("ix_core3_m08_profile_missing_gin", "missing_signals_json", postgresql_using="gin"),
        Index("ix_core3_m08_profile_risk_gin", "risk_signals_json", postgresql_using="gin"),
        Index("ix_core3_m08_profile_evidence_gin", "representative_evidence_ids", postgresql_using="gin"),
    )

    sku_signal_profile_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_code: Mapped[str | None] = mapped_column(String(160))
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    profile_scope: Mapped[str] = mapped_column(String(80), nullable=False, default="sku_default", index=True)
    analysis_window: Mapped[str] = mapped_column(String(80), nullable=False, default="full_observed_window", index=True)
    source_coverage_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    source_profile_refs_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    sku_master_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    core_params_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    param_profile_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    claim_activation_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    claim_evidence_breakdown_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    comment_signal_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    comment_quality_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    market_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    market_recent_windows_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    market_signal_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    comparable_pool_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    business_signal_index_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    missing_signals_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    risk_signals_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    domain_completeness_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    data_completeness_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    domain_confidence_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    confidence_level: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    profile_status: Mapped[str] = mapped_column(String(80), nullable=False, default="limited", index=True)
    downstream_ready_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    representative_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    profile_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m08_sku_signal_profile_v1")
    feature_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m08_v1", index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SkuSignalEvidenceMatrix(Base, AuditMixin):
    __tablename__ = "core3_sku_signal_evidence_matrix"
    __table_args__ = (
        UniqueConstraint(
            "sku_signal_profile_id",
            "domain",
            "sub_domain",
            "evidence_role",
            "feature_version",
            name="uq_core3_sku_signal_matrix_key",
        ),
        CheckConstraint("evidence_count >= 0", name="ck_m08_matrix_evidence_count"),
        CheckConstraint("high_confidence_count >= 0", name="ck_m08_matrix_high_count"),
        CheckConstraint("medium_confidence_count >= 0", name="ck_m08_matrix_medium_count"),
        CheckConstraint("low_confidence_count >= 0", name="ck_m08_matrix_low_count"),
        CheckConstraint("domain_confidence >= 0 and domain_confidence <= 1", name="ck_m08_matrix_confidence"),
        Index("ix_core3_m08_matrix_profile", "sku_signal_profile_id", "domain", "sub_domain"),
        Index("ix_core3_m08_matrix_sku_domain", "project_id", "category_code", "batch_id", "sku_code", "domain"),
        Index("ix_core3_m08_matrix_missing", "project_id", "category_code", "batch_id", "missing_flag", "review_required"),
        Index("ix_core3_m08_matrix_evidence_gin", "representative_evidence_ids", postgresql_using="gin"),
        Index("ix_core3_m08_matrix_risk_gin", "risk_flags_json", postgresql_using="gin"),
    )

    sku_signal_evidence_matrix_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    sku_signal_profile_id: Mapped[str] = mapped_column(ForeignKey("core3_sku_signal_profile.sku_signal_profile_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    domain: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    sub_domain: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    feature_code: Mapped[str | None] = mapped_column(String(160), index=True)
    evidence_role: Mapped[str] = mapped_column(String(80), nullable=False, default="representative", index=True)
    coverage_status: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown", index=True)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    high_confidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    medium_confidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    low_confidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    representative_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_query_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    source_record_refs_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    missing_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    missing_reason_code: Mapped[str | None] = mapped_column(String(160), index=True)
    risk_flags_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    domain_confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m08_sku_signal_profile_v1")
    feature_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m08_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3SkuDownstreamFeatureView(Base, AuditMixin):
    __tablename__ = "core3_sku_downstream_feature_view"
    __table_args__ = (
        UniqueConstraint(
            "sku_signal_profile_id",
            "for_module",
            "view_role",
            "view_schema_version",
            "view_hash",
            name="uq_core3_downstream_feature_view_hash",
        ),
        Index("ix_core3_m08_view_current", "project_id", "category_code", "batch_id", "sku_code", "for_module", "view_role", "view_schema_version", "is_current"),
        Index("ix_core3_m08_view_module", "project_id", "category_code", "batch_id", "for_module", "ready_for_module"),
        Index("ix_core3_m08_view_hash", "project_id", "category_code", "batch_id", "profile_hash", "view_hash"),
        Index("ix_core3_m08_view_payload_gin", "feature_payload_json", postgresql_using="gin"),
        Index("ix_core3_m08_view_missing_gin", "required_missing_fields_json", postgresql_using="gin"),
        Index("ix_core3_m08_view_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    sku_downstream_feature_view_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    sku_signal_profile_id: Mapped[str] = mapped_column(ForeignKey("core3_sku_signal_profile.sku_signal_profile_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    for_module: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    view_role: Mapped[str] = mapped_column(String(80), nullable=False, default="primary_input", index=True)
    view_schema_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m08_downstream_feature_view_v1", index=True)
    required_feature_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    optional_feature_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    feature_payload_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    feature_quality_flags_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    required_missing_fields_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    optional_missing_fields_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_matrix_refs_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    profile_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    view_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    dependency_hash_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    ready_for_module: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    block_reason_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="m08_sku_signal_profile_v1")
    feature_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m08_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3CommentNativeSignal(Base, AuditMixin):
    __tablename__ = "core3_comment_native_signal"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "native_signal_code",
            "source_rule_version",
            name="uq_core3_m084_native_signal_key",
        ),
        CheckConstraint("sentence_count >= 0", name="ck_m084_signal_sentence_count"),
        CheckConstraint("sku_count >= 0", name="ck_m084_signal_sku_count"),
        CheckConstraint("service_sentence_count >= 0", name="ck_m084_signal_service_count"),
        CheckConstraint("low_value_excluded_count >= 0", name="ck_m084_signal_low_value_count"),
        CheckConstraint("avg_strength_score >= 0 and avg_strength_score <= 1", name="ck_m084_signal_strength"),
        CheckConstraint("specificity_score >= 0 and specificity_score <= 1", name="ck_m084_signal_specificity"),
        CheckConstraint("comment_confidence >= 0 and comment_confidence <= 1", name="ck_m084_signal_confidence"),
        Index("ix_core3_m084_signal_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m084_signal_type", "signal_type", "native_signal_code"),
        Index("ix_core3_m084_signal_sku_count", "sku_count", "sentence_count"),
        Index("ix_core3_m084_signal_service", "service_context_flag"),
        Index("ix_core3_m084_signal_current", "project_id", "category_code", "batch_id", "is_current"),
        Index("ix_core3_m084_signal_evidence_gin", "representative_evidence_ids", postgresql_using="gin"),
        Index("ix_core3_m084_signal_keywords_gin", "native_keyword_json", postgresql_using="gin"),
    )

    native_signal_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    native_signal_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    native_signal_name_cn: Mapped[str] = mapped_column(String(240), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_comment_domain: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown", index=True)
    sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    strong_sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    positive_sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    negative_sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    service_sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    low_value_excluded_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_strength_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    specificity_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    comment_confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    native_keyword_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    sku_distribution_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    representative_phrase_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    representative_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    product_anchor_hint_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    service_context_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    signal_status: Mapped[str] = mapped_column(String(60), nullable=False, default="active", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    source_rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="core3_mvp_real_data_v2_m08_4_v1")
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3NativeDimensionCandidate(Base, AuditMixin):
    __tablename__ = "core3_native_dimension_candidate"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "dimension_type",
            "native_dimension_code",
            "rule_version",
            name="uq_core3_m084_candidate_key",
        ),
        CheckConstraint("sentence_count >= 0", name="ck_m084_candidate_sentence_count"),
        CheckConstraint("sku_count >= 0", name="ck_m084_candidate_sku_count"),
        CheckConstraint("strong_sku_count >= 0", name="ck_m084_candidate_strong_sku_count"),
        CheckConstraint("native_support_score >= 0 and native_support_score <= 1", name="ck_m084_candidate_support"),
        CheckConstraint("product_anchor_score >= 0 and product_anchor_score <= 1", name="ck_m084_candidate_anchor"),
        CheckConstraint("distinctiveness_score >= 0 and distinctiveness_score <= 1", name="ck_m084_candidate_distinct"),
        Index("ix_core3_m084_candidate_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m084_candidate_type", "dimension_type", "candidate_status"),
        Index("ix_core3_m084_candidate_support", "native_support_score", "sku_count"),
        Index("ix_core3_m084_candidate_service", "service_context_flag"),
        Index("ix_core3_m084_candidate_current", "project_id", "category_code", "batch_id", "is_current"),
        Index("ix_core3_m084_candidate_source_gin", "source_signal_codes", postgresql_using="gin"),
        Index("ix_core3_m084_candidate_evidence_gin", "representative_evidence_ids", postgresql_using="gin"),
    )

    native_dimension_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    dimension_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    native_dimension_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    native_dimension_name_cn: Mapped[str] = mapped_column(String(240), nullable=False)
    definition_draft_cn: Mapped[str] = mapped_column(Text, nullable=False)
    source_signal_codes: Mapped[list] = mapped_column(JSONBCompat, default=list)
    include_keyword_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    exclude_keyword_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    strong_sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    native_support_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    product_anchor_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    distinctiveness_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    representative_phrase_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    representative_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    support_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    service_context_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    candidate_status: Mapped[str] = mapped_column(String(80), nullable=False, default="candidate", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="core3_mvp_real_data_v2_m08_4_v1")
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3NativeDimensionSkuSupport(Base, AuditMixin):
    __tablename__ = "core3_native_dimension_sku_support"
    __table_args__ = (
        UniqueConstraint(
            "native_dimension_id",
            "sku_code",
            "rule_version",
            name="uq_core3_m084_sku_support_key",
        ),
        CheckConstraint("comment_sentence_count >= 0", name="ck_m084_support_sentence_count"),
        CheckConstraint("support_score >= 0 and support_score <= 1", name="ck_m084_support_score"),
        CheckConstraint("comment_support_score >= 0 and comment_support_score <= 1", name="ck_m084_comment_support"),
        CheckConstraint("product_anchor_score >= 0 and product_anchor_score <= 1", name="ck_m084_support_anchor"),
        CheckConstraint("market_anchor_score >= 0 and market_anchor_score <= 1", name="ck_m084_support_market"),
        Index("ix_core3_m084_support_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m084_support_sku", "sku_code", "dimension_type"),
        Index("ix_core3_m084_support_dimension", "native_dimension_id", "support_level"),
        Index("ix_core3_m084_support_current", "project_id", "category_code", "batch_id", "is_current"),
        Index("ix_core3_m084_support_evidence_gin", "representative_evidence_ids", postgresql_using="gin"),
    )

    native_dimension_sku_support_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    native_dimension_id: Mapped[str] = mapped_column(ForeignKey("core3_native_dimension_candidate.native_dimension_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    dimension_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    native_dimension_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    comment_sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    comment_support_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    product_anchor_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    market_anchor_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    support_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    support_level: Mapped[str] = mapped_column(String(40), nullable=False, default="weak", index=True)
    evidence_breakdown_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    representative_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    support_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    service_context_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="core3_mvp_real_data_v2_m08_4_v1")
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3NativeDimensionAlignmentProposal(Base, AuditMixin):
    __tablename__ = "core3_native_dimension_alignment_proposal"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "alignment_key",
            "rule_version",
            name="uq_core3_m084_alignment_key",
        ),
        CheckConstraint("alignment_score >= 0 and alignment_score <= 1", name="ck_m084_alignment_score"),
        Index("ix_core3_m084_alignment_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m084_alignment_seed", "seed_dimension_type", "seed_dimension_code"),
        Index("ix_core3_m084_alignment_native", "native_dimension_code"),
        Index("ix_core3_m084_alignment_action", "proposed_action", "review_required"),
        Index("ix_core3_m084_alignment_current", "project_id", "category_code", "batch_id", "is_current"),
    )

    alignment_proposal_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    native_dimension_id: Mapped[str | None] = mapped_column(ForeignKey("core3_native_dimension_candidate.native_dimension_id"), index=True)
    alignment_key: Mapped[str] = mapped_column(String(360), nullable=False, index=True)
    seed_dimension_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    seed_dimension_code: Mapped[str | None] = mapped_column(String(160), index=True)
    seed_dimension_name_cn: Mapped[str | None] = mapped_column(String(240))
    native_dimension_code: Mapped[str | None] = mapped_column(String(160), index=True)
    native_dimension_name_cn: Mapped[str | None] = mapped_column(String(240))
    alignment_relation: Mapped[str] = mapped_column(String(80), nullable=False, default="unmatched", index=True)
    alignment_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    proposed_action: Mapped[str] = mapped_column(String(80), nullable=False, default="review", index=True)
    reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    downstream_effect_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="open", index=True)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="core3_mvp_real_data_v2_m08_4_v1")
    seed_version: Mapped[str] = mapped_column(String(80), nullable=False, default="tv_core3_mvp_seed_v0_2")
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3NativeDimensionReviewIssue(Base, AuditMixin):
    __tablename__ = "core3_native_dimension_review_issue"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "issue_key",
            "rule_version",
            name="uq_core3_m084_review_issue_key",
        ),
        Index("ix_core3_m084_issue_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m084_issue_object", "object_type", "object_code"),
        Index("ix_core3_m084_issue_status", "severity", "review_status"),
        Index("ix_core3_m084_issue_current", "project_id", "category_code", "batch_id", "is_current"),
    )

    native_dimension_issue_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    issue_key: Mapped[str] = mapped_column(String(360), nullable=False, index=True)
    issue_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    issue_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(40), nullable=False, default="warning", index=True)
    object_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    object_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    issue_message_cn: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    suggested_action_cn: Mapped[str] = mapped_column(Text, nullable=False)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="open", index=True)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="core3_mvp_real_data_v2_m08_4_v1")
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3DimensionOntologyVersion(Base, AuditMixin):
    __tablename__ = "core3_dimension_ontology_version"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "ontology_version",
            name="uq_core3_dimension_ontology_version_key",
        ),
        Index("ix_core3_dimension_ontology_version_active", "project_id", "category_code", "batch_id", "status", "is_current"),
        Index("ix_core3_dimension_ontology_version_seed_hash", "base_seed_hash"),
        Index("ix_core3_dimension_ontology_version_input", "source_profile_batch_hash"),
    )

    ontology_version_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    ontology_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    base_seed_version: Mapped[str] = mapped_column(String(80), nullable=False)
    base_seed_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    source_profile_batch_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    calibration_scope: Mapped[str] = mapped_column(String(80), nullable=False, default="project_batch")
    status: Mapped[str] = mapped_column(String(60), nullable=False, default="active", index=True)
    active_from_run_id: Mapped[str | None] = mapped_column(String(120), index=True)
    dimension_count_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    quality_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="core3_mvp_real_data_v2_m08_5_v1")
    seed_version: Mapped[str] = mapped_column(String(80), nullable=False, default="tv_core3_mvp_seed_v0_2")
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime)


class Core3DimensionDefinition(Base, AuditMixin):
    __tablename__ = "core3_dimension_definition"
    __table_args__ = (
        UniqueConstraint(
            "ontology_version_id",
            "dimension_type",
            "dimension_code",
            name="uq_core3_dimension_definition_key",
        ),
        CheckConstraint("distinctiveness_score >= 0 and distinctiveness_score <= 1", name="ck_m085_definition_distinctiveness"),
        CheckConstraint("support_score >= 0 and support_score <= 1", name="ck_m085_definition_support"),
        CheckConstraint("sku_coverage_count >= 0", name="ck_m085_definition_sku_count"),
        CheckConstraint("strong_sku_coverage_count >= 0", name="ck_m085_definition_strong_sku_count"),
        Index("ix_core3_dimension_definition_type", "ontology_version_id", "dimension_type"),
        Index("ix_core3_dimension_definition_status", "definition_status"),
        Index("ix_core3_dimension_definition_boundary", "boundary_policy"),
        Index("ix_core3_dimension_definition_batch", "project_id", "category_code", "batch_id"),
    )

    dimension_definition_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    ontology_version_id: Mapped[str] = mapped_column(ForeignKey("core3_dimension_ontology_version.ontology_version_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    dimension_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    dimension_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    base_dimension_code: Mapped[str | None] = mapped_column(String(160), index=True)
    dimension_name_cn: Mapped[str] = mapped_column(String(240), nullable=False)
    definition_cn: Mapped[str] = mapped_column(Text, nullable=False)
    business_question_cn: Mapped[str] = mapped_column(Text, nullable=False)
    include_rule_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    exclude_rule_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    required_evidence_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    optional_evidence_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    negative_evidence_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    boundary_policy: Mapped[str] = mapped_column(String(80), nullable=False, default="product_value", index=True)
    allocation_policy: Mapped[str] = mapped_column(String(120), nullable=False, default="candidate_only", index=True)
    candidate_trigger_policy_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    profile_eligibility_policy_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    downstream_policy_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    distinctiveness_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    support_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    sku_coverage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    strong_sku_coverage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    definition_status: Mapped[str] = mapped_column(String(80), nullable=False, default="active", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="core3_mvp_real_data_v2_m08_5_v1")
    seed_version: Mapped[str] = mapped_column(String(80), nullable=False, default="tv_core3_mvp_seed_v0_2")
    seed_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3DimensionEvidenceAnchor(Base, AuditMixin):
    __tablename__ = "core3_dimension_evidence_anchor"
    __table_args__ = (
        UniqueConstraint(
            "dimension_definition_id",
            "anchor_type",
            "anchor_code",
            "anchor_role",
            "polarity",
            name="uq_core3_dimension_evidence_anchor_key",
        ),
        CheckConstraint("weight >= 0 and weight <= 1", name="ck_m085_anchor_weight"),
        Index("ix_core3_dimension_anchor_definition", "dimension_definition_id", "anchor_type"),
        Index("ix_core3_dimension_anchor_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_dimension_anchor_code", "anchor_type", "anchor_code"),
    )

    dimension_anchor_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    dimension_definition_id: Mapped[str] = mapped_column(ForeignKey("core3_dimension_definition.dimension_definition_id"), index=True)
    ontology_version_id: Mapped[str] = mapped_column(ForeignKey("core3_dimension_ontology_version.ontology_version_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    anchor_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    anchor_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    anchor_name_cn: Mapped[str] = mapped_column(String(240), nullable=False)
    anchor_role: Mapped[str] = mapped_column(String(80), nullable=False, default="optional", index=True)
    polarity: Mapped[str] = mapped_column(String(40), nullable=False, default="positive", index=True)
    weight: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    min_sentence_count: Mapped[int | None] = mapped_column(Integer)
    min_sku_count: Mapped[int | None] = mapped_column(Integer)
    min_confidence: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    representative_phrase_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    representative_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    source_rule_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="core3_mvp_real_data_v2_m08_5_v1")
    seed_version: Mapped[str] = mapped_column(String(80), nullable=False, default="tv_core3_mvp_seed_v0_2")
    seed_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3DimensionMappingRule(Base, AuditMixin):
    __tablename__ = "core3_dimension_mapping_rule"
    __table_args__ = (
        UniqueConstraint(
            "ontology_version_id",
            "source_type",
            "source_code",
            "target_dimension_type",
            "target_dimension_code",
            "mapping_level",
            name="uq_core3_dimension_mapping_rule_key",
        ),
        CheckConstraint("mapping_strength >= 0 and mapping_strength <= 1", name="ck_m085_mapping_strength"),
        Index("ix_core3_dimension_mapping_source", "ontology_version_id", "source_type", "source_code"),
        Index("ix_core3_dimension_mapping_target", "ontology_version_id", "target_dimension_type", "target_dimension_code"),
        Index("ix_core3_dimension_mapping_flags", "mapping_level", "active", "service_guardrail_flag"),
    )

    dimension_mapping_rule_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    ontology_version_id: Mapped[str] = mapped_column(ForeignKey("core3_dimension_ontology_version.ontology_version_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    source_name_cn: Mapped[str | None] = mapped_column(String(240))
    target_dimension_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    target_dimension_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    mapping_level: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    mapping_strength: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    requires_product_anchor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    requires_market_anchor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    service_guardrail_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    low_value_guardrail_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    rule_expr_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    reason_cn: Mapped[str] = mapped_column(Text, nullable=False, default="")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="core3_mvp_real_data_v2_m08_5_v1")
    seed_version: Mapped[str] = mapped_column(String(80), nullable=False, default="tv_core3_mvp_seed_v0_2")
    seed_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3DimensionCandidateSnapshot(Base, AuditMixin):
    __tablename__ = "core3_dimension_candidate_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "ontology_version_id",
            "snapshot_type",
            "signal_type",
            "signal_code",
            name="uq_core3_dimension_candidate_snapshot_key",
        ),
        CheckConstraint("sentence_count >= 0", name="ck_m085_snapshot_sentence_count"),
        CheckConstraint("sku_count >= 0", name="ck_m085_snapshot_sku_count"),
        CheckConstraint("avg_signal_score >= 0 and avg_signal_score <= 1", name="ck_m085_snapshot_avg_signal"),
        CheckConstraint("coverage_ratio >= 0 and coverage_ratio <= 1", name="ck_m085_snapshot_coverage"),
        CheckConstraint("specificity_score >= 0 and specificity_score <= 1", name="ck_m085_snapshot_specificity"),
        Index("ix_core3_dimension_snapshot_signal", "ontology_version_id", "snapshot_type", "signal_type"),
        Index("ix_core3_dimension_snapshot_batch", "project_id", "category_code", "batch_id"),
    )

    candidate_snapshot_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    ontology_version_id: Mapped[str] = mapped_column(ForeignKey("core3_dimension_ontology_version.ontology_version_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    snapshot_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    signal_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    signal_name_cn: Mapped[str] = mapped_column(String(240), nullable=False)
    sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    strong_sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    service_sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    low_value_sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_signal_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    coverage_ratio: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    specificity_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    distribution_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    representative_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="core3_mvp_real_data_v2_m08_5_v1")
    seed_version: Mapped[str] = mapped_column(String(80), nullable=False, default="tv_core3_mvp_seed_v0_2")
    seed_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3DimensionCalibrationIssue(Base, AuditMixin):
    __tablename__ = "core3_dimension_calibration_issue"
    __table_args__ = (
        UniqueConstraint(
            "ontology_version_id",
            "issue_scope",
            "dimension_type",
            "dimension_code",
            "source_type",
            "source_code",
            "issue_code",
            name="uq_core3_dimension_calibration_issue_key",
        ),
        Index("ix_core3_dimension_issue_scope", "ontology_version_id", "issue_scope", "severity"),
        Index("ix_core3_dimension_issue_dimension", "ontology_version_id", "dimension_type", "dimension_code"),
        Index("ix_core3_dimension_issue_status", "review_status"),
        Index("ix_core3_dimension_issue_batch", "project_id", "category_code", "batch_id"),
    )

    calibration_issue_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    ontology_version_id: Mapped[str] = mapped_column(ForeignKey("core3_dimension_ontology_version.ontology_version_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    issue_scope: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    dimension_type: Mapped[str | None] = mapped_column(String(80), index=True)
    dimension_code: Mapped[str | None] = mapped_column(String(160), index=True)
    source_type: Mapped[str | None] = mapped_column(String(80), index=True)
    source_code: Mapped[str | None] = mapped_column(String(160), index=True)
    issue_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(40), nullable=False, default="warning", index=True)
    issue_message_cn: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    suggested_action_cn: Mapped[str] = mapped_column(Text, nullable=False, default="")
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="open", index=True)
    rule_version: Mapped[str] = mapped_column(String(80), nullable=False, default="core3_mvp_real_data_v2_m08_5_v1")
    seed_version: Mapped[str] = mapped_column(String(80), nullable=False, default="tv_core3_mvp_seed_v0_2")
    seed_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3SkuTaskCandidate(Base, AuditMixin):
    __tablename__ = "core3_sku_task_candidate"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "task_code",
            "rule_version",
            "task_seed_hash",
            name="uq_core3_m09_candidate_key",
        ),
        CheckConstraint("initial_candidate_score >= 0 and initial_candidate_score <= 1", name="ck_m09_candidate_score"),
        Index("ix_core3_m09_candidate_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m09_candidate_sku", "project_id", "category_code", "batch_id", "sku_code"),
        Index("ix_core3_m09_candidate_task", "project_id", "category_code", "batch_id", "task_code", "candidate_status"),
        Index("ix_core3_m09_candidate_review", "project_id", "category_code", "batch_id", "review_required", "review_status"),
        Index("ix_core3_m09_candidate_sources_gin", "candidate_sources_json", postgresql_using="gin"),
        Index("ix_core3_m09_candidate_evidence_gin", "candidate_evidence_refs_json", postgresql_using="gin"),
    )

    sku_task_candidate_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_signal_profile_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_signal_profile.sku_signal_profile_id"), index=True)
    sku_downstream_feature_view_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_downstream_feature_view.sku_downstream_feature_view_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_code: Mapped[str | None] = mapped_column(String(160))
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    task_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    task_name_cn: Mapped[str] = mapped_column(String(240), nullable=False)
    task_definition_cn: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    candidate_sources_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    candidate_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    initial_candidate_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    candidate_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_reason_parts_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    candidate_evidence_refs_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    rejected_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    blocked_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m09_v1", index=True)
    task_seed_version: Mapped[str] = mapped_column(String(120), nullable=False, default="tv_core3_mvp_seed_v0_2", index=True)
    task_seed_file_version: Mapped[str] = mapped_column(String(120), nullable=False)
    task_seed_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    feature_view_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SkuTaskScore(Base, AuditMixin):
    __tablename__ = "core3_sku_task_score"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "task_code",
            "rule_version",
            "task_seed_hash",
            name="uq_core3_m09_score_key",
        ),
        CheckConstraint("task_score >= 0 and task_score <= 1", name="ck_m09_score_task"),
        CheckConstraint("raw_task_score >= 0 and raw_task_score <= 1", name="ck_m09_score_raw"),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_m09_score_confidence"),
        CheckConstraint("param_signal_score >= 0 and param_signal_score <= 1", name="ck_m09_score_param"),
        CheckConstraint("claim_signal_score >= 0 and claim_signal_score <= 1", name="ck_m09_score_claim"),
        CheckConstraint("comment_signal_score >= 0 and comment_signal_score <= 1", name="ck_m09_score_comment"),
        CheckConstraint("market_signal_score >= 0 and market_signal_score <= 1", name="ck_m09_score_market"),
        CheckConstraint("risk_penalty >= 0 and risk_penalty <= 1", name="ck_m09_score_risk"),
        Index("ix_core3_m09_score_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m09_score_sku", "project_id", "category_code", "batch_id", "sku_code"),
        Index("ix_core3_m09_score_task", "project_id", "category_code", "batch_id", "task_code", "relation_level"),
        Index("ix_core3_m09_score_current", "project_id", "category_code", "batch_id", "sku_code", "task_code", "is_current"),
        Index("ix_core3_m09_score_review", "project_id", "category_code", "batch_id", "review_required", "review_status"),
        Index("ix_core3_m09_score_payload_gin", "next_module_payload_json", postgresql_using="gin"),
    )

    sku_task_score_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    sku_task_candidate_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_task_candidate.sku_task_candidate_id"), index=True)
    sku_signal_profile_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_signal_profile.sku_signal_profile_id"), index=True)
    sku_downstream_feature_view_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_downstream_feature_view.sku_downstream_feature_view_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_code: Mapped[str | None] = mapped_column(String(160))
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    task_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    task_name_cn: Mapped[str] = mapped_column(String(240), nullable=False)
    task_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    raw_task_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    relation_level: Mapped[str] = mapped_column(String(40), nullable=False, default="insufficient", index=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    param_signal_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    claim_signal_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    comment_signal_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    market_signal_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    risk_penalty: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    cap_applied_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_domain_coverage_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    business_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    business_reason_parts_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    next_module_payload_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m09_v1", index=True)
    task_seed_version: Mapped[str] = mapped_column(String(120), nullable=False, default="tv_core3_mvp_seed_v0_2", index=True)
    task_seed_file_version: Mapped[str] = mapped_column(String(120), nullable=False)
    task_seed_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    feature_view_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SkuTaskEvidenceBreakdown(Base, AuditMixin):
    __tablename__ = "core3_sku_task_evidence_breakdown"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "task_code",
            "evidence_domain",
            "rule_version",
            "task_seed_hash",
            name="uq_core3_m09_breakdown_key",
        ),
        CheckConstraint("domain_score >= 0 and domain_score <= 1", name="ck_m09_breakdown_score"),
        CheckConstraint("domain_weight >= 0 and domain_weight <= 1", name="ck_m09_breakdown_weight"),
        CheckConstraint("weighted_score >= 0 and weighted_score <= 1", name="ck_m09_breakdown_weighted"),
        CheckConstraint("evidence_count >= 0", name="ck_m09_breakdown_evidence_count"),
        Index("ix_core3_m09_breakdown_score", "sku_task_score_id", "evidence_domain"),
        Index("ix_core3_m09_breakdown_sku", "project_id", "category_code", "batch_id", "sku_code"),
        Index("ix_core3_m09_breakdown_task", "project_id", "category_code", "batch_id", "task_code", "evidence_domain"),
        Index("ix_core3_m09_breakdown_evidence_gin", "evidence_refs_json", postgresql_using="gin"),
    )

    sku_task_evidence_breakdown_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    sku_task_score_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_task_score.sku_task_score_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_code: Mapped[str | None] = mapped_column(String(160))
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    task_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    task_name_cn: Mapped[str] = mapped_column(String(240), nullable=False)
    evidence_domain: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    support_level: Mapped[str] = mapped_column(String(40), nullable=False, default="missing", index=True)
    domain_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    domain_weight: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    weighted_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dedup_comment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    effective_sentence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_refs_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    source_feature_refs_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    domain_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    domain_risk_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m09_v1", index=True)
    task_seed_version: Mapped[str] = mapped_column(String(120), nullable=False, default="tv_core3_mvp_seed_v0_2", index=True)
    task_seed_file_version: Mapped[str] = mapped_column(String(120), nullable=False)
    task_seed_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    feature_view_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SkuTaskReviewIssue(Base, AuditMixin):
    __tablename__ = "core3_sku_task_review_issue"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "task_code",
            "issue_type",
            "input_fingerprint",
            name="uq_core3_m09_review_issue_key",
        ),
        Index("ix_core3_m09_review_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m09_review_sku", "project_id", "category_code", "batch_id", "sku_code"),
        Index("ix_core3_m09_review_task", "project_id", "category_code", "batch_id", "task_code", "issue_type"),
        Index("ix_core3_m09_review_status", "project_id", "category_code", "batch_id", "issue_severity", "issue_status"),
        Index("ix_core3_m09_review_evidence_gin", "evidence_refs_json", postgresql_using="gin"),
    )

    sku_task_review_issue_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    sku_task_score_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_task_score.sku_task_score_id"), index=True)
    sku_task_candidate_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_task_candidate.sku_task_candidate_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_code: Mapped[str | None] = mapped_column(String(160))
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    task_code: Mapped[str | None] = mapped_column(String(160), index=True)
    task_name_cn: Mapped[str | None] = mapped_column(String(240))
    issue_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    issue_severity: Mapped[str] = mapped_column(String(40), nullable=False, default="warning", index=True)
    issue_status: Mapped[str] = mapped_column(String(40), nullable=False, default="open", index=True)
    issue_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    issue_detail_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    affected_output_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_refs_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    suggested_action_cn: Mapped[str] = mapped_column(Text, nullable=False)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m09_v1", index=True)
    task_seed_version: Mapped[str] = mapped_column(String(120), nullable=False, default="tv_core3_mvp_seed_v0_2", index=True)
    task_seed_file_version: Mapped[str] = mapped_column(String(120), nullable=False)
    task_seed_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    feature_view_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="warning", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="review_required", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SkuTargetGroupCandidate(Base, AuditMixin):
    __tablename__ = "core3_sku_target_group_candidate"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "target_group_code",
            "rule_version",
            "target_group_seed_hash",
            name="uq_core3_m10_candidate_key",
        ),
        CheckConstraint("candidate_initial_score >= 0 and candidate_initial_score <= 1", name="ck_m10_candidate_score"),
        Index("ix_core3_m10_candidate_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m10_candidate_sku", "project_id", "category_code", "batch_id", "sku_code"),
        Index("ix_core3_m10_candidate_group", "project_id", "category_code", "batch_id", "target_group_code", "candidate_status"),
        Index("ix_core3_m10_candidate_review", "project_id", "category_code", "batch_id", "review_required", "review_status"),
        Index("ix_core3_m10_candidate_source_gin", "candidate_source_json", postgresql_using="gin"),
        Index("ix_core3_m10_candidate_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    sku_target_group_candidate_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_signal_profile_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_signal_profile.sku_signal_profile_id"), index=True)
    sku_downstream_feature_view_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_downstream_feature_view.sku_downstream_feature_view_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_code: Mapped[str | None] = mapped_column(String(160))
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    target_group_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    target_group_name_cn: Mapped[str] = mapped_column(String(240), nullable=False)
    target_group_definition_cn: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_source_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    candidate_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_task_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    candidate_initial_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    candidate_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    reject_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    missing_signals_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    risk_flags_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_matrix_refs_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    feature_view_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    task_score_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    target_group_seed_version: Mapped[str] = mapped_column(String(120), nullable=False, default="tv_core3_mvp_seed_v0_2", index=True)
    target_group_seed_file_version: Mapped[str] = mapped_column(String(120), nullable=False)
    target_group_seed_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m10_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SkuTargetGroupScore(Base, AuditMixin):
    __tablename__ = "core3_sku_target_group_score"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "target_group_code",
            "rule_version",
            "target_group_seed_hash",
            name="uq_core3_m10_score_key",
        ),
        CheckConstraint("task_support_score >= 0 and task_support_score <= 1", name="ck_m10_score_task"),
        CheckConstraint("comment_group_signal_score >= 0 and comment_group_signal_score <= 1", name="ck_m10_score_comment"),
        CheckConstraint("price_channel_fit_score >= 0 and price_channel_fit_score <= 1", name="ck_m10_score_price"),
        CheckConstraint("market_validation_score >= 0 and market_validation_score <= 1", name="ck_m10_score_market"),
        CheckConstraint("service_side_score >= 0 and service_side_score <= 1", name="ck_m10_score_service"),
        CheckConstraint("raw_target_group_score >= 0 and raw_target_group_score <= 1", name="ck_m10_score_raw"),
        CheckConstraint("risk_penalty >= 0 and risk_penalty <= 1", name="ck_m10_score_risk"),
        CheckConstraint("target_group_score >= 0 and target_group_score <= 1", name="ck_m10_score_final"),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_m10_score_confidence"),
        Index("ix_core3_m10_score_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m10_score_sku", "project_id", "category_code", "batch_id", "sku_code"),
        Index("ix_core3_m10_score_group", "project_id", "category_code", "batch_id", "target_group_code", "relation_level"),
        Index("ix_core3_m10_score_current", "project_id", "category_code", "batch_id", "sku_code", "target_group_code", "is_current"),
        Index("ix_core3_m10_score_review", "project_id", "category_code", "batch_id", "review_required", "review_status"),
    )

    sku_target_group_score_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    sku_target_group_candidate_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_target_group_candidate.sku_target_group_candidate_id"), index=True)
    sku_signal_profile_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_signal_profile.sku_signal_profile_id"), index=True)
    sku_downstream_feature_view_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_downstream_feature_view.sku_downstream_feature_view_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_code: Mapped[str | None] = mapped_column(String(160))
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    target_group_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    target_group_name_cn: Mapped[str] = mapped_column(String(240), nullable=False)
    target_group_definition_cn: Mapped[str] = mapped_column(Text, nullable=False)
    task_support_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    comment_group_signal_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    price_channel_fit_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    market_validation_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    service_side_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    raw_target_group_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    risk_penalty: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    target_group_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    relation_level: Mapped[str] = mapped_column(String(40), nullable=False, default="insufficient", index=True)
    relation_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    confidence_level: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    evidence_domain_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    effective_domain_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    source_task_scores_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    score_breakdown_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    cap_rule_applied_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    missing_signals_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    risk_flags_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    business_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    business_reason_parts_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_matrix_refs_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    feature_view_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    task_score_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    target_group_seed_version: Mapped[str] = mapped_column(String(120), nullable=False, default="tv_core3_mvp_seed_v0_2", index=True)
    target_group_seed_file_version: Mapped[str] = mapped_column(String(120), nullable=False)
    target_group_seed_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m10_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SkuTargetGroupEvidenceBreakdown(Base, AuditMixin):
    __tablename__ = "core3_sku_target_group_evidence_breakdown"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "target_group_code",
            "evidence_domain",
            "rule_version",
            "target_group_seed_hash",
            name="uq_core3_m10_breakdown_key",
        ),
        CheckConstraint("domain_score >= 0 and domain_score <= 1", name="ck_m10_breakdown_score"),
        CheckConstraint("domain_weight >= 0 and domain_weight <= 1", name="ck_m10_breakdown_weight"),
        CheckConstraint("weighted_score >= 0 and weighted_score <= 1", name="ck_m10_breakdown_weighted"),
        CheckConstraint("evidence_count >= 0", name="ck_m10_breakdown_evidence_count"),
        Index("ix_core3_m10_breakdown_score", "sku_target_group_score_id", "evidence_domain"),
        Index("ix_core3_m10_breakdown_sku", "project_id", "category_code", "batch_id", "sku_code"),
        Index("ix_core3_m10_breakdown_group", "project_id", "category_code", "batch_id", "target_group_code", "evidence_domain"),
        Index("ix_core3_m10_breakdown_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    sku_target_group_evidence_breakdown_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    sku_target_group_score_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_target_group_score.sku_target_group_score_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_code: Mapped[str | None] = mapped_column(String(160))
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    target_group_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    target_group_name_cn: Mapped[str] = mapped_column(String(240), nullable=False)
    evidence_domain: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    support_level: Mapped[str] = mapped_column(String(40), nullable=False, default="missing", index=True)
    domain_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    domain_weight: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    weighted_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    source_feature_refs_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    domain_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    domain_risk_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    feature_view_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    task_score_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    target_group_seed_version: Mapped[str] = mapped_column(String(120), nullable=False, default="tv_core3_mvp_seed_v0_2", index=True)
    target_group_seed_file_version: Mapped[str] = mapped_column(String(120), nullable=False)
    target_group_seed_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m10_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SkuTargetGroupReviewIssue(Base, AuditMixin):
    __tablename__ = "core3_sku_target_group_review_issue"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "target_group_code",
            "issue_type",
            "input_fingerprint",
            name="uq_core3_m10_review_issue_key",
        ),
        Index("ix_core3_m10_review_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m10_review_sku", "project_id", "category_code", "batch_id", "sku_code"),
        Index("ix_core3_m10_review_group", "project_id", "category_code", "batch_id", "target_group_code", "issue_type"),
        Index("ix_core3_m10_review_status", "project_id", "category_code", "batch_id", "issue_severity", "issue_status"),
        Index("ix_core3_m10_review_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    sku_target_group_review_issue_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    sku_target_group_score_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_target_group_score.sku_target_group_score_id"), index=True)
    sku_target_group_candidate_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_target_group_candidate.sku_target_group_candidate_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_code: Mapped[str | None] = mapped_column(String(160))
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    target_group_code: Mapped[str | None] = mapped_column(String(160), index=True)
    target_group_name_cn: Mapped[str | None] = mapped_column(String(240))
    issue_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    issue_severity: Mapped[str] = mapped_column(String(40), nullable=False, default="warning", index=True)
    issue_status: Mapped[str] = mapped_column(String(40), nullable=False, default="open", index=True)
    issue_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    issue_detail_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    affected_output_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    suggested_action_cn: Mapped[str] = mapped_column(Text, nullable=False)
    profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    feature_view_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    task_score_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    target_group_seed_version: Mapped[str] = mapped_column(String(120), nullable=False, default="tv_core3_mvp_seed_v0_2", index=True)
    target_group_seed_file_version: Mapped[str] = mapped_column(String(120), nullable=False)
    target_group_seed_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m10_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="warning", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="review_required", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SkuBattlefieldCandidate(Base, AuditMixin):
    __tablename__ = "core3_sku_battlefield_candidate"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "battlefield_code",
            "rule_version",
            "battlefield_seed_hash",
            name="uq_core3_m11_candidate_key",
        ),
        CheckConstraint("candidate_initial_score >= 0 and candidate_initial_score <= 1", name="ck_m11_candidate_score"),
        Index("ix_core3_m11_candidate_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m11_candidate_sku", "project_id", "category_code", "batch_id", "sku_code"),
        Index("ix_core3_m11_candidate_battlefield", "project_id", "category_code", "batch_id", "battlefield_code", "candidate_status"),
        Index("ix_core3_m11_candidate_review", "project_id", "category_code", "batch_id", "review_required", "review_status"),
        Index("ix_core3_m11_candidate_source_gin", "candidate_source_json", postgresql_using="gin"),
        Index("ix_core3_m11_candidate_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    sku_battlefield_candidate_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_signal_profile_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_signal_profile.sku_signal_profile_id"), index=True)
    sku_downstream_feature_view_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_downstream_feature_view.sku_downstream_feature_view_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_code: Mapped[str | None] = mapped_column(String(160))
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    battlefield_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    battlefield_name_cn: Mapped[str] = mapped_column(String(240), nullable=False)
    battlefield_definition_cn: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_source_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    candidate_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_task_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    source_target_group_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    source_claim_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    source_param_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    source_topic_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    candidate_initial_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    candidate_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    reject_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    missing_signals_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    risk_flags_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_matrix_refs_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    feature_view_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    task_score_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    target_group_score_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    battlefield_seed_version: Mapped[str] = mapped_column(String(120), nullable=False, default="tv_core3_mvp_seed_v0_2", index=True)
    battlefield_seed_file_version: Mapped[str] = mapped_column(String(120), nullable=False)
    battlefield_seed_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m11_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SkuBattlefieldScore(Base, AuditMixin):
    __tablename__ = "core3_sku_battlefield_score"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "battlefield_code",
            "rule_version",
            "battlefield_seed_hash",
            name="uq_core3_m11_score_key",
        ),
        CheckConstraint("semantic_score >= 0 and semantic_score <= 1", name="ck_m11_score_semantic"),
        CheckConstraint("market_score >= 0 and market_score <= 1", name="ck_m11_score_market"),
        CheckConstraint("core_task_score >= 0 and core_task_score <= 1", name="ck_m11_score_task"),
        CheckConstraint("target_group_score >= 0 and target_group_score <= 1", name="ck_m11_score_group"),
        CheckConstraint("core_claim_combo_score >= 0 and core_claim_combo_score <= 1", name="ck_m11_score_claim"),
        CheckConstraint("core_param_capability_score >= 0 and core_param_capability_score <= 1", name="ck_m11_score_param"),
        CheckConstraint("comment_support_score >= 0 and comment_support_score <= 1", name="ck_m11_score_comment"),
        CheckConstraint("price_position_fit >= 0 and price_position_fit <= 1", name="ck_m11_score_price"),
        CheckConstraint("sales_validation_score >= 0 and sales_validation_score <= 1", name="ck_m11_score_sales"),
        CheckConstraint("raw_battlefield_score >= 0 and raw_battlefield_score <= 1", name="ck_m11_score_raw"),
        CheckConstraint("risk_penalty >= 0 and risk_penalty <= 1", name="ck_m11_score_risk"),
        CheckConstraint("battlefield_score >= 0 and battlefield_score <= 1", name="ck_m11_score_final"),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_m11_score_confidence"),
        Index("ix_core3_m11_score_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m11_score_sku", "project_id", "category_code", "batch_id", "sku_code"),
        Index("ix_core3_m11_score_battlefield", "project_id", "category_code", "batch_id", "battlefield_code", "relation_level"),
        Index("ix_core3_m11_score_role", "project_id", "category_code", "batch_id", "sku_code", "competitor_selection_role"),
        Index("ix_core3_m11_score_current", "project_id", "category_code", "batch_id", "sku_code", "battlefield_code", "is_current"),
        Index("ix_core3_m11_score_review", "project_id", "category_code", "batch_id", "review_required", "review_status"),
    )

    sku_battlefield_score_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    sku_battlefield_candidate_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_battlefield_candidate.sku_battlefield_candidate_id"), index=True)
    sku_signal_profile_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_signal_profile.sku_signal_profile_id"), index=True)
    sku_downstream_feature_view_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_downstream_feature_view.sku_downstream_feature_view_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_code: Mapped[str | None] = mapped_column(String(160))
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    battlefield_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    battlefield_name_cn: Mapped[str] = mapped_column(String(240), nullable=False)
    battlefield_definition_cn: Mapped[str] = mapped_column(Text, nullable=False)
    semantic_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    market_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    core_task_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    target_group_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    core_claim_combo_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    core_param_capability_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    comment_support_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    pain_point_risk_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    price_position_fit: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    sales_validation_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    sales_amount_validation_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    channel_fit_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    trend_signal_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    comparable_pool_strength: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    raw_battlefield_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    risk_penalty: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    battlefield_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    relation_level: Mapped[str] = mapped_column(String(40), nullable=False, default="insufficient", index=True)
    relation_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    competitor_selection_role: Mapped[str] = mapped_column(String(80), nullable=False, default="not_for_core_search", index=True)
    competitor_selection_role_cn: Mapped[str] = mapped_column(String(160), nullable=False, default="不进入核心召回")
    sample_sufficiency: Mapped[str] = mapped_column(String(60), nullable=False, default="unknown", index=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    confidence_level: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    evidence_domain_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    effective_domain_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    score_breakdown_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    cap_rule_applied_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    missing_signals_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    risk_flags_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    business_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    business_reason_parts_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    next_module_payload_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_matrix_refs_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    feature_view_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    task_score_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    target_group_score_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    battlefield_seed_version: Mapped[str] = mapped_column(String(120), nullable=False, default="tv_core3_mvp_seed_v0_2", index=True)
    battlefield_seed_file_version: Mapped[str] = mapped_column(String(120), nullable=False)
    battlefield_seed_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m11_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SkuBattlefieldEvidenceBreakdown(Base, AuditMixin):
    __tablename__ = "core3_sku_battlefield_evidence_breakdown"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "battlefield_code",
            "evidence_domain",
            "rule_version",
            "battlefield_seed_hash",
            name="uq_core3_m11_breakdown_key",
        ),
        CheckConstraint("domain_score >= 0 and domain_score <= 1", name="ck_m11_breakdown_score"),
        CheckConstraint("domain_weight >= 0 and domain_weight <= 1", name="ck_m11_breakdown_weight"),
        CheckConstraint("weighted_score >= 0 and weighted_score <= 1", name="ck_m11_breakdown_weighted"),
        CheckConstraint("evidence_count >= 0", name="ck_m11_breakdown_evidence_count"),
        Index("ix_core3_m11_breakdown_score", "sku_battlefield_score_id", "evidence_domain"),
        Index("ix_core3_m11_breakdown_sku", "project_id", "category_code", "batch_id", "sku_code"),
        Index("ix_core3_m11_breakdown_battlefield", "project_id", "category_code", "batch_id", "battlefield_code", "evidence_domain"),
        Index("ix_core3_m11_breakdown_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    sku_battlefield_evidence_breakdown_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    sku_battlefield_score_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_battlefield_score.sku_battlefield_score_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_code: Mapped[str | None] = mapped_column(String(160))
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    battlefield_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    battlefield_name_cn: Mapped[str] = mapped_column(String(240), nullable=False)
    evidence_domain: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    support_level: Mapped[str] = mapped_column(String(40), nullable=False, default="missing", index=True)
    domain_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    domain_weight: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    weighted_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    source_feature_refs_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    domain_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    domain_risk_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    feature_view_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    task_score_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    target_group_score_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    battlefield_seed_version: Mapped[str] = mapped_column(String(120), nullable=False, default="tv_core3_mvp_seed_v0_2", index=True)
    battlefield_seed_file_version: Mapped[str] = mapped_column(String(120), nullable=False)
    battlefield_seed_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m11_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SkuBattlefieldPortfolio(Base, AuditMixin):
    __tablename__ = "core3_sku_battlefield_portfolio"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "rule_version",
            "battlefield_seed_hash",
            name="uq_core3_m11_portfolio_key",
        ),
        CheckConstraint("portfolio_confidence >= 0 and portfolio_confidence <= 1", name="ck_m11_portfolio_confidence"),
        Index("ix_core3_m11_portfolio_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m11_portfolio_sku", "project_id", "category_code", "batch_id", "sku_code"),
        Index("ix_core3_m11_portfolio_primary_gin", "primary_search_battlefield_codes_json", postgresql_using="gin"),
        Index("ix_core3_m11_portfolio_score_refs_gin", "battlefield_score_refs_json", postgresql_using="gin"),
    )

    sku_battlefield_portfolio_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    sku_signal_profile_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_signal_profile.sku_signal_profile_id"), index=True)
    sku_downstream_feature_view_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_downstream_feature_view.sku_downstream_feature_view_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_code: Mapped[str | None] = mapped_column(String(160))
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    main_battlefields_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    secondary_battlefields_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    opportunity_battlefields_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    weak_battlefields_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    insufficient_battlefields_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    primary_competitor_search_context_cn: Mapped[str] = mapped_column(Text, nullable=False)
    primary_search_battlefield_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    secondary_search_battlefield_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    opportunity_monitoring_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    risk_or_service_context_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    portfolio_confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    portfolio_risk_flags_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    battlefield_score_refs_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    feature_view_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    task_score_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    target_group_score_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    battlefield_seed_version: Mapped[str] = mapped_column(String(120), nullable=False, default="tv_core3_mvp_seed_v0_2", index=True)
    battlefield_seed_file_version: Mapped[str] = mapped_column(String(120), nullable=False)
    battlefield_seed_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m11_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SkuBattlefieldReviewIssue(Base, AuditMixin):
    __tablename__ = "core3_sku_battlefield_review_issue"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "battlefield_code",
            "issue_type",
            "input_fingerprint",
            name="uq_core3_m11_review_issue_key",
        ),
        Index("ix_core3_m11_review_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m11_review_sku", "project_id", "category_code", "batch_id", "sku_code"),
        Index("ix_core3_m11_review_battlefield", "project_id", "category_code", "batch_id", "battlefield_code", "issue_type"),
        Index("ix_core3_m11_review_status", "project_id", "category_code", "batch_id", "issue_severity", "issue_status"),
        Index("ix_core3_m11_review_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    sku_battlefield_review_issue_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    sku_battlefield_score_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_battlefield_score.sku_battlefield_score_id"), index=True)
    sku_battlefield_candidate_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_battlefield_candidate.sku_battlefield_candidate_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_code: Mapped[str | None] = mapped_column(String(160))
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    battlefield_code: Mapped[str | None] = mapped_column(String(160), nullable=False, default="", index=True)
    battlefield_name_cn: Mapped[str | None] = mapped_column(String(240))
    issue_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    issue_severity: Mapped[str] = mapped_column(String(40), nullable=False, default="warning", index=True)
    issue_status: Mapped[str] = mapped_column(String(40), nullable=False, default="open", index=True)
    issue_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    issue_detail_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    affected_output_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    suggested_action_cn: Mapped[str] = mapped_column(Text, nullable=False)
    profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    feature_view_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    task_score_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    target_group_score_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    battlefield_seed_version: Mapped[str] = mapped_column(String(120), nullable=False, default="tv_core3_mvp_seed_v0_2", index=True)
    battlefield_seed_file_version: Mapped[str] = mapped_column(String(120), nullable=False)
    battlefield_seed_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m11_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="warning", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="review_required", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3M09cSkuUserTaskProfile(Base, AuditMixin):
    __tablename__ = "core3_m09c_sku_user_task_profile"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "taxonomy_version",
            "sku_code",
            "rule_version",
            "is_current",
            name="uq_core3_m09c_profile_current",
        ),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_m09c_profile_confidence"),
        Index("ix_core3_m09c_profile_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m09c_profile_sku", "project_id", "category_code", "batch_id", "sku_code"),
        Index("ix_core3_m09c_profile_primary", "primary_user_task_code"),
        Index("ix_core3_m09c_profile_size_price", "size_tier", "price_band_in_size_tier"),
        Index("ix_core3_m09c_profile_secondary_gin", "secondary_user_task_codes_json", postgresql_using="gin"),
        Index("ix_core3_m09c_profile_observed_gin", "comment_observed_task_codes_json", postgresql_using="gin"),
        Index("ix_core3_m09c_profile_claimed_gin", "brand_claimed_task_codes_json", postgresql_using="gin"),
        Index("ix_core3_m09c_profile_latent_gin", "latent_capability_task_codes_json", postgresql_using="gin"),
        Index("ix_core3_m09c_profile_drag_gin", "drag_factor_task_codes_json", postgresql_using="gin"),
        Index("ix_core3_m09c_profile_summary_gin", "user_task_summary_json", postgresql_using="gin"),
        Index("ix_core3_m09c_profile_evidence_gin", "evidence_ids_json", postgresql_using="gin"),
    )

    profile_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    product_category: Mapped[str] = mapped_column(String(40), nullable=False, default="TV", index=True)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m09c_tv_user_task_profile_v0.1", index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    size_tier: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown", index=True)
    price_band_in_size_tier: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    price_percentile_in_size_tier: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    primary_user_task_code: Mapped[str | None] = mapped_column(String(160), index=True)
    primary_relation_status: Mapped[str | None] = mapped_column(String(80), index=True)
    secondary_user_task_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    comment_observed_task_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    brand_claimed_task_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    latent_capability_task_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    drag_factor_task_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    user_task_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    no_primary_reason: Mapped[str | None] = mapped_column(Text)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    evidence_ids_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    profile_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3M09cSkuUserTaskScore(Base, AuditMixin):
    __tablename__ = "core3_m09c_sku_user_task_score"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "taxonomy_version",
            "sku_code",
            "user_task_code",
            "rule_version",
            "is_current",
            name="uq_core3_m09c_score_current",
        ),
        CheckConstraint("user_task_score >= 0 and user_task_score <= 1", name="ck_m09c_score_final"),
        CheckConstraint("comment_task_need_score >= 0 and comment_task_need_score <= 1", name="ck_m09c_score_comment"),
        CheckConstraint("claim_task_alignment_score >= 0 and claim_task_alignment_score <= 1", name="ck_m09c_score_claim"),
        CheckConstraint("param_capability_score >= 0 and param_capability_score <= 1", name="ck_m09c_score_param"),
        CheckConstraint("size_price_fit_score >= 0 and size_price_fit_score <= 1", name="ck_m09c_score_size_price"),
        CheckConstraint("market_validation_score >= 0 and market_validation_score <= 1", name="ck_m09c_score_market"),
        CheckConstraint("negative_drag_score >= 0 and negative_drag_score <= 1", name="ck_m09c_score_drag"),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_m09c_score_confidence"),
        Index("ix_core3_m09c_score_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m09c_score_sku", "project_id", "category_code", "batch_id", "sku_code"),
        Index("ix_core3_m09c_score_task", "project_id", "category_code", "batch_id", "user_task_code", "relation_status"),
        Index("ix_core3_m09c_score_size_price", "size_tier", "price_band_in_size_tier"),
        Index("ix_core3_m09c_score_breakdown_gin", "score_breakdown_json", postgresql_using="gin"),
        Index("ix_core3_m09c_score_evidence_gin", "evidence_ids_json", postgresql_using="gin"),
    )

    score_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    product_category: Mapped[str] = mapped_column(String(40), nullable=False, default="TV", index=True)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m09c_tv_user_task_profile_v0.1", index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    user_task_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    user_task_name: Mapped[str] = mapped_column(String(240), nullable=False)
    user_task_definition: Mapped[str] = mapped_column(Text, nullable=False)
    relation_status: Mapped[str] = mapped_column(String(80), nullable=False, default="not_supported", index=True)
    user_task_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    comment_task_need_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    claim_task_alignment_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    param_capability_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    size_price_fit_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    market_validation_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    negative_drag_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    sentiment_polarity: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    size_tier: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown", index=True)
    price_band_in_size_tier: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    price_percentile_in_size_tier: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    score_breakdown_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    status_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3M09cUserTaskCoverage(Base, AuditMixin):
    __tablename__ = "core3_m09c_user_task_coverage"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "taxonomy_version",
            "user_task_code",
            "rule_version",
            "is_current",
            name="uq_core3_m09c_coverage_current",
        ),
        Index("ix_core3_m09c_coverage_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m09c_coverage_task", "project_id", "category_code", "batch_id", "user_task_code"),
        Index("ix_core3_m09c_coverage_status_gin", "relation_status_counts_json", postgresql_using="gin"),
        Index("ix_core3_m09c_coverage_top_gin", "top_skus_json", postgresql_using="gin"),
    )

    coverage_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    product_category: Mapped[str] = mapped_column(String(40), nullable=False, default="TV", index=True)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m09c_tv_user_task_profile_v0.1", index=True)
    user_task_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    user_task_name: Mapped[str] = mapped_column(String(240), nullable=False)
    sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    relation_status_counts_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    primary_sku_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    secondary_sku_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    comment_observed_sku_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    brand_claimed_sku_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    latent_capability_sku_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    drag_factor_sku_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    top_skus_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    coverage_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3M10cSkuTargetGroupProfile(Base, AuditMixin):
    __tablename__ = "core3_m10c_sku_target_group_profile"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "taxonomy_version",
            "sku_code",
            "rule_version",
            "is_current",
            name="uq_core3_m10c_profile_current",
        ),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_m10c_profile_confidence"),
        Index("ix_core3_m10c_profile_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m10c_profile_sku", "project_id", "category_code", "batch_id", "sku_code"),
        Index("ix_core3_m10c_profile_primary", "primary_target_group_code"),
        Index("ix_core3_m10c_profile_size_price", "size_tier", "price_band_in_size_tier"),
        Index("ix_core3_m10c_profile_secondary_gin", "secondary_target_group_codes_json", postgresql_using="gin"),
        Index("ix_core3_m10c_profile_observed_gin", "comment_observed_group_codes_json", postgresql_using="gin"),
        Index("ix_core3_m10c_profile_claimed_gin", "brand_claimed_group_codes_json", postgresql_using="gin"),
        Index("ix_core3_m10c_profile_latent_gin", "latent_group_codes_json", postgresql_using="gin"),
        Index("ix_core3_m10c_profile_unmet_gin", "unmet_group_need_codes_json", postgresql_using="gin"),
        Index("ix_core3_m10c_profile_summary_gin", "target_group_summary_json", postgresql_using="gin"),
        Index("ix_core3_m10c_profile_evidence_gin", "evidence_ids_json", postgresql_using="gin"),
    )

    profile_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    product_category: Mapped[str] = mapped_column(String(40), nullable=False, default="TV", index=True)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m10c_tv_target_group_profile_v0.1", index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    size_tier: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown", index=True)
    price_band_in_size_tier: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    price_percentile_in_size_tier: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    primary_target_group_code: Mapped[str | None] = mapped_column(String(160), index=True)
    primary_relation_status: Mapped[str | None] = mapped_column(String(80), index=True)
    secondary_target_group_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    comment_observed_group_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    brand_claimed_group_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    latent_group_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    unmet_group_need_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    target_group_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    evidence_ids_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    profile_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3M10cSkuTargetGroupScore(Base, AuditMixin):
    __tablename__ = "core3_m10c_sku_target_group_score"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "taxonomy_version",
            "sku_code",
            "target_group_code",
            "rule_version",
            "is_current",
            name="uq_core3_m10c_score_current",
        ),
        CheckConstraint("target_group_score >= 0 and target_group_score <= 1", name="ck_m10c_score_final"),
        CheckConstraint("comment_audience_motivation_score >= 0 and comment_audience_motivation_score <= 1", name="ck_m10c_score_comment"),
        CheckConstraint("task_support_score >= 0 and task_support_score <= 1", name="ck_m10c_score_task"),
        CheckConstraint("size_price_fit_score >= 0 and size_price_fit_score <= 1", name="ck_m10c_score_size_price"),
        CheckConstraint("claim_alignment_score >= 0 and claim_alignment_score <= 1", name="ck_m10c_score_claim"),
        CheckConstraint("param_capability_score >= 0 and param_capability_score <= 1", name="ck_m10c_score_param"),
        CheckConstraint("market_validation_score >= 0 and market_validation_score <= 1", name="ck_m10c_score_market"),
        CheckConstraint("brand_trust_boost >= 0 and brand_trust_boost <= 1", name="ck_m10c_score_brand"),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_m10c_score_confidence"),
        Index("ix_core3_m10c_score_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m10c_score_sku", "project_id", "category_code", "batch_id", "sku_code"),
        Index("ix_core3_m10c_score_group", "project_id", "category_code", "batch_id", "target_group_code", "relation_status"),
        Index("ix_core3_m10c_score_size_price", "size_tier", "price_band_in_size_tier"),
        Index("ix_core3_m10c_score_breakdown_gin", "score_breakdown_json", postgresql_using="gin"),
        Index("ix_core3_m10c_score_evidence_gin", "evidence_ids_json", postgresql_using="gin"),
    )

    score_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    product_category: Mapped[str] = mapped_column(String(40), nullable=False, default="TV", index=True)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m10c_tv_target_group_profile_v0.1", index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    target_group_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    target_group_name: Mapped[str] = mapped_column(String(240), nullable=False)
    target_group_definition: Mapped[str] = mapped_column(Text, nullable=False)
    relation_status: Mapped[str] = mapped_column(String(80), nullable=False, default="not_supported", index=True)
    target_group_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    comment_audience_motivation_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    task_support_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    size_price_fit_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    claim_alignment_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    param_capability_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    market_validation_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    brand_trust_boost: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    sentiment_polarity: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    size_tier: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown", index=True)
    price_band_in_size_tier: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    price_percentile_in_size_tier: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    score_breakdown_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    status_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3M10cTargetGroupCoverage(Base, AuditMixin):
    __tablename__ = "core3_m10c_target_group_coverage"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "taxonomy_version",
            "target_group_code",
            "rule_version",
            "is_current",
            name="uq_core3_m10c_coverage_current",
        ),
        Index("ix_core3_m10c_coverage_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m10c_coverage_group", "project_id", "category_code", "batch_id", "target_group_code"),
        Index("ix_core3_m10c_coverage_status_gin", "relation_status_counts_json", postgresql_using="gin"),
        Index("ix_core3_m10c_coverage_top_gin", "top_skus_json", postgresql_using="gin"),
    )

    coverage_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    product_category: Mapped[str] = mapped_column(String(40), nullable=False, default="TV", index=True)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m10c_tv_target_group_profile_v0.1", index=True)
    target_group_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    target_group_name: Mapped[str] = mapped_column(String(240), nullable=False)
    sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    relation_status_counts_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    primary_sku_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    secondary_sku_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    comment_observed_sku_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    brand_claimed_sku_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    latent_sku_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    unmet_need_sku_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    top_skus_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    coverage_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3SkuValueBattlefieldProfile(Base, AuditMixin):
    __tablename__ = "core3_sku_value_battlefield_profile"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "taxonomy_version",
            "sku_code",
            "rule_version",
            "is_current",
            name="uq_core3_m11c_profile_current",
        ),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_m11c_profile_confidence"),
        Index("ix_core3_m11c_profile_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m11c_profile_sku", "project_id", "category_code", "batch_id", "sku_code"),
        Index("ix_core3_m11c_profile_primary", "primary_battlefield_code"),
        Index("ix_core3_m11c_profile_size_price", "size_tier", "price_band_in_size_tier"),
        Index("ix_core3_m11c_profile_secondary_gin", "secondary_battlefield_codes_json", postgresql_using="gin"),
        Index("ix_core3_m11c_profile_opportunity_gin", "opportunity_battlefield_codes_json", postgresql_using="gin"),
        Index("ix_core3_m11c_profile_drag_gin", "drag_factor_battlefield_codes_json", postgresql_using="gin"),
        Index("ix_core3_m11c_profile_summary_gin", "battlefield_summary_json", postgresql_using="gin"),
        Index("ix_core3_m11c_profile_evidence_gin", "evidence_ids_json", postgresql_using="gin"),
    )

    profile_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    product_category: Mapped[str] = mapped_column(String(40), nullable=False, default="TV", index=True)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m11c_tv_value_battlefield_profile_v0.1", index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    size_tier: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown", index=True)
    price_band_in_size_tier: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    price_percentile_in_size_tier: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    primary_battlefield_code: Mapped[str | None] = mapped_column(String(160), index=True)
    primary_relation_status: Mapped[str | None] = mapped_column(String(80), index=True)
    secondary_battlefield_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    opportunity_battlefield_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    drag_factor_battlefield_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    battlefield_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    evidence_ids_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    profile_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3SkuValueBattlefieldScore(Base, AuditMixin):
    __tablename__ = "core3_sku_value_battlefield_score"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "taxonomy_version",
            "sku_code",
            "battlefield_code",
            "rule_version",
            "is_current",
            name="uq_core3_m11c_score_current",
        ),
        CheckConstraint("battlefield_score >= 0 and battlefield_score <= 1", name="ck_m11c_score_final"),
        CheckConstraint("market_pool_fit_score >= 0 and market_pool_fit_score <= 1", name="ck_m11c_score_market_fit"),
        CheckConstraint("user_voice_score >= 0 and user_voice_score <= 1", name="ck_m11c_score_user_voice"),
        CheckConstraint("task_group_fit_score >= 0 and task_group_fit_score <= 1", name="ck_m11c_score_task_group"),
        CheckConstraint("claim_alignment_score >= 0 and claim_alignment_score <= 1", name="ck_m11c_score_claim"),
        CheckConstraint("param_capability_score >= 0 and param_capability_score <= 1", name="ck_m11c_score_param"),
        CheckConstraint("market_validation_score >= 0 and market_validation_score <= 1", name="ck_m11c_score_market_validation"),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_m11c_score_confidence"),
        Index("ix_core3_m11c_score_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m11c_score_sku", "project_id", "category_code", "batch_id", "sku_code"),
        Index("ix_core3_m11c_score_battlefield", "project_id", "category_code", "batch_id", "battlefield_code", "relation_status"),
        Index("ix_core3_m11c_score_size_price", "size_tier", "price_band_in_size_tier"),
        Index("ix_core3_m11c_score_breakdown_gin", "score_breakdown_json", postgresql_using="gin"),
        Index("ix_core3_m11c_score_evidence_gin", "evidence_ids_json", postgresql_using="gin"),
    )

    score_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    product_category: Mapped[str] = mapped_column(String(40), nullable=False, default="TV", index=True)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m11c_tv_value_battlefield_profile_v0.1", index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    battlefield_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    battlefield_name: Mapped[str] = mapped_column(String(240), nullable=False)
    battlefield_definition: Mapped[str] = mapped_column(Text, nullable=False)
    relation_status: Mapped[str] = mapped_column(String(80), nullable=False, default="excluded", index=True)
    value_effect: Mapped[str] = mapped_column(String(80), nullable=False, default="not_applicable", index=True)
    battlefield_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    market_gate_status: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    market_pool_fit_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    user_voice_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    task_group_fit_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    claim_alignment_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    param_capability_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    market_validation_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    sentiment_polarity: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    size_tier: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown", index=True)
    price_band_in_size_tier: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    price_percentile_in_size_tier: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    score_breakdown_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    status_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.0000"))
    result_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3ValueBattlefieldGraphSnapshot(Base, AuditMixin):
    __tablename__ = "core3_value_battlefield_graph_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "taxonomy_version",
            "rule_version",
            "is_current",
            name="uq_core3_m11c_graph_current",
        ),
        Index("ix_core3_m11c_graph_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m11c_graph_graph_gin", "graph_json", postgresql_using="gin"),
        Index("ix_core3_m11c_graph_coverage_gin", "coverage_summary_json", postgresql_using="gin"),
    )

    graph_snapshot_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    product_category: Mapped[str] = mapped_column(String(40), nullable=False, default="TV", index=True)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m11c_tv_value_battlefield_profile_v0.1", index=True)
    node_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    edge_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    battlefield_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    graph_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    coverage_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    graph_hash: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3SemanticMarketAllocation(Base, AuditMixin):
    __tablename__ = "core3_semantic_market_allocation"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "analysis_population",
            "market_window",
            "dimension_type",
            "sku_code",
            "dimension_code",
            "rule_version",
            "is_current",
            name="uq_core3_m11d_allocation_current",
        ),
        CheckConstraint("allocation_weight >= 0 and allocation_weight <= 1", name="ck_m11d_allocation_weight"),
        CheckConstraint("allocation_confidence >= 0 and allocation_confidence <= 1", name="ck_m11d_allocation_confidence"),
        CheckConstraint("final_score >= 0 and final_score <= 1", name="ck_m11d_allocation_final_score"),
        Index("ix_core3_m11d_allocation_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m11d_allocation_sku", "project_id", "category_code", "batch_id", "sku_code"),
        Index("ix_core3_m11d_allocation_dimension", "project_id", "category_code", "batch_id", "dimension_type", "dimension_code"),
        Index("ix_core3_m11d_allocation_population_window", "analysis_population", "market_window"),
        Index("ix_core3_m11d_allocation_basis_gin", "allocation_basis_json", postgresql_using="gin"),
        Index("ix_core3_m11d_allocation_evidence_gin", "evidence_ids_json", postgresql_using="gin"),
    )

    allocation_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    product_category: Mapped[str] = mapped_column(String(40), nullable=False, default="TV", index=True)
    analysis_population: Mapped[str] = mapped_column(String(80), nullable=False, default="fact_complete_with_comment", index=True)
    market_window: Mapped[str] = mapped_column(String(80), nullable=False, default="full_observed_window", index=True)
    window_start_week: Mapped[int | None] = mapped_column(Integer)
    window_end_week: Mapped[int | None] = mapped_column(Integer)
    active_week_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dimension_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    dimension_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    dimension_name: Mapped[str] = mapped_column(String(240), nullable=False)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    brand_name: Mapped[str | None] = mapped_column(String(160))
    model_name: Mapped[str | None] = mapped_column(String(240))
    size_tier: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown", index=True)
    price_band_in_size_tier: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    price_percentile_in_size_tier: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    relation_status: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    allocation_role: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    allocation_value_type: Mapped[str] = mapped_column(String(80), nullable=False, default="positive_value", index=True)
    source_profile_id: Mapped[str | None] = mapped_column(String(120), index=True)
    source_score_id: Mapped[str | None] = mapped_column(String(120), index=True)
    final_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    allocation_basis: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    relation_factor: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    allocation_weight: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    sales_volume_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    sales_amount_total: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    avg_weekly_sales_volume: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0.000000"))
    avg_weekly_sales_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0.000000"))
    allocated_sales_volume: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    allocated_sales_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    allocated_avg_weekly_sales_volume: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0.000000"))
    allocated_avg_weekly_sales_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0.000000"))
    allocation_confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    allocation_basis_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_ids_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    market_source_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m11d_semantic_market_allocation_v0.1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SemanticMarketDimensionSummary(Base, AuditMixin):
    __tablename__ = "core3_semantic_market_dimension_summary"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "analysis_population",
            "market_window",
            "dimension_type",
            "dimension_code",
            "rule_version",
            "is_current",
            name="uq_core3_m11d_summary_current",
        ),
        CheckConstraint("sales_volume_share >= 0 and sales_volume_share <= 1", name="ck_m11d_summary_volume_share"),
        CheckConstraint("sales_amount_share >= 0 and sales_amount_share <= 1", name="ck_m11d_summary_amount_share"),
        CheckConstraint("allocation_coverage_rate >= 0 and allocation_coverage_rate <= 1", name="ck_m11d_summary_coverage"),
        CheckConstraint("confidence_avg >= 0 and confidence_avg <= 1", name="ck_m11d_summary_confidence"),
        Index("ix_core3_m11d_summary_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m11d_summary_dimension", "project_id", "category_code", "batch_id", "dimension_type", "dimension_code"),
        Index("ix_core3_m11d_summary_window", "analysis_population", "market_window"),
        Index("ix_core3_m11d_summary_top_gin", "top_skus_json", postgresql_using="gin"),
        Index("ix_core3_m11d_summary_distribution_gin", "size_price_distribution_json", postgresql_using="gin"),
    )

    summary_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    product_category: Mapped[str] = mapped_column(String(40), nullable=False, default="TV", index=True)
    analysis_population: Mapped[str] = mapped_column(String(80), nullable=False, default="fact_complete_with_comment", index=True)
    market_window: Mapped[str] = mapped_column(String(80), nullable=False, default="full_observed_window", index=True)
    dimension_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    dimension_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    dimension_name: Mapped[str] = mapped_column(String(240), nullable=False)
    taxonomy_version: Mapped[str] = mapped_column(String(160), nullable=False, default="unknown", index=True)
    sku_relation_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    allocated_sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    primary_sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    secondary_sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observed_need_sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    brand_claim_sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    opportunity_sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    drag_risk_sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_sales_volume: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    estimated_sales_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    estimated_avg_weekly_sales_volume: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0.000000"))
    estimated_avg_weekly_sales_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0.000000"))
    observed_need_sales_volume: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    observed_need_sales_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    drag_risk_market_volume: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    drag_risk_market_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    total_market_sales_volume: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    total_market_sales_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    allocated_market_sales_volume: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    allocated_market_sales_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    unallocated_market_sales_volume: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    unallocated_market_sales_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    sales_volume_share: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    sales_amount_share: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    allocation_coverage_rate: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    brand_distribution_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    size_price_distribution_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    relation_status_counts_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    top_skus_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    confidence_avg: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    business_summary_cn: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m11d_semantic_market_allocation_v0.1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SemanticMarketSkuContribution(Base, AuditMixin):
    __tablename__ = "core3_semantic_market_sku_contribution"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "analysis_population",
            "market_window",
            "dimension_type",
            "dimension_code",
            "sku_code",
            "rule_version",
            "is_current",
            name="uq_core3_m11d_contribution_current",
        ),
        CheckConstraint("allocation_weight >= 0 and allocation_weight <= 1", name="ck_m11d_contribution_weight"),
        CheckConstraint("sku_share_in_dimension_volume >= 0 and sku_share_in_dimension_volume <= 1", name="ck_m11d_contribution_volume_share"),
        CheckConstraint("sku_share_in_dimension_amount >= 0 and sku_share_in_dimension_amount <= 1", name="ck_m11d_contribution_amount_share"),
        CheckConstraint("allocation_confidence >= 0 and allocation_confidence <= 1", name="ck_m11d_contribution_confidence"),
        Index("ix_core3_m11d_contribution_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m11d_contribution_dimension", "project_id", "category_code", "batch_id", "dimension_type", "dimension_code"),
        Index("ix_core3_m11d_contribution_sku", "project_id", "category_code", "batch_id", "sku_code"),
    )

    contribution_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    summary_id: Mapped[str | None] = mapped_column(ForeignKey("core3_semantic_market_dimension_summary.summary_id"), index=True)
    allocation_id: Mapped[str | None] = mapped_column(ForeignKey("core3_semantic_market_allocation.allocation_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    product_category: Mapped[str] = mapped_column(String(40), nullable=False, default="TV", index=True)
    analysis_population: Mapped[str] = mapped_column(String(80), nullable=False, default="fact_complete_with_comment", index=True)
    market_window: Mapped[str] = mapped_column(String(80), nullable=False, default="full_observed_window", index=True)
    dimension_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    dimension_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    dimension_name: Mapped[str] = mapped_column(String(240), nullable=False)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    brand_name: Mapped[str | None] = mapped_column(String(160))
    model_name: Mapped[str | None] = mapped_column(String(240))
    allocation_weight: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    allocated_sales_volume: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    allocated_sales_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    allocated_avg_weekly_sales_volume: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0.000000"))
    allocated_avg_weekly_sales_amount: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0.000000"))
    sku_share_in_dimension_volume: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    sku_share_in_dimension_amount: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    sku_rank_in_dimension: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    is_primary_dimension: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    allocation_role: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    relation_status: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    allocation_confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    contribution_reason_cn: Mapped[str] = mapped_column(Text, nullable=False, default="")
    evidence_ids_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m11d_semantic_market_allocation_v0.1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)


class Core3SemanticMarketGraphSnapshot(Base, AuditMixin):
    __tablename__ = "core3_semantic_market_graph_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "analysis_population",
            "market_window",
            "rule_version",
            "is_current",
            name="uq_core3_m11d_graph_current",
        ),
        Index("ix_core3_m11d_graph_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m11d_graph_window", "analysis_population", "market_window"),
        Index("ix_core3_m11d_graph_graph_gin", "graph_json", postgresql_using="gin"),
        Index("ix_core3_m11d_graph_coverage_gin", "coverage_summary_json", postgresql_using="gin"),
    )

    graph_snapshot_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    product_category: Mapped[str] = mapped_column(String(40), nullable=False, default="TV", index=True)
    analysis_population: Mapped[str] = mapped_column(String(80), nullable=False, default="fact_complete_with_comment", index=True)
    market_window: Mapped[str] = mapped_column(String(80), nullable=False, default="full_observed_window", index=True)
    node_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    edge_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dimension_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    graph_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    coverage_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    allocation_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    unallocated_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m11d_semantic_market_allocation_v0.1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    graph_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3SemanticMarketReconciliationCheck(Base, AuditMixin):
    __tablename__ = "core3_semantic_market_reconciliation_check"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "analysis_population",
            "market_window",
            "check_type",
            "sku_code",
            "dimension_type",
            "dimension_code",
            "input_fingerprint",
            name="uq_core3_m11d_check_key",
        ),
        Index("ix_core3_m11d_check_batch", "project_id", "category_code", "batch_id", "status"),
        Index("ix_core3_m11d_check_dimension", "project_id", "category_code", "batch_id", "dimension_type", "dimension_code"),
        Index("ix_core3_m11d_check_sku", "project_id", "category_code", "batch_id", "sku_code"),
    )

    check_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    product_category: Mapped[str] = mapped_column(String(40), nullable=False, default="TV", index=True)
    analysis_population: Mapped[str] = mapped_column(String(80), nullable=False, default="fact_complete_with_comment", index=True)
    market_window: Mapped[str] = mapped_column(String(80), nullable=False, default="full_observed_window", index=True)
    check_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, default="", index=True)
    dimension_type: Mapped[str] = mapped_column(String(60), nullable=False, default="", index=True)
    dimension_code: Mapped[str] = mapped_column(String(160), nullable=False, default="", index=True)
    expected_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0.000000"))
    actual_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0.000000"))
    gap_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0.000000"))
    tolerance_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0.000000"))
    status: Mapped[str] = mapped_column(String(60), nullable=False, default="passed", index=True)
    severity: Mapped[str] = mapped_column(String(40), nullable=False, default="info", index=True)
    failure_reason_code: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    failure_reason_cn: Mapped[str] = mapped_column(Text, nullable=False, default="")
    check_payload_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m11d_semantic_market_allocation_v0.1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SkuBattlefieldClaimCandidate(Base, AuditMixin):
    __tablename__ = "core3_sku_battlefield_claim_candidate"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "battlefield_code",
            "claim_code",
            "rule_version",
            "claim_seed_hash",
            "battlefield_seed_hash",
            name="uq_core3_m115_candidate_key",
        ),
        CheckConstraint("candidate_initial_score >= 0 and candidate_initial_score <= 1", name="ck_m115_candidate_score"),
        Index("ix_core3_m115_candidate_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m115_candidate_sku_bf", "project_id", "category_code", "batch_id", "sku_code", "battlefield_code"),
        Index("ix_core3_m115_candidate_claim", "project_id", "category_code", "batch_id", "claim_code", "candidate_status"),
        Index("ix_core3_m115_candidate_review", "project_id", "category_code", "batch_id", "review_required", "review_status"),
        Index("ix_core3_m115_candidate_source_gin", "candidate_source_json", postgresql_using="gin"),
        Index("ix_core3_m115_candidate_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    sku_battlefield_claim_candidate_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_signal_profile_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_signal_profile.sku_signal_profile_id"), index=True)
    sku_downstream_feature_view_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_downstream_feature_view.sku_downstream_feature_view_id"), index=True)
    sku_battlefield_score_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_battlefield_score.sku_battlefield_score_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_code: Mapped[str | None] = mapped_column(String(160))
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    battlefield_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    battlefield_name_cn: Mapped[str] = mapped_column(String(240), nullable=False)
    battlefield_relation_level: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    claim_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    claim_name_cn: Mapped[str] = mapped_column(String(240), nullable=False)
    claim_group: Mapped[str | None] = mapped_column(String(80), index=True)
    candidate_source_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    candidate_source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    candidate_initial_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    candidate_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    reject_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    missing_signals_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    risk_flags_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_matrix_refs_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    feature_view_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    battlefield_score_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    claim_seed_version: Mapped[str] = mapped_column(String(120), nullable=False, default="tv_core3_mvp_seed_v0_2", index=True)
    claim_seed_file_version: Mapped[str] = mapped_column(String(120), nullable=False)
    claim_seed_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    battlefield_seed_version: Mapped[str] = mapped_column(String(120), nullable=False, default="tv_core3_mvp_seed_v0_2", index=True)
    battlefield_seed_file_version: Mapped[str] = mapped_column(String(120), nullable=False)
    battlefield_seed_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m11_5_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SkuClaimValueLayer(Base, AuditMixin):
    __tablename__ = "core3_sku_claim_value_layer"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "battlefield_code",
            "claim_code",
            "rule_version",
            "claim_seed_hash",
            "battlefield_seed_hash",
            name="uq_core3_m115_layer_key",
        ),
        CheckConstraint("claim_activation_score >= 0 and claim_activation_score <= 1", name="ck_m115_layer_activation"),
        CheckConstraint("coverage_position_score >= 0 and coverage_position_score <= 1", name="ck_m115_layer_coverage_position"),
        CheckConstraint("price_support_score >= 0 and price_support_score <= 1", name="ck_m115_layer_price_support"),
        CheckConstraint("sales_support_score >= 0 and sales_support_score <= 1", name="ck_m115_layer_sales_support"),
        CheckConstraint("comment_perception_score >= 0 and comment_perception_score <= 1", name="ck_m115_layer_comment_support"),
        CheckConstraint("claim_value_score >= 0 and claim_value_score <= 1", name="ck_m115_layer_score"),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_m115_layer_confidence"),
        Index("ix_core3_m115_layer_sku_bf", "project_id", "category_code", "batch_id", "sku_code", "battlefield_code", "layer"),
        Index("ix_core3_m115_layer_claim", "project_id", "category_code", "batch_id", "claim_code", "layer"),
        Index("ix_core3_m115_layer_downstream", "project_id", "category_code", "batch_id", "sku_code", "battlefield_code", "layer", "claim_value_score"),
        Index("ix_core3_m115_layer_reason_gin", "layer_reason_json", postgresql_using="gin"),
        Index("ix_core3_m115_layer_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    sku_claim_value_layer_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    sku_battlefield_claim_candidate_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_battlefield_claim_candidate.sku_battlefield_claim_candidate_id"), index=True)
    sku_signal_profile_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_signal_profile.sku_signal_profile_id"), index=True)
    sku_downstream_feature_view_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_downstream_feature_view.sku_downstream_feature_view_id"), index=True)
    sku_battlefield_score_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_battlefield_score.sku_battlefield_score_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_code: Mapped[str | None] = mapped_column(String(160))
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    battlefield_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    battlefield_name_cn: Mapped[str] = mapped_column(String(240), nullable=False)
    battlefield_relation_level: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    claim_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    claim_name_cn: Mapped[str] = mapped_column(String(240), nullable=False)
    claim_group: Mapped[str | None] = mapped_column(String(80), index=True)
    claim_activation_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    activation_basis_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    battlefield_relevance_role: Mapped[str] = mapped_column(String(60), nullable=False, default="not_applicable", index=True)
    comparable_pool_id: Mapped[str | None] = mapped_column(String(160), index=True)
    pool_type: Mapped[str | None] = mapped_column(String(80), index=True)
    pool_sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    with_claim_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    without_claim_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    coverage_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    coverage_position_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    psi: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    ssi: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    sai: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    cpi: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    positive_mention_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    negative_mention_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    neutral_mention_rate: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    price_support_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    sales_support_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    comment_perception_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    risk_penalty: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    claim_value_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    layer: Mapped[str] = mapped_column(String(80), nullable=False, default="insufficient_sample", index=True)
    layer_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    confidence_level: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    sample_sufficiency: Mapped[str] = mapped_column(String(60), nullable=False, default="unknown", index=True)
    sample_sufficiency_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    missing_signals_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    risk_flags_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    business_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    business_reason_parts_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    next_module_payload_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_matrix_refs_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    feature_view_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    battlefield_score_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    claim_seed_version: Mapped[str] = mapped_column(String(120), nullable=False, default="tv_core3_mvp_seed_v0_2", index=True)
    claim_seed_file_version: Mapped[str] = mapped_column(String(120), nullable=False)
    claim_seed_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    battlefield_seed_version: Mapped[str] = mapped_column(String(120), nullable=False, default="tv_core3_mvp_seed_v0_2", index=True)
    battlefield_seed_file_version: Mapped[str] = mapped_column(String(120), nullable=False)
    battlefield_seed_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m11_5_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SkuClaimValueEvidenceBreakdown(Base, AuditMixin):
    __tablename__ = "core3_sku_claim_value_evidence_breakdown"
    __table_args__ = (
        UniqueConstraint(
            "sku_claim_value_layer_id",
            "evidence_domain",
            "claim_seed_version",
            "battlefield_seed_version",
            "rule_version",
            name="uq_core3_m115_breakdown_key",
        ),
        CheckConstraint("support_score >= 0 and support_score <= 1", name="ck_m115_breakdown_score"),
        CheckConstraint("domain_weight >= 0 and domain_weight <= 1", name="ck_m115_breakdown_weight"),
        CheckConstraint("weighted_contribution >= 0 and weighted_contribution <= 1", name="ck_m115_breakdown_weighted"),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_m115_breakdown_confidence"),
        Index("ix_core3_m115_breakdown_layer", "sku_claim_value_layer_id", "evidence_domain"),
        Index("ix_core3_m115_breakdown_sku_bf_claim", "project_id", "category_code", "batch_id", "sku_code", "battlefield_code", "claim_code"),
        Index("ix_core3_m115_breakdown_support", "project_id", "category_code", "batch_id", "evidence_domain", "support_level"),
        Index("ix_core3_m115_breakdown_evidence_gin", "representative_evidence_ids", postgresql_using="gin"),
    )

    sku_claim_value_evidence_breakdown_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    sku_claim_value_layer_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_claim_value_layer.sku_claim_value_layer_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_code: Mapped[str | None] = mapped_column(String(160))
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    battlefield_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    battlefield_name_cn: Mapped[str] = mapped_column(String(240), nullable=False)
    claim_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    claim_name_cn: Mapped[str] = mapped_column(String(240), nullable=False)
    evidence_domain: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    support_level: Mapped[str] = mapped_column(String(60), nullable=False, default="missing", index=True)
    support_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    domain_weight: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    weighted_contribution: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    support_summary_cn: Mapped[str] = mapped_column(Text, nullable=False)
    source_signal_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    source_values_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    representative_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_matrix_refs_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    missing_reason_code: Mapped[str | None] = mapped_column(String(120))
    risk_flags_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    feature_view_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    battlefield_score_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    claim_seed_version: Mapped[str] = mapped_column(String(120), nullable=False, default="tv_core3_mvp_seed_v0_2", index=True)
    claim_seed_file_version: Mapped[str] = mapped_column(String(120), nullable=False)
    claim_seed_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    battlefield_seed_version: Mapped[str] = mapped_column(String(120), nullable=False, default="tv_core3_mvp_seed_v0_2", index=True)
    battlefield_seed_file_version: Mapped[str] = mapped_column(String(120), nullable=False)
    battlefield_seed_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m11_5_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3SkuBattlefieldClaimValueSummary(Base, AuditMixin):
    __tablename__ = "core3_sku_battlefield_claim_value_summary"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "battlefield_code",
            "rule_version",
            "claim_seed_hash",
            "battlefield_seed_hash",
            name="uq_core3_m115_summary_key",
        ),
        CheckConstraint("summary_confidence >= 0 and summary_confidence <= 1", name="ck_m115_summary_confidence"),
        Index("ix_core3_m115_summary_sku_bf", "project_id", "category_code", "batch_id", "sku_code", "battlefield_code"),
        Index("ix_core3_m115_summary_confidence", "project_id", "category_code", "batch_id", "summary_confidence", "review_required"),
        Index("ix_core3_m115_summary_focus_gin", "comparison_focus_claims_json", postgresql_using="gin"),
    )

    sku_battlefield_claim_value_summary_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    sku_signal_profile_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_signal_profile.sku_signal_profile_id"), index=True)
    sku_downstream_feature_view_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_downstream_feature_view.sku_downstream_feature_view_id"), index=True)
    sku_battlefield_score_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_battlefield_score.sku_battlefield_score_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_code: Mapped[str | None] = mapped_column(String(160))
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    battlefield_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    battlefield_name_cn: Mapped[str] = mapped_column(String(240), nullable=False)
    battlefield_relation_level: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    premium_claims_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    performance_claims_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    threshold_claims_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    weak_claims_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    insufficient_claims_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    not_applicable_claims_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    claim_value_profile_cn: Mapped[str] = mapped_column(Text, nullable=False)
    comparison_focus_claims_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    summary_confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    summary_risk_flags_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    claim_value_layer_refs_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    feature_view_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    battlefield_score_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    claim_seed_version: Mapped[str] = mapped_column(String(120), nullable=False, default="tv_core3_mvp_seed_v0_2", index=True)
    claim_seed_file_version: Mapped[str] = mapped_column(String(120), nullable=False)
    claim_seed_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    battlefield_seed_version: Mapped[str] = mapped_column(String(120), nullable=False, default="tv_core3_mvp_seed_v0_2", index=True)
    battlefield_seed_file_version: Mapped[str] = mapped_column(String(120), nullable=False)
    battlefield_seed_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m11_5_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SkuClaimValueReviewIssue(Base, AuditMixin):
    __tablename__ = "core3_sku_claim_value_review_issue"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "battlefield_code",
            "claim_code",
            "issue_type",
            "input_fingerprint",
            name="uq_core3_m115_review_issue_key",
        ),
        Index("ix_core3_m115_review_open", "project_id", "category_code", "batch_id", "resolved_status", "issue_level"),
        Index("ix_core3_m115_review_sku_bf_claim", "project_id", "category_code", "batch_id", "sku_code", "battlefield_code", "claim_code"),
        Index("ix_core3_m115_review_type", "project_id", "category_code", "batch_id", "issue_type"),
        Index("ix_core3_m115_review_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    sku_claim_value_review_issue_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    related_layer_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_claim_value_layer.sku_claim_value_layer_id"), index=True)
    related_candidate_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_battlefield_claim_candidate.sku_battlefield_claim_candidate_id"), index=True)
    related_battlefield_score_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_battlefield_score.sku_battlefield_score_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_code: Mapped[str | None] = mapped_column(String(160))
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    battlefield_code: Mapped[str] = mapped_column(String(160), nullable=False, default="", index=True)
    battlefield_name_cn: Mapped[str | None] = mapped_column(String(240))
    claim_code: Mapped[str] = mapped_column(String(160), nullable=False, default="", index=True)
    claim_name_cn: Mapped[str | None] = mapped_column(String(240))
    issue_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    issue_level: Mapped[str] = mapped_column(String(40), nullable=False, default="warning", index=True)
    issue_message_cn: Mapped[str] = mapped_column(Text, nullable=False)
    issue_context_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    feature_view_hash: Mapped[str] = mapped_column(String(160), nullable=False, default="", index=True)
    battlefield_score_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    claim_seed_version: Mapped[str] = mapped_column(String(120), nullable=False, default="tv_core3_mvp_seed_v0_2", index=True)
    claim_seed_file_version: Mapped[str] = mapped_column(String(120), nullable=False)
    claim_seed_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    battlefield_seed_version: Mapped[str] = mapped_column(String(120), nullable=False, default="tv_core3_mvp_seed_v0_2", index=True)
    battlefield_seed_file_version: Mapped[str] = mapped_column(String(120), nullable=False)
    battlefield_seed_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m11_5_v1", index=True)
    resolved_status: Mapped[str] = mapped_column(String(40), nullable=False, default="open", index=True)
    resolved_by: Mapped[str | None] = mapped_column(String(160))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="warning", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="review_required", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SkuBusinessProfile(Base, AuditMixin):
    __tablename__ = "core3_sku_business_profile"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "rule_version",
            name="uq_core3_m116_profile_key",
        ),
        CheckConstraint("primary_task_score >= 0 and primary_task_score <= 1", name="ck_m116_profile_task_score"),
        CheckConstraint("primary_target_group_score >= 0 and primary_target_group_score <= 1", name="ck_m116_profile_group_score"),
        CheckConstraint("primary_battlefield_score >= 0 and primary_battlefield_score <= 1", name="ck_m116_profile_bf_score"),
        CheckConstraint("claim_value_strength >= 0 and claim_value_strength <= 1", name="ck_m116_profile_claim_strength"),
        CheckConstraint("premium_score >= 0 and premium_score <= 1", name="ck_m116_profile_premium_score"),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_m116_profile_confidence"),
        Index("ix_core3_m116_profile_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m116_profile_sku", "project_id", "category_code", "batch_id", "sku_code"),
        Index("ix_core3_m116_profile_primary_bf", "project_id", "category_code", "batch_id", "primary_battlefield_code"),
        Index("ix_core3_m116_profile_role", "project_id", "category_code", "batch_id", "market_role"),
        Index("ix_core3_m116_profile_premium", "project_id", "category_code", "batch_id", "premium_type"),
        Index("ix_core3_m116_profile_current", "project_id", "category_code", "batch_id", "is_current"),
        Index("ix_core3_m116_profile_claims_gin", "core_claims_json", postgresql_using="gin"),
        Index("ix_core3_m116_profile_alloc_gin", "sales_allocation_summary_json", postgresql_using="gin"),
        Index("ix_core3_m116_profile_evidence_gin", "representative_evidence_ids", postgresql_using="gin"),
    )

    sku_business_profile_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    sku_signal_profile_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_signal_profile.sku_signal_profile_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(120), index=True)
    module_run_id: Mapped[str | None] = mapped_column(String(120), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    model_code: Mapped[str | None] = mapped_column(String(160))
    model_name: Mapped[str | None] = mapped_column(String(240))
    brand_name: Mapped[str | None] = mapped_column(String(160))
    series_name: Mapped[str | None] = mapped_column(String(160))
    screen_size_inch: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    size_segment: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    price_band: Mapped[str] = mapped_column(String(60), nullable=False, default="unknown", index=True)
    main_platform: Mapped[str | None] = mapped_column(String(80), index=True)
    sales_volume_total: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    sales_amount_total: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    price_wavg: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    price_latest: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    price_percentile_in_pool: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    sales_percentile_in_pool: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    amount_percentile_in_pool: Mapped[Decimal | None] = mapped_column(Numeric(8, 6))
    price_gap_to_pool_median: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    market_sample_status: Mapped[str] = mapped_column(String(60), nullable=False, default="unknown", index=True)
    market_source: Mapped[str] = mapped_column(String(60), nullable=False, default="M08", index=True)
    primary_task_code: Mapped[str | None] = mapped_column(String(160), index=True)
    primary_task_name: Mapped[str | None] = mapped_column(String(240))
    primary_task_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    primary_task_evidence_level: Mapped[str] = mapped_column(String(60), nullable=False, default="unknown")
    primary_task_confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    primary_target_group_code: Mapped[str | None] = mapped_column(String(160), index=True)
    primary_target_group_name: Mapped[str | None] = mapped_column(String(240))
    primary_target_group_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    primary_target_group_evidence_level: Mapped[str] = mapped_column(String(60), nullable=False, default="unknown")
    primary_target_group_confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    primary_battlefield_code: Mapped[str | None] = mapped_column(String(160), index=True)
    primary_battlefield_name: Mapped[str | None] = mapped_column(String(240))
    primary_battlefield_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    primary_battlefield_evidence_level: Mapped[str] = mapped_column(String(60), nullable=False, default="unknown")
    primary_battlefield_confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    secondary_tasks_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    secondary_target_groups_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    secondary_battlefields_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    core_claims_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    claim_value_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    claim_value_strength: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    premium_position: Mapped[str] = mapped_column(String(60), nullable=False, default="unknown", index=True)
    premium_type: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown", index=True)
    premium_support_level: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown", index=True)
    premium_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    premium_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    premium_risk_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    market_role: Mapped[str] = mapped_column(String(80), nullable=False, default="unknown", index=True)
    market_role_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    competitive_role_hints_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    candidate_recall_priority_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    same_brand_competition_policy: Mapped[str] = mapped_column(String(40), nullable=False, default="allow", index=True)
    sales_allocation_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_strength: Mapped[str] = mapped_column(String(60), nullable=False, default="unknown", index=True)
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    confidence_level: Mapped[str] = mapped_column(String(40), nullable=False, default="unknown", index=True)
    missing_signals_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    risk_signals_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    representative_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    business_summary_cn: Mapped[str] = mapped_column(Text, nullable=False)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m11_6_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SkuBusinessProfileDimension(Base, AuditMixin):
    __tablename__ = "core3_sku_business_profile_dimension"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "dimension_type",
            "dimension_code",
            "rule_version",
            name="uq_core3_m116_dimension_key",
        ),
        CheckConstraint("dimension_score >= 0 and dimension_score <= 1", name="ck_m116_dimension_score"),
        CheckConstraint("normalized_weight >= 0 and normalized_weight <= 1", name="ck_m116_dimension_weight"),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_m116_dimension_confidence"),
        Index("ix_core3_m116_dimension_profile", "sku_business_profile_id", "dimension_type", "dimension_rank"),
        Index("ix_core3_m116_dimension_sku", "project_id", "category_code", "batch_id", "sku_code", "dimension_type"),
        Index("ix_core3_m116_dimension_code", "project_id", "category_code", "batch_id", "dimension_type", "dimension_code"),
        Index("ix_core3_m116_dimension_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    profile_dimension_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    sku_business_profile_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_business_profile.sku_business_profile_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(120), index=True)
    module_run_id: Mapped[str | None] = mapped_column(String(120), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    dimension_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    dimension_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    dimension_name: Mapped[str] = mapped_column(String(240), nullable=False)
    dimension_rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    dimension_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    normalized_weight: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    evidence_level: Mapped[str] = mapped_column(String(60), nullable=False, default="unknown", index=True)
    relation_level: Mapped[str] = mapped_column(String(60), nullable=False, default="unknown", index=True)
    value_layer: Mapped[str | None] = mapped_column(String(80), index=True)
    source_module: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_record_refs_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    support_breakdown_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    business_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m11_6_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3SkuBusinessProfileSalesAllocation(Base, AuditMixin):
    __tablename__ = "core3_sku_business_profile_sales_allocation"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "dimension_type",
            "dimension_code",
            "rule_version",
            name="uq_core3_m116_allocation_key",
        ),
        CheckConstraint("allocation_weight >= 0 and allocation_weight <= 1", name="ck_m116_allocation_weight"),
        CheckConstraint("allocation_confidence >= 0 and allocation_confidence <= 1", name="ck_m116_allocation_confidence"),
        Index("ix_core3_m116_allocation_profile", "sku_business_profile_id", "dimension_type"),
        Index("ix_core3_m116_allocation_sku", "project_id", "category_code", "batch_id", "sku_code", "dimension_type"),
        Index("ix_core3_m116_allocation_code", "project_id", "category_code", "batch_id", "dimension_type", "dimension_code"),
    )

    sales_allocation_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    sku_business_profile_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_business_profile.sku_business_profile_id"), index=True)
    profile_dimension_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_business_profile_dimension.profile_dimension_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(120), index=True)
    module_run_id: Mapped[str | None] = mapped_column(String(120), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    dimension_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    dimension_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    dimension_name: Mapped[str] = mapped_column(String(240), nullable=False)
    allocation_method: Mapped[str] = mapped_column(String(120), nullable=False, default="score_normalized_with_market_volume")
    allocation_weight: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    allocated_sales_volume: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    allocated_sales_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    allocation_confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    allocation_basis_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m11_6_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3SkuBusinessProfileReviewIssue(Base, AuditMixin):
    __tablename__ = "core3_sku_business_profile_review_issue"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "sku_code",
            "dimension_type",
            "dimension_code",
            "issue_type",
            "input_fingerprint",
            name="uq_core3_m116_review_issue_key",
        ),
        Index("ix_core3_m116_review_open", "project_id", "category_code", "batch_id", "resolved_status", "issue_level"),
        Index("ix_core3_m116_review_sku", "project_id", "category_code", "batch_id", "sku_code"),
        Index("ix_core3_m116_review_type", "project_id", "category_code", "batch_id", "issue_type"),
    )

    sku_business_profile_review_issue_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    sku_business_profile_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_business_profile.sku_business_profile_id"), index=True)
    profile_dimension_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_business_profile_dimension.profile_dimension_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(120), index=True)
    module_run_id: Mapped[str | None] = mapped_column(String(120), index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    dimension_type: Mapped[str] = mapped_column(String(60), nullable=False, default="", index=True)
    dimension_code: Mapped[str] = mapped_column(String(160), nullable=False, default="", index=True)
    issue_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    issue_level: Mapped[str] = mapped_column(String(40), nullable=False, default="warning", index=True)
    issue_message_cn: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_action_cn: Mapped[str] = mapped_column(Text, nullable=False)
    issue_context_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m11_6_v1", index=True)
    resolved_status: Mapped[str] = mapped_column(String(40), nullable=False, default="open", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="warning", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="review_required", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3BusinessDimensionSalesSummary(Base, AuditMixin):
    __tablename__ = "core3_business_dimension_sales_summary"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "dimension_type",
            "dimension_code",
            "rule_version",
            name="uq_core3_m117_summary_key",
        ),
        CheckConstraint("sku_count >= 0", name="ck_m117_summary_sku_count"),
        CheckConstraint("primary_sku_count >= 0", name="ck_m117_summary_primary_count"),
        CheckConstraint("sales_volume_share >= 0 and sales_volume_share <= 1", name="ck_m117_summary_volume_share"),
        CheckConstraint("sales_amount_share >= 0 and sales_amount_share <= 1", name="ck_m117_summary_amount_share"),
        CheckConstraint("avg_allocation_confidence >= 0 and avg_allocation_confidence <= 1", name="ck_m117_summary_conf"),
        Index("ix_core3_m117_summary_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m117_summary_dimension", "project_id", "category_code", "batch_id", "dimension_type", "dimension_code"),
        Index("ix_core3_m117_summary_current", "project_id", "category_code", "batch_id", "is_current"),
    )

    dimension_sales_summary_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(120), index=True)
    module_run_id: Mapped[str | None] = mapped_column(String(120), index=True)
    source_m11_6_module_run_id: Mapped[str | None] = mapped_column(String(120), index=True)
    dimension_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    dimension_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    dimension_name: Mapped[str] = mapped_column(String(240), nullable=False)
    standard_dimension_rank: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    primary_sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_sales_volume: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    estimated_sales_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    total_market_sales_volume: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    total_market_sales_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    sales_volume_share: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    sales_amount_share: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    avg_allocation_confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    evidence_quality_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    top_sku_contribution_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    reconciliation_status: Mapped[str] = mapped_column(String(60), nullable=False, default="matched", index=True)
    business_summary_cn: Mapped[str] = mapped_column(Text, nullable=False)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m11_7_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3BusinessDimensionSkuContribution(Base, AuditMixin):
    __tablename__ = "core3_business_dimension_sku_contribution"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "dimension_type",
            "dimension_code",
            "sku_code",
            "rule_version",
            name="uq_core3_m117_contribution_key",
        ),
        CheckConstraint("allocation_weight >= 0 and allocation_weight <= 1", name="ck_m117_contribution_weight"),
        CheckConstraint("sku_share_in_dimension_volume >= 0 and sku_share_in_dimension_volume <= 1", name="ck_m117_contribution_volume_share"),
        CheckConstraint("sku_share_in_dimension_amount >= 0 and sku_share_in_dimension_amount <= 1", name="ck_m117_contribution_amount_share"),
        CheckConstraint("allocation_confidence >= 0 and allocation_confidence <= 1", name="ck_m117_contribution_conf"),
        Index("ix_core3_m117_contribution_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m117_contribution_dimension", "project_id", "category_code", "batch_id", "dimension_type", "dimension_code"),
        Index("ix_core3_m117_contribution_sku", "project_id", "category_code", "batch_id", "sku_code"),
    )

    dimension_sku_contribution_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    dimension_sales_summary_id: Mapped[str | None] = mapped_column(ForeignKey("core3_business_dimension_sales_summary.dimension_sales_summary_id"), index=True)
    sku_business_profile_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_business_profile.sku_business_profile_id"), index=True)
    sales_allocation_id: Mapped[str | None] = mapped_column(ForeignKey("core3_sku_business_profile_sales_allocation.sales_allocation_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(120), index=True)
    module_run_id: Mapped[str | None] = mapped_column(String(120), index=True)
    dimension_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    dimension_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    dimension_name: Mapped[str] = mapped_column(String(240), nullable=False)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    brand_name: Mapped[str | None] = mapped_column(String(160))
    model_name: Mapped[str | None] = mapped_column(String(240))
    allocation_weight: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    allocated_sales_volume: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    allocated_sales_amount: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0.0000"))
    sku_share_in_dimension_volume: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    sku_share_in_dimension_amount: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False, default=Decimal("0.000000"))
    is_primary_dimension: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    allocation_confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    evidence_level: Mapped[str] = mapped_column(String(60), nullable=False, default="unknown", index=True)
    contribution_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m11_7_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)


class Core3BusinessSalesReconciliationCheck(Base, AuditMixin):
    __tablename__ = "core3_business_sales_reconciliation_check"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "check_type",
            "sku_code",
            "dimension_type",
            "dimension_code",
            "input_fingerprint",
            name="uq_core3_m117_check_key",
        ),
        Index("ix_core3_m117_check_batch", "project_id", "category_code", "batch_id", "status"),
        Index("ix_core3_m117_check_dimension", "project_id", "category_code", "batch_id", "dimension_type", "dimension_code"),
        Index("ix_core3_m117_check_sku", "project_id", "category_code", "batch_id", "sku_code"),
    )

    reconciliation_check_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(120), index=True)
    module_run_id: Mapped[str | None] = mapped_column(String(120), index=True)
    source_m11_6_module_run_id: Mapped[str | None] = mapped_column(String(120), index=True)
    check_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, default="", index=True)
    dimension_type: Mapped[str] = mapped_column(String(60), nullable=False, default="", index=True)
    dimension_code: Mapped[str] = mapped_column(String(160), nullable=False, default="", index=True)
    expected_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0.000000"))
    actual_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0.000000"))
    gap_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0.000000"))
    gap_ratio: Mapped[Decimal] = mapped_column(Numeric(10, 8), nullable=False, default=Decimal("0.00000000"))
    tolerance_value: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False, default=Decimal("0.000000"))
    status: Mapped[str] = mapped_column(String(60), nullable=False, default="passed", index=True)
    failure_reason_code: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    failure_reason_cn: Mapped[str] = mapped_column(Text, nullable=False, default="")
    check_payload_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m11_7_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3BusinessSalesReconciliationIssue(Base, AuditMixin):
    __tablename__ = "core3_business_sales_reconciliation_issue"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "issue_scope",
            "sku_code",
            "dimension_type",
            "dimension_code",
            "issue_code",
            "input_fingerprint",
            name="uq_core3_m117_issue_key",
        ),
        Index("ix_core3_m117_issue_open", "project_id", "category_code", "batch_id", "resolved_status", "severity"),
        Index("ix_core3_m117_issue_dimension", "project_id", "category_code", "batch_id", "dimension_type", "dimension_code"),
        Index("ix_core3_m117_issue_sku", "project_id", "category_code", "batch_id", "sku_code"),
    )

    reconciliation_issue_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    reconciliation_check_id: Mapped[str | None] = mapped_column(ForeignKey("core3_business_sales_reconciliation_check.reconciliation_check_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(120), index=True)
    module_run_id: Mapped[str | None] = mapped_column(String(120), index=True)
    issue_scope: Mapped[str] = mapped_column(String(80), nullable=False, default="global", index=True)
    sku_code: Mapped[str] = mapped_column(String(160), nullable=False, default="", index=True)
    dimension_type: Mapped[str] = mapped_column(String(60), nullable=False, default="", index=True)
    dimension_code: Mapped[str] = mapped_column(String(160), nullable=False, default="", index=True)
    issue_code: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(40), nullable=False, default="warning", index=True)
    issue_message_cn: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_action_cn: Mapped[str] = mapped_column(Text, nullable=False)
    issue_context_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m11_7_v1", index=True)
    resolved_status: Mapped[str] = mapped_column(String(40), nullable=False, default="open", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="warning", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="review_required", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3CandidateRecallRun(Base, AuditMixin):
    __tablename__ = "core3_candidate_recall_run"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "run_key",
            "rule_version",
            name="uq_core3_m12_run_key",
        ),
        CheckConstraint("target_sku_count >= 0", name="ck_m12_run_target_count"),
        CheckConstraint("candidate_pair_count >= 0", name="ck_m12_run_pair_count"),
        CheckConstraint("reason_count >= 0", name="ck_m12_run_reason_count"),
        CheckConstraint("feature_snapshot_count >= 0", name="ck_m12_run_snapshot_count"),
        CheckConstraint("review_issue_count >= 0", name="ck_m12_run_review_count"),
        Index("ix_core3_m12_run_batch", "project_id", "category_code", "batch_id"),
        Index("ix_core3_m12_run_status", "project_id", "category_code", "batch_id", "recall_status"),
        Index("ix_core3_m12_run_summary_gin", "summary_json", postgresql_using="gin"),
    )

    candidate_recall_run_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    run_key: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    target_sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    candidate_pair_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reason_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    feature_snapshot_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_issue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    strong_pair_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    medium_pair_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    weak_pair_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_only_pair_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recall_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    target_scope_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    source_module_versions_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    warning_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    boundary_note_cn: Mapped[str] = mapped_column(Text, nullable=False)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m12_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3CandidatePool(Base, AuditMixin):
    __tablename__ = "core3_candidate_pool"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "target_sku_code",
            "candidate_sku_code",
            "rule_version",
            name="uq_core3_m12_candidate_pair_key",
        ),
        CheckConstraint("recall_priority_score >= 0 and recall_priority_score <= 1", name="ck_m12_pool_priority"),
        CheckConstraint("evidence_quality_score >= 0 and evidence_quality_score <= 1", name="ck_m12_pool_quality"),
        CheckConstraint("source_count >= 0", name="ck_m12_pool_source_count"),
        Index("ix_core3_m12_pool_target", "project_id", "category_code", "batch_id", "target_sku_code", "recall_strength"),
        Index("ix_core3_m12_pool_candidate", "project_id", "category_code", "batch_id", "candidate_sku_code"),
        Index("ix_core3_m12_pool_relation", "project_id", "category_code", "batch_id", "primary_relation_type"),
        Index("ix_core3_m12_pool_sources_gin", "recall_sources_json", postgresql_using="gin"),
        Index("ix_core3_m12_pool_relations_gin", "relation_types_json", postgresql_using="gin"),
        Index("ix_core3_m12_pool_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    candidate_pool_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    candidate_recall_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_candidate_recall_run.candidate_recall_run_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    target_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    target_model_name: Mapped[str | None] = mapped_column(String(240))
    target_brand_name: Mapped[str | None] = mapped_column(String(160))
    candidate_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    candidate_model_name: Mapped[str | None] = mapped_column(String(240))
    candidate_brand_name: Mapped[str | None] = mapped_column(String(160))
    same_brand_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    primary_relation_type: Mapped[str] = mapped_column(String(80), nullable=False, default="scenario_substitute", index=True)
    relation_types_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    recall_sources_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recall_strength: Mapped[str] = mapped_column(String(60), nullable=False, default="weak", index=True)
    recall_priority_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"), index=True)
    evidence_quality_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    price_relation: Mapped[str] = mapped_column(String(60), nullable=False, default="unknown", index=True)
    size_relation: Mapped[str] = mapped_column(String(60), nullable=False, default="unknown", index=True)
    sample_status: Mapped[str] = mapped_column(String(60), nullable=False, default="unknown", index=True)
    role_hints_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    business_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    score_parts_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    missing_signals_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    risk_flags_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    target_profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    candidate_profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    feature_snapshot_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m12_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3CandidateRecallReason(Base, AuditMixin):
    __tablename__ = "core3_candidate_recall_reason"
    __table_args__ = (
        UniqueConstraint(
            "candidate_pool_id",
            "recall_source",
            "relation_type",
            "reason_code",
            "rule_version",
            name="uq_core3_m12_reason_key",
        ),
        CheckConstraint("support_score >= 0 and support_score <= 1", name="ck_m12_reason_support"),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_m12_reason_confidence"),
        Index("ix_core3_m12_reason_pair", "candidate_pool_id", "recall_source"),
        Index("ix_core3_m12_reason_target", "project_id", "category_code", "batch_id", "target_sku_code", "recall_source"),
        Index("ix_core3_m12_reason_candidate", "project_id", "category_code", "batch_id", "candidate_sku_code"),
        Index("ix_core3_m12_reason_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    candidate_recall_reason_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    candidate_pool_id: Mapped[str] = mapped_column(ForeignKey("core3_candidate_pool.candidate_pool_id"), index=True)
    candidate_recall_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_candidate_recall_run.candidate_recall_run_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    target_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    candidate_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    recall_source: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    relation_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    reason_code: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    support_level: Mapped[str] = mapped_column(String(60), nullable=False, default="weak", index=True)
    support_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    reason_summary_cn: Mapped[str] = mapped_column(Text, nullable=False)
    source_payload_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    risk_flags_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m12_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3CandidateFeatureSnapshot(Base, AuditMixin):
    __tablename__ = "core3_candidate_feature_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "candidate_pool_id",
            "rule_version",
            "feature_snapshot_hash",
            name="uq_core3_m12_snapshot_hash",
        ),
        Index("ix_core3_m12_snapshot_pair", "candidate_pool_id"),
        Index("ix_core3_m12_snapshot_target", "project_id", "category_code", "batch_id", "target_sku_code"),
        Index("ix_core3_m12_snapshot_candidate", "project_id", "category_code", "batch_id", "candidate_sku_code"),
        Index("ix_core3_m12_snapshot_m13_gin", "m13_component_input_json", postgresql_using="gin"),
    )

    candidate_feature_snapshot_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    candidate_pool_id: Mapped[str] = mapped_column(ForeignKey("core3_candidate_pool.candidate_pool_id"), index=True)
    candidate_recall_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_candidate_recall_run.candidate_recall_run_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    target_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    candidate_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    size_feature_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    price_feature_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    channel_feature_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    market_feature_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    param_feature_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    battlefield_overlap_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    task_overlap_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    audience_overlap_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    claim_value_overlap_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    quality_feature_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    m13_component_input_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    target_profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    candidate_profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    feature_snapshot_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m12_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3CandidateRecallReviewIssue(Base, AuditMixin):
    __tablename__ = "core3_candidate_recall_review_issue"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "target_sku_code",
            "candidate_sku_code",
            "issue_type",
            "input_fingerprint",
            name="uq_core3_m12_review_issue_key",
        ),
        Index("ix_core3_m12_review_open", "project_id", "category_code", "batch_id", "resolved_status", "issue_level"),
        Index("ix_core3_m12_review_target", "project_id", "category_code", "batch_id", "target_sku_code"),
        Index("ix_core3_m12_review_candidate", "project_id", "category_code", "batch_id", "candidate_sku_code"),
        Index("ix_core3_m12_review_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    candidate_recall_review_issue_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    candidate_pool_id: Mapped[str | None] = mapped_column(ForeignKey("core3_candidate_pool.candidate_pool_id"), index=True)
    candidate_feature_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("core3_candidate_feature_snapshot.candidate_feature_snapshot_id"), index=True)
    candidate_recall_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_candidate_recall_run.candidate_recall_run_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    target_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    candidate_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, default="", index=True)
    issue_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    issue_level: Mapped[str] = mapped_column(String(40), nullable=False, default="warning", index=True)
    issue_message_cn: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_action_cn: Mapped[str] = mapped_column(Text, nullable=False)
    issue_context_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m12_v1", index=True)
    resolved_status: Mapped[str] = mapped_column(String(40), nullable=False, default="open", index=True)
    resolved_by: Mapped[str | None] = mapped_column(String(160))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="warning", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="review_required", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3CandidateComponentScore(Base, AuditMixin):
    __tablename__ = "core3_candidate_component_score"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "target_sku_code",
            "candidate_sku_code",
            "rule_version",
            name="uq_core3_m13_component_pair_key",
        ),
        CheckConstraint("component_total_score >= 0 and component_total_score <= 1", name="ck_m13_component_total"),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_m13_component_confidence"),
        CheckConstraint("evidence_completeness_score >= 0 and evidence_completeness_score <= 1", name="ck_m13_evidence_completeness"),
        Index("ix_core3_m13_component_target", "project_id", "category_code", "batch_id", "target_sku_code", "component_total_score"),
        Index("ix_core3_m13_component_candidate", "project_id", "category_code", "batch_id", "candidate_sku_code"),
        Index("ix_core3_m13_component_roles", "project_id", "category_code", "batch_id", "target_sku_code", "direct_fight_score", "price_volume_pressure_score", "benchmark_potential_score"),
        Index("ix_core3_m13_component_review", "project_id", "category_code", "batch_id", "review_required", "review_reason"),
        Index("ix_core3_m13_component_scores_gin", "component_scores_json", postgresql_using="gin"),
        Index("ix_core3_m13_component_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    candidate_component_score_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    candidate_pool_id: Mapped[str] = mapped_column(ForeignKey("core3_candidate_pool.candidate_pool_id"), index=True)
    feature_snapshot_id: Mapped[str] = mapped_column(ForeignKey("core3_candidate_feature_snapshot.candidate_feature_snapshot_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    target_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    target_model_name: Mapped[str | None] = mapped_column(String(240))
    candidate_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    candidate_model_name: Mapped[str | None] = mapped_column(String(240))
    candidate_brand_name: Mapped[str | None] = mapped_column(String(160))
    same_brand_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    candidate_relation_types_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    candidate_role_hints_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    recall_strength: Mapped[str] = mapped_column(String(60), nullable=False, default="weak", index=True)
    base_comparability_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    battlefield_fit_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    task_overlap_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    audience_overlap_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    price_position_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    price_advantage_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    size_fit_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    channel_overlap_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    param_similarity_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    param_superiority_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    claim_confrontation_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    claim_superiority_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    claim_threshold_sufficiency_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    market_threat_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    sales_amount_strength_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    comment_perception_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    price_trend_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    evidence_completeness_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    component_scores_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    component_total_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"), index=True)
    direct_fight_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"), index=True)
    price_volume_pressure_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"), index=True)
    benchmark_potential_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"), index=True)
    configuration_pressure_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    service_reference_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"), index=True)
    sample_status: Mapped[str] = mapped_column(String(60), nullable=False, default="unknown", index=True)
    main_strengths_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    main_gaps_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    risk_flags_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_reason: Mapped[str | None] = mapped_column(String(160), index=True)
    positive_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    weakening_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    target_profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    candidate_profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    feature_snapshot_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    component_rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m13_component_formula_v1", index=True)
    role_rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m13_role_formula_v1", index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m13_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3CandidateRoleScore(Base, AuditMixin):
    __tablename__ = "core3_candidate_role_score"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "target_sku_code",
            "candidate_sku_code",
            "role_code",
            "rule_version",
            name="uq_core3_m13_role_key",
        ),
        CheckConstraint("role_score >= 0 and role_score <= 1", name="ck_m13_role_score"),
        CheckConstraint("role_confidence >= 0 and role_confidence <= 1", name="ck_m13_role_confidence"),
        Index("ix_core3_m13_role_target", "project_id", "category_code", "batch_id", "target_sku_code", "role_code", "role_score"),
        Index("ix_core3_m13_role_auto", "project_id", "category_code", "batch_id", "role_code", "auto_select_eligible", "role_confidence"),
        Index("ix_core3_m13_role_evidence_gin", "positive_evidence_ids", postgresql_using="gin"),
    )

    candidate_role_score_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    candidate_component_score_id: Mapped[str] = mapped_column(ForeignKey("core3_candidate_component_score.candidate_component_score_id"), index=True)
    candidate_pool_id: Mapped[str] = mapped_column(ForeignKey("core3_candidate_pool.candidate_pool_id"), index=True)
    feature_snapshot_id: Mapped[str] = mapped_column(ForeignKey("core3_candidate_feature_snapshot.candidate_feature_snapshot_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    target_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    candidate_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    role_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    role_name_cn: Mapped[str] = mapped_column(String(120), nullable=False)
    role_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"), index=True)
    role_confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    role_rank_hint: Mapped[int | None] = mapped_column(Integer)
    auto_select_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    auto_select_block_reason: Mapped[str | None] = mapped_column(String(160))
    role_business_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    role_business_reason_short_cn: Mapped[str] = mapped_column(String(255), nullable=False)
    formula_version: Mapped[str] = mapped_column(String(120), nullable=False, default="m13_role_formula_v1", index=True)
    component_contribution_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    positive_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    weakening_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    risk_flags_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_reason: Mapped[str | None] = mapped_column(String(160), index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m13_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3CandidateComponentExplanation(Base, AuditMixin):
    __tablename__ = "core3_candidate_component_explanation"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "target_sku_code",
            "candidate_sku_code",
            "component_code",
            "rule_version",
            name="uq_core3_m13_explanation_key",
        ),
        CheckConstraint("score >= 0 and score <= 1", name="ck_m13_explanation_score"),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_m13_explanation_confidence"),
        Index("ix_core3_m13_explanation_pair", "project_id", "category_code", "batch_id", "target_sku_code", "candidate_sku_code"),
        Index("ix_core3_m13_explanation_component", "project_id", "category_code", "batch_id", "component_code", "support_level"),
        Index("ix_core3_m13_explanation_evidence_gin", "supporting_evidence_ids", postgresql_using="gin"),
    )

    candidate_component_explanation_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    candidate_component_score_id: Mapped[str] = mapped_column(ForeignKey("core3_candidate_component_score.candidate_component_score_id"), index=True)
    candidate_pool_id: Mapped[str] = mapped_column(ForeignKey("core3_candidate_pool.candidate_pool_id"), index=True)
    feature_snapshot_id: Mapped[str] = mapped_column(ForeignKey("core3_candidate_feature_snapshot.candidate_feature_snapshot_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    target_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    candidate_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    component_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    component_name_cn: Mapped[str] = mapped_column(String(160), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    support_level: Mapped[str] = mapped_column(String(60), nullable=False, default="weak", index=True)
    business_explanation_cn: Mapped[str] = mapped_column(Text, nullable=False)
    positive_summary_cn: Mapped[str | None] = mapped_column(Text)
    gap_summary_cn: Mapped[str | None] = mapped_column(Text)
    supporting_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    weakening_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    missing_evidence_reasons_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    source_payload_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    risk_flags_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m13_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)


class Core3CandidateScoreReviewIssue(Base, AuditMixin):
    __tablename__ = "core3_candidate_score_review_issue"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "target_sku_code",
            "candidate_sku_code",
            "issue_scope",
            "component_code",
            "role_code",
            "issue_type",
            "input_fingerprint",
            name="uq_core3_m13_review_issue_key",
        ),
        Index("ix_core3_m13_review_open", "project_id", "category_code", "batch_id", "resolved_status", "issue_level"),
        Index("ix_core3_m13_review_pair", "project_id", "category_code", "batch_id", "target_sku_code", "candidate_sku_code"),
        Index("ix_core3_m13_review_component", "project_id", "category_code", "batch_id", "component_code"),
        Index("ix_core3_m13_review_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    candidate_score_review_issue_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    candidate_component_score_id: Mapped[str | None] = mapped_column(ForeignKey("core3_candidate_component_score.candidate_component_score_id"), index=True)
    candidate_role_score_id: Mapped[str | None] = mapped_column(ForeignKey("core3_candidate_role_score.candidate_role_score_id"), index=True)
    candidate_pool_id: Mapped[str | None] = mapped_column(ForeignKey("core3_candidate_pool.candidate_pool_id"), index=True)
    feature_snapshot_id: Mapped[str | None] = mapped_column(ForeignKey("core3_candidate_feature_snapshot.candidate_feature_snapshot_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    target_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    candidate_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, default="", index=True)
    issue_scope: Mapped[str] = mapped_column(String(60), nullable=False, default="pair", index=True)
    component_code: Mapped[str] = mapped_column(String(80), nullable=False, default="", index=True)
    role_code: Mapped[str] = mapped_column(String(80), nullable=False, default="", index=True)
    issue_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    issue_level: Mapped[str] = mapped_column(String(40), nullable=False, default="warning", index=True)
    issue_message_cn: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_action_cn: Mapped[str | None] = mapped_column(Text)
    source_payload_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    resolved_status: Mapped[str] = mapped_column(String(40), nullable=False, default="open", index=True)
    resolved_by: Mapped[str | None] = mapped_column(String(160))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m13_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="warning", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="review_required", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3CompetitorSelectionRun(Base, AuditMixin):
    __tablename__ = "core3_competitor_selection_run"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "target_sku_code",
            "rule_version",
            name="uq_core3_m14_selection_run_key",
        ),
        CheckConstraint("candidate_count >= 0", name="ck_m14_run_candidate_count"),
        CheckConstraint("scored_candidate_count >= 0", name="ck_m14_run_scored_count"),
        CheckConstraint("selected_count >= 0 and selected_count <= 3", name="ck_m14_run_selected_count"),
        CheckConstraint("empty_slot_count >= 0 and empty_slot_count <= 3", name="ck_m14_run_empty_slot_count"),
        CheckConstraint("review_candidate_count >= 0", name="ck_m14_run_review_count"),
        CheckConstraint("blocked_candidate_count >= 0", name="ck_m14_run_blocked_count"),
        Index("ix_core3_m14_run_target", "project_id", "category_code", "batch_id", "target_sku_code"),
        Index("ix_core3_m14_run_status", "project_id", "category_code", "batch_id", "selection_status", "review_required"),
        Index("ix_core3_m14_run_empty_gin", "empty_slots_json", postgresql_using="gin"),
        Index("ix_core3_m14_run_policy_gin", "selection_policy_json", postgresql_using="gin"),
    )

    selection_run_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    target_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    target_model_name: Mapped[str | None] = mapped_column(String(240))
    target_brand_name: Mapped[str | None] = mapped_column(String(160))
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scored_candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    selected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    empty_slot_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    review_candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocked_candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    selection_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    selection_summary_cn: Mapped[str] = mapped_column(Text, nullable=False)
    empty_slots_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    selection_policy_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    target_profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    m12_recall_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    m13_score_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    evidence_revision: Mapped[str] = mapped_column(String(120), nullable=False, default="m14_evidence_revision_v1", index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m14_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3CompetitorSelection(Base, AuditMixin):
    __tablename__ = "core3_competitor_selection"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "target_sku_code",
            "slot_code",
            "rule_version",
            name="uq_core3_m14_selection_slot_key",
        ),
        CheckConstraint("selection_rank >= 1 and selection_rank <= 3", name="ck_m14_selection_rank"),
        CheckConstraint("slot_selection_score >= 0 and slot_selection_score <= 1", name="ck_m14_selection_slot_score"),
        CheckConstraint("role_score >= 0 and role_score <= 1", name="ck_m14_selection_role_score"),
        CheckConstraint("component_total_score >= 0 and component_total_score <= 1", name="ck_m14_selection_component_total"),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_m14_selection_confidence"),
        CheckConstraint("evidence_completeness_score >= 0 and evidence_completeness_score <= 1", name="ck_m14_selection_evidence"),
        Index("ix_core3_m14_selection_target", "project_id", "category_code", "batch_id", "target_sku_code", "selection_rank"),
        Index("ix_core3_m14_selection_slot", "project_id", "category_code", "batch_id", "slot_code", "slot_selection_score"),
        Index("ix_core3_m14_selection_candidate", "project_id", "category_code", "batch_id", "candidate_sku_code"),
        Index("ix_core3_m14_selection_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    competitor_selection_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    selection_run_id: Mapped[str] = mapped_column(ForeignKey("core3_competitor_selection_run.selection_run_id"), index=True)
    candidate_pool_id: Mapped[str] = mapped_column(ForeignKey("core3_candidate_pool.candidate_pool_id"), index=True)
    candidate_component_score_id: Mapped[str] = mapped_column(ForeignKey("core3_candidate_component_score.candidate_component_score_id"), index=True)
    candidate_role_score_id: Mapped[str | None] = mapped_column(ForeignKey("core3_candidate_role_score.candidate_role_score_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    target_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    target_model_name: Mapped[str | None] = mapped_column(String(240))
    target_brand_name: Mapped[str | None] = mapped_column(String(160))
    candidate_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    candidate_model_name: Mapped[str | None] = mapped_column(String(240))
    candidate_brand_name: Mapped[str | None] = mapped_column(String(160))
    same_brand_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    slot_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    slot_name_cn: Mapped[str] = mapped_column(String(160), nullable=False)
    selection_rank: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True)
    primary_battlefield_code: Mapped[str | None] = mapped_column(String(160), index=True)
    primary_battlefield_name: Mapped[str | None] = mapped_column(String(200))
    slot_selection_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"), index=True)
    role_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    component_total_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    evidence_completeness_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    pressure_level: Mapped[str] = mapped_column(String(60), nullable=False, default="medium", index=True)
    selection_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    selection_reason_short_cn: Mapped[str] = mapped_column(String(255), nullable=False)
    business_conclusion_cn: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_hint_cn: Mapped[str | None] = mapped_column(Text)
    risk_summary_cn: Mapped[str | None] = mapped_column(Text)
    component_scores_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    role_scores_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    selection_evidence_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    selected_by_rules_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_reason: Mapped[str | None] = mapped_column(String(160), index=True)
    positive_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    weakening_evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    target_profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    candidate_profile_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    m13_score_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m14_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3CompetitorSlotDecision(Base, AuditMixin):
    __tablename__ = "core3_competitor_slot_decision"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "target_sku_code",
            "slot_code",
            "rule_version",
            name="uq_core3_m14_slot_decision_key",
        ),
        CheckConstraint("slot_candidate_count >= 0", name="ck_m14_slot_candidate_count"),
        CheckConstraint("selected_candidate_count >= 0 and selected_candidate_count <= 1", name="ck_m14_slot_selected_count"),
        CheckConstraint("top_candidate_score >= 0 and top_candidate_score <= 1", name="ck_m14_slot_top_score"),
        CheckConstraint("decision_confidence >= 0 and decision_confidence <= 1", name="ck_m14_slot_confidence"),
        Index("ix_core3_m14_slot_target", "project_id", "category_code", "batch_id", "target_sku_code", "slot_code"),
        Index("ix_core3_m14_slot_status", "project_id", "category_code", "batch_id", "decision_status", "empty_reason_code"),
        Index("ix_core3_m14_slot_payload_gin", "decision_payload_json", postgresql_using="gin"),
    )

    slot_decision_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    selection_run_id: Mapped[str] = mapped_column(ForeignKey("core3_competitor_selection_run.selection_run_id"), index=True)
    selected_competitor_selection_id: Mapped[str | None] = mapped_column(ForeignKey("core3_competitor_selection.competitor_selection_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    target_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    target_model_name: Mapped[str | None] = mapped_column(String(240))
    candidate_sku_code: Mapped[str | None] = mapped_column(String(160), index=True)
    candidate_model_name: Mapped[str | None] = mapped_column(String(240))
    slot_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    slot_name_cn: Mapped[str] = mapped_column(String(160), nullable=False)
    decision_status: Mapped[str] = mapped_column(String(60), nullable=False, default="empty", index=True)
    selected_candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    slot_candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    empty_reason_code: Mapped[str | None] = mapped_column(String(100), index=True)
    empty_reason_cn: Mapped[str | None] = mapped_column(Text)
    review_reason: Mapped[str | None] = mapped_column(String(160), index=True)
    top_candidate_sku_code: Mapped[str | None] = mapped_column(String(160), index=True)
    top_candidate_model_name: Mapped[str | None] = mapped_column(String(240))
    top_candidate_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    decision_confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    decision_summary_cn: Mapped[str] = mapped_column(Text, nullable=False)
    decision_payload_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m14_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3CompetitorSelectionAudit(Base, AuditMixin):
    __tablename__ = "core3_competitor_selection_audit"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "target_sku_code",
            "candidate_sku_code",
            "rule_version",
            name="uq_core3_m14_audit_pair_key",
        ),
        CheckConstraint("candidate_total_score >= 0 and candidate_total_score <= 1", name="ck_m14_audit_total_score"),
        CheckConstraint("best_role_score >= 0 and best_role_score <= 1", name="ck_m14_audit_role_score"),
        CheckConstraint("evidence_completeness_score >= 0 and evidence_completeness_score <= 1", name="ck_m14_audit_evidence"),
        CheckConstraint("confidence >= 0 and confidence <= 1", name="ck_m14_audit_confidence"),
        CheckConstraint("business_distinctiveness_score >= 0 and business_distinctiveness_score <= 1", name="ck_m14_audit_distinctiveness"),
        CheckConstraint("strategic_value_score >= 0 and strategic_value_score <= 1", name="ck_m14_audit_strategy"),
        Index("ix_core3_m14_audit_target", "project_id", "category_code", "batch_id", "target_sku_code", "audit_decision"),
        Index("ix_core3_m14_audit_candidate", "project_id", "category_code", "batch_id", "candidate_sku_code"),
        Index("ix_core3_m14_audit_slot_gin", "slot_scores_json", postgresql_using="gin"),
        Index("ix_core3_m14_audit_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    selection_audit_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    selection_run_id: Mapped[str] = mapped_column(ForeignKey("core3_competitor_selection_run.selection_run_id"), index=True)
    candidate_pool_id: Mapped[str] = mapped_column(ForeignKey("core3_candidate_pool.candidate_pool_id"), index=True)
    candidate_component_score_id: Mapped[str] = mapped_column(ForeignKey("core3_candidate_component_score.candidate_component_score_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    target_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    target_model_name: Mapped[str | None] = mapped_column(String(240))
    candidate_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    candidate_model_name: Mapped[str | None] = mapped_column(String(240))
    candidate_brand_name: Mapped[str | None] = mapped_column(String(160))
    evaluated_slot_codes_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    audit_decision: Mapped[str] = mapped_column(String(60), nullable=False, default="rejected", index=True)
    selected_slot_code: Mapped[str | None] = mapped_column(String(80), index=True)
    best_slot_code: Mapped[str | None] = mapped_column(String(80), index=True)
    decision_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    failed_conditions_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    slot_scores_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    candidate_total_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    best_role_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    evidence_completeness_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    risk_flags_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    duplicate_with_candidate_sku_code: Mapped[str | None] = mapped_column(String(160), index=True)
    business_distinctiveness_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.8000"))
    strategic_value_score: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m14_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3CompetitorSelectionReviewIssue(Base, AuditMixin):
    __tablename__ = "core3_competitor_selection_review_issue"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "target_sku_code",
            "candidate_sku_code",
            "slot_code",
            "issue_scope",
            "issue_type",
            "input_fingerprint",
            name="uq_core3_m14_review_issue_key",
        ),
        Index("ix_core3_m14_review_open", "project_id", "category_code", "batch_id", "resolved_status", "issue_level"),
        Index("ix_core3_m14_review_target", "project_id", "category_code", "batch_id", "target_sku_code"),
        Index("ix_core3_m14_review_slot", "project_id", "category_code", "batch_id", "slot_code", "issue_type"),
        Index("ix_core3_m14_review_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    selection_review_issue_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    selection_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_competitor_selection_run.selection_run_id"), index=True)
    competitor_selection_id: Mapped[str | None] = mapped_column(ForeignKey("core3_competitor_selection.competitor_selection_id"), index=True)
    slot_decision_id: Mapped[str | None] = mapped_column(ForeignKey("core3_competitor_slot_decision.slot_decision_id"), index=True)
    selection_audit_id: Mapped[str | None] = mapped_column(ForeignKey("core3_competitor_selection_audit.selection_audit_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    target_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    slot_code: Mapped[str] = mapped_column(String(80), nullable=False, default="", index=True)
    candidate_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, default="", index=True)
    issue_scope: Mapped[str] = mapped_column(String(60), nullable=False, default="candidate", index=True)
    issue_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    issue_level: Mapped[str] = mapped_column(String(40), nullable=False, default="warning", index=True)
    issue_message_cn: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_action_cn: Mapped[str | None] = mapped_column(Text)
    source_payload_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    resolved_status: Mapped[str] = mapped_column(String(40), nullable=False, default="open", index=True)
    resolved_by: Mapped[str | None] = mapped_column(String(160))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m14_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="warning", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="review_required", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3ReportEvidenceCard(Base, AuditMixin):
    __tablename__ = "core3_report_evidence_card"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "target_sku_code",
            "competitor_sku_code",
            "slot_code",
            "rule_version",
            name="uq_core3_m15_report_evidence_card_key",
        ),
        Index("ix_core3_m15_card_target", "project_id", "category_code", "batch_id", "target_sku_code", "slot_code"),
        Index("ix_core3_m15_card_selection", "selection_run_id", "selection_id"),
        Index("ix_core3_m15_card_readiness", "project_id", "category_code", "batch_id", "readiness_level"),
        Index("ix_core3_m15_card_short_refs_gin", "short_evidence_refs_json", postgresql_using="gin"),
        Index("ix_core3_m15_card_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    evidence_card_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    card_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    selection_run_id: Mapped[str] = mapped_column(ForeignKey("core3_competitor_selection_run.selection_run_id"), index=True)
    selection_id: Mapped[str] = mapped_column(ForeignKey("core3_competitor_selection.competitor_selection_id"), index=True)
    component_score_id: Mapped[str | None] = mapped_column(ForeignKey("core3_candidate_component_score.candidate_component_score_id"), index=True)
    candidate_pool_id: Mapped[str | None] = mapped_column(ForeignKey("core3_candidate_pool.candidate_pool_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    target_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    target_model_name: Mapped[str | None] = mapped_column(String(240))
    target_display_name_cn: Mapped[str] = mapped_column(String(255), nullable=False)
    competitor_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    competitor_model_name: Mapped[str | None] = mapped_column(String(240))
    competitor_brand_name: Mapped[str | None] = mapped_column(String(160))
    competitor_display_name_cn: Mapped[str] = mapped_column(String(255), nullable=False)
    slot_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    slot_name_cn: Mapped[str] = mapped_column(String(160), nullable=False)
    primary_battlefield_code: Mapped[str | None] = mapped_column(String(160), index=True)
    primary_battlefield_name_cn: Mapped[str] = mapped_column(String(200), nullable=False)
    pressure_level_cn: Mapped[str] = mapped_column(String(80), nullable=False)
    readiness_level: Mapped[str] = mapped_column(String(40), nullable=False, default="ready", index=True)
    confidence_label_cn: Mapped[str] = mapped_column(String(40), nullable=False, default="中")
    headline_cn: Mapped[str] = mapped_column(String(255), nullable=False)
    summary_cn: Mapped[str] = mapped_column(Text, nullable=False)
    one_sentence_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    price_evidence_cn: Mapped[str | None] = mapped_column(Text)
    channel_evidence_cn: Mapped[str | None] = mapped_column(Text)
    param_evidence_cn: Mapped[str | None] = mapped_column(Text)
    claim_value_evidence_cn: Mapped[str | None] = mapped_column(Text)
    task_audience_evidence_cn: Mapped[str | None] = mapped_column(Text)
    market_evidence_cn: Mapped[str | None] = mapped_column(Text)
    comment_evidence_cn: Mapped[str | None] = mapped_column(Text)
    evidence_matrix_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    key_difference_cn: Mapped[str] = mapped_column(Text, nullable=False)
    target_advantage_cn: Mapped[str] = mapped_column(Text, nullable=False)
    competitor_advantage_cn: Mapped[str] = mapped_column(Text, nullable=False)
    strategy_implication_cn: Mapped[str] = mapped_column(Text, nullable=False)
    risk_note_cn: Mapped[str | None] = mapped_column(Text)
    short_evidence_refs_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    display_payload_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    export_payload_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    selection_result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m15_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3TargetReportPayload(Base, AuditMixin):
    __tablename__ = "core3_target_report_payload"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "target_sku_code",
            "selection_run_id",
            "rule_version",
            name="uq_core3_m15_target_report_key",
        ),
        CheckConstraint("selected_count >= 0 and selected_count <= 3", name="ck_m15_report_selected_count"),
        CheckConstraint("empty_slot_count >= 0 and empty_slot_count <= 3", name="ck_m15_report_empty_slot_count"),
        Index("ix_core3_m15_report_target", "project_id", "category_code", "batch_id", "target_sku_code", "readiness_level"),
        Index("ix_core3_m15_report_selection", "project_id", "category_code", "batch_id", "selection_run_id"),
        Index("ix_core3_m15_report_competitors_gin", "core_competitors_json", postgresql_using="gin"),
        Index("ix_core3_m15_report_sop_gin", "sop_trace_json", postgresql_using="gin"),
    )

    target_report_payload_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    target_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    target_display_name_cn: Mapped[str] = mapped_column(String(255), nullable=False)
    report_title_cn: Mapped[str] = mapped_column(String(255), nullable=False)
    executive_conclusion_cn: Mapped[str] = mapped_column(Text, nullable=False)
    readiness_level: Mapped[str] = mapped_column(String(40), nullable=False, default="review_required", index=True)
    confidence_label_cn: Mapped[str] = mapped_column(String(40), nullable=False, default="中")
    data_scope_note_cn: Mapped[str] = mapped_column(Text, nullable=False)
    target_profile_summary_cn: Mapped[str] = mapped_column(Text, nullable=False)
    selection_run_id: Mapped[str] = mapped_column(ForeignKey("core3_competitor_selection_run.selection_run_id"), index=True)
    selected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    empty_slot_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    battlefield_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    task_group_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    target_signal_cards_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    core_competitors_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    empty_slots_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    why_competitor_logic_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_matrix_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    key_difference_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    strategy_hint_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    sop_trace_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    candidate_pool_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    review_questions_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    data_quality_note_cn: Mapped[str] = mapped_column(Text, nullable=False)
    short_evidence_map_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    export_payload_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    ui_guardrail_result_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    m14_selection_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    evidence_revision: Mapped[str | None] = mapped_column(String(160), index=True)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m15_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3ReportSection(Base, AuditMixin):
    __tablename__ = "core3_report_section"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "target_sku_code",
            "selection_run_id",
            "section_code",
            "rule_version",
            name="uq_core3_m15_report_section_key",
        ),
        Index("ix_core3_m15_section_order", "project_id", "category_code", "batch_id", "target_sku_code", "section_order"),
        Index("ix_core3_m15_section_display", "project_id", "category_code", "batch_id", "display_status", "readiness_level"),
        Index("ix_core3_m15_section_payload_gin", "section_payload_json", postgresql_using="gin"),
        Index("ix_core3_m15_section_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    report_section_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    target_report_payload_id: Mapped[str | None] = mapped_column(ForeignKey("core3_target_report_payload.target_report_payload_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    target_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    selection_run_id: Mapped[str] = mapped_column(ForeignKey("core3_competitor_selection_run.selection_run_id"), index=True)
    section_code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    section_title_cn: Mapped[str] = mapped_column(String(160), nullable=False)
    section_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    section_payload_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    display_status: Mapped[str] = mapped_column(String(40), nullable=False, default="visible", index=True)
    readiness_level: Mapped[str] = mapped_column(String(40), nullable=False, default="ready", index=True)
    contains_internal_field_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    contains_uuid_flag: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    short_evidence_refs_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m15_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3ReportExport(Base, AuditMixin):
    __tablename__ = "core3_report_export"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "target_sku_code",
            "selection_run_id",
            "export_type",
            "rule_version",
            name="uq_core3_m15_report_export_key",
        ),
        Index("ix_core3_m15_export_target", "project_id", "category_code", "batch_id", "target_sku_code", "export_type", "export_status"),
        Index("ix_core3_m15_export_readiness", "project_id", "category_code", "batch_id", "readiness_level"),
    )

    report_export_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    target_report_payload_id: Mapped[str | None] = mapped_column(ForeignKey("core3_target_report_payload.target_report_payload_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    target_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    selection_run_id: Mapped[str] = mapped_column(ForeignKey("core3_competitor_selection_run.selection_run_id"), index=True)
    export_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    export_title_cn: Mapped[str] = mapped_column(String(255), nullable=False)
    export_payload: Mapped[str] = mapped_column(Text, nullable=False)
    export_payload_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    data_scope_note_cn: Mapped[str] = mapped_column(Text, nullable=False)
    readiness_level: Mapped[str] = mapped_column(String(40), nullable=False, default="ready", index=True)
    checksum: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    page_payload_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    export_status: Mapped[str] = mapped_column(String(40), nullable=False, default="ready", index=True)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m15_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="success", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="auto_pass", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3ReportReviewIssue(Base, AuditMixin):
    __tablename__ = "core3_report_review_issue"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "category_code",
            "batch_id",
            "target_sku_code",
            "selection_run_id",
            "issue_scope",
            "section_code",
            "issue_type",
            "input_fingerprint",
            name="uq_core3_m15_report_review_issue_key",
        ),
        Index("ix_core3_m15_review_open", "project_id", "category_code", "batch_id", "resolved_status", "issue_level"),
        Index("ix_core3_m15_review_target", "project_id", "category_code", "batch_id", "target_sku_code", "issue_type"),
        Index("ix_core3_m15_review_evidence_gin", "evidence_ids", postgresql_using="gin"),
    )

    report_review_issue_id: Mapped[str] = mapped_column(String(120), primary_key=True, default=new_id)
    target_report_payload_id: Mapped[str | None] = mapped_column(ForeignKey("core3_target_report_payload.target_report_payload_id"), index=True)
    evidence_card_id: Mapped[str | None] = mapped_column(ForeignKey("core3_report_evidence_card.evidence_card_id"), index=True)
    report_section_id: Mapped[str | None] = mapped_column(ForeignKey("core3_report_section.report_section_id"), index=True)
    report_export_id: Mapped[str | None] = mapped_column(ForeignKey("core3_report_export.report_export_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str] = mapped_column(ForeignKey("core3_source_batch.batch_id"), index=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    target_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    selection_run_id: Mapped[str] = mapped_column(ForeignKey("core3_competitor_selection_run.selection_run_id"), index=True)
    issue_scope: Mapped[str] = mapped_column(String(60), nullable=False, default="report", index=True)
    section_code: Mapped[str] = mapped_column(String(80), nullable=False, default="", index=True)
    issue_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    issue_level: Mapped[str] = mapped_column(String(40), nullable=False, default="warning", index=True)
    issue_message_cn: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_action_cn: Mapped[str | None] = mapped_column(Text)
    source_payload_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    resolved_status: Mapped[str] = mapped_column(String(40), nullable=False, default="open", index=True)
    resolved_by: Mapped[str | None] = mapped_column(String(160))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    rule_version: Mapped[str] = mapped_column(String(120), nullable=False, default="core3_mvp_real_data_v2_m15_v1", index=True)
    input_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    result_hash: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    processing_status: Mapped[str] = mapped_column(String(60), nullable=False, default="warning", index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    review_status: Mapped[str] = mapped_column(String(60), nullable=False, default="review_required", index=True)
    review_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3V2RecomputePlan(Base, AuditMixin):
    __tablename__ = "core3_v2_recompute_plan"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "module_code",
            "target_type",
            "target_id",
            name="uq_core3_v2_recompute_plan_item",
        ),
        Index("ix_core3_v2_recompute_plan_module", "run_id", "module_code", "planned_action", "priority"),
        Index("ix_core3_v2_recompute_plan_domain", "project_id", "category_code", "batch_id", "change_domain"),
    )

    plan_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str | None] = mapped_column(String(120), index=True)
    module_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    start_from_module: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    change_domain: Mapped[str] = mapped_column(String(60), nullable=False, default="report", index=True)
    change_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    upstream_dependency_hash: Mapped[str | None] = mapped_column(String(180), index=True)
    previous_output_hash: Mapped[str | None] = mapped_column(String(180), index=True)
    planned_action: Mapped[str] = mapped_column(String(40), nullable=False, default="reuse", index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100, index=True)
    related_targets_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    plan_reason_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3V2ReviewQueue(Base, AuditMixin):
    __tablename__ = "core3_v2_review_queue"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "module_code",
            "target_type",
            "target_id",
            "issue_type",
            "object_id",
            name="uq_core3_v2_review_queue_issue",
        ),
        Index("ix_core3_v2_review_queue_pending", "project_id", "category_code", "review_status", "severity"),
        Index("ix_core3_v2_review_queue_target", "project_id", "category_code", "batch_id", "target_sku_code"),
        Index("ix_core3_v2_review_queue_blocking", "run_id", "is_blocking_release", "severity"),
    )

    review_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    source_module_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_module_run.module_run_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str | None] = mapped_column(String(120), index=True)
    module_code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    target_sku_code: Mapped[str | None] = mapped_column(String(160), index=True)
    candidate_sku_code: Mapped[str | None] = mapped_column(String(160), index=True)
    object_type: Mapped[str] = mapped_column(String(80), nullable=False, default="run", index=True)
    object_id: Mapped[str] = mapped_column(String(180), nullable=False, default="", index=True)
    issue_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(40), nullable=False, default="medium", index=True)
    issue_title_cn: Mapped[str] = mapped_column(String(256), nullable=False)
    issue_detail_cn: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    risk_flags_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    suggested_action_cn: Mapped[str] = mapped_column(Text, nullable=False)
    review_status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending", index=True)
    reviewer: Mapped[str | None] = mapped_column(String(160))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    resolution_note_cn: Mapped[str | None] = mapped_column(Text)
    is_blocking_release: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    source_issue_table: Mapped[str | None] = mapped_column(String(128))
    source_issue_id: Mapped[str | None] = mapped_column(String(180), index=True)


class Core3V2ReviewDecision(Base, AuditMixin):
    __tablename__ = "core3_v2_review_decision"
    __table_args__ = (
        Index("ix_core3_v2_review_decision_review", "review_id", "decided_at"),
        Index("ix_core3_v2_review_decision_recompute", "run_id", "need_recompute", "recompute_mode"),
    )

    decision_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    review_id: Mapped[str] = mapped_column(ForeignKey("core3_v2_review_queue.review_id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    decision_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    decision_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    impact_scope_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    need_recompute: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    recompute_mode: Mapped[str | None] = mapped_column(String(80), index=True)
    created_followup_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    decided_by: Mapped[str] = mapped_column(String(160), nullable=False, default="system")
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, nullable=False)


class Core3V2AcceptanceReport(Base, AuditMixin):
    __tablename__ = "core3_v2_acceptance_report"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_core3_v2_acceptance_report_run"),
        Index("ix_core3_v2_acceptance_report_status", "project_id", "category_code", "acceptance_status", "created_at"),
    )

    acceptance_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    data_batch_id: Mapped[str | None] = mapped_column(String(120), index=True)
    processed_sku_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processed_target_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    report_ready_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    high_confidence_report_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    medium_confidence_report_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    limited_report_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocked_report_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_competitor_count: Mapped[Decimal] = mapped_column(Numeric(6, 3), nullable=False, default=Decimal("0.000"))
    direct_slot_fill_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    pressure_slot_fill_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    benchmark_slot_fill_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    evidence_coverage_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False, default=Decimal("0.0000"))
    review_pending_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocker_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    acceptance_status: Mapped[str] = mapped_column(String(60), nullable=False, default="passed_with_warning", index=True)
    acceptance_summary_cn: Mapped[str] = mapped_column(Text, nullable=False)
    data_scope_note_cn: Mapped[str] = mapped_column(Text, nullable=False)
    module_status_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    report_status_summary_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    quality_gate_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    acceptance_detail_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class Core3V2ReleaseGate(Base, AuditMixin):
    __tablename__ = "core3_v2_release_gate"
    __table_args__ = (
        UniqueConstraint("run_id", "target_sku_code", name="uq_core3_v2_release_gate_target"),
        Index("ix_core3_v2_release_gate_status", "project_id", "category_code", "gate_status", "updated_at"),
        Index("ix_core3_v2_release_gate_target", "project_id", "category_code", "batch_id", "target_sku_code"),
    )

    release_gate_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("core3_v2_pipeline_run.run_id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    batch_id: Mapped[str | None] = mapped_column(String(120), index=True)
    target_sku_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    report_payload_id: Mapped[str | None] = mapped_column(ForeignKey("core3_target_report_payload.target_report_payload_id"), index=True)
    selection_run_id: Mapped[str | None] = mapped_column(ForeignKey("core3_competitor_selection_run.selection_run_id"), index=True)
    gate_status: Mapped[str] = mapped_column(String(60), nullable=False, default="not_ready", index=True)
    gate_reason_cn: Mapped[str] = mapped_column(Text, nullable=False)
    required_review_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    warning_review_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    data_scope_note_cn: Mapped[str] = mapped_column(Text, nullable=False)
    display_badges_json: Mapped[list] = mapped_column(JSONBCompat, default=list)
    gate_check_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    released_by: Mapped[str | None] = mapped_column(String(160))
    released_at: Mapped[datetime | None] = mapped_column(DateTime)


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
    component_scores: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    evidence_card: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    rule_version: Mapped[str] = mapped_column(String(40), nullable=False, default="1.0.0")
    asset_version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")
    review_status: Mapped[str] = mapped_column(String(40), nullable=False, default="auto_pass")
    insufficient_reasons: Mapped[list] = mapped_column(JSONBCompat, default=list)
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
    raw_payload: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    asset_version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")


class EvaluationRun(Base, AuditMixin):
    __tablename__ = "evaluation_run"

    evaluation_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="completed")
    gold_label_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metrics: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    report: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    rule_versions: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    asset_version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")


class CalibrationRun(Base, AuditMixin):
    __tablename__ = "calibration_run"

    calibration_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft_candidate")
    target_metric: Mapped[str] = mapped_column(String(80), nullable=False, default="macro_f1")
    before_metrics: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    after_metrics: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    candidate_rule_patch: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    rule_versions: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
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
    checkpoint_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    result_ref: Mapped[dict | None] = mapped_column(JSONBCompat)
    diagnostics_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
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
    diagnostics_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


class AssetVersion(Base, AuditMixin):
    __tablename__ = "asset_version"

    asset_version_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    asset_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    version: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    lifecycle_status: Mapped[str] = mapped_column(String(40), nullable=False, default="draft", index=True)
    content_hash: Mapped[str] = mapped_column(String(120), nullable=False)
    manifest_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
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
    diff_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)


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
    metadata_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now_utc, nullable=False)


class RuntimeExport(Base, AuditMixin):
    __tablename__ = "runtime_export"

    export_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    asset_version_id: Mapped[str] = mapped_column(ForeignKey("asset_version.asset_version_id"), index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="completed")
    manifest_json: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
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
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
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
    evidence_ids: Mapped[list] = mapped_column(JSONBCompat, default=list)
    candidate_payload: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    priority: Mapped[str] = mapped_column(String(40), nullable=False, default="medium")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    reviewer: Mapped[str | None] = mapped_column(String(120))
    decision_payload: Mapped[dict | None] = mapped_column(JSONBCompat)


class AssetPackage(Base, AuditMixin):
    __tablename__ = "asset_package"

    package_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="exported")
    file_list: Mapped[list] = mapped_column(JSONBCompat, default=list)
    package_path: Mapped[str] = mapped_column(Text, nullable=False)
    package_metadata: Mapped[dict] = mapped_column(JSONBCompat, default=dict)
