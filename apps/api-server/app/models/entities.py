from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
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
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)


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
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")


class SkuClaimResult(Base, AuditMixin):
    __tablename__ = "sku_claim_result"

    result_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("category_project.project_id"), index=True)
    category_code: Mapped[str] = mapped_column(String(40), nullable=False, default="TV")
    sku_code: Mapped[str] = mapped_column(String(120), index=True)
    claim_code: Mapped[str] = mapped_column(String(140), index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.8)
    activation_source: Mapped[str] = mapped_column(String(80), nullable=False, default="rule")
    evidence_ids: Mapped[list] = mapped_column(JSON, default=list)
    extracted_values: Mapped[dict] = mapped_column(JSON, default=dict)
    review_status: Mapped[str] = mapped_column(String(40), nullable=False, default="pending")
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="candidate")
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
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="candidate")
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
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="candidate")
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
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="candidate")
    version: Mapped[str] = mapped_column(String(40), nullable=False, default="0.1.0")


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

