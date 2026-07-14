"""Resolve one competitor profile once and share it with every consumer."""

from __future__ import annotations

from app.services.core3_real_data.analyst.competitor_profile_consumption_schemas import (
    COMPETITOR_PROFILE_CONSUMERS,
    CompetitorProfileConsumptionContext,
)
from app.services.core3_real_data.analyst.competitor_profile_reader import (
    CompetitorProfileReader,
)
from app.services.core3_real_data.analyst.competitor_profile_reader_schemas import (
    CompetitorProfileReadRequest,
)


class CompetitorProfileConsumptionService:
    """Prevent agent, reports, QA, and sellpoint analysis from re-reading versions."""

    def __init__(self, reader: CompetitorProfileReader) -> None:
        self.reader = reader

    def load(
        self,
        request: CompetitorProfileReadRequest,
    ) -> CompetitorProfileConsumptionContext:
        result = self.reader.read(request)
        if result.status == "profile_unavailable":
            return CompetitorProfileConsumptionContext(
                status="profile_unavailable",
                preview=result.preview,
                message_cn=result.message_cn,
            )
        return CompetitorProfileConsumptionContext(
            status="available",
            competitor_profile_version_id=result.competitor_profile_version_id,
            preview=result.preview,
            consumers=list(COMPETITOR_PROFILE_CONSUMERS),
            business=result.business,
            evidence=result.evidence,
            message_cn=result.message_cn,
        )


__all__ = ["CompetitorProfileConsumptionService"]
