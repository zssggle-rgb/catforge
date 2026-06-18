"""M01 domain cleaners for market, attribute, claim and comment rows."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from app.services.core3_real_data.cleaning_normalizers import (
    CleanHashService,
    MISSING_COLUMN,
    NumberParser,
    PeriodParser,
    SentenceSplitter,
    TextNormalizer,
    ValuePresenceClassifier,
    check_average_price,
    extract_claim_seq,
    extract_number_candidates,
    is_low_value_comment,
)
from app.services.core3_real_data.constants import (
    CORE3_M01_CLEAN_HASH_VERSION,
    CORE3_M01_CLEAN_VERSION,
    Core3CategoryCode,
    Core3CleanQualityStatus,
    Core3CleanRecordStatus,
    Core3QualityIssueType,
    Core3ReviewStatus,
    Core3SourceOperationType,
    Core3ValuePresenceStatus,
)
from app.services.core3_real_data.hash_utils import stable_hash


@dataclass(frozen=True)
class CleaningSourceContext:
    project_id: str
    batch_id: str
    source_table: str
    source_pk: str
    source_row_id: str
    source_operation_type: Core3SourceOperationType | str
    category_code: Core3CategoryCode | str = Core3CategoryCode.TV
    run_id: str | None = None
    module_run_id: str | None = None
    source_row_hash: str | None = None
    clean_version: str = CORE3_M01_CLEAN_VERSION
    hash_version: str = CORE3_M01_CLEAN_HASH_VERSION

    def common_payload(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "category_code": _enum_value(self.category_code),
            "batch_id": self.batch_id,
            "run_id": self.run_id,
            "module_run_id": self.module_run_id,
            "source_table": self.source_table,
            "source_pk": self.source_pk,
            "source_row_id": self.source_row_id,
            "source_row_hash": self.source_row_hash,
            "source_operation_type": _enum_value(self.source_operation_type),
            "clean_version": self.clean_version,
            "hash_version": self.hash_version,
            "record_status": Core3CleanRecordStatus.ACTIVE.value,
            "review_required": False,
            "review_status": Core3ReviewStatus.AUTO_PASS.value,
        }


@dataclass(frozen=True)
class MarketCleanResult:
    market: dict[str, Any]


@dataclass(frozen=True)
class AttributeCleanResult:
    attribute: dict[str, Any]


@dataclass(frozen=True)
class ClaimCleanResult:
    claim: dict[str, Any] | None
    sentences: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class CommentCleanResult:
    comment: dict[str, Any]
    sentences: list[dict[str, Any]] = field(default_factory=list)
    dimension: dict[str, Any] | None = None


@dataclass(frozen=True)
class CleanSkuBuildResult:
    skus: list[dict[str, Any]]


@dataclass(frozen=True)
class QualityIssueBuildResult:
    issues: list[dict[str, Any]]


class MarketCleaner:
    def clean(self, row: Mapping[str, Any], context: CleaningSourceContext) -> MarketCleanResult:
        period = PeriodParser.parse(_field(row, "date_value"))
        sales_volume = NumberParser.parse(_field(row, "sales_volume"))
        sales_amount = NumberParser.parse(_field(row, "sales_amount"))
        avg_price = NumberParser.parse(_field(row, "avg_price"))
        price_check = check_average_price(
            sales_amount=sales_amount.value,
            sales_volume=sales_volume.value,
            avg_price=avg_price.value,
        )
        quality_flags = _issue_values(
            [
                sales_volume.issue_type,
                sales_amount.issue_type,
                avg_price.issue_type,
                price_check.issue_type,
                Core3QualityIssueType.INVALID_NUMBER if period.period_parse_status == "failed" else None,
            ]
        )

        payload = {
            **context.common_payload(),
            "source_table": "week_sales_data",
            "sku_code": _clean_text(_field(row, "model_code")),
            "model_name": _clean_text(_field(row, "model")),
            "brand_name": _clean_text(_field(row, "brand")),
            "category_name_raw": _clean_text(_field(row, "category")),
            "period_raw": _clean_text(_field(row, "date_value")),
            "period_type": period.period_type,
            "period_year_hint": period.period_year_hint,
            "period_week_index": period.period_week_index,
            "period_parse_status": period.period_parse_status,
            "channel_raw": _clean_text(_field(row, "channel")),
            "channel_type": _clean_text(_field(row, "channel")),
            "platform_raw": _clean_text(_field(row, "platform")),
            "platform_type": _clean_text(_field(row, "platform")),
            "sales_volume_raw": _string_or_none(_field(row, "sales_volume")),
            "sales_volume": sales_volume.value,
            "sales_amount_raw": _string_or_none(_field(row, "sales_amount")),
            "sales_amount": sales_amount.value,
            "avg_price_raw": _string_or_none(_field(row, "avg_price")),
            "avg_price": avg_price.value,
            "avg_price_expected": price_check.expected_price,
            "price_check_status": price_check.status,
            "price_check_delta": price_check.delta,
            "clean_record_key": CleanHashService.clean_record_key("market", context.source_row_id),
            "quality_status": _quality_status(quality_flags),
            "quality_flags": quality_flags,
        }
        payload["clean_hash"] = CleanHashService.clean_hash("market", payload)
        return MarketCleanResult(market=payload)


class AttributeCleaner:
    def clean(self, row: Mapping[str, Any], context: CleaningSourceContext) -> AttributeCleanResult:
        raw_attr_value = _field(row, "attr_value")
        value_presence = ValuePresenceClassifier.classify(raw_attr_value, field_exists="attr_value" in row)
        number_candidates = extract_number_candidates(raw_attr_value)
        unit_candidates = sorted({candidate["unit"] for candidate in number_candidates if "unit" in candidate})
        quality_flags = []
        if value_presence != Core3ValuePresenceStatus.PRESENT:
            quality_flags.append(Core3QualityIssueType.UNKNOWN_VALUE.value)

        payload = {
            **context.common_payload(),
            "source_table": "attribute_data",
            "sku_code": _clean_text(_field(row, "model_code")),
            "model_name": _clean_text(_field(row, "model")),
            "brand_name": _clean_text(_field(row, "brand")),
            "raw_attr_name": _string_or_none(_field(row, "attr_name")),
            "clean_attr_name": _clean_text(_field(row, "attr_name")),
            "raw_attr_value": _string_or_none(raw_attr_value),
            "clean_attr_value": _clean_text(raw_attr_value) if value_presence == Core3ValuePresenceStatus.PRESENT else None,
            "value_presence": value_presence.value,
            "value_number_candidates": number_candidates,
            "value_unit_candidates": unit_candidates,
            "raw_value_token_count": len(str(raw_attr_value).split()) if raw_attr_value is not MISSING_COLUMN else None,
            "conflict_group_key": _attribute_conflict_group(row),
            "clean_record_key": CleanHashService.clean_record_key("attribute", context.source_row_id),
            "quality_status": _quality_status(quality_flags),
            "quality_flags": quality_flags,
        }
        payload["clean_hash"] = CleanHashService.clean_hash("attribute", payload)
        return AttributeCleanResult(attribute=payload)


class ClaimCleaner:
    def clean(self, row: Mapping[str, Any], context: CleaningSourceContext) -> ClaimCleanResult:
        raw_claim_text = _field(row, "selling_point")
        claim_presence = ValuePresenceClassifier.classify(raw_claim_text, field_exists="selling_point" in row)
        if claim_presence != Core3ValuePresenceStatus.PRESENT:
            return ClaimCleanResult(claim=None, sentences=[])

        claim_seq = extract_claim_seq(_field(row, "variable"))
        quality_flags = []
        if claim_seq is None:
            quality_flags.append(Core3QualityIssueType.CLAIM_SEQ_PARSE_FAILED.value)

        clean_claim_text = _clean_text(raw_claim_text)
        payload = {
            **context.common_payload(),
            "source_table": "selling_points_data",
            "sku_code": _clean_text(_field(row, "model_code")),
            "model_name": _clean_text(_field(row, "model")),
            "brand_name": _clean_text(_field(row, "brand")),
            "claim_seq_raw": _string_or_none(_field(row, "variable")),
            "claim_seq": claim_seq,
            "raw_claim_text": _string_or_none(raw_claim_text),
            "clean_claim_text": clean_claim_text,
            "claim_text_presence": claim_presence.value,
            "title_hint": _claim_title_hint(clean_claim_text),
            "structure_hints": _claim_structure_hints(clean_claim_text),
            "clean_record_key": CleanHashService.clean_record_key("claim", context.source_row_id),
            "quality_status": _quality_status(quality_flags),
            "quality_flags": quality_flags,
        }
        payload["clean_hash"] = CleanHashService.clean_hash("claim", payload)
        sentences = [
            _sentence_payload(
                context,
                "claim_sentence",
                payload,
                sentence,
                sentence_seq=index,
                extra={
                    "claim_seq": claim_seq,
                    "sentence_role_hint": None,
                },
            )
            for index, sentence in enumerate(SentenceSplitter.split(clean_claim_text), start=1)
        ]
        return ClaimCleanResult(claim=payload, sentences=sentences)


class CommentCleaner:
    def clean(self, row: Mapping[str, Any], context: CleaningSourceContext) -> CommentCleanResult:
        raw_comment_text = _field(row, "comment_content")
        clean_comment_text = _clean_text(raw_comment_text)
        text_presence = ValuePresenceClassifier.classify(raw_comment_text, field_exists="comment_content" in row)
        segment_raw = _field(row, "comments_segments")
        segment_clean = _clean_text(segment_raw)
        sentiment_clean = _clean_sentiment(_field(row, "sentiment"))
        low_value = is_low_value_comment(clean_comment_text)
        dimension_payload = self._dimension(row, context)
        quality_flags = []
        if text_presence != Core3ValuePresenceStatus.PRESENT:
            quality_flags.append(Core3QualityIssueType.UNKNOWN_VALUE.value)
        if low_value:
            quality_flags.append(Core3QualityIssueType.LOW_VALUE_COMMENT.value)

        payload = {
            **context.common_payload(),
            "source_table": "comment_data",
            "sku_code": _clean_text(_field(row, "model_code")),
            "model_name": _clean_text(_field(row, "model")),
            "brand_name": _clean_text(_field(row, "brand")),
            "platform_raw": _clean_text(_field(row, "platform")),
            "url_id": _string_or_none(_field(row, "url_id")),
            "comment_id": _string_or_none(_field(row, "comment_id")),
            "comment_time_raw": _string_or_none(_field(row, "comment_time")),
            "comment_time": _parse_datetime(_field(row, "comment_time")),
            "comment_time_parse_status": "parsed" if _parse_datetime(_field(row, "comment_time")) else "missing",
            "raw_comment_text": _string_or_none(raw_comment_text),
            "clean_comment_text": clean_comment_text,
            "comment_text_presence": text_presence.value,
            "comment_text_hash": stable_hash(clean_comment_text, version=CORE3_M01_CLEAN_HASH_VERSION)
            if clean_comment_text
            else None,
            "segment_text_raw": _string_or_none(segment_raw),
            "segment_text_clean": segment_clean,
            "segment_text_hash": stable_hash(segment_clean, version=CORE3_M01_CLEAN_HASH_VERSION)
            if segment_clean
            else None,
            "sentiment_raw": _string_or_none(_field(row, "sentiment")),
            "sentiment_clean": sentiment_clean,
            "low_value_flag": low_value,
            "low_value_reason": "默认或空评价" if low_value else None,
            "duplicate_group_key": stable_hash(clean_comment_text, version=CORE3_M01_CLEAN_HASH_VERSION)
            if clean_comment_text
            else None,
            "dimension_available": bool(dimension_payload and dimension_payload["dimension_available"]),
            "clean_record_key": CleanHashService.clean_record_key("comment", context.source_row_id),
            "quality_status": _quality_status(quality_flags),
            "quality_flags": quality_flags,
        }
        payload["clean_hash"] = CleanHashService.clean_hash("comment", payload)

        sentences = []
        if not low_value:
            sentences.extend(
                _sentence_payload(
                    context,
                    "comment_sentence",
                    payload,
                    sentence,
                    sentence_seq=index,
                    extra={
                        "comment_id": payload["comment_id"],
                        "sentence_source": "system_split",
                        "source_segment_text": None,
                        "is_from_existing_segment": False,
                    },
                )
                for index, sentence in enumerate(SentenceSplitter.split(clean_comment_text), start=1)
            )
        if segment_clean and not low_value:
            for index, sentence in enumerate(SentenceSplitter.split(segment_clean), start=1):
                sentences.append(
                    _sentence_payload(
                        context,
                        "comment_sentence",
                        payload,
                        sentence,
                        sentence_seq=index,
                        extra={
                            "comment_id": payload["comment_id"],
                            "sentence_source": "source_segment",
                            "source_segment_text": segment_clean,
                            "is_from_existing_segment": True,
                        },
                    )
                )

        return CommentCleanResult(comment=payload, sentences=sentences, dimension=dimension_payload)

    def _dimension(self, row: Mapping[str, Any], context: CleaningSourceContext) -> dict[str, Any]:
        primary = _clean_text(_field(row, "primary_dim"))
        secondary = _clean_text(_field(row, "secondary_dim"))
        third = _clean_text(_field(row, "third_dim"))
        dimension_parts = [part for part in [primary, secondary, third] if part]
        payload = {
            **context.common_payload(),
            "source_table": "comment_data",
            "sku_code": _clean_text(_field(row, "model_code")),
            "comment_id": _string_or_none(_field(row, "comment_id")),
            "primary_dim_raw": primary,
            "secondary_dim_raw": secondary,
            "third_dim_raw": third,
            "dimension_path_raw": "/".join(dimension_parts) if dimension_parts else None,
            "dimension_available": bool(dimension_parts),
            "dimension_quality_flag": "ok" if dimension_parts else "missing",
            "clean_record_key": CleanHashService.clean_record_key("comment_dimension", context.source_row_id),
            "quality_status": "ok" if dimension_parts else "warning",
            "quality_flags": [] if dimension_parts else [Core3QualityIssueType.COMMENT_DIMENSION_MISSING.value],
        }
        payload["clean_hash"] = CleanHashService.clean_hash("comment_dimension", payload)
        return payload


class CleanSkuBuilder:
    def build(
        self,
        *,
        project_id: str,
        batch_id: str,
        markets: list[Mapping[str, Any]] | None = None,
        attributes: list[Mapping[str, Any]] | None = None,
        claims: list[Mapping[str, Any]] | None = None,
        comments: list[Mapping[str, Any]] | None = None,
        comment_dimensions: list[Mapping[str, Any]] | None = None,
        market_scope: Mapping[str, Any] | None = None,
        category_code: Core3CategoryCode | str = Core3CategoryCode.TV,
        run_id: str | None = None,
        module_run_id: str | None = None,
        clean_version: str = CORE3_M01_CLEAN_VERSION,
        hash_version: str = CORE3_M01_CLEAN_HASH_VERSION,
    ) -> CleanSkuBuildResult:
        records_by_domain = {
            "market": list(markets or []),
            "attribute": list(attributes or []),
            "claim": list(claims or []),
            "comment": list(comments or []),
        }
        comment_dimension_records = list(comment_dimensions or [])
        market_scope_json = dict(market_scope or build_market_batch_scope(records_by_domain["market"]))
        sku_codes = sorted(
            {
                str(record["sku_code"])
                for records in records_by_domain.values()
                for record in records
                if record.get("sku_code")
            }
        )

        sku_payloads: list[dict[str, Any]] = []
        for sku_code in sku_codes:
            domain_records = {
                domain: [record for record in records if record.get("sku_code") == sku_code]
                for domain, records in records_by_domain.items()
            }
            sku_comment_dimensions = [
                record for record in comment_dimension_records if record.get("sku_code") == sku_code
            ]
            source_tables = sorted(
                {
                    str(record["source_table"])
                    for records in domain_records.values()
                    for record in records
                    if record.get("source_table")
                }
            )
            coverage_json = _coverage_json(
                domain_records,
                market_scope=market_scope_json,
                comment_dimensions=sku_comment_dimensions,
            )
            field_conflicts_json = _field_conflicts_json(domain_records)
            missing_signals_json = _missing_signals_json(coverage_json)
            quality_flags = _sku_quality_flags(field_conflicts_json, missing_signals_json)
            representative_source_row_ids = [
                record["source_row_id"]
                for records in domain_records.values()
                for record in records
                if record.get("source_row_id")
            ][:20]
            payload = {
                "project_id": project_id,
                "category_code": _enum_value(category_code),
                "batch_id": batch_id,
                "run_id": run_id,
                "module_run_id": module_run_id,
                "sku_code": sku_code,
                "sku_code_raw_values": [sku_code],
                "model_name": _first_non_empty(
                    record.get("model_name")
                    for records in domain_records.values()
                    for record in records
                ),
                "model_name_raw_values": _unique_non_empty(
                    record.get("model_name")
                    for records in domain_records.values()
                    for record in records
                ),
                "brand_name": _first_non_empty(
                    record.get("brand_name")
                    for records in domain_records.values()
                    for record in records
                ),
                "brand_raw_values": _unique_non_empty(
                    record.get("brand_name")
                    for records in domain_records.values()
                    for record in records
                ),
                "category_name": _first_non_empty(
                    record.get("category_name_raw") or record.get("category_name")
                    for records in domain_records.values()
                    for record in records
                ),
                "source_tables": source_tables,
                "first_seen_source_row_id": representative_source_row_ids[0] if representative_source_row_ids else None,
                "representative_source_row_ids": representative_source_row_ids,
                "coverage_json": coverage_json,
                "field_conflicts_json": field_conflicts_json,
                "missing_signals_json": missing_signals_json,
                "clean_record_key": CleanHashService.clean_record_key("sku", sku_code),
                "clean_version": clean_version,
                "hash_version": hash_version,
                "quality_status": _quality_status(quality_flags),
                "quality_flags": quality_flags,
                "review_required": bool(quality_flags),
                "review_status": (
                    Core3ReviewStatus.REVIEW_REQUIRED.value
                    if quality_flags
                    else Core3ReviewStatus.AUTO_PASS.value
                ),
            }
            payload["clean_hash"] = CleanHashService.clean_hash("sku", payload)
            sku_payloads.append(payload)

        return CleanSkuBuildResult(skus=sku_payloads)


class QualityIssueBuilder:
    def build(
        self,
        *,
        project_id: str,
        batch_id: str,
        clean_skus: list[Mapping[str, Any]] | None = None,
        markets: list[Mapping[str, Any]] | None = None,
        attributes: list[Mapping[str, Any]] | None = None,
        claims: list[Mapping[str, Any]] | None = None,
        comments: list[Mapping[str, Any]] | None = None,
        comment_dimensions: list[Mapping[str, Any]] | None = None,
        category_code: Core3CategoryCode | str = Core3CategoryCode.TV,
        run_id: str | None = None,
        module_run_id: str | None = None,
    ) -> QualityIssueBuildResult:
        issues: list[dict[str, Any]] = []
        common = {
            "project_id": project_id,
            "category_code": _enum_value(category_code),
            "batch_id": batch_id,
            "run_id": run_id,
            "module_run_id": module_run_id,
            "module_code": "M01",
        }

        for sku in clean_skus or []:
            sku_code = sku.get("sku_code")
            missing_signals = sku.get("missing_signals_json") or {}
            field_conflicts = sku.get("field_conflicts_json") or {}
            if missing_signals.get("claim_structured", {}).get("missing"):
                issues.append(
                    _quality_issue(
                        common,
                        domain="claim",
                        issue_type=Core3QualityIssueType.CLAIM_COVERAGE_MISSING.value,
                        severity="warning",
                        issue_detail="结构化卖点数据缺失，不代表该 SKU 没有卖点",
                        clean_table="core3_clean_sku",
                        clean_record_key=sku.get("clean_record_key"),
                        sku_code=sku_code,
                        issue_payload_json={"missing_signal": missing_signals["claim_structured"]},
                        suggested_downstream_action="M04a 不得伪造卖点事实，后续只能按未知处理",
                        review_required=True,
                    )
                )
            for field_name, conflict in field_conflicts.items():
                if conflict.get("has_conflict"):
                    issues.append(
                        _quality_issue(
                            common,
                            domain="sku",
                            issue_type=Core3QualityIssueType.CROSS_TABLE_CONFLICT.value,
                            severity="warning",
                            issue_detail=f"SKU {sku_code} 的 {field_name} 跨表值不一致",
                            clean_table="core3_clean_sku",
                            clean_record_key=sku.get("clean_record_key"),
                            sku_code=sku_code,
                            issue_payload_json={"field": field_name, "values": conflict.get("values", [])},
                            suggested_downstream_action="下游画像可继续，但高层报告需要保留数据口径提示",
                            review_required=True,
                        )
                    )

        for market in markets or []:
            issues.extend(self._issues_from_quality_flags(common, market, domain="market", clean_table="core3_clean_market_weekly"))
        for attribute in attributes or []:
            issues.extend(
                self._issues_from_quality_flags(
                    common,
                    attribute,
                    domain="param",
                    clean_table="core3_clean_attribute",
                )
            )
        for claim in claims or []:
            issues.extend(
                self._issues_from_quality_flags(
                    common,
                    claim,
                    domain="claim",
                    clean_table="core3_clean_claim",
                )
            )
        for comment in comments or []:
            issues.extend(
                self._issues_from_quality_flags(
                    common,
                    comment,
                    domain="comment",
                    clean_table="core3_clean_comment",
                )
            )
        for dimension in comment_dimensions or []:
            issues.extend(
                self._issues_from_quality_flags(
                    common,
                    dimension,
                    domain="comment",
                    clean_table="core3_clean_comment_dimension",
                )
            )
        issues.extend(self._duplicate_comment_issues(common, comments or []))

        return QualityIssueBuildResult(issues=_dedupe_issues(issues))

    def _issues_from_quality_flags(
        self,
        common: Mapping[str, Any],
        payload: Mapping[str, Any],
        *,
        domain: str,
        clean_table: str,
    ) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        for issue_type in payload.get("quality_flags") or []:
            issue_type = str(issue_type)
            if clean_table == "core3_clean_comment" and issue_type == Core3QualityIssueType.LOW_VALUE_COMMENT.value:
                continue
            issues.append(
                _quality_issue(
                    common,
                    domain=domain,
                    issue_type=issue_type,
                    severity=_severity_for_issue_type(issue_type),
                    issue_detail=_issue_detail(issue_type, payload),
                    source_table=payload.get("source_table"),
                    source_row_id=payload.get("source_row_id"),
                    clean_table=clean_table,
                    clean_record_key=payload.get("clean_record_key"),
                    sku_code=payload.get("sku_code"),
                    issue_payload_json=_issue_payload(issue_type, payload),
                    suggested_downstream_action=_suggested_downstream_action(issue_type),
                    review_required=_review_required_for_issue_type(issue_type),
                )
            )
        return issues

    def _duplicate_comment_issues(
        self,
        common: Mapping[str, Any],
        comments: list[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        by_hash: dict[str, list[Mapping[str, Any]]] = {}
        for comment in comments:
            if comment.get("low_value_flag"):
                continue
            comment_hash = comment.get("comment_text_hash")
            if comment_hash:
                by_hash.setdefault(str(comment_hash), []).append(comment)

        issues: list[dict[str, Any]] = []
        for comment_hash, rows in by_hash.items():
            if len(rows) < 2:
                continue
            for row in rows:
                issues.append(
                    _quality_issue(
                        common,
                        domain="comment",
                        issue_type=Core3QualityIssueType.DUPLICATE_COMMENT_TEXT.value,
                        severity="warning",
                        issue_detail="评论正文重复，保留清洗事实但下游需要降权或复核",
                        source_table=row.get("source_table"),
                        source_row_id=row.get("source_row_id"),
                        clean_table="core3_clean_comment",
                        clean_record_key=row.get("clean_record_key"),
                        sku_code=row.get("sku_code"),
                        issue_payload_json={
                            "comment_text_hash": comment_hash,
                            "duplicate_count": len(rows),
                        },
                        suggested_downstream_action="M05/M06 使用评论证据时避免重复放大同一正文",
                        review_required=False,
                    )
                )
        return issues


def _field(row: Mapping[str, Any], name: str) -> Any:
    return row[name] if name in row else MISSING_COLUMN


def _clean_text(value: Any) -> str | None:
    if value is MISSING_COLUMN:
        return None
    return TextNormalizer.normalize(value)


def _string_or_none(value: Any) -> str | None:
    if value is MISSING_COLUMN or value is None:
        return None
    return str(value)


def _parse_datetime(value: Any) -> datetime | None:
    if value is MISSING_COLUMN or value is None or isinstance(value, datetime):
        return value if isinstance(value, datetime) else None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _enum_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else value


def _issue_values(issue_types: list[Core3QualityIssueType | None]) -> list[str]:
    return [issue_type.value for issue_type in issue_types if issue_type is not None]


def _quality_status(quality_flags: list[str]) -> str:
    return Core3CleanQualityStatus.WARNING.value if quality_flags else Core3CleanQualityStatus.OK.value


SERVICE_COMMENT_TERMS: tuple[str, ...] = (
    "客服",
    "服务",
    "物流",
    "配送",
    "快递",
    "安装",
    "售后",
    "退货",
    "退款",
    "发货",
    "送货",
    "维修",
    "保修",
    "包装",
    "上门",
    "师傅",
    "店家",
    "商家",
)


def build_market_batch_scope(markets: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...]) -> dict[str, Any]:
    week_records = [
        {
            "period_week_index": int(row["period_week_index"]),
            "period_raw": row.get("period_raw"),
            "period_year_hint": row.get("period_year_hint"),
        }
        for row in markets
        if row.get("period_week_index") is not None
    ]
    if not week_records:
        return {
            "batch_first_week_index": None,
            "batch_last_week_index": None,
            "batch_expected_week_count": 0,
            "batch_weeks": [],
        }

    first_week = min(row["period_week_index"] for row in week_records)
    last_week = max(row["period_week_index"] for row in week_records)
    labels_by_week = {
        row["period_week_index"]: str(row["period_raw"])
        for row in week_records
        if row.get("period_raw")
    }
    year_hints = [int(row["period_year_hint"]) for row in week_records if row.get("period_year_hint")]
    default_year_hint = year_hints[0] if year_hints else None
    return {
        "batch_first_week_index": first_week,
        "batch_last_week_index": last_week,
        "batch_first_week": _week_label(first_week, labels_by_week, default_year_hint),
        "batch_last_week": _week_label(last_week, labels_by_week, default_year_hint),
        "batch_expected_week_count": last_week - first_week + 1,
        "batch_weeks": [
            _week_label(week_index, labels_by_week, default_year_hint)
            for week_index in range(first_week, last_week + 1)
        ],
    }


def build_preliminary_cleaning_summary(
    clean_skus: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
) -> dict[str, Any]:
    market_summaries = []
    comment_summaries = []
    for sku in clean_skus:
        coverage_json = _record_value(sku, "coverage_json") or {}
        market = coverage_json.get("market") or {}
        comment = coverage_json.get("comment") or {}
        if market:
            market_summaries.append(market.get("weekly_coverage") or {})
        if comment:
            comment_summaries.append(comment.get("preliminary_filter") or {})

    market_summary = {
        "sku_count": len(clean_skus),
        "market_covered_sku_count": sum(1 for item in market_summaries if item.get("covered")),
        "full_week_coverage_sku_count": sum(
            1 for item in market_summaries if item.get("covered") and item.get("missing_week_count", 0) == 0
        ),
        "sku_with_leading_absence_count": sum(
            1 for item in market_summaries if item.get("leading_absence_week_count", 0) > 0
        ),
        "sku_with_trailing_absence_count": sum(
            1 for item in market_summaries if item.get("trailing_absence_week_count", 0) > 0
        ),
        "sku_with_internal_gap_count": sum(
            1 for item in market_summaries if item.get("internal_gap_week_count", 0) > 0
        ),
        "sku_with_single_platform_week_count": sum(
            1 for item in market_summaries if item.get("single_platform_week_count", 0) > 0
        ),
        "missing_sku_week_count": sum(int(item.get("missing_week_count") or 0) for item in market_summaries),
        "leading_absence_sku_week_count": sum(
            int(item.get("leading_absence_week_count") or 0) for item in market_summaries
        ),
        "trailing_absence_sku_week_count": sum(
            int(item.get("trailing_absence_week_count") or 0) for item in market_summaries
        ),
        "internal_gap_sku_week_count": sum(int(item.get("internal_gap_week_count") or 0) for item in market_summaries),
        "explanation_cn": [
            "SKU+周只要任一平台有量价行，即视为该 SKU 该周有覆盖。",
            "同一周单平台有数据正常，通常表示单平台销售或平台特供。",
            "首周前缺失按新品/后入样本解释，末周后缺失按退市/离样本解释，不直接判为质量问题。",
            "首末观察周之间的缺失才记为内部断档软提示，供下游趋势分析谨慎使用。",
        ],
    }

    raw_comment_count = sum(int(item.get("raw_row_count") or 0) for item in comment_summaries)
    low_value_count = sum(int(item.get("low_value_comment_count") or 0) for item in comment_summaries)
    service_candidate_count = sum(int(item.get("service_candidate_count") or 0) for item in comment_summaries)
    service_after_low_value_count = sum(
        int(item.get("service_candidate_after_low_value_count") or 0) for item in comment_summaries
    )
    comment_summary = {
        "sku_with_comment_count": sum(1 for item in comment_summaries if item.get("raw_row_count", 0) > 0),
        "raw_comment_count": raw_comment_count,
        "low_value_comment_count": low_value_count,
        "low_value_comment_rate": _rate(low_value_count, raw_comment_count),
        "candidate_after_low_value_count": sum(
            int(item.get("candidate_after_low_value_count") or 0) for item in comment_summaries
        ),
        "duplicate_text_group_count": sum(
            int(item.get("duplicate_text_group_count") or 0) for item in comment_summaries
        ),
        "duplicate_text_row_count": sum(int(item.get("duplicate_text_row_count") or 0) for item in comment_summaries),
        "service_candidate_count": service_candidate_count,
        "service_candidate_rate": _rate(service_candidate_count, raw_comment_count),
        "service_candidate_after_low_value_count": service_after_low_value_count,
        "service_candidate_after_low_value_rate": _rate(
            service_after_low_value_count,
            max(raw_comment_count - low_value_count, 0),
        ),
        "service_candidate_not_blocked": True,
        "explanation_cn": [
            "本阶段只快速过滤空、默认、明显低质评论。",
            "服务类评论仅做候选计数，不提前拦截；后续根据占比再判断是否前置拦截。",
        ],
    }
    return {
        "market_coverage_summary": market_summary,
        "comment_preliminary_summary": comment_summary,
    }


def _coverage_json(
    domain_records: Mapping[str, list[Mapping[str, Any]]],
    *,
    market_scope: Mapping[str, Any] | None = None,
    comment_dimensions: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    attributes = domain_records["attribute"]
    comments = domain_records["comment"]
    markets = domain_records["market"]
    return {
        "market": {
            "row_count": len(markets),
            "covered": bool(markets),
            "weekly_coverage": _market_weekly_coverage_json(markets, market_scope or {}),
        },
        "attribute": {
            "row_count": len(attributes),
            "covered": bool(attributes),
            "unknown_count": sum(1 for row in attributes if row.get("value_presence") != "present"),
        },
        "claim": {
            "row_count": len(domain_records["claim"]),
            "covered": bool(domain_records["claim"]),
        },
        "comment": {
            "row_count": len(comments),
            "covered": bool(comments),
            "distinct_comment_id_count": len({row.get("comment_id") for row in comments if row.get("comment_id")}),
            "preliminary_filter": _comment_preliminary_filter_json(comments, comment_dimensions or []),
        },
    }


def _market_weekly_coverage_json(
    markets: list[Mapping[str, Any]],
    market_scope: Mapping[str, Any],
) -> dict[str, Any]:
    first_batch_week = market_scope.get("batch_first_week_index")
    last_batch_week = market_scope.get("batch_last_week_index")
    if first_batch_week is None or last_batch_week is None:
        return {
            "covered": False,
            "batch_expected_week_count": 0,
            "active_week_count": 0,
            "missing_week_count": 0,
            "single_platform_week_count": 0,
            "business_interpretation_cn": [
                "本批未形成可解析的周度量价范围，不能据此判断 SKU 是否缺周。",
            ],
        }

    labels_by_week = _labels_by_week(markets, market_scope)
    default_year_hint = _default_year_hint(markets)
    expected_weeks = list(range(int(first_batch_week), int(last_batch_week) + 1))
    by_week: dict[int, list[Mapping[str, Any]]] = {}
    for row in markets:
        if row.get("period_week_index") is None:
            continue
        by_week.setdefault(int(row["period_week_index"]), []).append(row)

    observed_weeks = sorted(set(by_week))
    if not observed_weeks:
        missing_weeks = [_week_label(week, labels_by_week, default_year_hint) for week in expected_weeks]
        return {
            "covered": False,
            "batch_first_week": market_scope.get("batch_first_week"),
            "batch_last_week": market_scope.get("batch_last_week"),
            "batch_expected_week_count": len(expected_weeks),
            "active_week_count": 0,
            "missing_week_count": len(missing_weeks),
            "missing_weeks": missing_weeks,
            "single_platform_week_count": 0,
            "business_interpretation_cn": [
                "本批未观察到该 SKU 的量价周度行，只能解释为本批市场数据未覆盖该 SKU。",
            ],
        }

    first_seen = observed_weeks[0]
    last_seen = observed_weeks[-1]
    observed_set = set(observed_weeks)
    leading_absence_weeks = [week for week in expected_weeks if week < first_seen and week not in observed_set]
    trailing_absence_weeks = [week for week in expected_weeks if week > last_seen and week not in observed_set]
    internal_gap_weeks = [
        week for week in expected_weeks if first_seen < week < last_seen and week not in observed_set
    ]
    missing_weeks = leading_absence_weeks + internal_gap_weeks + trailing_absence_weeks
    platform_counts_by_week = {
        week: len(
            {
                str(row.get("platform_type") or row.get("platform_raw"))
                for row in rows
                if row.get("platform_type") or row.get("platform_raw")
            }
        )
        for week, rows in by_week.items()
    }
    platform_distribution = Counter(str(count) for count in platform_counts_by_week.values())
    return {
        "covered": True,
        "batch_first_week": market_scope.get("batch_first_week"),
        "batch_last_week": market_scope.get("batch_last_week"),
        "batch_expected_week_count": len(expected_weeks),
        "first_seen_week": _week_label(first_seen, labels_by_week, default_year_hint),
        "last_seen_week": _week_label(last_seen, labels_by_week, default_year_hint),
        "active_week_count": len(observed_weeks),
        "active_weeks": [_week_label(week, labels_by_week, default_year_hint) for week in observed_weeks],
        "covered_week_rate": _rate(len(observed_weeks), len(expected_weeks)),
        "missing_week_count": len(missing_weeks),
        "missing_weeks": [_week_label(week, labels_by_week, default_year_hint) for week in missing_weeks],
        "leading_absence_week_count": len(leading_absence_weeks),
        "leading_absence_weeks": [
            _week_label(week, labels_by_week, default_year_hint) for week in leading_absence_weeks
        ],
        "trailing_absence_week_count": len(trailing_absence_weeks),
        "trailing_absence_weeks": [
            _week_label(week, labels_by_week, default_year_hint) for week in trailing_absence_weeks
        ],
        "internal_gap_week_count": len(internal_gap_weeks),
        "internal_gap_weeks": [_week_label(week, labels_by_week, default_year_hint) for week in internal_gap_weeks],
        "single_platform_week_count": sum(1 for count in platform_counts_by_week.values() if count == 1),
        "multi_platform_week_count": sum(1 for count in platform_counts_by_week.values() if count > 1),
        "platform_count_distribution": dict(sorted(platform_distribution.items())),
        "single_platform_is_normal": True,
        "normal_missing_patterns": [
            "leading_absence_as_new_or_late_entry",
            "trailing_absence_as_delisted_or_out_of_sample",
            "single_platform_week_as_single_channel_or_platform_special",
        ],
        "soft_warning_codes": ["market_internal_gap"] if internal_gap_weeks else [],
        "business_interpretation_cn": [
            "SKU+周只要任一平台有量价行，即视为该 SKU 该周有覆盖。",
            "同一周单平台有数据正常，通常表示单平台销售或平台特供。",
            "首周前缺失按新品/后入样本解释，末周后缺失按退市/离样本解释，不直接判为质量问题。",
            "首末观察周之间缺失才作为内部断档软提示。",
        ],
    }


def _comment_preliminary_filter_json(
    comments: list[Mapping[str, Any]],
    comment_dimensions: list[Mapping[str, Any]],
) -> dict[str, Any]:
    raw_row_count = len(comments)
    low_value_count = sum(1 for row in comments if bool(row.get("low_value_flag")))
    text_hash_counts = Counter(
        str(row.get("comment_text_hash"))
        for row in comments
        if row.get("comment_text_hash") and not bool(row.get("low_value_flag"))
    )
    duplicate_text_group_count = sum(1 for count in text_hash_counts.values() if count > 1)
    duplicate_text_row_count = sum(count for count in text_hash_counts.values() if count > 1)
    dimension_text_by_source_row_id = {
        str(row.get("source_row_id")): " ".join(
            str(part)
            for part in (
                row.get("primary_dim_raw"),
                row.get("secondary_dim_raw"),
                row.get("third_dim_raw"),
                row.get("dimension_path_raw"),
            )
            if part
        )
        for row in comment_dimensions
        if row.get("source_row_id")
    }
    service_candidate_count = 0
    service_after_low_value_count = 0
    for row in comments:
        source_row_id = str(row.get("source_row_id") or "")
        dimension_text = dimension_text_by_source_row_id.get(source_row_id, "")
        is_service_candidate = _is_service_comment_candidate(row.get("clean_comment_text"), dimension_text)
        if is_service_candidate:
            service_candidate_count += 1
            if not bool(row.get("low_value_flag")):
                service_after_low_value_count += 1

    return {
        "raw_row_count": raw_row_count,
        "low_value_comment_count": low_value_count,
        "low_value_comment_rate": _rate(low_value_count, raw_row_count),
        "empty_or_default_comment_count": low_value_count,
        "candidate_after_low_value_count": raw_row_count - low_value_count,
        "distinct_comment_id_count": len({row.get("comment_id") for row in comments if row.get("comment_id")}),
        "distinct_comment_text_hash_count": len(text_hash_counts),
        "duplicate_text_group_count": duplicate_text_group_count,
        "duplicate_text_row_count": duplicate_text_row_count,
        "service_candidate_count": service_candidate_count,
        "service_candidate_rate": _rate(service_candidate_count, raw_row_count),
        "service_candidate_after_low_value_count": service_after_low_value_count,
        "service_candidate_after_low_value_rate": _rate(
            service_after_low_value_count,
            max(raw_row_count - low_value_count, 0),
        ),
        "service_candidate_not_blocked": True,
        "policy_cn": "本阶段仅过滤空/默认/低质评论；服务类只计数，不提前拦截。",
    }


def _field_conflicts_json(domain_records: Mapping[str, list[Mapping[str, Any]]]) -> dict[str, Any]:
    all_records = [record for records in domain_records.values() for record in records]
    return {
        "brand": _field_conflict(record.get("brand_name") for record in all_records),
        "model": _field_conflict(record.get("model_name") for record in all_records),
        "category": _field_conflict(record.get("category_name_raw") or record.get("category_name") for record in all_records),
    }


def _field_conflict(values: Any) -> dict[str, Any]:
    unique_values = _unique_non_empty(values)
    return {"has_conflict": len(unique_values) > 1, "values": unique_values}


def _missing_signals_json(coverage_json: Mapping[str, Any]) -> dict[str, Any]:
    missing_signals: dict[str, Any] = {}
    if not coverage_json["claim"]["covered"]:
        missing_signals["claim_structured"] = {
            "missing": True,
            "reason": "本批 selling_points_data 未覆盖该 SKU",
            "business_interpretation": "结构化卖点数据缺失，不代表该 SKU 没有卖点",
        }
    return missing_signals


def _sku_quality_flags(field_conflicts_json: Mapping[str, Any], missing_signals_json: Mapping[str, Any]) -> list[str]:
    quality_flags: list[str] = []
    if missing_signals_json.get("claim_structured", {}).get("missing"):
        quality_flags.append(Core3QualityIssueType.CLAIM_COVERAGE_MISSING.value)
    if any(conflict.get("has_conflict") for conflict in field_conflicts_json.values()):
        quality_flags.append(Core3QualityIssueType.CROSS_TABLE_CONFLICT.value)
    return quality_flags


def _first_non_empty(values: Any) -> str | None:
    for value in values:
        if value:
            return str(value)
    return None


def _unique_non_empty(values: Any) -> list[str]:
    unique_values: list[str] = []
    for value in values:
        if value is None or value == "":
            continue
        string_value = str(value)
        if string_value not in unique_values:
            unique_values.append(string_value)
    return unique_values


def _labels_by_week(markets: list[Mapping[str, Any]], market_scope: Mapping[str, Any]) -> dict[int, str]:
    labels: dict[int, str] = {}
    batch_weeks = market_scope.get("batch_weeks") or []
    first_week = market_scope.get("batch_first_week_index")
    if first_week is not None:
        for offset, label in enumerate(batch_weeks):
            labels[int(first_week) + offset] = str(label)
    for row in markets:
        if row.get("period_week_index") is not None and row.get("period_raw"):
            labels[int(row["period_week_index"])] = str(row["period_raw"])
    return labels


def _week_label(week_index: int, labels_by_week: Mapping[int, str], default_year_hint: int | None) -> str:
    if labels_by_week.get(week_index):
        return str(labels_by_week[week_index])
    if default_year_hint is not None:
        return f"{default_year_hint % 100:02d}W{week_index:02d}"
    return f"W{week_index:02d}"


def _default_year_hint(markets: list[Mapping[str, Any]]) -> int | None:
    for row in markets:
        if row.get("period_year_hint"):
            return int(row["period_year_hint"])
    return None


def _rate(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(part / total, 4)


def _record_value(record: Any, field_name: str) -> Any:
    if isinstance(record, Mapping):
        return record.get(field_name)
    return getattr(record, field_name, None)


def _is_service_comment_candidate(comment_text: Any, dimension_text: Any = None) -> bool:
    combined_text = f"{comment_text or ''} {dimension_text or ''}"
    return any(term in combined_text for term in SERVICE_COMMENT_TERMS)


def _quality_issue(
    common: Mapping[str, Any],
    *,
    domain: str,
    issue_type: str,
    severity: str,
    issue_detail: str,
    source_table: str | None = None,
    source_row_id: str | None = None,
    clean_table: str | None = None,
    clean_record_key: str | None = None,
    sku_code: str | None = None,
    issue_payload_json: Mapping[str, Any] | None = None,
    suggested_downstream_action: str | None = None,
    review_required: bool = False,
) -> dict[str, Any]:
    return {
        **dict(common),
        "domain": domain,
        "source_table": source_table,
        "source_row_id": source_row_id,
        "clean_table": clean_table,
        "clean_record_key": clean_record_key,
        "sku_code": sku_code,
        "issue_type": issue_type,
        "severity": severity,
        "issue_detail": issue_detail,
        "issue_payload_json": dict(issue_payload_json or {}),
        "suggested_downstream_action": suggested_downstream_action,
        "review_required": review_required,
        "review_status": (
            Core3ReviewStatus.REVIEW_REQUIRED.value
            if review_required
            else Core3ReviewStatus.AUTO_PASS.value
        ),
    }


def _severity_for_issue_type(issue_type: str) -> str:
    if issue_type in {
        Core3QualityIssueType.INVALID_NUMBER.value,
        Core3QualityIssueType.NEGATIVE_NUMBER.value,
        Core3QualityIssueType.PRICE_CHECK_MISMATCH.value,
        Core3QualityIssueType.CROSS_TABLE_CONFLICT.value,
        Core3QualityIssueType.CLAIM_COVERAGE_MISSING.value,
    }:
        return "warning"
    return "info"


def _review_required_for_issue_type(issue_type: str) -> bool:
    return issue_type in {
        Core3QualityIssueType.CLAIM_COVERAGE_MISSING.value,
        Core3QualityIssueType.CROSS_TABLE_CONFLICT.value,
        Core3QualityIssueType.SCHEMA_CHANGED.value,
        Core3QualityIssueType.CLEAN_HASH_CHANGED_HIGH.value,
    }


def _issue_detail(issue_type: str, payload: Mapping[str, Any]) -> str:
    sku_code = payload.get("sku_code") or "未知 SKU"
    details = {
        Core3QualityIssueType.INVALID_NUMBER.value: f"{sku_code} 存在无法解析的数值字段",
        Core3QualityIssueType.NEGATIVE_NUMBER.value: f"{sku_code} 存在负数型量价字段",
        Core3QualityIssueType.PRICE_CHECK_MISMATCH.value: f"{sku_code} 均价与销额/销量校验不一致",
        Core3QualityIssueType.UNKNOWN_VALUE.value: f"{sku_code} 存在空值、unknown 或横杠等未知值",
        Core3QualityIssueType.CLAIM_SEQ_PARSE_FAILED.value: f"{sku_code} 卖点序号无法解析",
        Core3QualityIssueType.LOW_VALUE_COMMENT.value: f"{sku_code} 存在默认评价或空评价",
        Core3QualityIssueType.COMMENT_DIMENSION_MISSING.value: f"{sku_code} 评论原始维度缺失",
    }
    return details.get(issue_type, f"{sku_code} 存在 {issue_type} 数据质量问题")


def _issue_payload(issue_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    if issue_type == Core3QualityIssueType.PRICE_CHECK_MISMATCH.value:
        return {
            "avg_price": str(payload.get("avg_price")),
            "avg_price_expected": str(payload.get("avg_price_expected")),
            "price_check_delta": str(payload.get("price_check_delta")),
        }
    if issue_type == Core3QualityIssueType.UNKNOWN_VALUE.value:
        return {
            "value_presence": payload.get("value_presence") or payload.get("comment_text_presence"),
            "raw_attr_name": payload.get("raw_attr_name"),
            "raw_attr_value": payload.get("raw_attr_value"),
        }
    if issue_type == Core3QualityIssueType.CLAIM_SEQ_PARSE_FAILED.value:
        return {"claim_seq_raw": payload.get("claim_seq_raw")}
    if issue_type == Core3QualityIssueType.LOW_VALUE_COMMENT.value:
        return {
            "comment_id": payload.get("comment_id"),
            "low_value_reason": payload.get("low_value_reason"),
        }
    if issue_type == Core3QualityIssueType.COMMENT_DIMENSION_MISSING.value:
        return {"comment_id": payload.get("comment_id"), "dimension_path_raw": payload.get("dimension_path_raw")}
    return {"quality_flags": payload.get("quality_flags") or []}


def _suggested_downstream_action(issue_type: str) -> str | None:
    actions = {
        Core3QualityIssueType.INVALID_NUMBER.value: "M07 市场画像使用该行时降低量价置信度",
        Core3QualityIssueType.NEGATIVE_NUMBER.value: "M07 市场画像需排除或复核该量价行",
        Core3QualityIssueType.PRICE_CHECK_MISMATCH.value: "M07 市场画像保留原值并标记价格校验异常",
        Core3QualityIssueType.UNKNOWN_VALUE.value: "下游必须按 unknown 处理，不能解释为 false",
        Core3QualityIssueType.CLAIM_SEQ_PARSE_FAILED.value: "M04a 可使用文本，但不得依赖卖点序号",
        Core3QualityIssueType.LOW_VALUE_COMMENT.value: "M02 以后不进入评论语义分析链路，仅进入数据质量统计",
        Core3QualityIssueType.COMMENT_DIMENSION_MISSING.value: "M05/M06 不得把缺失维度解释为无对应主题",
    }
    return actions.get(issue_type)


def _dedupe_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    deduped: list[dict[str, Any]] = []
    for issue in issues:
        key = (
            issue.get("batch_id"),
            issue.get("domain"),
            issue.get("issue_type"),
            issue.get("source_row_id"),
            issue.get("clean_record_key"),
            issue.get("sku_code"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)
    return deduped


def _attribute_conflict_group(row: Mapping[str, Any]) -> str | None:
    sku_code = _clean_text(_field(row, "model_code"))
    attr_name = _clean_text(_field(row, "attr_name"))
    if not sku_code or not attr_name:
        return None
    return f"{sku_code}:{attr_name}"


def _claim_title_hint(clean_claim_text: str | None) -> str | None:
    if not clean_claim_text:
        return None
    for separator in ("：", ":"):
        if separator in clean_claim_text:
            return clean_claim_text.split(separator, 1)[0].strip() or None
    return None


def _claim_structure_hints(clean_claim_text: str | None) -> dict[str, Any]:
    if not clean_claim_text:
        return {}
    return {
        "has_colon_title": "：" in clean_claim_text or ":" in clean_claim_text,
        "has_parentheses": any(token in clean_claim_text for token in ("(", ")", "（", "）")),
        "sentence_count": len(SentenceSplitter.split(clean_claim_text)),
    }


def _clean_sentiment(value: Any) -> str:
    normalized = _clean_text(value)
    if not normalized:
        return "unknown"
    mapping = {
        "正面": "positive",
        "好评": "positive",
        "positive": "positive",
        "负面": "negative",
        "差评": "negative",
        "negative": "negative",
        "中性": "neutral",
        "neutral": "neutral",
    }
    return mapping.get(normalized.casefold(), normalized)


def _sentence_payload(
    context: CleaningSourceContext,
    domain: str,
    parent_payload: Mapping[str, Any],
    sentence: str,
    *,
    sentence_seq: int,
    extra: Mapping[str, Any],
) -> dict[str, Any]:
    sentence_source = extra.get("sentence_source")
    key_parts = [context.source_row_id]
    if sentence_source:
        key_parts.append(sentence_source)
    key_parts.append(sentence_seq)
    payload = {
        "project_id": context.project_id,
        "category_code": _enum_value(context.category_code),
        "batch_id": context.batch_id,
        "source_row_id": context.source_row_id,
        "sku_code": parent_payload.get("sku_code"),
        "sentence_seq": sentence_seq,
        "sentence_text": sentence,
        "sentence_text_hash": stable_hash(sentence, version=CORE3_M01_CLEAN_HASH_VERSION),
        "split_rule": "punctuation",
        "clean_record_key": CleanHashService.clean_record_key(domain, *key_parts),
        "clean_version": context.clean_version,
        "hash_version": context.hash_version,
        "quality_status": Core3CleanQualityStatus.OK.value,
        "quality_flags": [],
        **dict(extra),
    }
    payload["clean_hash"] = CleanHashService.clean_hash(domain, payload)
    return payload
