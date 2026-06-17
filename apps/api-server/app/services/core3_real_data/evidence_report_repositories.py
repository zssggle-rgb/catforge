"""M15 evidence report repository boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Sequence

from pydantic import BaseModel
from sqlalchemy import func, select

from app.models import entities
from app.services.core3_real_data.repositories import Core3BaseRepository


class M15InputBlockedError(RuntimeError):
    pass


@dataclass(frozen=True)
class M15TargetReportInput:
    selection_run: entities.Core3CompetitorSelectionRun
    selections: tuple[entities.Core3CompetitorSelection, ...]
    slot_decisions: tuple[entities.Core3CompetitorSlotDecision, ...]
    audits: tuple[entities.Core3CompetitorSelectionAudit, ...]
    selection_issues: tuple[entities.Core3CompetitorSelectionReviewIssue, ...]
    component_scores: dict[str, entities.Core3CandidateComponentScore]
    explanations_by_selection: dict[str, tuple[entities.Core3CandidateComponentExplanation, ...]]
    recall_reasons_by_candidate: dict[str, tuple[entities.Core3CandidateRecallReason, ...]]
    profiles_by_sku: dict[str, entities.Core3SkuSignalProfile]
    task_scores_by_sku: dict[str, tuple[entities.Core3SkuTaskScore, ...]]
    target_group_scores_by_sku: dict[str, tuple[entities.Core3SkuTargetGroupScore, ...]]
    battlefield_scores_by_sku: dict[str, tuple[entities.Core3SkuBattlefieldScore, ...]]
    claim_layers_by_sku: dict[str, tuple[entities.Core3SkuClaimValueLayer, ...]]
    evidence_atoms: dict[str, entities.Core3EvidenceAtom]


@dataclass(frozen=True)
class EvidenceReportRepositoryWriteResult:
    records: tuple[Any, ...]
    created_count: int = 0
    reused_count: int = 0
    updated_count: int = 0


class EvidenceReportRepository(Core3BaseRepository):
    def assert_inputs_ready(self, batch_id: str) -> None:
        required_counts = {
            "M14 三槽位选择运行": self._count_current_rows(entities.Core3CompetitorSelectionRun, batch_id),
            "M14 槽位决策": self._count_current_rows(entities.Core3CompetitorSlotDecision, batch_id),
            "M14 候选审计": self._count_current_rows(entities.Core3CompetitorSelectionAudit, batch_id),
        }
        missing = [name for name, count in required_counts.items() if int(count) == 0]
        if missing:
            raise M15InputBlockedError(f"M15 需要先完成上游产物：{', '.join(missing)}。")

    def list_report_inputs(
        self,
        batch_id: str,
        *,
        sku_scope: Sequence[str] = (),
        rule_version: str,
        max_targets: int | None = None,
        only_unreported: bool = False,
    ) -> list[M15TargetReportInput]:
        target_codes = self.list_current_selection_target_codes(
            batch_id,
            sku_scope=sku_scope,
            rule_version=rule_version,
            max_targets=max_targets,
            only_unreported=only_unreported,
        )
        if not target_codes:
            return []
        run_stmt = self._current_query(entities.Core3CompetitorSelectionRun, batch_id).order_by(
            entities.Core3CompetitorSelectionRun.target_sku_code,
            entities.Core3CompetitorSelectionRun.updated_at.desc(),
        ).where(entities.Core3CompetitorSelectionRun.target_sku_code.in_(target_codes))
        selection_runs = self._paged_scalars(run_stmt, limit=100000, offset=0)
        if not selection_runs:
            return []

        selection_run_ids = tuple({row.selection_run_id for row in selection_runs})
        target_sku_codes = tuple({row.target_sku_code for row in selection_runs})
        selections_by_run = self._list_by_selection_run(
            entities.Core3CompetitorSelection,
            batch_id,
            selection_run_ids,
            order_by=(
                entities.Core3CompetitorSelection.selection_run_id,
                entities.Core3CompetitorSelection.selection_rank,
                entities.Core3CompetitorSelection.slot_code,
            ),
        )
        slot_decisions_by_run = self._list_by_selection_run(
            entities.Core3CompetitorSlotDecision,
            batch_id,
            selection_run_ids,
            order_by=(
                entities.Core3CompetitorSlotDecision.selection_run_id,
                entities.Core3CompetitorSlotDecision.slot_code,
            ),
        )
        audits_by_run = self._list_by_selection_run(
            entities.Core3CompetitorSelectionAudit,
            batch_id,
            selection_run_ids,
            order_by=(
                entities.Core3CompetitorSelectionAudit.selection_run_id,
                entities.Core3CompetitorSelectionAudit.audit_decision,
                entities.Core3CompetitorSelectionAudit.candidate_sku_code,
            ),
        )
        issues_by_run = self._list_by_selection_run(
            entities.Core3CompetitorSelectionReviewIssue,
            batch_id,
            selection_run_ids,
            order_by=(
                entities.Core3CompetitorSelectionReviewIssue.selection_run_id,
                entities.Core3CompetitorSelectionReviewIssue.issue_level.desc(),
                entities.Core3CompetitorSelectionReviewIssue.issue_type,
            ),
        )

        selected_rows = [item for rows in selections_by_run.values() for item in rows]
        audit_rows = [item for rows in audits_by_run.values() for item in rows]
        component_score_ids = tuple({row.candidate_component_score_id for row in selected_rows + audit_rows if row.candidate_component_score_id})
        pool_ids = tuple({row.candidate_pool_id for row in selected_rows + audit_rows if row.candidate_pool_id})
        selected_selection_ids = tuple({row.competitor_selection_id for row in selected_rows})
        sku_codes = tuple(
            sorted(
                {
                    *target_sku_codes,
                    *(row.candidate_sku_code for row in selected_rows if row.candidate_sku_code),
                    *(row.candidate_sku_code for row in audit_rows if row.candidate_sku_code),
                }
            )
        )

        component_scores = self._list_component_scores(batch_id, component_score_ids)
        explanations_by_component = self._list_explanations(batch_id, component_score_ids)
        recall_reasons_by_pool = self._list_recall_reasons(batch_id, pool_ids)
        profiles_by_sku = self._list_profiles(batch_id, sku_codes)
        task_scores_by_sku = self._list_task_scores(batch_id, sku_codes)
        target_group_scores_by_sku = self._list_target_group_scores(batch_id, sku_codes)
        battlefield_scores_by_sku = self._list_battlefield_scores(batch_id, sku_codes)
        claim_layers_by_sku = self._list_claim_layers(batch_id, sku_codes)

        evidence_ids = _collect_evidence_ids(
            selected_rows,
            audit_rows,
            [item for rows in slot_decisions_by_run.values() for item in rows],
            [item for rows in issues_by_run.values() for item in rows],
            [item for rows in explanations_by_component.values() for item in rows],
            [item for rows in recall_reasons_by_pool.values() for item in rows],
            profiles_by_sku.values(),
            [item for rows in task_scores_by_sku.values() for item in rows],
            [item for rows in target_group_scores_by_sku.values() for item in rows],
            [item for rows in battlefield_scores_by_sku.values() for item in rows],
            [item for rows in claim_layers_by_sku.values() for item in rows],
        )
        evidence_atoms = self._list_evidence_atoms(batch_id, evidence_ids)

        inputs: list[M15TargetReportInput] = []
        for run in selection_runs:
            selections = tuple(selections_by_run.get(run.selection_run_id, ()))
            inputs.append(
                M15TargetReportInput(
                    selection_run=run,
                    selections=selections,
                    slot_decisions=tuple(slot_decisions_by_run.get(run.selection_run_id, ())),
                    audits=tuple(audits_by_run.get(run.selection_run_id, ())),
                    selection_issues=tuple(issues_by_run.get(run.selection_run_id, ())),
                    component_scores={row.candidate_component_score_id: row for row in component_scores.values()},
                    explanations_by_selection={
                        row.competitor_selection_id: tuple(
                            explanations_by_component.get(row.candidate_component_score_id, ())
                        )
                        for row in selections
                        if row.competitor_selection_id in selected_selection_ids
                    },
                    recall_reasons_by_candidate={
                        row.candidate_sku_code: tuple(recall_reasons_by_pool.get(row.candidate_pool_id, ()))
                        for row in selections
                    },
                    profiles_by_sku=profiles_by_sku,
                    task_scores_by_sku=task_scores_by_sku,
                    target_group_scores_by_sku=target_group_scores_by_sku,
                    battlefield_scores_by_sku=battlefield_scores_by_sku,
                    claim_layers_by_sku=claim_layers_by_sku,
                    evidence_atoms=evidence_atoms,
                )
            )
        return inputs

    def list_current_selection_target_codes(
        self,
        batch_id: str,
        *,
        sku_scope: Sequence[str] = (),
        rule_version: str,
        max_targets: int | None = None,
        only_unreported: bool = False,
    ) -> tuple[str, ...]:
        sku_scope_tuple = tuple(sorted({code for code in sku_scope if code}))
        stmt = (
            select(entities.Core3CompetitorSelectionRun.target_sku_code)
            .distinct()
            .where(entities.Core3CompetitorSelectionRun.project_id == self.project_id)
            .where(entities.Core3CompetitorSelectionRun.category_code == self.category_code.value)
            .where(entities.Core3CompetitorSelectionRun.batch_id == batch_id)
            .where(entities.Core3CompetitorSelectionRun.is_current.is_(True))
            .order_by(entities.Core3CompetitorSelectionRun.target_sku_code)
        )
        if sku_scope_tuple:
            stmt = stmt.where(entities.Core3CompetitorSelectionRun.target_sku_code.in_(sku_scope_tuple))
        if only_unreported:
            stmt = stmt.where(~self._report_payload_exists(batch_id, rule_version))
        limit = max_targets if max_targets is not None and max_targets > 0 else 100000
        return tuple(str(row[0]) for row in self.db.execute(stmt.limit(limit)).all())

    def count_current_selection_targets(self, batch_id: str, *, sku_scope: Sequence[str] = ()) -> int:
        sku_scope_tuple = tuple(sorted({code for code in sku_scope if code}))
        stmt = (
            select(func.count(func.distinct(entities.Core3CompetitorSelectionRun.target_sku_code)))
            .where(entities.Core3CompetitorSelectionRun.project_id == self.project_id)
            .where(entities.Core3CompetitorSelectionRun.category_code == self.category_code.value)
            .where(entities.Core3CompetitorSelectionRun.batch_id == batch_id)
            .where(entities.Core3CompetitorSelectionRun.is_current.is_(True))
        )
        if sku_scope_tuple:
            stmt = stmt.where(entities.Core3CompetitorSelectionRun.target_sku_code.in_(sku_scope_tuple))
        return int(self.db.execute(stmt).scalar_one())

    def count_current_report_payload_targets(
        self,
        batch_id: str,
        *,
        sku_scope: Sequence[str] = (),
        rule_version: str,
    ) -> int:
        sku_scope_tuple = tuple(sorted({code for code in sku_scope if code}))
        stmt = (
            select(func.count(func.distinct(entities.Core3TargetReportPayload.target_sku_code)))
            .where(entities.Core3TargetReportPayload.project_id == self.project_id)
            .where(entities.Core3TargetReportPayload.category_code == self.category_code.value)
            .where(entities.Core3TargetReportPayload.batch_id == batch_id)
            .where(entities.Core3TargetReportPayload.rule_version == rule_version)
            .where(entities.Core3TargetReportPayload.is_current.is_(True))
        )
        if sku_scope_tuple:
            stmt = stmt.where(entities.Core3TargetReportPayload.target_sku_code.in_(sku_scope_tuple))
        return int(self.db.execute(stmt).scalar_one())

    def save_evidence_cards(self, records: Sequence[Any]) -> EvidenceReportRepositoryWriteResult:
        return self._save_many(
            entities.Core3ReportEvidenceCard,
            records,
            unique_fields=("batch_id", "target_sku_code", "competitor_sku_code", "slot_code", "rule_version"),
        )

    def save_report_payloads(self, records: Sequence[Any]) -> EvidenceReportRepositoryWriteResult:
        return self._save_many(
            entities.Core3TargetReportPayload,
            records,
            unique_fields=("batch_id", "target_sku_code", "selection_run_id", "rule_version"),
        )

    def save_report_sections(self, records: Sequence[Any]) -> EvidenceReportRepositoryWriteResult:
        return self._save_many(
            entities.Core3ReportSection,
            records,
            unique_fields=("batch_id", "target_sku_code", "selection_run_id", "section_code", "rule_version"),
        )

    def save_report_exports(self, records: Sequence[Any]) -> EvidenceReportRepositoryWriteResult:
        return self._save_many(
            entities.Core3ReportExport,
            records,
            unique_fields=("batch_id", "target_sku_code", "selection_run_id", "export_type", "rule_version"),
        )

    def save_review_issues(self, records: Sequence[Any]) -> EvidenceReportRepositoryWriteResult:
        return self._save_many(
            entities.Core3ReportReviewIssue,
            records,
            unique_fields=(
                "batch_id",
                "target_sku_code",
                "selection_run_id",
                "issue_scope",
                "section_code",
                "issue_type",
                "input_fingerprint",
            ),
        )

    def list_current_report_payloads(
        self,
        batch_id: str,
        *,
        target_sku_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3TargetReportPayload]:
        stmt = self._current_query(entities.Core3TargetReportPayload, batch_id).order_by(
            entities.Core3TargetReportPayload.target_sku_code,
            entities.Core3TargetReportPayload.updated_at.desc(),
        )
        if target_sku_code is not None:
            stmt = stmt.where(entities.Core3TargetReportPayload.target_sku_code == target_sku_code)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_evidence_cards(
        self,
        batch_id: str,
        *,
        target_sku_code: str | None = None,
        slot_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3ReportEvidenceCard]:
        stmt = self._current_query(entities.Core3ReportEvidenceCard, batch_id).order_by(
            entities.Core3ReportEvidenceCard.target_sku_code,
            entities.Core3ReportEvidenceCard.slot_code,
            entities.Core3ReportEvidenceCard.competitor_sku_code,
        )
        if target_sku_code is not None:
            stmt = stmt.where(entities.Core3ReportEvidenceCard.target_sku_code == target_sku_code)
        if slot_code is not None:
            stmt = stmt.where(entities.Core3ReportEvidenceCard.slot_code == slot_code)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_report_sections(
        self,
        batch_id: str,
        *,
        target_sku_code: str | None = None,
        section_code: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3ReportSection]:
        stmt = self._current_query(entities.Core3ReportSection, batch_id).order_by(
            entities.Core3ReportSection.target_sku_code,
            entities.Core3ReportSection.section_order,
        )
        if target_sku_code is not None:
            stmt = stmt.where(entities.Core3ReportSection.target_sku_code == target_sku_code)
        if section_code is not None:
            stmt = stmt.where(entities.Core3ReportSection.section_code == section_code)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_report_exports(
        self,
        batch_id: str,
        *,
        target_sku_code: str | None = None,
        export_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3ReportExport]:
        stmt = self._current_query(entities.Core3ReportExport, batch_id).order_by(
            entities.Core3ReportExport.target_sku_code,
            entities.Core3ReportExport.export_type,
        )
        if target_sku_code is not None:
            stmt = stmt.where(entities.Core3ReportExport.target_sku_code == target_sku_code)
        if export_type is not None:
            stmt = stmt.where(entities.Core3ReportExport.export_type == export_type)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def list_current_review_issues(
        self,
        batch_id: str,
        *,
        target_sku_code: str | None = None,
        issue_type: str | None = None,
        issue_level: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[entities.Core3ReportReviewIssue]:
        stmt = self._current_query(entities.Core3ReportReviewIssue, batch_id).order_by(
            entities.Core3ReportReviewIssue.issue_level.desc(),
            entities.Core3ReportReviewIssue.target_sku_code,
            entities.Core3ReportReviewIssue.issue_type,
        )
        if target_sku_code is not None:
            stmt = stmt.where(entities.Core3ReportReviewIssue.target_sku_code == target_sku_code)
        if issue_type is not None:
            stmt = stmt.where(entities.Core3ReportReviewIssue.issue_type == issue_type)
        if issue_level is not None:
            stmt = stmt.where(entities.Core3ReportReviewIssue.issue_level == issue_level)
        return self._paged_scalars(stmt, limit=limit, offset=offset)

    def get_evidence_by_short_ref(
        self,
        batch_id: str,
        *,
        target_sku_code: str,
        short_ref: str,
    ) -> entities.Core3EvidenceAtom | None:
        payload = self.list_current_report_payloads(batch_id, target_sku_code=target_sku_code, limit=1)
        if not payload:
            return None
        for item in payload[0].short_evidence_map_json or []:
            if str(item.get("short_ref")) == short_ref and item.get("evidence_id"):
                return self.db.get(entities.Core3EvidenceAtom, str(item["evidence_id"]))
        return None

    def _base_query(self, model_cls: Any, batch_id: str) -> Any:
        return (
            select(model_cls)
            .where(model_cls.project_id == self.project_id)
            .where(model_cls.category_code == self.category_code.value)
            .where(model_cls.batch_id == batch_id)
        )

    def _current_query(self, model_cls: Any, batch_id: str) -> Any:
        return self._base_query(model_cls, batch_id).where(model_cls.is_current.is_(True))

    def _paged_scalars(self, stmt: Any, *, limit: int, offset: int) -> list[Any]:
        normalized_limit, normalized_offset = self.pagination(limit=limit, offset=offset, max_limit=100000)
        return list(self.db.execute(stmt.limit(normalized_limit).offset(normalized_offset)).scalars())

    def _count_current_rows(self, model_cls: Any, batch_id: str, **filters: Any) -> int:
        stmt = self._current_query(model_cls, batch_id)
        for field_name, value in filters.items():
            stmt = stmt.where(getattr(model_cls, field_name) == value)
        return int(self.db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())

    def _report_payload_exists(self, batch_id: str, rule_version: str) -> Any:
        return (
            select(entities.Core3TargetReportPayload.target_report_payload_id)
            .where(entities.Core3TargetReportPayload.project_id == self.project_id)
            .where(entities.Core3TargetReportPayload.category_code == self.category_code.value)
            .where(entities.Core3TargetReportPayload.batch_id == batch_id)
            .where(entities.Core3TargetReportPayload.rule_version == rule_version)
            .where(entities.Core3TargetReportPayload.is_current.is_(True))
            .where(
                entities.Core3TargetReportPayload.target_sku_code
                == entities.Core3CompetitorSelectionRun.target_sku_code
            )
            .exists()
        )

    def _list_by_selection_run(
        self,
        model_cls: Any,
        batch_id: str,
        selection_run_ids: tuple[str, ...],
        *,
        order_by: tuple[Any, ...],
    ) -> dict[str, list[Any]]:
        if not selection_run_ids:
            return {}
        stmt = (
            self._current_query(model_cls, batch_id)
            .where(model_cls.selection_run_id.in_(selection_run_ids))
            .order_by(*order_by)
        )
        result: dict[str, list[Any]] = {}
        for row in self._paged_scalars(stmt, limit=100000, offset=0):
            result.setdefault(row.selection_run_id, []).append(row)
        return result

    def _list_component_scores(
        self,
        batch_id: str,
        component_score_ids: tuple[str, ...],
    ) -> dict[str, entities.Core3CandidateComponentScore]:
        if not component_score_ids:
            return {}
        stmt = self._current_query(entities.Core3CandidateComponentScore, batch_id).where(
            entities.Core3CandidateComponentScore.candidate_component_score_id.in_(component_score_ids)
        )
        return {row.candidate_component_score_id: row for row in self._paged_scalars(stmt, limit=100000, offset=0)}

    def _list_explanations(
        self,
        batch_id: str,
        component_score_ids: tuple[str, ...],
    ) -> dict[str, list[entities.Core3CandidateComponentExplanation]]:
        if not component_score_ids:
            return {}
        stmt = (
            self._current_query(entities.Core3CandidateComponentExplanation, batch_id)
            .where(entities.Core3CandidateComponentExplanation.candidate_component_score_id.in_(component_score_ids))
            .order_by(
                entities.Core3CandidateComponentExplanation.candidate_component_score_id,
                entities.Core3CandidateComponentExplanation.component_code,
            )
        )
        result: dict[str, list[entities.Core3CandidateComponentExplanation]] = {}
        for row in self._paged_scalars(stmt, limit=100000, offset=0):
            result.setdefault(row.candidate_component_score_id, []).append(row)
        return result

    def _list_recall_reasons(
        self,
        batch_id: str,
        pool_ids: tuple[str, ...],
    ) -> dict[str, list[entities.Core3CandidateRecallReason]]:
        if not pool_ids:
            return {}
        stmt = (
            self._current_query(entities.Core3CandidateRecallReason, batch_id)
            .where(entities.Core3CandidateRecallReason.candidate_pool_id.in_(pool_ids))
            .order_by(
                entities.Core3CandidateRecallReason.candidate_pool_id,
                entities.Core3CandidateRecallReason.support_score.desc(),
                entities.Core3CandidateRecallReason.recall_source,
            )
        )
        result: dict[str, list[entities.Core3CandidateRecallReason]] = {}
        for row in self._paged_scalars(stmt, limit=100000, offset=0):
            result.setdefault(row.candidate_pool_id, []).append(row)
        return result

    def _list_profiles(self, batch_id: str, sku_codes: tuple[str, ...]) -> dict[str, entities.Core3SkuSignalProfile]:
        if not sku_codes:
            return {}
        stmt = (
            self._current_query(entities.Core3SkuSignalProfile, batch_id)
            .where(entities.Core3SkuSignalProfile.sku_code.in_(sku_codes))
            .order_by(
                entities.Core3SkuSignalProfile.sku_code,
                entities.Core3SkuSignalProfile.data_completeness_score.desc(),
            )
        )
        result: dict[str, entities.Core3SkuSignalProfile] = {}
        for row in self._paged_scalars(stmt, limit=100000, offset=0):
            result.setdefault(row.sku_code, row)
        return result

    def _list_task_scores(self, batch_id: str, sku_codes: tuple[str, ...]) -> dict[str, tuple[entities.Core3SkuTaskScore, ...]]:
        return self._list_sku_rows(entities.Core3SkuTaskScore, batch_id, sku_codes, entities.Core3SkuTaskScore.task_score.desc())

    def _list_target_group_scores(self, batch_id: str, sku_codes: tuple[str, ...]) -> dict[str, tuple[entities.Core3SkuTargetGroupScore, ...]]:
        return self._list_sku_rows(entities.Core3SkuTargetGroupScore, batch_id, sku_codes, entities.Core3SkuTargetGroupScore.target_group_score.desc())

    def _list_battlefield_scores(self, batch_id: str, sku_codes: tuple[str, ...]) -> dict[str, tuple[entities.Core3SkuBattlefieldScore, ...]]:
        return self._list_sku_rows(entities.Core3SkuBattlefieldScore, batch_id, sku_codes, entities.Core3SkuBattlefieldScore.battlefield_score.desc())

    def _list_claim_layers(self, batch_id: str, sku_codes: tuple[str, ...]) -> dict[str, tuple[entities.Core3SkuClaimValueLayer, ...]]:
        return self._list_sku_rows(entities.Core3SkuClaimValueLayer, batch_id, sku_codes, entities.Core3SkuClaimValueLayer.claim_value_score.desc())

    def _list_sku_rows(self, model_cls: Any, batch_id: str, sku_codes: tuple[str, ...], order_score: Any) -> dict[str, tuple[Any, ...]]:
        if not sku_codes:
            return {}
        stmt = self._current_query(model_cls, batch_id).where(model_cls.sku_code.in_(sku_codes)).order_by(model_cls.sku_code, order_score)
        result: dict[str, list[Any]] = {}
        for row in self._paged_scalars(stmt, limit=100000, offset=0):
            result.setdefault(row.sku_code, []).append(row)
        return {key: tuple(value[:10]) for key, value in result.items()}

    def _list_evidence_atoms(self, batch_id: str, evidence_ids: tuple[str, ...]) -> dict[str, entities.Core3EvidenceAtom]:
        if not evidence_ids:
            return {}
        stmt = self._current_query(entities.Core3EvidenceAtom, batch_id).where(
            entities.Core3EvidenceAtom.evidence_id.in_(evidence_ids)
        )
        return {row.evidence_id: row for row in self._paged_scalars(stmt, limit=100000, offset=0)}

    def _save_many(
        self,
        model_cls: Any,
        payloads: Sequence[Any],
        *,
        unique_fields: tuple[str, ...],
        hash_field: str = "result_hash",
    ) -> EvidenceReportRepositoryWriteResult:
        records: list[Any] = []
        created_count = 0
        reused_count = 0
        updated_count = 0
        for payload in payloads:
            record, status = self._save_one(model_cls, payload, unique_fields=unique_fields, hash_field=hash_field)
            records.append(record)
            if status == "created":
                created_count += 1
            elif status == "updated":
                updated_count += 1
            else:
                reused_count += 1
        return EvidenceReportRepositoryWriteResult(tuple(records), created_count, reused_count, updated_count)

    def _save_one(self, model_cls: Any, payload: Any, *, unique_fields: tuple[str, ...], hash_field: str) -> tuple[Any, str]:
        normalized_payload = self._normalize_payload(model_cls, payload)
        existing = self._find_by_unique(model_cls, normalized_payload, unique_fields)
        if existing is None:
            record = model_cls(**_jsonable_payload(normalized_payload))
            self.db.add(record)
            self.db.flush()
            return record, "created"
        if normalized_payload.get(hash_field) == getattr(existing, hash_field):
            _refresh_existing(existing, normalized_payload)
            self.db.flush()
            return existing, "reused"
        _refresh_existing(existing, normalized_payload)
        self.db.flush()
        return existing, "updated"

    def _normalize_payload(self, model_cls: Any, payload: Any) -> dict[str, Any]:
        if isinstance(payload, BaseModel):
            raw_payload = payload.model_dump(mode="python")
        elif isinstance(payload, Mapping):
            raw_payload = dict(payload)
        else:
            raise TypeError("M15 repository payload must be a mapping or Pydantic model")
        raw_payload.setdefault("project_id", self.project_id)
        raw_payload.setdefault("category_code", self.category_code.value)
        model_fields = set(model_cls.__table__.columns.keys())
        result = {key: value for key, value in raw_payload.items() if key in model_fields}
        for audit_field in ("created_at", "updated_at"):
            if result.get(audit_field) is None:
                result.pop(audit_field, None)
        return result

    def _find_by_unique(self, model_cls: Any, payload: Mapping[str, Any], unique_fields: tuple[str, ...]) -> Any | None:
        stmt = (
            select(model_cls)
            .where(model_cls.project_id == self.project_id)
            .where(model_cls.category_code == self.category_code.value)
        )
        for field_name in unique_fields:
            value = payload.get(field_name)
            if value is None:
                raise ValueError(f"{model_cls.__tablename__}.{field_name} is required")
            stmt = stmt.where(getattr(model_cls, field_name) == value)
        return self.db.execute(stmt).scalars().first()


def _collect_evidence_ids(*row_groups: Any) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for group in row_groups:
        for row in group:
            for field_name in (
                "evidence_ids",
                "positive_evidence_ids",
                "weakening_evidence_ids",
                "supporting_evidence_ids",
                "representative_evidence_ids",
            ):
                values = getattr(row, field_name, None)
                if not values:
                    continue
                for value in values:
                    if value and str(value) not in seen:
                        seen.add(str(value))
                        result.append(str(value))
    return tuple(result)


def _jsonable_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _jsonable_value(value, nested=False) for key, value in payload.items()}


def _jsonable_value(value: Any, *, nested: bool = True) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return float(value) if nested else value
    if isinstance(value, dict):
        return {str(key): _jsonable_value(item, nested=True) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable_value(item, nested=True) for item in value]
    if isinstance(value, tuple):
        return [_jsonable_value(item, nested=True) for item in value]
    return value


def _refresh_existing(existing: Any, payload: Mapping[str, Any]) -> None:
    primary_keys = {column.name for column in existing.__table__.primary_key.columns}
    for field_name, value in _jsonable_payload(payload).items():
        if field_name in primary_keys or field_name == "created_at":
            continue
        setattr(existing, field_name, value)
