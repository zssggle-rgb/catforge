from __future__ import annotations

from app.services.core3_real_data.analyst.competitor_profile_config import (
    PRODUCTION_CONFIG_METHOD_VERSION,
    build_production_materialization_config,
)
from app.services.core3_real_data.analyst.competitor_profile_request_builder import (
    build_production_generation_request,
)
from tests.core3_real_data.test_competitor_profile_candidate_recall import (
    _category_bundle,
)


def test_production_config_is_deterministic_and_classifies_complete_coverage() -> None:
    bundle = _category_bundle()
    first = build_production_materialization_config(bundle)
    second = build_production_materialization_config(bundle.model_copy(deep=True))

    assert first == second
    assert first.config_version.startswith(PRODUCTION_CONFIG_METHOD_VERSION)
    assert first.product_category == "TV"
    assert first.purchase_pool.value_coverage_ratios
    assert list(first.purchase_pool.value_coverage_ratios) == sorted(
        first.purchase_pool.value_coverage_ratios
    )
    assert not (
        set(first.purchase_pool.generic_value_codes)
        & set(first.purchase_pool.discriminative_value_codes)
    )
    assert first.purchase_pool.value_coverage_ratios == (
        first.value_substitution.value_coverage_ratios
    )


def test_production_request_builder_uses_provider_snapshot_once() -> None:
    category = _category_bundle()

    class Provider:
        def __init__(self) -> None:
            self.request_calls = 0
            self.bundle_calls = 0

        def build_production_input_request(self):
            self.request_calls += 1
            from tests.core3_real_data.test_competitor_profile_generation import _request

            return _request(category).input_request

        def load_category_input_bundle(self, request):
            del request
            self.bundle_calls += 1
            return category

    provider = Provider()
    request = build_production_generation_request(
        provider=provider,  # type: ignore[arg-type]
        profile_version="competitor-profile-production-v1",
        generated_by="test",
    )

    assert provider.request_calls == 1
    assert provider.bundle_calls == 1
    assert request.input_request.category_code == "TV"
    assert request.config.product_category == "TV"
