"""Build a complete generation request from one exact current published scope."""

from __future__ import annotations

from app.services.core3_real_data.analyst.competitor_profile_config import (
    build_production_materialization_config,
)
from app.services.core3_real_data.analyst.competitor_profile_generation_schemas import (
    CompetitorProfileGenerationRequest,
)
from app.services.core3_real_data.analyst.competitor_profile_input_provider import (
    CompetitorProfileInputProvider,
)


def build_production_generation_request(
    *,
    provider: CompetitorProfileInputProvider,
    profile_version: str,
    generated_by: str,
) -> CompetitorProfileGenerationRequest:
    input_request = provider.build_production_input_request()
    category_bundle = provider.load_category_input_bundle(input_request)
    return CompetitorProfileGenerationRequest(
        input_request=input_request,
        profile_version=profile_version,
        config=build_production_materialization_config(category_bundle),
        generated_by=generated_by,
    )


__all__ = ["build_production_generation_request"]
