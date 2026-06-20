"""M03A category parameter taxonomy builder.

M03A turns cleaned M02 ``param_raw`` evidence into a category-scoped parameter
taxonomy draft. It does not read raw source tables and does not create
downstream task, target-group, battlefield, or claim assets.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
import json
import re
from typing import Any, Mapping, Protocol, Sequence

import httpx

from app.core.config import get_settings
from app.models import entities
from app.services.core3_real_data.hash_utils import stable_hash
from app.services.core3_real_data.param_taxonomy_repositories import (
    ParamTaxonomyEvidenceReader,
    ParamTaxonomyPayload,
    ParamTaxonomyRepository,
)
from app.services.core3_real_data.param_taxonomy_schemas import (
    AnalysisStatus,
    ClusterMethod,
    EvidenceRole,
    M03A_PROMPT_VERSION,
    M03A_RULE_VERSION,
    MappingType,
    ParamConceptCandidateInput,
    ParamDefinitionInput,
    ParamFieldMappingRuleInput,
    ParamTaxonomyDraftRequest,
    ParamTaxonomyDraftResult,
    RawFieldStatus,
    TaxonomyReviewSeverity,
    TaxonomyReviewStatus,
    TaxonomyStatus,
    ValuePolicy,
)


M03A_TAXONOMY_HASH_VERSION = "m03a_taxonomy_hash_v1"
M03A_FIELD_HASH_VERSION = "m03a_field_hash_v1"
M03A_ID_HASH_VERSION = "m03a_id_hash_v1"
M03A_PAGE_SIZE = 50000
M03A_TOP_VALUE_LIMIT = 20
M03A_SAMPLE_VALUE_LIMIT = 12
M03A_LLM_FIELD_LIMIT = 220

MISSING_VALUE_TOKENS = {"", "-", "--", "null", "none", "nan", "n/a", "na", "未知", "无", "不详", "未标注"}
DOWNSTREAM_CODE_PREFIXES = ("CLAIM_", "TASK_", "TG_", "BF_", "BATTLEFIELD_")


class ParamTaxonomyLlmError(RuntimeError):
    pass


class ParamTaxonomyLlmClient(Protocol):
    model_name: str

    def generate_taxonomy(self, package: Mapping[str, Any]) -> dict[str, Any]:
        """Return an LLM-generated taxonomy JSON payload."""


@dataclass
class FieldStats:
    raw_param_name: str
    clean_param_name: str
    normalized_param_name: str
    occurrence_count: int = 0
    unknown_count: int = 0
    sku_codes: set[str] = field(default_factory=set)
    value_counts: Counter[str] = field(default_factory=Counter)
    sample_values: list[str] = field(default_factory=list)
    unit_counts: Counter[str] = field(default_factory=Counter)
    numeric_count: int = 0
    boolean_count: int = 0
    multi_value_count: int = 0
    text_length_total: int = 0
    evidence_ids: list[str] = field(default_factory=list)

    def consume(self, atom: entities.Core3EvidenceAtom) -> None:
        self.occurrence_count += 1
        if atom.sku_code:
            self.sku_codes.add(str(atom.sku_code))
        if len(self.evidence_ids) < 10:
            self.evidence_ids.append(str(atom.evidence_id))

        value = _atom_value(atom)
        if _is_unknown_value(value, atom.value_presence):
            self.unknown_count += 1
            return

        value_text = _stringify_value(value)
        if value_text in MISSING_VALUE_TOKENS:
            self.unknown_count += 1
            return

        self.value_counts[value_text] += 1
        self.text_length_total += len(value_text)
        if len(self.sample_values) < M03A_SAMPLE_VALUE_LIMIT and value_text not in self.sample_values:
            self.sample_values.append(value_text)
        if _looks_numeric(value_text) or atom.numeric_value is not None or atom.numeric_values_json:
            self.numeric_count += 1
        if _looks_boolean(value_text):
            self.boolean_count += 1
        if _looks_multi_value(value_text):
            self.multi_value_count += 1
        if atom.unit_value:
            self.unit_counts[str(atom.unit_value)] += 1
        for unit in _extract_units(value_text):
            self.unit_counts[unit] += 1

    @property
    def present_count(self) -> int:
        return max(self.occurrence_count - self.unknown_count, 0)

    def coverage_rate(self, total_sku_count: int) -> Decimal:
        return _ratio(len(self.sku_codes), total_sku_count)

    def unknown_rate(self) -> Decimal:
        return _ratio(self.unknown_count, self.occurrence_count)

    def top_values(self) -> list[dict[str, Any]]:
        return [
            {"value": value, "count": count}
            for value, count in self.value_counts.most_common(M03A_TOP_VALUE_LIMIT)
        ]

    def unit_candidates(self) -> list[dict[str, Any]]:
        return [{"unit": unit, "count": count} for unit, count in self.unit_counts.most_common(8)]

    def value_pattern(self) -> dict[str, Any]:
        present_count = max(self.present_count, 1)
        numeric_rate = _ratio(self.numeric_count, present_count)
        boolean_rate = _ratio(self.boolean_count, present_count)
        multi_value_rate = _ratio(self.multi_value_count, present_count)
        avg_text_length = Decimal(self.text_length_total).scaleb(-0) / Decimal(present_count)
        return {
            "data_type_guess": _data_type_guess(numeric_rate, boolean_rate, self.value_counts),
            "numeric_rate": str(numeric_rate),
            "boolean_rate": str(boolean_rate),
            "multi_value_rate": str(multi_value_rate),
            "distinct_value_count": len(self.value_counts),
            "avg_text_length": float(avg_text_length.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        }


@dataclass
class FieldInventory:
    fields: dict[str, FieldStats] = field(default_factory=dict)
    sku_fields: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    processed_count: int = 0

    def consume(self, atom: entities.Core3EvidenceAtom) -> None:
        field_name = _field_name(atom)
        if not field_name:
            return
        raw_name = _first_non_empty(atom.raw_field, field_name)
        clean_name = _first_non_empty(atom.clean_field, field_name)
        stats = self.fields.get(raw_name)
        if stats is None:
            stats = FieldStats(
                raw_param_name=raw_name,
                clean_param_name=clean_name,
                normalized_param_name=_normalize_field_name(clean_name),
            )
            self.fields[raw_name] = stats
        stats.consume(atom)
        if atom.sku_code:
            self.sku_fields[str(atom.sku_code)].add(raw_name)
        self.processed_count += 1

    def total_sku_count(self) -> int:
        return len(self.sku_fields)

    def cooccurrence(self) -> dict[str, list[str]]:
        counters: dict[str, Counter[str]] = {field_name: Counter() for field_name in self.fields}
        for field_names in self.sku_fields.values():
            ordered = sorted(field_names)
            for field_name in ordered:
                counters[field_name].update(other for other in ordered if other != field_name)
        return {
            field_name: [name for name, _ in counter.most_common(10)]
            for field_name, counter in counters.items()
        }


class DeepSeekOpenAIParamTaxonomyClient:
    """OpenAI-compatible client for DeepSeek taxonomy generation."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key: str | None = None,
        model_name: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.llm_base_url or "").rstrip("/")
        self.api_key = api_key or settings.llm_api_key
        self.model_name = model_name or settings.llm_model
        self.timeout_seconds = timeout_seconds or settings.llm_timeout_seconds

    def generate_taxonomy(self, package: Mapping[str, Any]) -> dict[str, Any]:
        if not self.base_url or not self.api_key:
            raise ParamTaxonomyLlmError("LLM is not configured; set CATFORGE_LLM_BASE_URL and CATFORGE_LLM_API_KEY")
        payload = {
            "model": self.model_name,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是 CatForge 品类参数资产专家。只基于输入的 M02 参数证据生成参数分类草案；"
                        "不得创建用户任务、目标客群、价值战场、卖点 claim 代码。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "instruction": _llm_instruction(),
                            "input": package,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                },
            ],
        }
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(_strip_json_fence(str(content)))
        except Exception as exc:
            raise ParamTaxonomyLlmError(f"LLM taxonomy generation failed: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ParamTaxonomyLlmError("LLM taxonomy generation returned non-object JSON")
        return parsed


class ParamTaxonomyService:
    def __init__(
        self,
        repository: ParamTaxonomyRepository,
        evidence_reader: ParamTaxonomyEvidenceReader,
        *,
        llm_client: ParamTaxonomyLlmClient | None = None,
        page_size: int = M03A_PAGE_SIZE,
    ) -> None:
        self.repository = repository
        self.evidence_reader = evidence_reader
        self.llm_client = llm_client or DeepSeekOpenAIParamTaxonomyClient()
        self.page_size = page_size

    def build_draft(self, request: ParamTaxonomyDraftRequest) -> ParamTaxonomyDraftResult:
        inventory = self._build_inventory(request)
        if not inventory.fields:
            raise ValueError("M02 param_raw evidence not ready: no usable parameter evidence found for M03A")

        total_sku_count = inventory.total_sku_count()
        cooccurrence = inventory.cooccurrence()
        field_payloads = self._build_field_payloads(request, inventory, cooccurrence, total_sku_count)
        cluster_payloads = self._build_cluster_payloads(request, field_payloads)
        llm_package = self._build_llm_package(request, field_payloads, cluster_payloads, total_sku_count)
        warnings: list[str] = []
        llm_payload: dict[str, Any] = {}
        llm_used = False
        if request.use_llm:
            try:
                llm_payload = self.llm_client.generate_taxonomy(llm_package)
                llm_used = True
            except ParamTaxonomyLlmError as exc:
                warnings.append(str(exc))

        taxonomy_version = request.taxonomy_version or _default_taxonomy_version(request.category_code)
        candidate_payloads, definition_payloads, mapping_payloads, review_payloads = self._build_assets(
            request=request,
            taxonomy_version=taxonomy_version,
            field_payloads=field_payloads,
            cluster_payloads=cluster_payloads,
            llm_payload=llm_payload,
            llm_used=llm_used,
            warnings=warnings,
        )
        taxonomy_hash = stable_hash(
            {
                "fields": _hashable_records(field_payloads, ["raw_param_name"]),
                "clusters": _hashable_records(cluster_payloads, ["cluster_code"]),
                "candidates": _hashable_records(candidate_payloads, ["candidate_code"]),
                "definitions": _hashable_records(definition_payloads, ["param_code"]),
                "mapping_rules": _hashable_records(mapping_payloads, ["raw_param_name", "param_code", "mapping_type"]),
            },
            version=M03A_TAXONOMY_HASH_VERSION,
        )
        review_required_count = sum(
            1 for item in review_payloads if item["review_status"] == TaxonomyReviewStatus.REVIEW_REQUIRED.value
        )
        blocking_review_count = sum(
            1
            for item in review_payloads
            if item["review_status"] == TaxonomyReviewStatus.REVIEW_REQUIRED.value
            and item["severity"] == TaxonomyReviewSeverity.BLOCKING.value
        )
        version_payload = {
            "taxonomy_version_id": _id(
                "m03atv",
                self.repository.project_id,
                request.category_code,
                taxonomy_version,
            ),
            "taxonomy_version": taxonomy_version,
            "project_id": self.repository.project_id,
            "category_code": request.category_code,
            "status": (
                TaxonomyStatus.REVIEW_READY.value
                if review_required_count > 0
                else TaxonomyStatus.DRAFT.value
            ),
            "source_batch_ids": list(request.batch_ids),
            "source_field_count": len(field_payloads),
            "active_param_count": sum(
                1 for item in definition_payloads if item["analysis_status"] == AnalysisStatus.ACTIVE.value
            ),
            "review_required_count": review_required_count,
            "blocking_review_count": blocking_review_count,
            "llm_model_snapshot": self.llm_client.model_name if llm_used else None,
            "llm_prompt_version": M03A_PROMPT_VERSION if llm_used else None,
            "rule_version": request.rule_version,
            "taxonomy_hash": taxonomy_hash,
            "published_at": None,
            "created_by": request.created_by,
        }
        payload = ParamTaxonomyPayload(
            version=version_payload,
            fields=[
                {
                    **item,
                    "taxonomy_version": taxonomy_version,
                    "project_id": self.repository.project_id,
                    "category_code": request.category_code,
                }
                for item in field_payloads
            ],
            clusters=[
                {
                    **item,
                    "taxonomy_version": taxonomy_version,
                    "project_id": self.repository.project_id,
                    "category_code": request.category_code,
                }
                for item in cluster_payloads
            ],
            candidates=[
                {
                    **item,
                    "taxonomy_version": taxonomy_version,
                    "project_id": self.repository.project_id,
                    "category_code": request.category_code,
                }
                for item in candidate_payloads
            ],
            definitions=[
                {
                    **item,
                    "taxonomy_version": taxonomy_version,
                    "project_id": self.repository.project_id,
                    "category_code": request.category_code,
                }
                for item in definition_payloads
            ],
            mapping_rules=[
                {
                    **item,
                    "taxonomy_version": taxonomy_version,
                    "project_id": self.repository.project_id,
                    "category_code": request.category_code,
                }
                for item in mapping_payloads
            ],
            review_items=[
                {
                    **item,
                    "taxonomy_version": taxonomy_version,
                    "project_id": self.repository.project_id,
                    "category_code": request.category_code,
                }
                for item in review_payloads
            ],
        )
        self.repository.save_taxonomy_payload(payload, force_rebuild=request.force_rebuild)
        return ParamTaxonomyDraftResult(
            taxonomy_version=taxonomy_version,
            status=version_payload["status"],
            source_field_count=len(field_payloads),
            active_param_count=version_payload["active_param_count"],
            review_required_count=review_required_count,
            blocking_review_count=blocking_review_count,
            taxonomy_hash=taxonomy_hash,
            warnings=warnings,
        )

    def _build_inventory(self, request: ParamTaxonomyDraftRequest) -> FieldInventory:
        inventory = FieldInventory()
        offset = 0
        while True:
            rows = self.evidence_reader.list_param_raw_evidence(
                batch_ids=request.batch_ids,
                category_code=request.category_code,
                limit=self.page_size,
                offset=offset,
            )
            if not rows:
                break
            for row in rows:
                inventory.consume(row)
            if len(rows) < self.page_size:
                break
            offset += len(rows)
        return inventory

    def _build_field_payloads(
        self,
        request: ParamTaxonomyDraftRequest,
        inventory: FieldInventory,
        cooccurrence: Mapping[str, list[str]],
        total_sku_count: int,
    ) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        for stats in sorted(inventory.fields.values(), key=lambda item: item.raw_param_name):
            coverage_rate = stats.coverage_rate(total_sku_count)
            unknown_rate = stats.unknown_rate()
            field_status = _field_status(stats, coverage_rate, unknown_rate)
            field_core = {
                "raw_param_name": stats.raw_param_name,
                "clean_param_name": stats.clean_param_name,
                "normalized_param_name": stats.normalized_param_name,
                "occurrence_count": stats.occurrence_count,
                "sku_coverage_count": len(stats.sku_codes),
                "sku_coverage_rate": coverage_rate,
                "unknown_count": stats.unknown_count,
                "unknown_rate": unknown_rate,
                "top_values_json": stats.top_values(),
                "sample_values_json": stats.sample_values,
                "value_pattern_json": stats.value_pattern(),
                "unit_candidates_json": stats.unit_candidates(),
                "cooccurrence_field_names": cooccurrence.get(stats.raw_param_name, []),
                "field_status": field_status.value,
            }
            payloads.append(
                {
                    "raw_field_id": _id(
                        "m03arf",
                        self.repository.project_id,
                        request.category_code,
                        request.rule_version,
                        stats.raw_param_name,
                    ),
                    **field_core,
                    "field_hash": stable_hash(field_core, version=M03A_FIELD_HASH_VERSION),
                }
            )
        return payloads

    def _build_cluster_payloads(
        self,
        request: ParamTaxonomyDraftRequest,
        field_payloads: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for field_payload in field_payloads:
            grouped[_cluster_key(field_payload)].append(field_payload)
        clusters: list[dict[str, Any]] = []
        for key, members in sorted(grouped.items()):
            raw_fields = sorted(str(item["raw_param_name"]) for item in members)
            cluster_code = f"CLUSTER_{_safe_code_fragment(key)}"
            clusters.append(
                {
                    "field_cluster_id": _id(
                        "m03acl",
                        self.repository.project_id,
                        request.category_code,
                        request.rule_version,
                        cluster_code,
                    ),
                    "cluster_code": cluster_code,
                    "cluster_name_candidate": _cluster_name_cn(key),
                    "member_raw_fields": raw_fields,
                    "cluster_method": ClusterMethod.RULE.value,
                    "cluster_confidence": Decimal("0.5000") if len(raw_fields) == 1 else Decimal("0.6500"),
                    "cluster_reason_json": {
                        "method": "keyword_and_value_pattern",
                        "field_count": len(raw_fields),
                    },
                    "review_status": TaxonomyReviewStatus.AUTO_PASS.value,
                }
            )
        return clusters

    def _build_llm_package(
        self,
        request: ParamTaxonomyDraftRequest,
        field_payloads: Sequence[Mapping[str, Any]],
        cluster_payloads: Sequence[Mapping[str, Any]],
        total_sku_count: int,
    ) -> dict[str, Any]:
        fields_for_llm = [
            {
                "raw_param_name": item["raw_param_name"],
                "clean_param_name": item["clean_param_name"],
                "sku_coverage_rate": str(item["sku_coverage_rate"]),
                "unknown_rate": str(item["unknown_rate"]),
                "top_values": item["top_values_json"][:8],
                "sample_values": item["sample_values_json"][:6],
                "value_pattern": item["value_pattern_json"],
                "unit_candidates": item["unit_candidates_json"][:4],
                "cooccurrence_field_names": item["cooccurrence_field_names"][:6],
                "field_status": item["field_status"],
            }
            for item in field_payloads[:M03A_LLM_FIELD_LIMIT]
        ]
        return {
            "project_id": self.repository.project_id,
            "category_code": request.category_code,
            "source_batch_ids": list(request.batch_ids),
            "rule_version": request.rule_version,
            "prompt_version": M03A_PROMPT_VERSION,
            "total_sku_count": total_sku_count,
            "field_count": len(field_payloads),
            "fields": fields_for_llm,
            "clusters": [
                {
                    "cluster_code": item["cluster_code"],
                    "cluster_name_candidate": item["cluster_name_candidate"],
                    "member_raw_fields": item["member_raw_fields"],
                }
                for item in cluster_payloads
            ],
            "output_schema": {
                "param_candidates": [
                    {
                        "candidate_code": "PARAM_CODE",
                        "candidate_name": "中文参数名",
                        "source_raw_fields": ["必须来自 fields.raw_param_name"],
                        "definition_candidate": "参数定义",
                        "data_type_candidate": "string|number|boolean|enum|list",
                        "unit_candidate": "可为空",
                        "parser_candidate": "string|number_unit|boolean|enum|list",
                        "capability_tags": ["只能是自然语言能力标签，不得是 TASK_/TG_/BF_/CLAIM_ 代码"],
                        "benefit_hints": ["参数可能支撑的用户收益，不是卖点代码"],
                        "scenario_hints": ["参数可能出现的使用语境，不是任务代码"],
                        "comparison_axis": "larger_better|smaller_better|presence_better|not_comparable",
                        "evidence_role": "strong_param_evidence|supporting_param_evidence|weak_signal|metadata_only",
                        "confidence": 0.8,
                        "review_required": False,
                        "risk_notes": [],
                    }
                ],
                "field_decisions": [
                    {
                        "raw_param_name": "字段名",
                        "param_code": "映射到的 PARAM_CODE，可为空",
                        "mapping_type": "direct|alias|derived_helper|metadata|weak_signal|ignore|review_required",
                        "value_policy": "use_as_value|use_as_helper|do_not_extract|requires_rule",
                        "confidence": 0.8,
                        "review_required": False,
                    }
                ],
                "review_items": [
                    {
                        "item_type": "需要复核的类型",
                        "severity": "info|warning|blocking",
                        "raw_param_name": "可为空",
                        "param_code": "可为空",
                        "issue_summary_cn": "中文说明",
                        "suggested_action": "review|merge|ignore|split|add_rule",
                    }
                ],
            },
        }

    def _build_assets(
        self,
        *,
        request: ParamTaxonomyDraftRequest,
        taxonomy_version: str,
        field_payloads: Sequence[Mapping[str, Any]],
        cluster_payloads: Sequence[Mapping[str, Any]],
        llm_payload: Mapping[str, Any],
        llm_used: bool,
        warnings: list[str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        raw_field_names = {str(item["raw_param_name"]) for item in field_payloads}
        cluster_by_field = _cluster_lookup(cluster_payloads)
        llm_candidates = llm_payload.get("param_candidates") if isinstance(llm_payload, Mapping) else None
        if not isinstance(llm_candidates, list) or not llm_candidates:
            llm_candidates = _fallback_candidates(field_payloads)
            if llm_used:
                warnings.append("LLM did not return param_candidates; used rule fallback candidates")

        candidates: list[dict[str, Any]] = []
        definitions: list[dict[str, Any]] = []
        review_items: list[dict[str, Any]] = []
        param_by_field: dict[str, str] = {}
        for item in llm_candidates:
            if not isinstance(item, Mapping):
                continue
            source_fields = [
                str(field_name)
                for field_name in _list_of_strings(item.get("source_raw_fields"))
                if str(field_name) in raw_field_names
            ]
            if not source_fields:
                review_items.append(
                    _review_payload(
                        taxonomy_version=taxonomy_version,
                        project_id=self.repository.project_id,
                        category_code=request.category_code,
                        item_type="candidate_without_source_field",
                        severity=TaxonomyReviewSeverity.WARNING.value,
                        raw_param_name=None,
                        param_code=_candidate_code(item, request.category_code),
                        issue_summary_cn="候选参数没有可追溯的原始字段，已跳过定义生成。",
                        evidence_json={"candidate": dict(item)},
                        suggested_action="review",
                    )
                )
                continue

            candidate_code = _candidate_code(item, request.category_code)
            capability_tags, removed_tags = _safe_capability_tags(item.get("capability_tags"))
            if removed_tags:
                review_items.append(
                    _review_payload(
                        taxonomy_version=taxonomy_version,
                        project_id=self.repository.project_id,
                        category_code=request.category_code,
                        item_type="downstream_tag_removed",
                        severity=TaxonomyReviewSeverity.WARNING.value,
                        raw_param_name=source_fields[0],
                        param_code=candidate_code,
                        issue_summary_cn="LLM 输出包含下游业务代码标签，已移除；参数分类只保留自然语言用途标签。",
                        evidence_json={"removed_tags": removed_tags},
                        suggested_action="review",
                    )
                )
            confidence = _decimal_confidence(item.get("confidence", item.get("llm_confidence")))
            review_required = bool(item.get("review_required", confidence < Decimal("0.7000")))
            evidence_role = _enum_value_or_default(
                item.get("evidence_role"),
                EvidenceRole,
                EvidenceRole.WEAK_SIGNAL.value,
            )
            source_cluster_ids = sorted(
                {
                    cluster_by_field[field_name]
                    for field_name in source_fields
                    if field_name in cluster_by_field
                }
            )
            candidate_input = ParamConceptCandidateInput(
                candidate_code=candidate_code,
                candidate_name=str(item.get("candidate_name") or item.get("param_name") or source_fields[0]),
                source_cluster_ids=source_cluster_ids,
                source_raw_fields=source_fields,
                definition_candidate=str(
                    item.get("definition_candidate") or item.get("definition") or f"由字段 {', '.join(source_fields)} 归纳的参数。"
                ),
                data_type_candidate=str(item.get("data_type_candidate") or item.get("data_type") or "string"),
                unit_candidate=_optional_text(item.get("unit_candidate") or item.get("unit")),
                parser_candidate=_optional_text(item.get("parser_candidate") or item.get("value_parser")),
                capability_tags=capability_tags,
                benefit_hints=_list_of_strings(item.get("benefit_hints")),
                scenario_hints=_list_of_strings(item.get("scenario_hints")),
                comparison_axis=str(item.get("comparison_axis") or "not_comparable"),
                evidence_role=evidence_role,
                risk_notes=_list_of_strings(item.get("risk_notes")),
                llm_confidence=confidence if llm_used else Decimal("0.0000"),
                rule_confidence=Decimal("0.3000") if not llm_used else Decimal("0.0000"),
                review_required=review_required,
                review_status=(
                    TaxonomyReviewStatus.REVIEW_REQUIRED.value
                    if review_required
                    else TaxonomyReviewStatus.AUTO_PASS.value
                ),
            )
            candidate_payload = {
                "concept_candidate_id": _id("m03acc", self.repository.project_id, request.category_code, taxonomy_version, candidate_code),
                **candidate_input.model_dump(),
            }
            candidates.append(candidate_payload)
            for field_name in source_fields:
                param_by_field.setdefault(field_name, candidate_code)

            analysis_status = (
                AnalysisStatus.REVIEW_REQUIRED.value
                if review_required
                else AnalysisStatus.ACTIVE.value
            )
            definition_core = {
                "param_code": candidate_code,
                "param_name": candidate_input.candidate_name,
                "definition": candidate_input.definition_candidate,
                "param_group": _param_group(candidate_input, source_fields),
                "data_type": candidate_input.data_type_candidate,
                "unit": candidate_input.unit_candidate,
                "value_parser": candidate_input.parser_candidate or _parser_for_data_type(candidate_input.data_type_candidate),
                "parser_config_json": {},
                "source_raw_fields": source_fields,
                "capability_tags": capability_tags,
                "benefit_hints": candidate_input.benefit_hints,
                "scenario_hints": candidate_input.scenario_hints,
                "comparison_axis": candidate_input.comparison_axis,
                "evidence_role": candidate_input.evidence_role,
                "analysis_status": analysis_status,
                "review_status": candidate_input.review_status,
            }
            definition_input = ParamDefinitionInput(
                **definition_core,
                definition_hash=stable_hash(definition_core, version=M03A_TAXONOMY_HASH_VERSION),
            )
            definitions.append(
                {
                    "param_definition_id": _id("m03apd", self.repository.project_id, request.category_code, taxonomy_version, candidate_code),
                    **definition_input.model_dump(),
                }
            )
            if review_required:
                review_items.append(
                    _review_payload(
                        taxonomy_version=taxonomy_version,
                        project_id=self.repository.project_id,
                        category_code=request.category_code,
                        item_type="candidate_review_required",
                        severity=TaxonomyReviewSeverity.WARNING.value,
                        raw_param_name=source_fields[0],
                        param_code=candidate_code,
                        issue_summary_cn="候选参数置信度不足或标记为需复核，发布前建议确认定义、字段映射和用途标签。",
                        evidence_json={"source_raw_fields": source_fields, "confidence": str(confidence)},
                        suggested_action="review",
                    )
                )

        field_decisions = llm_payload.get("field_decisions") if isinstance(llm_payload, Mapping) else None
        decisions = field_decisions if isinstance(field_decisions, list) else []
        mapping_payloads = self._build_mapping_rules(
            request=request,
            taxonomy_version=taxonomy_version,
            field_payloads=field_payloads,
            decisions=decisions,
            param_by_field=param_by_field,
            review_items=review_items,
        )
        review_items.extend(
            self._extra_review_items(
                request=request,
                taxonomy_version=taxonomy_version,
                llm_payload=llm_payload,
                raw_field_names=raw_field_names,
            )
        )
        return candidates, definitions, mapping_payloads, _dedupe_review_items(review_items)

    def _build_mapping_rules(
        self,
        *,
        request: ParamTaxonomyDraftRequest,
        taxonomy_version: str,
        field_payloads: Sequence[Mapping[str, Any]],
        decisions: Sequence[Any],
        param_by_field: Mapping[str, str],
        review_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        decision_by_field = {
            str(item.get("raw_param_name")): item
            for item in decisions
            if isinstance(item, Mapping) and item.get("raw_param_name")
        }
        rules: list[dict[str, Any]] = []
        for field_payload in field_payloads:
            raw_name = str(field_payload["raw_param_name"])
            decision = decision_by_field.get(raw_name, {})
            suggested_param = _optional_text(decision.get("param_code")) if isinstance(decision, Mapping) else None
            param_code = suggested_param or param_by_field.get(raw_name)
            mapping_type = _enum_value_or_default(
                decision.get("mapping_type") if isinstance(decision, Mapping) else None,
                MappingType,
                MappingType.DIRECT.value if param_code else MappingType.REVIEW_REQUIRED.value,
            )
            if param_code is None and mapping_type in {MappingType.DIRECT.value, MappingType.ALIAS.value}:
                mapping_type = MappingType.REVIEW_REQUIRED.value
            value_policy = _enum_value_or_default(
                decision.get("value_policy") if isinstance(decision, Mapping) else None,
                ValuePolicy,
                ValuePolicy.USE_AS_VALUE.value if param_code else ValuePolicy.REQUIRES_RULE.value,
            )
            confidence = _decimal_confidence(decision.get("confidence") if isinstance(decision, Mapping) else None)
            review_status = (
                TaxonomyReviewStatus.AUTO_PASS.value
                if param_code and mapping_type in {MappingType.DIRECT.value, MappingType.ALIAS.value} and confidence >= Decimal("0.6500")
                else TaxonomyReviewStatus.REVIEW_REQUIRED.value
            )
            rule_input = ParamFieldMappingRuleInput(
                raw_param_name=raw_name,
                param_code=param_code,
                mapping_type=mapping_type,
                value_policy=value_policy,
                parser_type=_parser_from_pattern(field_payload),
                parser_config_json={"value_pattern": field_payload.get("value_pattern_json") or {}},
                invalid_value_policy_json={"missing_is_unknown": True},
                source_priority=_source_priority(field_payload),
                confidence=confidence,
                review_status=review_status,
            )
            rules.append(
                {
                    "mapping_rule_id": _id("m03amr", self.repository.project_id, request.category_code, taxonomy_version, raw_name, param_code or "", mapping_type),
                    **rule_input.model_dump(),
                }
            )
            if review_status == TaxonomyReviewStatus.REVIEW_REQUIRED.value:
                severity = (
                    TaxonomyReviewSeverity.BLOCKING.value
                    if _is_high_coverage_usable_field(field_payload)
                    else TaxonomyReviewSeverity.WARNING.value
                )
                review_items.append(
                    _review_payload(
                        taxonomy_version=taxonomy_version,
                        project_id=self.repository.project_id,
                        category_code=request.category_code,
                        item_type="field_mapping_review_required",
                        severity=severity,
                        raw_param_name=raw_name,
                        param_code=param_code,
                        issue_summary_cn="字段映射需要人工确认，避免把弱信号、元数据或多义字段直接进入 SKU 参数事实画像。",
                        evidence_json={
                            "field_status": field_payload.get("field_status"),
                            "sku_coverage_rate": str(field_payload.get("sku_coverage_rate")),
                            "unknown_rate": str(field_payload.get("unknown_rate")),
                            "top_values": field_payload.get("top_values_json", [])[:5],
                        },
                        suggested_action="review",
                    )
                )
        return rules

    def _extra_review_items(
        self,
        *,
        request: ParamTaxonomyDraftRequest,
        taxonomy_version: str,
        llm_payload: Mapping[str, Any],
        raw_field_names: set[str],
    ) -> list[dict[str, Any]]:
        review_payloads: list[dict[str, Any]] = []
        llm_review_items = llm_payload.get("review_items") if isinstance(llm_payload, Mapping) else None
        if isinstance(llm_review_items, list):
            for item in llm_review_items:
                if not isinstance(item, Mapping):
                    continue
                raw_param_name = _optional_text(item.get("raw_param_name"))
                if raw_param_name is not None and raw_param_name not in raw_field_names:
                    raw_param_name = None
                severity = _enum_value_or_default(
                    item.get("severity"),
                    TaxonomyReviewSeverity,
                    TaxonomyReviewSeverity.WARNING.value,
                )
                review_payloads.append(
                    _review_payload(
                        taxonomy_version=taxonomy_version,
                        project_id=self.repository.project_id,
                        category_code=request.category_code,
                        item_type=str(item.get("item_type") or "llm_review_item"),
                        severity=severity,
                        raw_param_name=raw_param_name,
                        param_code=_optional_text(item.get("param_code")),
                        issue_summary_cn=str(item.get("issue_summary_cn") or "LLM 标记需复核。"),
                        evidence_json={"llm_review_item": dict(item)},
                        suggested_action=str(item.get("suggested_action") or "review"),
                    )
                )
        return review_payloads


def _llm_instruction() -> str:
    return (
        "请把输入字段归纳为本品类的标准参数分类草案。必须遵守："
        "1. 每个候选参数都要引用 source_raw_fields，字段必须来自输入；"
        "2. capability_tags、benefit_hints、scenario_hints 只能是自然语言用途提示，不能是 TASK_/TG_/BF_/CLAIM_ 等下游业务代码；"
        "3. 不要因为已有框架而保留无证据参数；当前数据不支持的内容只能放 review_items；"
        "4. 多义、弱覆盖、高缺失、疑似元数据字段要标 review_required；"
        "5. 只返回 JSON 对象，不要 Markdown。"
    )


def _hashable_records(records: Sequence[Mapping[str, Any]], keys: Sequence[str]) -> list[dict[str, Any]]:
    return [
        {key: _json_safe(record.get(key)) for key in sorted(record)}
        for record in sorted(records, key=lambda record: tuple(str(record.get(key, "")) for key in keys))
    ]


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat() if value.tzinfo else value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _strip_json_fence(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _atom_value(atom: entities.Core3EvidenceAtom) -> Any:
    return _first_non_empty(atom.clean_value, atom.text_value, atom.raw_value)


def _field_name(atom: entities.Core3EvidenceAtom) -> str | None:
    return _optional_text(_first_non_empty(atom.clean_field, atom.raw_field, atom.evidence_field))


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        text = _optional_text(value)
        if text is not None:
            return text
    return None


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _stringify_value(value: Any) -> str:
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, list | dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).strip()


def _is_unknown_value(value: Any, value_presence: str | None) -> bool:
    presence = str(value_presence or "").strip().lower()
    if presence and presence not in {"present", "ok", "valid"}:
        return True
    if value is None:
        return True
    return _stringify_value(value).strip().lower() in MISSING_VALUE_TOKENS


def _looks_numeric(value: str) -> bool:
    return bool(re.search(r"[-+]?\d+(?:\.\d+)?", value))


def _looks_boolean(value: str) -> bool:
    return value.strip().lower() in {
        "是",
        "否",
        "有",
        "无",
        "支持",
        "不支持",
        "true",
        "false",
        "yes",
        "no",
    }


def _looks_multi_value(value: str) -> bool:
    return any(separator in value for separator in ["/", "、", ",", "，", ";", "；", "+"])


def _extract_units(value: str) -> list[str]:
    units = []
    for match in re.finditer(r"\d+(?:\.\d+)?\s*([a-zA-Z]+|英寸|寸|赫兹|毫秒|瓦|升|公斤|kg|hz|ms|w)", value):
        unit = match.group(1).strip()
        if unit:
            units.append(unit)
    return units


def _ratio(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return Decimal("0.000000")
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _data_type_guess(numeric_rate: Decimal, boolean_rate: Decimal, value_counts: Counter[str]) -> str:
    if boolean_rate >= Decimal("0.800000"):
        return "boolean"
    if numeric_rate >= Decimal("0.700000"):
        return "number"
    if 0 < len(value_counts) <= 12:
        return "enum"
    return "string"


def _normalize_field_name(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[()（）【】\\[\\]：:；;，,。./\\-+_]+", "", text)
    return text


def _field_status(stats: FieldStats, coverage_rate: Decimal, unknown_rate: Decimal) -> RawFieldStatus:
    name = stats.clean_param_name + stats.raw_param_name
    metadata_keywords = ("品牌", "型号", "商品编号", "条码", "产地", "上市", "包装清单", "保修")
    weak_keywords = ("备注", "其他", "适用", "随机", "以实物为准")
    if any(keyword in name for keyword in metadata_keywords):
        return RawFieldStatus.METADATA
    if unknown_rate >= Decimal("0.950000") or coverage_rate < Decimal("0.010000"):
        return RawFieldStatus.WEAK_SIGNAL
    if any(keyword in name for keyword in weak_keywords):
        return RawFieldStatus.REVIEW_REQUIRED
    return RawFieldStatus.USABLE


def _cluster_key(field_payload: Mapping[str, Any]) -> str:
    name = f"{field_payload.get('raw_param_name', '')}{field_payload.get('clean_param_name', '')}".lower()
    pattern = field_payload.get("value_pattern_json") or {}
    if any(keyword in name for keyword in ["尺寸", "大小", "容量", "英寸", "inch", "宽", "高", "厚", "重量", "kg"]):
        return "size_capacity_dimension"
    if any(keyword in name for keyword in ["刷新", "频率", "hz", "速度", "功率", "性能", "响应", "转速"]):
        return "performance_rate"
    if any(keyword in name for keyword in ["屏", "画质", "分辨率", "色域", "亮度", "hdr", "显示", "对比度"]):
        return "display_image"
    if any(keyword in name for keyword in ["接口", "hdmi", "usb", "wifi", "蓝牙", "网络", "连接"]):
        return "connectivity_port"
    if any(keyword in name for keyword in ["能效", "耗电", "功耗", "电压", "节能"]):
        return "energy_power"
    if any(keyword in name for keyword in ["智能", "语音", "系统", "芯片", "内存", "遥控", "app"]):
        return "control_intelligence"
    if any(keyword in name for keyword in ["安装", "墙", "底座", "开孔", "嵌入", "摆放"]):
        return "installation_space"
    if any(keyword in name for keyword in ["颜色", "材质", "外观", "边框", "造型"]):
        return "design_appearance"
    if pattern.get("data_type_guess") == "number":
        return "numeric_specs"
    return "other_specs"


def _cluster_name_cn(key: str) -> str:
    names = {
        "size_capacity_dimension": "尺寸/容量/空间参数",
        "performance_rate": "性能/频率参数",
        "display_image": "显示/成像参数",
        "connectivity_port": "连接/接口参数",
        "energy_power": "能效/功耗参数",
        "control_intelligence": "智能/控制参数",
        "installation_space": "安装/空间适配参数",
        "design_appearance": "外观/材质参数",
        "numeric_specs": "数值规格参数",
        "other_specs": "其他参数",
    }
    return names.get(key, key)


def _cluster_lookup(cluster_payloads: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for cluster in cluster_payloads:
        cluster_id = str(cluster["field_cluster_id"])
        for raw_field in cluster.get("member_raw_fields") or []:
            lookup[str(raw_field)] = cluster_id
    return lookup


def _fallback_candidates(field_payloads: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for field_payload in field_payloads:
        raw_name = str(field_payload["raw_param_name"])
        field_status = str(field_payload.get("field_status") or "")
        if field_status in {RawFieldStatus.IGNORE.value, RawFieldStatus.WEAK_SIGNAL.value}:
            continue
        pattern = field_payload.get("value_pattern_json") or {}
        code_fragment = _safe_code_fragment(raw_name)
        candidates.append(
            {
                "candidate_code": f"PARAM_{code_fragment}",
                "candidate_name": str(field_payload.get("clean_param_name") or raw_name),
                "source_raw_fields": [raw_name],
                "definition_candidate": f"由原始参数字段“{raw_name}”归纳的候选参数。",
                "data_type_candidate": pattern.get("data_type_guess") or "string",
                "unit_candidate": _first_unit_candidate(field_payload.get("unit_candidates_json") or []),
                "parser_candidate": _parser_from_pattern(field_payload),
                "capability_tags": [],
                "benefit_hints": [],
                "scenario_hints": [],
                "comparison_axis": "not_comparable",
                "evidence_role": EvidenceRole.SUPPORTING_PARAM_EVIDENCE.value,
                "confidence": 0.3,
                "review_required": True,
                "risk_notes": ["rule_fallback"],
            }
        )
    return candidates


def _first_unit_candidate(unit_candidates: Sequence[Any]) -> str | None:
    if not unit_candidates:
        return None
    first = unit_candidates[0]
    if isinstance(first, Mapping):
        return _optional_text(first.get("unit"))
    return _optional_text(first)


def _candidate_code(item: Mapping[str, Any], category_code: str) -> str:
    raw = _optional_text(item.get("candidate_code") or item.get("param_code"))
    if raw is None:
        raw = f"PARAM_{_safe_code_fragment(str(item.get('candidate_name') or category_code))}"
    normalized = re.sub(r"[^A-Za-z0-9_]+", "_", raw.strip()).strip("_").upper()
    if not normalized:
        normalized = f"PARAM_{_safe_code_fragment(category_code)}"
    if any(normalized.startswith(prefix) for prefix in DOWNSTREAM_CODE_PREFIXES):
        normalized = f"PARAM_{stable_hash(normalized, version=M03A_ID_HASH_VERSION).split(':')[-1][:12].upper()}"
    if not normalized.startswith("PARAM_"):
        normalized = f"PARAM_{normalized}"
    return normalized[:160]


def _safe_code_fragment(value: str) -> str:
    ascii_text = re.sub(r"[^A-Za-z0-9]+", "_", value.upper()).strip("_")
    if ascii_text:
        return ascii_text[:64]
    return stable_hash(value, version=M03A_ID_HASH_VERSION).split(":")[-1][:16].upper()


def _safe_capability_tags(value: Any) -> tuple[list[str], list[str]]:
    tags = _list_of_strings(value)
    kept: list[str] = []
    removed: list[str] = []
    for tag in tags:
        if any(tag.upper().startswith(prefix) for prefix in DOWNSTREAM_CODE_PREFIXES):
            removed.append(tag)
        else:
            kept.append(tag)
    return kept, removed


def _list_of_strings(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        result: list[str] = []
        for item in value:
            text = _optional_text(item)
            if text is not None and text not in result:
                result.append(text)
        return result
    return []


def _decimal_confidence(value: Any) -> Decimal:
    try:
        confidence = Decimal(str(value if value is not None else "0"))
    except Exception:
        confidence = Decimal("0")
    if confidence < 0:
        return Decimal("0.0000")
    if confidence > 1:
        return Decimal("1.0000")
    return confidence.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _enum_value_or_default(value: Any, enum_cls: Any, default: str) -> str:
    text = _optional_text(value)
    if text is None:
        return default
    allowed = {item.value for item in enum_cls}
    return text if text in allowed else default


def _param_group(candidate: ParamConceptCandidateInput, source_fields: Sequence[str]) -> str:
    text = f"{candidate.candidate_name}{' '.join(source_fields)}".lower()
    if any(keyword in text for keyword in ["尺寸", "容量", "大小", "重量", "宽", "高"]):
        return "size_capacity_dimension"
    if any(keyword in text for keyword in ["接口", "hdmi", "usb", "wifi", "蓝牙"]):
        return "connectivity"
    if any(keyword in text for keyword in ["能效", "功耗", "电压", "耗电"]):
        return "energy_power"
    if any(keyword in text for keyword in ["刷新", "速度", "频率", "性能", "转速"]):
        return "performance"
    if any(keyword in text for keyword in ["智能", "语音", "系统", "芯片"]):
        return "control_intelligence"
    return "other"


def _parser_for_data_type(data_type: str) -> str:
    if data_type in {"number", "numeric"}:
        return "number"
    if data_type == "boolean":
        return "boolean"
    if data_type == "list":
        return "list"
    if data_type == "enum":
        return "enum"
    return "string"


def _parser_from_pattern(field_payload: Mapping[str, Any]) -> str:
    pattern = field_payload.get("value_pattern_json") or {}
    return _parser_for_data_type(str(pattern.get("data_type_guess") or "string"))


def _source_priority(field_payload: Mapping[str, Any]) -> int:
    field_status = str(field_payload.get("field_status") or "")
    if field_status == RawFieldStatus.USABLE.value:
        return 10
    if field_status == RawFieldStatus.METADATA.value:
        return 80
    if field_status == RawFieldStatus.WEAK_SIGNAL.value:
        return 90
    return 60


def _is_high_coverage_usable_field(field_payload: Mapping[str, Any]) -> bool:
    try:
        coverage_rate = Decimal(str(field_payload.get("sku_coverage_rate") or "0"))
    except Exception:
        coverage_rate = Decimal("0")
    return (
        str(field_payload.get("field_status") or "") == RawFieldStatus.USABLE.value
        and coverage_rate >= Decimal("0.500000")
    )


def _review_payload(
    *,
    taxonomy_version: str,
    project_id: str,
    category_code: str,
    item_type: str,
    severity: str,
    raw_param_name: str | None,
    param_code: str | None,
    issue_summary_cn: str,
    evidence_json: dict[str, Any],
    suggested_action: str,
) -> dict[str, Any]:
    return {
        "review_item_id": _id(
            "m03ari",
            project_id,
            category_code,
            taxonomy_version,
            item_type,
            raw_param_name or "",
            param_code or "",
            issue_summary_cn,
        ),
        "item_type": item_type,
        "severity": severity,
        "raw_param_name": raw_param_name,
        "param_code": param_code,
        "issue_summary_cn": issue_summary_cn,
        "evidence_json": evidence_json,
        "suggested_action": suggested_action,
        "review_decision_json": {},
        "review_status": TaxonomyReviewStatus.REVIEW_REQUIRED.value,
    }


def _dedupe_review_items(review_items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str | None, str | None], dict[str, Any]] = {}
    severity_rank = {
        TaxonomyReviewSeverity.INFO.value: 0,
        TaxonomyReviewSeverity.WARNING.value: 1,
        TaxonomyReviewSeverity.BLOCKING.value: 2,
    }
    for item in review_items:
        key = (
            str(item.get("item_type") or ""),
            _optional_text(item.get("raw_param_name")),
            _optional_text(item.get("param_code")),
        )
        existing = deduped.get(key)
        if existing is None or severity_rank.get(str(item.get("severity")), 0) > severity_rank.get(str(existing.get("severity")), 0):
            deduped[key] = dict(item)
    return list(deduped.values())


def _default_taxonomy_version(category_code: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{category_code.lower()}_param_taxonomy_{timestamp}"


def _id(prefix: str, *parts: Any) -> str:
    digest = stable_hash([str(part) for part in parts], version=M03A_ID_HASH_VERSION).split(":")[-1][:32]
    return f"{prefix}_{digest}"
