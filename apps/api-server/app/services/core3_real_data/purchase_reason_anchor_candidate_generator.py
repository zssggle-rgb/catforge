"""Candidate generation against the versioned M12D standard anchor taxonomy."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Literal, Mapping, Sequence

from app.services.core3_real_data.constants import M12DAnchorRole
from app.services.core3_real_data.purchase_reason_profile_schemas import (
    M12DAnchorCandidate,
    M12DAnchorCandidateSet,
    M12DAnchorEvidenceMatch,
    M12DAnchorEvidencePattern,
    M12DAnchorTaxonomy,
    M12DInputSnapshot,
    M12DSourceRef,
    M12DSkuPurchaseReasonContext,
)


class M12DAnchorCandidateGenerationError(ValueError):
    pass


class AnchorCandidateGenerator:
    def __init__(self, taxonomy: M12DAnchorTaxonomy) -> None:
        self.taxonomy = taxonomy

    def generate(self, context: M12DSkuPurchaseReasonContext) -> M12DAnchorCandidateSet:
        if context.product_category.upper() != self.taxonomy.product_category.upper():
            raise M12DAnchorCandidateGenerationError(
                f"taxonomy {self.taxonomy.taxonomy_version} is for {self.taxonomy.product_category}, "
                f"not {context.product_category}"
            )

        snapshots = _snapshots_by_module(context)
        value_theme_candidates: list[M12DAnchorCandidate] = []
        for theme in self.taxonomy.value_themes:
            matches = _dedupe_matches(
                match
                for pattern in theme.evidence_patterns
                for match in _matches_pattern(pattern, snapshots)
            )
            if not matches:
                continue
            value_theme_candidates.append(
                _build_candidate(
                    taxonomy=self.taxonomy,
                    context=context,
                    candidate_type="value_theme",
                    anchor_code=theme.value_theme_code,
                    anchor_cn=theme.value_theme_cn,
                    anchor_family_code=theme.value_theme_family_code,
                    anchor_family_cn=theme.value_theme_family_cn,
                    candidate_rank=theme.candidate_rank,
                    matches=matches,
                )
            )

        purchase_reason_candidates: list[M12DAnchorCandidate] = []
        for reason in self.taxonomy.purchase_reasons:
            matches = _dedupe_matches(
                match
                for pattern in reason.evidence_patterns
                for match in _matches_pattern(pattern, snapshots)
            )
            if not matches or not _passes_candidate_gate(matches, reason.candidate_gate_domain_groups):
                continue
            purchase_reason_candidates.append(
                _build_candidate(
                    taxonomy=self.taxonomy,
                    context=context,
                    candidate_type="purchase_reason",
                    anchor_code=reason.purchase_reason_code,
                    anchor_cn=reason.purchase_reason_cn,
                    anchor_family_code=reason.purchase_reason_family_code,
                    anchor_family_cn=reason.purchase_reason_family_cn,
                    candidate_rank=reason.candidate_rank,
                    matches=matches,
                    related_value_theme_codes=reason.related_value_theme_codes,
                    required_logic_cn=reason.required_logic_cn,
                    weak_boundary_cn=reason.weak_boundary_cn,
                    decision_question_cn=reason.decision_question_cn,
                )
            )
        return M12DAnchorCandidateSet(
            taxonomy_version=self.taxonomy.taxonomy_version,
            product_category=self.taxonomy.product_category,
            sku_code=context.sku_code,
            value_theme_candidates=sorted(
                value_theme_candidates,
                key=lambda item: (item.candidate_rank, item.anchor_code),
            ),
            purchase_reason_candidates=sorted(
                purchase_reason_candidates,
                key=lambda item: (item.candidate_rank, item.anchor_code),
            ),
        )


def _build_candidate(
    *,
    taxonomy: M12DAnchorTaxonomy,
    context: M12DSkuPurchaseReasonContext,
    candidate_type: Literal["value_theme", "purchase_reason"],
    anchor_code: str,
    anchor_cn: str,
    anchor_family_code: str,
    anchor_family_cn: str,
    candidate_rank: int,
    matches: list[M12DAnchorEvidenceMatch],
    related_value_theme_codes: list[str] | None = None,
    required_logic_cn: str | None = None,
    weak_boundary_cn: str | None = None,
    decision_question_cn: str | None = None,
) -> M12DAnchorCandidate:
    role_cap = None
    role_cap_reasons: list[str] = []
    if all(match.weak_expression_only for match in matches):
        role_cap = M12DAnchorRole.WEAK_EXPRESSION
        role_cap_reasons.append("only_weak_expression_sources")
    evidence_domains = _dedupe_strings(str(match.evidence_domain) for match in matches)
    source_refs = _dedupe_source_refs(
        source_ref
        for match in matches
        for source_ref in match.source_refs_json
    )
    candidate_payload = {
        "taxonomy_version": taxonomy.taxonomy_version,
        "product_category": taxonomy.product_category,
        "sku_code": context.sku_code,
        "candidate_type": candidate_type,
        "anchor_code": anchor_code,
        "evidence": [
            {
                "module_code": match.module_code,
                "domain": str(match.evidence_domain),
                "match_source": match.match_source,
                "match_key": match.match_key,
                "match_value": match.match_value,
                "weak_expression_only": match.weak_expression_only,
            }
            for match in matches
        ],
        "context_input_fingerprint": context.input_fingerprint,
    }
    return M12DAnchorCandidate(
        taxonomy_version=taxonomy.taxonomy_version,
        product_category=taxonomy.product_category,
        sku_code=context.sku_code,
        candidate_type=candidate_type,
        anchor_code=anchor_code,
        anchor_cn=anchor_cn,
        anchor_family_code=anchor_family_code,
        anchor_family_cn=anchor_family_cn,
        related_value_theme_codes=related_value_theme_codes or [],
        required_logic_cn=required_logic_cn,
        weak_boundary_cn=weak_boundary_cn,
        decision_question_cn=decision_question_cn,
        candidate_rank=candidate_rank,
        evidence_matches=matches,
        evidence_domains_json=evidence_domains,
        role_cap=role_cap,
        role_cap_reasons=role_cap_reasons,
        support_summary_cn=_support_summary(anchor_cn, matches),
        source_refs_json=source_refs,
        input_fingerprint=_fingerprint(candidate_payload),
    )


def _passes_candidate_gate(
    matches: Sequence[M12DAnchorEvidenceMatch],
    domain_groups: Sequence[Sequence[str]],
) -> bool:
    if not domain_groups:
        return True
    matched_domains = {str(match.evidence_domain) for match in matches}
    return all(
        any(str(domain) in matched_domains for domain in domain_group)
        for domain_group in domain_groups
    )


def _snapshots_by_module(context: M12DSkuPurchaseReasonContext) -> dict[str, M12DInputSnapshot]:
    return {
        "M03B": context.param_profile,
        "M04C": context.claim_fact_profile,
        "M05C": context.comment_profile,
        "M07": context.market_profile,
        "M09C_M10C_M11C": context.semantic_profile,
        "M11D": context.semantic_market_profile,
        "M12C": context.claim_value_profile,
    }


def _matches_pattern(
    pattern: M12DAnchorEvidencePattern,
    snapshots: Mapping[str, M12DInputSnapshot],
) -> list[M12DAnchorEvidenceMatch]:
    snapshot = snapshots.get(pattern.module_code)
    if snapshot is None or snapshot.record_count <= 0:
        return []
    payload = _selected_payload(snapshot.summary, pattern.summary_keys)
    flattened = list(_flatten_payload(payload))
    normalized_tokens = {_normalize(token) for _, token in flattened if token is not None}
    normalized_blob = " ".join(normalized_tokens)
    matches: list[M12DAnchorEvidenceMatch] = []
    for code in pattern.exact_codes:
        normalized_code = _normalize(code)
        if normalized_code in normalized_tokens or normalized_code in normalized_blob:
            matches.append(
                _match(
                    pattern,
                    snapshot,
                    match_source="exact_code",
                    match_key=code,
                    match_value=code,
                )
            )
    for term in pattern.terms:
        normalized_term = _normalize(term)
        if normalized_term and normalized_term in normalized_blob:
            matches.append(
                _match(
                    pattern,
                    snapshot,
                    match_source="term",
                    match_key=term,
                    match_value=term,
                )
            )
    return _dedupe_matches(matches)


def _match(
    pattern: M12DAnchorEvidencePattern,
    snapshot: M12DInputSnapshot,
    *,
    match_source: str,
    match_key: str,
    match_value: str,
) -> M12DAnchorEvidenceMatch:
    return M12DAnchorEvidenceMatch(
        module_code=pattern.module_code,
        evidence_domain=pattern.evidence_domain,
        match_source=match_source,
        match_key=match_key,
        match_value=match_value,
        support_label_cn=pattern.support_label_cn,
        weak_expression_only=pattern.weak_expression_only,
        source_refs_json=snapshot.source_refs,
    )


def _selected_payload(payload: Mapping[str, Any], summary_keys: Sequence[str]) -> dict[str, Any]:
    if not summary_keys:
        return dict(payload)
    result: dict[str, Any] = {}
    for key in summary_keys:
        if key in payload:
            result[key] = payload[key]
    return result


def _flatten_payload(payload: Any, *, prefix: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_str = str(key)
            path = f"{prefix}.{key_str}" if prefix else key_str
            yield path, key_str
            yield from _flatten_payload(value, prefix=path)
        return
    if isinstance(payload, list):
        for index, value in enumerate(payload):
            yield from _flatten_payload(value, prefix=f"{prefix}[{index}]")
        return
    if isinstance(payload, tuple):
        for index, value in enumerate(payload):
            yield from _flatten_payload(value, prefix=f"{prefix}[{index}]")
        return
    if payload is not None:
        yield prefix, str(payload)


def _dedupe_matches(matches: Iterable[M12DAnchorEvidenceMatch]) -> list[M12DAnchorEvidenceMatch]:
    result: list[M12DAnchorEvidenceMatch] = []
    seen: set[tuple[str, str, str, str, bool]] = set()
    for match in matches:
        key = (
            match.module_code,
            str(match.evidence_domain),
            match.match_source,
            _normalize(match.match_key),
            match.weak_expression_only,
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(match)
    return result


def _dedupe_source_refs(source_refs: Iterable[M12DSourceRef]) -> list[M12DSourceRef]:
    result: list[M12DSourceRef] = []
    seen: set[tuple[str, str, str]] = set()
    for source_ref in source_refs:
        key = (source_ref.module_code, source_ref.table_name, source_ref.record_id)
        if key in seen:
            continue
        seen.add(key)
        result.append(source_ref)
    return result


def _dedupe_strings(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _support_summary(anchor_cn: str, matches: Sequence[M12DAnchorEvidenceMatch]) -> str:
    labels = _dedupe_strings(match.support_label_cn for match in matches)
    return f"{anchor_cn}候选命中：" + "；".join(labels) + "。"


def _normalize(value: str) -> str:
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _jsonable_mapping(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _jsonable_value(value) for key, value in payload.items()}


def _jsonable_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return _jsonable_mapping(value)
    if isinstance(value, list):
        return [_jsonable_value(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable_value(item) for item in value]
    return value


def _fingerprint(payload: Mapping[str, Any]) -> str:
    normalized = json.dumps(_jsonable_mapping(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
