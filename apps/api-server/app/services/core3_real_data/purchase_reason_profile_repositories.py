"""M12D purchase reason profile repository boundaries."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Sequence

from pydantic import BaseModel
from sqlalchemy import select, update

from app.models import entities
from app.services.core3_real_data.constants import M12DReleaseStatus
from app.services.core3_real_data.purchase_reason_profile_schemas import M12DPublishedProfile, M12DWriteResult
from app.services.core3_real_data.repositories import Core3BaseRepository


class M12DVersionNotFoundError(RuntimeError):
    pass


class PurchaseReasonProfileRepository(Core3BaseRepository):
    def save_versions(self, records: Sequence[Any]) -> M12DWriteResult:
        return self._save_many(
            entities.Core3PurchaseReasonProfileVersion,
            records,
            unique_fields=("batch_id", "m12d_profile_version", "rule_version"),
        )

    def save_profiles(self, records: Sequence[Any]) -> M12DWriteResult:
        return self._save_many(
            entities.Core3SkuPurchaseReasonProfile,
            records,
            unique_fields=("batch_id", "m12d_profile_version", "sku_code", "rule_version"),
        )

    def save_anchors(self, records: Sequence[Any]) -> M12DWriteResult:
        return self._save_many(
            entities.Core3SkuPurchaseReasonAnchor,
            records,
            unique_fields=("batch_id", "m12d_profile_version", "sku_code", "anchor_code", "rule_version"),
        )

    def publish_version(
        self,
        *,
        batch_id: str,
        m12d_profile_version: str,
        rule_version: str,
        published_by: str = "system",
        release_note_cn: str | None = None,
    ) -> entities.Core3PurchaseReasonProfileVersion:
        version = self._find_version(
            batch_id=batch_id,
            m12d_profile_version=m12d_profile_version,
            rule_version=rule_version,
        )
        if version is None:
            raise M12DVersionNotFoundError(f"M12D profile version not found: {batch_id}/{m12d_profile_version}/{rule_version}")

        now = datetime.now(timezone.utc)
        self.db.execute(
            update(entities.Core3PurchaseReasonProfileVersion)
            .where(entities.Core3PurchaseReasonProfileVersion.project_id == self.project_id)
            .where(entities.Core3PurchaseReasonProfileVersion.category_code == self.category_code.value)
            .where(entities.Core3PurchaseReasonProfileVersion.batch_id == batch_id)
            .where(entities.Core3PurchaseReasonProfileVersion.purchase_reason_version_id != version.purchase_reason_version_id)
            .where(entities.Core3PurchaseReasonProfileVersion.is_current.is_(True))
            .values(is_current=False)
        )

        version.release_status = M12DReleaseStatus.PUBLISHED.value
        version.is_current = True
        version.published_at = now
        version.published_by = published_by
        if release_note_cn is not None:
            version.release_note_cn = release_note_cn

        release_filter = {
            "project_id": self.project_id,
            "category_code": self.category_code.value,
            "batch_id": batch_id,
            "m12d_profile_version": m12d_profile_version,
            "rule_version": rule_version,
        }
        for model_cls in (entities.Core3SkuPurchaseReasonProfile, entities.Core3SkuPurchaseReasonAnchor):
            stmt = update(model_cls)
            for field_name, value in release_filter.items():
                stmt = stmt.where(getattr(model_cls, field_name) == value)
            self.db.execute(stmt.values(release_status=M12DReleaseStatus.PUBLISHED.value, is_current=True))

        self.db.flush()
        return version

    def get_published_profile(
        self,
        *,
        batch_id: str,
        sku_code: str,
        m12d_profile_version: str | None = None,
    ) -> M12DPublishedProfile | None:
        version = self._find_published_version(batch_id=batch_id, m12d_profile_version=m12d_profile_version)
        if version is None:
            return None
        profile_stmt = (
            select(entities.Core3SkuPurchaseReasonProfile)
            .where(entities.Core3SkuPurchaseReasonProfile.project_id == self.project_id)
            .where(entities.Core3SkuPurchaseReasonProfile.category_code == self.category_code.value)
            .where(entities.Core3SkuPurchaseReasonProfile.batch_id == batch_id)
            .where(entities.Core3SkuPurchaseReasonProfile.m12d_profile_version == version.m12d_profile_version)
            .where(entities.Core3SkuPurchaseReasonProfile.rule_version == version.rule_version)
            .where(entities.Core3SkuPurchaseReasonProfile.sku_code == sku_code)
            .where(entities.Core3SkuPurchaseReasonProfile.release_status == M12DReleaseStatus.PUBLISHED.value)
            .where(entities.Core3SkuPurchaseReasonProfile.is_current.is_(True))
        )
        profile = self.db.execute(profile_stmt).scalars().first()
        if profile is None:
            return None
        anchors = self.list_published_anchors(profile.purchase_reason_profile_id)
        return M12DPublishedProfile(version=version, profile=profile, anchors=tuple(anchors))

    def list_published_anchors(self, purchase_reason_profile_id: str) -> list[entities.Core3SkuPurchaseReasonAnchor]:
        stmt = (
            select(entities.Core3SkuPurchaseReasonAnchor)
            .where(entities.Core3SkuPurchaseReasonAnchor.project_id == self.project_id)
            .where(entities.Core3SkuPurchaseReasonAnchor.category_code == self.category_code.value)
            .where(entities.Core3SkuPurchaseReasonAnchor.purchase_reason_profile_id == purchase_reason_profile_id)
            .where(entities.Core3SkuPurchaseReasonAnchor.release_status == M12DReleaseStatus.PUBLISHED.value)
            .where(entities.Core3SkuPurchaseReasonAnchor.is_current.is_(True))
            .order_by(entities.Core3SkuPurchaseReasonAnchor.anchor_rank, entities.Core3SkuPurchaseReasonAnchor.anchor_code)
        )
        return list(self.db.execute(stmt).scalars())

    def _find_version(
        self,
        *,
        batch_id: str,
        m12d_profile_version: str,
        rule_version: str,
    ) -> entities.Core3PurchaseReasonProfileVersion | None:
        stmt = (
            select(entities.Core3PurchaseReasonProfileVersion)
            .where(entities.Core3PurchaseReasonProfileVersion.project_id == self.project_id)
            .where(entities.Core3PurchaseReasonProfileVersion.category_code == self.category_code.value)
            .where(entities.Core3PurchaseReasonProfileVersion.batch_id == batch_id)
            .where(entities.Core3PurchaseReasonProfileVersion.m12d_profile_version == m12d_profile_version)
            .where(entities.Core3PurchaseReasonProfileVersion.rule_version == rule_version)
        )
        return self.db.execute(stmt).scalars().first()

    def _find_published_version(
        self,
        *,
        batch_id: str,
        m12d_profile_version: str | None,
    ) -> entities.Core3PurchaseReasonProfileVersion | None:
        stmt = (
            select(entities.Core3PurchaseReasonProfileVersion)
            .where(entities.Core3PurchaseReasonProfileVersion.project_id == self.project_id)
            .where(entities.Core3PurchaseReasonProfileVersion.category_code == self.category_code.value)
            .where(entities.Core3PurchaseReasonProfileVersion.batch_id == batch_id)
            .where(entities.Core3PurchaseReasonProfileVersion.release_status == M12DReleaseStatus.PUBLISHED.value)
        )
        if m12d_profile_version is None:
            stmt = stmt.where(entities.Core3PurchaseReasonProfileVersion.is_current.is_(True))
        else:
            stmt = stmt.where(entities.Core3PurchaseReasonProfileVersion.m12d_profile_version == m12d_profile_version)
        return self.db.execute(stmt.order_by(entities.Core3PurchaseReasonProfileVersion.published_at.desc())).scalars().first()

    def _save_many(
        self,
        model_cls: Any,
        payloads: Sequence[Any],
        *,
        unique_fields: tuple[str, ...],
        hash_field: str = "result_hash",
    ) -> M12DWriteResult:
        records: list[Any] = []
        created_count = 0
        reused_count = 0
        updated_count = 0
        for payload in payloads:
            record, status = self._save_one(model_cls, payload, unique_fields=unique_fields, hash_field=hash_field)
            records.append(record)
            if status == "created":
                created_count += 1
            elif status == "updated":
                updated_count += 1
            else:
                reused_count += 1
        return M12DWriteResult(tuple(records), created_count, reused_count, updated_count)

    def _save_one(self, model_cls: Any, payload: Any, *, unique_fields: tuple[str, ...], hash_field: str) -> tuple[Any, str]:
        normalized_payload = self._normalize_payload(model_cls, payload)
        existing = self._find_by_unique(model_cls, normalized_payload, unique_fields)
        if existing is None:
            record = model_cls(**_jsonable_payload(normalized_payload))
            self.db.add(record)
            self.db.flush()
            return record, "created"
        if normalized_payload.get(hash_field) == getattr(existing, hash_field):
            _refresh_existing(existing, normalized_payload)
            self.db.flush()
            return existing, "reused"
        _refresh_existing(existing, normalized_payload)
        self.db.flush()
        return existing, "updated"

    def _normalize_payload(self, model_cls: Any, payload: Any) -> dict[str, Any]:
        if isinstance(payload, BaseModel):
            raw_payload = payload.model_dump(mode="python")
        elif isinstance(payload, Mapping):
            raw_payload = dict(payload)
        else:
            raise TypeError("M12D repository payload must be a mapping or Pydantic model")
        raw_payload.setdefault("project_id", self.project_id)
        raw_payload.setdefault("category_code", self.category_code.value)
        model_fields = set(model_cls.__table__.columns.keys())
        result = {key: value for key, value in raw_payload.items() if key in model_fields}
        for audit_field in ("created_at", "updated_at", "generated_at"):
            if result.get(audit_field) is None:
                result.pop(audit_field, None)
        return result

    def _find_by_unique(self, model_cls: Any, payload: Mapping[str, Any], unique_fields: tuple[str, ...]) -> Any | None:
        stmt = (
            select(model_cls)
            .where(model_cls.project_id == self.project_id)
            .where(model_cls.category_code == self.category_code.value)
        )
        for field_name in unique_fields:
            value = payload.get(field_name)
            if value is None:
                raise ValueError(f"{model_cls.__tablename__}.{field_name} is required")
            stmt = stmt.where(getattr(model_cls, field_name) == value)
        return self.db.execute(stmt).scalars().first()


def _jsonable_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {key: _jsonable_value(value, nested=False) for key, value in payload.items()}


def _jsonable_value(value: Any, *, nested: bool = True) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return float(value) if nested else value
    if isinstance(value, dict):
        return {str(key): _jsonable_value(item, nested=True) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable_value(item, nested=True) for item in value]
    if isinstance(value, tuple):
        return [_jsonable_value(item, nested=True) for item in value]
    return value


def _refresh_existing(existing: Any, payload: Mapping[str, Any]) -> None:
    primary_keys = {column.name for column in existing.__table__.primary_key.columns}
    for field_name, value in _jsonable_payload(payload).items():
        if field_name in primary_keys or field_name == "created_at":
            continue
        setattr(existing, field_name, value)
