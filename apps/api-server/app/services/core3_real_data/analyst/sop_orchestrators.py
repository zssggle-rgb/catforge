"""SOP orchestrator placeholders for CatForge analyst."""

from __future__ import annotations

from typing import Any

from app.services.core3_real_data.analyst.analyst_schemas import AnalystContext, AnalystStatus, base_result


SOP_STEP_MAP: dict[str, tuple[str, ...]] = {
    "competitor-set": (
        "resolve-sku",
        "sku-fact-brief",
        "same-size-price-candidates",
        "semantic-overlap",
        "param-claim-overlap",
        "sales-overlap",
    ),
    "why-sales-diff": (
        "resolve-sku",
        "sales-overlap",
        "semantic-overlap",
        "param-claim-overlap",
        "comment-support",
    ),
    "premium-claim-drivers": (
        "sku-fact-brief",
        "comment-support",
        "semantic-dimension-space",
    ),
    "battlefield-space": ("semantic-dimension-space",),
    "battlefield-opportunity": (
        "sku-fact-brief",
        "opportunity-gaps",
        "semantic-dimension-space",
    ),
    "sku-business-brief": (
        "resolve-sku",
        "sku-fact-brief",
        "same-size-price-candidates",
        "semantic-dimension-space",
    ),
}


class SopOrchestrators:
    def planned_sop(self, context: AnalystContext, *, command: str, **_: Any) -> dict[str, Any]:
        steps = [
            {"step_code": step, "status": "planned", "description_cn": "后续实现时由 catforge_analyst 原子能力执行。"}
            for step in SOP_STEP_MAP.get(command, ())
        ]
        return base_result(
            status=AnalystStatus.NOT_IMPLEMENTED,
            command=command,
            context=context,
            sop_steps=steps,
            atoms_used=[{"ability_code": step["step_code"], "status": "planned"} for step in steps],
            limitations=["该 SOP 编排入口已创建，具体原子能力编排将在后续步骤实现。"],
            message_cn=f"{command} SOP 编排尚未实现。",
        )
