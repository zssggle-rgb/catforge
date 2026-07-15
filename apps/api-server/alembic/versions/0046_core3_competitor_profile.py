"""core3 versioned competitor profile persistence

Revision ID: 0046_core3_competitor_profile
Revises: 0045_core3_sellpoint_value_profile
Create Date: 2026-07-14

The V1 tables are declared locally so this historical revision cannot drift when
the application ORM grows new competitor-profile columns or constraints.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB


revision = "0046_core3_competitor_profile"
down_revision = "0045_core3_sellpoint_value_profile"
branch_labels = None
depends_on = None


def _json_type() -> sa.types.TypeEngine[object]:
    return sa.JSON().with_variant(JSONB, "postgresql")


def _audit_columns() -> tuple[sa.Column[object], sa.Column[object]]:
    return (
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )


_metadata = sa.MetaData()
sa.Table(
    "category_project",
    _metadata,
    sa.Column("project_id", sa.String(36), primary_key=True),
)
sa.Table(
    "core3_source_batch",
    _metadata,
    sa.Column("batch_id", sa.String(80), primary_key=True),
)

VERSION_TABLE = sa.Table(
    "core3_competitor_profile_version",
    _metadata,
    sa.Column("competitor_profile_version_id", sa.String(120), primary_key=True),
    sa.Column(
        "project_id",
        sa.String(36),
        sa.ForeignKey("category_project.project_id"),
        nullable=False,
        index=True,
    ),
    sa.Column("category_code", sa.String(40), nullable=False, index=True),
    sa.Column("product_category", sa.String(40), nullable=False, index=True),
    sa.Column(
        "storage_batch_id",
        sa.String(80),
        sa.ForeignKey("core3_source_batch.batch_id"),
        nullable=False,
        index=True,
    ),
    sa.Column("release_scope_key", sa.String(200), nullable=False, index=True),
    sa.Column("profile_version", sa.String(160), nullable=False, index=True),
    sa.Column("schema_version", sa.String(160), nullable=False, index=True),
    sa.Column("rule_version", sa.String(160), nullable=False, index=True),
    sa.Column("method_version", sa.String(160), nullable=False, index=True),
    sa.Column("method_versions_json", _json_type(), nullable=False),
    sa.Column("serving_scope_json", _json_type(), nullable=False),
    sa.Column("source_authorities_json", _json_type(), nullable=False),
    sa.Column("source_batch_ids_json", _json_type(), nullable=False),
    sa.Column("authoritative_sku_manifest_hash", sa.String(200), nullable=False),
    sa.Column("release_status", sa.String(40), nullable=False, index=True),
    sa.Column("release_quality_status", sa.String(40), nullable=False, index=True),
    sa.Column("is_current", sa.Boolean(), nullable=False, index=True),
    sa.Column("freshness_status", sa.String(40), nullable=False, index=True),
    sa.Column("generated_at", sa.DateTime(), nullable=False),
    sa.Column("generated_by", sa.String(160), nullable=False),
    sa.Column("reviewed_at", sa.DateTime(), nullable=True),
    sa.Column("reviewed_by", sa.String(160), nullable=True),
    sa.Column("published_at", sa.DateTime(), nullable=True),
    sa.Column("published_by", sa.String(160), nullable=True),
    sa.Column("current_at", sa.DateTime(), nullable=True),
    sa.Column("current_by", sa.String(160), nullable=True),
    sa.Column("deprecated_at", sa.DateTime(), nullable=True),
    sa.Column("deprecated_by", sa.String(160), nullable=True),
    sa.Column("release_note_cn", sa.Text(), nullable=True),
    sa.Column("sku_count", sa.Integer(), nullable=False),
    sa.Column("ready_count", sa.Integer(), nullable=False),
    sa.Column("partial_count", sa.Integer(), nullable=False),
    sa.Column("blocked_count", sa.Integer(), nullable=False),
    sa.Column("failed_count", sa.Integer(), nullable=False),
    sa.Column("pair_count", sa.Integer(), nullable=False),
    sa.Column("relation_count", sa.Integer(), nullable=False),
    sa.Column("selection_count", sa.Integer(), nullable=False),
    sa.Column("input_fingerprint", sa.String(200), nullable=False, index=True),
    sa.Column("candidate_universe_fingerprint", sa.String(200), nullable=False),
    sa.Column("result_hash", sa.String(200), nullable=False, index=True),
    sa.Column("processing_status", sa.String(60), nullable=False, index=True),
    sa.Column("review_required", sa.Boolean(), nullable=False, index=True),
    sa.Column("review_status", sa.String(60), nullable=False, index=True),
    sa.Column("review_reasons_json", _json_type(), nullable=False),
    sa.Column("safe_error_summary_json", _json_type(), nullable=False),
    *_audit_columns(),
    sa.UniqueConstraint(
        "project_id",
        "category_code",
        "release_scope_key",
        "profile_version",
        "rule_version",
        name="uq_core3_cp_version_key",
    ),
    sa.CheckConstraint(
        "category_code = product_category", name="ck_core3_cp_version_category"
    ),
    sa.CheckConstraint("sku_count >= 0", name="ck_core3_cp_version_sku_count"),
    sa.CheckConstraint("ready_count >= 0", name="ck_core3_cp_version_ready_count"),
    sa.CheckConstraint("partial_count >= 0", name="ck_core3_cp_version_partial_count"),
    sa.CheckConstraint("blocked_count >= 0", name="ck_core3_cp_version_blocked_count"),
    sa.CheckConstraint("failed_count >= 0", name="ck_core3_cp_version_failed_count"),
    sa.CheckConstraint("pair_count >= 0", name="ck_core3_cp_version_pair_count"),
    sa.CheckConstraint(
        "relation_count >= 0", name="ck_core3_cp_version_relation_count"
    ),
    sa.CheckConstraint(
        "selection_count >= 0", name="ck_core3_cp_version_selection_count"
    ),
    sa.CheckConstraint(
        "ready_count + partial_count + blocked_count + failed_count <= sku_count",
        name="ck_core3_cp_version_status_counts",
    ),
    sa.CheckConstraint(
        "selection_count <= sku_count * 3",
        name="ck_core3_cp_version_selection_limit",
    ),
    sa.CheckConstraint(
        "relation_count <= pair_count * 7",
        name="ck_core3_cp_version_relation_limit",
    ),
    sa.CheckConstraint(
        "release_status in ('draft','review','published','deprecated')",
        name="ck_core3_cp_version_release_status",
    ),
    sa.CheckConstraint(
        "release_quality_status in ('unassessed','ready','limited','blocked')",
        name="ck_core3_cp_version_quality_status",
    ),
    sa.CheckConstraint(
        "freshness_status in ('current','stale','unknown')",
        name="ck_core3_cp_version_freshness",
    ),
    sa.CheckConstraint(
        "NOT is_current OR release_status = 'published'",
        name="ck_core3_cp_version_current_release",
    ),
    sa.Index(
        "ix_core3_cp_version_scope",
        "project_id",
        "category_code",
        "release_scope_key",
    ),
    sa.Index(
        "ix_core3_cp_version_release",
        "project_id",
        "category_code",
        "release_scope_key",
        "release_status",
        "is_current",
    ),
    sa.Index("ix_core3_cp_version_input_fp", "input_fingerprint"),
    sa.Index("ix_core3_cp_version_result_hash", "result_hash"),
    sa.Index(
        "uq_core3_cp_current_published",
        "project_id",
        "category_code",
        "release_scope_key",
        unique=True,
        postgresql_where=sa.text("release_status = 'published' AND is_current = true"),
        sqlite_where=sa.text("release_status = 'published' AND is_current = 1"),
    ),
    sa.Index(
        "ix_core3_cp_version_scope_gin",
        "serving_scope_json",
        postgresql_using="gin",
    ),
    sa.Index(
        "ix_core3_cp_version_authority_gin",
        "source_authorities_json",
        postgresql_using="gin",
    ),
)

PROFILE_TABLE = sa.Table(
    "core3_sku_competitor_profile",
    _metadata,
    sa.Column("sku_competitor_profile_id", sa.String(120), primary_key=True),
    sa.Column(
        "competitor_profile_version_id",
        sa.String(120),
        sa.ForeignKey(
            "core3_competitor_profile_version.competitor_profile_version_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    ),
    sa.Column(
        "project_id",
        sa.String(36),
        sa.ForeignKey("category_project.project_id"),
        nullable=False,
        index=True,
    ),
    sa.Column("category_code", sa.String(40), nullable=False, index=True),
    sa.Column("product_category", sa.String(40), nullable=False, index=True),
    sa.Column(
        "storage_batch_id",
        sa.String(80),
        sa.ForeignKey("core3_source_batch.batch_id"),
        nullable=False,
        index=True,
    ),
    sa.Column("release_scope_key", sa.String(200), nullable=False, index=True),
    sa.Column("profile_version", sa.String(160), nullable=False, index=True),
    sa.Column("schema_version", sa.String(160), nullable=False),
    sa.Column("rule_version", sa.String(160), nullable=False, index=True),
    sa.Column("method_version", sa.String(160), nullable=False),
    sa.Column("target_sku_code", sa.String(160), nullable=False, index=True),
    sa.Column("display_name_cn", sa.String(320), nullable=False),
    sa.Column("analysis_state", sa.String(40), nullable=False, index=True),
    sa.Column("conclusion_state", sa.String(60), nullable=False, index=True),
    sa.Column("freshness_status", sa.String(40), nullable=False),
    sa.Column("profile_confidence", sa.Numeric(6, 4), nullable=False),
    sa.Column("candidate_status_counts_json", _json_type(), nullable=False),
    sa.Column("relation_status_counts_json", _json_type(), nullable=False),
    sa.Column("competitive_advantages_json", _json_type(), nullable=False),
    sa.Column("substitutable_values_json", _json_type(), nullable=False),
    sa.Column("price_scale_pressure_json", _json_type(), nullable=False),
    sa.Column("same_brand_findings_json", _json_type(), nullable=False),
    sa.Column("configuration_decisions_json", _json_type(), nullable=False),
    sa.Column("no_conclusion_reason_json", _json_type(), nullable=False),
    sa.Column("source_lineage_json", _json_type(), nullable=False),
    sa.Column("qa_index_json", _json_type(), nullable=False),
    sa.Column("evidence_refs_json", _json_type(), nullable=False),
    sa.Column("limitations_json", _json_type(), nullable=False),
    sa.Column("profile_payload_json", _json_type(), nullable=False),
    sa.Column("release_status", sa.String(40), nullable=False, index=True),
    sa.Column("is_current", sa.Boolean(), nullable=False, index=True),
    sa.Column("input_fingerprint", sa.String(200), nullable=False, index=True),
    sa.Column("result_hash", sa.String(200), nullable=False, index=True),
    sa.Column("processing_status", sa.String(60), nullable=False),
    sa.Column("review_required", sa.Boolean(), nullable=False, index=True),
    sa.Column("review_status", sa.String(60), nullable=False),
    sa.Column("review_reasons_json", _json_type(), nullable=False),
    *_audit_columns(),
    sa.UniqueConstraint(
        "competitor_profile_version_id",
        "target_sku_code",
        name="uq_core3_cp_profile_key",
    ),
    sa.CheckConstraint(
        "category_code = product_category", name="ck_core3_cp_profile_category"
    ),
    sa.CheckConstraint(
        "analysis_state in ('ready','partial','blocked')",
        name="ck_core3_cp_profile_analysis_state",
    ),
    sa.CheckConstraint(
        "conclusion_state in "
        "('available','no_priority_competitor','insufficient_evidence')",
        name="ck_core3_cp_profile_conclusion_state",
    ),
    sa.CheckConstraint(
        "profile_confidence >= 0 and profile_confidence <= 1",
        name="ck_core3_cp_profile_confidence",
    ),
    sa.CheckConstraint(
        "release_status in ('draft','review','published','deprecated')",
        name="ck_core3_cp_profile_release_status",
    ),
    sa.CheckConstraint(
        "NOT is_current OR release_status = 'published'",
        name="ck_core3_cp_profile_current_release",
    ),
    sa.Index("ix_core3_cp_profile_version", "competitor_profile_version_id"),
    sa.Index(
        "ix_core3_cp_profile_sku",
        "project_id",
        "category_code",
        "release_scope_key",
        "target_sku_code",
    ),
    sa.Index(
        "ix_core3_cp_profile_status",
        "project_id",
        "category_code",
        "analysis_state",
        "conclusion_state",
        "review_required",
    ),
    sa.Index("ix_core3_cp_profile_result_hash", "result_hash"),
    sa.Index("ix_core3_cp_profile_qa_gin", "qa_index_json", postgresql_using="gin"),
)

PAIR_TABLE = sa.Table(
    "core3_sku_competitor_profile_pair",
    _metadata,
    sa.Column("sku_competitor_profile_pair_id", sa.String(120), primary_key=True),
    sa.Column(
        "sku_competitor_profile_id",
        sa.String(120),
        sa.ForeignKey(
            "core3_sku_competitor_profile.sku_competitor_profile_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    ),
    sa.Column(
        "competitor_profile_version_id",
        sa.String(120),
        sa.ForeignKey(
            "core3_competitor_profile_version.competitor_profile_version_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    ),
    sa.Column(
        "project_id",
        sa.String(36),
        sa.ForeignKey("category_project.project_id"),
        nullable=False,
        index=True,
    ),
    sa.Column("category_code", sa.String(40), nullable=False, index=True),
    sa.Column("product_category", sa.String(40), nullable=False),
    sa.Column(
        "storage_batch_id",
        sa.String(80),
        sa.ForeignKey("core3_source_batch.batch_id"),
        nullable=False,
        index=True,
    ),
    sa.Column("release_scope_key", sa.String(200), nullable=False, index=True),
    sa.Column("profile_version", sa.String(160), nullable=False, index=True),
    sa.Column("schema_version", sa.String(160), nullable=False),
    sa.Column("rule_version", sa.String(160), nullable=False, index=True),
    sa.Column("method_version", sa.String(160), nullable=False),
    sa.Column("target_sku_code", sa.String(160), nullable=False, index=True),
    sa.Column("candidate_sku_code", sa.String(160), nullable=False, index=True),
    sa.Column("candidate_identity_json", _json_type(), nullable=False),
    sa.Column("recall_sources_json", _json_type(), nullable=False),
    sa.Column("recall_facts_json", _json_type(), nullable=False),
    sa.Column("competitor_member", sa.Boolean(), nullable=False),
    sa.Column("reference_member", sa.Boolean(), nullable=False),
    sa.Column("candidate_status", sa.String(60), nullable=False, index=True),
    sa.Column("purchase_pool_level", sa.String(20), nullable=False, index=True),
    sa.Column("purchase_pool_json", _json_type(), nullable=False),
    sa.Column("evidence_family_json", _json_type(), nullable=False),
    sa.Column("market_comparison_json", _json_type(), nullable=False),
    sa.Column("question_eligibility_json", _json_type(), nullable=False),
    sa.Column("reference_purposes_json", _json_type(), nullable=False),
    sa.Column("primary_relation_code", sa.String(80), nullable=True, index=True),
    sa.Column("relation_codes_json", _json_type(), nullable=False),
    sa.Column("selected", sa.Boolean(), nullable=False, index=True),
    sa.Column("non_selection_reason_code", sa.String(120), nullable=True, index=True),
    sa.Column("non_selection_reason_cn", sa.Text(), nullable=True),
    sa.Column("confidence_level", sa.String(20), nullable=False, index=True),
    sa.Column("confidence", sa.Numeric(6, 4), nullable=False),
    sa.Column("evidence_refs_json", _json_type(), nullable=False),
    sa.Column("limitations_json", _json_type(), nullable=False),
    sa.Column("risk_flags_json", _json_type(), nullable=False),
    sa.Column("pair_payload_json", _json_type(), nullable=False),
    sa.Column("release_status", sa.String(40), nullable=False, index=True),
    sa.Column("is_current", sa.Boolean(), nullable=False),
    sa.Column("input_fingerprint", sa.String(200), nullable=False, index=True),
    sa.Column("result_hash", sa.String(200), nullable=False, index=True),
    sa.Column("processing_status", sa.String(60), nullable=False),
    sa.Column("review_required", sa.Boolean(), nullable=False, index=True),
    sa.Column("review_status", sa.String(60), nullable=False),
    sa.Column("review_reasons_json", _json_type(), nullable=False),
    *_audit_columns(),
    sa.UniqueConstraint(
        "sku_competitor_profile_id",
        "candidate_sku_code",
        name="uq_core3_cp_pair_key",
    ),
    sa.CheckConstraint(
        "target_sku_code <> candidate_sku_code",
        name="ck_core3_cp_pair_distinct",
    ),
    sa.CheckConstraint(
        "competitor_member OR reference_member OR candidate_status in "
        "('review_required','blocked','recalled_only')",
        name="ck_core3_cp_pair_membership",
    ),
    sa.CheckConstraint(
        "confidence >= 0 and confidence <= 1",
        name="ck_core3_cp_pair_confidence",
    ),
    sa.CheckConstraint(
        "candidate_status in "
        "('eligible','limited','review_required','blocked','recalled_only',"
        "'reference_only')",
        name="ck_core3_cp_pair_status",
    ),
    sa.CheckConstraint(
        "purchase_pool_level in ('P0','P1','P2','P3','unknown')",
        name="ck_core3_cp_pair_pool",
    ),
    sa.CheckConstraint(
        "confidence_level in ('high','medium','low','unknown')",
        name="ck_core3_cp_pair_confidence_level",
    ),
    sa.CheckConstraint(
        "NOT selected OR candidate_status in ('eligible','limited')",
        name="ck_core3_cp_pair_selected_status",
    ),
    sa.Index(
        "ix_core3_cp_pair_profile",
        "sku_competitor_profile_id",
        "candidate_status",
    ),
    sa.Index("ix_core3_cp_pair_version", "competitor_profile_version_id"),
    sa.Index(
        "ix_core3_cp_pair_target_candidate",
        "project_id",
        "category_code",
        "target_sku_code",
        "candidate_sku_code",
    ),
    sa.Index(
        "ix_core3_cp_pair_candidate_target",
        "candidate_sku_code",
        "target_sku_code",
    ),
    sa.Index("ix_core3_cp_pair_selected", "sku_competitor_profile_id", "selected"),
    sa.Index(
        "ix_core3_cp_pair_questions_gin",
        "question_eligibility_json",
        postgresql_using="gin",
    ),
    sa.Index(
        "ix_core3_cp_pair_reference_gin",
        "reference_purposes_json",
        postgresql_using="gin",
    ),
)

RELATION_TABLE = sa.Table(
    "core3_sku_competitor_profile_relation",
    _metadata,
    sa.Column("sku_competitor_profile_relation_id", sa.String(120), primary_key=True),
    sa.Column(
        "sku_competitor_profile_pair_id",
        sa.String(120),
        sa.ForeignKey(
            "core3_sku_competitor_profile_pair.sku_competitor_profile_pair_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    ),
    sa.Column(
        "competitor_profile_version_id",
        sa.String(120),
        sa.ForeignKey(
            "core3_competitor_profile_version.competitor_profile_version_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    ),
    sa.Column(
        "project_id",
        sa.String(36),
        sa.ForeignKey("category_project.project_id"),
        nullable=False,
        index=True,
    ),
    sa.Column("category_code", sa.String(40), nullable=False, index=True),
    sa.Column("product_category", sa.String(40), nullable=False),
    sa.Column(
        "storage_batch_id",
        sa.String(80),
        sa.ForeignKey("core3_source_batch.batch_id"),
        nullable=False,
        index=True,
    ),
    sa.Column("release_scope_key", sa.String(200), nullable=False, index=True),
    sa.Column("profile_version", sa.String(160), nullable=False),
    sa.Column("schema_version", sa.String(160), nullable=False),
    sa.Column("rule_version", sa.String(160), nullable=False),
    sa.Column("method_version", sa.String(160), nullable=False),
    sa.Column("target_sku_code", sa.String(160), nullable=False, index=True),
    sa.Column("candidate_sku_code", sa.String(160), nullable=False, index=True),
    sa.Column("relation_code", sa.String(80), nullable=False, index=True),
    sa.Column("relation_status", sa.String(40), nullable=False, index=True),
    sa.Column("is_primary", sa.Boolean(), nullable=False),
    sa.Column("confidence_level", sa.String(20), nullable=False, index=True),
    sa.Column("gate_results_json", _json_type(), nullable=False),
    sa.Column("supporting_evidence_families_json", _json_type(), nullable=False),
    sa.Column("business_effect_json", _json_type(), nullable=False),
    sa.Column("eligible_question_codes_json", _json_type(), nullable=False),
    sa.Column("reason_codes_json", _json_type(), nullable=False),
    sa.Column("evidence_refs_json", _json_type(), nullable=False),
    sa.Column("limitations_json", _json_type(), nullable=False),
    sa.Column("relation_payload_json", _json_type(), nullable=False),
    sa.Column("release_status", sa.String(40), nullable=False, index=True),
    sa.Column("is_current", sa.Boolean(), nullable=False),
    sa.Column("input_fingerprint", sa.String(200), nullable=False, index=True),
    sa.Column("result_hash", sa.String(200), nullable=False, index=True),
    sa.Column("processing_status", sa.String(60), nullable=False),
    sa.Column("review_required", sa.Boolean(), nullable=False, index=True),
    sa.Column("review_status", sa.String(60), nullable=False),
    sa.Column("review_reasons_json", _json_type(), nullable=False),
    *_audit_columns(),
    sa.UniqueConstraint(
        "sku_competitor_profile_pair_id",
        "relation_code",
        name="uq_core3_cp_relation_key",
    ),
    sa.CheckConstraint(
        "relation_code in "
        "('direct_substitute','same_budget_alternative','downtrade_diversion',"
        "'uptrade_alternative','same_brand_ladder','scenario_substitute',"
        "'same_value_substitute')",
        name="ck_core3_cp_relation_code",
    ),
    sa.CheckConstraint(
        "relation_status in "
        "('passed','limited','unassessable','failed','review_required')",
        name="ck_core3_cp_relation_status",
    ),
    sa.CheckConstraint(
        "confidence_level in ('high','medium','low','unknown')",
        name="ck_core3_cp_relation_confidence",
    ),
    sa.CheckConstraint(
        "NOT is_primary OR relation_status in ('passed','limited')",
        name="ck_core3_cp_relation_primary",
    ),
    sa.Index(
        "ix_core3_cp_relation_pair", "sku_competitor_profile_pair_id", "relation_code"
    ),
    sa.Index("ix_core3_cp_relation_version", "competitor_profile_version_id"),
    sa.Index(
        "ix_core3_cp_relation_status",
        "relation_code",
        "relation_status",
        "confidence_level",
    ),
    sa.Index(
        "ix_core3_cp_relation_review",
        "project_id",
        "category_code",
        "review_required",
    ),
)

SELECTION_TABLE = sa.Table(
    "core3_sku_competitor_profile_selection",
    _metadata,
    sa.Column("sku_competitor_profile_selection_id", sa.String(120), primary_key=True),
    sa.Column(
        "sku_competitor_profile_id",
        sa.String(120),
        sa.ForeignKey(
            "core3_sku_competitor_profile.sku_competitor_profile_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    ),
    sa.Column(
        "sku_competitor_profile_pair_id",
        sa.String(120),
        sa.ForeignKey(
            "core3_sku_competitor_profile_pair.sku_competitor_profile_pair_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    ),
    sa.Column(
        "competitor_profile_version_id",
        sa.String(120),
        sa.ForeignKey(
            "core3_competitor_profile_version.competitor_profile_version_id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    ),
    sa.Column(
        "project_id",
        sa.String(36),
        sa.ForeignKey("category_project.project_id"),
        nullable=False,
        index=True,
    ),
    sa.Column("category_code", sa.String(40), nullable=False, index=True),
    sa.Column("product_category", sa.String(40), nullable=False),
    sa.Column(
        "storage_batch_id",
        sa.String(80),
        sa.ForeignKey("core3_source_batch.batch_id"),
        nullable=False,
        index=True,
    ),
    sa.Column("release_scope_key", sa.String(200), nullable=False),
    sa.Column("profile_version", sa.String(160), nullable=False),
    sa.Column("schema_version", sa.String(160), nullable=False),
    sa.Column("rule_version", sa.String(160), nullable=False),
    sa.Column("method_version", sa.String(160), nullable=False),
    sa.Column("target_sku_code", sa.String(160), nullable=False, index=True),
    sa.Column("candidate_sku_code", sa.String(160), nullable=False, index=True),
    sa.Column("selection_rank", sa.Integer(), nullable=False, index=True),
    sa.Column("primary_decision_topic", sa.String(80), nullable=False, index=True),
    sa.Column("covered_decision_topics_json", _json_type(), nullable=False),
    sa.Column("primary_relation_code", sa.String(80), nullable=False, index=True),
    sa.Column("auxiliary_relation_codes_json", _json_type(), nullable=False),
    sa.Column("selection_reason_cn", sa.Text(), nullable=False),
    sa.Column("independent_information_reason_cn", sa.Text(), nullable=False),
    sa.Column("price_value_pressure_summary_json", _json_type(), nullable=False),
    sa.Column("confidence_level", sa.String(20), nullable=False, index=True),
    sa.Column("evidence_refs_json", _json_type(), nullable=False),
    sa.Column("selection_payload_json", _json_type(), nullable=False),
    sa.Column("release_status", sa.String(40), nullable=False, index=True),
    sa.Column("is_current", sa.Boolean(), nullable=False),
    sa.Column("input_fingerprint", sa.String(200), nullable=False, index=True),
    sa.Column("result_hash", sa.String(200), nullable=False, index=True),
    sa.Column("processing_status", sa.String(60), nullable=False),
    sa.Column("review_required", sa.Boolean(), nullable=False),
    sa.Column("review_status", sa.String(60), nullable=False),
    sa.Column("review_reasons_json", _json_type(), nullable=False),
    *_audit_columns(),
    sa.UniqueConstraint(
        "sku_competitor_profile_id",
        "selection_rank",
        name="uq_core3_cp_selection_rank",
    ),
    sa.UniqueConstraint(
        "sku_competitor_profile_id",
        "candidate_sku_code",
        name="uq_core3_cp_selection_candidate",
    ),
    sa.CheckConstraint(
        "selection_rank >= 1 and selection_rank <= 3",
        name="ck_core3_cp_selection_rank",
    ),
    sa.CheckConstraint(
        "primary_decision_topic in "
        "('purchase_choice','price_scale_pressure','portfolio_or_scenario','value_route')",
        name="ck_core3_cp_selection_topic",
    ),
    sa.CheckConstraint(
        "confidence_level in ('high','medium','low','unknown')",
        name="ck_core3_cp_selection_confidence",
    ),
    sa.Index(
        "ix_core3_cp_selection_profile",
        "sku_competitor_profile_id",
        "selection_rank",
    ),
    sa.Index("ix_core3_cp_selection_pair", "sku_competitor_profile_pair_id"),
    sa.Index("ix_core3_cp_selection_version", "competitor_profile_version_id"),
    sa.Index("ix_core3_cp_selection_topic", "primary_decision_topic"),
)

PROFILE_TABLES = (
    VERSION_TABLE,
    PROFILE_TABLE,
    PAIR_TABLE,
    RELATION_TABLE,
    SELECTION_TABLE,
)


def upgrade() -> None:
    bind = op.get_bind()
    for table in PROFILE_TABLES:
        table.create(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    existing = set(sa.inspect(bind).get_table_names())
    populated = []
    for table in PROFILE_TABLES:
        if table.name not in existing:
            continue
        count = int(bind.scalar(sa.select(sa.func.count()).select_from(table)) or 0)
        if count:
            populated.append(f"{table.name}={count}")
    if populated:
        raise RuntimeError(
            "refusing to downgrade competitor profile tables with persisted data: "
            + ", ".join(populated)
        )
    for table in reversed(PROFILE_TABLES):
        table.drop(bind=bind, checkfirst=True)
