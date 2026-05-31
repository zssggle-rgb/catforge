from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    CategoryProject,
    DataQualityIssue,
    ImportBatch,
    RawMarketFact,
    RawSkuClaim,
    RawSkuComment,
    RawSkuMaster,
    RawSkuParam,
    SourceFile,
)
from app.services.utils import clean_text, is_missing, to_bool, to_float


FILE_TYPES = {
    "master": "sku_master",
    "sku_master": "sku_master",
    "params": "sku_param",
    "param": "sku_param",
    "sku_param": "sku_param",
    "claims": "sku_claim",
    "claim": "sku_claim",
    "sku_claim": "sku_claim",
    "comments": "sku_comment",
    "comment": "sku_comment",
    "sku_comment": "sku_comment",
    "market": "market_fact",
    "market_fact": "market_fact",
}

REQUIRED_FIELDS = {
    "sku_master": ["sku_code", "brand", "model_name", "category_code"],
    "sku_param": ["sku_code", "raw_param_name"],
    "sku_claim": ["sku_code", "claim_text"],
    "sku_comment": ["sku_code", "comment_text"],
    "market_fact": ["sku_code", "period", "period_type", "channel_group", "channel_type"],
}

MODEL_BY_TYPE = {
    "sku_master": RawSkuMaster,
    "sku_param": RawSkuParam,
    "sku_claim": RawSkuClaim,
    "sku_comment": RawSkuComment,
    "market_fact": RawMarketFact,
}


def infer_file_type(filename: str, explicit: str | None = None) -> str:
    if explicit:
        key = explicit.lower().strip()
        if key in FILE_TYPES:
            return FILE_TYPES[key]
    lowered = filename.lower()
    for marker, file_type in FILE_TYPES.items():
        if marker in lowered:
            return file_type
    raise ValueError(f"无法识别文件类型: {filename}")


def register_source_file(
    db: Session,
    *,
    project_id: str,
    file_name: str,
    file_type: str,
    storage_path: str,
) -> SourceFile:
    project = db.get(CategoryProject, project_id)
    if not project:
        raise ValueError("项目不存在")
    source = SourceFile(
        project_id=project_id,
        category_code=project.category_code,
        file_name=file_name,
        file_type=infer_file_type(file_name, file_type),
        storage_path=storage_path,
        status="uploaded",
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def save_upload(project_id: str, filename: str, data: bytes) -> Path:
    settings = get_settings()
    target_dir = settings.resolved_upload_dir / project_id
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name
    target = target_dir / safe_name
    target.write_bytes(data)
    return target


def _read_frame(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".xlsx", ".xls"}:
        return pd.read_excel(path, dtype=str).fillna("")
    return pd.read_csv(path, dtype=str, keep_default_na=False).fillna("")


def _row_dict(row: pd.Series) -> dict[str, Any]:
    return {str(key): ("" if value is None else value) for key, value in row.to_dict().items()}


def _add_issue(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    source_file_id: str,
    import_batch_id: str,
    raw_row_id: str | None,
    table_name: str,
    field_name: str | None,
    issue_code: str,
    severity: str,
    message: str,
    evidence: dict | None = None,
) -> None:
    db.add(
        DataQualityIssue(
            project_id=project_id,
            category_code=category_code,
            source_file_id=source_file_id,
            import_batch_id=import_batch_id,
            raw_row_id=raw_row_id,
            table_name=table_name,
            field_name=field_name,
            issue_code=issue_code,
            severity=severity,
            message=message,
            evidence=evidence or {},
        )
    )


def _validate_required(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    source_file_id: str,
    import_batch_id: str,
    file_type: str,
    raw_row_id: str,
    data: dict[str, Any],
) -> int:
    errors = 0
    for field in REQUIRED_FIELDS[file_type]:
        if is_missing(data.get(field)):
            _add_issue(
                db,
                project_id=project_id,
                category_code=category_code,
                source_file_id=source_file_id,
                import_batch_id=import_batch_id,
                raw_row_id=raw_row_id,
                table_name=MODEL_BY_TYPE[file_type].__tablename__,
                field_name=field,
                issue_code="missing_required_field",
                severity="critical",
                message=f"必填字段 {field} 为空",
                evidence={"row": data},
            )
            errors += 1
    return errors


def _parse_market_number(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    source_file_id: str,
    import_batch_id: str,
    raw_row_id: str,
    field_name: str,
    value: Any,
) -> float | None:
    if is_missing(value):
        return None
    parsed = to_float(value)
    if parsed is None:
        _add_issue(
            db,
            project_id=project_id,
            category_code=category_code,
            source_file_id=source_file_id,
            import_batch_id=import_batch_id,
            raw_row_id=raw_row_id,
            table_name="raw_market_fact",
            field_name=field_name,
            issue_code="invalid_numeric_field",
            severity="warning",
            message=f"数值字段 {field_name} 无法解析: {value}",
            evidence={"raw_value": value},
        )
    return parsed


def import_source_file(db: Session, source_file: SourceFile) -> ImportBatch:
    path = Path(source_file.storage_path)
    if not path.exists():
        raise FileNotFoundError(f"源文件不存在: {path}")
    project = db.get(CategoryProject, source_file.project_id)
    if not project:
        raise ValueError("项目不存在")

    frame = _read_frame(path)
    batch = ImportBatch(
        project_id=source_file.project_id,
        category_code=project.category_code,
        source_file_id=source_file.source_file_id,
        file_type=source_file.file_type,
        status="running",
    )
    db.add(batch)
    db.flush()

    error_count = 0
    for index, row in frame.iterrows():
        raw_row_id = str(index + 2)
        data = _row_dict(row)
        data.setdefault("category_code", project.category_code)
        error_count += _validate_required(
            db,
            project_id=project.project_id,
            category_code=project.category_code,
            source_file_id=source_file.source_file_id,
            import_batch_id=batch.import_batch_id,
            file_type=source_file.file_type,
            raw_row_id=raw_row_id,
            data=data,
        )

        common = {
            "project_id": project.project_id,
            "category_code": clean_text(data.get("category_code")) or project.category_code,
            "source_file_id": source_file.source_file_id,
            "import_batch_id": batch.import_batch_id,
            "raw_row_id": raw_row_id,
        }
        if source_file.file_type == "sku_master":
            db.add(
                RawSkuMaster(
                    **common,
                    sku_code=clean_text(data.get("sku_code")) or None,
                    brand=clean_text(data.get("brand")) or None,
                    model_name=clean_text(data.get("model_name")) or None,
                    series=clean_text(data.get("series")) or None,
                    category_name=clean_text(data.get("category_name")) or None,
                    launch_date=clean_text(data.get("launch_date")) or None,
                    product_url=clean_text(data.get("product_url")) or None,
                )
            )
        elif source_file.file_type == "sku_param":
            db.add(
                RawSkuParam(
                    **common,
                    sku_code=clean_text(data.get("sku_code")) or None,
                    raw_param_name=clean_text(data.get("raw_param_name")) or None,
                    raw_param_value=clean_text(data.get("raw_param_value")) or None,
                    raw_unit=clean_text(data.get("raw_unit")) or None,
                    source_channel=clean_text(data.get("source_channel")) or None,
                    observed_at=clean_text(data.get("observed_at")) or None,
                )
            )
        elif source_file.file_type == "sku_claim":
            db.add(
                RawSkuClaim(
                    **common,
                    sku_code=clean_text(data.get("sku_code")) or None,
                    claim_title=clean_text(data.get("claim_title")) or None,
                    claim_text=clean_text(data.get("claim_text")) or None,
                    claim_order=int(to_float(data.get("claim_order")) or 0) or None,
                    source_channel=clean_text(data.get("source_channel")) or None,
                    observed_at=clean_text(data.get("observed_at")) or None,
                )
            )
        elif source_file.file_type == "sku_comment":
            db.add(
                RawSkuComment(
                    **common,
                    sku_code=clean_text(data.get("sku_code")) or None,
                    platform=clean_text(data.get("platform")) or None,
                    comment_id=clean_text(data.get("comment_id")) or None,
                    comment_text=clean_text(data.get("comment_text")) or None,
                    rating=to_float(data.get("rating")),
                    comment_time=clean_text(data.get("comment_time")) or None,
                    dimension_1=clean_text(data.get("dimension_1")) or None,
                    dimension_2=clean_text(data.get("dimension_2")) or None,
                    dimension_3=clean_text(data.get("dimension_3")) or None,
                )
            )
        elif source_file.file_type == "market_fact":
            db.add(
                RawMarketFact(
                    **common,
                    sku_code=clean_text(data.get("sku_code")) or None,
                    period=clean_text(data.get("period")) or None,
                    period_type=clean_text(data.get("period_type")) or None,
                    channel_group=clean_text(data.get("channel_group")) or None,
                    channel_type=clean_text(data.get("channel_type")) or None,
                    channel_name=clean_text(data.get("channel_name")) or None,
                    sales_volume=_parse_market_number(
                        db,
                        project_id=project.project_id,
                        category_code=project.category_code,
                        source_file_id=source_file.source_file_id,
                        import_batch_id=batch.import_batch_id,
                        raw_row_id=raw_row_id,
                        field_name="sales_volume",
                        value=data.get("sales_volume"),
                    ),
                    sales_amount=_parse_market_number(
                        db,
                        project_id=project.project_id,
                        category_code=project.category_code,
                        source_file_id=source_file.source_file_id,
                        import_batch_id=batch.import_batch_id,
                        raw_row_id=raw_row_id,
                        field_name="sales_amount",
                        value=data.get("sales_amount"),
                    ),
                    avg_price=_parse_market_number(
                        db,
                        project_id=project.project_id,
                        category_code=project.category_code,
                        source_file_id=source_file.source_file_id,
                        import_batch_id=batch.import_batch_id,
                        raw_row_id=raw_row_id,
                        field_name="avg_price",
                        value=data.get("avg_price"),
                    ),
                    promotion_flag=to_bool(data.get("promotion_flag")),
                )
            )

    batch.row_count = len(frame)
    batch.error_count = error_count
    batch.status = "completed"
    source_file.status = "imported"
    source_file.row_count = len(frame)
    _flag_duplicate_skus(db, project.project_id, project.category_code, source_file, batch)
    db.commit()
    db.refresh(batch)
    return batch


def import_from_path(
    db: Session,
    *,
    project_id: str,
    file_path: str,
    file_type: str | None = None,
) -> ImportBatch:
    path = Path(file_path)
    if not path.is_absolute():
        path = get_settings().repo_root / file_path
    source = register_source_file(
        db,
        project_id=project_id,
        file_name=path.name,
        file_type=infer_file_type(path.name, file_type),
        storage_path=str(path),
    )
    return import_source_file(db, source)


def _flag_duplicate_skus(
    db: Session,
    project_id: str,
    category_code: str,
    source_file: SourceFile,
    batch: ImportBatch,
) -> None:
    if source_file.file_type != "sku_master":
        return
    duplicates = (
        db.execute(
            select(RawSkuMaster.sku_code, func.count(RawSkuMaster.id))
            .where(RawSkuMaster.project_id == project_id, RawSkuMaster.sku_code.is_not(None))
            .group_by(RawSkuMaster.sku_code, RawSkuMaster.brand, RawSkuMaster.model_name)
            .having(func.count(RawSkuMaster.id) > 1)
        )
        .all()
    )
    for sku_code, count in duplicates:
        _add_issue(
            db,
            project_id=project_id,
            category_code=category_code,
            source_file_id=source_file.source_file_id,
            import_batch_id=batch.import_batch_id,
            raw_row_id=None,
            table_name="raw_sku_master",
            field_name="sku_code",
            issue_code="duplicate_sku",
            severity="warning",
            message=f"SKU {sku_code} 存在重复主数据记录 {count} 条",
            evidence={"sku_code": sku_code, "count": count},
        )

