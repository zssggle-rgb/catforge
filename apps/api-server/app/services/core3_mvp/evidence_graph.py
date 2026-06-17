from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import EvidenceItem


def get_or_create_evidence(
    db: Session,
    *,
    project_id: str,
    category_code: str,
    sku_code: str | None,
    source_type: str,
    source_file_id: str | None,
    raw_row_id: str | None,
    field_name: str | None,
    raw_value: str | None,
    normalized_value: dict | list | str | int | float | bool | None,
    source_ref: dict[str, Any] | list | None = None,
    confidence: float = 1.0,
) -> EvidenceItem:
    rows = db.execute(
        select(EvidenceItem).where(
            EvidenceItem.project_id == project_id,
            EvidenceItem.category_code == category_code,
            EvidenceItem.sku_code == sku_code,
            EvidenceItem.source_type == source_type,
            EvidenceItem.source_file_id == source_file_id,
            EvidenceItem.raw_row_id == raw_row_id,
            EvidenceItem.field_name == field_name,
            EvidenceItem.raw_value == raw_value,
        )
    ).scalars().all()
    for row in rows:
        if (row.source_ref or None) == (source_ref or None):
            return row

    evidence = EvidenceItem(
        project_id=project_id,
        category_code=category_code,
        sku_code=sku_code,
        source_type=source_type,
        source_file_id=source_file_id,
        raw_row_id=raw_row_id,
        field_name=field_name,
        raw_value=raw_value,
        normalized_value=normalized_value,
        source_ref=source_ref,
        confidence=confidence,
    )
    db.add(evidence)
    db.flush()
    return evidence
