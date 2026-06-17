"""M02 evidence link builder."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from app.services.core3_real_data.constants import Core3EvidenceLinkType, Core3EvidenceType


COMMENT_EVIDENCE_TYPES = {
    Core3EvidenceType.COMMENT_RAW.value,
    Core3EvidenceType.COMMENT_SENTENCE.value,
    Core3EvidenceType.COMMENT_DIMENSION.value,
}
MAX_EXHAUSTIVE_SAME_COMMENT_GROUP_SIZE = 50
MAX_EXHAUSTIVE_TEXT_DUPLICATE_GROUP_SIZE = 50
DOMAIN_EVIDENCE_TYPES = {
    "sku": {Core3EvidenceType.SKU_FACT.value},
    "market": {Core3EvidenceType.MARKET_FACT.value},
    "param": {Core3EvidenceType.PARAM_RAW.value},
    "claim": {Core3EvidenceType.PROMO_RAW.value, Core3EvidenceType.PROMO_SENTENCE.value},
    "comment": COMMENT_EVIDENCE_TYPES,
}


@dataclass(frozen=True)
class EvidenceLinkDraft:
    project_id: str
    category_code: str
    batch_id: str
    from_evidence_id: str
    to_evidence_id: str
    from_evidence_key: str
    to_evidence_key: str
    link_type: Core3EvidenceLinkType
    link_payload_json: dict[str, Any]
    confidence: Decimal

    def to_payload(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "category_code": self.category_code,
            "batch_id": self.batch_id,
            "from_evidence_id": self.from_evidence_id,
            "to_evidence_id": self.to_evidence_id,
            "from_evidence_key": self.from_evidence_key,
            "to_evidence_key": self.to_evidence_key,
            "link_type": self.link_type.value,
            "link_payload_json": self.link_payload_json,
            "confidence": self.confidence,
        }


class EvidenceLinkBuilder:
    def build_links(
        self,
        evidence_atoms: Sequence[Mapping[str, Any] | Any],
        *,
        superseded_pairs: Sequence[tuple[Mapping[str, Any] | Any, Mapping[str, Any] | Any]] | None = None,
    ) -> list[EvidenceLinkDraft]:
        atoms = [_atom_payload(atom) for atom in evidence_atoms]
        drafts = [
            *self.build_sentence_links(atoms),
            *self.build_dimension_links(atoms),
            *self.build_same_comment_links(atoms),
            *self.build_same_text_links(atoms),
            *self.build_quality_issue_links(atoms),
        ]
        for new_atom, old_atom in superseded_pairs or ():
            drafts.append(self.build_supersedes_link(new_atom, old_atom))
        return _dedupe_links(drafts)

    def build_sentence_links(self, evidence_atoms: Sequence[Mapping[str, Any] | Any]) -> list[EvidenceLinkDraft]:
        atoms = [_atom_payload(atom) for atom in evidence_atoms]
        links: list[EvidenceLinkDraft] = []
        for parent_type, child_type in [
            (Core3EvidenceType.COMMENT_RAW.value, Core3EvidenceType.COMMENT_SENTENCE.value),
            (Core3EvidenceType.PROMO_RAW.value, Core3EvidenceType.PROMO_SENTENCE.value),
        ]:
            parents = [atom for atom in atoms if atom.get("evidence_type") == parent_type and atom.get("source_row_id")]
            children = [atom for atom in atoms if atom.get("evidence_type") == child_type and atom.get("source_row_id")]
            children_by_source = _group_by(children, "source_row_id")
            for parent in parents:
                for child in children_by_source.get(str(parent["source_row_id"]), []):
                    links.append(
                        self._make_link(
                            parent,
                            child,
                            Core3EvidenceLinkType.HAS_SENTENCE,
                            Decimal("1.0000"),
                            {
                                "match_rule": "same_source_row",
                                "source_row_id": parent.get("source_row_id"),
                                "parent_type": parent_type,
                                "child_type": child_type,
                            },
                        )
                    )
        return links

    def build_dimension_links(self, evidence_atoms: Sequence[Mapping[str, Any] | Any]) -> list[EvidenceLinkDraft]:
        atoms = [_atom_payload(atom) for atom in evidence_atoms]
        parents = [
            atom
            for atom in atoms
            if atom.get("evidence_type") == Core3EvidenceType.COMMENT_RAW.value and atom.get("source_row_id")
        ]
        dimensions_by_source = _group_by(
            [
                atom
                for atom in atoms
                if atom.get("evidence_type") == Core3EvidenceType.COMMENT_DIMENSION.value and atom.get("source_row_id")
            ],
            "source_row_id",
        )
        links: list[EvidenceLinkDraft] = []
        for parent in parents:
            for dimension in dimensions_by_source.get(str(parent["source_row_id"]), []):
                links.append(
                    self._make_link(
                        parent,
                        dimension,
                        Core3EvidenceLinkType.HAS_DIMENSION,
                        Decimal("0.5500"),
                        {
                            "match_rule": "same_source_row",
                            "source_row_id": parent.get("source_row_id"),
                            "dimension_path_raw": dimension.get("dimension_path_raw"),
                        },
                    )
                )
        return links

    def build_same_comment_links(self, evidence_atoms: Sequence[Mapping[str, Any] | Any]) -> list[EvidenceLinkDraft]:
        atoms = []
        for atom in evidence_atoms:
            payload = _atom_payload(atom)
            if _is_comment_atom(payload) and payload.get("sku_code") and payload.get("comment_id"):
                atoms.append(payload)
        groups: dict[str, list[dict[str, Any]]] = {}
        for atom in atoms:
            groups.setdefault(f"{atom['sku_code']}::{atom['comment_id']}", []).append(atom)
        links: list[EvidenceLinkDraft] = []
        for group in groups.values():
            sorted_group = _sorted_group(group)
            exhaustive = len(sorted_group) <= MAX_EXHAUSTIVE_SAME_COMMENT_GROUP_SIZE
            pairs = _pairwise_sorted_group(sorted_group) if exhaustive else _representative_pairs(sorted_group)
            for left, right in pairs:
                payload = {
                    "match_rule": "sku_code_comment_id",
                    "sku_code": left.get("sku_code"),
                    "comment_id": left.get("comment_id"),
                }
                if not exhaustive:
                    payload.update(
                        same_comment_group_size=len(sorted_group),
                        exhaustive_pair_cap=MAX_EXHAUSTIVE_SAME_COMMENT_GROUP_SIZE,
                        link_strategy="representative_same_comment_group",
                    )
                links.append(
                    self._make_link(
                        left,
                        right,
                        Core3EvidenceLinkType.SAME_COMMENT,
                        Decimal("0.8000"),
                        payload,
                    )
                )
        return links

    def build_same_text_links(self, evidence_atoms: Sequence[Mapping[str, Any] | Any]) -> list[EvidenceLinkDraft]:
        atoms = []
        for atom in evidence_atoms:
            payload = _atom_payload(atom)
            if _is_comment_atom(payload):
                atoms.append(payload)
        links: list[EvidenceLinkDraft] = []
        for field_name, link_type in [
            ("comment_text_hash", Core3EvidenceLinkType.SAME_COMMENT_TEXT),
            ("segment_text_hash", Core3EvidenceLinkType.SAME_SEGMENT),
        ]:
            groups = _group_by([atom for atom in atoms if atom.get(field_name)], field_name)
            for hash_value, group in groups.items():
                sorted_group = _sorted_group(group)
                exhaustive = len(sorted_group) <= MAX_EXHAUSTIVE_TEXT_DUPLICATE_GROUP_SIZE
                pairs = (
                    _pairwise_sorted_group(sorted_group)
                    if exhaustive
                    else _representative_pairs(sorted_group)
                )
                for left, right in pairs:
                    payload = {
                        "match_rule": field_name,
                        field_name: hash_value,
                    }
                    if not exhaustive:
                        payload.update(
                            duplicate_group_size=len(sorted_group),
                            exhaustive_pair_cap=MAX_EXHAUSTIVE_TEXT_DUPLICATE_GROUP_SIZE,
                            link_strategy="representative_duplicate_group",
                        )
                    links.append(
                        self._make_link(
                            left,
                            right,
                            link_type,
                            Decimal("0.7000"),
                            payload,
                        )
                    )
        return links

    def build_quality_issue_links(self, evidence_atoms: Sequence[Mapping[str, Any] | Any]) -> list[EvidenceLinkDraft]:
        atoms = [_atom_payload(atom) for atom in evidence_atoms]
        quality_atoms = [atom for atom in atoms if atom.get("evidence_type") == Core3EvidenceType.QUALITY_ISSUE.value]
        fact_atoms = [atom for atom in atoms if atom.get("evidence_type") != Core3EvidenceType.QUALITY_ISSUE.value]
        facts_by_clean_key = _group_by(fact_atoms, "clean_record_key")
        facts_by_source_row = _group_by(fact_atoms, "source_row_id")
        facts_by_sku_domain = _group_facts_by_sku_domain(fact_atoms)
        links: list[EvidenceLinkDraft] = []
        for quality_atom in quality_atoms:
            for fact_atom, match_rule in _quality_issue_candidates(
                quality_atom,
                facts_by_clean_key=facts_by_clean_key,
                facts_by_source_row=facts_by_source_row,
                facts_by_sku_domain=facts_by_sku_domain,
            ):
                links.append(
                    self._make_link(
                        fact_atom,
                        quality_atom,
                        Core3EvidenceLinkType.HAS_QUALITY_ISSUE,
                        Decimal("1.0000"),
                        {
                            "match_rule": match_rule,
                            "issue_type": _payload_value(quality_atom, "issue_type"),
                            "domain": _payload_value(quality_atom, "domain"),
                        },
                    )
                )
        return links

    def build_supersedes_link(
        self,
        new_atom: Mapping[str, Any] | Any,
        old_atom: Mapping[str, Any] | Any,
    ) -> EvidenceLinkDraft:
        new_payload = _atom_payload(new_atom)
        old_payload = _atom_payload(old_atom)
        return self._make_link(
            new_payload,
            old_payload,
            Core3EvidenceLinkType.SUPERSEDES,
            Decimal("1.0000"),
            {
                "match_rule": "same_evidence_key",
                "evidence_key": new_payload.get("evidence_key"),
                "new_clean_hash": new_payload.get("clean_hash"),
                "old_clean_hash": old_payload.get("clean_hash"),
            },
        )

    def _make_link(
        self,
        from_atom: Mapping[str, Any],
        to_atom: Mapping[str, Any],
        link_type: Core3EvidenceLinkType,
        confidence: Decimal,
        payload: Mapping[str, Any],
    ) -> EvidenceLinkDraft:
        if from_atom.get("evidence_id") == to_atom.get("evidence_id"):
            raise ValueError("evidence link cannot point to itself")
        return EvidenceLinkDraft(
            project_id=str(from_atom["project_id"]),
            category_code=str(from_atom.get("category_code") or "TV"),
            batch_id=str(from_atom["batch_id"]),
            from_evidence_id=str(from_atom["evidence_id"]),
            to_evidence_id=str(to_atom["evidence_id"]),
            from_evidence_key=str(from_atom["evidence_key"]),
            to_evidence_key=str(to_atom["evidence_key"]),
            link_type=link_type,
            confidence=confidence,
            link_payload_json=_json_safe_dict(payload),
        )


def _atom_payload(atom: Mapping[str, Any] | Any) -> dict[str, Any]:
    if isinstance(atom, Mapping):
        return dict(atom)
    table = getattr(atom, "__table__", None)
    if table is not None:
        return {column.name: getattr(atom, column.name) for column in table.columns}
    return dict(vars(atom))


def atom_value(atom: Mapping[str, Any] | Any, field_name: str) -> Any:
    if isinstance(atom, Mapping):
        return atom.get(field_name)
    return getattr(atom, field_name, None)


def _group_by(atoms: Iterable[Mapping[str, Any]], field_name: str) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for atom in atoms:
        value = atom.get(field_name)
        if value is None or str(value) == "":
            continue
        groups.setdefault(str(value), []).append(dict(atom))
    return groups


def _pairwise_sorted(group: Sequence[Mapping[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    return _pairwise_sorted_group(_sorted_group(group))


def _sorted_group(group: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (dict(atom) for atom in group),
        key=lambda atom: (str(atom.get("evidence_type")), str(atom.get("evidence_id"))),
    )


def _pairwise_sorted_group(sorted_group: Sequence[Mapping[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for left_index, left in enumerate(sorted_group):
        for right in sorted_group[left_index + 1 :]:
            pairs.append((dict(left), dict(right)))
    return pairs


def _representative_pairs(sorted_group: Sequence[Mapping[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    if len(sorted_group) < 2:
        return []
    representative = dict(sorted_group[0])
    return [(representative, dict(atom)) for atom in sorted_group[1:]]


def _group_facts_by_sku_domain(fact_atoms: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for atom in fact_atoms:
        sku_code = atom.get("sku_code")
        if not sku_code:
            continue
        evidence_type = atom.get("evidence_type")
        for domain, evidence_types in DOMAIN_EVIDENCE_TYPES.items():
            if evidence_type in evidence_types:
                groups.setdefault((str(sku_code), domain), []).append(dict(atom))
    return groups


def _quality_issue_candidates(
    quality_atom: Mapping[str, Any],
    *,
    facts_by_clean_key: Mapping[str, Sequence[Mapping[str, Any]]],
    facts_by_source_row: Mapping[str, Sequence[Mapping[str, Any]]],
    facts_by_sku_domain: Mapping[tuple[str, str], Sequence[Mapping[str, Any]]],
) -> list[tuple[dict[str, Any], str]]:
    candidates: dict[str, tuple[dict[str, Any], str]] = {}

    def add(facts: Sequence[Mapping[str, Any]], match_rule: str) -> None:
        for fact in facts:
            evidence_id = fact.get("evidence_id")
            if evidence_id is None:
                continue
            candidates.setdefault(str(evidence_id), (dict(fact), match_rule))

    clean_record_key = quality_atom.get("clean_record_key")
    if clean_record_key:
        add(facts_by_clean_key.get(str(clean_record_key), ()), "clean_record_key")

    target_clean_record_key = _payload_only_value(quality_atom, "clean_record_key")
    if target_clean_record_key:
        add(facts_by_clean_key.get(str(target_clean_record_key), ()), "quality_payload_clean_record_key")

    source_row_id = quality_atom.get("source_row_id")
    if source_row_id:
        add(facts_by_source_row.get(str(source_row_id), ()), "source_row_id")

    domain = _payload_value(quality_atom, "domain")
    sku_code = quality_atom.get("sku_code")
    if domain and sku_code and _is_domain_level_quality_issue(quality_atom):
        add(facts_by_sku_domain.get((str(sku_code), str(domain)), ()), "sku_code_domain")

    return list(candidates.values())


def _dedupe_links(links: Sequence[EvidenceLinkDraft]) -> list[EvidenceLinkDraft]:
    deduped: dict[tuple[str, str, str], EvidenceLinkDraft] = {}
    for link in links:
        key = (link.from_evidence_id, link.to_evidence_id, link.link_type.value)
        deduped.setdefault(key, link)
    return list(deduped.values())


def _is_comment_atom(atom: Mapping[str, Any]) -> bool:
    return str(atom.get("evidence_type")) in COMMENT_EVIDENCE_TYPES


def _quality_match_rule(fact_atom: Mapping[str, Any], quality_atom: Mapping[str, Any]) -> str | None:
    if fact_atom.get("clean_record_key") and fact_atom.get("clean_record_key") == quality_atom.get("clean_record_key"):
        return "clean_record_key"
    target_clean_record_key = _payload_only_value(quality_atom, "clean_record_key")
    if target_clean_record_key and fact_atom.get("clean_record_key") == target_clean_record_key:
        return "quality_payload_clean_record_key"
    if fact_atom.get("source_row_id") and fact_atom.get("source_row_id") == quality_atom.get("source_row_id"):
        return "source_row_id"
    domain = _payload_value(quality_atom, "domain")
    if (
        domain
        and _is_domain_level_quality_issue(quality_atom)
        and fact_atom.get("sku_code")
        and fact_atom.get("sku_code") == quality_atom.get("sku_code")
        and fact_atom.get("evidence_type") in DOMAIN_EVIDENCE_TYPES.get(str(domain), set())
    ):
        return "sku_code_domain"
    return None


def _is_domain_level_quality_issue(quality_atom: Mapping[str, Any]) -> bool:
    target_clean_record_key = _payload_only_value(quality_atom, "clean_record_key")
    if target_clean_record_key:
        return False
    source_row_id = quality_atom.get("source_row_id")
    return not source_row_id or str(source_row_id).startswith("quality:")


def _payload_value(atom: Mapping[str, Any], field_name: str) -> Any:
    payload = atom.get("evidence_payload_json")
    if isinstance(payload, Mapping) and payload.get(field_name) is not None:
        return payload[field_name]
    return atom.get(field_name)


def _payload_only_value(atom: Mapping[str, Any], field_name: str) -> Any:
    payload = atom.get("evidence_payload_json")
    if isinstance(payload, Mapping):
        return payload.get(field_name)
    return None


def _json_safe_dict(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _json_safe_value(payload[key]) for key in sorted(payload)}


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        return _json_safe_dict(value)
    if isinstance(value, tuple):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    return value
