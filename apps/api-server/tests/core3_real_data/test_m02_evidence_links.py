from decimal import Decimal

from app.services.core3_real_data.constants import Core3EvidenceLinkType, Core3EvidenceType
from app.services.core3_real_data.evidence_links import EvidenceLinkBuilder


PROJECT_ID = "core3_mvp"
BATCH_ID = "m00_202606130001"


def atom(
    evidence_id: str,
    evidence_type: Core3EvidenceType,
    *,
    source_row_id: str = "comment_data:1",
    clean_record_key: str | None = "comment:comment_data:1",
    sku_code: str = "TV00029115",
    evidence_payload_json: dict | None = None,
    **overrides,
) -> dict:
    payload = {
        "project_id": PROJECT_ID,
        "category_code": "TV",
        "batch_id": BATCH_ID,
        "evidence_id": evidence_id,
        "evidence_key": f"sha256:m02_evidence_key:{evidence_id}",
        "evidence_type": evidence_type.value,
        "source_row_id": source_row_id,
        "clean_record_key": clean_record_key,
        "clean_hash": f"sha256:m01_clean_hash_v1:{evidence_id}",
        "sku_code": sku_code,
        "evidence_payload_json": evidence_payload_json or {},
    }
    payload.update(overrides)
    return payload


def links_by_type(links):
    grouped = {}
    for link in links:
        grouped.setdefault(link.link_type, []).append(link)
    return grouped


def test_link_builder_creates_sentence_and_dimension_links_from_source_rows():
    builder = EvidenceLinkBuilder()
    comment_raw = atom("comment_raw", Core3EvidenceType.COMMENT_RAW, source_row_id="comment_data:10")
    comment_sentence = atom(
        "comment_sentence",
        Core3EvidenceType.COMMENT_SENTENCE,
        source_row_id="comment_data:10",
        clean_record_key="comment_sentence:comment_data:10:1",
    )
    comment_dimension = atom(
        "comment_dimension",
        Core3EvidenceType.COMMENT_DIMENSION,
        source_row_id="comment_data:10",
        clean_record_key="comment_dimension:comment_data:10",
        dimension_path_raw="使用体验>游戏",
    )
    promo_raw = atom(
        "promo_raw",
        Core3EvidenceType.PROMO_RAW,
        source_row_id="selling_points_data:7",
        clean_record_key="claim:selling_points_data:7",
    )
    promo_sentence = atom(
        "promo_sentence",
        Core3EvidenceType.PROMO_SENTENCE,
        source_row_id="selling_points_data:7",
        clean_record_key="claim_sentence:selling_points_data:7:1",
    )

    grouped = links_by_type(builder.build_links([comment_raw, comment_sentence, comment_dimension, promo_raw, promo_sentence]))

    sentence_links = grouped[Core3EvidenceLinkType.HAS_SENTENCE]
    dimension_links = grouped[Core3EvidenceLinkType.HAS_DIMENSION]

    assert {(link.from_evidence_id, link.to_evidence_id) for link in sentence_links} == {
        ("comment_raw", "comment_sentence"),
        ("promo_raw", "promo_sentence"),
    }
    assert all(link.confidence == Decimal("1.0000") for link in sentence_links)
    assert [(link.from_evidence_id, link.to_evidence_id, link.confidence) for link in dimension_links] == [
        ("comment_raw", "comment_dimension", Decimal("0.5500"))
    ]
    assert dimension_links[0].link_payload_json == {
        "dimension_path_raw": "使用体验>游戏",
        "match_rule": "same_source_row",
        "source_row_id": "comment_data:10",
    }


def test_link_builder_creates_comment_identity_and_text_duplicate_links():
    builder = EvidenceLinkBuilder()
    left = atom(
        "comment_left",
        Core3EvidenceType.COMMENT_RAW,
        comment_id="cmt-001",
        comment_text_hash="sha256:text:same",
        segment_text_hash="sha256:segment:same",
    )
    right = atom(
        "comment_right",
        Core3EvidenceType.COMMENT_SENTENCE,
        clean_record_key="comment_sentence:comment_data:1:1",
        comment_id="cmt-001",
        comment_text_hash="sha256:text:same",
        segment_text_hash="sha256:segment:same",
    )
    missing_comment_id = atom(
        "comment_without_id",
        Core3EvidenceType.COMMENT_DIMENSION,
        clean_record_key="comment_dimension:comment_data:1",
        comment_text_hash="sha256:text:same",
    )

    grouped = links_by_type(builder.build_links([left, right, missing_comment_id]))

    assert [(link.from_evidence_id, link.to_evidence_id, link.confidence) for link in grouped[Core3EvidenceLinkType.SAME_COMMENT]] == [
        ("comment_left", "comment_right", Decimal("0.8000"))
    ]
    assert {
        (frozenset({link.from_evidence_id, link.to_evidence_id}), link.confidence)
        for link in grouped[Core3EvidenceLinkType.SAME_COMMENT_TEXT]
    } == {
        (frozenset({"comment_left", "comment_right"}), Decimal("0.7000")),
        (frozenset({"comment_left", "comment_without_id"}), Decimal("0.7000")),
        (frozenset({"comment_right", "comment_without_id"}), Decimal("0.7000")),
    }
    assert [(link.from_evidence_id, link.to_evidence_id, link.confidence) for link in grouped[Core3EvidenceLinkType.SAME_SEGMENT]] == [
        ("comment_left", "comment_right", Decimal("0.7000"))
    ]


def test_large_text_duplicate_group_uses_representative_links_instead_of_pairwise_explosion():
    builder = EvidenceLinkBuilder()
    duplicates = [
        atom(
            f"comment_dup_{index:02d}",
            Core3EvidenceType.COMMENT_RAW,
            source_row_id=f"comment_data:{index}",
            clean_record_key=f"comment:comment_data:{index}",
            comment_text_hash="sha256:text:large-duplicate",
        )
        for index in range(60)
    ]

    links = builder.build_same_text_links(duplicates)

    assert len(links) == 59
    assert {link.link_type for link in links} == {Core3EvidenceLinkType.SAME_COMMENT_TEXT}
    assert {link.from_evidence_id for link in links} == {"comment_dup_00"}
    assert {link.to_evidence_id for link in links} == {f"comment_dup_{index:02d}" for index in range(1, 60)}
    assert all(link.link_payload_json["link_strategy"] == "representative_duplicate_group" for link in links)
    assert all(link.link_payload_json["duplicate_group_size"] == 60 for link in links)


def test_large_same_comment_group_uses_representative_links_instead_of_pairwise_explosion():
    builder = EvidenceLinkBuilder()
    duplicates = [
        atom(
            f"comment_same_{index:02d}",
            Core3EvidenceType.COMMENT_SENTENCE,
            source_row_id=f"comment_data:{index}",
            clean_record_key=f"comment_sentence:comment_data:{index}:1",
            comment_id="comment-large-duplicate",
        )
        for index in range(60)
    ]

    links = builder.build_same_comment_links(duplicates)

    assert len(links) == 59
    assert {link.link_type for link in links} == {Core3EvidenceLinkType.SAME_COMMENT}
    assert {link.from_evidence_id for link in links} == {"comment_same_00"}
    assert {link.to_evidence_id for link in links} == {f"comment_same_{index:02d}" for index in range(1, 60)}
    assert all(link.link_payload_json["link_strategy"] == "representative_same_comment_group" for link in links)
    assert all(link.link_payload_json["same_comment_group_size"] == 60 for link in links)


def test_link_builder_links_quality_issues_by_clean_record_source_row_and_domain():
    builder = EvidenceLinkBuilder()
    param = atom(
        "param_fact",
        Core3EvidenceType.PARAM_RAW,
        source_row_id="attribute_data:123",
        clean_record_key="attribute:attribute_data:123",
    )
    param_issue = atom(
        "param_issue",
        Core3EvidenceType.QUALITY_ISSUE,
        source_row_id="quality:param",
        clean_record_key="quality:unknown_value:TV00029115",
        evidence_payload_json={
            "clean_record_key": "attribute:attribute_data:123",
            "domain": "param",
            "issue_type": "unknown_value",
        },
    )
    comment = atom(
        "comment_fact",
        Core3EvidenceType.COMMENT_RAW,
        source_row_id="comment_data:456",
        clean_record_key="comment:comment_data:456",
    )
    comment_issue = atom(
        "comment_issue",
        Core3EvidenceType.QUALITY_ISSUE,
        source_row_id="comment_data:456",
        clean_record_key="quality:low_value_comment:TV00029115",
        evidence_payload_json={"domain": "comment", "issue_type": "low_value_comment"},
    )
    claim = atom(
        "claim_fact",
        Core3EvidenceType.PROMO_RAW,
        source_row_id="selling_points_data:789",
        clean_record_key="claim:selling_points_data:789",
    )
    claim_issue = atom(
        "claim_issue",
        Core3EvidenceType.QUALITY_ISSUE,
        source_row_id="quality:claim",
        clean_record_key="quality:claim_coverage_missing:TV00029115",
        evidence_payload_json={"domain": "claim", "issue_type": "claim_coverage_missing"},
    )

    quality_links = links_by_type(
        builder.build_links([param, param_issue, comment, comment_issue, claim, claim_issue])
    )[Core3EvidenceLinkType.HAS_QUALITY_ISSUE]

    assert {
        (link.from_evidence_id, link.to_evidence_id, link.link_payload_json["match_rule"])
        for link in quality_links
    } >= {
        ("param_fact", "param_issue", "quality_payload_clean_record_key"),
        ("comment_fact", "comment_issue", "source_row_id"),
        ("claim_fact", "claim_issue", "sku_code_domain"),
    }
    assert all(link.confidence == Decimal("1.0000") for link in quality_links)
    assert all(link.link_payload_json["domain"] in {"param", "comment", "claim"} for link in quality_links)


def test_quality_issue_links_only_use_indexed_candidates_not_cartesian_pairs():
    builder = EvidenceLinkBuilder()
    unrelated_facts = [
        atom(
            f"unrelated_param_{index}",
            Core3EvidenceType.PARAM_RAW,
            source_row_id=f"attribute_data:{index}",
            clean_record_key=f"attribute:attribute_data:{index}",
            sku_code=f"OTHER{index}",
        )
        for index in range(200)
    ]
    unrelated_issues = [
        atom(
            f"unrelated_issue_{index}",
            Core3EvidenceType.QUALITY_ISSUE,
            source_row_id=f"quality:unrelated:{index}",
            clean_record_key=f"quality:unknown_value:OTHER{index}",
            sku_code=f"NO_FACT{index}",
            evidence_payload_json={"domain": "param", "issue_type": "unknown_value"},
        )
        for index in range(50)
    ]
    target_fact = atom(
        "target_param",
        Core3EvidenceType.PARAM_RAW,
        source_row_id="attribute_data:target",
        clean_record_key="attribute:attribute_data:target",
    )
    target_issue = atom(
        "target_issue",
        Core3EvidenceType.QUALITY_ISSUE,
        source_row_id="quality:target",
        clean_record_key="quality:unknown_value:TV00029115",
        evidence_payload_json={
            "clean_record_key": "attribute:attribute_data:target",
            "domain": "param",
            "issue_type": "unknown_value",
        },
    )

    links = builder.build_quality_issue_links([*unrelated_facts, *unrelated_issues, target_fact, target_issue])

    assert [(link.from_evidence_id, link.to_evidence_id, link.link_payload_json["match_rule"]) for link in links] == [
        ("target_param", "target_issue", "quality_payload_clean_record_key")
    ]


def test_row_level_quality_issue_does_not_fan_out_to_entire_domain():
    builder = EvidenceLinkBuilder()
    matching_comment = atom(
        "matching_comment",
        Core3EvidenceType.COMMENT_RAW,
        source_row_id="comment_data:456",
        clean_record_key="comment:comment_data:456",
    )
    same_sku_other_comment = atom(
        "same_sku_other_comment",
        Core3EvidenceType.COMMENT_RAW,
        source_row_id="comment_data:789",
        clean_record_key="comment:comment_data:789",
    )
    row_issue = atom(
        "row_issue",
        Core3EvidenceType.QUALITY_ISSUE,
        source_row_id="comment_data:456",
        clean_record_key="quality:low_value_comment:TV00029115",
        evidence_payload_json={"domain": "comment", "issue_type": "low_value_comment"},
    )

    links = builder.build_quality_issue_links([matching_comment, same_sku_other_comment, row_issue])

    assert [(link.from_evidence_id, link.to_evidence_id, link.link_payload_json["match_rule"]) for link in links] == [
        ("matching_comment", "row_issue", "source_row_id")
    ]


def test_link_builder_creates_supersedes_links_and_dedupes_same_triple():
    builder = EvidenceLinkBuilder()
    old_atom = atom("old_param", Core3EvidenceType.PARAM_RAW, clean_hash="sha256:m01_clean_hash_v1:old")
    new_atom = atom("new_param", Core3EvidenceType.PARAM_RAW, clean_hash="sha256:m01_clean_hash_v1:new")
    old_atom["evidence_key"] = "sha256:m02_evidence_key:param:stable"
    new_atom["evidence_key"] = "sha256:m02_evidence_key:param:stable"

    links = builder.build_links(
        [],
        superseded_pairs=[
            (new_atom, old_atom),
            (new_atom, old_atom),
        ],
    )

    assert len(links) == 1
    link = links[0]
    assert link.link_type == Core3EvidenceLinkType.SUPERSEDES
    assert (link.from_evidence_id, link.to_evidence_id, link.confidence) == (
        "new_param",
        "old_param",
        Decimal("1.0000"),
    )
    assert link.link_payload_json == {
        "evidence_key": "sha256:m02_evidence_key:param:stable",
        "match_rule": "same_evidence_key",
        "new_clean_hash": "sha256:m01_clean_hash_v1:new",
        "old_clean_hash": "sha256:m01_clean_hash_v1:old",
    }


def test_link_builder_payloads_stay_inside_m02_evidence_boundary():
    builder = EvidenceLinkBuilder()
    comment_raw = atom(
        "comment_raw",
        Core3EvidenceType.COMMENT_RAW,
        source_row_id="comment_data:10",
        comment_id="cmt-001",
        comment_text_hash="sha256:text:same",
        segment_text_hash="sha256:segment:same",
    )
    comment_sentence = atom(
        "comment_sentence",
        Core3EvidenceType.COMMENT_SENTENCE,
        source_row_id="comment_data:10",
        clean_record_key="comment_sentence:comment_data:10:1",
        comment_id="cmt-001",
        comment_text_hash="sha256:text:same",
        segment_text_hash="sha256:segment:same",
    )

    links = builder.build_links([comment_raw, comment_sentence])

    forbidden_business_words = {"task", "target_group", "battlefield", "competitor", "score", "report"}
    assert links
    for link in links:
        payload_text = " ".join(str(item) for key_value in link.link_payload_json.items() for item in key_value)
        assert all(word not in payload_text for word in forbidden_business_words)


def test_link_drafts_are_repository_payload_compatible():
    builder = EvidenceLinkBuilder()
    [link] = builder.build_sentence_links(
        [
            atom("comment_raw", Core3EvidenceType.COMMENT_RAW, source_row_id="comment_data:10"),
            atom(
                "comment_sentence",
                Core3EvidenceType.COMMENT_SENTENCE,
                source_row_id="comment_data:10",
                clean_record_key="comment_sentence:comment_data:10:1",
            ),
        ]
    )

    assert link.to_payload() == {
        "project_id": PROJECT_ID,
        "category_code": "TV",
        "batch_id": BATCH_ID,
        "from_evidence_id": "comment_raw",
        "to_evidence_id": "comment_sentence",
        "from_evidence_key": "sha256:m02_evidence_key:comment_raw",
        "to_evidence_key": "sha256:m02_evidence_key:comment_sentence",
        "link_type": "has_sentence",
        "link_payload_json": {
            "child_type": "comment_sentence",
            "match_rule": "same_source_row",
            "parent_type": "comment_raw",
            "source_row_id": "comment_data:10",
        },
        "confidence": Decimal("1.0000"),
    }
