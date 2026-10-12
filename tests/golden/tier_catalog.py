"""Golden tier metadata shared by harness, metamorphic, and golden tests."""

from __future__ import annotations

ALL_GOLDEN_TIERS = (
    "gt1",
    "gt2",
    "gt3",
    "gt4",
    "gt5",
    "gt6",
    "gt7",
    "gt8",
    "gt9",
    "gt10",
)

RESUME_STAGE_BY_TIER: dict[str, str | None] = {
    "gt8": "tag_category",
}


def resume_stage_for_tier(tier: str) -> str | None:
    return RESUME_STAGE_BY_TIER.get(tier)
