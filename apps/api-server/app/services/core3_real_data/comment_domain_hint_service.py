"""M05 weak domain hint service.

The service enriches M05 sentence atoms with weak business domains. It only
updates domain hints on existing sentence atoms and intentionally stops before
sentiment correction, topic hints, quality profiles, tasks, battlefields,
competitors, and reports.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence

from app.services.core3_real_data.comment_evidence_schemas import CommentEvidenceAtomRecord, DomainHint
from app.services.core3_real_data.constants import CommentDomainHint
from app.services.core3_real_data.hash_utils import stable_hash


COMMENT_DOMAIN_HINT_RESULT_HASH_VERSION = "m05_comment_domain_hint_result_v1"

DOMAIN_NAME_CN = {
    CommentDomainHint.PRODUCT_EXPERIENCE.value: "产品体验",
    CommentDomainHint.PRODUCT_RISK.value: "产品风险",
    CommentDomainHint.MARKET_PERCEPTION.value: "价格价值感",
    CommentDomainHint.SERVICE_EXPERIENCE.value: "服务体验",
    CommentDomainHint.LOGISTICS_INSTALLATION.value: "物流安装",
    CommentDomainHint.UNKNOWN.value: "未知",
}

DOMAIN_TEXT_TERMS = {
    CommentDomainHint.PRODUCT_EXPERIENCE.value: frozenset(
        {
            "画质",
            "画面",
            "清晰",
            "色彩",
            "亮度",
            "hdr",
            "暗场",
            "对比",
            "音质",
            "音效",
            "游戏",
            "高刷",
            "刷新",
            "刷新率",
            "延迟",
            "流畅",
            "接口",
            "hdmi",
            "护眼",
            "尺寸",
            "客厅",
            "卧室",
            "看球",
            "球赛",
            "体育",
            "主机",
        }
    ),
    CommentDomainHint.PRODUCT_RISK.value: frozenset(
        {
            "卡顿",
            "卡",
            "广告",
            "故障",
            "坏",
            "漏光",
            "刺眼",
            "复杂",
            "闪退",
            "死机",
            "花屏",
            "开机慢",
            "发热",
            "拖影",
        }
    ),
    CommentDomainHint.MARKET_PERCEPTION.value: frozenset(
        {"价格", "性价比", "划算", "优惠", "贵", "便宜", "不值", "券", "补贴", "活动"}
    ),
    CommentDomainHint.SERVICE_EXPERIENCE.value: frozenset({"客服", "售后", "服务", "师傅", "态度", "维修"}),
    CommentDomainHint.LOGISTICS_INSTALLATION.value: frozenset(
        {"物流", "配送", "送货", "上门", "挂装", "安装", "预约", "送装"}
    ),
}

DOMAIN_DIMENSION_TERMS = {
    CommentDomainHint.PRODUCT_EXPERIENCE.value: frozenset(
        {"产品体验", "产品质量", "显示画质", "音频效果", "产品设计", "游戏流畅", "画面流畅", "接口连接"}
    ),
    CommentDomainHint.PRODUCT_RISK.value: frozenset({"产品风险", "系统体验", "负面评价", "质量问题", "故障问题"}),
    CommentDomainHint.MARKET_PERCEPTION.value: frozenset({"产品价格", "价格", "性价比", "促销优惠"}),
    CommentDomainHint.SERVICE_EXPERIENCE.value: frozenset({"服务体验", "安装服务", "售后服务", "送装维保"}),
    CommentDomainHint.LOGISTICS_INSTALLATION.value: frozenset({"物流安装", "物流配送", "送货安装", "安装整体服务", "送装维保"}),
}

SERVICE_DOMAINS = {
    CommentDomainHint.SERVICE_EXPERIENCE.value,
    CommentDomainHint.LOGISTICS_INSTALLATION.value,
}
PRODUCT_DOMAINS = {
    CommentDomainHint.PRODUCT_EXPERIENCE.value,
    CommentDomainHint.PRODUCT_RISK.value,
    CommentDomainHint.MARKET_PERCEPTION.value,
}


@dataclass(frozen=True)
class CommentDomainHintIssue:
    issue_code: str
    message_cn: str
    comment_evidence_id: str | None = None
    review_required: bool = True
    blocked: bool = False


@dataclass(frozen=True)
class CommentDomainHintResult:
    records: list[CommentEvidenceAtomRecord]
    issues: list[CommentDomainHintIssue] = field(default_factory=list)
    unknown_count: int = 0
    domain_conflict_count: int = 0
    service_only_count: int = 0


@dataclass(frozen=True)
class _DomainScore:
    domain: str
    text_terms: list[str]
    dimension_paths: list[str]
    confidence: Decimal
    text_score: Decimal
    dimension_score: Decimal


class CommentDomainHintService:
    def apply_domain_hints(self, atoms: Sequence[CommentEvidenceAtomRecord]) -> CommentDomainHintResult:
        records: list[CommentEvidenceAtomRecord] = []
        for atom in atoms:
            domain_scores = self._score_domains(atom)
            domain_hints = self._build_domain_hints(atom, domain_scores)
            primary_domain = self._primary_domain(atom, domain_scores)
            domain_conflict_flag = self._domain_conflict(atom, domain_scores, primary_domain)
            records.append(
                atom.model_copy(
                    update={
                        "domain_hints": domain_hints,
                        "primary_domain_hint": primary_domain,
                        "domain_conflict_flag": domain_conflict_flag,
                        "result_hash": self._result_hash(atom, domain_hints, primary_domain, domain_conflict_flag),
                    }
                )
            )

        return CommentDomainHintResult(
            records=records,
            unknown_count=sum(1 for record in records if record.primary_domain_hint == CommentDomainHint.UNKNOWN.value),
            domain_conflict_count=sum(1 for record in records if record.domain_conflict_flag),
            service_only_count=sum(
                1
                for record in records
                if record.primary_domain_hint in {CommentDomainHint.SERVICE_EXPERIENCE.value, CommentDomainHint.LOGISTICS_INSTALLATION.value}
            ),
        )

    def _score_domains(self, atom: CommentEvidenceAtomRecord) -> list[_DomainScore]:
        compact_text = _compact_text(atom.normalized_sentence_text or atom.sentence_text)
        scores: list[_DomainScore] = []
        for domain in [
            CommentDomainHint.PRODUCT_EXPERIENCE.value,
            CommentDomainHint.PRODUCT_RISK.value,
            CommentDomainHint.MARKET_PERCEPTION.value,
            CommentDomainHint.SERVICE_EXPERIENCE.value,
            CommentDomainHint.LOGISTICS_INSTALLATION.value,
        ]:
            text_terms = _matched_terms(compact_text, DOMAIN_TEXT_TERMS[domain])
            dimension_paths = _matched_dimension_paths(atom.raw_dimension_paths, DOMAIN_DIMENSION_TERMS[domain])
            if not text_terms and not dimension_paths:
                continue
            text_score = min(Decimal("1.0000"), Decimal("0.4500") + Decimal("0.1500") * len(text_terms)) if text_terms else Decimal("0.0000")
            dimension_score = min(Decimal("1.0000"), Decimal("0.5000") + Decimal("0.1000") * len(dimension_paths)) if dimension_paths else Decimal("0.0000")
            confidence = _quantize_confidence(
                min(
                    Decimal("1.0000"),
                    Decimal("0.70") * text_score
                    + Decimal("0.25") * dimension_score
                    + Decimal("0.05") * atom.specificity_score,
                )
            )
            scores.append(
                _DomainScore(
                    domain=domain,
                    text_terms=text_terms,
                    dimension_paths=dimension_paths,
                    confidence=confidence,
                    text_score=text_score,
                    dimension_score=dimension_score,
                )
            )
        return sorted(scores, key=lambda score: (-score.confidence, _domain_sort_rank(score.domain)))

    def _build_domain_hints(
        self,
        atom: CommentEvidenceAtomRecord,
        domain_scores: Sequence[_DomainScore],
    ) -> list[DomainHint]:
        if not domain_scores:
            return [
                DomainHint(
                    domain_hint=CommentDomainHint.UNKNOWN,
                    source_terms=[],
                    source_dimension_paths=[],
                    confidence=Decimal("0.0000"),
                    evidence_ids=list(atom.source_evidence_ids),
                )
            ]
        return [
            DomainHint(
                domain_hint=score.domain,
                source_terms=score.text_terms,
                source_dimension_paths=score.dimension_paths,
                confidence=score.confidence,
                evidence_ids=list(atom.source_evidence_ids),
            )
            for score in domain_scores
        ]

    def _primary_domain(self, atom: CommentEvidenceAtomRecord, domain_scores: Sequence[_DomainScore]) -> CommentDomainHint:
        if not domain_scores:
            return CommentDomainHint.UNKNOWN

        text_domains = [score for score in domain_scores if score.text_score > 0]
        if text_domains:
            service_text_domains = [score for score in text_domains if score.domain in SERVICE_DOMAINS]
            product_text_domains = [score for score in text_domains if score.domain in PRODUCT_DOMAINS]
            if service_text_domains and not product_text_domains:
                return CommentDomainHint(service_text_domains[0].domain)
            if product_text_domains:
                return CommentDomainHint(product_text_domains[0].domain)

        return CommentDomainHint(domain_scores[0].domain)

    def _domain_conflict(
        self,
        atom: CommentEvidenceAtomRecord,
        domain_scores: Sequence[_DomainScore],
        primary_domain: CommentDomainHint,
    ) -> bool:
        text_domains = {score.domain for score in domain_scores if score.text_score > 0}
        dimension_domains = {score.domain for score in domain_scores if score.dimension_score > 0}
        if not text_domains or not dimension_domains:
            return False
        primary = primary_domain.value
        if primary in text_domains and primary in dimension_domains:
            return False
        has_product_text = bool(text_domains.intersection(PRODUCT_DOMAINS))
        has_service_text = bool(text_domains.intersection(SERVICE_DOMAINS))
        has_product_dimension = bool(dimension_domains.intersection(PRODUCT_DOMAINS))
        has_service_dimension = bool(dimension_domains.intersection(SERVICE_DOMAINS))
        return (has_product_text and has_service_dimension) or (has_service_text and has_product_dimension)

    def _result_hash(
        self,
        atom: CommentEvidenceAtomRecord,
        domain_hints: Sequence[DomainHint],
        primary_domain: CommentDomainHint,
        domain_conflict_flag: bool,
    ) -> str:
        return stable_hash(
            {
                "comment_evidence_id": atom.comment_evidence_id,
                "sentence_hash": atom.sentence_hash,
                "previous_result_hash": atom.result_hash,
                "domain_hints": [hint.model_dump() for hint in domain_hints],
                "primary_domain_hint": primary_domain.value,
                "domain_conflict_flag": domain_conflict_flag,
                "rule_version": atom.rule_version,
                "asset_version": atom.asset_version,
            },
            version=COMMENT_DOMAIN_HINT_RESULT_HASH_VERSION,
        )


def _matched_terms(compact_text: str, terms: frozenset[str]) -> list[str]:
    lower_text = compact_text.lower()
    return sorted({term for term in terms if term.lower() in lower_text}, key=lambda value: (len(value), value))


def _matched_dimension_paths(paths: Sequence[str], terms: frozenset[str]) -> list[str]:
    matched: list[str] = []
    for path in paths:
        compact_path = _compact_text(path)
        if any(_compact_text(term) in compact_path for term in terms):
            matched.append(path)
    return sorted(set(matched))


def _compact_text(value: str | None) -> str:
    return "".join(re.findall(r"[\w\u4e00-\u9fff]+", (value or "").lower()))


def _domain_sort_rank(domain: str) -> int:
    order = [
        CommentDomainHint.PRODUCT_EXPERIENCE.value,
        CommentDomainHint.PRODUCT_RISK.value,
        CommentDomainHint.MARKET_PERCEPTION.value,
        CommentDomainHint.SERVICE_EXPERIENCE.value,
        CommentDomainHint.LOGISTICS_INSTALLATION.value,
        CommentDomainHint.UNKNOWN.value,
    ]
    return order.index(domain)


def _quantize_confidence(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
