"""M16 fixed dependency graph for Core3 real-data v2."""

from __future__ import annotations

from app.services.core3_real_data.constants import Core3ModuleCode, Core3RunStatus


CORE3_PIPELINE_MODULE_ORDER: tuple[Core3ModuleCode, ...] = (
    Core3ModuleCode.M00,
    Core3ModuleCode.M01,
    Core3ModuleCode.M02,
    Core3ModuleCode.M03,
    Core3ModuleCode.M03B,
    Core3ModuleCode.M04A,
    Core3ModuleCode.M05,
    Core3ModuleCode.M06,
    Core3ModuleCode.M04B,
    Core3ModuleCode.M07,
    Core3ModuleCode.M08,
    Core3ModuleCode.M08_4,
    Core3ModuleCode.M08_5,
    Core3ModuleCode.M09,
    Core3ModuleCode.M10,
    Core3ModuleCode.M11,
    Core3ModuleCode.M11_5,
    Core3ModuleCode.M11_6,
    Core3ModuleCode.M11_7,
    Core3ModuleCode.M12C,
    Core3ModuleCode.M12,
    Core3ModuleCode.M13,
    Core3ModuleCode.M14,
    Core3ModuleCode.M15,
    Core3ModuleCode.M16,
)

CORE3_PIPELINE_REQUIRED_UPSTREAMS: dict[Core3ModuleCode, tuple[Core3ModuleCode, ...]] = {
    Core3ModuleCode.M00: (),
    Core3ModuleCode.M01: (Core3ModuleCode.M00,),
    Core3ModuleCode.M02: (Core3ModuleCode.M01,),
    Core3ModuleCode.M03: (Core3ModuleCode.M02,),
    Core3ModuleCode.M03B: (Core3ModuleCode.M02,),
    Core3ModuleCode.M04A: (Core3ModuleCode.M02, Core3ModuleCode.M03, Core3ModuleCode.M03B),
    Core3ModuleCode.M05: (Core3ModuleCode.M02,),
    Core3ModuleCode.M06: (Core3ModuleCode.M05,),
    Core3ModuleCode.M04B: (Core3ModuleCode.M03, Core3ModuleCode.M03B, Core3ModuleCode.M04A, Core3ModuleCode.M05, Core3ModuleCode.M06),
    Core3ModuleCode.M07: (Core3ModuleCode.M02,),
    Core3ModuleCode.M08: (Core3ModuleCode.M03, Core3ModuleCode.M03B, Core3ModuleCode.M04A, Core3ModuleCode.M04B, Core3ModuleCode.M06, Core3ModuleCode.M07),
    Core3ModuleCode.M08_4: (Core3ModuleCode.M08,),
    Core3ModuleCode.M08_5: (Core3ModuleCode.M08_4,),
    Core3ModuleCode.M09: (Core3ModuleCode.M04A, Core3ModuleCode.M04B, Core3ModuleCode.M05, Core3ModuleCode.M07, Core3ModuleCode.M08, Core3ModuleCode.M08_5),
    Core3ModuleCode.M10: (Core3ModuleCode.M04A, Core3ModuleCode.M04B, Core3ModuleCode.M05, Core3ModuleCode.M07, Core3ModuleCode.M08, Core3ModuleCode.M08_5),
    Core3ModuleCode.M11: (Core3ModuleCode.M08, Core3ModuleCode.M08_5, Core3ModuleCode.M09, Core3ModuleCode.M10),
    Core3ModuleCode.M11_5: (Core3ModuleCode.M04A, Core3ModuleCode.M04B, Core3ModuleCode.M11),
    Core3ModuleCode.M11_6: (Core3ModuleCode.M07, Core3ModuleCode.M08, Core3ModuleCode.M09, Core3ModuleCode.M10, Core3ModuleCode.M11, Core3ModuleCode.M11_5),
    Core3ModuleCode.M11_7: (Core3ModuleCode.M07, Core3ModuleCode.M08, Core3ModuleCode.M11_6),
    Core3ModuleCode.M12C: (Core3ModuleCode.M03B, Core3ModuleCode.M04C, Core3ModuleCode.M05C, Core3ModuleCode.M07, Core3ModuleCode.M09C, Core3ModuleCode.M10C, Core3ModuleCode.M11C, Core3ModuleCode.M11D),
    Core3ModuleCode.M12: (Core3ModuleCode.M11_7, Core3ModuleCode.M12C),
    Core3ModuleCode.M13: (Core3ModuleCode.M07, Core3ModuleCode.M08, Core3ModuleCode.M09, Core3ModuleCode.M10, Core3ModuleCode.M11, Core3ModuleCode.M11_5, Core3ModuleCode.M11_6, Core3ModuleCode.M11_7, Core3ModuleCode.M12C, Core3ModuleCode.M12),
    Core3ModuleCode.M14: (Core3ModuleCode.M12, Core3ModuleCode.M13),
    Core3ModuleCode.M15: (Core3ModuleCode.M02, Core3ModuleCode.M03B, Core3ModuleCode.M08, Core3ModuleCode.M09, Core3ModuleCode.M10, Core3ModuleCode.M11, Core3ModuleCode.M11_5, Core3ModuleCode.M11_6, Core3ModuleCode.M11_7, Core3ModuleCode.M12C, Core3ModuleCode.M12, Core3ModuleCode.M13, Core3ModuleCode.M14),
    Core3ModuleCode.M16: tuple(code for code in CORE3_PIPELINE_MODULE_ORDER if code != Core3ModuleCode.M16),
}

_BLOCKING_STATUSES = {
    Core3RunStatus.BLOCKED.value,
    Core3RunStatus.FAILED.value,
    Core3RunStatus.SKIPPED_BY_DEPENDENCY.value,
}


class PipelineDependencyGraph:
    def topological_order(self) -> tuple[Core3ModuleCode, ...]:
        return CORE3_PIPELINE_MODULE_ORDER

    def required_upstreams(self, module_code: Core3ModuleCode | str) -> tuple[Core3ModuleCode, ...]:
        return CORE3_PIPELINE_REQUIRED_UPSTREAMS[Core3ModuleCode(module_code)]

    def downstream_modules(self, module_code: Core3ModuleCode | str) -> tuple[Core3ModuleCode, ...]:
        normalized = Core3ModuleCode(module_code)
        return tuple(
            candidate
            for candidate, upstreams in CORE3_PIPELINE_REQUIRED_UPSTREAMS.items()
            if normalized in upstreams
        )

    def must_block_downstream(self, status: Core3RunStatus | str) -> bool:
        return str(status) in _BLOCKING_STATUSES
