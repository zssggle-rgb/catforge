from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models import entities
from app.schemas.core3_real_data import (
    CleanCoverageSummary,
    CleanQualityIssueRead,
    CleanSkuSummary,
    ClaimActivationBaseRead,
    ClaimActivationEvidenceResponse,
    ClaimCommentReviewIssueListResponse,
    ClaimCommentReviewIssueResponse,
    ClaimCommentValidationListResponse,
    ClaimCommentValidationResponse,
    Core3ComparablePoolListResponse,
    Core3ComparablePoolResponse,
    Core3CandidateFeatureSnapshotListResponse,
    Core3CandidateFeatureSnapshotResponse,
    Core3CandidatePoolListResponse,
    Core3CandidatePoolResponse,
    Core3CandidateRecallReasonListResponse,
    Core3CandidateRecallReasonResponse,
    Core3CandidateRecallReviewIssueListResponse,
    Core3CandidateRecallReviewIssueResponse,
    Core3CandidateRecallRunApiRequest,
    Core3CandidateRecallRunListResponse,
    Core3CandidateRecallRunResponse,
    Core3CandidateComponentExplanationListResponse,
    Core3CandidateComponentExplanationResponse,
    Core3CandidateComponentScoreListResponse,
    Core3CandidateComponentScoreResponse,
    Core3CandidateRoleScoreListResponse,
    Core3CandidateRoleScoreResponse,
    Core3CandidateScoreReviewIssueListResponse,
    Core3CandidateScoreReviewIssueResponse,
    Core3ComponentScoringRunApiRequest,
    Core3CompetitorSelectionAuditListResponse,
    Core3CompetitorSelectionAuditResponse,
    Core3CompetitorSelectionListResponse,
    Core3CompetitorSelectionResponse,
    Core3CompetitorSelectionReviewIssueListResponse,
    Core3CompetitorSelectionReviewIssueResponse,
    Core3CompetitorSelectionRunListResponse,
    Core3CompetitorSelectionRunResponse,
    Core3CompetitorSlotDecisionListResponse,
    Core3CompetitorSlotDecisionResponse,
    Core3EvidenceCardListResponse,
    Core3EvidenceCardResponse,
    Core3EvidenceReportRunApiRequest,
    Core3EvidenceShortRefTraceResponse,
    Core3ReportExportListResponse,
    Core3ReportExportResponse,
    Core3ReportReviewIssueListResponse,
    Core3ReportReviewIssueResponse,
    Core3ReportSectionListResponse,
    Core3ReportSectionResponse,
    Core3SelectionRunApiRequest,
    Core3TargetReportPayloadListResponse,
    Core3TargetReportPayloadResponse,
    ClaimHitRead,
    ClaimSourceStatusRead,
    CommentEvidenceAtomListResponse,
    CommentEvidenceAtomResponse,
    CommentDownstreamSignalListResponse,
    CommentDownstreamSignalResponse,
    CommentQualityProfileListResponse,
    CommentQualityProfileResponse,
    CommentSignalCandidateListResponse,
    CommentSignalCandidateResponse,
    CommentTopicHintListResponse,
    CommentTopicHintResponse,
    CommentUnitSourceListResponse,
    CommentUnitSourceResponse,
    Core3BattlefieldRunApiRequest,
    Core3BaseClaimActivationRunApiRequest,
    Core3CleaningRunApiRequest,
    Core3ClaimValueLayerRunApiRequest,
    Core3ClaimActivationBaseListOut,
    Core3ClaimHitListOut,
    Core3ClaimSourceStatusListOut,
    Core3CleanSkuListOut,
    Core3CleanSummaryOut,
    Core3CommentEvidenceRunApiRequest,
    Core3ClaimCommentEnhancementRunApiRequest,
    Core3CommentSignalRunApiRequest,
    Core3EvidenceRunApiRequest,
    Core3MarketPoolMemberListResponse,
    Core3MarketPoolMemberResponse,
    Core3MarketProfileRunApiRequest,
    Core3MarketSignalListResponse,
    Core3MarketSignalResponse,
    Core3ModuleRunResultSchema,
    Core3PipelineInitializationModuleStatus,
    Core3PipelineInitializationRunApiRequest,
    Core3PipelineInitializationRunResponse,
    Core3PipelineInitializationStatusResponse,
    Core3ParamAliasCandidateListOut,
    Core3ParamExtractionRunApiRequest,
    Core3ParamFieldProfileListOut,
    Core3ParamTaxonomyDraftApiRequest,
    Core3ParamValueConflictListOut,
    Core3QualityIssueListOut,
    Core3SkuParamOut,
    Core3SourceBatchListOut,
    Core3SourceBatchOut,
    Core3SourceBatchRegisterApiRequest,
    Core3SourceBatchRegisterRequest,
    Core3SourceImpactedSkuListOut,
    Core3SourceImpactedSkuOut,
    Core3SourceRowRegistryListOut,
    Core3SourceRowRegistryOut,
    Core3SkuMarketProfileListResponse,
    Core3SkuMarketProfileResponse,
    Core3SkuDownstreamFeatureViewListResponse,
    Core3SkuDownstreamFeatureViewResponse,
    Core3SkuSignalEvidenceMatrixListResponse,
    Core3SkuSignalEvidenceMatrixResponse,
    Core3SkuSignalProfileListResponse,
    Core3SkuSignalProfileResponse,
    Core3SkuSignalProfileRunApiRequest,
    Core3SkuBattlefieldCandidateListResponse,
    Core3SkuBattlefieldCandidateResponse,
    Core3SkuBattlefieldEvidenceBreakdownListResponse,
    Core3SkuBattlefieldEvidenceBreakdownResponse,
    Core3SkuBattlefieldPortfolioListResponse,
    Core3SkuBattlefieldPortfolioResponse,
    Core3SkuBattlefieldReviewIssueListResponse,
    Core3SkuBattlefieldReviewIssueResponse,
    Core3SkuBattlefieldScoreListResponse,
    Core3SkuBattlefieldScoreResponse,
    Core3SkuBattlefieldClaimCandidateListResponse,
    Core3SkuBattlefieldClaimCandidateResponse,
    Core3SkuBattlefieldClaimValueSummaryListResponse,
    Core3SkuBattlefieldClaimValueSummaryResponse,
    Core3BusinessDimensionSalesSummaryListResponse,
    Core3BusinessDimensionSalesSummaryResponse,
    Core3BusinessDimensionSkuContributionListResponse,
    Core3BusinessDimensionSkuContributionResponse,
    Core3BusinessSalesReconciliationCheckListResponse,
    Core3BusinessSalesReconciliationCheckResponse,
    Core3BusinessSalesReconciliationIssueListResponse,
    Core3BusinessSalesReconciliationIssueResponse,
    Core3DimensionSalesReconciliationRunApiRequest,
    Core3DimensionCalibrationIssueListResponse,
    Core3DimensionCalibrationIssueResponse,
    Core3DimensionCandidateSnapshotListResponse,
    Core3DimensionCandidateSnapshotResponse,
    Core3DimensionDefinitionListResponse,
    Core3DimensionDefinitionResponse,
    Core3DimensionMappingRuleListResponse,
    Core3DimensionMappingRuleResponse,
    Core3CommentNativeDimensionRunApiRequest,
    Core3DimensionOntologyRunApiRequest,
    Core3DimensionOntologyVersionResponse,
    Core3SkuBusinessProfileDimensionListResponse,
    Core3SkuBusinessProfileDimensionResponse,
    Core3SkuBusinessProfileListResponse,
    Core3SkuBusinessProfileResponse,
    Core3SkuBusinessProfileReviewIssueListResponse,
    Core3SkuBusinessProfileReviewIssueResponse,
    Core3SkuBusinessProfileRunApiRequest,
    Core3SkuBusinessProfileSalesAllocationListResponse,
    Core3SkuBusinessProfileSalesAllocationResponse,
    Core3SkuClaimValueEvidenceBreakdownListResponse,
    Core3SkuClaimValueEvidenceBreakdownResponse,
    Core3SkuClaimValueLayerListResponse,
    Core3SkuClaimValueLayerResponse,
    Core3SkuClaimValueReviewIssueListResponse,
    Core3SkuClaimValueReviewIssueResponse,
    Core3SkuTaskCandidateListResponse,
    Core3SkuTaskCandidateResponse,
    Core3SkuTaskEvidenceBreakdownListResponse,
    Core3SkuTaskEvidenceBreakdownResponse,
    Core3SkuTaskReviewIssueListResponse,
    Core3SkuTaskReviewIssueResponse,
    Core3SkuTaskScoreListResponse,
    Core3SkuTaskScoreResponse,
    Core3SkuTargetGroupCandidateListResponse,
    Core3SkuTargetGroupCandidateResponse,
    Core3SkuTargetGroupEvidenceBreakdownListResponse,
    Core3SkuTargetGroupEvidenceBreakdownResponse,
    Core3SkuTargetGroupReviewIssueListResponse,
    Core3SkuTargetGroupReviewIssueResponse,
    Core3SkuTargetGroupScoreListResponse,
    Core3SkuTargetGroupScoreResponse,
    Core3TargetScopeSchema,
    Core3TargetGroupRunApiRequest,
    Core3UserTaskRunApiRequest,
    EvidenceAtomListItem,
    EvidenceAtomRead,
    EvidenceCounts,
    EvidenceLinkRead,
    EvidenceSummary,
    EvidenceTraceResponse,
    ExtractParamValueRead,
    ParamAliasCandidateRead,
    ParamFieldProfileRead,
    ParamTaxonomyDraftRequest,
    ParamTaxonomyDraftResult,
    ParamTaxonomyOut,
    ParamTaxonomyPublishRequest,
    ParamTaxonomyReviewDecisionRequest,
    ParamTaxonomyReviewItemRead,
    ParamTaxonomyReviewItemListOut,
    ParamValueConflictRead,
    SkuEvidenceQuery,
    SkuEvidenceResponse,
    SkuClaimBaseResponse,
    SkuClaimActivationListResponse,
    SkuClaimActivationResponse,
    SkuCommentSignalProfileListResponse,
    SkuCommentSignalProfileResponse,
    SkuParamProfileRead,
)
from app.services.core3_real_data.base_claim_activation_repositories import (
    ClaimActivationRepository,
    ClaimEvidenceReader,
    SkuParamProfileReader,
)
from app.services.core3_real_data.base_claim_activation_runner import BaseClaimActivationRunner
from app.services.core3_real_data.cleaning_repositories import CleaningQueryRepository
from app.services.core3_real_data.cleaning_runner import CleaningQualityRunner
from app.services.core3_real_data.comment_evidence_input_service import (
    CommentEvidenceInputRepository,
    M05InputBlockedError,
)
from app.services.core3_real_data.comment_evidence_repositories import CommentEvidenceReadRepository
from app.services.core3_real_data.comment_evidence_runner import CommentEvidenceRunner
from app.services.core3_real_data.comment_downstream_signal_repositories import (
    CommentDownstreamSignalReadRepository,
    M06InputBlockedError,
)
from app.services.core3_real_data.comment_downstream_signal_runner import CommentDownstreamSignalRunner
from app.services.core3_real_data.claim_comment_enhancement_repositories import (
    ClaimCommentEnhancementRepository,
    M04bInputBlockedError,
)
from app.services.core3_real_data.claim_comment_enhancement_runner import ClaimCommentEnhancementRunner
from app.services.core3_real_data.market_profile_repositories import M07InputBlockedError, M07MarketRepository
from app.services.core3_real_data.market_profile_runner import MarketProfileRunner
from app.services.core3_real_data.sku_signal_profile_repositories import M08InputBlockedError, M08SkuSignalRepository
from app.services.core3_real_data.sku_signal_profile_runner import SkuSignalProfileRunner
from app.services.core3_real_data.comment_native_dimension_repositories import (
    CommentNativeDimensionRepository,
    M084InputBlockedError,
)
from app.services.core3_real_data.comment_native_dimension_runner import M084CommentNativeDimensionRunner
from app.services.core3_real_data.dimension_ontology_repositories import DimensionOntologyRepository, M085InputBlockedError
from app.services.core3_real_data.dimension_ontology_runner import M085DimensionOntologyRunner
from app.services.core3_real_data.user_task_repositories import M09InputBlockedError, M09UserTaskRepository
from app.services.core3_real_data.user_task_runner import UserTaskRunner
from app.services.core3_real_data.target_group_repositories import M10InputBlockedError, M10TargetGroupRepository
from app.services.core3_real_data.target_group_runner import TargetGroupRunner
from app.services.core3_real_data.battlefield_repositories import M11BattlefieldRepository, M11InputBlockedError
from app.services.core3_real_data.battlefield_runner import BattlefieldRunner
from app.services.core3_real_data.claim_value_layer_repositories import ClaimValueLayerRepository, M115InputBlockedError
from app.services.core3_real_data.claim_value_layer_runner import ClaimValueLayerRunner
from app.services.core3_real_data.sku_business_profile_repositories import M116InputBlockedError, SkuBusinessProfileRepository
from app.services.core3_real_data.sku_business_profile_runner import SkuBusinessProfileRunner
from app.services.core3_real_data.dimension_sales_reconciliation_repositories import (
    DimensionSalesReconciliationRepository,
    M117InputBlockedError,
)
from app.services.core3_real_data.dimension_sales_reconciliation_runner import DimensionSalesReconciliationRunner
from app.services.core3_real_data.candidate_recall_repositories import CandidateRecallRepository, M12InputBlockedError
from app.services.core3_real_data.candidate_recall_runner import CandidateRecallRunner
from app.services.core3_real_data.component_scoring_repositories import ComponentScoringRepository, M13InputBlockedError
from app.services.core3_real_data.component_scoring_runner import ComponentScoringRunner
from app.services.core3_real_data.core3_selection_repositories import Core3SelectionRepository, M14InputBlockedError
from app.services.core3_real_data.core3_selection_runner import Core3SelectionRunner
from app.services.core3_real_data.evidence_report_repositories import EvidenceReportRepository, M15InputBlockedError
from app.services.core3_real_data.evidence_report_runner import EvidenceReportRunner
from app.services.core3_real_data.api_repositories import Core3RealDataApiRepository
from app.services.core3_real_data.api_response_schemas import (
    ApiQueryError,
    Core3V2BusinessReportResponse,
    Core3V2CoreCompetitorResponse,
    Core3V2DataStatusResponse,
    Core3V2EvidenceCardBusinessResponse,
    Core3V2EvidenceTraceResponse,
    Core3V2ExportBusinessResponse,
    Core3V2OverviewResponse,
    Core3V2PipelineRunListResponse,
    Core3V2ReleaseActionRequest,
    Core3V2ReportSectionBusinessResponse,
    Core3V2ReviewDecisionAliasRequest,
    Core3V2SkuResolveResponse,
    Core3V2TargetListResponse,
)
from app.services.core3_real_data.business_report_query_service import BusinessReportQueryService
from app.services.core3_real_data.evidence_trace_query_service import EvidenceTraceQueryService
from app.services.core3_real_data.export_delivery_service import ExportDeliveryService
from app.services.core3_real_data.overview_query_service import OverviewQueryService
from app.services.core3_real_data.pipeline_execution_service import PipelineExecutionService
from app.services.core3_real_data.pipeline_repositories import PipelineRepository
from app.services.core3_real_data.pipeline_schemas import (
    M16AcceptanceReportRecord,
    M16DependencySnapshotRecord,
    M16ListResponse,
    M16ModuleRunRecord,
    M16PipelineRunRequest,
    M16PipelineRunResponse,
    M16RecomputePlanRecord,
    M16ReleaseGateRecord,
    M16ReviewDecisionRecord,
    M16ReviewDecisionRequest,
    M16ReviewQueueRecord,
)
from app.services.core3_real_data.pipeline_status_query_service import PipelineStatusQueryService
from app.services.core3_real_data.pipeline_initialization_service import PipelineInitializationStatusService
from app.services.core3_real_data.review_action_api_service import ReviewActionApiService
from app.services.core3_real_data.sku_resolution_service import SkuResolutionService
from app.services.core3_real_data.constants import (
    CORE3_DEFAULT_RULESET_VERSION,
    CORE3_M02_CLEAN_SOURCE_TABLES,
    CORE3_M02_CONFIDENCE_RULE_VERSION,
    CORE3_M02_EVIDENCE_VERSION,
    CORE3_RAW_SOURCE_TABLES,
    Core3DataDomain,
    Core3EvidenceLinkStatus,
    Core3EvidenceLinkType,
    Core3EvidenceStatus,
    Core3EvidenceType,
    Core3ModuleCode,
    Core3ModuleTargetScope,
    Core3PipelineTriggerType,
    Core3RunMode,
    Core3RunStatus,
    Core3SourceBatchType,
    Core3TargetScopeType,
)
from app.services.core3_real_data.evidence_atom_repositories import (
    EvidenceAtomRepository,
    EvidenceLinkRepository,
)
from app.services.core3_real_data.evidence_atom_service import EvidenceAtomRunner
from app.services.core3_real_data.param_extraction_repositories import (
    ParamEvidenceReader,
    ParamExtractionRepository,
)
from app.services.core3_real_data.param_extraction_runner import ParamExtractionRunner
from app.services.core3_real_data.param_taxonomy_repositories import (
    ParamTaxonomyEvidenceReader,
    ParamTaxonomyImmutableError,
    ParamTaxonomyNotFoundError,
    ParamTaxonomyRepository,
)
from app.services.core3_real_data.param_taxonomy_service import ParamTaxonomyService
from app.services.core3_real_data.repositories import Core3RepositoryContext
from app.services.core3_real_data.runner import Core3ModuleTarget
from app.services.core3_real_data.run_context import build_run_context
from app.services.core3_real_data.source_registry_service import SourceRegistryRunner


router = APIRouter(prefix="/api/mvp/core3/v2", tags=["tv-core3-real-data"])


@router.post(
    "/projects/{project_id}/source-batches/register",
    response_model=Core3ModuleRunResultSchema,
)
def register_source_batch(
    project_id: str,
    payload: Core3SourceBatchRegisterApiRequest,
    db: Session = Depends(get_db),
) -> Core3ModuleRunResultSchema:
    request = Core3SourceBatchRegisterRequest(project_id=project_id, **payload.model_dump())
    try:
        result = SourceRegistryRunner(db).register_batch(request)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get(
    "/projects/{project_id}/source-batches",
    response_model=Core3SourceBatchListOut,
)
def list_source_batches(
    project_id: str,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SourceBatchListOut:
    total = db.execute(
        select(func.count()).select_from(entities.Core3SourceBatch).where(
            entities.Core3SourceBatch.project_id == project_id
        )
    ).scalar_one()
    rows = db.execute(
        select(entities.Core3SourceBatch)
        .where(entities.Core3SourceBatch.project_id == project_id)
        .order_by(entities.Core3SourceBatch.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    return Core3SourceBatchListOut(
        items=[Core3SourceBatchOut.model_validate(row, from_attributes=True) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/projects/{project_id}/source-batches/{batch_id}",
    response_model=Core3SourceBatchOut,
)
def get_source_batch(
    project_id: str,
    batch_id: str,
    db: Session = Depends(get_db),
) -> Core3SourceBatchOut:
    batch = _get_batch_or_404(db, project_id, batch_id)
    return Core3SourceBatchOut.model_validate(batch, from_attributes=True)


@router.get(
    "/projects/{project_id}/source-batches/{batch_id}/rows",
    response_model=Core3SourceRowRegistryListOut,
)
def list_source_batch_rows(
    project_id: str,
    batch_id: str,
    source_table: str | None = Query(default=None),
    sku_code_candidate: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SourceRowRegistryListOut:
    _get_batch_or_404(db, project_id, batch_id)
    if source_table is not None and source_table not in CORE3_RAW_SOURCE_TABLES:
        raise HTTPException(status_code=400, detail=f"unknown source_table: {source_table}")

    filters = [
        entities.Core3SourceRowRegistry.project_id == project_id,
        entities.Core3SourceRowRegistry.batch_id == batch_id,
    ]
    if source_table:
        filters.append(entities.Core3SourceRowRegistry.source_table == source_table)
    if sku_code_candidate:
        filters.append(entities.Core3SourceRowRegistry.sku_code_candidate == sku_code_candidate)

    total = db.execute(
        select(func.count()).select_from(entities.Core3SourceRowRegistry).where(*filters)
    ).scalar_one()
    rows = db.execute(
        select(entities.Core3SourceRowRegistry)
        .where(*filters)
        .order_by(entities.Core3SourceRowRegistry.source_table, entities.Core3SourceRowRegistry.source_pk)
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    return Core3SourceRowRegistryListOut(
        items=[_row_registry_out(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/projects/{project_id}/source-batches/{batch_id}/impacted-skus",
    response_model=Core3SourceImpactedSkuListOut,
)
def list_source_batch_impacted_skus(
    project_id: str,
    batch_id: str,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SourceImpactedSkuListOut:
    _get_batch_or_404(db, project_id, batch_id)
    filters = [
        entities.Core3SourceImpactedSku.project_id == project_id,
        entities.Core3SourceImpactedSku.batch_id == batch_id,
    ]
    total = db.execute(
        select(func.count()).select_from(entities.Core3SourceImpactedSku).where(*filters)
    ).scalar_one()
    rows = db.execute(
        select(entities.Core3SourceImpactedSku)
        .where(*filters)
        .order_by(entities.Core3SourceImpactedSku.sku_code_candidate)
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    return Core3SourceImpactedSkuListOut(
        items=[Core3SourceImpactedSkuOut.model_validate(row, from_attributes=True) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/projects/{project_id}/batches/{batch_id}/cleaning/run",
    response_model=Core3ModuleRunResultSchema,
)
def run_cleaning_quality(
    project_id: str,
    batch_id: str,
    payload: Core3CleaningRunApiRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> Core3ModuleRunResultSchema:
    payload = payload or Core3CleaningRunApiRequest()
    _get_batch_or_404(db, project_id, batch_id)
    context = build_run_context(
        run_id=payload.run_id or f"m01-api-{batch_id}",
        project_id=project_id,
        category_code=payload.category_code,
        batch_id=batch_id,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(
            scope_type=Core3TargetScopeType.CHANGED_SKU,
            sku_codes=payload.target_sku_codes,
            data_domains=[
                Core3DataDomain.SKU,
                Core3DataDomain.MARKET,
                Core3DataDomain.PARAM,
                Core3DataDomain.CLAIM,
                Core3DataDomain.COMMENT,
                Core3DataDomain.QUALITY,
            ],
            note_cn="M01 清洗规范化与质量诊断手工触发",
        ),
    )
    target = Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        target_ids=tuple(payload.target_sku_codes),
        data_domains=(
            Core3DataDomain.SKU,
            Core3DataDomain.MARKET,
            Core3DataDomain.PARAM,
            Core3DataDomain.CLAIM,
            Core3DataDomain.COMMENT,
            Core3DataDomain.QUALITY,
        ),
        metadata={
            "batch_id": batch_id,
            "module_run_id": payload.module_run_id,
            "include_no_change": payload.include_no_change,
            "clean_version": payload.clean_version,
            "hash_version": payload.hash_version,
        },
    )
    try:
        result = CleaningQualityRunner(db).run(context, target)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get(
    "/projects/{project_id}/batches/{batch_id}/cleaning/summary",
    response_model=Core3CleanSummaryOut,
)
def get_cleaning_summary(
    project_id: str,
    batch_id: str,
    db: Session = Depends(get_db),
) -> Core3CleanSummaryOut:
    batch = _get_batch_or_404(db, project_id, batch_id)
    query = CleaningQueryRepository(_repository_context(db, project_id, batch.category_code))
    summary = query.get_clean_summary(batch_id)
    return Core3CleanSummaryOut(
        project_id=project_id,
        category_code=batch.category_code,
        batch_id=batch_id,
        clean_counts=summary["clean_counts"],
        issue_counts=summary["issue_counts"],
        review_required=summary["review_required"],
        quality_summary_cn=_quality_summary_cn(summary["issue_counts"], summary["review_required"]),
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/cleaning/skus",
    response_model=Core3CleanSkuListOut,
)
def list_cleaning_skus(
    project_id: str,
    batch_id: str,
    sku_code: str | None = Query(default=None),
    quality_status: str | None = Query(default=None),
    review_required: bool | None = Query(default=None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3CleanSkuListOut:
    batch = _get_batch_or_404(db, project_id, batch_id)
    filters = [
        entities.Core3CleanSku.project_id == project_id,
        entities.Core3CleanSku.category_code == batch.category_code,
        entities.Core3CleanSku.batch_id == batch_id,
    ]
    if sku_code:
        filters.append(entities.Core3CleanSku.sku_code == sku_code)
    if quality_status:
        filters.append(entities.Core3CleanSku.quality_status == quality_status)
    if review_required is not None:
        filters.append(entities.Core3CleanSku.review_required == review_required)

    total = db.execute(select(func.count()).select_from(entities.Core3CleanSku).where(*filters)).scalar_one()
    rows = db.execute(
        select(entities.Core3CleanSku)
        .where(*filters)
        .order_by(entities.Core3CleanSku.sku_code)
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    return Core3CleanSkuListOut(
        items=[_clean_sku_summary(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/quality-issues",
    response_model=Core3QualityIssueListOut,
)
def list_cleaning_quality_issues(
    project_id: str,
    batch_id: str,
    sku_code: str | None = Query(default=None),
    domain: str | None = Query(default=None),
    issue_type: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    review_required: bool | None = Query(default=None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3QualityIssueListOut:
    batch = _get_batch_or_404(db, project_id, batch_id)
    filters = [
        entities.Core3DataQualityIssue.project_id == project_id,
        entities.Core3DataQualityIssue.category_code == batch.category_code,
        entities.Core3DataQualityIssue.batch_id == batch_id,
    ]
    if sku_code:
        filters.append(entities.Core3DataQualityIssue.sku_code == sku_code)
    if domain:
        filters.append(entities.Core3DataQualityIssue.domain == domain)
    if issue_type:
        filters.append(entities.Core3DataQualityIssue.issue_type == issue_type)
    if severity:
        filters.append(entities.Core3DataQualityIssue.severity == severity)
    if review_required is not None:
        filters.append(entities.Core3DataQualityIssue.review_required == review_required)

    total = db.execute(
        select(func.count()).select_from(entities.Core3DataQualityIssue).where(*filters)
    ).scalar_one()
    rows = db.execute(
        select(entities.Core3DataQualityIssue)
        .where(*filters)
        .order_by(entities.Core3DataQualityIssue.created_at, entities.Core3DataQualityIssue.issue_id)
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    issue_counts = _issue_counts_from_rows(rows)
    return Core3QualityIssueListOut(
        items=[CleanQualityIssueRead.model_validate(row, from_attributes=True) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
        quality_summary_cn=_quality_summary_cn(issue_counts, bool(issue_counts["review_required"])),
    )


@router.post(
    "/projects/{project_id}/batches/{batch_id}/evidence/run",
    response_model=Core3ModuleRunResultSchema,
)
def run_evidence_atom(
    project_id: str,
    batch_id: str,
    payload: Core3EvidenceRunApiRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> Core3ModuleRunResultSchema:
    payload = payload or Core3EvidenceRunApiRequest()
    _get_batch_or_404(db, project_id, batch_id)
    context = build_run_context(
        run_id=payload.run_id or f"m02-api-{batch_id}",
        project_id=project_id,
        category_code=payload.category_code,
        batch_id=batch_id,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(
            scope_type=Core3TargetScopeType.CHANGED_SKU,
            sku_codes=payload.target_sku_codes,
            data_domains=[
                Core3DataDomain.SKU,
                Core3DataDomain.MARKET,
                Core3DataDomain.PARAM,
                Core3DataDomain.CLAIM,
                Core3DataDomain.COMMENT,
                Core3DataDomain.QUALITY,
            ],
            note_cn="M02 证据原子层手工触发",
        ),
    )
    target = Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        target_ids=tuple(payload.target_sku_codes),
        data_domains=(
            Core3DataDomain.SKU,
            Core3DataDomain.MARKET,
            Core3DataDomain.PARAM,
            Core3DataDomain.CLAIM,
            Core3DataDomain.COMMENT,
            Core3DataDomain.QUALITY,
        ),
        metadata={
            "batch_id": batch_id,
            "module_run_id": payload.module_run_id,
            "evidence_version": payload.evidence_version,
            "confidence_rule_version": payload.confidence_rule_version,
        },
    )
    try:
        result = EvidenceAtomRunner(db).run(context, target)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get(
    "/projects/{project_id}/batches/{batch_id}/evidence/summary",
    response_model=EvidenceSummary,
)
def get_evidence_summary(
    project_id: str,
    batch_id: str,
    db: Session = Depends(get_db),
) -> EvidenceSummary:
    batch = _get_batch_or_404(db, project_id, batch_id)
    context = _repository_context(db, project_id, batch.category_code)
    summary = EvidenceAtomRepository(context).get_summary(batch_id)
    link_count = sum(EvidenceLinkRepository(context).count_by_type(batch_id).values())
    source_clean_tables = _source_clean_tables_for_evidence(db, project_id, batch.category_code, batch_id)
    return _evidence_summary_out(
        project_id=project_id,
        category_code=batch.category_code,
        batch_id=batch_id,
        summary=summary,
        link_count=link_count,
        source_clean_tables=source_clean_tables,
    )


@router.get(
    "/projects/{project_id}/evidence/{evidence_id}",
    response_model=EvidenceTraceResponse,
)
def get_evidence_atom(
    project_id: str,
    evidence_id: str,
    db: Session = Depends(get_db),
) -> EvidenceTraceResponse:
    record = _get_evidence_or_404(db, project_id, evidence_id)
    return _evidence_trace_response(db, project_id, record)


@router.get(
    "/projects/{project_id}/evidence/{evidence_id}/links",
    response_model=list[EvidenceLinkRead],
)
def list_evidence_links(
    project_id: str,
    evidence_id: str,
    direction: str = Query("both", pattern="^(from|to|both)$"),
    link_type: str | None = Query(default=None),
    current_only: bool = Query(default=True),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> list[EvidenceLinkRead]:
    record = _get_evidence_or_404(db, project_id, evidence_id)
    normalized_link_type = _normalize_evidence_link_type(link_type)
    context = _repository_context(db, project_id, record.category_code)
    try:
        links = EvidenceLinkRepository(context).list_links(
            evidence_id,
            direction=direction,
            link_type=normalized_link_type,
            current_only=current_only,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return [EvidenceLinkRead.model_validate(link, from_attributes=True) for link in links]


@router.get(
    "/projects/{project_id}/skus/{sku_code}/evidence",
    response_model=SkuEvidenceResponse,
)
def list_sku_evidence(
    project_id: str,
    sku_code: str,
    batch_id: str | None = Query(default=None),
    evidence_type: list[str] | None = Query(default=None),
    evidence_status: list[str] | None = Query(default=None),
    min_confidence: Decimal | None = Query(default=None, ge=0, le=1),
    current_only: bool = Query(default=True),
    include_links: bool = Query(default=True),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> SkuEvidenceResponse:
    category_code = "TV"
    if batch_id:
        batch = _get_batch_or_404(db, project_id, batch_id)
        category_code = batch.category_code

    evidence_types = _normalize_evidence_types(evidence_type or [])
    statuses = _normalize_evidence_statuses(evidence_status or [])
    filters = [
        entities.Core3EvidenceAtom.project_id == project_id,
        entities.Core3EvidenceAtom.category_code == category_code,
        entities.Core3EvidenceAtom.sku_code == sku_code,
    ]
    if batch_id:
        filters.append(entities.Core3EvidenceAtom.batch_id == batch_id)
    if evidence_types:
        filters.append(entities.Core3EvidenceAtom.evidence_type.in_(tuple(evidence_types)))
    if min_confidence is not None:
        filters.append(entities.Core3EvidenceAtom.base_confidence >= min_confidence)
    if current_only:
        filters.append(entities.Core3EvidenceAtom.is_current.is_(True))
        filters.append(entities.Core3EvidenceAtom.evidence_status == Core3EvidenceStatus.CURRENT.value)
    elif statuses:
        filters.append(entities.Core3EvidenceAtom.evidence_status.in_(tuple(statuses)))

    total = db.execute(select(func.count()).select_from(entities.Core3EvidenceAtom).where(*filters)).scalar_one()
    rows = db.execute(
        select(entities.Core3EvidenceAtom)
        .where(*filters)
        .order_by(
            entities.Core3EvidenceAtom.evidence_type,
            entities.Core3EvidenceAtom.evidence_field,
            entities.Core3EvidenceAtom.evidence_id,
        )
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    links = _links_for_evidence_rows(db, project_id, category_code, rows) if include_links else []
    summary = None
    if batch_id:
        context = _repository_context(db, project_id, category_code)
        evidence_summary = EvidenceAtomRepository(context).get_summary(batch_id)
        link_count = sum(EvidenceLinkRepository(context).count_by_type(batch_id).values())
        source_clean_tables = _source_clean_tables_for_evidence(db, project_id, category_code, batch_id)
        summary = _evidence_summary_out(
            project_id=project_id,
            category_code=category_code,
            batch_id=batch_id,
            summary=evidence_summary,
            link_count=link_count,
            source_clean_tables=source_clean_tables,
        )
    return SkuEvidenceResponse(
        query=SkuEvidenceQuery(
            project_id=project_id,
            sku_code=sku_code,
            category_code=category_code,
            batch_id=batch_id,
            evidence_types=evidence_types,
            evidence_statuses=statuses or [Core3EvidenceStatus.CURRENT.value],
            min_confidence=min_confidence,
            include_links=include_links,
            limit=limit,
            offset=offset,
        ),
        items=[EvidenceAtomListItem.model_validate(row, from_attributes=True) for row in rows],
        links=links,
        summary=summary,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/projects/{project_id}/batches/{batch_id}/params/run",
    response_model=Core3ModuleRunResultSchema,
)
def run_param_extraction(
    project_id: str,
    batch_id: str,
    payload: Core3ParamExtractionRunApiRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> Core3ModuleRunResultSchema:
    payload = payload or Core3ParamExtractionRunApiRequest()
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository_context = _repository_context(db, project_id, batch.category_code)
    ready_evidence = ParamEvidenceReader(repository_context).list_param_evidence(
        batch_id,
        target_sku_codes=payload.target_sku_codes,
        limit=1,
    )
    if not ready_evidence:
        raise HTTPException(
            status_code=409,
            detail="M02 evidence not ready: no current param_raw, promo_sentence or quality_issue evidence for M03.",
        )

    context = build_run_context(
        run_id=payload.run_id or f"m03-api-{batch_id}",
        project_id=project_id,
        category_code=payload.category_code,
        batch_id=batch_id,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(
            scope_type=Core3TargetScopeType.CHANGED_SKU,
            sku_codes=payload.target_sku_codes,
            data_domains=[
                Core3DataDomain.PARAM,
                Core3DataDomain.CLAIM,
                Core3DataDomain.QUALITY,
            ],
            note_cn="M03 参数字段画像与标准参数抽取手工触发",
        ),
    )
    target = Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        target_ids=tuple(payload.target_sku_codes),
        data_domains=(
            Core3DataDomain.PARAM,
            Core3DataDomain.CLAIM,
            Core3DataDomain.QUALITY,
        ),
        metadata={
            "batch_id": batch_id,
            "module_run_id": payload.module_run_id,
            "seed_version": payload.seed_version,
            "parser_version": payload.parser_version,
            "rule_version": payload.rule_version,
            "force_rebuild": payload.force_rebuild,
        },
    )
    try:
        result = ParamExtractionRunner(db).run(context, target)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get(
    "/projects/{project_id}/batches/{batch_id}/params/field-profiles",
    response_model=Core3ParamFieldProfileListOut,
)
def list_param_field_profiles(
    project_id: str,
    batch_id: str,
    matched: bool | None = Query(default=None),
    review_required: bool | None = Query(default=None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3ParamFieldProfileListOut:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = ParamExtractionRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_field_profiles(
        batch_id,
        matched=matched,
        review_required=review_required,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3ParamFieldProfile.project_id == project_id,
        entities.Core3ParamFieldProfile.category_code == batch.category_code,
        entities.Core3ParamFieldProfile.batch_id == batch_id,
    ]
    if matched is True:
        filters.append(entities.Core3ParamFieldProfile.matched_param_code.is_not(None))
    elif matched is False:
        filters.append(entities.Core3ParamFieldProfile.matched_param_code.is_(None))
    if review_required is not None:
        filters.append(entities.Core3ParamFieldProfile.review_required.is_(review_required))
    return Core3ParamFieldProfileListOut(
        items=[ParamFieldProfileRead.model_validate(item, from_attributes=True) for item in items],
        total=_count_model_rows(db, entities.Core3ParamFieldProfile, filters),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/projects/{project_id}/skus/{sku_code}/params",
    response_model=Core3SkuParamOut,
)
def get_sku_params(
    project_id: str,
    sku_code: str,
    batch_id: str | None = Query(default=None),
    param_code: str | None = Query(default=None),
    review_required: bool | None = Query(default=None),
    include_conflicts: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> Core3SkuParamOut:
    if batch_id is not None:
        batch = _get_batch_or_404(db, project_id, batch_id)
        repository = ParamExtractionRepository(_repository_context(db, project_id, batch.category_code))
        profile = repository.get_sku_param_profile(batch_id, sku_code)
    else:
        profile = db.execute(
            select(entities.Core3SkuParamProfile)
            .where(entities.Core3SkuParamProfile.project_id == project_id)
            .where(entities.Core3SkuParamProfile.sku_code == sku_code)
            .order_by(
                entities.Core3SkuParamProfile.updated_at.desc(),
                entities.Core3SkuParamProfile.sku_param_profile_id,
            )
        ).scalars().first()
        repository = (
            ParamExtractionRepository(_repository_context(db, project_id, profile.category_code))
            if profile is not None
            else None
        )
    if profile is None or repository is None:
        raise HTTPException(status_code=404, detail="sku param profile not found")

    values = repository.list_param_values(
        profile.batch_id,
        sku_code=sku_code,
        param_code=param_code,
        review_required=review_required,
        limit=500,
    )
    conflicts = (
        repository.list_param_conflicts(
            profile.batch_id,
            sku_code=sku_code,
            param_code=param_code,
            review_required=review_required,
            limit=500,
        )
        if include_conflicts
        else []
    )
    return Core3SkuParamOut(
        profile=SkuParamProfileRead.model_validate(profile, from_attributes=True),
        values=[ExtractParamValueRead.model_validate(item, from_attributes=True) for item in values],
        conflicts=[ParamValueConflictRead.model_validate(item, from_attributes=True) for item in conflicts],
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/params/alias-candidates",
    response_model=Core3ParamAliasCandidateListOut,
)
def list_param_alias_candidates(
    project_id: str,
    batch_id: str,
    review_status: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3ParamAliasCandidateListOut:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = ParamExtractionRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_alias_candidates(
        batch_id,
        review_status=review_status,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3ParamAliasCandidate.project_id == project_id,
        entities.Core3ParamAliasCandidate.category_code == batch.category_code,
        entities.Core3ParamAliasCandidate.batch_id == batch_id,
    ]
    if review_status is not None:
        filters.append(entities.Core3ParamAliasCandidate.review_status == review_status)
    return Core3ParamAliasCandidateListOut(
        items=[ParamAliasCandidateRead.model_validate(item, from_attributes=True) for item in items],
        total=_count_model_rows(db, entities.Core3ParamAliasCandidate, filters),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/params/conflicts",
    response_model=Core3ParamValueConflictListOut,
)
def list_param_conflicts(
    project_id: str,
    batch_id: str,
    sku_code: str | None = Query(default=None),
    param_code: str | None = Query(default=None),
    review_required: bool | None = Query(default=None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3ParamValueConflictListOut:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = ParamExtractionRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_param_conflicts(
        batch_id,
        sku_code=sku_code,
        param_code=param_code,
        review_required=review_required,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3ParamValueConflict.project_id == project_id,
        entities.Core3ParamValueConflict.category_code == batch.category_code,
        entities.Core3ParamValueConflict.batch_id == batch_id,
    ]
    if sku_code is not None:
        filters.append(entities.Core3ParamValueConflict.sku_code == sku_code)
    if param_code is not None:
        filters.append(entities.Core3ParamValueConflict.param_code == param_code)
    if review_required is not None:
        filters.append(entities.Core3ParamValueConflict.review_required.is_(review_required))
    return Core3ParamValueConflictListOut(
        items=[ParamValueConflictRead.model_validate(item, from_attributes=True) for item in items],
        total=_count_model_rows(db, entities.Core3ParamValueConflict, filters),
        limit=limit,
        offset=offset,
    )


@router.post(
    "/projects/{project_id}/categories/{category_code}/param-taxonomies/draft",
    response_model=ParamTaxonomyDraftResult,
)
def build_param_taxonomy_draft(
    project_id: str,
    category_code: str,
    payload: Core3ParamTaxonomyDraftApiRequest,
    db: Session = Depends(get_db),
) -> ParamTaxonomyDraftResult:
    normalized_category = category_code.strip().upper()
    _validate_taxonomy_batches(db, project_id, normalized_category, payload.batch_ids)
    repository = ParamTaxonomyRepository(db, project_id)
    evidence_reader = ParamTaxonomyEvidenceReader(db, project_id)
    request = ParamTaxonomyDraftRequest(
        category_code=normalized_category,
        batch_ids=payload.batch_ids,
        taxonomy_version=payload.taxonomy_version,
        use_llm=payload.use_llm,
        force_rebuild=payload.force_rebuild,
        created_by=payload.created_by,
        rule_version=payload.rule_version,
    )
    try:
        result = ParamTaxonomyService(repository, evidence_reader).build_draft(request)
        db.commit()
        return result
    except ParamTaxonomyImmutableError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get(
    "/projects/{project_id}/categories/{category_code}/param-taxonomies/current",
    response_model=ParamTaxonomyOut,
)
def get_current_param_taxonomy(
    project_id: str,
    category_code: str,
    db: Session = Depends(get_db),
) -> ParamTaxonomyOut:
    normalized_category = category_code.strip().upper()
    repository = ParamTaxonomyRepository(db, project_id)
    version = repository.get_current_published(normalized_category)
    if version is None:
        raise HTTPException(status_code=404, detail="published param taxonomy not found")
    return _param_taxonomy_out(repository.load_taxonomy(version.taxonomy_version, category_code=normalized_category))


@router.get(
    "/projects/{project_id}/categories/{category_code}/param-taxonomies/{taxonomy_version}",
    response_model=ParamTaxonomyOut,
)
def get_param_taxonomy(
    project_id: str,
    category_code: str,
    taxonomy_version: str,
    db: Session = Depends(get_db),
) -> ParamTaxonomyOut:
    normalized_category = category_code.strip().upper()
    repository = ParamTaxonomyRepository(db, project_id)
    try:
        return _param_taxonomy_out(repository.load_taxonomy(taxonomy_version, category_code=normalized_category))
    except ParamTaxonomyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/projects/{project_id}/categories/{category_code}/param-taxonomies/{taxonomy_version}/review-items",
    response_model=ParamTaxonomyReviewItemListOut,
)
def list_param_taxonomy_review_items(
    project_id: str,
    category_code: str,
    taxonomy_version: str,
    review_status: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> ParamTaxonomyReviewItemListOut:
    normalized_category = category_code.strip().upper()
    repository = ParamTaxonomyRepository(db, project_id)
    if repository.get_version(taxonomy_version, category_code=normalized_category) is None:
        raise HTTPException(status_code=404, detail="param taxonomy not found")
    items = repository.list_review_items(
        taxonomy_version,
        category_code=normalized_category,
        review_status=review_status,
        limit=limit,
        offset=offset,
    )
    return ParamTaxonomyReviewItemListOut(
        items=[ParamTaxonomyReviewItemRead.model_validate(item, from_attributes=True) for item in items],
        total=repository.count_review_items(
            taxonomy_version,
            category_code=normalized_category,
            review_status=review_status,
        ),
        limit=limit,
        offset=offset,
    )


@router.post(
    "/projects/{project_id}/categories/{category_code}/param-taxonomies/{taxonomy_version}/review-decisions",
    response_model=ParamTaxonomyReviewItemRead,
)
def decide_param_taxonomy_review_item(
    project_id: str,
    category_code: str,
    taxonomy_version: str,
    payload: ParamTaxonomyReviewDecisionRequest,
    db: Session = Depends(get_db),
) -> ParamTaxonomyReviewItemRead:
    normalized_category = category_code.strip().upper()
    repository = ParamTaxonomyRepository(db, project_id)
    if repository.get_version(taxonomy_version, category_code=normalized_category) is None:
        raise HTTPException(status_code=404, detail="param taxonomy not found")
    try:
        item = repository.apply_review_decision(
            taxonomy_version=taxonomy_version,
            review_item_id=payload.review_item_id,
            review_status=payload.decision,
            decision_payload=payload.decision_payload,
        )
        db.commit()
        return ParamTaxonomyReviewItemRead.model_validate(item, from_attributes=True)
    except ParamTaxonomyNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/projects/{project_id}/categories/{category_code}/param-taxonomies/{taxonomy_version}/publish",
    response_model=ParamTaxonomyOut,
)
def publish_param_taxonomy(
    project_id: str,
    category_code: str,
    taxonomy_version: str,
    payload: ParamTaxonomyPublishRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> ParamTaxonomyOut:
    del payload
    normalized_category = category_code.strip().upper()
    repository = ParamTaxonomyRepository(db, project_id)
    try:
        repository.publish(category_code=normalized_category, taxonomy_version=taxonomy_version)
        db.commit()
        return _param_taxonomy_out(repository.load_taxonomy(taxonomy_version, category_code=normalized_category))
    except ParamTaxonomyNotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/projects/{project_id}/batches/{batch_id}/claims/base/run",
    response_model=Core3ModuleRunResultSchema,
)
def run_base_claim_activation(
    project_id: str,
    batch_id: str,
    payload: Core3BaseClaimActivationRunApiRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> Core3ModuleRunResultSchema:
    payload = payload or Core3BaseClaimActivationRunApiRequest()
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository_context = _repository_context(db, project_id, batch.category_code)
    ready_evidence = ClaimEvidenceReader(repository_context).list_claim_evidence(
        batch_id,
        target_sku_codes=payload.target_sku_codes,
        limit=1,
    )
    ready_profiles = SkuParamProfileReader(repository_context).list_sku_param_profiles(
        batch_id,
        target_sku_codes=payload.target_sku_codes,
        limit=1,
    )
    if not ready_evidence and not ready_profiles:
        raise HTTPException(
            status_code=409,
            detail="M04a inputs not ready: no current promo/param/quality evidence or M03 SKU param profiles.",
        )

    context = build_run_context(
        run_id=payload.run_id or f"m04a-api-{batch_id}",
        project_id=project_id,
        category_code=payload.category_code,
        batch_id=batch_id,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(
            scope_type=Core3TargetScopeType.CHANGED_SKU,
            sku_codes=payload.target_sku_codes,
            data_domains=[
                Core3DataDomain.CLAIM,
                Core3DataDomain.PARAM,
                Core3DataDomain.QUALITY,
            ],
            note_cn="M04a 基础卖点激活手工触发",
        ),
    )
    target = Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        target_ids=tuple(payload.target_sku_codes),
        data_domains=(
            Core3DataDomain.CLAIM,
            Core3DataDomain.PARAM,
            Core3DataDomain.QUALITY,
        ),
        metadata={
            "batch_id": batch_id,
            "module_run_id": payload.module_run_id,
            "seed_version": payload.seed_version,
            "rule_version": payload.rule_version,
            "include_param_only_claims": payload.include_param_only_claims,
            "force_rebuild": payload.force_rebuild,
        },
    )
    try:
        result = BaseClaimActivationRunner(db).run(context, target)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get(
    "/projects/{project_id}/batches/{batch_id}/claims/source-status",
    response_model=Core3ClaimSourceStatusListOut,
)
def list_claim_source_statuses(
    project_id: str,
    batch_id: str,
    sku_code: str | None = Query(default=None),
    claim_source_status: str | None = Query(default=None),
    review_required: bool | None = Query(default=None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3ClaimSourceStatusListOut:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = ClaimActivationRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_claim_source_statuses(
        batch_id,
        sku_code=sku_code,
        claim_source_status=claim_source_status,
        review_required=review_required,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuClaimSourceStatus.project_id == project_id,
        entities.Core3SkuClaimSourceStatus.category_code == batch.category_code,
        entities.Core3SkuClaimSourceStatus.batch_id == batch_id,
    ]
    if sku_code is not None:
        filters.append(entities.Core3SkuClaimSourceStatus.sku_code == sku_code)
    if claim_source_status is not None:
        filters.append(entities.Core3SkuClaimSourceStatus.claim_source_status == claim_source_status)
    if review_required is not None:
        filters.append(entities.Core3SkuClaimSourceStatus.review_required.is_(review_required))
    return Core3ClaimSourceStatusListOut(
        items=[ClaimSourceStatusRead.model_validate(item, from_attributes=True) for item in items],
        total=_count_model_rows(db, entities.Core3SkuClaimSourceStatus, filters),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/projects/{project_id}/skus/{sku_code}/claims/base",
    response_model=SkuClaimBaseResponse,
)
def get_sku_base_claims(
    project_id: str,
    sku_code: str,
    batch_id: str | None = Query(default=None),
    claim_code: str | None = Query(default=None),
    activation_basis: str | None = Query(default=None),
    review_required: bool | None = Query(default=None),
    include_hits: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> SkuClaimBaseResponse:
    category_code = "TV"
    resolved_batch_id = batch_id
    if resolved_batch_id is not None:
        batch = _get_batch_or_404(db, project_id, resolved_batch_id)
        category_code = batch.category_code
    else:
        latest = db.execute(
            select(entities.Core3SkuClaimActivationBase)
            .where(entities.Core3SkuClaimActivationBase.project_id == project_id)
            .where(entities.Core3SkuClaimActivationBase.sku_code == sku_code)
            .order_by(
                entities.Core3SkuClaimActivationBase.updated_at.desc(),
                entities.Core3SkuClaimActivationBase.claim_activation_base_id,
            )
        ).scalars().first()
        if latest is None:
            raise HTTPException(status_code=404, detail="sku base claim activation not found")
        resolved_batch_id = latest.batch_id
        category_code = latest.category_code

    repository = ClaimActivationRepository(_repository_context(db, project_id, category_code))
    source_status = repository.get_claim_source_status(resolved_batch_id, sku_code)
    base_claims = repository.list_base_claims(
        resolved_batch_id,
        sku_code=sku_code,
        claim_code=claim_code,
        activation_basis=activation_basis,
        review_required=review_required,
        limit=500,
    )
    if source_status is None and not base_claims:
        raise HTTPException(status_code=404, detail="sku base claim activation not found")
    claim_hits = (
        repository.list_claim_hits(
            resolved_batch_id,
            sku_code=sku_code,
            claim_code=claim_code,
            review_required=review_required,
            limit=500,
        )
        if include_hits
        else []
    )
    return SkuClaimBaseResponse(
        project_id=project_id,
        category_code=category_code,
        batch_id=resolved_batch_id,
        sku_code=sku_code,
        model_name=_claim_model_name(source_status, base_claims, claim_hits),
        source_status=ClaimSourceStatusRead.model_validate(source_status, from_attributes=True)
        if source_status is not None
        else None,
        base_claims=[ClaimActivationBaseRead.model_validate(item, from_attributes=True) for item in base_claims],
        claim_hits=[ClaimHitRead.model_validate(item, from_attributes=True) for item in claim_hits],
        total_base_claim_count=len(base_claims),
        param_only_count=sum(1 for item in base_claims if item.activation_basis == "param_only"),
        review_required_count=sum(1 for item in [source_status, *base_claims, *claim_hits] if item and item.review_required),
        summary_cn=_sku_base_claim_summary_cn(source_status, base_claims),
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/claims/hits",
    response_model=Core3ClaimHitListOut,
)
def list_claim_hits(
    project_id: str,
    batch_id: str,
    sku_code: str | None = Query(default=None),
    claim_code: str | None = Query(default=None),
    hit_source_type: str | None = Query(default=None),
    review_required: bool | None = Query(default=None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3ClaimHitListOut:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = ClaimActivationRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_claim_hits(
        batch_id,
        sku_code=sku_code,
        claim_code=claim_code,
        hit_source_type=hit_source_type,
        review_required=review_required,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3ExtractClaimHit.project_id == project_id,
        entities.Core3ExtractClaimHit.category_code == batch.category_code,
        entities.Core3ExtractClaimHit.batch_id == batch_id,
    ]
    if sku_code is not None:
        filters.append(entities.Core3ExtractClaimHit.sku_code == sku_code)
    if claim_code is not None:
        filters.append(entities.Core3ExtractClaimHit.claim_code == claim_code)
    if hit_source_type is not None:
        filters.append(entities.Core3ExtractClaimHit.hit_source_type == hit_source_type)
    if review_required is not None:
        filters.append(entities.Core3ExtractClaimHit.review_required.is_(review_required))
    return Core3ClaimHitListOut(
        items=[ClaimHitRead.model_validate(item, from_attributes=True) for item in items],
        total=_count_model_rows(db, entities.Core3ExtractClaimHit, filters),
        limit=limit,
        offset=offset,
    )


@router.post(
    "/projects/{project_id}/batches/{batch_id}/comments/run",
    response_model=Core3ModuleRunResultSchema,
)
def run_comment_evidence(
    project_id: str,
    batch_id: str,
    payload: Core3CommentEvidenceRunApiRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> Core3ModuleRunResultSchema:
    payload = payload or Core3CommentEvidenceRunApiRequest()
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository_context = _repository_context(db, project_id, batch.category_code)
    input_repository = CommentEvidenceInputRepository(repository_context)
    try:
        input_repository.assert_m02_completed(batch_id)
    except M05InputBlockedError as exc:
        raise HTTPException(status_code=409, detail=f"M05 inputs not ready: {exc}") from exc

    if not payload.sku_scope and not input_repository.list_sku_codes_with_comment_evidence(batch_id):
        raise HTTPException(
            status_code=409,
            detail="M05 inputs not ready: no current comment evidence from M02 for this batch.",
        )

    context = build_run_context(
        run_id=payload.run_id or f"m05-api-{batch_id}",
        project_id=project_id,
        category_code=payload.category_code,
        batch_id=batch_id,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(
            scope_type=Core3TargetScopeType.CHANGED_SKU,
            sku_codes=payload.sku_scope,
            data_domains=[
                Core3DataDomain.COMMENT,
                Core3DataDomain.QUALITY,
            ],
            note_cn="M05 评论基础证据层手工触发",
        ),
        module_versions={"M05": payload.module_version},
        seed_versions={"M05": payload.seed_version},
        triggered_by=payload.triggered_by,
    )
    target = Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        target_ids=tuple(payload.sku_scope),
        data_domains=(
            Core3DataDomain.COMMENT,
            Core3DataDomain.QUALITY,
        ),
        metadata={
            "batch_id": batch_id,
            "module_run_id": payload.module_run_id,
            "module_version": payload.module_version,
            "seed_version": payload.seed_version,
            "rule_version": payload.rule_version,
            "force_rebuild": payload.force_rebuild,
        },
    )
    try:
        result = CommentEvidenceRunner(db).run(context, target)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get(
    "/projects/{project_id}/batches/{batch_id}/comments/profiles",
    response_model=CommentQualityProfileListResponse,
)
def list_comment_quality_profiles(
    project_id: str,
    batch_id: str,
    sku_code: str | None = Query(default=None),
    downstream_ready: bool | None = Query(default=None),
    review_required: bool | None = Query(default=None),
    sample_status: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> CommentQualityProfileListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = CommentEvidenceReadRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_profiles(
        batch_id,
        sku_code=sku_code,
        downstream_ready=downstream_ready,
        review_required=review_required,
        sample_status=sample_status,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3CommentQualityProfile.project_id == project_id,
        entities.Core3CommentQualityProfile.category_code == batch.category_code,
        entities.Core3CommentQualityProfile.batch_id == batch_id,
        entities.Core3CommentQualityProfile.is_current.is_(True),
    ]
    if sku_code is not None:
        filters.append(entities.Core3CommentQualityProfile.sku_code == sku_code)
    if downstream_ready is not None:
        filters.append(entities.Core3CommentQualityProfile.downstream_ready.is_(downstream_ready))
    if review_required is not None:
        filters.append(entities.Core3CommentQualityProfile.review_required.is_(review_required))
    if sample_status is not None:
        filters.append(entities.Core3CommentQualityProfile.sample_status == sample_status)
    total = _count_model_rows(db, entities.Core3CommentQualityProfile, filters)
    return CommentQualityProfileListResponse(
        items=[_comment_quality_profile_out(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=_comment_profile_list_summary_cn(items, total),
    )


@router.get(
    "/projects/{project_id}/skus/{sku_code}/comments/profile",
    response_model=CommentQualityProfileResponse,
)
def get_sku_comment_quality_profile(
    project_id: str,
    sku_code: str,
    batch_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> CommentQualityProfileResponse:
    if batch_id is not None:
        batch = _get_batch_or_404(db, project_id, batch_id)
        repository = CommentEvidenceReadRepository(_repository_context(db, project_id, batch.category_code))
        profile = repository.get_current_profile(batch_id, sku_code)
    else:
        profile = db.execute(
            select(entities.Core3CommentQualityProfile)
            .where(entities.Core3CommentQualityProfile.project_id == project_id)
            .where(entities.Core3CommentQualityProfile.sku_code == sku_code)
            .where(entities.Core3CommentQualityProfile.is_current.is_(True))
            .order_by(
                entities.Core3CommentQualityProfile.updated_at.desc(),
                entities.Core3CommentQualityProfile.comment_quality_profile_id,
            )
        ).scalars().first()
    if profile is None:
        raise HTTPException(status_code=404, detail="sku comment quality profile not found")
    return _comment_quality_profile_out(profile)


@router.get(
    "/projects/{project_id}/batches/{batch_id}/comments/units",
    response_model=CommentUnitSourceListResponse,
)
def list_comment_units(
    project_id: str,
    batch_id: str,
    sku_code: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> CommentUnitSourceListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = CommentEvidenceReadRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_units(batch_id, sku_code, limit=limit, offset=offset)
    filters = [
        entities.Core3CommentUnit.project_id == project_id,
        entities.Core3CommentUnit.category_code == batch.category_code,
        entities.Core3CommentUnit.batch_id == batch_id,
        entities.Core3CommentUnit.sku_code == sku_code,
        entities.Core3CommentUnit.is_current.is_(True),
    ]
    total = _count_model_rows(db, entities.Core3CommentUnit, filters)
    return CommentUnitSourceListResponse(
        items=[_comment_unit_out(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=_comment_unit_list_summary_cn(items, total),
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/comments/atoms",
    response_model=CommentEvidenceAtomListResponse,
)
def list_comment_atoms(
    project_id: str,
    batch_id: str,
    sku_code: str = Query(..., min_length=1),
    primary_domain_hint: str | None = Query(default=None),
    sentiment_hint: str | None = Query(default=None),
    low_value_flag: bool | None = Query(default=None),
    usable_for_downstream: bool | None = Query(default=None),
    topic_code: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> CommentEvidenceAtomListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = CommentEvidenceReadRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_atoms(
        batch_id,
        sku_code,
        primary_domain_hint=primary_domain_hint,
        sentiment_hint=sentiment_hint,
        low_value_flag=low_value_flag,
        usable_for_downstream=usable_for_downstream,
        topic_code=topic_code,
        limit=limit,
        offset=offset,
    )
    filters = _comment_atom_filters(
        project_id=project_id,
        category_code=batch.category_code,
        batch_id=batch_id,
        sku_code=sku_code,
        primary_domain_hint=primary_domain_hint,
        sentiment_hint=sentiment_hint,
        low_value_flag=low_value_flag,
        usable_for_downstream=usable_for_downstream,
        topic_code=topic_code,
    )
    total = _count_model_rows(db, entities.Core3CommentEvidenceAtom, filters)
    return CommentEvidenceAtomListResponse(
        items=[_comment_atom_out(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=_comment_atom_list_summary_cn(items, total),
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/comments/topics",
    response_model=CommentTopicHintListResponse,
)
def list_comment_topic_hints(
    project_id: str,
    batch_id: str,
    sku_code: str = Query(..., min_length=1),
    topic_code: str | None = Query(default=None),
    topic_group: str | None = Query(default=None),
    polarity_hint: str | None = Query(default=None),
    topic_hint_status: str | None = Query(default=None),
    service_guardrail_flag: bool | None = Query(default=None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> CommentTopicHintListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = CommentEvidenceReadRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_topic_hints(
        batch_id,
        sku_code,
        topic_code=topic_code,
        topic_group=topic_group,
        polarity_hint=polarity_hint,
        topic_hint_status=topic_hint_status,
        service_guardrail_flag=service_guardrail_flag,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3CommentTopicHint.project_id == project_id,
        entities.Core3CommentTopicHint.category_code == batch.category_code,
        entities.Core3CommentTopicHint.batch_id == batch_id,
        entities.Core3CommentTopicHint.sku_code == sku_code,
        entities.Core3CommentTopicHint.is_current.is_(True),
    ]
    if topic_code is not None:
        filters.append(entities.Core3CommentTopicHint.topic_code == topic_code)
    if topic_group is not None:
        filters.append(entities.Core3CommentTopicHint.topic_group == topic_group)
    if polarity_hint is not None:
        filters.append(entities.Core3CommentTopicHint.polarity_hint == polarity_hint)
    if topic_hint_status is not None:
        filters.append(entities.Core3CommentTopicHint.topic_hint_status == topic_hint_status)
    if service_guardrail_flag is not None:
        filters.append(entities.Core3CommentTopicHint.service_guardrail_flag.is_(service_guardrail_flag))
    total = _count_model_rows(db, entities.Core3CommentTopicHint, filters)
    return CommentTopicHintListResponse(
        items=[CommentTopicHintResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=_comment_topic_list_summary_cn(items, total),
    )


@router.post(
    "/projects/{project_id}/batches/{batch_id}/comments/signals/run",
    response_model=Core3ModuleRunResultSchema,
)
def run_comment_downstream_signals(
    project_id: str,
    batch_id: str,
    payload: Core3CommentSignalRunApiRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> Core3ModuleRunResultSchema:
    payload = payload or Core3CommentSignalRunApiRequest()
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = CommentDownstreamSignalReadRepository(_repository_context(db, project_id, batch.category_code))
    try:
        repository.assert_m05_completed(batch_id)
    except M06InputBlockedError as exc:
        raise HTTPException(status_code=409, detail=f"M06 inputs not ready: {exc}") from exc

    context = build_run_context(
        run_id=payload.run_id or f"m06-api-{batch_id}",
        project_id=project_id,
        category_code=payload.category_code,
        batch_id=batch_id,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(
            scope_type=Core3TargetScopeType.CHANGED_SKU,
            sku_codes=payload.sku_scope,
            data_domains=[Core3DataDomain.COMMENT, Core3DataDomain.PROFILE],
            note_cn="M06 评论下游信号抽取手工触发",
        ),
        module_versions={"M06": payload.module_version},
        seed_versions={"M06": payload.seed_version},
        triggered_by=payload.triggered_by,
    )
    target = Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        target_ids=tuple(payload.sku_scope),
        data_domains=(Core3DataDomain.COMMENT, Core3DataDomain.PROFILE),
        metadata={
            "batch_id": batch_id,
            "module_run_id": payload.module_run_id,
            "module_version": payload.module_version,
            "seed_version": payload.seed_version,
            "rule_version": payload.rule_version,
            "force_rebuild": payload.force_rebuild,
            "signal_types": [str(item) for item in payload.signal_types],
            "sku_batch_size": payload.sku_batch_size,
        },
    )
    try:
        result = CommentDownstreamSignalRunner(db).run(context, target)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get(
    "/projects/{project_id}/batches/{batch_id}/comments/signals/profiles",
    response_model=SkuCommentSignalProfileListResponse,
)
def list_sku_comment_signal_profiles(
    project_id: str,
    batch_id: str,
    sku_code: str | None = Query(default=None),
    review_required: bool | None = Query(default=None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> SkuCommentSignalProfileListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = CommentDownstreamSignalReadRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_profiles(
        batch_id,
        sku_code=sku_code,
        review_required=review_required,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuCommentSignalProfile.project_id == project_id,
        entities.Core3SkuCommentSignalProfile.category_code == batch.category_code,
        entities.Core3SkuCommentSignalProfile.batch_id == batch_id,
        entities.Core3SkuCommentSignalProfile.is_current.is_(True),
    ]
    if sku_code is not None:
        filters.append(entities.Core3SkuCommentSignalProfile.sku_code == sku_code)
    if review_required is not None:
        filters.append(entities.Core3SkuCommentSignalProfile.review_required.is_(review_required))
    total = _count_model_rows(db, entities.Core3SkuCommentSignalProfile, filters)
    return SkuCommentSignalProfileListResponse(
        items=[SkuCommentSignalProfileResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=_comment_signal_profile_list_summary_cn(items, total),
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/comments/signals",
    response_model=CommentDownstreamSignalListResponse,
)
def list_comment_downstream_signals(
    project_id: str,
    batch_id: str,
    sku_code: str | None = Query(default=None),
    signal_type: str | None = Query(default=None),
    target_code_hint: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> CommentDownstreamSignalListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = CommentDownstreamSignalReadRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_signals(
        batch_id,
        sku_code=sku_code,
        signal_type=signal_type,
        target_code_hint=target_code_hint,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3CommentDownstreamSignal.project_id == project_id,
        entities.Core3CommentDownstreamSignal.category_code == batch.category_code,
        entities.Core3CommentDownstreamSignal.batch_id == batch_id,
        entities.Core3CommentDownstreamSignal.is_current.is_(True),
    ]
    if sku_code is not None:
        filters.append(entities.Core3CommentDownstreamSignal.sku_code == sku_code)
    if signal_type is not None:
        filters.append(entities.Core3CommentDownstreamSignal.signal_type == signal_type)
    if target_code_hint is not None:
        filters.append(entities.Core3CommentDownstreamSignal.target_code_hint == target_code_hint)
    total = _count_model_rows(db, entities.Core3CommentDownstreamSignal, filters)
    return CommentDownstreamSignalListResponse(
        items=[CommentDownstreamSignalResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=_comment_signal_list_summary_cn(items, total),
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/comments/signals/candidates",
    response_model=CommentSignalCandidateListResponse,
)
def list_comment_signal_candidates(
    project_id: str,
    batch_id: str,
    sku_code: str | None = Query(default=None),
    signal_type: str | None = Query(default=None),
    target_code_hint: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> CommentSignalCandidateListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = CommentDownstreamSignalReadRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_candidates(
        batch_id,
        sku_code=sku_code,
        signal_type=signal_type,
        target_code_hint=target_code_hint,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3CommentSignalCandidate.project_id == project_id,
        entities.Core3CommentSignalCandidate.category_code == batch.category_code,
        entities.Core3CommentSignalCandidate.batch_id == batch_id,
        entities.Core3CommentSignalCandidate.is_current.is_(True),
    ]
    if sku_code is not None:
        filters.append(entities.Core3CommentSignalCandidate.sku_code == sku_code)
    if signal_type is not None:
        filters.append(entities.Core3CommentSignalCandidate.signal_type == signal_type)
    if target_code_hint is not None:
        filters.append(entities.Core3CommentSignalCandidate.target_code_hint == target_code_hint)
    total = _count_model_rows(db, entities.Core3CommentSignalCandidate, filters)
    return CommentSignalCandidateListResponse(
        items=[CommentSignalCandidateResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=_comment_signal_candidate_list_summary_cn(items, total),
    )


@router.post(
    "/projects/{project_id}/batches/{batch_id}/claims/comment-enhancement/run",
    response_model=Core3ModuleRunResultSchema,
)
def run_claim_comment_enhancement(
    project_id: str,
    batch_id: str,
    payload: Core3ClaimCommentEnhancementRunApiRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> Core3ModuleRunResultSchema:
    payload = payload or Core3ClaimCommentEnhancementRunApiRequest()
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = ClaimCommentEnhancementRepository(_repository_context(db, project_id, batch.category_code))
    try:
        repository.assert_m04a_completed(batch_id)
        repository.assert_m06_completed(batch_id)
    except M04bInputBlockedError as exc:
        raise HTTPException(status_code=409, detail=f"M04b inputs not ready: {exc}") from exc

    context = build_run_context(
        run_id=payload.run_id or f"m04b-api-{batch_id}",
        project_id=project_id,
        category_code=payload.category_code,
        batch_id=batch_id,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(
            scope_type=Core3TargetScopeType.CHANGED_SKU,
            sku_codes=payload.sku_scope,
            data_domains=[Core3DataDomain.CLAIM, Core3DataDomain.COMMENT],
            note_cn="M04b 卖点评论验证增强手工触发",
        ),
        module_versions={"M04b": payload.module_version},
        seed_versions={"M04b": payload.seed_version},
        triggered_by=payload.triggered_by,
    )
    target = Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        target_ids=tuple(payload.sku_scope),
        data_domains=(Core3DataDomain.CLAIM, Core3DataDomain.COMMENT),
        metadata={
            "batch_id": batch_id,
            "module_run_id": payload.module_run_id,
            "module_version": payload.module_version,
            "seed_version": payload.seed_version,
            "rule_version": payload.rule_version,
            "force_rebuild": payload.force_rebuild,
            "claim_scope": payload.claim_scope,
        },
    )
    try:
        result = ClaimCommentEnhancementRunner(db).run(context, target)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/claim-activations",
    response_model=SkuClaimActivationListResponse,
)
def list_sku_claim_activations(
    project_id: str,
    batch_id: str,
    sku_code: str,
    claim_code: str | None = Query(default=None),
    activation_level: str | None = Query(default=None),
    activation_basis: str | None = Query(default=None),
    perception_status: str | None = Query(default=None),
    missing_structured_claim_flag: bool | None = Query(default=None),
    param_only_flag: bool | None = Query(default=None),
    comment_only_flag: bool | None = Query(default=None),
    review_required: bool | None = Query(default=None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> SkuClaimActivationListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = ClaimCommentEnhancementRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_activations(
        batch_id,
        sku_code=sku_code,
        claim_code=claim_code,
        activation_level=activation_level,
        activation_basis=activation_basis,
        perception_status=perception_status,
        missing_structured_claim_flag=missing_structured_claim_flag,
        param_only_flag=param_only_flag,
        comment_only_flag=comment_only_flag,
        review_required=review_required,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuClaimActivation.project_id == project_id,
        entities.Core3SkuClaimActivation.category_code == batch.category_code,
        entities.Core3SkuClaimActivation.batch_id == batch_id,
        entities.Core3SkuClaimActivation.sku_code == sku_code,
        entities.Core3SkuClaimActivation.is_current.is_(True),
    ]
    if claim_code is not None:
        filters.append(entities.Core3SkuClaimActivation.claim_code == claim_code)
    if activation_level is not None:
        filters.append(entities.Core3SkuClaimActivation.activation_level == activation_level)
    if activation_basis is not None:
        filters.append(entities.Core3SkuClaimActivation.activation_basis == activation_basis)
    if perception_status is not None:
        filters.append(entities.Core3SkuClaimActivation.perception_status == perception_status)
    if missing_structured_claim_flag is not None:
        filters.append(entities.Core3SkuClaimActivation.missing_structured_claim_flag.is_(missing_structured_claim_flag))
    if param_only_flag is not None:
        filters.append(entities.Core3SkuClaimActivation.param_only_flag.is_(param_only_flag))
    if comment_only_flag is not None:
        filters.append(entities.Core3SkuClaimActivation.comment_only_flag.is_(comment_only_flag))
    if review_required is not None:
        filters.append(entities.Core3SkuClaimActivation.review_required.is_(review_required))
    total = _count_model_rows(db, entities.Core3SkuClaimActivation, filters)
    return SkuClaimActivationListResponse(
        items=[SkuClaimActivationResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=_claim_activation_list_summary_cn(items, total),
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/claim-comment-validations",
    response_model=ClaimCommentValidationListResponse,
)
def list_sku_claim_comment_validations(
    project_id: str,
    batch_id: str,
    sku_code: str,
    claim_code: str | None = Query(default=None),
    comment_effect: str | None = Query(default=None),
    perception_status: str | None = Query(default=None),
    review_required: bool | None = Query(default=None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> ClaimCommentValidationListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = ClaimCommentEnhancementRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_validations(
        batch_id,
        sku_code=sku_code,
        claim_code=claim_code,
        comment_effect=comment_effect,
        perception_status=perception_status,
        review_required=review_required,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuClaimCommentValidation.project_id == project_id,
        entities.Core3SkuClaimCommentValidation.category_code == batch.category_code,
        entities.Core3SkuClaimCommentValidation.batch_id == batch_id,
        entities.Core3SkuClaimCommentValidation.sku_code == sku_code,
        entities.Core3SkuClaimCommentValidation.is_current.is_(True),
    ]
    if claim_code is not None:
        filters.append(entities.Core3SkuClaimCommentValidation.claim_code == claim_code)
    if comment_effect is not None:
        filters.append(entities.Core3SkuClaimCommentValidation.comment_effect == comment_effect)
    if perception_status is not None:
        filters.append(entities.Core3SkuClaimCommentValidation.perception_status == perception_status)
    if review_required is not None:
        filters.append(entities.Core3SkuClaimCommentValidation.review_required.is_(review_required))
    total = _count_model_rows(db, entities.Core3SkuClaimCommentValidation, filters)
    return ClaimCommentValidationListResponse(
        items=[ClaimCommentValidationResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=_claim_validation_list_summary_cn(items, total),
    )


@router.get(
    "/projects/{project_id}/claim-activations/{claim_activation_id}/evidence",
    response_model=ClaimActivationEvidenceResponse,
)
def get_claim_activation_evidence(
    project_id: str,
    claim_activation_id: str,
    db: Session = Depends(get_db),
) -> ClaimActivationEvidenceResponse:
    latest = db.execute(
        select(entities.Core3SkuClaimActivation)
        .where(entities.Core3SkuClaimActivation.project_id == project_id)
        .where(entities.Core3SkuClaimActivation.claim_activation_id == claim_activation_id)
        .where(entities.Core3SkuClaimActivation.is_current.is_(True))
    ).scalars().first()
    if latest is None:
        raise HTTPException(status_code=404, detail="claim activation not found")
    activation = SkuClaimActivationResponse.model_validate(latest, from_attributes=True)
    return ClaimActivationEvidenceResponse(
        claim_activation=activation,
        param_evidence_ids=list(latest.param_evidence_ids or []),
        promo_evidence_ids=list(latest.promo_evidence_ids or []),
        comment_evidence_ids=list(latest.comment_evidence_ids or []),
        comment_signal_ids=list(latest.comment_signal_ids or []),
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/claim-comment-review-issues",
    response_model=ClaimCommentReviewIssueListResponse,
)
def list_claim_comment_review_issues(
    project_id: str,
    batch_id: str,
    sku_code: str | None = Query(default=None),
    claim_code: str | None = Query(default=None),
    issue_type: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    issue_status: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> ClaimCommentReviewIssueListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = ClaimCommentEnhancementRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_issues(
        batch_id,
        sku_code=sku_code,
        claim_code=claim_code,
        issue_type=issue_type,
        severity=severity,
        issue_status=issue_status,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3ClaimCommentReviewIssue.project_id == project_id,
        entities.Core3ClaimCommentReviewIssue.category_code == batch.category_code,
        entities.Core3ClaimCommentReviewIssue.batch_id == batch_id,
        entities.Core3ClaimCommentReviewIssue.is_current.is_(True),
    ]
    if sku_code is not None:
        filters.append(entities.Core3ClaimCommentReviewIssue.sku_code == sku_code)
    if claim_code is not None:
        filters.append(entities.Core3ClaimCommentReviewIssue.claim_code == claim_code)
    if issue_type is not None:
        filters.append(entities.Core3ClaimCommentReviewIssue.issue_type == issue_type)
    if severity is not None:
        filters.append(entities.Core3ClaimCommentReviewIssue.severity == severity)
    if issue_status is not None:
        filters.append(entities.Core3ClaimCommentReviewIssue.issue_status == issue_status)
    total = _count_model_rows(db, entities.Core3ClaimCommentReviewIssue, filters)
    return ClaimCommentReviewIssueListResponse(
        items=[ClaimCommentReviewIssueResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=_claim_comment_issue_list_summary_cn(items, total),
    )


@router.post(
    "/projects/{project_id}/batches/{batch_id}/market/run",
    response_model=Core3ModuleRunResultSchema,
)
def run_market_profile(
    project_id: str,
    batch_id: str,
    payload: Core3MarketProfileRunApiRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> Core3ModuleRunResultSchema:
    payload = payload or Core3MarketProfileRunApiRequest()
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = M07MarketRepository(_repository_context(db, project_id, batch.category_code))
    try:
        repository.assert_inputs_ready(batch_id)
    except M07InputBlockedError as exc:
        raise HTTPException(status_code=409, detail=f"M07 inputs not ready: {exc}") from exc

    context = build_run_context(
        run_id=payload.run_id or f"m07-api-{batch_id}",
        project_id=project_id,
        category_code=payload.category_code,
        batch_id=batch_id,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(
            scope_type=Core3TargetScopeType.CHANGED_SKU,
            sku_codes=payload.sku_scope,
            data_domains=[Core3DataDomain.MARKET, Core3DataDomain.PROFILE],
            note_cn="M07 市场画像与可比池基线手工触发",
        ),
        module_versions={"M07": payload.module_version},
        triggered_by=payload.triggered_by,
    )
    target = Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        target_ids=tuple(payload.sku_scope),
        data_domains=(Core3DataDomain.MARKET, Core3DataDomain.PROFILE),
        metadata={
            "batch_id": batch_id,
            "module_run_id": payload.module_run_id,
            "module_version": payload.module_version,
            "rule_version": payload.rule_version,
            "price_band_rule_version": payload.price_band_rule_version,
            "pool_rule_version": payload.pool_rule_version,
            "analysis_windows": payload.analysis_windows,
            "force_rebuild": payload.force_rebuild,
        },
    )
    try:
        result = MarketProfileRunner(db).run(context, target)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/market-profiles",
    response_model=Core3SkuMarketProfileListResponse,
)
def list_sku_market_profiles(
    project_id: str,
    batch_id: str,
    sku_code: str,
    analysis_window: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SkuMarketProfileListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = M07MarketRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_profiles(
        batch_id,
        sku_code=sku_code,
        analysis_window=analysis_window,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuMarketProfile.project_id == project_id,
        entities.Core3SkuMarketProfile.category_code == batch.category_code,
        entities.Core3SkuMarketProfile.batch_id == batch_id,
        entities.Core3SkuMarketProfile.sku_code == sku_code,
        entities.Core3SkuMarketProfile.is_current.is_(True),
    ]
    if analysis_window is not None:
        filters.append(entities.Core3SkuMarketProfile.analysis_window == analysis_window)
    total = _count_model_rows(db, entities.Core3SkuMarketProfile, filters)
    return Core3SkuMarketProfileListResponse(
        items=[Core3SkuMarketProfileResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=_market_profile_list_summary_cn(items, total),
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/market-signals",
    response_model=Core3MarketSignalListResponse,
)
def list_sku_market_signals(
    project_id: str,
    batch_id: str,
    sku_code: str,
    signal_code: str | None = Query(default=None),
    analysis_window: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3MarketSignalListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = M07MarketRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_signals(
        batch_id,
        sku_code=sku_code,
        signal_code=signal_code,
        analysis_window=analysis_window,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3MarketSignal.project_id == project_id,
        entities.Core3MarketSignal.category_code == batch.category_code,
        entities.Core3MarketSignal.batch_id == batch_id,
        entities.Core3MarketSignal.sku_code == sku_code,
        entities.Core3MarketSignal.is_current.is_(True),
    ]
    if signal_code is not None:
        filters.append(entities.Core3MarketSignal.signal_code == signal_code)
    if analysis_window is not None:
        filters.append(entities.Core3MarketSignal.analysis_window == analysis_window)
    total = _count_model_rows(db, entities.Core3MarketSignal, filters)
    return Core3MarketSignalListResponse(
        items=[Core3MarketSignalResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=_market_signal_list_summary_cn(items, total),
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/comparable-pools",
    response_model=Core3ComparablePoolListResponse,
)
def list_sku_comparable_pools(
    project_id: str,
    batch_id: str,
    sku_code: str,
    pool_type: str | None = Query(default=None),
    analysis_window: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3ComparablePoolListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = M07MarketRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_pools(
        batch_id,
        target_sku_code=sku_code,
        pool_type=pool_type,
        analysis_window=analysis_window,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3ComparablePoolBaseline.project_id == project_id,
        entities.Core3ComparablePoolBaseline.category_code == batch.category_code,
        entities.Core3ComparablePoolBaseline.batch_id == batch_id,
        entities.Core3ComparablePoolBaseline.target_sku_code == sku_code,
        entities.Core3ComparablePoolBaseline.is_current.is_(True),
    ]
    if pool_type is not None:
        filters.append(entities.Core3ComparablePoolBaseline.pool_type == pool_type)
    if analysis_window is not None:
        filters.append(entities.Core3ComparablePoolBaseline.analysis_window == analysis_window)
    total = _count_model_rows(db, entities.Core3ComparablePoolBaseline, filters)
    return Core3ComparablePoolListResponse(
        items=[Core3ComparablePoolResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=_comparable_pool_list_summary_cn(items, total),
    )


@router.get(
    "/projects/{project_id}/market-pools/{pool_id}/members",
    response_model=Core3MarketPoolMemberListResponse,
)
def list_market_pool_members(
    project_id: str,
    pool_id: str,
    target_sku_code: str | None = Query(default=None),
    member_sku_code: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3MarketPoolMemberListResponse:
    pool = db.execute(
        select(entities.Core3ComparablePoolBaseline)
        .where(entities.Core3ComparablePoolBaseline.project_id == project_id)
        .where(entities.Core3ComparablePoolBaseline.pool_id == pool_id)
        .where(entities.Core3ComparablePoolBaseline.is_current.is_(True))
    ).scalars().first()
    if pool is None:
        raise HTTPException(status_code=404, detail="market pool not found")
    repository = M07MarketRepository(_repository_context(db, project_id, pool.category_code))
    items = repository.list_current_members(
        pool.batch_id,
        pool_id=pool_id,
        target_sku_code=target_sku_code,
        member_sku_code=member_sku_code,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3MarketPoolMember.project_id == project_id,
        entities.Core3MarketPoolMember.category_code == pool.category_code,
        entities.Core3MarketPoolMember.batch_id == pool.batch_id,
        entities.Core3MarketPoolMember.pool_id == pool_id,
        entities.Core3MarketPoolMember.is_current.is_(True),
    ]
    if target_sku_code is not None:
        filters.append(entities.Core3MarketPoolMember.target_sku_code == target_sku_code)
    if member_sku_code is not None:
        filters.append(entities.Core3MarketPoolMember.member_sku_code == member_sku_code)
    total = _count_model_rows(db, entities.Core3MarketPoolMember, filters)
    return Core3MarketPoolMemberListResponse(
        items=[Core3MarketPoolMemberResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=_market_pool_member_list_summary_cn(items, total),
    )


@router.post(
    "/projects/{project_id}/batches/{batch_id}/sku-signals/run",
    response_model=Core3ModuleRunResultSchema,
)
def run_sku_signal_profile(
    project_id: str,
    batch_id: str,
    payload: Core3SkuSignalProfileRunApiRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> Core3ModuleRunResultSchema:
    payload = payload or Core3SkuSignalProfileRunApiRequest()
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = M08SkuSignalRepository(_repository_context(db, project_id, batch.category_code))
    try:
        repository.assert_inputs_ready(batch_id)
    except M08InputBlockedError as exc:
        raise HTTPException(status_code=409, detail=f"M08 inputs not ready: {exc}") from exc

    context = build_run_context(
        run_id=payload.run_id or f"m08-api-{batch_id}",
        project_id=project_id,
        category_code=payload.category_code,
        batch_id=batch_id,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(
            scope_type=Core3TargetScopeType.CHANGED_SKU,
            sku_codes=payload.sku_scope,
            data_domains=[Core3DataDomain.PROFILE],
            note_cn="M08 SKU 综合信号画像手工触发",
        ),
        module_versions={"M08": payload.module_version},
        triggered_by=payload.triggered_by,
    )
    target = Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        target_ids=tuple(payload.sku_scope),
        data_domains=(Core3DataDomain.PROFILE,),
        metadata={
            "batch_id": batch_id,
            "module_run_id": payload.module_run_id,
            "module_version": payload.module_version,
            "rule_version": payload.rule_version,
            "feature_version": payload.feature_version,
            "view_schema_version": payload.view_schema_version,
            "force_rebuild": payload.force_rebuild,
        },
    )
    try:
        result = SkuSignalProfileRunner(db).run(context, target)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/sku-signal-profile",
    response_model=Core3SkuSignalProfileListResponse,
)
def list_sku_signal_profiles(
    project_id: str,
    batch_id: str,
    sku_code: str,
    profile_status: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SkuSignalProfileListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = M08SkuSignalRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_profiles(
        batch_id,
        sku_code=sku_code,
        profile_status=profile_status,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuSignalProfile.project_id == project_id,
        entities.Core3SkuSignalProfile.category_code == batch.category_code,
        entities.Core3SkuSignalProfile.batch_id == batch_id,
        entities.Core3SkuSignalProfile.sku_code == sku_code,
        entities.Core3SkuSignalProfile.is_current.is_(True),
    ]
    if profile_status is not None:
        filters.append(entities.Core3SkuSignalProfile.profile_status == profile_status)
    total = _count_model_rows(db, entities.Core3SkuSignalProfile, filters)
    return Core3SkuSignalProfileListResponse(
        items=[Core3SkuSignalProfileResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=_sku_signal_profile_list_summary_cn(items, total),
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/sku-signal-evidence-matrix",
    response_model=Core3SkuSignalEvidenceMatrixListResponse,
)
def list_sku_signal_evidence_matrix(
    project_id: str,
    batch_id: str,
    sku_code: str,
    domain: str | None = Query(default=None),
    missing_flag: bool | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SkuSignalEvidenceMatrixListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = M08SkuSignalRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_matrices(
        batch_id,
        sku_code=sku_code,
        domain=domain,
        missing_flag=missing_flag,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuSignalEvidenceMatrix.project_id == project_id,
        entities.Core3SkuSignalEvidenceMatrix.category_code == batch.category_code,
        entities.Core3SkuSignalEvidenceMatrix.batch_id == batch_id,
        entities.Core3SkuSignalEvidenceMatrix.sku_code == sku_code,
        entities.Core3SkuSignalEvidenceMatrix.is_current.is_(True),
    ]
    if domain is not None:
        filters.append(entities.Core3SkuSignalEvidenceMatrix.domain == domain)
    if missing_flag is not None:
        filters.append(entities.Core3SkuSignalEvidenceMatrix.missing_flag.is_(missing_flag))
    total = _count_model_rows(db, entities.Core3SkuSignalEvidenceMatrix, filters)
    return Core3SkuSignalEvidenceMatrixListResponse(
        items=[Core3SkuSignalEvidenceMatrixResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=_sku_signal_matrix_list_summary_cn(items, total),
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/downstream-feature-views",
    response_model=Core3SkuDownstreamFeatureViewListResponse,
)
def list_sku_downstream_feature_views(
    project_id: str,
    batch_id: str,
    sku_code: str,
    for_module: str | None = Query(default=None),
    ready_for_module: bool | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SkuDownstreamFeatureViewListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = M08SkuSignalRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_views(
        batch_id,
        sku_code=sku_code,
        for_module=for_module,
        ready_for_module=ready_for_module,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuDownstreamFeatureView.project_id == project_id,
        entities.Core3SkuDownstreamFeatureView.category_code == batch.category_code,
        entities.Core3SkuDownstreamFeatureView.batch_id == batch_id,
        entities.Core3SkuDownstreamFeatureView.sku_code == sku_code,
        entities.Core3SkuDownstreamFeatureView.is_current.is_(True),
    ]
    if for_module is not None:
        filters.append(entities.Core3SkuDownstreamFeatureView.for_module == for_module)
    if ready_for_module is not None:
        filters.append(entities.Core3SkuDownstreamFeatureView.ready_for_module.is_(ready_for_module))
    total = _count_model_rows(db, entities.Core3SkuDownstreamFeatureView, filters)
    return Core3SkuDownstreamFeatureViewListResponse(
        items=[Core3SkuDownstreamFeatureViewResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=_sku_downstream_view_list_summary_cn(items, total),
    )


@router.post(
    "/projects/{project_id}/batches/{batch_id}/comment-native-dimensions/run",
    response_model=Core3ModuleRunResultSchema,
)
def run_comment_native_dimensions(
    project_id: str,
    batch_id: str,
    payload: Core3CommentNativeDimensionRunApiRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> Core3ModuleRunResultSchema:
    payload = payload or Core3CommentNativeDimensionRunApiRequest()
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = CommentNativeDimensionRepository(_repository_context(db, project_id, batch.category_code))
    try:
        repository.assert_inputs_ready(batch_id)
    except M084InputBlockedError as exc:
        raise HTTPException(status_code=409, detail=f"M08.4 inputs not ready: {exc}") from exc

    context = build_run_context(
        run_id=payload.run_id or f"m084-api-{batch_id}",
        project_id=project_id,
        category_code=payload.category_code,
        batch_id=batch_id,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(
            scope_type=Core3TargetScopeType.CHANGED_SKU,
            sku_codes=[],
            data_domains=[Core3DataDomain.ONTOLOGY],
            note_cn="M08.4 评论原生业务维度发现手工触发",
        ),
        module_versions={"M08.4": payload.module_version},
        seed_versions={"M08.4": payload.seed_version},
        triggered_by=payload.triggered_by,
    )
    _ensure_manual_pipeline_run_for_context(db, context)
    module_run_id = payload.module_run_id or str(uuid4())
    if db.get(entities.Core3V2ModuleRun, module_run_id) is None:
        _create_initialization_module_run_placeholder(
            db,
            run_id=context.run_id,
            project_id=project_id,
            batch_id=batch_id,
            module_code=Core3ModuleCode.M08_4,
            module_run_id=module_run_id,
        )
    target = Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        target_ids=(),
        data_domains=(Core3DataDomain.ONTOLOGY,),
        metadata={
            "batch_id": batch_id,
            "module_run_id": module_run_id,
            "module_version": payload.module_version,
            "rule_version": payload.rule_version,
            "seed_version": payload.seed_version,
            "force_rebuild": payload.force_rebuild,
        },
    )
    try:
        result = M084CommentNativeDimensionRunner(db).run(context, target)
        _persist_initialization_module_result(
            db,
            run_id=context.run_id,
            project_id=project_id,
            batch_id=batch_id,
            result=result,
            module_run_id=module_run_id,
        )
        _finish_initialization_pipeline_run(db, context.run_id, result)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.post(
    "/projects/{project_id}/batches/{batch_id}/dimension-ontology/run",
    response_model=Core3ModuleRunResultSchema,
)
def run_dimension_ontology(
    project_id: str,
    batch_id: str,
    payload: Core3DimensionOntologyRunApiRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> Core3ModuleRunResultSchema:
    payload = payload or Core3DimensionOntologyRunApiRequest()
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = DimensionOntologyRepository(_repository_context(db, project_id, batch.category_code))
    try:
        repository.assert_inputs_ready(batch_id)
    except M085InputBlockedError as exc:
        raise HTTPException(status_code=409, detail=f"M08.5 inputs not ready: {exc}") from exc

    context = build_run_context(
        run_id=payload.run_id or f"m085-api-{batch_id}",
        project_id=project_id,
        category_code=payload.category_code,
        batch_id=batch_id,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(
            scope_type=Core3TargetScopeType.CHANGED_SKU,
            sku_codes=[],
            data_domains=[Core3DataDomain.ONTOLOGY],
            note_cn="M08.5 业务维度本体校准手工触发",
        ),
        module_versions={"M08.5": payload.module_version},
        triggered_by=payload.triggered_by,
    )
    _ensure_manual_pipeline_run_for_context(db, context)
    target = Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        target_ids=(),
        data_domains=(Core3DataDomain.ONTOLOGY,),
        metadata={
            "batch_id": batch_id,
            "module_run_id": payload.module_run_id,
            "module_version": payload.module_version,
            "rule_version": payload.rule_version,
            "seed_version": payload.seed_version,
            "force_rebuild": payload.force_rebuild,
            "force_new_version": payload.force_new_version,
        },
    )
    try:
        result = M085DimensionOntologyRunner(db).run(context, target)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get(
    "/projects/{project_id}/batches/{batch_id}/dimension-ontology/current",
    response_model=Core3DimensionOntologyVersionResponse,
)
def get_current_dimension_ontology(
    project_id: str,
    batch_id: str,
    db: Session = Depends(get_db),
) -> Core3DimensionOntologyVersionResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = DimensionOntologyRepository(_repository_context(db, project_id, batch.category_code))
    version = repository.get_current_version(batch_id)
    if version is None:
        raise HTTPException(status_code=404, detail="当前批次尚未生成业务维度本体版本。")
    return Core3DimensionOntologyVersionResponse.model_validate(version, from_attributes=True)


@router.get(
    "/projects/{project_id}/batches/{batch_id}/dimension-ontology/{ontology_version_id}/definitions",
    response_model=Core3DimensionDefinitionListResponse,
)
def list_dimension_definitions(
    project_id: str,
    batch_id: str,
    ontology_version_id: str,
    dimension_type: str | None = Query(default=None),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3DimensionDefinitionListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = DimensionOntologyRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_definitions(
        ontology_version_id,
        dimension_type=dimension_type,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3DimensionDefinition.project_id == project_id,
        entities.Core3DimensionDefinition.category_code == batch.category_code,
        entities.Core3DimensionDefinition.batch_id == batch_id,
        entities.Core3DimensionDefinition.ontology_version_id == ontology_version_id,
        entities.Core3DimensionDefinition.is_current.is_(True),
    ]
    if dimension_type is not None:
        filters.append(entities.Core3DimensionDefinition.dimension_type == dimension_type)
    total = _count_model_rows(db, entities.Core3DimensionDefinition, filters)
    return Core3DimensionDefinitionListResponse(
        items=[Core3DimensionDefinitionResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"当前返回 {len(items)} 个业务维度定义，共 {total} 个。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/dimension-ontology/{ontology_version_id}/snapshots",
    response_model=Core3DimensionCandidateSnapshotListResponse,
)
def list_dimension_snapshots(
    project_id: str,
    batch_id: str,
    ontology_version_id: str,
    snapshot_type: str | None = Query(default=None),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3DimensionCandidateSnapshotListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = DimensionOntologyRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_snapshots(
        ontology_version_id,
        snapshot_type=snapshot_type,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3DimensionCandidateSnapshot.project_id == project_id,
        entities.Core3DimensionCandidateSnapshot.category_code == batch.category_code,
        entities.Core3DimensionCandidateSnapshot.batch_id == batch_id,
        entities.Core3DimensionCandidateSnapshot.ontology_version_id == ontology_version_id,
        entities.Core3DimensionCandidateSnapshot.is_current.is_(True),
    ]
    if snapshot_type is not None:
        filters.append(entities.Core3DimensionCandidateSnapshot.snapshot_type == snapshot_type)
    total = _count_model_rows(db, entities.Core3DimensionCandidateSnapshot, filters)
    return Core3DimensionCandidateSnapshotListResponse(
        items=[Core3DimensionCandidateSnapshotResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"当前返回 {len(items)} 个线索/维度快照，共 {total} 个。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/dimension-ontology/{ontology_version_id}/mapping-rules",
    response_model=Core3DimensionMappingRuleListResponse,
)
def list_dimension_mapping_rules(
    project_id: str,
    batch_id: str,
    ontology_version_id: str,
    target_dimension_type: str | None = Query(default=None),
    mapping_level: str | None = Query(default=None),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3DimensionMappingRuleListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = DimensionOntologyRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_mapping_rules(
        ontology_version_id,
        target_dimension_type=target_dimension_type,
        mapping_level=mapping_level,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3DimensionMappingRule.project_id == project_id,
        entities.Core3DimensionMappingRule.category_code == batch.category_code,
        entities.Core3DimensionMappingRule.batch_id == batch_id,
        entities.Core3DimensionMappingRule.ontology_version_id == ontology_version_id,
        entities.Core3DimensionMappingRule.is_current.is_(True),
    ]
    if target_dimension_type is not None:
        filters.append(entities.Core3DimensionMappingRule.target_dimension_type == target_dimension_type)
    if mapping_level is not None:
        filters.append(entities.Core3DimensionMappingRule.mapping_level == mapping_level)
    total = _count_model_rows(db, entities.Core3DimensionMappingRule, filters)
    return Core3DimensionMappingRuleListResponse(
        items=[Core3DimensionMappingRuleResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"当前返回 {len(items)} 条维度映射规则，共 {total} 条。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/dimension-ontology/{ontology_version_id}/issues",
    response_model=Core3DimensionCalibrationIssueListResponse,
)
def list_dimension_calibration_issues(
    project_id: str,
    batch_id: str,
    ontology_version_id: str,
    severity: str | None = Query(default=None),
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3DimensionCalibrationIssueListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = DimensionOntologyRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_issues(
        ontology_version_id,
        severity=severity,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3DimensionCalibrationIssue.project_id == project_id,
        entities.Core3DimensionCalibrationIssue.category_code == batch.category_code,
        entities.Core3DimensionCalibrationIssue.batch_id == batch_id,
        entities.Core3DimensionCalibrationIssue.ontology_version_id == ontology_version_id,
        entities.Core3DimensionCalibrationIssue.is_current.is_(True),
    ]
    if severity is not None:
        filters.append(entities.Core3DimensionCalibrationIssue.severity == severity)
    total = _count_model_rows(db, entities.Core3DimensionCalibrationIssue, filters)
    return Core3DimensionCalibrationIssueListResponse(
        items=[Core3DimensionCalibrationIssueResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"当前返回 {len(items)} 个校准问题，共 {total} 个。",
    )


@router.post(
    "/projects/{project_id}/batches/{batch_id}/user-tasks/run",
    response_model=Core3ModuleRunResultSchema,
)
def run_user_tasks(
    project_id: str,
    batch_id: str,
    payload: Core3UserTaskRunApiRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> Core3ModuleRunResultSchema:
    payload = payload or Core3UserTaskRunApiRequest()
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = M09UserTaskRepository(_repository_context(db, project_id, batch.category_code))
    try:
        repository.assert_inputs_ready(batch_id)
    except M09InputBlockedError as exc:
        raise HTTPException(status_code=409, detail=f"M09 inputs not ready: {exc}") from exc

    context = build_run_context(
        run_id=payload.run_id or f"m09-api-{batch_id}",
        project_id=project_id,
        category_code=payload.category_code,
        batch_id=batch_id,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(
            scope_type=Core3TargetScopeType.CHANGED_SKU,
            sku_codes=payload.sku_scope,
            data_domains=[Core3DataDomain.TASK],
            note_cn="M09 用户任务手工触发",
        ),
        module_versions={"M09": payload.module_version},
        triggered_by=payload.triggered_by,
    )
    _ensure_manual_pipeline_run_for_context(db, context)
    target = Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        target_ids=tuple(payload.sku_scope),
        data_domains=(Core3DataDomain.TASK,),
        metadata={
            "batch_id": batch_id,
            "module_run_id": payload.module_run_id,
            "module_version": payload.module_version,
            "rule_version": payload.rule_version,
            "seed_version": payload.seed_version,
            "force_rebuild": payload.force_rebuild,
        },
    )
    try:
        result = UserTaskRunner(db).run(context, target)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/user-task-candidates",
    response_model=Core3SkuTaskCandidateListResponse,
)
def list_sku_task_candidates(
    project_id: str,
    batch_id: str,
    sku_code: str,
    task_code: str | None = Query(default=None),
    candidate_status: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SkuTaskCandidateListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = M09UserTaskRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_candidates(
        batch_id,
        sku_code=sku_code,
        task_code=task_code,
        candidate_status=candidate_status,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuTaskCandidate.project_id == project_id,
        entities.Core3SkuTaskCandidate.category_code == batch.category_code,
        entities.Core3SkuTaskCandidate.batch_id == batch_id,
        entities.Core3SkuTaskCandidate.sku_code == sku_code,
        entities.Core3SkuTaskCandidate.is_current.is_(True),
    ]
    if task_code is not None:
        filters.append(entities.Core3SkuTaskCandidate.task_code == task_code)
    if candidate_status is not None:
        filters.append(entities.Core3SkuTaskCandidate.candidate_status == candidate_status)
    total = _count_model_rows(db, entities.Core3SkuTaskCandidate, filters)
    return Core3SkuTaskCandidateListResponse(
        items=[Core3SkuTaskCandidateResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"该 SKU 当前生成 {total} 条用户任务候选记录，候选只说明进入任务判断范围，不等于最终竞品结论。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/user-tasks",
    response_model=Core3SkuTaskScoreListResponse,
)
def list_sku_task_scores(
    project_id: str,
    batch_id: str,
    sku_code: str,
    task_code: str | None = Query(default=None),
    relation_level: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SkuTaskScoreListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = M09UserTaskRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_task_scores(
        batch_id,
        sku_code=sku_code,
        task_code=task_code,
        relation_level=relation_level,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuTaskScore.project_id == project_id,
        entities.Core3SkuTaskScore.category_code == batch.category_code,
        entities.Core3SkuTaskScore.batch_id == batch_id,
        entities.Core3SkuTaskScore.sku_code == sku_code,
        entities.Core3SkuTaskScore.is_current.is_(True),
    ]
    if task_code is not None:
        filters.append(entities.Core3SkuTaskScore.task_code == task_code)
    if relation_level is not None:
        filters.append(entities.Core3SkuTaskScore.relation_level == relation_level)
    total = _count_model_rows(db, entities.Core3SkuTaskScore, filters)
    return Core3SkuTaskScoreListResponse(
        items=[Core3SkuTaskScoreResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"该 SKU 当前生成 {total} 条用户任务判断；任务关系来自能力基础、价值表达、用户反馈和市场验证四域证据。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/user-tasks/{task_code}/evidence-breakdown",
    response_model=Core3SkuTaskEvidenceBreakdownListResponse,
)
def list_sku_task_evidence_breakdowns(
    project_id: str,
    batch_id: str,
    sku_code: str,
    task_code: str,
    evidence_domain: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SkuTaskEvidenceBreakdownListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = M09UserTaskRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_breakdowns(
        batch_id,
        sku_code=sku_code,
        task_code=task_code,
        evidence_domain=evidence_domain,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuTaskEvidenceBreakdown.project_id == project_id,
        entities.Core3SkuTaskEvidenceBreakdown.category_code == batch.category_code,
        entities.Core3SkuTaskEvidenceBreakdown.batch_id == batch_id,
        entities.Core3SkuTaskEvidenceBreakdown.sku_code == sku_code,
        entities.Core3SkuTaskEvidenceBreakdown.task_code == task_code,
        entities.Core3SkuTaskEvidenceBreakdown.is_current.is_(True),
    ]
    if evidence_domain is not None:
        filters.append(entities.Core3SkuTaskEvidenceBreakdown.evidence_domain == evidence_domain)
    total = _count_model_rows(db, entities.Core3SkuTaskEvidenceBreakdown, filters)
    return Core3SkuTaskEvidenceBreakdownListResponse(
        items=[Core3SkuTaskEvidenceBreakdownResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"{task_code} 当前有 {total} 条分域证据拆分，用于解释任务判断为何成立或为何需要复核。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/task-review-issues",
    response_model=Core3SkuTaskReviewIssueListResponse,
)
def list_sku_task_review_issues(
    project_id: str,
    batch_id: str,
    sku_code: str | None = Query(default=None),
    task_code: str | None = Query(default=None),
    issue_type: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SkuTaskReviewIssueListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = M09UserTaskRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_review_issues(
        batch_id,
        sku_code=sku_code,
        task_code=task_code,
        issue_type=issue_type,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuTaskReviewIssue.project_id == project_id,
        entities.Core3SkuTaskReviewIssue.category_code == batch.category_code,
        entities.Core3SkuTaskReviewIssue.batch_id == batch_id,
        entities.Core3SkuTaskReviewIssue.is_current.is_(True),
    ]
    if sku_code is not None:
        filters.append(entities.Core3SkuTaskReviewIssue.sku_code == sku_code)
    if task_code is not None:
        filters.append(entities.Core3SkuTaskReviewIssue.task_code == task_code)
    if issue_type is not None:
        filters.append(entities.Core3SkuTaskReviewIssue.issue_type == issue_type)
    total = _count_model_rows(db, entities.Core3SkuTaskReviewIssue, filters)
    return Core3SkuTaskReviewIssueListResponse(
        items=[Core3SkuTaskReviewIssueResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"当前有 {total} 条用户任务复核问题，主要用于标记缺卖点、评论单域、单参数或市场样本限制。",
    )


@router.post(
    "/projects/{project_id}/batches/{batch_id}/target-groups/run",
    response_model=Core3ModuleRunResultSchema,
)
def run_target_groups(
    project_id: str,
    batch_id: str,
    payload: Core3TargetGroupRunApiRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> Core3ModuleRunResultSchema:
    payload = payload or Core3TargetGroupRunApiRequest()
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = M10TargetGroupRepository(_repository_context(db, project_id, batch.category_code))
    try:
        repository.assert_inputs_ready(batch_id)
    except M10InputBlockedError as exc:
        raise HTTPException(status_code=409, detail=f"M10 inputs not ready: {exc}") from exc

    context = build_run_context(
        run_id=payload.run_id or f"m10-api-{batch_id}",
        project_id=project_id,
        category_code=payload.category_code,
        batch_id=batch_id,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(
            scope_type=Core3TargetScopeType.CHANGED_SKU,
            sku_codes=payload.sku_scope,
            data_domains=[Core3DataDomain.TARGET_GROUP],
            note_cn="M10 目标客群手工触发",
        ),
        module_versions={"M10": payload.module_version},
        triggered_by=payload.triggered_by,
    )
    _ensure_manual_pipeline_run_for_context(db, context)
    target = Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        target_ids=tuple(payload.sku_scope),
        data_domains=(Core3DataDomain.TARGET_GROUP,),
        metadata={
            "batch_id": batch_id,
            "module_run_id": payload.module_run_id,
            "module_version": payload.module_version,
            "rule_version": payload.rule_version,
            "seed_version": payload.seed_version,
            "force_rebuild": payload.force_rebuild,
        },
    )
    try:
        result = TargetGroupRunner(db).run(context, target)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/target-group-candidates",
    response_model=Core3SkuTargetGroupCandidateListResponse,
)
def list_sku_target_group_candidates(
    project_id: str,
    batch_id: str,
    sku_code: str,
    target_group_code: str | None = Query(default=None),
    candidate_status: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SkuTargetGroupCandidateListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = M10TargetGroupRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_candidates(
        batch_id,
        sku_code=sku_code,
        target_group_code=target_group_code,
        candidate_status=candidate_status,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuTargetGroupCandidate.project_id == project_id,
        entities.Core3SkuTargetGroupCandidate.category_code == batch.category_code,
        entities.Core3SkuTargetGroupCandidate.batch_id == batch_id,
        entities.Core3SkuTargetGroupCandidate.sku_code == sku_code,
        entities.Core3SkuTargetGroupCandidate.is_current.is_(True),
    ]
    if target_group_code is not None:
        filters.append(entities.Core3SkuTargetGroupCandidate.target_group_code == target_group_code)
    if candidate_status is not None:
        filters.append(entities.Core3SkuTargetGroupCandidate.candidate_status == candidate_status)
    total = _count_model_rows(db, entities.Core3SkuTargetGroupCandidate, filters)
    return Core3SkuTargetGroupCandidateListResponse(
        items=[Core3SkuTargetGroupCandidateResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"该 SKU 当前生成 {total} 条目标客群候选；候选只说明进入客群判断范围，不等于竞品结论。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/target-groups",
    response_model=Core3SkuTargetGroupScoreListResponse,
)
def list_sku_target_group_scores(
    project_id: str,
    batch_id: str,
    sku_code: str,
    target_group_code: str | None = Query(default=None),
    relation_level: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SkuTargetGroupScoreListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = M10TargetGroupRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_scores(
        batch_id,
        sku_code=sku_code,
        target_group_code=target_group_code,
        relation_level=relation_level,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuTargetGroupScore.project_id == project_id,
        entities.Core3SkuTargetGroupScore.category_code == batch.category_code,
        entities.Core3SkuTargetGroupScore.batch_id == batch_id,
        entities.Core3SkuTargetGroupScore.sku_code == sku_code,
        entities.Core3SkuTargetGroupScore.is_current.is_(True),
    ]
    if target_group_code is not None:
        filters.append(entities.Core3SkuTargetGroupScore.target_group_code == target_group_code)
    if relation_level is not None:
        filters.append(entities.Core3SkuTargetGroupScore.relation_level == relation_level)
    total = _count_model_rows(db, entities.Core3SkuTargetGroupScore, filters)
    return Core3SkuTargetGroupScoreListResponse(
        items=[Core3SkuTargetGroupScoreResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"该 SKU 当前生成 {total} 条目标客群判断；客群关系来自购买任务、用户线索、价格渠道和市场验证。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/target-groups/{target_group_code}/evidence-breakdown",
    response_model=Core3SkuTargetGroupEvidenceBreakdownListResponse,
)
def list_sku_target_group_evidence_breakdowns(
    project_id: str,
    batch_id: str,
    sku_code: str,
    target_group_code: str,
    evidence_domain: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SkuTargetGroupEvidenceBreakdownListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = M10TargetGroupRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_breakdowns(
        batch_id,
        sku_code=sku_code,
        target_group_code=target_group_code,
        evidence_domain=evidence_domain,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuTargetGroupEvidenceBreakdown.project_id == project_id,
        entities.Core3SkuTargetGroupEvidenceBreakdown.category_code == batch.category_code,
        entities.Core3SkuTargetGroupEvidenceBreakdown.batch_id == batch_id,
        entities.Core3SkuTargetGroupEvidenceBreakdown.sku_code == sku_code,
        entities.Core3SkuTargetGroupEvidenceBreakdown.target_group_code == target_group_code,
        entities.Core3SkuTargetGroupEvidenceBreakdown.is_current.is_(True),
    ]
    if evidence_domain is not None:
        filters.append(entities.Core3SkuTargetGroupEvidenceBreakdown.evidence_domain == evidence_domain)
    total = _count_model_rows(db, entities.Core3SkuTargetGroupEvidenceBreakdown, filters)
    return Core3SkuTargetGroupEvidenceBreakdownListResponse(
        items=[Core3SkuTargetGroupEvidenceBreakdownResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"{target_group_code} 当前有 {total} 条分域证据拆分，用于解释客群判断为何成立或为何需要复核。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/target-group-review-issues",
    response_model=Core3SkuTargetGroupReviewIssueListResponse,
)
def list_sku_target_group_review_issues(
    project_id: str,
    batch_id: str,
    sku_code: str | None = Query(default=None),
    target_group_code: str | None = Query(default=None),
    issue_type: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SkuTargetGroupReviewIssueListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = M10TargetGroupRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_review_issues(
        batch_id,
        sku_code=sku_code,
        target_group_code=target_group_code,
        issue_type=issue_type,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuTargetGroupReviewIssue.project_id == project_id,
        entities.Core3SkuTargetGroupReviewIssue.category_code == batch.category_code,
        entities.Core3SkuTargetGroupReviewIssue.batch_id == batch_id,
        entities.Core3SkuTargetGroupReviewIssue.is_current.is_(True),
    ]
    if sku_code is not None:
        filters.append(entities.Core3SkuTargetGroupReviewIssue.sku_code == sku_code)
    if target_group_code is not None:
        filters.append(entities.Core3SkuTargetGroupReviewIssue.target_group_code == target_group_code)
    if issue_type is not None:
        filters.append(entities.Core3SkuTargetGroupReviewIssue.issue_type == issue_type)
    total = _count_model_rows(db, entities.Core3SkuTargetGroupReviewIssue, filters)
    return Core3SkuTargetGroupReviewIssueListResponse(
        items=[Core3SkuTargetGroupReviewIssueResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"当前有 {total} 条目标客群复核问题，主要用于标记评论单域、服务单域、价格错位、市场样本限制或源任务降级。",
    )


@router.post(
    "/projects/{project_id}/batches/{batch_id}/battlefields/run",
    response_model=Core3ModuleRunResultSchema,
)
def run_battlefields(
    project_id: str,
    batch_id: str,
    payload: Core3BattlefieldRunApiRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> Core3ModuleRunResultSchema:
    payload = payload or Core3BattlefieldRunApiRequest()
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = M11BattlefieldRepository(_repository_context(db, project_id, batch.category_code))
    try:
        repository.assert_inputs_ready(batch_id)
    except M11InputBlockedError as exc:
        raise HTTPException(status_code=409, detail=f"M11 inputs not ready: {exc}") from exc

    context = build_run_context(
        run_id=payload.run_id or f"m11-api-{batch_id}",
        project_id=project_id,
        category_code=payload.category_code,
        batch_id=batch_id,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(
            scope_type=Core3TargetScopeType.CHANGED_SKU,
            sku_codes=payload.sku_scope,
            data_domains=[Core3DataDomain.BATTLEFIELD],
            note_cn="M11 价值战场手工触发",
        ),
        module_versions={"M11": payload.module_version},
        triggered_by=payload.triggered_by,
    )
    _ensure_manual_pipeline_run_for_context(db, context)
    target = Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        target_ids=tuple(payload.sku_scope),
        data_domains=(Core3DataDomain.BATTLEFIELD,),
        metadata={
            "batch_id": batch_id,
            "module_run_id": payload.module_run_id,
            "module_version": payload.module_version,
            "rule_version": payload.rule_version,
            "seed_version": payload.seed_version,
            "force_rebuild": payload.force_rebuild,
        },
    )
    try:
        result = BattlefieldRunner(db).run(context, target)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/battlefield-candidates",
    response_model=Core3SkuBattlefieldCandidateListResponse,
)
def list_sku_battlefield_candidates(
    project_id: str,
    batch_id: str,
    sku_code: str,
    battlefield_code: str | None = Query(default=None),
    candidate_status: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SkuBattlefieldCandidateListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = M11BattlefieldRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_candidates(
        batch_id,
        sku_code=sku_code,
        battlefield_code=battlefield_code,
        candidate_status=candidate_status,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuBattlefieldCandidate.project_id == project_id,
        entities.Core3SkuBattlefieldCandidate.category_code == batch.category_code,
        entities.Core3SkuBattlefieldCandidate.batch_id == batch_id,
        entities.Core3SkuBattlefieldCandidate.sku_code == sku_code,
        entities.Core3SkuBattlefieldCandidate.is_current.is_(True),
    ]
    if battlefield_code is not None:
        filters.append(entities.Core3SkuBattlefieldCandidate.battlefield_code == battlefield_code)
    if candidate_status is not None:
        filters.append(entities.Core3SkuBattlefieldCandidate.candidate_status == candidate_status)
    total = _count_model_rows(db, entities.Core3SkuBattlefieldCandidate, filters)
    return Core3SkuBattlefieldCandidateListResponse(
        items=[Core3SkuBattlefieldCandidateResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"该 SKU 当前生成 {total} 条价值战场候选；候选只说明进入战场判断范围，不等于竞品结论。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/battlefields",
    response_model=Core3SkuBattlefieldScoreListResponse,
)
def list_sku_battlefield_scores(
    project_id: str,
    batch_id: str,
    sku_code: str,
    battlefield_code: str | None = Query(default=None),
    relation_level: str | None = Query(default=None),
    competitor_selection_role: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SkuBattlefieldScoreListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = M11BattlefieldRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_scores(
        batch_id,
        sku_code=sku_code,
        battlefield_code=battlefield_code,
        relation_level=relation_level,
        competitor_selection_role=competitor_selection_role,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuBattlefieldScore.project_id == project_id,
        entities.Core3SkuBattlefieldScore.category_code == batch.category_code,
        entities.Core3SkuBattlefieldScore.batch_id == batch_id,
        entities.Core3SkuBattlefieldScore.sku_code == sku_code,
        entities.Core3SkuBattlefieldScore.is_current.is_(True),
    ]
    if battlefield_code is not None:
        filters.append(entities.Core3SkuBattlefieldScore.battlefield_code == battlefield_code)
    if relation_level is not None:
        filters.append(entities.Core3SkuBattlefieldScore.relation_level == relation_level)
    if competitor_selection_role is not None:
        filters.append(entities.Core3SkuBattlefieldScore.competitor_selection_role == competitor_selection_role)
    total = _count_model_rows(db, entities.Core3SkuBattlefieldScore, filters)
    return Core3SkuBattlefieldScoreListResponse(
        items=[Core3SkuBattlefieldScoreResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"该 SKU 当前生成 {total} 条价值战场判断；战场关系来自任务、客群、卖点、参数、评论和市场验证。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/battlefields/{battlefield_code}/evidence-breakdown",
    response_model=Core3SkuBattlefieldEvidenceBreakdownListResponse,
)
def list_sku_battlefield_evidence_breakdowns(
    project_id: str,
    batch_id: str,
    sku_code: str,
    battlefield_code: str,
    evidence_domain: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SkuBattlefieldEvidenceBreakdownListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = M11BattlefieldRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_breakdowns(
        batch_id,
        sku_code=sku_code,
        battlefield_code=battlefield_code,
        evidence_domain=evidence_domain,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuBattlefieldEvidenceBreakdown.project_id == project_id,
        entities.Core3SkuBattlefieldEvidenceBreakdown.category_code == batch.category_code,
        entities.Core3SkuBattlefieldEvidenceBreakdown.batch_id == batch_id,
        entities.Core3SkuBattlefieldEvidenceBreakdown.sku_code == sku_code,
        entities.Core3SkuBattlefieldEvidenceBreakdown.battlefield_code == battlefield_code,
        entities.Core3SkuBattlefieldEvidenceBreakdown.is_current.is_(True),
    ]
    if evidence_domain is not None:
        filters.append(entities.Core3SkuBattlefieldEvidenceBreakdown.evidence_domain == evidence_domain)
    total = _count_model_rows(db, entities.Core3SkuBattlefieldEvidenceBreakdown, filters)
    return Core3SkuBattlefieldEvidenceBreakdownListResponse(
        items=[Core3SkuBattlefieldEvidenceBreakdownResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"{battlefield_code} 当前有 {total} 条分域证据拆分，用于解释为什么属于该战场或为何需要复核。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/battlefield-portfolio",
    response_model=Core3SkuBattlefieldPortfolioListResponse,
)
def list_sku_battlefield_portfolios(
    project_id: str,
    batch_id: str,
    sku_code: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SkuBattlefieldPortfolioListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = M11BattlefieldRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_portfolios(batch_id, sku_code=sku_code, limit=limit, offset=offset)
    filters = [
        entities.Core3SkuBattlefieldPortfolio.project_id == project_id,
        entities.Core3SkuBattlefieldPortfolio.category_code == batch.category_code,
        entities.Core3SkuBattlefieldPortfolio.batch_id == batch_id,
        entities.Core3SkuBattlefieldPortfolio.sku_code == sku_code,
        entities.Core3SkuBattlefieldPortfolio.is_current.is_(True),
    ]
    total = _count_model_rows(db, entities.Core3SkuBattlefieldPortfolio, filters)
    return Core3SkuBattlefieldPortfolioListResponse(
        items=[Core3SkuBattlefieldPortfolioResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"该 SKU 当前生成 {total} 条战场组合摘要，用于后续候选召回和竞品解释。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/battlefield-review-issues",
    response_model=Core3SkuBattlefieldReviewIssueListResponse,
)
def list_sku_battlefield_review_issues(
    project_id: str,
    batch_id: str,
    sku_code: str | None = Query(default=None),
    battlefield_code: str | None = Query(default=None),
    issue_type: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SkuBattlefieldReviewIssueListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = M11BattlefieldRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_review_issues(
        batch_id,
        sku_code=sku_code,
        battlefield_code=battlefield_code,
        issue_type=issue_type,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuBattlefieldReviewIssue.project_id == project_id,
        entities.Core3SkuBattlefieldReviewIssue.category_code == batch.category_code,
        entities.Core3SkuBattlefieldReviewIssue.batch_id == batch_id,
        entities.Core3SkuBattlefieldReviewIssue.is_current.is_(True),
    ]
    if sku_code is not None:
        filters.append(entities.Core3SkuBattlefieldReviewIssue.sku_code == sku_code)
    if battlefield_code is not None:
        filters.append(entities.Core3SkuBattlefieldReviewIssue.battlefield_code == battlefield_code)
    if issue_type is not None:
        filters.append(entities.Core3SkuBattlefieldReviewIssue.issue_type == issue_type)
    total = _count_model_rows(db, entities.Core3SkuBattlefieldReviewIssue, filters)
    return Core3SkuBattlefieldReviewIssueListResponse(
        items=[Core3SkuBattlefieldReviewIssueResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"当前有 {total} 条价值战场复核问题，主要用于标记评论单域、服务单域、市场样本限制或上游任务/客群降级。",
    )


@router.post(
    "/projects/{project_id}/batches/{batch_id}/claim-value-layers/run",
    response_model=Core3ModuleRunResultSchema,
)
def run_claim_value_layers(
    project_id: str,
    batch_id: str,
    payload: Core3ClaimValueLayerRunApiRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> Core3ModuleRunResultSchema:
    payload = payload or Core3ClaimValueLayerRunApiRequest()
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = ClaimValueLayerRepository(_repository_context(db, project_id, batch.category_code))
    try:
        repository.assert_inputs_ready(batch_id)
    except M115InputBlockedError as exc:
        raise HTTPException(status_code=409, detail=f"M11.5 inputs not ready: {exc}") from exc

    context = build_run_context(
        run_id=payload.run_id or f"m115-api-{batch_id}",
        project_id=project_id,
        category_code=payload.category_code,
        batch_id=batch_id,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(
            scope_type=Core3TargetScopeType.CHANGED_SKU,
            sku_codes=payload.sku_scope,
            data_domains=[Core3DataDomain.CLAIM_VALUE],
            note_cn="M11.5 战场内卖点价值分层手工触发",
        ),
        module_versions={"M11.5": payload.module_version},
        triggered_by=payload.triggered_by,
    )
    _ensure_manual_pipeline_run_for_context(db, context)
    target = Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        target_ids=tuple(payload.sku_scope),
        data_domains=(Core3DataDomain.CLAIM_VALUE,),
        metadata={
            "batch_id": batch_id,
            "module_run_id": payload.module_run_id,
            "module_version": payload.module_version,
            "rule_version": payload.rule_version,
            "claim_seed_version": payload.claim_seed_version,
            "battlefield_seed_version": payload.battlefield_seed_version,
            "force_rebuild": payload.force_rebuild,
        },
    )
    try:
        result = ClaimValueLayerRunner(db).run(context, target)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/battlefields/{battlefield_code}/claim-value-candidates",
    response_model=Core3SkuBattlefieldClaimCandidateListResponse,
)
def list_sku_battlefield_claim_candidates(
    project_id: str,
    batch_id: str,
    sku_code: str,
    battlefield_code: str,
    claim_code: str | None = Query(default=None),
    candidate_status: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SkuBattlefieldClaimCandidateListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = ClaimValueLayerRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_candidates(
        batch_id,
        sku_code=sku_code,
        battlefield_code=battlefield_code,
        claim_code=claim_code,
        candidate_status=candidate_status,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuBattlefieldClaimCandidate.project_id == project_id,
        entities.Core3SkuBattlefieldClaimCandidate.category_code == batch.category_code,
        entities.Core3SkuBattlefieldClaimCandidate.batch_id == batch_id,
        entities.Core3SkuBattlefieldClaimCandidate.sku_code == sku_code,
        entities.Core3SkuBattlefieldClaimCandidate.battlefield_code == battlefield_code,
        entities.Core3SkuBattlefieldClaimCandidate.is_current.is_(True),
    ]
    if claim_code is not None:
        filters.append(entities.Core3SkuBattlefieldClaimCandidate.claim_code == claim_code)
    if candidate_status is not None:
        filters.append(entities.Core3SkuBattlefieldClaimCandidate.candidate_status == candidate_status)
    total = _count_model_rows(db, entities.Core3SkuBattlefieldClaimCandidate, filters)
    return Core3SkuBattlefieldClaimCandidateListResponse(
        items=[Core3SkuBattlefieldClaimCandidateResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"{sku_code} 在 {battlefield_code} 当前有 {total} 个卖点候选进入战场内价值分层，候选不是竞品结论。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/battlefields/{battlefield_code}/claim-value-layers",
    response_model=Core3SkuClaimValueLayerListResponse,
)
def list_sku_claim_value_layers(
    project_id: str,
    batch_id: str,
    sku_code: str,
    battlefield_code: str,
    claim_code: str | None = Query(default=None),
    layer: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SkuClaimValueLayerListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = ClaimValueLayerRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_layers(
        batch_id,
        sku_code=sku_code,
        battlefield_code=battlefield_code,
        claim_code=claim_code,
        layer=layer,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuClaimValueLayer.project_id == project_id,
        entities.Core3SkuClaimValueLayer.category_code == batch.category_code,
        entities.Core3SkuClaimValueLayer.batch_id == batch_id,
        entities.Core3SkuClaimValueLayer.sku_code == sku_code,
        entities.Core3SkuClaimValueLayer.battlefield_code == battlefield_code,
        entities.Core3SkuClaimValueLayer.is_current.is_(True),
    ]
    if claim_code is not None:
        filters.append(entities.Core3SkuClaimValueLayer.claim_code == claim_code)
    if layer is not None:
        filters.append(entities.Core3SkuClaimValueLayer.layer == layer)
    total = _count_model_rows(db, entities.Core3SkuClaimValueLayer, filters)
    return Core3SkuClaimValueLayerListResponse(
        items=[Core3SkuClaimValueLayerResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"{sku_code} 在 {battlefield_code} 当前有 {total} 个战场内卖点价值分层结果，可供 M12-M15 消费。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/battlefields/{battlefield_code}/claim-value-layers/{claim_code}/evidence-breakdown",
    response_model=Core3SkuClaimValueEvidenceBreakdownListResponse,
)
def list_sku_claim_value_evidence_breakdowns(
    project_id: str,
    batch_id: str,
    sku_code: str,
    battlefield_code: str,
    claim_code: str,
    evidence_domain: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SkuClaimValueEvidenceBreakdownListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = ClaimValueLayerRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_breakdowns(
        batch_id,
        sku_code=sku_code,
        battlefield_code=battlefield_code,
        claim_code=claim_code,
        evidence_domain=evidence_domain,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuClaimValueEvidenceBreakdown.project_id == project_id,
        entities.Core3SkuClaimValueEvidenceBreakdown.category_code == batch.category_code,
        entities.Core3SkuClaimValueEvidenceBreakdown.batch_id == batch_id,
        entities.Core3SkuClaimValueEvidenceBreakdown.sku_code == sku_code,
        entities.Core3SkuClaimValueEvidenceBreakdown.battlefield_code == battlefield_code,
        entities.Core3SkuClaimValueEvidenceBreakdown.claim_code == claim_code,
        entities.Core3SkuClaimValueEvidenceBreakdown.is_current.is_(True),
    ]
    if evidence_domain is not None:
        filters.append(entities.Core3SkuClaimValueEvidenceBreakdown.evidence_domain == evidence_domain)
    total = _count_model_rows(db, entities.Core3SkuClaimValueEvidenceBreakdown, filters)
    return Core3SkuClaimValueEvidenceBreakdownListResponse(
        items=[Core3SkuClaimValueEvidenceBreakdownResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"{claim_code} 当前有 {total} 条卖点价值分域证据拆分，用于解释分层结论是否站得住。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/battlefields/{battlefield_code}/claim-value-summary",
    response_model=Core3SkuBattlefieldClaimValueSummaryListResponse,
)
def list_sku_battlefield_claim_value_summaries(
    project_id: str,
    batch_id: str,
    sku_code: str,
    battlefield_code: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SkuBattlefieldClaimValueSummaryListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = ClaimValueLayerRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_summaries(
        batch_id,
        sku_code=sku_code,
        battlefield_code=battlefield_code,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuBattlefieldClaimValueSummary.project_id == project_id,
        entities.Core3SkuBattlefieldClaimValueSummary.category_code == batch.category_code,
        entities.Core3SkuBattlefieldClaimValueSummary.batch_id == batch_id,
        entities.Core3SkuBattlefieldClaimValueSummary.sku_code == sku_code,
        entities.Core3SkuBattlefieldClaimValueSummary.battlefield_code == battlefield_code,
        entities.Core3SkuBattlefieldClaimValueSummary.is_current.is_(True),
    ]
    total = _count_model_rows(db, entities.Core3SkuBattlefieldClaimValueSummary, filters)
    return Core3SkuBattlefieldClaimValueSummaryListResponse(
        items=[Core3SkuBattlefieldClaimValueSummaryResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"{sku_code} 在 {battlefield_code} 当前有 {total} 条战场内卖点组合摘要，用于下游候选召回、评分和报告解释。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/claim-value-review-issues",
    response_model=Core3SkuClaimValueReviewIssueListResponse,
)
def list_sku_claim_value_review_issues(
    project_id: str,
    batch_id: str,
    sku_code: str | None = Query(default=None),
    battlefield_code: str | None = Query(default=None),
    claim_code: str | None = Query(default=None),
    issue_type: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SkuClaimValueReviewIssueListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = ClaimValueLayerRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_review_issues(
        batch_id,
        sku_code=sku_code,
        battlefield_code=battlefield_code,
        claim_code=claim_code,
        issue_type=issue_type,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuClaimValueReviewIssue.project_id == project_id,
        entities.Core3SkuClaimValueReviewIssue.category_code == batch.category_code,
        entities.Core3SkuClaimValueReviewIssue.batch_id == batch_id,
        entities.Core3SkuClaimValueReviewIssue.is_current.is_(True),
    ]
    if sku_code is not None:
        filters.append(entities.Core3SkuClaimValueReviewIssue.sku_code == sku_code)
    if battlefield_code is not None:
        filters.append(entities.Core3SkuClaimValueReviewIssue.battlefield_code == battlefield_code)
    if claim_code is not None:
        filters.append(entities.Core3SkuClaimValueReviewIssue.claim_code == claim_code)
    if issue_type is not None:
        filters.append(entities.Core3SkuClaimValueReviewIssue.issue_type == issue_type)
    total = _count_model_rows(db, entities.Core3SkuClaimValueReviewIssue, filters)
    return Core3SkuClaimValueReviewIssueListResponse(
        items=[Core3SkuClaimValueReviewIssueResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"当前有 {total} 条战场内卖点价值复核问题，主要来自样本不足、宣传/评论缺口或服务卖点边界。",
    )


@router.post(
    "/projects/{project_id}/batches/{batch_id}/sku-business-profiles/run",
    response_model=Core3ModuleRunResultSchema,
)
def run_sku_business_profiles(
    project_id: str,
    batch_id: str,
    payload: Core3SkuBusinessProfileRunApiRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> Core3ModuleRunResultSchema:
    payload = payload or Core3SkuBusinessProfileRunApiRequest()
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = SkuBusinessProfileRepository(_repository_context(db, project_id, batch.category_code))
    try:
        repository.assert_inputs_ready(batch_id)
    except M116InputBlockedError as exc:
        raise HTTPException(status_code=409, detail=f"M11.6 inputs not ready: {exc}") from exc

    context = build_run_context(
        run_id=payload.run_id or f"m116-api-{batch_id}",
        project_id=project_id,
        category_code=payload.category_code,
        batch_id=batch_id,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(
            scope_type=Core3TargetScopeType.CHANGED_SKU,
            sku_codes=payload.sku_scope,
            data_domains=[
                Core3DataDomain.PROFILE,
                Core3DataDomain.MARKET,
                Core3DataDomain.TASK,
                Core3DataDomain.TARGET_GROUP,
                Core3DataDomain.BATTLEFIELD,
                Core3DataDomain.CLAIM_VALUE,
            ],
            note_cn="M11.6 SKU 业务画像聚合手工触发",
        ),
        module_versions={"M11.6": payload.module_version},
        triggered_by=payload.triggered_by,
    )
    _ensure_manual_pipeline_run_for_context(db, context)
    target = Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        target_ids=tuple(payload.sku_scope),
        data_domains=(
            Core3DataDomain.PROFILE,
            Core3DataDomain.MARKET,
            Core3DataDomain.TASK,
            Core3DataDomain.TARGET_GROUP,
            Core3DataDomain.BATTLEFIELD,
            Core3DataDomain.CLAIM_VALUE,
        ),
        metadata={
            "batch_id": batch_id,
            "module_run_id": payload.module_run_id,
            "module_version": payload.module_version,
            "rule_version": payload.rule_version,
            "force_rebuild": payload.force_rebuild,
        },
    )
    try:
        result = SkuBusinessProfileRunner(db).run(context, target)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get(
    "/projects/{project_id}/batches/{batch_id}/sku-business-profiles",
    response_model=Core3SkuBusinessProfileListResponse,
)
def list_sku_business_profiles(
    project_id: str,
    batch_id: str,
    sku_code: str | None = Query(default=None),
    market_role: str | None = Query(default=None),
    premium_type: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SkuBusinessProfileListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = SkuBusinessProfileRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_profiles(
        batch_id,
        sku_code=sku_code,
        market_role=market_role,
        premium_type=premium_type,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuBusinessProfile.project_id == project_id,
        entities.Core3SkuBusinessProfile.category_code == batch.category_code,
        entities.Core3SkuBusinessProfile.batch_id == batch_id,
        entities.Core3SkuBusinessProfile.is_current.is_(True),
    ]
    if sku_code is not None:
        filters.append(entities.Core3SkuBusinessProfile.sku_code == sku_code)
    if market_role is not None:
        filters.append(entities.Core3SkuBusinessProfile.market_role == market_role)
    if premium_type is not None:
        filters.append(entities.Core3SkuBusinessProfile.premium_type == premium_type)
    total = _count_model_rows(db, entities.Core3SkuBusinessProfile, filters)
    return Core3SkuBusinessProfileListResponse(
        items=[Core3SkuBusinessProfileResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"当前批次有 {total} 个 SKU 业务画像；该层解释 SKU 定位、卖点价值、溢价和主战场，不输出核心竞品。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/business-profile",
    response_model=Core3SkuBusinessProfileListResponse,
)
def get_sku_business_profile(
    project_id: str,
    batch_id: str,
    sku_code: str,
    db: Session = Depends(get_db),
) -> Core3SkuBusinessProfileListResponse:
    return list_sku_business_profiles(
        project_id,
        batch_id,
        sku_code=sku_code,
        market_role=None,
        premium_type=None,
        limit=10,
        offset=0,
        db=db,
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/business-profile-dimensions",
    response_model=Core3SkuBusinessProfileDimensionListResponse,
)
def list_sku_business_profile_dimensions(
    project_id: str,
    batch_id: str,
    sku_code: str,
    dimension_type: str | None = Query(default=None),
    dimension_code: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SkuBusinessProfileDimensionListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = SkuBusinessProfileRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_dimensions(
        batch_id,
        sku_code=sku_code,
        dimension_type=dimension_type,
        dimension_code=dimension_code,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuBusinessProfileDimension.project_id == project_id,
        entities.Core3SkuBusinessProfileDimension.category_code == batch.category_code,
        entities.Core3SkuBusinessProfileDimension.batch_id == batch_id,
        entities.Core3SkuBusinessProfileDimension.sku_code == sku_code,
        entities.Core3SkuBusinessProfileDimension.is_current.is_(True),
    ]
    if dimension_type is not None:
        filters.append(entities.Core3SkuBusinessProfileDimension.dimension_type == dimension_type)
    if dimension_code is not None:
        filters.append(entities.Core3SkuBusinessProfileDimension.dimension_code == dimension_code)
    total = _count_model_rows(db, entities.Core3SkuBusinessProfileDimension, filters)
    return Core3SkuBusinessProfileDimensionListResponse(
        items=[Core3SkuBusinessProfileDimensionResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"{sku_code} 当前有 {total} 条画像维度权重，覆盖卖点、任务、客群和价值战场。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{sku_code}/business-profile-sales-allocation",
    response_model=Core3SkuBusinessProfileSalesAllocationListResponse,
)
def list_sku_business_profile_sales_allocations(
    project_id: str,
    batch_id: str,
    sku_code: str,
    dimension_type: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SkuBusinessProfileSalesAllocationListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = SkuBusinessProfileRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_allocations(
        batch_id,
        sku_code=sku_code,
        dimension_type=dimension_type,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuBusinessProfileSalesAllocation.project_id == project_id,
        entities.Core3SkuBusinessProfileSalesAllocation.category_code == batch.category_code,
        entities.Core3SkuBusinessProfileSalesAllocation.batch_id == batch_id,
        entities.Core3SkuBusinessProfileSalesAllocation.sku_code == sku_code,
        entities.Core3SkuBusinessProfileSalesAllocation.is_current.is_(True),
    ]
    if dimension_type is not None:
        filters.append(entities.Core3SkuBusinessProfileSalesAllocation.dimension_type == dimension_type)
    total = _count_model_rows(db, entities.Core3SkuBusinessProfileSalesAllocation, filters)
    return Core3SkuBusinessProfileSalesAllocationListResponse(
        items=[Core3SkuBusinessProfileSalesAllocationResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"{sku_code} 当前有 {total} 条 SKU 内销量分配结果；全局口径守恒由后续独立对账模块处理。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/business-profile-review-issues",
    response_model=Core3SkuBusinessProfileReviewIssueListResponse,
)
def list_sku_business_profile_review_issues(
    project_id: str,
    batch_id: str,
    sku_code: str | None = Query(default=None),
    issue_type: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3SkuBusinessProfileReviewIssueListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = SkuBusinessProfileRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_review_issues(
        batch_id,
        sku_code=sku_code,
        issue_type=issue_type,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3SkuBusinessProfileReviewIssue.project_id == project_id,
        entities.Core3SkuBusinessProfileReviewIssue.category_code == batch.category_code,
        entities.Core3SkuBusinessProfileReviewIssue.batch_id == batch_id,
        entities.Core3SkuBusinessProfileReviewIssue.is_current.is_(True),
    ]
    if sku_code is not None:
        filters.append(entities.Core3SkuBusinessProfileReviewIssue.sku_code == sku_code)
    if issue_type is not None:
        filters.append(entities.Core3SkuBusinessProfileReviewIssue.issue_type == issue_type)
    total = _count_model_rows(db, entities.Core3SkuBusinessProfileReviewIssue, filters)
    return Core3SkuBusinessProfileReviewIssueListResponse(
        items=[Core3SkuBusinessProfileReviewIssueResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"当前有 {total} 条 SKU 业务画像复核问题，主要来自量价缺失或画像维度证据不足。",
    )


@router.post(
    "/projects/{project_id}/batches/{batch_id}/dimension-sales-reconciliation/run",
    response_model=Core3ModuleRunResultSchema,
)
def run_dimension_sales_reconciliation(
    project_id: str,
    batch_id: str,
    payload: Core3DimensionSalesReconciliationRunApiRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> Core3ModuleRunResultSchema:
    payload = payload or Core3DimensionSalesReconciliationRunApiRequest()
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = DimensionSalesReconciliationRepository(_repository_context(db, project_id, batch.category_code))
    try:
        repository.assert_inputs_ready(batch_id)
    except M117InputBlockedError as exc:
        raise HTTPException(status_code=409, detail=f"M11.7 inputs not ready: {exc}") from exc

    context = build_run_context(
        run_id=payload.run_id or f"m117-api-{batch_id}",
        project_id=project_id,
        category_code=payload.category_code,
        batch_id=batch_id,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(
            scope_type=Core3TargetScopeType.CHANGED_SKU,
            sku_codes=payload.sku_scope,
            data_domains=[
                Core3DataDomain.PROFILE,
                Core3DataDomain.MARKET,
                Core3DataDomain.TASK,
                Core3DataDomain.TARGET_GROUP,
                Core3DataDomain.BATTLEFIELD,
                Core3DataDomain.CLAIM_VALUE,
            ],
            note_cn="M11.7 销量分配对账手工触发",
        ),
        module_versions={"M11.7": payload.module_version},
        triggered_by=payload.triggered_by,
    )
    _ensure_manual_pipeline_run_for_context(db, context)
    target = Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        target_ids=tuple(payload.sku_scope),
        data_domains=(
            Core3DataDomain.PROFILE,
            Core3DataDomain.MARKET,
            Core3DataDomain.TASK,
            Core3DataDomain.TARGET_GROUP,
            Core3DataDomain.BATTLEFIELD,
            Core3DataDomain.CLAIM_VALUE,
        ),
        metadata={
            "batch_id": batch_id,
            "module_run_id": payload.module_run_id,
            "module_version": payload.module_version,
            "rule_version": payload.rule_version,
            "force_rebuild": payload.force_rebuild,
        },
    )
    try:
        result = DimensionSalesReconciliationRunner(db).run(context, target)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get(
    "/projects/{project_id}/batches/{batch_id}/dimension-sales-summary",
    response_model=Core3BusinessDimensionSalesSummaryListResponse,
)
def list_dimension_sales_summaries(
    project_id: str,
    batch_id: str,
    dimension_type: str | None = Query(default=None),
    dimension_code: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3BusinessDimensionSalesSummaryListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = DimensionSalesReconciliationRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_summaries(
        batch_id,
        dimension_type=dimension_type,
        dimension_code=dimension_code,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3BusinessDimensionSalesSummary.project_id == project_id,
        entities.Core3BusinessDimensionSalesSummary.category_code == batch.category_code,
        entities.Core3BusinessDimensionSalesSummary.batch_id == batch_id,
        entities.Core3BusinessDimensionSalesSummary.is_current.is_(True),
    ]
    if dimension_type is not None:
        filters.append(entities.Core3BusinessDimensionSalesSummary.dimension_type == dimension_type)
    if dimension_code is not None:
        filters.append(entities.Core3BusinessDimensionSalesSummary.dimension_code == dimension_code)
    total = _count_model_rows(db, entities.Core3BusinessDimensionSalesSummary, filters)
    return Core3BusinessDimensionSalesSummaryListResponse(
        items=[Core3BusinessDimensionSalesSummaryResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"当前有 {total} 条维度销量结构汇总，用于检查卖点、任务、客群和战场的销量口径是否闭合。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/dimension-sales-summary/{dimension_type}/{dimension_code}/sku-contributions",
    response_model=Core3BusinessDimensionSkuContributionListResponse,
)
def list_dimension_sku_contributions(
    project_id: str,
    batch_id: str,
    dimension_type: str,
    dimension_code: str,
    sku_code: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3BusinessDimensionSkuContributionListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = DimensionSalesReconciliationRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_contributions(
        batch_id,
        dimension_type=dimension_type,
        dimension_code=dimension_code,
        sku_code=sku_code,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3BusinessDimensionSkuContribution.project_id == project_id,
        entities.Core3BusinessDimensionSkuContribution.category_code == batch.category_code,
        entities.Core3BusinessDimensionSkuContribution.batch_id == batch_id,
        entities.Core3BusinessDimensionSkuContribution.dimension_type == dimension_type,
        entities.Core3BusinessDimensionSkuContribution.dimension_code == dimension_code,
        entities.Core3BusinessDimensionSkuContribution.is_current.is_(True),
    ]
    if sku_code is not None:
        filters.append(entities.Core3BusinessDimensionSkuContribution.sku_code == sku_code)
    total = _count_model_rows(db, entities.Core3BusinessDimensionSkuContribution, filters)
    return Core3BusinessDimensionSkuContributionListResponse(
        items=[Core3BusinessDimensionSkuContributionResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"{dimension_code} 当前有 {total} 个 SKU 贡献记录，用于解释该维度销量结构来自哪些商品。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/sales-reconciliation-checks",
    response_model=Core3BusinessSalesReconciliationCheckListResponse,
)
def list_sales_reconciliation_checks(
    project_id: str,
    batch_id: str,
    status: str | None = Query(default=None),
    check_type: str | None = Query(default=None),
    dimension_type: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3BusinessSalesReconciliationCheckListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = DimensionSalesReconciliationRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_checks(
        batch_id,
        status=status,
        check_type=check_type,
        dimension_type=dimension_type,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3BusinessSalesReconciliationCheck.project_id == project_id,
        entities.Core3BusinessSalesReconciliationCheck.category_code == batch.category_code,
        entities.Core3BusinessSalesReconciliationCheck.batch_id == batch_id,
        entities.Core3BusinessSalesReconciliationCheck.is_current.is_(True),
    ]
    if status is not None:
        filters.append(entities.Core3BusinessSalesReconciliationCheck.status == status)
    if check_type is not None:
        filters.append(entities.Core3BusinessSalesReconciliationCheck.check_type == check_type)
    if dimension_type is not None:
        filters.append(entities.Core3BusinessSalesReconciliationCheck.dimension_type == dimension_type)
    total = _count_model_rows(db, entities.Core3BusinessSalesReconciliationCheck, filters)
    failed_count = sum(1 for item in items if item.status == "failed")
    return Core3BusinessSalesReconciliationCheckListResponse(
        items=[Core3BusinessSalesReconciliationCheckResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"当前返回 {len(items)} 条销量对账检查，本页未通过 {failed_count} 条。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/sales-reconciliation-issues",
    response_model=Core3BusinessSalesReconciliationIssueListResponse,
)
def list_sales_reconciliation_issues(
    project_id: str,
    batch_id: str,
    severity: str | None = Query(default=None),
    issue_code: str | None = Query(default=None),
    sku_code: str | None = Query(default=None),
    dimension_type: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3BusinessSalesReconciliationIssueListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = DimensionSalesReconciliationRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_issues(
        batch_id,
        severity=severity,
        issue_code=issue_code,
        sku_code=sku_code,
        dimension_type=dimension_type,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3BusinessSalesReconciliationIssue.project_id == project_id,
        entities.Core3BusinessSalesReconciliationIssue.category_code == batch.category_code,
        entities.Core3BusinessSalesReconciliationIssue.batch_id == batch_id,
        entities.Core3BusinessSalesReconciliationIssue.is_current.is_(True),
    ]
    if severity is not None:
        filters.append(entities.Core3BusinessSalesReconciliationIssue.severity == severity)
    if issue_code is not None:
        filters.append(entities.Core3BusinessSalesReconciliationIssue.issue_code == issue_code)
    if sku_code is not None:
        filters.append(entities.Core3BusinessSalesReconciliationIssue.sku_code == sku_code)
    if dimension_type is not None:
        filters.append(entities.Core3BusinessSalesReconciliationIssue.dimension_type == dimension_type)
    total = _count_model_rows(db, entities.Core3BusinessSalesReconciliationIssue, filters)
    blocker_count = sum(1 for item in items if item.severity == "blocker")
    return Core3BusinessSalesReconciliationIssueListResponse(
        items=[Core3BusinessSalesReconciliationIssueResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"当前有 {total} 条销量对账问题，本页阻断级 {blocker_count} 条；阻断级未解决前不应继续 M12。",
    )


@router.post(
    "/projects/{project_id}/batches/{batch_id}/candidate-recall/run",
    response_model=Core3ModuleRunResultSchema,
)
def run_candidate_recall(
    project_id: str,
    batch_id: str,
    payload: Core3CandidateRecallRunApiRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> Core3ModuleRunResultSchema:
    payload = payload or Core3CandidateRecallRunApiRequest()
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = CandidateRecallRepository(_repository_context(db, project_id, batch.category_code))
    try:
        repository.assert_inputs_ready(batch_id)
    except M12InputBlockedError as exc:
        raise HTTPException(status_code=409, detail=f"M12 inputs not ready: {exc}") from exc

    context = build_run_context(
        run_id=payload.run_id or f"m12-api-{batch_id}",
        project_id=project_id,
        category_code=payload.category_code,
        batch_id=batch_id,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(
            scope_type=Core3TargetScopeType.CHANGED_SKU,
            sku_codes=payload.sku_scope,
            data_domains=[Core3DataDomain.CANDIDATE],
            note_cn="M12 候选池召回手工触发",
        ),
        module_versions={"M12": payload.module_version},
        triggered_by=payload.triggered_by,
    )
    target = Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        target_ids=tuple(payload.sku_scope),
        data_domains=(Core3DataDomain.CANDIDATE,),
        metadata={
            "batch_id": batch_id,
            "module_run_id": payload.module_run_id,
            "module_version": payload.module_version,
            "rule_version": payload.rule_version,
            "force_rebuild": payload.force_rebuild,
        },
    )
    try:
        result = CandidateRecallRunner(db).run(context, target)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get(
    "/projects/{project_id}/batches/{batch_id}/candidate-recall-runs",
    response_model=Core3CandidateRecallRunListResponse,
)
def list_candidate_recall_runs(
    project_id: str,
    batch_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3CandidateRecallRunListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = CandidateRecallRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_runs(batch_id, limit=limit, offset=offset)
    filters = [
        entities.Core3CandidateRecallRun.project_id == project_id,
        entities.Core3CandidateRecallRun.category_code == batch.category_code,
        entities.Core3CandidateRecallRun.batch_id == batch_id,
        entities.Core3CandidateRecallRun.is_current.is_(True),
    ]
    total = _count_model_rows(db, entities.Core3CandidateRecallRun, filters)
    return Core3CandidateRecallRunListResponse(
        items=[Core3CandidateRecallRunResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"本批次有 {total} 次当前有效的候选池召回运行记录；M12 只表示入池候选，不代表最终三竞品。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{target_sku_code}/candidate-pool",
    response_model=Core3CandidatePoolListResponse,
)
def list_candidate_pool(
    project_id: str,
    batch_id: str,
    target_sku_code: str,
    candidate_sku_code: str | None = Query(default=None),
    recall_strength: str | None = Query(default=None),
    primary_relation_type: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3CandidatePoolListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = CandidateRecallRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_pools(
        batch_id,
        target_sku_code=target_sku_code,
        candidate_sku_code=candidate_sku_code,
        recall_strength=recall_strength,
        primary_relation_type=primary_relation_type,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3CandidatePool.project_id == project_id,
        entities.Core3CandidatePool.category_code == batch.category_code,
        entities.Core3CandidatePool.batch_id == batch_id,
        entities.Core3CandidatePool.target_sku_code == target_sku_code,
        entities.Core3CandidatePool.is_current.is_(True),
    ]
    if candidate_sku_code is not None:
        filters.append(entities.Core3CandidatePool.candidate_sku_code == candidate_sku_code)
    if recall_strength is not None:
        filters.append(entities.Core3CandidatePool.recall_strength == recall_strength)
    if primary_relation_type is not None:
        filters.append(entities.Core3CandidatePool.primary_relation_type == primary_relation_type)
    total = _count_model_rows(db, entities.Core3CandidatePool, filters)
    strong_count = sum(1 for item in items if str(item.recall_strength) == "strong")
    same_brand_count = sum(1 for item in items if item.same_brand_flag)
    return Core3CandidatePoolListResponse(
        items=[Core3CandidatePoolResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=(
            f"{target_sku_code} 当前返回 {len(items)} 个候选 SKU，其中 {strong_count} 个为强召回、"
            f"{same_brand_count} 个为同品牌候选；候选池用于 M13 评分，不是最终竞品名单。"
        ),
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{target_sku_code}/candidate-pool/{candidate_sku_code}/reasons",
    response_model=Core3CandidateRecallReasonListResponse,
)
def list_candidate_recall_reasons(
    project_id: str,
    batch_id: str,
    target_sku_code: str,
    candidate_sku_code: str,
    recall_source: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3CandidateRecallReasonListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = CandidateRecallRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_reasons(
        batch_id,
        target_sku_code=target_sku_code,
        candidate_sku_code=candidate_sku_code,
        recall_source=recall_source,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3CandidateRecallReason.project_id == project_id,
        entities.Core3CandidateRecallReason.category_code == batch.category_code,
        entities.Core3CandidateRecallReason.batch_id == batch_id,
        entities.Core3CandidateRecallReason.target_sku_code == target_sku_code,
        entities.Core3CandidateRecallReason.candidate_sku_code == candidate_sku_code,
        entities.Core3CandidateRecallReason.is_current.is_(True),
    ]
    if recall_source is not None:
        filters.append(entities.Core3CandidateRecallReason.recall_source == recall_source)
    total = _count_model_rows(db, entities.Core3CandidateRecallReason, filters)
    sources = sorted({str(item.recall_source) for item in items})
    return Core3CandidateRecallReasonListResponse(
        items=[Core3CandidateRecallReasonResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=(
            f"{candidate_sku_code} 进入 {target_sku_code} 候选池的当前理由共 {total} 条，"
            f"本页覆盖 {len(sources)} 类召回入口。"
        ),
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{target_sku_code}/candidate-pool/{candidate_sku_code}/feature-snapshot",
    response_model=Core3CandidateFeatureSnapshotListResponse,
)
def list_candidate_feature_snapshots(
    project_id: str,
    batch_id: str,
    target_sku_code: str,
    candidate_sku_code: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3CandidateFeatureSnapshotListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = CandidateRecallRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_snapshots(
        batch_id,
        target_sku_code=target_sku_code,
        candidate_sku_code=candidate_sku_code,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3CandidateFeatureSnapshot.project_id == project_id,
        entities.Core3CandidateFeatureSnapshot.category_code == batch.category_code,
        entities.Core3CandidateFeatureSnapshot.batch_id == batch_id,
        entities.Core3CandidateFeatureSnapshot.target_sku_code == target_sku_code,
        entities.Core3CandidateFeatureSnapshot.candidate_sku_code == candidate_sku_code,
        entities.Core3CandidateFeatureSnapshot.is_current.is_(True),
    ]
    total = _count_model_rows(db, entities.Core3CandidateFeatureSnapshot, filters)
    return Core3CandidateFeatureSnapshotListResponse(
        items=[Core3CandidateFeatureSnapshotResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"{target_sku_code} 与 {candidate_sku_code} 当前有 {total} 条 M13 可消费的 pair 特征快照。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/candidate-recall-review-issues",
    response_model=Core3CandidateRecallReviewIssueListResponse,
)
def list_candidate_recall_review_issues(
    project_id: str,
    batch_id: str,
    target_sku_code: str | None = Query(default=None),
    candidate_sku_code: str | None = Query(default=None),
    issue_type: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3CandidateRecallReviewIssueListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = CandidateRecallRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_review_issues(
        batch_id,
        target_sku_code=target_sku_code,
        candidate_sku_code=candidate_sku_code,
        issue_type=issue_type,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3CandidateRecallReviewIssue.project_id == project_id,
        entities.Core3CandidateRecallReviewIssue.category_code == batch.category_code,
        entities.Core3CandidateRecallReviewIssue.batch_id == batch_id,
        entities.Core3CandidateRecallReviewIssue.is_current.is_(True),
    ]
    if target_sku_code is not None:
        filters.append(entities.Core3CandidateRecallReviewIssue.target_sku_code == target_sku_code)
    if candidate_sku_code is not None:
        filters.append(entities.Core3CandidateRecallReviewIssue.candidate_sku_code == candidate_sku_code)
    if issue_type is not None:
        filters.append(entities.Core3CandidateRecallReviewIssue.issue_type == issue_type)
    total = _count_model_rows(db, entities.Core3CandidateRecallReviewIssue, filters)
    blocker_count = sum(1 for item in items if str(item.issue_level) in {"blocking", "blocker"})
    return Core3CandidateRecallReviewIssueListResponse(
        items=[Core3CandidateRecallReviewIssueResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"当前有 {total} 条 M12 候选召回复核问题；本页阻断级 {blocker_count} 条。",
    )


@router.post(
    "/projects/{project_id}/batches/{batch_id}/component-scores/run",
    response_model=Core3ModuleRunResultSchema,
)
def run_component_scoring(
    project_id: str,
    batch_id: str,
    payload: Core3ComponentScoringRunApiRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> Core3ModuleRunResultSchema:
    payload = payload or Core3ComponentScoringRunApiRequest()
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = ComponentScoringRepository(_repository_context(db, project_id, batch.category_code))
    try:
        repository.assert_inputs_ready(batch_id)
    except M13InputBlockedError as exc:
        raise HTTPException(status_code=409, detail=f"M13 inputs not ready: {exc}") from exc

    context = build_run_context(
        run_id=payload.run_id or f"m13-api-{batch_id}",
        project_id=project_id,
        category_code=payload.category_code,
        batch_id=batch_id,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(
            scope_type=Core3TargetScopeType.CHANGED_SKU,
            sku_codes=payload.sku_scope,
            data_domains=[Core3DataDomain.SCORE],
            note_cn="M13 竞品组件评分手工触发",
        ),
        module_versions={"M13": payload.module_version},
        triggered_by=payload.triggered_by,
    )
    _ensure_manual_pipeline_run_for_context(db, context)
    target = Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        target_ids=tuple(payload.sku_scope),
        data_domains=(Core3DataDomain.SCORE,),
        metadata={
            "batch_id": batch_id,
            "module_run_id": payload.module_run_id,
            "module_version": payload.module_version,
            "rule_version": payload.rule_version,
            "component_rule_version": payload.component_rule_version,
            "role_rule_version": payload.role_rule_version,
            "max_pairs": payload.max_pairs,
            "resume_unscored_only": payload.resume_unscored_only,
            "force_rebuild": payload.force_rebuild,
        },
    )
    try:
        result = ComponentScoringRunner(db).run(context, target)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{target_sku_code}/component-scores",
    response_model=Core3CandidateComponentScoreListResponse,
)
def list_candidate_component_scores(
    project_id: str,
    batch_id: str,
    target_sku_code: str,
    candidate_sku_code: str | None = Query(default=None),
    review_required: bool | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3CandidateComponentScoreListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = ComponentScoringRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_component_scores(
        batch_id,
        target_sku_code=target_sku_code,
        candidate_sku_code=candidate_sku_code,
        review_required=review_required,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3CandidateComponentScore.project_id == project_id,
        entities.Core3CandidateComponentScore.category_code == batch.category_code,
        entities.Core3CandidateComponentScore.batch_id == batch_id,
        entities.Core3CandidateComponentScore.target_sku_code == target_sku_code,
        entities.Core3CandidateComponentScore.is_current.is_(True),
    ]
    if candidate_sku_code is not None:
        filters.append(entities.Core3CandidateComponentScore.candidate_sku_code == candidate_sku_code)
    if review_required is not None:
        filters.append(entities.Core3CandidateComponentScore.review_required.is_(review_required))
    total = _count_model_rows(db, entities.Core3CandidateComponentScore, filters)
    review_count = sum(1 for item in items if item.review_required)
    return Core3CandidateComponentScoreListResponse(
        items=[Core3CandidateComponentScoreResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=(
            f"{target_sku_code} 当前返回 {len(items)} 个已评分候选，"
            f"本页 {review_count} 个需要复核；M13 分数只供 M14 选择和 M15 证据解释使用。"
        ),
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{target_sku_code}/component-scores/{candidate_sku_code}",
    response_model=Core3CandidateComponentScoreListResponse,
)
def get_candidate_component_score(
    project_id: str,
    batch_id: str,
    target_sku_code: str,
    candidate_sku_code: str,
    db: Session = Depends(get_db),
) -> Core3CandidateComponentScoreListResponse:
    return list_candidate_component_scores(
        project_id=project_id,
        batch_id=batch_id,
        target_sku_code=target_sku_code,
        candidate_sku_code=candidate_sku_code,
        review_required=None,
        limit=20,
        offset=0,
        db=db,
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{target_sku_code}/component-scores/{candidate_sku_code}/roles",
    response_model=Core3CandidateRoleScoreListResponse,
)
def list_candidate_role_scores(
    project_id: str,
    batch_id: str,
    target_sku_code: str,
    candidate_sku_code: str,
    role_code: str | None = Query(default=None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3CandidateRoleScoreListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = ComponentScoringRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_role_scores(
        batch_id,
        target_sku_code=target_sku_code,
        candidate_sku_code=candidate_sku_code,
        role_code=role_code,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3CandidateRoleScore.project_id == project_id,
        entities.Core3CandidateRoleScore.category_code == batch.category_code,
        entities.Core3CandidateRoleScore.batch_id == batch_id,
        entities.Core3CandidateRoleScore.target_sku_code == target_sku_code,
        entities.Core3CandidateRoleScore.candidate_sku_code == candidate_sku_code,
        entities.Core3CandidateRoleScore.is_current.is_(True),
    ]
    if role_code is not None:
        filters.append(entities.Core3CandidateRoleScore.role_code == role_code)
    total = _count_model_rows(db, entities.Core3CandidateRoleScore, filters)
    return Core3CandidateRoleScoreListResponse(
        items=[Core3CandidateRoleScoreResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"{candidate_sku_code} 相对 {target_sku_code} 当前有 {total} 条角色分，用于 M14 分槽选择。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{target_sku_code}/component-scores/{candidate_sku_code}/explanations",
    response_model=Core3CandidateComponentExplanationListResponse,
)
def list_candidate_component_explanations(
    project_id: str,
    batch_id: str,
    target_sku_code: str,
    candidate_sku_code: str,
    component_code: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3CandidateComponentExplanationListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = ComponentScoringRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_explanations(
        batch_id,
        target_sku_code=target_sku_code,
        candidate_sku_code=candidate_sku_code,
        component_code=component_code,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3CandidateComponentExplanation.project_id == project_id,
        entities.Core3CandidateComponentExplanation.category_code == batch.category_code,
        entities.Core3CandidateComponentExplanation.batch_id == batch_id,
        entities.Core3CandidateComponentExplanation.target_sku_code == target_sku_code,
        entities.Core3CandidateComponentExplanation.candidate_sku_code == candidate_sku_code,
        entities.Core3CandidateComponentExplanation.is_current.is_(True),
    ]
    if component_code is not None:
        filters.append(entities.Core3CandidateComponentExplanation.component_code == component_code)
    total = _count_model_rows(db, entities.Core3CandidateComponentExplanation, filters)
    return Core3CandidateComponentExplanationListResponse(
        items=[Core3CandidateComponentExplanationResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"{candidate_sku_code} 相对 {target_sku_code} 当前有 {total} 条组件解释，可供 M15 证据卡使用。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/component-score-review-issues",
    response_model=Core3CandidateScoreReviewIssueListResponse,
)
def list_candidate_score_review_issues(
    project_id: str,
    batch_id: str,
    target_sku_code: str | None = Query(default=None),
    candidate_sku_code: str | None = Query(default=None),
    issue_type: str | None = Query(default=None),
    issue_level: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3CandidateScoreReviewIssueListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = ComponentScoringRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_review_issues(
        batch_id,
        target_sku_code=target_sku_code,
        candidate_sku_code=candidate_sku_code,
        issue_type=issue_type,
        issue_level=issue_level,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3CandidateScoreReviewIssue.project_id == project_id,
        entities.Core3CandidateScoreReviewIssue.category_code == batch.category_code,
        entities.Core3CandidateScoreReviewIssue.batch_id == batch_id,
        entities.Core3CandidateScoreReviewIssue.is_current.is_(True),
    ]
    if target_sku_code is not None:
        filters.append(entities.Core3CandidateScoreReviewIssue.target_sku_code == target_sku_code)
    if candidate_sku_code is not None:
        filters.append(entities.Core3CandidateScoreReviewIssue.candidate_sku_code == candidate_sku_code)
    if issue_type is not None:
        filters.append(entities.Core3CandidateScoreReviewIssue.issue_type == issue_type)
    if issue_level is not None:
        filters.append(entities.Core3CandidateScoreReviewIssue.issue_level == issue_level)
    total = _count_model_rows(db, entities.Core3CandidateScoreReviewIssue, filters)
    return Core3CandidateScoreReviewIssueListResponse(
        items=[Core3CandidateScoreReviewIssueResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"当前有 {total} 条 M13 评分复核问题，主要用于限制 M14 自动入选和提示 M16 人工复核。",
    )


@router.post(
    "/projects/{project_id}/batches/{batch_id}/core3-selection/run",
    response_model=Core3ModuleRunResultSchema,
)
def run_core3_selection(
    project_id: str,
    batch_id: str,
    payload: Core3SelectionRunApiRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> Core3ModuleRunResultSchema:
    payload = payload or Core3SelectionRunApiRequest()
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = Core3SelectionRepository(_repository_context(db, project_id, batch.category_code))
    try:
        repository.assert_inputs_ready(batch_id)
    except M14InputBlockedError as exc:
        raise HTTPException(status_code=409, detail=f"M14 inputs not ready: {exc}") from exc

    context = build_run_context(
        run_id=payload.run_id or f"m14-api-{batch_id}",
        project_id=project_id,
        category_code=payload.category_code,
        batch_id=batch_id,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(
            scope_type=Core3TargetScopeType.CHANGED_SKU,
            sku_codes=payload.sku_scope,
            data_domains=[Core3DataDomain.SELECTION],
            note_cn="M14 三槽位核心竞品选择手工触发",
        ),
        module_versions={"M14": payload.module_version},
        triggered_by=payload.triggered_by,
    )
    _ensure_manual_pipeline_run_for_context(db, context)
    target = Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        target_ids=tuple(payload.sku_scope),
        data_domains=(Core3DataDomain.SELECTION,),
        metadata={
            "batch_id": batch_id,
            "module_run_id": payload.module_run_id,
            "module_version": payload.module_version,
            "rule_version": payload.rule_version,
            "max_targets": payload.max_targets,
            "resume_unselected_only": payload.resume_unselected_only,
            "force_rebuild": payload.force_rebuild,
        },
    )
    try:
        result = Core3SelectionRunner(db).run(context, target)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{target_sku_code}/core3-selection-runs",
    response_model=Core3CompetitorSelectionRunListResponse,
)
def list_core3_selection_runs(
    project_id: str,
    batch_id: str,
    target_sku_code: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3CompetitorSelectionRunListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = Core3SelectionRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_selection_runs(batch_id, target_sku_code=target_sku_code, limit=limit, offset=offset)
    filters = [
        entities.Core3CompetitorSelectionRun.project_id == project_id,
        entities.Core3CompetitorSelectionRun.category_code == batch.category_code,
        entities.Core3CompetitorSelectionRun.batch_id == batch_id,
        entities.Core3CompetitorSelectionRun.target_sku_code == target_sku_code,
        entities.Core3CompetitorSelectionRun.is_current.is_(True),
    ]
    total = _count_model_rows(db, entities.Core3CompetitorSelectionRun, filters)
    return Core3CompetitorSelectionRunListResponse(
        items=[Core3CompetitorSelectionRunResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"{target_sku_code} 当前有 {total} 次 M14 三槽位选择运行记录。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{target_sku_code}/core3-selections",
    response_model=Core3CompetitorSelectionListResponse,
)
def list_core3_selections(
    project_id: str,
    batch_id: str,
    target_sku_code: str,
    slot_code: str | None = Query(default=None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3CompetitorSelectionListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = Core3SelectionRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_selections(
        batch_id,
        target_sku_code=target_sku_code,
        slot_code=slot_code,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3CompetitorSelection.project_id == project_id,
        entities.Core3CompetitorSelection.category_code == batch.category_code,
        entities.Core3CompetitorSelection.batch_id == batch_id,
        entities.Core3CompetitorSelection.target_sku_code == target_sku_code,
        entities.Core3CompetitorSelection.is_current.is_(True),
    ]
    if slot_code is not None:
        filters.append(entities.Core3CompetitorSelection.slot_code == slot_code)
    total = _count_model_rows(db, entities.Core3CompetitorSelection, filters)
    return Core3CompetitorSelectionListResponse(
        items=[Core3CompetitorSelectionResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"{target_sku_code} 当前入选 {total} 个核心竞品；M14 不按总分 TopN，也不强行凑满空槽。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{target_sku_code}/core3-slot-decisions",
    response_model=Core3CompetitorSlotDecisionListResponse,
)
def list_core3_slot_decisions(
    project_id: str,
    batch_id: str,
    target_sku_code: str,
    slot_code: str | None = Query(default=None),
    decision_status: str | None = Query(default=None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3CompetitorSlotDecisionListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = Core3SelectionRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_slot_decisions(
        batch_id,
        target_sku_code=target_sku_code,
        slot_code=slot_code,
        decision_status=decision_status,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3CompetitorSlotDecision.project_id == project_id,
        entities.Core3CompetitorSlotDecision.category_code == batch.category_code,
        entities.Core3CompetitorSlotDecision.batch_id == batch_id,
        entities.Core3CompetitorSlotDecision.target_sku_code == target_sku_code,
        entities.Core3CompetitorSlotDecision.is_current.is_(True),
    ]
    if slot_code is not None:
        filters.append(entities.Core3CompetitorSlotDecision.slot_code == slot_code)
    if decision_status is not None:
        filters.append(entities.Core3CompetitorSlotDecision.decision_status == decision_status)
    total = _count_model_rows(db, entities.Core3CompetitorSlotDecision, filters)
    return Core3CompetitorSlotDecisionListResponse(
        items=[Core3CompetitorSlotDecisionResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"{target_sku_code} 当前返回 {total} 个槽位决策，空槽会保留原因而不补弱候选。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{target_sku_code}/core3-selection-audits",
    response_model=Core3CompetitorSelectionAuditListResponse,
)
def list_core3_selection_audits(
    project_id: str,
    batch_id: str,
    target_sku_code: str,
    candidate_sku_code: str | None = Query(default=None),
    audit_decision: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3CompetitorSelectionAuditListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = Core3SelectionRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_audits(
        batch_id,
        target_sku_code=target_sku_code,
        candidate_sku_code=candidate_sku_code,
        audit_decision=audit_decision,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3CompetitorSelectionAudit.project_id == project_id,
        entities.Core3CompetitorSelectionAudit.category_code == batch.category_code,
        entities.Core3CompetitorSelectionAudit.batch_id == batch_id,
        entities.Core3CompetitorSelectionAudit.target_sku_code == target_sku_code,
        entities.Core3CompetitorSelectionAudit.is_current.is_(True),
    ]
    if candidate_sku_code is not None:
        filters.append(entities.Core3CompetitorSelectionAudit.candidate_sku_code == candidate_sku_code)
    if audit_decision is not None:
        filters.append(entities.Core3CompetitorSelectionAudit.audit_decision == audit_decision)
    total = _count_model_rows(db, entities.Core3CompetitorSelectionAudit, filters)
    return Core3CompetitorSelectionAuditListResponse(
        items=[Core3CompetitorSelectionAuditResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"{target_sku_code} 当前有 {total} 条候选审计记录，可解释入选、未选或待复核原因。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/core3-selection-review-issues",
    response_model=Core3CompetitorSelectionReviewIssueListResponse,
)
def list_core3_selection_review_issues(
    project_id: str,
    batch_id: str,
    target_sku_code: str | None = Query(default=None),
    candidate_sku_code: str | None = Query(default=None),
    slot_code: str | None = Query(default=None),
    issue_type: str | None = Query(default=None),
    issue_level: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3CompetitorSelectionReviewIssueListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = Core3SelectionRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_review_issues(
        batch_id,
        target_sku_code=target_sku_code,
        candidate_sku_code=candidate_sku_code,
        slot_code=slot_code,
        issue_type=issue_type,
        issue_level=issue_level,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3CompetitorSelectionReviewIssue.project_id == project_id,
        entities.Core3CompetitorSelectionReviewIssue.category_code == batch.category_code,
        entities.Core3CompetitorSelectionReviewIssue.batch_id == batch_id,
        entities.Core3CompetitorSelectionReviewIssue.is_current.is_(True),
    ]
    if target_sku_code is not None:
        filters.append(entities.Core3CompetitorSelectionReviewIssue.target_sku_code == target_sku_code)
    if candidate_sku_code is not None:
        filters.append(entities.Core3CompetitorSelectionReviewIssue.candidate_sku_code == candidate_sku_code)
    if slot_code is not None:
        filters.append(entities.Core3CompetitorSelectionReviewIssue.slot_code == slot_code)
    if issue_type is not None:
        filters.append(entities.Core3CompetitorSelectionReviewIssue.issue_type == issue_type)
    if issue_level is not None:
        filters.append(entities.Core3CompetitorSelectionReviewIssue.issue_level == issue_level)
    total = _count_model_rows(db, entities.Core3CompetitorSelectionReviewIssue, filters)
    return Core3CompetitorSelectionReviewIssueListResponse(
        items=[Core3CompetitorSelectionReviewIssueResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"当前有 {total} 条 M14 三槽位选择复核问题，供 M16 人工复核使用。",
    )


@router.post(
    "/projects/{project_id}/batches/{batch_id}/evidence-report/run",
    response_model=Core3ModuleRunResultSchema,
)
def run_evidence_report(
    project_id: str,
    batch_id: str,
    payload: Core3EvidenceReportRunApiRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> Core3ModuleRunResultSchema:
    payload = payload or Core3EvidenceReportRunApiRequest()
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = EvidenceReportRepository(_repository_context(db, project_id, batch.category_code))
    try:
        repository.assert_inputs_ready(batch_id)
    except M15InputBlockedError as exc:
        raise HTTPException(status_code=409, detail=f"M15 inputs not ready: {exc}") from exc

    context = build_run_context(
        run_id=payload.run_id or f"m15-api-{batch_id}",
        project_id=project_id,
        category_code=payload.category_code,
        batch_id=batch_id,
        run_mode=Core3RunMode.DAILY_INCREMENTAL,
        target_scope=Core3TargetScopeSchema(
            scope_type=Core3TargetScopeType.CHANGED_SKU,
            sku_codes=payload.sku_scope,
            data_domains=[Core3DataDomain.REPORT],
            note_cn="M15 证据卡与高层报告手工触发",
        ),
        module_versions={"M15": payload.module_version},
        triggered_by=payload.triggered_by,
    )
    _ensure_manual_pipeline_run_for_context(db, context)
    target = Core3ModuleTarget(
        scope=Core3ModuleTargetScope.BATCH,
        target_ids=tuple(payload.sku_scope),
        data_domains=(Core3DataDomain.REPORT,),
        metadata={
            "batch_id": batch_id,
            "module_run_id": payload.module_run_id,
            "module_version": payload.module_version,
            "rule_version": payload.rule_version,
            "max_targets": payload.max_targets,
            "resume_unreported_only": payload.resume_unreported_only,
            "force_rebuild": payload.force_rebuild,
        },
    )
    try:
        result = EvidenceReportRunner(db).run(context, target)
        _finish_initialization_pipeline_run(db, context.run_id, result)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{target_sku_code}/report",
    response_model=Core3TargetReportPayloadResponse,
)
def get_target_evidence_report(
    project_id: str,
    batch_id: str,
    target_sku_code: str,
    db: Session = Depends(get_db),
) -> Core3TargetReportPayloadResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = EvidenceReportRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_report_payloads(batch_id, target_sku_code=target_sku_code, limit=1, offset=0)
    if not items:
        raise HTTPException(status_code=404, detail="evidence report not found")
    return _m15_report_response(items[0])


@router.get(
    "/projects/{project_id}/batches/{batch_id}/reports",
    response_model=Core3TargetReportPayloadListResponse,
)
def list_target_evidence_reports(
    project_id: str,
    batch_id: str,
    target_sku_code: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3TargetReportPayloadListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = EvidenceReportRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_report_payloads(
        batch_id,
        target_sku_code=target_sku_code,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3TargetReportPayload.project_id == project_id,
        entities.Core3TargetReportPayload.category_code == batch.category_code,
        entities.Core3TargetReportPayload.batch_id == batch_id,
        entities.Core3TargetReportPayload.is_current.is_(True),
    ]
    if target_sku_code is not None:
        filters.append(entities.Core3TargetReportPayload.target_sku_code == target_sku_code)
    total = _count_model_rows(db, entities.Core3TargetReportPayload, filters)
    return Core3TargetReportPayloadListResponse(
        items=[_m15_report_response(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"当前有 {total} 份 M15 高层报告，报告只展示业务语言和证据短号。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{target_sku_code}/evidence-cards",
    response_model=Core3EvidenceCardListResponse,
)
def list_evidence_cards(
    project_id: str,
    batch_id: str,
    target_sku_code: str,
    slot_code: str | None = Query(default=None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3EvidenceCardListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = EvidenceReportRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_evidence_cards(
        batch_id,
        target_sku_code=target_sku_code,
        slot_code=slot_code,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3ReportEvidenceCard.project_id == project_id,
        entities.Core3ReportEvidenceCard.category_code == batch.category_code,
        entities.Core3ReportEvidenceCard.batch_id == batch_id,
        entities.Core3ReportEvidenceCard.target_sku_code == target_sku_code,
        entities.Core3ReportEvidenceCard.is_current.is_(True),
    ]
    if slot_code is not None:
        filters.append(entities.Core3ReportEvidenceCard.slot_code == slot_code)
    total = _count_model_rows(db, entities.Core3ReportEvidenceCard, filters)
    return Core3EvidenceCardListResponse(
        items=[Core3EvidenceCardResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"{target_sku_code} 当前有 {total} 张核心竞品证据卡。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{target_sku_code}/report/sections",
    response_model=Core3ReportSectionListResponse,
)
def list_evidence_report_sections(
    project_id: str,
    batch_id: str,
    target_sku_code: str,
    section_code: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3ReportSectionListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = EvidenceReportRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_report_sections(
        batch_id,
        target_sku_code=target_sku_code,
        section_code=section_code,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3ReportSection.project_id == project_id,
        entities.Core3ReportSection.category_code == batch.category_code,
        entities.Core3ReportSection.batch_id == batch_id,
        entities.Core3ReportSection.target_sku_code == target_sku_code,
        entities.Core3ReportSection.is_current.is_(True),
    ]
    if section_code is not None:
        filters.append(entities.Core3ReportSection.section_code == section_code)
    total = _count_model_rows(db, entities.Core3ReportSection, filters)
    return Core3ReportSectionListResponse(
        items=[Core3ReportSectionResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"{target_sku_code} 当前有 {total} 个报告章节，首屏、折叠和导出内容已分层。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{target_sku_code}/report/exports",
    response_model=Core3ReportExportListResponse,
)
def list_evidence_report_exports(
    project_id: str,
    batch_id: str,
    target_sku_code: str,
    export_type: str | None = Query(default=None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3ReportExportListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = EvidenceReportRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_report_exports(
        batch_id,
        target_sku_code=target_sku_code,
        export_type=export_type,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3ReportExport.project_id == project_id,
        entities.Core3ReportExport.category_code == batch.category_code,
        entities.Core3ReportExport.batch_id == batch_id,
        entities.Core3ReportExport.target_sku_code == target_sku_code,
        entities.Core3ReportExport.is_current.is_(True),
    ]
    if export_type is not None:
        filters.append(entities.Core3ReportExport.export_type == export_type)
    total = _count_model_rows(db, entities.Core3ReportExport, filters)
    return Core3ReportExportListResponse(
        items=[Core3ReportExportResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"{target_sku_code} 当前有 {total} 个报告导出产物。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{target_sku_code}/report/exports/{export_type}",
    response_model=Core3ReportExportResponse,
)
def get_evidence_report_export(
    project_id: str,
    batch_id: str,
    target_sku_code: str,
    export_type: str,
    db: Session = Depends(get_db),
) -> Core3ReportExportResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = EvidenceReportRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_report_exports(
        batch_id,
        target_sku_code=target_sku_code,
        export_type=export_type,
        limit=1,
        offset=0,
    )
    if not items:
        raise HTTPException(status_code=404, detail="report export not found")
    return Core3ReportExportResponse.model_validate(items[0], from_attributes=True)


@router.get(
    "/projects/{project_id}/batches/{batch_id}/report-review-issues",
    response_model=Core3ReportReviewIssueListResponse,
)
def list_evidence_report_review_issues(
    project_id: str,
    batch_id: str,
    target_sku_code: str | None = Query(default=None),
    issue_type: str | None = Query(default=None),
    issue_level: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3ReportReviewIssueListResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = EvidenceReportRepository(_repository_context(db, project_id, batch.category_code))
    items = repository.list_current_review_issues(
        batch_id,
        target_sku_code=target_sku_code,
        issue_type=issue_type,
        issue_level=issue_level,
        limit=limit,
        offset=offset,
    )
    filters = [
        entities.Core3ReportReviewIssue.project_id == project_id,
        entities.Core3ReportReviewIssue.category_code == batch.category_code,
        entities.Core3ReportReviewIssue.batch_id == batch_id,
        entities.Core3ReportReviewIssue.is_current.is_(True),
    ]
    if target_sku_code is not None:
        filters.append(entities.Core3ReportReviewIssue.target_sku_code == target_sku_code)
    if issue_type is not None:
        filters.append(entities.Core3ReportReviewIssue.issue_type == issue_type)
    if issue_level is not None:
        filters.append(entities.Core3ReportReviewIssue.issue_level == issue_level)
    total = _count_model_rows(db, entities.Core3ReportReviewIssue, filters)
    return Core3ReportReviewIssueListResponse(
        items=[Core3ReportReviewIssueResponse.model_validate(item, from_attributes=True) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        summary_cn=f"当前有 {total} 条 M15 报告复核问题，用于 M16 人工复核。",
    )


@router.get(
    "/projects/{project_id}/batches/{batch_id}/skus/{target_sku_code}/evidence-ref/{short_ref}",
    response_model=Core3EvidenceShortRefTraceResponse,
)
def get_evidence_short_ref_trace(
    project_id: str,
    batch_id: str,
    target_sku_code: str,
    short_ref: str,
    db: Session = Depends(get_db),
) -> Core3EvidenceShortRefTraceResponse:
    batch = _get_batch_or_404(db, project_id, batch_id)
    repository = EvidenceReportRepository(_repository_context(db, project_id, batch.category_code))
    payloads = repository.list_current_report_payloads(batch_id, target_sku_code=target_sku_code, limit=1, offset=0)
    if not payloads:
        raise HTTPException(status_code=404, detail="evidence report not found")
    ref_item = next((item for item in payloads[0].short_evidence_map_json or [] if item.get("short_ref") == short_ref), None)
    if not ref_item:
        raise HTTPException(status_code=404, detail="short evidence ref not found")
    evidence = repository.get_evidence_by_short_ref(batch_id, target_sku_code=target_sku_code, short_ref=short_ref)
    return Core3EvidenceShortRefTraceResponse(
        short_ref=short_ref,
        target_sku_code=target_sku_code,
        evidence_domain_cn=ref_item.get("evidence_domain_cn"),
        evidence_title_cn=ref_item.get("evidence_title_cn"),
        source_cn=ref_item.get("source_cn"),
        snippet_cn=ref_item.get("snippet_cn"),
        source_table=evidence.source_table if evidence is not None else None,
        clean_table=evidence.clean_table if evidence is not None else None,
        evidence_field=evidence.evidence_field if evidence is not None else None,
    )


@router.get(
    "/projects/{project_id}/data-status",
    response_model=Core3V2DataStatusResponse,
)
def get_business_data_status(
    project_id: str,
    db: Session = Depends(get_db),
) -> Core3V2DataStatusResponse:
    return OverviewQueryService(_api_repository(db, project_id)).data_status()


@router.get(
    "/projects/{project_id}/sku/resolve",
    response_model=Core3V2SkuResolveResponse,
)
def resolve_business_sku(
    project_id: str,
    query: str = Query(min_length=1),
    db: Session = Depends(get_db),
) -> Core3V2SkuResolveResponse:
    try:
        return SkuResolutionService(_api_repository(db, project_id)).resolve(query)
    except ApiQueryError as exc:
        _raise_api_error(exc)


@router.get(
    "/projects/{project_id}/overview",
    response_model=Core3V2OverviewResponse,
)
def get_business_overview(
    project_id: str,
    db: Session = Depends(get_db),
) -> Core3V2OverviewResponse:
    return OverviewQueryService(_api_repository(db, project_id)).overview()


@router.get(
    "/projects/{project_id}/targets",
    response_model=Core3V2TargetListResponse,
)
def list_business_targets(
    project_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3V2TargetListResponse:
    return OverviewQueryService(_api_repository(db, project_id)).targets(limit=limit, offset=offset)


@router.get(
    "/projects/{project_id}/targets/{sku_or_model}/report",
    response_model=Core3V2BusinessReportResponse,
)
def get_business_report(
    project_id: str,
    sku_or_model: str,
    db: Session = Depends(get_db),
) -> Core3V2BusinessReportResponse:
    try:
        return BusinessReportQueryService(_api_repository(db, project_id)).get_report(sku_or_model)
    except ApiQueryError as exc:
        _raise_api_error(exc)


@router.get(
    "/projects/{project_id}/targets/{sku_or_model}/competitors",
    response_model=list[Core3V2CoreCompetitorResponse],
)
def list_business_competitors(
    project_id: str,
    sku_or_model: str,
    db: Session = Depends(get_db),
) -> list[Core3V2CoreCompetitorResponse]:
    try:
        return BusinessReportQueryService(_api_repository(db, project_id)).list_competitors(sku_or_model)
    except ApiQueryError as exc:
        _raise_api_error(exc)


@router.get(
    "/projects/{project_id}/targets/{sku_or_model}/evidence-cards",
    response_model=list[Core3V2EvidenceCardBusinessResponse],
)
def list_business_evidence_cards(
    project_id: str,
    sku_or_model: str,
    db: Session = Depends(get_db),
) -> list[Core3V2EvidenceCardBusinessResponse]:
    try:
        return BusinessReportQueryService(_api_repository(db, project_id)).list_evidence_cards(sku_or_model)
    except ApiQueryError as exc:
        _raise_api_error(exc)


@router.get(
    "/projects/{project_id}/targets/{sku_or_model}/sections",
    response_model=list[Core3V2ReportSectionBusinessResponse],
)
def list_business_report_sections(
    project_id: str,
    sku_or_model: str,
    db: Session = Depends(get_db),
) -> list[Core3V2ReportSectionBusinessResponse]:
    try:
        return BusinessReportQueryService(_api_repository(db, project_id)).list_sections(sku_or_model)
    except ApiQueryError as exc:
        _raise_api_error(exc)


@router.get(
    "/projects/{project_id}/targets/{sku_or_model}/exports/{export_type}",
    response_model=Core3V2ExportBusinessResponse,
)
def get_business_report_export(
    project_id: str,
    sku_or_model: str,
    export_type: str,
    db: Session = Depends(get_db),
) -> Core3V2ExportBusinessResponse:
    try:
        report_service = BusinessReportQueryService(_api_repository(db, project_id))
        return ExportDeliveryService(report_service).get_export(sku_or_model, export_type)
    except ApiQueryError as exc:
        _raise_api_error(exc)


@router.get(
    "/projects/{project_id}/targets/{sku_or_model}/evidence/{short_ref}/trace",
    response_model=Core3V2EvidenceTraceResponse,
)
def trace_business_evidence_ref(
    project_id: str,
    sku_or_model: str,
    short_ref: str,
    db: Session = Depends(get_db),
) -> Core3V2EvidenceTraceResponse:
    try:
        return EvidenceTraceQueryService(_api_repository(db, project_id)).get_trace(sku_or_model, short_ref)
    except ApiQueryError as exc:
        _raise_api_error(exc)


@router.get(
    "/projects/{project_id}/pipeline/initialization",
    response_model=Core3PipelineInitializationStatusResponse,
)
def get_pipeline_initialization_status(
    project_id: str,
    batch_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> Core3PipelineInitializationStatusResponse:
    return PipelineInitializationStatusService(db, project_id).build_status(batch_id=batch_id)


@router.post(
    "/projects/{project_id}/pipeline/initialization/run",
    response_model=Core3PipelineInitializationRunResponse,
)
def run_pipeline_initialization_module(
    project_id: str,
    payload: Core3PipelineInitializationRunApiRequest,
    db: Session = Depends(get_db),
) -> Core3PipelineInitializationRunResponse:
    module_code = Core3ModuleCode(payload.module_code)
    batch_id = payload.batch_id or _latest_initialization_batch_id(db, project_id)
    before = PipelineInitializationStatusService(db, project_id).build_status(batch_id=batch_id)
    module_before = _initialization_module_status(before, module_code)
    if module_before.can_skip and not payload.force_rebuild:
        pipeline_run = _create_initialization_pipeline_run(
            db,
            project_id=project_id,
            batch_id=batch_id,
            module_code=module_code,
            triggered_by=payload.triggered_by,
            run_id=payload.run_id,
        )
        result = _skipped_initialization_result(module_before)
        _persist_initialization_module_result(
            db,
            run_id=pipeline_run.run_id,
            project_id=project_id,
            batch_id=batch_id,
            result=result,
        )
        _finish_initialization_pipeline_run(db, pipeline_run.run_id, result)
        db.commit()
        after = PipelineInitializationStatusService(db, project_id).build_status(batch_id=batch_id)
        return Core3PipelineInitializationRunResponse(
            project_id=project_id,
            category_code=after.category_code,
            batch_id=after.batch_id,
            module=_initialization_module_status(after, module_code),
            result=result,
            skipped=True,
            message_cn=f"“{module_before.stage_name_cn}”已有可用产物，本次已跳过。",
            next_action_cn="如确认上游规则或数据发生变化，可使用强制重跑。",
        )
    if module_code != Core3ModuleCode.M00 and module_before.blocked_reason_cn and not payload.force_rebuild:
        pipeline_run = _create_initialization_pipeline_run(
            db,
            project_id=project_id,
            batch_id=batch_id,
            module_code=module_code,
            triggered_by=payload.triggered_by,
            run_id=payload.run_id,
        )
        result = _blocked_initialization_result(module_before)
        _persist_initialization_module_result(
            db,
            run_id=pipeline_run.run_id,
            project_id=project_id,
            batch_id=batch_id,
            result=result,
        )
        _finish_initialization_pipeline_run(db, pipeline_run.run_id, result)
        db.commit()
        after = PipelineInitializationStatusService(db, project_id).build_status(batch_id=batch_id)
        return Core3PipelineInitializationRunResponse(
            project_id=project_id,
            category_code=after.category_code,
            batch_id=after.batch_id,
            module=_initialization_module_status(after, module_code),
            result=result,
            skipped=False,
            message_cn=module_before.blocked_reason_cn,
            next_action_cn="请先执行上游环节，再回到本环节。",
        )

    pipeline_run = _create_initialization_pipeline_run(
        db,
        project_id=project_id,
        batch_id=batch_id,
        module_code=module_code,
        triggered_by=payload.triggered_by,
        run_id=payload.run_id,
    )
    module_run_id = str(uuid4())
    if module_code != Core3ModuleCode.M16:
        _create_initialization_module_run_placeholder(
            db,
            run_id=pipeline_run.run_id,
            project_id=project_id,
            batch_id=batch_id,
            module_code=module_code,
            module_run_id=module_run_id,
        )
    try:
        result, result_batch_id = _execute_initialization_module(
            project_id=project_id,
            batch_id=batch_id,
            pipeline_run_id=pipeline_run.run_id,
            module_run_id=module_run_id,
            payload=payload,
            db=db,
        )
        batch_id = result_batch_id or batch_id
        _update_initialization_pipeline_batch(db, pipeline_run.run_id, batch_id)
        if module_code != Core3ModuleCode.M16:
            _persist_initialization_module_result(
                db,
                run_id=pipeline_run.run_id,
                project_id=project_id,
                batch_id=batch_id,
                result=result,
                module_run_id=module_run_id,
            )
        _finish_initialization_pipeline_run(db, pipeline_run.run_id, result)
        db.commit()
    except HTTPException as exc:
        db.rollback()
        pipeline_run = _create_initialization_pipeline_run(
            db,
            project_id=project_id,
            batch_id=batch_id,
            module_code=module_code,
            triggered_by=payload.triggered_by,
            run_id=str(uuid4()),
        )
        result = _failed_initialization_result(module_before, str(exc.detail), status=Core3RunStatus.BLOCKED)
        _persist_initialization_module_result(
            db,
            run_id=pipeline_run.run_id,
            project_id=project_id,
            batch_id=batch_id,
            result=result,
        )
        _finish_initialization_pipeline_run(db, pipeline_run.run_id, result)
        db.commit()
    except Exception as exc:
        db.rollback()
        pipeline_run = _create_initialization_pipeline_run(
            db,
            project_id=project_id,
            batch_id=batch_id,
            module_code=module_code,
            triggered_by=payload.triggered_by,
            run_id=str(uuid4()),
        )
        result = _failed_initialization_result(module_before, f"执行失败：{exc}", status=Core3RunStatus.FAILED)
        _persist_initialization_module_result(
            db,
            run_id=pipeline_run.run_id,
            project_id=project_id,
            batch_id=batch_id,
            result=result,
        )
        _finish_initialization_pipeline_run(db, pipeline_run.run_id, result)
        db.commit()

    after = PipelineInitializationStatusService(db, project_id).build_status(batch_id=batch_id)
    module_after = _initialization_module_status(after, module_code)
    return Core3PipelineInitializationRunResponse(
        project_id=project_id,
        category_code=after.category_code,
        batch_id=after.batch_id,
        module=module_after,
        result=result,
        skipped=_enum_value(result.status) == Core3RunStatus.SKIPPED_REUSED.value,
        message_cn=f"“{module_after.stage_name_cn}”执行完成，当前状态：{module_after.execution_status_cn}。",
        next_action_cn=_next_initialization_action_cn(after, module_code),
    )


@router.post(
    "/projects/{project_id}/pipeline/runs",
    response_model=M16PipelineRunResponse,
)
def run_pipeline_governance(
    project_id: str,
    payload: M16PipelineRunRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> M16PipelineRunResponse:
    payload = payload or M16PipelineRunRequest(project_id=project_id)
    if payload.project_id != project_id:
        raise HTTPException(status_code=400, detail="project_id in path and body must match")
    repository = PipelineRepository(_repository_context(db, project_id, payload.category_code))
    service = PipelineExecutionService(repository)
    try:
        artifacts = service.run(payload)
        db.commit()
        return service.response(artifacts.run)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get(
    "/projects/{project_id}/pipeline/runs",
    response_model=Core3V2PipelineRunListResponse,
)
def list_pipeline_governance_runs(
    project_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Core3V2PipelineRunListResponse:
    return PipelineStatusQueryService(_api_repository(db, project_id)).list_runs(limit=limit, offset=offset)


@router.get(
    "/projects/{project_id}/pipeline/runs/latest",
    response_model=M16PipelineRunResponse,
)
def get_latest_pipeline_governance_run(
    project_id: str,
    db: Session = Depends(get_db),
) -> M16PipelineRunResponse:
    try:
        run_id = PipelineStatusQueryService(_api_repository(db, project_id)).latest_run_id()
    except ApiQueryError as exc:
        _raise_api_error(exc)
    run = _get_m16_run_or_404(db, project_id, run_id)
    repository = PipelineRepository(_repository_context(db, project_id, run.category_code))
    return PipelineExecutionService(repository).response(run)


@router.get(
    "/projects/{project_id}/pipeline/runs/{run_id}",
    response_model=M16PipelineRunResponse,
)
def get_pipeline_governance_run(
    project_id: str,
    run_id: str,
    db: Session = Depends(get_db),
) -> M16PipelineRunResponse:
    run = _get_m16_run_or_404(db, project_id, run_id)
    repository = PipelineRepository(_repository_context(db, project_id, run.category_code))
    return PipelineExecutionService(repository).response(run)


@router.get(
    "/projects/{project_id}/pipeline/runs/{run_id}/recompute-plan",
    response_model=M16ListResponse,
)
def list_pipeline_recompute_plan(
    project_id: str,
    run_id: str,
    limit: int = Query(1000, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> M16ListResponse:
    run = _get_m16_run_or_404(db, project_id, run_id)
    repository = PipelineRepository(_repository_context(db, project_id, run.category_code))
    items = repository.list_plans(run_id, limit=limit, offset=offset)
    return _m16_list_response(
        items,
        M16RecomputePlanRecord,
        limit=limit,
        offset=offset,
        summary_cn=f"当前生产线运行有 {len(items)} 条重算计划，M16 只记录复用、重跑或阻断策略。",
    )


@router.get(
    "/projects/{project_id}/pipeline/runs/{run_id}/module-runs",
    response_model=M16ListResponse,
)
def list_pipeline_module_runs(
    project_id: str,
    run_id: str,
    limit: int = Query(1000, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> M16ListResponse:
    run = _get_m16_run_or_404(db, project_id, run_id)
    repository = PipelineRepository(_repository_context(db, project_id, run.category_code))
    items = repository.list_module_runs(run_id, limit=limit, offset=offset)
    return _m16_list_response(
        items,
        M16ModuleRunRecord,
        limit=limit,
        offset=offset,
        summary_cn=f"当前生产线运行有 {len(items)} 个模块运行快照，用于确认上游产物是否可被后续消费。",
    )


@router.get(
    "/projects/{project_id}/pipeline/runs/{run_id}/modules",
    response_model=M16ListResponse,
)
def list_pipeline_modules_alias(
    project_id: str,
    run_id: str,
    limit: int = Query(1000, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> M16ListResponse:
    return list_pipeline_module_runs(
        project_id=project_id,
        run_id=run_id,
        limit=limit,
        offset=offset,
        db=db,
    )


@router.get(
    "/projects/{project_id}/pipeline/runs/{run_id}/dependencies",
    response_model=M16ListResponse,
)
def list_pipeline_dependency_snapshots(
    project_id: str,
    run_id: str,
    module_code: str | None = Query(default=None),
    limit: int = Query(1000, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> M16ListResponse:
    run = _get_m16_run_or_404(db, project_id, run_id)
    repository = PipelineRepository(_repository_context(db, project_id, run.category_code))
    items = repository.list_dependency_snapshots(run_id, module_code=module_code, limit=limit, offset=offset)
    return _m16_list_response(
        items,
        M16DependencySnapshotRecord,
        limit=limit,
        offset=offset,
        summary_cn=f"当前生产线运行有 {len(items)} 条模块依赖快照，用于追踪每个结论使用的上游产物版本。",
    )


@router.get(
    "/projects/{project_id}/pipeline/runs/{run_id}/reviews",
    response_model=M16ListResponse,
)
def list_pipeline_reviews(
    project_id: str,
    run_id: str,
    target_sku_code: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> M16ListResponse:
    run = _get_m16_run_or_404(db, project_id, run_id)
    repository = PipelineRepository(_repository_context(db, project_id, run.category_code))
    items = repository.list_reviews(
        run_id,
        target_sku_code=target_sku_code,
        severity=severity,
        review_status=review_status,
        limit=limit,
        offset=offset,
    )
    return _m16_list_response(
        items,
        M16ReviewQueueRecord,
        limit=limit,
        offset=offset,
        summary_cn=f"当前生产线运行有 {len(items)} 条复核项，阻断项必须处理后才能发布。",
    )


@router.post(
    "/projects/{project_id}/pipeline/reviews/{review_id}/decisions",
    response_model=M16ReviewDecisionRecord,
)
def decide_pipeline_review(
    project_id: str,
    review_id: str,
    payload: M16ReviewDecisionRequest,
    db: Session = Depends(get_db),
) -> M16ReviewDecisionRecord:
    review = db.get(entities.Core3V2ReviewQueue, review_id)
    if review is None or review.project_id != project_id:
        raise HTTPException(status_code=404, detail="pipeline review item not found")
    repository = PipelineRepository(_repository_context(db, project_id, review.category_code))
    try:
        decision = repository.insert_review_decision(review_id, payload.model_dump(mode="json"))
        db.commit()
        return M16ReviewDecisionRecord.model_validate(decision, from_attributes=True)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.get(
    "/projects/{project_id}/pipeline/runs/{run_id}/acceptance",
    response_model=M16AcceptanceReportRecord,
)
def get_pipeline_acceptance_report(
    project_id: str,
    run_id: str,
    db: Session = Depends(get_db),
) -> M16AcceptanceReportRecord:
    run = _get_m16_run_or_404(db, project_id, run_id)
    repository = PipelineRepository(_repository_context(db, project_id, run.category_code))
    acceptance = repository.get_acceptance_report(run_id)
    if acceptance is None:
        raise HTTPException(status_code=404, detail="pipeline acceptance report not found")
    return M16AcceptanceReportRecord.model_validate(acceptance, from_attributes=True)


@router.get(
    "/projects/{project_id}/pipeline/runs/{run_id}/release-gates",
    response_model=M16ListResponse,
)
def list_pipeline_release_gates(
    project_id: str,
    run_id: str,
    target_sku_code: str | None = Query(default=None),
    gate_status: str | None = Query(default=None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> M16ListResponse:
    run = _get_m16_run_or_404(db, project_id, run_id)
    repository = PipelineRepository(_repository_context(db, project_id, run.category_code))
    items = repository.list_release_gates(
        run_id,
        target_sku_code=target_sku_code,
        gate_status=gate_status,
        limit=limit,
        offset=offset,
    )
    return _m16_list_response(
        items,
        M16ReleaseGateRecord,
        limit=limit,
        offset=offset,
        summary_cn=f"当前生产线运行有 {len(items)} 个目标 SKU 发布门禁，用于控制报告是否可进入业务展示。",
    )


@router.post(
    "/projects/{project_id}/pipeline/release-gates/{release_gate_id}/release",
    response_model=M16ReleaseGateRecord,
)
def release_pipeline_gate(
    project_id: str,
    release_gate_id: str,
    released_by: str = Query(default="system", min_length=1),
    db: Session = Depends(get_db),
) -> M16ReleaseGateRecord:
    gate = db.get(entities.Core3V2ReleaseGate, release_gate_id)
    if gate is None or gate.project_id != project_id:
        raise HTTPException(status_code=404, detail="pipeline release gate not found")
    repository = PipelineRepository(_repository_context(db, project_id, gate.category_code))
    try:
        released_gate = repository.mark_release_gate_released(release_gate_id, released_by=released_by)
        db.commit()
        return M16ReleaseGateRecord.model_validate(released_gate, from_attributes=True)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.post(
    "/projects/{project_id}/reviews/{review_id}/decision",
    response_model=M16ReviewDecisionRecord,
)
def decide_business_review(
    project_id: str,
    review_id: str,
    payload: Core3V2ReviewDecisionAliasRequest,
    db: Session = Depends(get_db),
) -> M16ReviewDecisionRecord:
    repository = PipelineRepository(_repository_context(db, project_id, "TV"))
    try:
        decision = ReviewActionApiService(repository).decide_review(review_id, payload)
        db.commit()
        return M16ReviewDecisionRecord.model_validate(decision, from_attributes=True)
    except ApiQueryError as exc:
        db.rollback()
        _raise_api_error(exc)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


@router.post(
    "/projects/{project_id}/release-gates/{gate_id}/release",
    response_model=M16ReleaseGateRecord,
)
def release_business_gate(
    project_id: str,
    gate_id: str,
    payload: Core3V2ReleaseActionRequest | None = Body(default=None),
    db: Session = Depends(get_db),
) -> M16ReleaseGateRecord:
    repository = PipelineRepository(_repository_context(db, project_id, "TV"))
    try:
        gate = ReviewActionApiService(repository).release_gate(
            gate_id,
            payload or Core3V2ReleaseActionRequest(),
        )
        db.commit()
        return M16ReleaseGateRecord.model_validate(gate, from_attributes=True)
    except ApiQueryError as exc:
        db.rollback()
        _raise_api_error(exc)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise


def _enum_value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _initialization_module_status(
    status: Core3PipelineInitializationStatusResponse,
    module_code: Core3ModuleCode,
) -> Core3PipelineInitializationModuleStatus:
    for item in status.modules:
        if Core3ModuleCode(item.module_code) == module_code:
            return item
    raise HTTPException(status_code=400, detail=f"unknown initialization module: {module_code.value}")


def _latest_initialization_batch_id(db: Session, project_id: str) -> str | None:
    row = db.execute(
        select(entities.Core3SourceBatch.batch_id)
        .where(entities.Core3SourceBatch.project_id == project_id)
        .where(entities.Core3SourceBatch.category_code == "TV")
        .order_by(entities.Core3SourceBatch.updated_at.desc())
    ).first()
    return row[0] if row else None


def _create_initialization_pipeline_run(
    db: Session,
    *,
    project_id: str,
    batch_id: str | None,
    module_code: Core3ModuleCode,
    triggered_by: str,
    run_id: str | None,
) -> entities.Core3V2PipelineRun:
    pipeline_run = entities.Core3V2PipelineRun(
        run_id=run_id or str(uuid4()),
        project_id=project_id,
        category_code="TV",
        run_mode=Core3RunMode.DAILY_INCREMENTAL.value,
        trigger_type=Core3PipelineTriggerType.MANUAL.value,
        triggered_by=triggered_by or "factory-web",
        data_batch_id=batch_id,
        target_scope_json={
            "scope_type": "initialization_control",
            "module_code": module_code.value,
            "note_cn": "初始化运行页面触发",
        },
        ruleset_version=CORE3_DEFAULT_RULESET_VERSION,
        module_version_json={module_code.value: "api-initialization"},
        status=Core3RunStatus.RUNNING.value,
        release_status="not_ready",
        started_at=datetime.utcnow(),
    )
    db.add(pipeline_run)
    db.flush()
    return pipeline_run


def _ensure_manual_pipeline_run_for_context(db: Session, context: Any) -> entities.Core3V2PipelineRun:
    existing = db.get(entities.Core3V2PipelineRun, context.run_id)
    if existing is not None:
        return existing
    repository = PipelineRepository(_repository_context(db, context.project_id, context.category_code.value))
    return repository.create_pipeline_run(
        run_id=context.run_id,
        parent_run_id=None,
        data_batch_id=context.batch_id,
        run_mode=context.run_mode.value,
        trigger_type=Core3PipelineTriggerType.MANUAL.value,
        triggered_by=context.triggered_by,
        target_scope_json=context.target_scope.model_dump(mode="json"),
        ruleset_version=context.ruleset_version,
        module_version_json=dict(context.module_versions or {}),
        seed_version_json=dict(context.seed_versions or {}),
        input_watermark_json=dict(context.input_watermarks or {}),
    )


def _update_initialization_pipeline_batch(db: Session, run_id: str, batch_id: str | None) -> None:
    if not batch_id:
        return
    run = db.get(entities.Core3V2PipelineRun, run_id)
    if run is not None:
        run.data_batch_id = batch_id
        run.output_summary_json = {**(run.output_summary_json or {}), "batch_id": batch_id}


def _create_initialization_module_run_placeholder(
    db: Session,
    *,
    run_id: str,
    project_id: str,
    batch_id: str | None,
    module_code: Core3ModuleCode,
    module_run_id: str,
) -> entities.Core3V2ModuleRun:
    module_run = entities.Core3V2ModuleRun(
        module_run_id=module_run_id,
        run_id=run_id,
        project_id=project_id,
        category_code="TV",
        module_code=module_code.value,
        target_scope="batch",
        target_id=batch_id,
        batch_id=batch_id,
        status=Core3RunStatus.RUNNING.value,
        input_count=0,
        changed_input_count=0,
        output_count=0,
        warnings_json=[],
        review_issue_summary_json={"count": 0, "items": []},
        downstream_impact_json={"items": []},
        summary_json={"note_cn": "初始化运行页面触发，模块执行中。"},
        started_at=datetime.utcnow(),
    )
    db.add(module_run)
    db.flush()
    return module_run


def _persist_initialization_module_result(
    db: Session,
    *,
    run_id: str,
    project_id: str,
    batch_id: str | None,
    result: Core3ModuleRunResultSchema,
    module_run_id: str | None = None,
) -> entities.Core3V2ModuleRun:
    issue_summary_items = [
        issue.model_dump(mode="json") if hasattr(issue, "model_dump") else dict(issue)
        for issue in result.review_issues[:20]
    ]
    issue_summary = {
        "count": len(result.review_issues),
        "items": issue_summary_items,
    }
    normalized_status = _enum_value(result.status)
    resolved_module_run_id = module_run_id or str(uuid4())
    module_run = db.get(entities.Core3V2ModuleRun, resolved_module_run_id)
    if module_run is None:
        module_run = entities.Core3V2ModuleRun(module_run_id=resolved_module_run_id)
        db.add(module_run)
    module_run.run_id = run_id
    module_run.project_id = project_id
    module_run.category_code = "TV"
    module_run.module_code = _enum_value(result.module_code)
    module_run.target_scope = "batch"
    module_run.target_id = batch_id
    module_run.batch_id = batch_id
    module_run.status = normalized_status
    module_run.input_count = result.input_count
    module_run.changed_input_count = result.changed_input_count
    module_run.output_count = result.output_count
    module_run.output_hash = result.output_hash
    module_run.warnings_json = list(result.warnings)
    module_run.review_issue_summary_json = issue_summary
    module_run.downstream_impact_json = {"items": list(result.downstream_impacts)}
    module_run.summary_json = dict(result.summary_json or {})
    module_run.started_at = result.started_at
    module_run.finished_at = result.finished_at or datetime.utcnow()
    module_run.error_code = "initialization_module_failed" if normalized_status == Core3RunStatus.FAILED.value else None
    module_run.error_message_cn = _result_error_message_cn(result)
    db.flush()
    return module_run


def _finish_initialization_pipeline_run(db: Session, run_id: str, result: Core3ModuleRunResultSchema) -> None:
    run = db.get(entities.Core3V2PipelineRun, run_id)
    if run is None:
        return
    status = _enum_value(result.status)
    run.status = status
    run.finished_at = result.finished_at or datetime.utcnow()
    run.output_summary_json = {
        **(run.output_summary_json or {}),
        "module_code": _enum_value(result.module_code),
        "input_count": result.input_count,
        "changed_input_count": result.changed_input_count,
        "output_count": result.output_count,
        "warnings": list(result.warnings),
        "review_issue_count": len(result.review_issues),
        "summary": dict(result.summary_json or {}),
    }
    run.quality_summary_json = {
        "warning_count": len(result.warnings),
        "review_issue_count": len(result.review_issues),
        "status": status,
    }
    run.release_status = "blocked" if status in {Core3RunStatus.FAILED.value, Core3RunStatus.BLOCKED.value} else "not_ready"
    run.error_message_cn = _result_error_message_cn(result)


def _result_error_message_cn(result: Core3ModuleRunResultSchema) -> str | None:
    status = _enum_value(result.status)
    if status not in {Core3RunStatus.FAILED.value, Core3RunStatus.BLOCKED.value}:
        return None
    if result.warnings:
        return "；".join(result.warnings[:3])
    return "初始化环节未能完成。"


def _skipped_initialization_result(
    module_status: Core3PipelineInitializationModuleStatus,
) -> Core3ModuleRunResultSchema:
    now = datetime.utcnow()
    return Core3ModuleRunResultSchema(
        module_code=module_status.module_code,
        status=Core3RunStatus.SKIPPED_REUSED,
        input_count=module_status.expected_target_count,
        changed_input_count=0,
        output_count=module_status.output_count,
        warnings=[],
        review_issues=[],
        downstream_impacts=[],
        summary_json={
            "skip_reason_cn": module_status.skip_reason_cn or "已有可用产物，本次跳过。",
            "processed_target_count": module_status.processed_target_count,
            "current_output_count": module_status.current_output_count,
            "reused_module_run_id": module_status.latest_module_run_id,
        },
        started_at=now,
        finished_at=now,
    )


def _blocked_initialization_result(
    module_status: Core3PipelineInitializationModuleStatus,
) -> Core3ModuleRunResultSchema:
    now = datetime.utcnow()
    return Core3ModuleRunResultSchema(
        module_code=module_status.module_code,
        status=Core3RunStatus.BLOCKED,
        warnings=[module_status.blocked_reason_cn or "上游产物未就绪。"],
        summary_json={
            "blocked_reason_cn": module_status.blocked_reason_cn or "上游产物未就绪。",
            "expected_target_count": module_status.expected_target_count,
            "processed_target_count": module_status.processed_target_count,
        },
        started_at=now,
        finished_at=now,
    )


def _failed_initialization_result(
    module_status: Core3PipelineInitializationModuleStatus,
    message_cn: str,
    *,
    status: Core3RunStatus,
) -> Core3ModuleRunResultSchema:
    now = datetime.utcnow()
    return Core3ModuleRunResultSchema(
        module_code=module_status.module_code,
        status=status,
        warnings=[message_cn],
        review_issues=[],
        downstream_impacts=[],
        summary_json={"message_cn": message_cn},
        started_at=now,
        finished_at=now,
    )


def _execute_initialization_module(
    *,
    project_id: str,
    batch_id: str | None,
    pipeline_run_id: str,
    module_run_id: str,
    payload: Core3PipelineInitializationRunApiRequest,
    db: Session,
) -> tuple[Core3ModuleRunResultSchema, str | None]:
    module_code = Core3ModuleCode(payload.module_code)
    if module_code == Core3ModuleCode.M00:
        result = register_source_batch(
            project_id,
            Core3SourceBatchRegisterApiRequest(
                run_id=pipeline_run_id,
                batch_type=Core3SourceBatchType.INCREMENTAL if batch_id else Core3SourceBatchType.FULL,
                triggered_by=payload.triggered_by,
                note_cn="初始化运行页面读取原始数据",
            ),
            db,
        )
        return result, str(result.summary_json.get("batch_id") or batch_id or "")

    if not batch_id:
        raise HTTPException(status_code=409, detail="请先执行“读取原始数据”。")

    if module_code == Core3ModuleCode.M01:
        return (
            run_cleaning_quality(
                project_id,
                batch_id,
                Core3CleaningRunApiRequest(run_id=pipeline_run_id, module_run_id=module_run_id),
                db,
            ),
            batch_id,
        )
    if module_code == Core3ModuleCode.M02:
        return (
            run_evidence_atom(
                project_id,
                batch_id,
                Core3EvidenceRunApiRequest(run_id=pipeline_run_id, module_run_id=module_run_id),
                db,
            ),
            batch_id,
        )
    if module_code == Core3ModuleCode.M03:
        return (
            run_param_extraction(
                project_id,
                batch_id,
                Core3ParamExtractionRunApiRequest(
                    run_id=pipeline_run_id,
                    module_run_id=module_run_id,
                    force_rebuild=True,
                ),
                db,
            ),
            batch_id,
        )
    if module_code == Core3ModuleCode.M04A:
        return (
            run_base_claim_activation(
                project_id,
                batch_id,
                Core3BaseClaimActivationRunApiRequest(
                    run_id=pipeline_run_id,
                    module_run_id=module_run_id,
                    force_rebuild=payload.force_rebuild,
                    triggered_by=payload.triggered_by,
                ),
                db,
            ),
            batch_id,
        )
    if module_code == Core3ModuleCode.M05:
        return (
            run_comment_evidence(
                project_id,
                batch_id,
                Core3CommentEvidenceRunApiRequest(
                    run_id=pipeline_run_id,
                    module_run_id=module_run_id,
                    force_rebuild=payload.force_rebuild,
                    triggered_by=payload.triggered_by,
                ),
                db,
            ),
            batch_id,
        )
    if module_code == Core3ModuleCode.M06:
        return (
            run_comment_downstream_signals(
                project_id,
                batch_id,
                Core3CommentSignalRunApiRequest(
                    run_id=pipeline_run_id,
                    module_run_id=module_run_id,
                    sku_batch_size=1,
                    force_rebuild=payload.force_rebuild,
                    triggered_by=payload.triggered_by,
                ),
                db,
            ),
            batch_id,
        )
    if module_code == Core3ModuleCode.M04B:
        return (
            run_claim_comment_enhancement(
                project_id,
                batch_id,
                Core3ClaimCommentEnhancementRunApiRequest(
                    run_id=pipeline_run_id,
                    module_run_id=module_run_id,
                    force_rebuild=payload.force_rebuild,
                    triggered_by=payload.triggered_by,
                ),
                db,
            ),
            batch_id,
        )
    if module_code == Core3ModuleCode.M07:
        return (
            run_market_profile(
                project_id,
                batch_id,
                Core3MarketProfileRunApiRequest(
                    run_id=pipeline_run_id,
                    module_run_id=module_run_id,
                    force_rebuild=payload.force_rebuild,
                    triggered_by=payload.triggered_by,
                ),
                db,
            ),
            batch_id,
        )
    if module_code == Core3ModuleCode.M08:
        return (
            run_sku_signal_profile(
                project_id,
                batch_id,
                Core3SkuSignalProfileRunApiRequest(
                    run_id=pipeline_run_id,
                    module_run_id=module_run_id,
                    force_rebuild=payload.force_rebuild,
                    triggered_by=payload.triggered_by,
                ),
                db,
            ),
            batch_id,
        )
    if module_code == Core3ModuleCode.M08_4:
        return (
            run_comment_native_dimensions(
                project_id,
                batch_id,
                Core3CommentNativeDimensionRunApiRequest(
                    run_id=pipeline_run_id,
                    module_run_id=module_run_id,
                    force_rebuild=payload.force_rebuild,
                    triggered_by=payload.triggered_by,
                ),
                db,
            ),
            batch_id,
        )
    if module_code == Core3ModuleCode.M08_5:
        return (
            run_dimension_ontology(
                project_id,
                batch_id,
                Core3DimensionOntologyRunApiRequest(
                    run_id=pipeline_run_id,
                    module_run_id=module_run_id,
                    force_rebuild=payload.force_rebuild,
                    triggered_by=payload.triggered_by,
                ),
                db,
            ),
            batch_id,
        )
    if module_code == Core3ModuleCode.M09:
        return (
            run_user_tasks(
                project_id,
                batch_id,
                Core3UserTaskRunApiRequest(
                    run_id=pipeline_run_id,
                    module_run_id=module_run_id,
                    force_rebuild=payload.force_rebuild,
                    triggered_by=payload.triggered_by,
                ),
                db,
            ),
            batch_id,
        )
    if module_code == Core3ModuleCode.M10:
        return (
            run_target_groups(
                project_id,
                batch_id,
                Core3TargetGroupRunApiRequest(
                    run_id=pipeline_run_id,
                    module_run_id=module_run_id,
                    force_rebuild=payload.force_rebuild,
                    triggered_by=payload.triggered_by,
                ),
                db,
            ),
            batch_id,
        )
    if module_code == Core3ModuleCode.M11:
        return (
            run_battlefields(
                project_id,
                batch_id,
                Core3BattlefieldRunApiRequest(
                    run_id=pipeline_run_id,
                    module_run_id=module_run_id,
                    force_rebuild=payload.force_rebuild,
                    triggered_by=payload.triggered_by,
                ),
                db,
            ),
            batch_id,
        )
    if module_code == Core3ModuleCode.M11_5:
        return (
            run_claim_value_layers(
                project_id,
                batch_id,
                Core3ClaimValueLayerRunApiRequest(
                    run_id=pipeline_run_id,
                    module_run_id=module_run_id,
                    force_rebuild=payload.force_rebuild,
                    triggered_by=payload.triggered_by,
                ),
                db,
            ),
            batch_id,
        )
    if module_code == Core3ModuleCode.M11_6:
        return (
            run_sku_business_profiles(
                project_id,
                batch_id,
                Core3SkuBusinessProfileRunApiRequest(
                    run_id=pipeline_run_id,
                    module_run_id=module_run_id,
                    force_rebuild=payload.force_rebuild,
                    triggered_by=payload.triggered_by,
                ),
                db,
            ),
            batch_id,
        )
    if module_code == Core3ModuleCode.M11_7:
        return (
            run_dimension_sales_reconciliation(
                project_id,
                batch_id,
                Core3DimensionSalesReconciliationRunApiRequest(
                    run_id=pipeline_run_id,
                    module_run_id=module_run_id,
                    force_rebuild=payload.force_rebuild,
                    triggered_by=payload.triggered_by,
                ),
                db,
            ),
            batch_id,
        )
    if module_code == Core3ModuleCode.M12:
        return (
            run_candidate_recall(
                project_id,
                batch_id,
                Core3CandidateRecallRunApiRequest(
                    run_id=pipeline_run_id,
                    module_run_id=module_run_id,
                    force_rebuild=payload.force_rebuild,
                    triggered_by=payload.triggered_by,
                ),
                db,
            ),
            batch_id,
        )
    if module_code == Core3ModuleCode.M13:
        return (
            run_component_scoring(
                project_id,
                batch_id,
                Core3ComponentScoringRunApiRequest(
                    run_id=pipeline_run_id,
                    module_run_id=module_run_id,
                    force_rebuild=payload.force_rebuild,
                    triggered_by=payload.triggered_by,
                ),
                db,
            ),
            batch_id,
        )
    if module_code == Core3ModuleCode.M14:
        return (
            run_core3_selection(
                project_id,
                batch_id,
                Core3SelectionRunApiRequest(
                    run_id=pipeline_run_id,
                    module_run_id=module_run_id,
                    force_rebuild=payload.force_rebuild,
                    triggered_by=payload.triggered_by,
                ),
                db,
            ),
            batch_id,
        )
    if module_code == Core3ModuleCode.M15:
        return (
            run_evidence_report(
                project_id,
                batch_id,
                Core3EvidenceReportRunApiRequest(
                    run_id=pipeline_run_id,
                    module_run_id=module_run_id,
                    force_rebuild=payload.force_rebuild,
                    triggered_by=payload.triggered_by,
                ),
                db,
            ),
            batch_id,
        )
    if module_code == Core3ModuleCode.M16:
        run_pipeline_governance(
            project_id,
            M16PipelineRunRequest(
                project_id=project_id,
                run_id=pipeline_run_id,
                data_batch_id=batch_id,
                triggered_by=payload.triggered_by,
            ),
            db,
        )
        m16_run = db.execute(
            select(entities.Core3V2ModuleRun)
            .where(entities.Core3V2ModuleRun.run_id == pipeline_run_id)
            .where(entities.Core3V2ModuleRun.module_code == Core3ModuleCode.M16.value)
            .order_by(entities.Core3V2ModuleRun.updated_at.desc())
        ).scalars().first()
        if not m16_run:
            raise HTTPException(status_code=409, detail="M16 已触发但未生成验收运行记录。")
        return _module_run_result_from_row(m16_run), batch_id

    raise HTTPException(status_code=400, detail=f"暂不支持的初始化环节：{module_code.value}")


def _module_run_result_from_row(row: entities.Core3V2ModuleRun) -> Core3ModuleRunResultSchema:
    return Core3ModuleRunResultSchema(
        module_code=Core3ModuleCode(row.module_code),
        status=Core3RunStatus(row.status),
        input_count=row.input_count,
        changed_input_count=row.changed_input_count,
        output_count=row.output_count,
        output_hash=row.output_hash,
        warnings=list(row.warnings_json or []),
        review_issues=[],
        downstream_impacts=list((row.downstream_impact_json or {}).get("items") or []),
        summary_json=dict(row.summary_json or {}),
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


def _next_initialization_action_cn(
    status: Core3PipelineInitializationStatusResponse,
    module_code: Core3ModuleCode,
) -> str | None:
    seen_current = False
    for item in status.modules:
        item_code = Core3ModuleCode(item.module_code)
        if not seen_current:
            seen_current = item_code == module_code
            continue
        if item.execution_status in {"not_started", "partial", "blocked", "failed"}:
            return f"下一步建议执行“{item.stage_name_cn}”。"
    return "所有环节已有运行记录，可进入报告查看或验收。"


def _m15_report_response(item: entities.Core3TargetReportPayload) -> Core3TargetReportPayloadResponse:
    payload = Core3TargetReportPayloadResponse.model_validate(item, from_attributes=True).model_dump(mode="python")
    payload["short_evidence_map_json"] = [
        {key: value for key, value in ref.items() if key != "evidence_id"}
        for ref in payload.get("short_evidence_map_json", [])
        if isinstance(ref, dict)
    ]
    return Core3TargetReportPayloadResponse(**payload)


def _get_m16_run_or_404(db: Session, project_id: str, run_id: str) -> entities.Core3V2PipelineRun:
    run = db.execute(
        select(entities.Core3V2PipelineRun)
        .where(entities.Core3V2PipelineRun.project_id == project_id)
        .where(entities.Core3V2PipelineRun.run_id == run_id)
    ).scalars().first()
    if run is None:
        raise HTTPException(status_code=404, detail="pipeline run not found")
    return run


def _m16_list_response(
    rows: list[Any],
    schema: type,
    *,
    limit: int,
    offset: int,
    summary_cn: str,
) -> M16ListResponse:
    return M16ListResponse(
        items=[schema.model_validate(row, from_attributes=True).model_dump(mode="json") for row in rows],
        total=len(rows),
        limit=limit,
        offset=offset,
        summary_cn=summary_cn,
    )


def _get_batch_or_404(db: Session, project_id: str, batch_id: str) -> entities.Core3SourceBatch:
    batch = db.execute(
        select(entities.Core3SourceBatch)
        .where(entities.Core3SourceBatch.project_id == project_id)
        .where(entities.Core3SourceBatch.batch_id == batch_id)
    ).scalars().first()
    if not batch:
        raise HTTPException(status_code=404, detail="source batch not found")
    return batch


def _validate_taxonomy_batches(
    db: Session,
    project_id: str,
    category_code: str,
    batch_ids: list[str],
) -> None:
    for batch_id in batch_ids:
        batch = _get_batch_or_404(db, project_id, batch_id)
        if str(batch.category_code).upper() != category_code:
            raise HTTPException(
                status_code=400,
                detail=f"batch {batch_id} belongs to category {batch.category_code}, not {category_code}",
            )


def _param_taxonomy_out(payload: dict[str, Any]) -> ParamTaxonomyOut:
    return ParamTaxonomyOut.model_validate(payload)


def _count_model_rows(db: Session, model_cls: Any, filters: list[Any]) -> int:
    return db.execute(select(func.count()).select_from(model_cls).where(*filters)).scalar_one()


def _claim_model_name(source_status: Any | None, base_claims: list[Any], claim_hits: list[Any]) -> str | None:
    for item in [source_status, *base_claims, *claim_hits]:
        model_name = getattr(item, "model_name", None) if item is not None else None
        if model_name:
            return str(model_name)
    return None


def _sku_base_claim_summary_cn(source_status: Any | None, base_claims: list[Any]) -> str:
    total = len(base_claims)
    if total == 0:
        return "该 SKU 尚未生成基础卖点激活结果，请先执行 M04a。"
    param_only_count = sum(1 for item in base_claims if item.activation_basis == "param_only")
    review_count = sum(1 for item in base_claims if item.review_required)
    status_note = getattr(source_status, "status_note", None) if source_status is not None else None
    if status_note:
        return f"该 SKU 已生成 {total} 个基础卖点，其中 {param_only_count} 个仅由参数支撑、{review_count} 个需要复核。{status_note}"
    return f"该 SKU 已生成 {total} 个基础卖点，其中 {param_only_count} 个仅由参数支撑、{review_count} 个需要复核。"


def _comment_quality_profile_out(row: entities.Core3CommentQualityProfile) -> CommentQualityProfileResponse:
    response = CommentQualityProfileResponse.model_validate(row, from_attributes=True)
    response.quality_summary_cn = response.quality_summary_cn or _comment_profile_summary_cn(row)
    return response


def _comment_atom_out(row: entities.Core3CommentEvidenceAtom) -> CommentEvidenceAtomResponse:
    response = CommentEvidenceAtomResponse.model_validate(row, from_attributes=True)
    response.source_evidence_count = len(_comment_atom_source_evidence_ids(row))
    return response


def _comment_unit_out(row: entities.Core3CommentUnit) -> CommentUnitSourceResponse:
    response = CommentUnitSourceResponse.model_validate(row, from_attributes=True)
    response.source_evidence_count = len(_comment_unit_source_evidence_ids(row))
    return response


def _comment_profile_summary_cn(row: entities.Core3CommentQualityProfile) -> str:
    quality_summary = row.quality_summary or {}
    summary_cn = quality_summary.get("summary_cn")
    if summary_cn:
        return str(summary_cn)
    sample_note = {
        "sufficient": "样本充足",
        "limited": "样本有限",
        "insufficient": "样本不足",
        "unknown": "样本未知",
    }.get(str(row.sample_status), "样本待识别")
    if row.downstream_ready:
        return (
            f"该 SKU 有 {row.comment_unit_count} 个去重评论单元、"
            f"{row.usable_sentence_count} 条可用句级评论证据，可进入后续评论信号抽取。"
        )
    if row.review_required:
        return (
            f"该 SKU 评论{sample_note}，当前有 {row.comment_unit_count} 个去重评论单元、"
            f"{row.usable_sentence_count} 条可用句级评论证据，需要业务或数据复核。"
        )
    return (
        f"该 SKU 评论{sample_note}，当前有 {row.comment_unit_count} 个去重评论单元、"
        f"{row.usable_sentence_count} 条可用句级评论证据。"
    )


def _comment_profile_list_summary_cn(rows: list[Any], total: int) -> str:
    if total == 0:
        return "本批次尚未生成评论质量画像，请先执行 M05。"
    downstream_ready_count = sum(1 for row in rows if row.downstream_ready)
    review_count = sum(1 for row in rows if row.review_required)
    return f"本次返回 {len(rows)} 个 SKU 的评论质量画像，其中 {downstream_ready_count} 个可进入后续评论信号抽取、{review_count} 个需要复核。"


def _comment_unit_list_summary_cn(rows: list[Any], total: int) -> str:
    if total == 0:
        return "该筛选条件下暂无去重评论单元。"
    low_value_count = sum(1 for row in rows if row.low_value_flag)
    return f"本次返回 {len(rows)} 个去重评论单元，其中 {low_value_count} 个仅保留为低信息量来源。"


def _comment_atom_list_summary_cn(rows: list[Any], total: int) -> str:
    if total == 0:
        return "该筛选条件下暂无句级评论证据。"
    usable_count = sum(1 for row in rows if row.usable_for_downstream)
    review_count = sum(1 for row in rows if row.review_required)
    return f"本次返回 {len(rows)} 条句级评论证据，其中 {usable_count} 条可作为后续评论信号、{review_count} 条需要复核。"


def _comment_topic_list_summary_cn(rows: list[Any], total: int) -> str:
    if total == 0:
        return "该筛选条件下暂无评论主题弱提示。"
    service_guardrail_count = sum(1 for row in rows if row.service_guardrail_flag)
    return f"本次返回 {len(rows)} 条评论主题弱提示，其中 {service_guardrail_count} 条属于服务或安装体验线索，不能直接证明产品卖点。"


def _comment_signal_profile_list_summary_cn(rows: list[Any], total: int) -> str:
    if total == 0:
        return "本批次尚未生成 SKU 评论信号画像，请先执行 M06。"
    claim_ready = sum(1 for row in rows if row.claim_validation_ready)
    task_ready = sum(1 for row in rows if row.task_cue_ready)
    battlefield_ready = sum(1 for row in rows if row.battlefield_support_ready)
    return (
        f"本次返回 {len(rows)} 个 SKU 的评论信号画像；"
        f"{claim_ready} 个有卖点体验验证信号，{task_ready} 个有用户任务线索，"
        f"{battlefield_ready} 个有价值战场评论支撑。"
    )


def _comment_signal_list_summary_cn(rows: list[Any], total: int) -> str:
    if total == 0:
        return "该筛选条件下暂无聚合评论信号。"
    signal_types = sorted({row.signal_type for row in rows})
    service_guardrail_count = sum(1 for row in rows if row.service_guardrail_flag)
    return (
        f"本次返回 {len(rows)} 条聚合评论信号，覆盖 {len(signal_types)} 类信号；"
        f"{service_guardrail_count} 条为服务隔离信号，只能用于服务保障相关分析。"
    )


def _comment_signal_candidate_list_summary_cn(rows: list[Any], total: int) -> str:
    if total == 0:
        return "该筛选条件下暂无句级评论信号候选。"
    review_count = sum(1 for row in rows if row.review_required)
    return (
        f"本次返回 {len(rows)} 条句级评论信号候选，其中 {review_count} 条需要复核；"
        "候选只表示评论线索，不代表最终任务、客群、战场或竞品结论。"
    )


def _claim_activation_list_summary_cn(rows: list[Any], total: int) -> str:
    if total == 0:
        return "该 SKU 尚未生成最终卖点激活，请先执行 M04b。"
    review_count = sum(1 for row in rows if row.review_required)
    comment_enhanced_count = sum(1 for row in rows if str(row.activation_basis) == "comment_enhanced")
    param_only_count = sum(1 for row in rows if row.param_only_flag)
    gap_count = sum(1 for row in rows if row.missing_structured_claim_flag)
    return (
        f"本次返回 {len(rows)} 个最终卖点激活结果，其中 {comment_enhanced_count} 个获得评论体验增强、"
        f"{param_only_count} 个主要由参数支撑、{gap_count} 个存在结构化卖点缺口、{review_count} 个需要复核。"
    )


def _claim_validation_list_summary_cn(rows: list[Any], total: int) -> str:
    if total == 0:
        return "该 SKU 尚未生成卖点评论验证结果，请先执行 M04b。"
    enhanced_count = sum(1 for row in rows if str(row.comment_effect) == "enhance")
    weakened_count = sum(1 for row in rows if str(row.comment_effect) == "weaken")
    blocked_count = sum(1 for row in rows if str(row.comment_effect) == "blocked")
    comment_only_count = sum(1 for row in rows if row.comment_only_flag)
    return (
        f"本次返回 {len(rows)} 个卖点评论验证结果，其中 {enhanced_count} 个形成体验增强、"
        f"{weakened_count} 个被评论削弱、{blocked_count} 个被边界拦截、{comment_only_count} 个仅为评论线索。"
    )


def _claim_comment_issue_list_summary_cn(rows: list[Any], total: int) -> str:
    if total == 0:
        return "当前筛选条件下暂无 M04b 复核问题。"
    blocked_count = sum(1 for row in rows if str(row.severity) == "blocked")
    review_count = sum(1 for row in rows if row.review_required)
    issue_types = sorted({str(row.issue_type) for row in rows})
    return (
        f"本次返回 {len(rows)} 条 M04b 复核问题，覆盖 {len(issue_types)} 类问题；"
        f"{blocked_count} 条为阻断级，{review_count} 条需要人工确认后再用于后续推导。"
    )


def _market_profile_list_summary_cn(rows: list[Any], total: int) -> str:
    if total == 0:
        return "该 SKU 尚未生成市场画像，请先执行 M07。"
    windows = sorted({str(row.analysis_window) for row in rows})
    review_count = sum(1 for row in rows if row.review_required)
    return (
        f"本次返回 {len(rows)} 个市场画像窗口，覆盖 {len(windows)} 个观察窗口；"
        f"{review_count} 个窗口需要谨慎使用或补充量价数据。"
    )


def _market_signal_list_summary_cn(rows: list[Any], total: int) -> str:
    if total == 0:
        return "该筛选条件下暂无市场信号。"
    signal_codes = sorted({str(row.signal_code) for row in rows})
    review_count = sum(1 for row in rows if row.review_required)
    return (
        f"本次返回 {len(rows)} 条市场信号，覆盖 {len(signal_codes)} 类信号；"
        f"{review_count} 条为样本或指标不足提示。"
    )


def _comparable_pool_list_summary_cn(rows: list[Any], total: int) -> str:
    if total == 0:
        return "该 SKU 尚未生成市场可比池，请先执行 M07。"
    insufficient_count = sum(1 for row in rows if str(row.sample_status) == "insufficient")
    return (
        f"本次返回 {len(rows)} 个市场可比池；"
        f"{insufficient_count} 个样本不足。可比池只是市场基线，不等同最终竞品。"
    )


def _market_pool_member_list_summary_cn(rows: list[Any], total: int) -> str:
    if total == 0:
        return "该可比池暂无成员关系。"
    self_count = sum(1 for row in rows if row.is_target_self)
    return (
        f"本次返回 {len(rows)} 条池成员关系，其中 {self_count} 条为目标 SKU 自身；"
        "后续候选召回会再排除目标自身。"
    )


def _sku_signal_profile_list_summary_cn(rows: list[Any], total: int) -> str:
    if total == 0:
        return "该 SKU 尚未生成综合信号画像，请先执行 M08。"
    ready_count = sum(1 for row in rows if str(row.profile_status) == "ready")
    review_count = sum(1 for row in rows if row.review_required)
    avg_score = sum(float(row.data_completeness_score or 0) for row in rows) / len(rows)
    return (
        f"本次返回 {len(rows)} 个 SKU 综合信号画像，平均完整度 {avg_score:.2f}；"
        f"{ready_count} 个可直接作为后续输入，{review_count} 个需要复核。"
    )


def _sku_signal_matrix_list_summary_cn(rows: list[Any], total: int) -> str:
    if total == 0:
        return "该 SKU 尚未生成证据矩阵，请先执行 M08。"
    missing_count = sum(1 for row in rows if row.missing_flag)
    domains = sorted({str(row.domain) for row in rows})
    evidence_count = sum(int(row.evidence_count or 0) for row in rows)
    return (
        f"本次返回 {len(rows)} 个证据矩阵格，覆盖 {len(domains)} 类信号域，"
        f"代表证据 {evidence_count} 条，缺口 {missing_count} 个。"
    )


def _sku_downstream_view_list_summary_cn(rows: list[Any], total: int) -> str:
    if total == 0:
        return "该 SKU 尚未生成下游特征视图，请先执行 M08。"
    ready_count = sum(1 for row in rows if row.ready_for_module)
    modules = sorted({str(row.for_module) for row in rows})
    return (
        f"本次返回 {len(rows)} 个下游特征视图，覆盖 {len(modules)} 个后续模块；"
        f"{ready_count} 个已具备输入条件。视图只提供输入，不生成最终业务结论。"
    )


def _comment_atom_source_evidence_ids(row: entities.Core3CommentEvidenceAtom) -> set[str]:
    evidence_ids: set[str] = set()
    for field_name in (
        "source_sentence_evidence_ids",
        "source_comment_evidence_ids",
        "source_dimension_evidence_ids",
        "source_quality_evidence_ids",
    ):
        for evidence_id in getattr(row, field_name, None) or []:
            evidence_ids.add(str(evidence_id))
    return evidence_ids


def _comment_unit_source_evidence_ids(row: entities.Core3CommentUnit) -> set[str]:
    evidence_ids: set[str] = set()
    for field_name in (
        "source_comment_evidence_ids",
        "source_sentence_evidence_ids",
        "source_dimension_evidence_ids",
        "source_quality_evidence_ids",
    ):
        for evidence_id in getattr(row, field_name, None) or []:
            evidence_ids.add(str(evidence_id))
    return evidence_ids


def _comment_atom_filters(
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    sku_code: str,
    primary_domain_hint: str | None,
    sentiment_hint: str | None,
    low_value_flag: bool | None,
    usable_for_downstream: bool | None,
    topic_code: str | None,
) -> list[Any]:
    filters: list[Any] = [
        entities.Core3CommentEvidenceAtom.project_id == project_id,
        entities.Core3CommentEvidenceAtom.category_code == category_code,
        entities.Core3CommentEvidenceAtom.batch_id == batch_id,
        entities.Core3CommentEvidenceAtom.sku_code == sku_code,
        entities.Core3CommentEvidenceAtom.is_current.is_(True),
    ]
    if primary_domain_hint is not None:
        filters.append(entities.Core3CommentEvidenceAtom.primary_domain_hint == primary_domain_hint)
    if sentiment_hint is not None:
        filters.append(entities.Core3CommentEvidenceAtom.sentiment_hint == sentiment_hint)
    if low_value_flag is not None:
        filters.append(entities.Core3CommentEvidenceAtom.low_value_flag.is_(low_value_flag))
    if usable_for_downstream is not None:
        filters.append(entities.Core3CommentEvidenceAtom.usable_for_downstream.is_(usable_for_downstream))
    if topic_code is not None:
        topic_subquery = (
            select(entities.Core3CommentTopicHint.comment_evidence_id)
            .where(entities.Core3CommentTopicHint.project_id == project_id)
            .where(entities.Core3CommentTopicHint.category_code == category_code)
            .where(entities.Core3CommentTopicHint.batch_id == batch_id)
            .where(entities.Core3CommentTopicHint.sku_code == sku_code)
            .where(entities.Core3CommentTopicHint.is_current.is_(True))
            .where(entities.Core3CommentTopicHint.topic_code == topic_code)
        )
        filters.append(entities.Core3CommentEvidenceAtom.comment_evidence_id.in_(topic_subquery))
    return filters


def _row_registry_out(row: entities.Core3SourceRowRegistry) -> Core3SourceRowRegistryOut:
    return Core3SourceRowRegistryOut(
        row_registry_id=row.row_registry_id,
        batch_id=row.batch_id,
        project_id=row.project_id,
        category_code=row.category_code,
        source_table=row.source_table,
        source_pk=row.source_pk,
        source_pk_strategy=row.source_pk_strategy,
        source_row_id=row.source_row_id,
        row_hash=row.row_hash,
        hash_version=row.hash_version,
        previous_batch_id=row.previous_batch_id,
        previous_row_hash=row.previous_row_hash,
        previous_operation_type=row.previous_operation_type,
        sku_code_candidate=row.sku_code_candidate,
        model_name_raw=row.model_name_raw,
        brand_raw=row.brand_raw,
        category_raw=row.category_raw,
        write_time=row.write_time,
        business_key_json=row.business_key_json or {},
        source_field_presence_json=row.source_field_presence_json or {},
        operation_type=row.operation_type,
        change_reason=row.change_reason,
        affected_modules=_affected_module_codes(row.affected_modules or []),
        quality_hint=row.quality_hint or {},
        review_required=row.review_required,
        review_status=row.review_status,
        created_at=row.created_at,
    )


def _affected_module_codes(affected_modules: list[Any]) -> list[str]:
    codes: list[str] = []
    for module in affected_modules:
        if isinstance(module, dict):
            code = module.get("module_code")
        else:
            code = module
        if code and code not in codes:
            codes.append(str(code))
    return codes


def _api_repository(db: Session, project_id: str, category_code: str = "TV") -> Core3RealDataApiRepository:
    return Core3RealDataApiRepository(_repository_context(db, project_id, category_code))


def _raise_api_error(exc: ApiQueryError) -> None:
    detail = {"error_code": exc.error_code, "message_cn": exc.message_cn}
    if exc.action_hint_cn:
        detail["action_hint_cn"] = exc.action_hint_cn
    raise HTTPException(status_code=exc.status_code, detail=detail)


def _repository_context(db: Session, project_id: str, category_code: str) -> Core3RepositoryContext:
    return Core3RepositoryContext(db=db, project_id=project_id, category_code=category_code)


def _clean_sku_summary(row: entities.Core3CleanSku) -> CleanSkuSummary:
    coverage_json = row.coverage_json or {}
    return CleanSkuSummary(
        clean_sku_id=row.clean_sku_id,
        project_id=row.project_id,
        category_code=row.category_code,
        batch_id=row.batch_id,
        sku_code=row.sku_code,
        model_name=row.model_name,
        brand_name=row.brand_name,
        category_name=row.category_name,
        source_tables=row.source_tables or [],
        coverage=CleanCoverageSummary(
            market=coverage_json.get("market", {}),
            attribute=coverage_json.get("attribute", {}),
            claim=coverage_json.get("claim", {}),
            comment=coverage_json.get("comment", {}),
            missing_signals=row.missing_signals_json or {},
            field_conflicts=row.field_conflicts_json or {},
        ),
        quality_status=row.quality_status,
        quality_flags=row.quality_flags or [],
        review_required=row.review_required,
        review_status=row.review_status,
        clean_hash=row.clean_hash,
    )


def _issue_counts_from_rows(rows: list[entities.Core3DataQualityIssue]) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    counts = {
        "info": 0,
        "warning": 0,
        "error": 0,
        "review_required": 0,
        "by_type": by_type,
    }
    for row in rows:
        if row.severity in {"info", "warning", "error"}:
            counts[row.severity] += 1
        if row.review_required:
            counts["review_required"] += 1
        by_type[row.issue_type] = by_type.get(row.issue_type, 0) + 1
    return counts


def _quality_summary_cn(issue_counts: dict[str, Any], review_required: bool) -> str:
    total = int(issue_counts.get("info", 0)) + int(issue_counts.get("warning", 0)) + int(issue_counts.get("error", 0))
    review_count = int(issue_counts.get("review_required", 0))
    if total == 0:
        return "本批次清洗未发现需要提示的数据质量问题。"
    if review_required or review_count:
        return f"本批次发现 {total} 个数据质量提示，其中 {review_count} 个需要业务或数据复核。"
    return f"本批次发现 {total} 个数据质量提示，当前不阻断后续分析。"


def _get_evidence_or_404(db: Session, project_id: str, evidence_id: str) -> entities.Core3EvidenceAtom:
    record = db.execute(
        select(entities.Core3EvidenceAtom)
        .where(entities.Core3EvidenceAtom.project_id == project_id)
        .where(entities.Core3EvidenceAtom.evidence_id == evidence_id)
    ).scalars().first()
    if record is None:
        raise HTTPException(status_code=404, detail="evidence atom not found")
    return record


def _source_clean_tables_for_evidence(
    db: Session,
    project_id: str,
    category_code: str,
    batch_id: str,
) -> list[str]:
    rows = db.execute(
        select(entities.Core3EvidenceAtom.clean_table)
        .where(entities.Core3EvidenceAtom.project_id == project_id)
        .where(entities.Core3EvidenceAtom.category_code == category_code)
        .where(entities.Core3EvidenceAtom.batch_id == batch_id)
        .distinct()
    ).all()
    present_tables = {str(row[0]) for row in rows if row[0]}
    return [table for table in CORE3_M02_CLEAN_SOURCE_TABLES if table in present_tables]


def _evidence_summary_out(
    *,
    project_id: str,
    category_code: str,
    batch_id: str,
    summary: dict[str, Any],
    link_count: int,
    source_clean_tables: list[str],
) -> EvidenceSummary:
    counts = _evidence_counts_out(summary, link_count)
    missing_clean_tables = [table for table in CORE3_M02_CLEAN_SOURCE_TABLES if table not in source_clean_tables]
    low_confidence_reasons = {}
    if counts.low_confidence:
        low_confidence_reasons["base_confidence_below_0.55"] = counts.low_confidence
    return EvidenceSummary(
        project_id=project_id,
        category_code=category_code,
        batch_id=batch_id,
        evidence_counts=counts,
        source_clean_tables=source_clean_tables,
        missing_clean_tables=missing_clean_tables,
        low_confidence_reasons=low_confidence_reasons,
        quality_summary_cn=_evidence_quality_summary_cn(counts),
        review_required=counts.review_required > 0,
    )


def _evidence_counts_out(summary: dict[str, Any], link_count: int) -> EvidenceCounts:
    by_type = _normalized_count_map(summary.get("by_type", {}), {item.value for item in Core3EvidenceType})
    by_status = _normalized_count_map(summary.get("by_status", {}), {item.value for item in Core3EvidenceStatus})
    return EvidenceCounts(
        sku_fact=by_type.get(Core3EvidenceType.SKU_FACT.value, 0),
        market_fact=by_type.get(Core3EvidenceType.MARKET_FACT.value, 0),
        param_raw=by_type.get(Core3EvidenceType.PARAM_RAW.value, 0),
        promo_raw=by_type.get(Core3EvidenceType.PROMO_RAW.value, 0),
        promo_sentence=by_type.get(Core3EvidenceType.PROMO_SENTENCE.value, 0),
        comment_raw=by_type.get(Core3EvidenceType.COMMENT_RAW.value, 0),
        comment_sentence=by_type.get(Core3EvidenceType.COMMENT_SENTENCE.value, 0),
        comment_dimension=by_type.get(Core3EvidenceType.COMMENT_DIMENSION.value, 0),
        quality_issue=by_type.get(Core3EvidenceType.QUALITY_ISSUE.value, 0),
        link=link_count,
        current=int(summary.get("current", 0) or 0),
        inactive=int(summary.get("inactive", 0) or 0),
        superseded=int(summary.get("superseded", 0) or 0),
        skipped=int(summary.get("skipped", 0) or 0),
        low_confidence=int(summary.get("low_confidence", 0) or 0),
        review_required=int(summary.get("review_required", 0) or 0),
        by_type=by_type,
        by_status=by_status,
        by_confidence_level=_normalized_count_map(
            summary.get("by_confidence_level", {}),
            {"high", "medium", "low", "unknown"},
        ),
    )


def _normalized_count_map(values: dict[str, Any], allowed_values: set[str]) -> dict[str, int]:
    return {str(key): int(value) for key, value in values.items() if str(key) in allowed_values}


def _evidence_quality_summary_cn(counts: EvidenceCounts) -> str:
    total = counts.current + counts.inactive + counts.superseded + counts.skipped
    if total == 0:
        return "本批次尚未生成 evidence，请先执行 M02 证据原子层。"
    if counts.review_required:
        return f"本批次已生成 {total} 条 evidence、{counts.link} 条证据关系，其中 {counts.review_required} 条需要复核。"
    if counts.low_confidence:
        return f"本批次已生成 {total} 条 evidence、{counts.link} 条证据关系，其中 {counts.low_confidence} 条置信度偏低。"
    return f"本批次已生成 {total} 条 evidence、{counts.link} 条证据关系，可供后续画像和竞品推导模块使用。"


def _evidence_trace_response(
    db: Session,
    project_id: str,
    record: entities.Core3EvidenceAtom,
) -> EvidenceTraceResponse:
    context = _repository_context(db, project_id, record.category_code)
    atom_repository = EvidenceAtomRepository(context)
    link_repository = EvidenceLinkRepository(context)
    upstream_links = link_repository.list_links(record.evidence_id, direction="to", limit=500)
    downstream_links = link_repository.list_links(record.evidence_id, direction="from", limit=500)
    related_records = []
    seen_ids: set[str] = set()
    for link in [*upstream_links, *downstream_links]:
        related_id = link.from_evidence_id if link.from_evidence_id != record.evidence_id else link.to_evidence_id
        if related_id in seen_ids:
            continue
        seen_ids.add(related_id)
        related_record = atom_repository.get_by_id(related_id)
        if related_record is not None:
            related_records.append(related_record)
    return EvidenceTraceResponse(
        evidence=EvidenceAtomRead.model_validate(record, from_attributes=True),
        upstream_links=[EvidenceLinkRead.model_validate(link, from_attributes=True) for link in upstream_links],
        downstream_links=[EvidenceLinkRead.model_validate(link, from_attributes=True) for link in downstream_links],
        related_evidence=[EvidenceAtomListItem.model_validate(item, from_attributes=True) for item in related_records],
        trace_summary_cn=_evidence_trace_summary_cn(record, len(upstream_links) + len(downstream_links)),
    )


def _evidence_trace_summary_cn(record: entities.Core3EvidenceAtom, link_count: int) -> str:
    source_part = record.source_table or "M01 清洗结果"
    if record.source_row_id:
        source_part = f"{source_part} / {record.source_row_id}"
    return f"该证据来自 {record.clean_table}，可回溯到 {source_part}；当前关联 {link_count} 条证据关系。"


def _links_for_evidence_rows(
    db: Session,
    project_id: str,
    category_code: str,
    rows: list[entities.Core3EvidenceAtom],
) -> list[EvidenceLinkRead]:
    context = _repository_context(db, project_id, category_code)
    link_repository = EvidenceLinkRepository(context)
    links_by_id: dict[str, entities.Core3EvidenceLink] = {}
    for row in rows:
        for link in link_repository.list_links(row.evidence_id, direction="both", limit=500):
            links_by_id.setdefault(link.link_id, link)
    return [EvidenceLinkRead.model_validate(link, from_attributes=True) for link in links_by_id.values()]


def _normalize_evidence_types(values: list[str]) -> list[str]:
    normalized_values = []
    for value in _split_query_values(values):
        try:
            normalized_values.append(Core3EvidenceType(value).value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"unknown evidence_type: {value}") from exc
    return normalized_values


def _normalize_evidence_statuses(values: list[str]) -> list[str]:
    normalized_values = []
    for value in _split_query_values(values):
        try:
            normalized_values.append(Core3EvidenceStatus(value).value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"unknown evidence_status: {value}") from exc
    return normalized_values


def _normalize_evidence_link_type(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return Core3EvidenceLinkType(value).value
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"unknown link_type: {value}") from exc


def _split_query_values(values: list[str]) -> list[str]:
    normalized_values: list[str] = []
    for raw_value in values:
        normalized_values.extend(item.strip() for item in raw_value.split(",") if item.strip())
    return normalized_values
