from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AssetVersion, CategoryProject, RuntimeExport
from app.services.asset_exporter import (
    _write_battlefield_defs,
    _write_claim_defs,
    _write_evidence_cards,
    _write_mapping_rules,
    _write_param_defs,
    _write_sample_sku_results,
    _write_target_groups,
    _write_task_defs,
    _write_topic_defs,
)
from app.services.audit_service import create_audit_event
from app.services.hardening_utils import sha256_bytes, sha256_json
from app.services.version_governance_service import latest_released_asset_version

REPO_ROOT = Path(__file__).resolve().parents[4]
ALLOWED_FILES_PATH = REPO_ROOT / "examples" / "goal2" / "exports" / "allowed_files.txt"
FORBIDDEN_PATTERNS_PATH = REPO_ROOT / "examples" / "goal2" / "exports" / "forbidden_patterns.txt"


class RuntimeExportError(ValueError):
    pass


def export_released_runtime_assets(
    db: Session,
    *,
    project_id: str,
    asset_version_id: str | None = None,
    allow_draft: bool = False,
    created_by: str = "system",
) -> RuntimeExport:
    project = db.get(CategoryProject, project_id)
    if not project:
        raise RuntimeExportError("项目不存在")
    asset_version = (
        db.get(AssetVersion, asset_version_id)
        if asset_version_id
        else latest_released_asset_version(db, project_id)
    )
    if not asset_version:
        raise RuntimeExportError("没有可导出的 released 资产版本")
    if asset_version.lifecycle_status != "released" and not allow_draft:
        raise RuntimeExportError("运行态导出拒绝未发布资产版本")

    settings = get_settings()
    export_root = settings.resolved_export_dir / project_id / f"runtime_{asset_version.version}"
    export_root.mkdir(parents=True, exist_ok=True)
    _clear_export_root(export_root)

    _write_default_runtime_files(db, project_id, project, asset_version, export_root)
    _write_manifest_runtime_files(asset_version.manifest_json.get("runtime_files", []), export_root)
    file_hashes = validate_runtime_export_boundary(export_root)
    manifest = {
        "export_id": "pending",
        "asset_version": asset_version.version,
        "asset_version_id": asset_version.asset_version_id,
        "category": asset_version.category_code,
        "files": [{"path": name, "sha256": file_hashes[name]} for name in sorted(file_hashes)],
        "created_by": created_by,
    }
    manifest["content_hash"] = sha256_json(manifest)
    (export_root / "asset_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    validate_runtime_export_boundary(export_root)

    zip_path = settings.resolved_export_dir / project_id / f"catforge_runtime_goal2_{asset_version.version}.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(export_root.iterdir()):
            if path.is_file():
                archive.write(path, arcname=path.name)

    export = RuntimeExport(
        project_id=project_id,
        asset_version_id=asset_version.asset_version_id,
        status="completed",
        manifest_json=manifest,
        file_path=str(zip_path),
        content_hash=sha256_bytes(zip_path.read_bytes()),
        created_by=created_by,
    )
    db.add(export)
    db.flush()
    manifest["export_id"] = export.export_id
    export.manifest_json = manifest
    create_audit_event(
        db,
        action="runtime_export_created",
        object_type="runtime_export",
        object_id=export.export_id,
        project_id=project_id,
        actor_id=created_by,
        after=runtime_export_to_dict(export),
        metadata={"asset_version_id": asset_version.asset_version_id},
    )
    db.commit()
    db.refresh(export)
    return export


def validate_runtime_export_boundary(export_root: Path) -> dict[str, str]:
    allowed_files = _allowed_files()
    forbidden_patterns = _forbidden_patterns()
    file_hashes: dict[str, str] = {}
    for path in export_root.iterdir():
        if not path.is_file():
            continue
        if path.name not in allowed_files:
            raise RuntimeExportError(f"导出文件不在白名单内: {path.name}")
        lowered_name = path.name.lower()
        for pattern in forbidden_patterns:
            if pattern in lowered_name:
                raise RuntimeExportError(f"导出文件名命中禁止模式 {pattern}: {path.name}")
        content = path.read_text(encoding="utf-8", errors="ignore")
        lowered = content.lower()
        for pattern in forbidden_patterns:
            if pattern in lowered:
                raise RuntimeExportError(f"导出内容命中禁止模式 {pattern}: {path.name}")
        file_hashes[path.name] = sha256_bytes(path.read_bytes())
    unexpected_missing = {"asset_manifest.json", "release_note.md"} - (set(file_hashes) | {"asset_manifest.json"})
    if unexpected_missing:
        raise RuntimeExportError(f"导出缺少必要文件: {sorted(unexpected_missing)}")
    return file_hashes


def runtime_export_to_dict(row: RuntimeExport) -> dict[str, Any]:
    return {
        "export_id": row.export_id,
        "project_id": row.project_id,
        "asset_version_id": row.asset_version_id,
        "status": row.status,
        "manifest_json": row.manifest_json,
        "file_path": row.file_path,
        "content_hash": row.content_hash,
        "created_by": row.created_by,
    }


def _write_default_runtime_files(
    db: Session,
    project_id: str,
    project: CategoryProject,
    asset_version: AssetVersion,
    export_root: Path,
) -> None:
    _write_param_defs(db, project_id, export_root / "std_param_def.csv")
    _write_claim_defs(db, project_id, export_root / "std_claim_def.csv")
    _write_topic_defs(db, project_id, export_root / "comment_topic_def.csv")
    _write_task_defs(db, project_id, export_root / "user_task_def.csv")
    _write_target_groups(db, project_id, export_root / "target_group_def.csv")
    _write_battlefield_defs(db, project_id, export_root / "battlefield_def.csv")
    _write_mapping_rules(db, project_id, export_root / "mapping_rules.csv")
    (export_root / "scoring_rules.yaml").write_text(
        "task_score:\n  source: released_runtime\nbattlefield_score:\n  source: released_runtime\n",
        encoding="utf-8",
    )
    (export_root / "competitor_runtime_rules.yaml").write_text(
        "competitor_score:\n  source: released_runtime\n  types: [direct, benchmark, substitute, potential]\n",
        encoding="utf-8",
    )
    _write_sample_sku_results(db, project_id, export_root / "sku_analysis_results.csv")
    _write_evidence_cards(db, project_id, export_root / "evidence_cards.jsonl")
    (export_root / "quality_report.json").write_text(
        json.dumps(asset_version.manifest_json.get("quality_gates", {}), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (export_root / "release_note.md").write_text(
        f"# CatForge 运行态发布\n\n- 品类: {project.category_code}\n- 版本: {asset_version.version}\n- 仅包含 Goal2 白名单运行态文件。\n",
        encoding="utf-8",
    )


def _write_manifest_runtime_files(runtime_files: list[dict[str, Any]], export_root: Path) -> None:
    for item in runtime_files:
        file_name = str(item["path"])
        if "/" in file_name or "\\" in file_name or file_name in {"", ".", ".."}:
            raise RuntimeExportError(f"运行态文件名非法: {file_name}")
        path = export_root / file_name
        path.write_text(str(item.get("content", "")), encoding="utf-8")


def _clear_export_root(export_root: Path) -> None:
    for path in export_root.iterdir():
        if path.is_file():
            path.unlink()


def _allowed_files() -> set[str]:
    return {
        line.strip()
        for line in ALLOWED_FILES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }


def _forbidden_patterns() -> list[str]:
    return [
        line.strip().lower()
        for line in FORBIDDEN_PATTERNS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
