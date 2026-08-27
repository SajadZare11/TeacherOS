from __future__ import annotations

import os
from collections.abc import Mapping


FEATURE_ENV_VARS: Mapping[str, str] = {
    "classes": "TEACHEROS_FEATURE_CLASSES",
    "continuity": "TEACHEROS_FEATURE_CONTINUITY",
    "evidence": "TEACHEROS_FEATURE_EVIDENCE",
    "differentiation": "TEACHEROS_FEATURE_DIFFERENTIATION",
    "reports": "TEACHEROS_FEATURE_REPORTS",
    "entitlements": "TEACHEROS_FEATURE_ENTITLEMENTS",
}

_DEPENDENCIES: Mapping[str, tuple[str, ...]] = {
    "classes": (),
    "continuity": ("classes",),
    "evidence": ("classes", "continuity"),
    "differentiation": ("classes", "continuity"),
    "reports": ("classes", "continuity", "evidence"),
    "entitlements": (),
}

_TRUE_VALUES = {"1", "true", "yes", "on", "enabled"}


def _validate_feature(feature: str) -> str:
    normalized = feature.strip().lower()
    if normalized not in FEATURE_ENV_VARS:
        raise ValueError(f"Unknown TeacherOS feature flag: {feature}")
    return normalized


def raw_feature_enabled(feature: str) -> bool:
    """Return the operator-controlled value without applying dependencies."""
    normalized = _validate_feature(feature)
    value = os.getenv(FEATURE_ENV_VARS[normalized], "false").strip().lower()
    return value in _TRUE_VALUES


def feature_enabled(feature: str) -> bool:
    """Return the effective value after fail-closed dependency checks."""
    normalized = _validate_feature(feature)
    return raw_feature_enabled(normalized) and all(
        raw_feature_enabled(dependency) for dependency in _DEPENDENCIES[normalized]
    )


def feature_flag_snapshot() -> dict[str, dict[str, bool]]:
    """Return non-secret flag state suitable for diagnostics."""
    return {
        feature: {
            "configured": raw_feature_enabled(feature),
            "effective": feature_enabled(feature),
        }
        for feature in FEATURE_ENV_VARS
    }


def quick_create_is_default() -> bool:
    """Quick Create remains the entry surface until Classes is enabled."""
    return not feature_enabled("classes")
