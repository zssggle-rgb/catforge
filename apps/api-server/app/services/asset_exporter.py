import csv
import json
import zipfile
from pathlib import Path
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    AssetPackage,
    BattlefieldDef,
    CategoryProject,
    ClaimValueLayerResult,
    CommentTopicDef,
    EvidenceItem,
    SkuBattlefieldScore,
    SkuClaimResult,
    SkuCommentTopicResult,
    SkuParamNormalized,
    SkuTaskScore,
    StdClaimDef,
    StdParamDef,
    TargetGroupDef,
    UserTaskDef,
)


ALLOWED_EXPORT_FILES = {
    "std_param_def.csv",
    "std_claim_def.csv",
    "comment_topic_def.csv",
    "user_task_def.csv",
    "target_group_def.csv",
    "battlefield_def.csv",
    "mapping_rules.csv",
    "scoring.yaml",
    "competitor_rule.yaml",
    "sample_sku_results.csv",
    "sample_evidence_cards.jsonl",
    "asset_readme.md",
    "release_note.md",
}

FORBIDDEN_PATTERNS = [
    "prompt",
    "gold_set_builder",
    "category_builder",
    "migration_template",
    "rule_generator",
    "semantic_clustering",
    "factory_internal",
    "benchmark_builder",
]


def export_runtime_package(db: Session, project_id: str, version: str) -> AssetPackage:
    project = db.get(CategoryProject, project_id)
    if not project:
        raise ValueError("项目不存在")

    settings = get_settings()
    export_root = settings.resolved_export_dir / project_id / version
    export_root.mkdir(parents=True, exist_ok=True)

    _write_param_defs(db, project_id, export_root / "std_param_def.csv")
    _write_claim_defs(db, project_id, export_root / "std_claim_def.csv")
    _write_topic_defs(db, project_id, export_root / "comment_topic_def.csv")
    _write_task_defs(db, project_id, export_root / "user_task_def.csv")
    _write_target_groups(db, project_id, export_root / "target_group_def.csv")
    _write_battlefield_defs(db, project_id, export_root / "battlefield_def.csv")
    _write_mapping_rules(db, project_id, export_root / "mapping_rules.csv")
    (export_root / "scoring.yaml").write_text(_scoring_yaml(), encoding="utf-8")
    (export_root / "competitor_rule.yaml").write_text(_competitor_yaml(), encoding="utf-8")
    _write_sample_sku_results(db, project_id, export_root / "sample_sku_results.csv")
    _write_evidence_cards(db, project_id, export_root / "sample_evidence_cards.jsonl")
    (export_root / "asset_readme.md").write_text(
        "# CatForge 品铸运行态资产包\n\n"
        "本包仅包含授权彩电品类的运行态资产和样例结果，不包含品类生产工具、提示词模板、评测集构建器或跨品类迁移方法。\n",
        encoding="utf-8",
    )
    (export_root / "release_note.md").write_text(
        f"# 发布说明\n\n- 品类: {project.category_code}\n- 版本: {version}\n- 边界: 仅运行态白名单文件。\n",
        encoding="utf-8",
    )

    file_names = sorted(path.name for path in export_root.iterdir() if path.is_file())
    _assert_export_boundary(file_names, export_root)

    zip_path = settings.resolved_export_dir / project_id / f"catforge_runtime_{version}.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_name in file_names:
            archive.write(export_root / file_name, arcname=file_name)

    package = AssetPackage(
        project_id=project_id,
        category_code=project.category_code,
        version=version,
        status="exported",
        file_list=file_names,
        package_path=str(zip_path),
        package_metadata={
            "boundary": "runtime_whitelist_only",
            "forbidden_patterns": FORBIDDEN_PATTERNS,
        },
    )
    db.add(package)
    db.commit()
    db.refresh(package)
    return package


def _assert_export_boundary(file_names: list[str], export_root: Path) -> None:
    unexpected = set(file_names) - ALLOWED_EXPORT_FILES
    if unexpected:
        raise ValueError(f"导出文件不在白名单内: {sorted(unexpected)}")
    for file_name in file_names:
        lowered = file_name.lower()
        if any(pattern in lowered for pattern in FORBIDDEN_PATTERNS):
            raise ValueError(f"导出文件命中禁止模式: {file_name}")
        content = (export_root / file_name).read_text(encoding="utf-8", errors="ignore").lower()
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in content:
                raise ValueError(f"导出内容命中禁止模式 {pattern}: {file_name}")


def _write_rows(path: Path, rows: Iterable[dict], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: _csv_value(row.get(key)) for key in fieldnames})


def _csv_value(value):
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return "" if value is None else value


def _write_param_defs(db: Session, project_id: str, path: Path) -> None:
    rows = db.execute(select(StdParamDef).where(StdParamDef.project_id == project_id)).scalars()
    _write_rows(
        path,
        [
            {
                "param_code": row.param_code,
                "param_name": row.param_name,
                "param_group": row.param_group,
                "data_type": row.data_type,
                "unit": row.unit,
                "raw_aliases": row.raw_aliases,
                "normalize_rule": row.normalize_rule,
                "version": row.version,
                "status": row.status,
            }
            for row in rows
        ],
        ["param_code", "param_name", "param_group", "data_type", "unit", "raw_aliases", "normalize_rule", "version", "status"],
    )


def _write_claim_defs(db: Session, project_id: str, path: Path) -> None:
    rows = db.execute(select(StdClaimDef).where(StdClaimDef.project_id == project_id)).scalars()
    _write_rows(
        path,
        [
            {
                "claim_code": row.claim_code,
                "claim_name": row.claim_name,
                "claim_group": row.claim_group,
                "definition": row.definition,
                "activation_rule": row.activation_rule,
                "raw_keywords": row.raw_keywords,
                "mapped_task_codes": row.mapped_task_codes,
                "mapped_battlefield_codes": row.mapped_battlefield_codes,
                "version": row.version,
                "status": row.status,
            }
            for row in rows
        ],
        ["claim_code", "claim_name", "claim_group", "definition", "activation_rule", "raw_keywords", "mapped_task_codes", "mapped_battlefield_codes", "version", "status"],
    )


def _write_topic_defs(db: Session, project_id: str, path: Path) -> None:
    rows = db.execute(select(CommentTopicDef).where(CommentTopicDef.project_id == project_id)).scalars()
    _write_rows(
        path,
        [
            {
                "topic_code": row.topic_code,
                "topic_name": row.topic_name,
                "topic_group": row.topic_group,
                "keywords": row.keywords,
                "activates_product_claim": row.activates_product_claim,
                "version": row.version,
                "status": row.status,
            }
            for row in rows
        ],
        ["topic_code", "topic_name", "topic_group", "keywords", "activates_product_claim", "version", "status"],
    )


def _write_task_defs(db: Session, project_id: str, path: Path) -> None:
    rows = db.execute(select(UserTaskDef).where(UserTaskDef.project_id == project_id)).scalars()
    _write_rows(
        path,
        [
            {
                "task_code": row.task_code,
                "task_name": row.task_name,
                "positive_claim_codes": row.positive_claim_codes,
                "positive_param_codes": row.positive_param_codes,
                "comment_topic_codes": row.comment_topic_codes,
                "score_rule": row.score_rule,
                "version": row.version,
                "status": row.status,
            }
            for row in rows
        ],
        ["task_code", "task_name", "positive_claim_codes", "positive_param_codes", "comment_topic_codes", "score_rule", "version", "status"],
    )


def _write_target_groups(db: Session, project_id: str, path: Path) -> None:
    rows = db.execute(select(TargetGroupDef).where(TargetGroupDef.project_id == project_id)).scalars()
    _write_rows(
        path,
        [
            {
                "target_group_code": row.target_group_code,
                "target_group_name": row.target_group_name,
                "definition": row.definition,
                "version": row.version,
                "status": row.status,
            }
            for row in rows
        ],
        ["target_group_code", "target_group_name", "definition", "version", "status"],
    )


def _write_battlefield_defs(db: Session, project_id: str, path: Path) -> None:
    rows = db.execute(select(BattlefieldDef).where(BattlefieldDef.project_id == project_id)).scalars()
    _write_rows(
        path,
        [
            {
                "battlefield_code": row.battlefield_code,
                "battlefield_name": row.battlefield_name,
                "definition": row.definition,
                "score_rule": row.score_rule,
                "entry_thresholds": row.entry_thresholds,
                "version": row.version,
                "status": row.status,
            }
            for row in rows
        ],
        ["battlefield_code", "battlefield_name", "definition", "score_rule", "entry_thresholds", "version", "status"],
    )


def _write_mapping_rules(db: Session, project_id: str, path: Path) -> None:
    claims = db.execute(select(StdClaimDef).where(StdClaimDef.project_id == project_id)).scalars()
    _write_rows(
        path,
        [
            {
                "source_type": "claim",
                "source_code": row.claim_code,
                "mapped_task_codes": row.mapped_task_codes,
                "mapped_battlefield_codes": row.mapped_battlefield_codes,
                "supporting_param_codes": row.supporting_param_codes,
            }
            for row in claims
        ],
        ["source_type", "source_code", "mapped_task_codes", "mapped_battlefield_codes", "supporting_param_codes"],
    )


def _write_sample_sku_results(db: Session, project_id: str, path: Path) -> None:
    params = db.execute(select(SkuParamNormalized).where(SkuParamNormalized.project_id == project_id)).scalars().all()
    claims = db.execute(select(SkuClaimResult).where(SkuClaimResult.project_id == project_id)).scalars().all()
    topics = db.execute(select(SkuCommentTopicResult).where(SkuCommentTopicResult.project_id == project_id)).scalars().all()
    tasks = db.execute(select(SkuTaskScore).where(SkuTaskScore.project_id == project_id)).scalars().all()
    battlefields = db.execute(select(SkuBattlefieldScore).where(SkuBattlefieldScore.project_id == project_id)).scalars().all()
    layers = db.execute(select(ClaimValueLayerResult).where(ClaimValueLayerResult.project_id == project_id)).scalars().all()
    sku_codes = sorted({row.sku_code for row in params + claims + topics + tasks + battlefields})
    _write_rows(
        path,
        [
            {
                "sku_code": sku,
                "params": {row.param_code: row.normalized_value for row in params if row.sku_code == sku},
                "claims": [row.claim_code for row in claims if row.sku_code == sku],
                "topics": [row.topic_code for row in topics if row.sku_code == sku],
                "tasks": {row.task_code: row.score for row in tasks if row.sku_code == sku},
                "battlefields": {row.battlefield_code: row.relation_level for row in battlefields if row.sku_code == sku},
                "claim_layers": {row.claim_code: row.layer for row in layers},
            }
            for sku in sku_codes
        ],
        ["sku_code", "params", "claims", "topics", "tasks", "battlefields", "claim_layers"],
    )


def _write_evidence_cards(db: Session, project_id: str, path: Path) -> None:
    evidence_rows = db.execute(
        select(EvidenceItem).where(EvidenceItem.project_id == project_id).limit(200)
    ).scalars()
    with path.open("w", encoding="utf-8") as handle:
        for row in evidence_rows:
            handle.write(
                json.dumps(
                    {
                        "evidence_id": row.evidence_id,
                        "sku_code": row.sku_code,
                        "source_type": row.source_type,
                        "field_name": row.field_name,
                        "raw_value": row.raw_value,
                        "normalized_value": row.normalized_value,
                        "confidence": row.confidence,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def _scoring_yaml() -> str:
    return (
        "task_score:\n"
        "  claim: 0.45\n"
        "  param: 0.25\n"
        "  comment: 0.20\n"
        "  market: 0.10\n"
        "battlefield_score:\n"
        "  task_score: 0.40\n"
        "  core_claim_bundle: 0.35\n"
        "  price_channel_fit: 0.15\n"
        "  comment_validation: 0.10\n"
    )


def _competitor_yaml() -> str:
    return (
        "direct_competitor_score:\n"
        "  battlefield_overlap: 0.25\n"
        "  price_similarity: 0.20\n"
        "  standard_claim_similarity: 0.20\n"
        "  core_param_similarity: 0.15\n"
        "  channel_overlap: 0.10\n"
        "  sales_strength: 0.10\n"
        "types:\n"
        "  direct: '同战场、同价格带、同渠道、关键卖点接近'\n"
        "  benchmark: '同战场且规格、价格或销量更强'\n"
    )

