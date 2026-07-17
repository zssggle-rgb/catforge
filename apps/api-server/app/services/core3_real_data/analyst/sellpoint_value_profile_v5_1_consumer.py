"""Strict read boundary for downstream consumers of saved V5.1 profiles.

The reader resolves one immutable profile and delegates full graph validation to
``SellpointValueV51Repository``.  It never recalls candidates or recalculates an
analytical result.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import Field, model_validator
from sqlalchemy import select

from app.models import entities
from app.services.core3_real_data.analyst.sellpoint_value_profile_schemas import (
    SellpointValueProfileBaseModel,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_materializer_schemas import (
    SellpointValueV51Readback,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_repository import (
    SellpointValueV51Repository,
)
from app.services.core3_real_data.analyst.sellpoint_value_profile_v5_1_schemas import (
    SPV_V5_1_METHOD_VERSION,
    SPV_V5_1_RULE_VERSION,
    SPV_V5_1_SCHEMA_VERSION,
)


class SellpointValueV51ConsumerIntegrityError(RuntimeError):
    """Raised when a saved V5.1 consumer scope is internally inconsistent."""


class SellpointValueV51ConsumerReadRequest(SellpointValueProfileBaseModel):
    project_id: str = Field(min_length=1)
    category_code: Literal["TV", "AC"]
    batch_id: str = Field(min_length=1)
    access_mode: Literal["formal", "preview"] = "formal"
    sku_code: str | None = Field(default=None, min_length=1)
    model_name: str | None = Field(default=None, min_length=1)
    query: str | None = Field(default=None, min_length=1)
    profile_version: str | None = Field(default=None, min_length=1)
    sellpoint_value_profile_version_id: str | None = Field(
        default=None,
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_selector(self) -> "SellpointValueV51ConsumerReadRequest":
        if not any((self.sku_code, self.model_name, self.query)):
            raise ValueError("V5.1 consumer reads require a target selector")
        version_selectors = (
            self.profile_version,
            self.sellpoint_value_profile_version_id,
        )
        if self.access_mode == "formal" and any(version_selectors):
            raise ValueError("formal V5.1 reads cannot select a version")
        if self.access_mode == "preview" and not all(version_selectors):
            raise ValueError(
                "preview V5.1 reads require profile_version and version id"
            )
        return self


class SellpointValueV51ConsumerReadResult(SellpointValueProfileBaseModel):
    status: Literal["available", "profile_unavailable", "ambiguous"]
    access_mode: Literal["formal", "preview"]
    readback: SellpointValueV51Readback | None = None
    candidates: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result(self) -> "SellpointValueV51ConsumerReadResult":
        if self.status == "available":
            if self.readback is None or self.candidates:
                raise ValueError("available V5.1 reads require one readback")
        elif self.readback is not None:
            raise ValueError("unavailable V5.1 reads cannot expose a readback")
        if self.status == "ambiguous" and len(self.candidates) < 2:
            raise ValueError("ambiguous V5.1 reads require multiple targets")
        if self.status == "profile_unavailable" and self.candidates:
            raise ValueError("unavailable V5.1 reads cannot expose candidates")
        return self


class SellpointValueV51ConsumerReader:
    """Read only current published V5.1 or one explicitly locked preview."""

    def __init__(self, repository: SellpointValueV51Repository) -> None:
        self.repository = repository

    def read(
        self,
        request: SellpointValueV51ConsumerReadRequest,
    ) -> SellpointValueV51ConsumerReadResult:
        request = SellpointValueV51ConsumerReadRequest.model_validate(
            request.model_dump(mode="python")
        )
        self._assert_repository_scope(request)
        version = self._resolve_version(request)
        if version is None:
            return SellpointValueV51ConsumerReadResult(
                status="profile_unavailable",
                access_mode=request.access_mode,
            )
        rows = list(
            self.repository.db.execute(
                select(entities.Core3SkuSellpointValueProfile)
                .where(
                    entities.Core3SkuSellpointValueProfile.sellpoint_value_profile_version_id
                    == version.sellpoint_value_profile_version_id
                )
                .order_by(entities.Core3SkuSellpointValueProfile.sku_code)
            ).scalars()
        )
        matches = [row for row in rows if _matches_target(row, request)]
        if not matches:
            return SellpointValueV51ConsumerReadResult(
                status="profile_unavailable",
                access_mode=request.access_mode,
            )
        if len(matches) > 1:
            return SellpointValueV51ConsumerReadResult(
                status="ambiguous",
                access_mode=request.access_mode,
                candidates=[_target_ref(row) for row in matches],
            )
        row = matches[0]
        readback = self.repository.get_v5_1_profile(
            batch_id=request.batch_id,
            profile_version=version.profile_version,
            sku_code=row.sku_code,
        )
        if readback is None:
            raise SellpointValueV51ConsumerIntegrityError(
                "V5.1 profile index has no typed readback"
            )
        self._assert_readback(version, readback, request)
        return SellpointValueV51ConsumerReadResult(
            status="available",
            access_mode=request.access_mode,
            readback=readback,
        )

    def _assert_repository_scope(
        self,
        request: SellpointValueV51ConsumerReadRequest,
    ) -> None:
        repository_category = _enum_value(self.repository.category_code)
        if request.project_id != self.repository.project_id:
            raise ValueError("V5.1 consumer project does not match repository")
        if request.category_code != repository_category:
            raise ValueError("V5.1 consumer category does not match repository")

    def _resolve_version(
        self,
        request: SellpointValueV51ConsumerReadRequest,
    ) -> entities.Core3SellpointValueProfileVersion | None:
        stmt = (
            select(entities.Core3SellpointValueProfileVersion)
            .where(
                entities.Core3SellpointValueProfileVersion.project_id
                == request.project_id
            )
            .where(
                entities.Core3SellpointValueProfileVersion.category_code
                == request.category_code
            )
            .where(
                entities.Core3SellpointValueProfileVersion.batch_id == request.batch_id
            )
            .where(
                entities.Core3SellpointValueProfileVersion.schema_version
                == SPV_V5_1_SCHEMA_VERSION
            )
            .where(
                entities.Core3SellpointValueProfileVersion.rule_version
                == SPV_V5_1_RULE_VERSION
            )
            .where(
                entities.Core3SellpointValueProfileVersion.method_version
                == SPV_V5_1_METHOD_VERSION
            )
        )
        if request.access_mode == "formal":
            stmt = stmt.where(
                entities.Core3SellpointValueProfileVersion.release_status
                == "published",
                entities.Core3SellpointValueProfileVersion.is_current.is_(True),
            )
        else:
            stmt = stmt.where(
                entities.Core3SellpointValueProfileVersion.sellpoint_value_profile_version_id
                == request.sellpoint_value_profile_version_id,
                entities.Core3SellpointValueProfileVersion.profile_version
                == request.profile_version,
            )
        versions = list(self.repository.db.execute(stmt).scalars())
        if len(versions) > 1:
            raise SellpointValueV51ConsumerIntegrityError(
                "multiple V5.1 versions occupy one consumer scope"
            )
        if not versions:
            return None
        version = versions[0]
        if request.access_mode == "preview" and not (
            (version.release_status == "draft" and not version.is_current)
            or (version.release_status == "published" and version.is_current)
        ):
            raise SellpointValueV51ConsumerIntegrityError(
                "preview V5.1 version is not an allowed immutable state"
            )
        return version

    @staticmethod
    def _assert_readback(
        version: entities.Core3SellpointValueProfileVersion,
        readback: SellpointValueV51Readback,
        request: SellpointValueV51ConsumerReadRequest,
    ) -> None:
        persisted = readback.persisted.version
        if (
            persisted.sellpoint_value_profile_version_id
            != version.sellpoint_value_profile_version_id
            or readback.profile.profile_version != version.profile_version
            or persisted.result_hash != version.result_hash
            or readback.profile.project_id != request.project_id
            or readback.profile.category_code != request.category_code
            or readback.profile.batch_id != request.batch_id
        ):
            raise SellpointValueV51ConsumerIntegrityError(
                "V5.1 typed readback crossed its locked version scope"
            )
        if request.access_mode == "formal" and (
            persisted.release_status != "published" or not persisted.is_current
        ):
            raise SellpointValueV51ConsumerIntegrityError(
                "formal V5.1 readback is not current published"
            )
        if request.access_mode == "preview" and (
            persisted.sellpoint_value_profile_version_id
            != request.sellpoint_value_profile_version_id
            or persisted.profile_version != request.profile_version
        ):
            raise SellpointValueV51ConsumerIntegrityError(
                "preview V5.1 readback differs from the explicit lock"
            )


def _matches_target(
    row: entities.Core3SkuSellpointValueProfile,
    request: SellpointValueV51ConsumerReadRequest,
) -> bool:
    if request.sku_code and row.sku_code.casefold() != request.sku_code.casefold():
        return False
    if request.model_name and (
        not row.model_name or row.model_name.casefold() != request.model_name.casefold()
    ):
        return False
    if request.query:
        query = request.query.casefold()
        values = (
            row.sku_code,
            row.model_code,
            row.model_name,
            row.brand_name,
            row.display_name_cn,
        )
        if not any(query in str(value).casefold() for value in values if value):
            return False
    return True


def _target_ref(row: entities.Core3SkuSellpointValueProfile) -> dict[str, Any]:
    return {
        "sku_code": row.sku_code,
        "brand_name": row.brand_name,
        "model_name": row.model_name,
        "display_name_cn": row.display_name_cn,
        "profile_version": row.profile_version,
        "result_hash": row.result_hash,
    }


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


__all__ = [
    "SellpointValueV51ConsumerIntegrityError",
    "SellpointValueV51ConsumerReadRequest",
    "SellpointValueV51ConsumerReadResult",
    "SellpointValueV51ConsumerReader",
]
