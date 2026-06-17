from importlib import import_module


CORE3_REAL_DATA_MODULES = [
    "app.services.core3_real_data",
    "app.services.core3_real_data.constants",
    "app.services.core3_real_data.hash_utils",
    "app.services.core3_real_data.run_context",
    "app.services.core3_real_data.runner",
    "app.services.core3_real_data.repositories",
    "app.services.core3_real_data.fixtures",
    "app.services.core3_real_data.source_registry_repositories",
    "app.services.core3_real_data.source_registry_service",
    "app.services.core3_real_data.cleaning_normalizers",
    "app.services.core3_real_data.cleaning_schemas",
    "app.services.core3_real_data.evidence_atom_schemas",
    "app.services.core3_real_data.evidence_mappers",
    "app.services.core3_real_data.evidence_payloads",
    "app.services.core3_real_data.evidence_confidence",
    "app.services.core3_real_data.evidence_atom_repositories",
    "app.services.core3_real_data.evidence_links",
    "app.services.core3_real_data.evidence_atom_service",
    "app.services.core3_real_data.cleaning_repositories",
    "app.services.core3_real_data.cleaning_quality_service",
    "app.api.core3_real_data",
    "app.schemas.core3_real_data",
]


def test_core3_real_data_package_skeleton_imports():
    for module_name in CORE3_REAL_DATA_MODULES:
        module = import_module(module_name)
        assert module.__name__ == module_name
