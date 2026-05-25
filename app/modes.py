"""Deterministic cost/quality compiler mode profiles."""

from __future__ import annotations

from copy import deepcopy
from typing import Dict


COMPILER_MODES: Dict[str, Dict] = {
    "fast": {
        "id": "fast",
        "label": "Fast Mode",
        "validationDepth": "basic",
        "repairDepth": "local_reference_repairs",
        "smokeTestDepth": "core",
        "estimatedCost": "$0 local",
        "estimatedLatency": "lowest",
        "reliabilityScore": 78,
        "description": "Quick preview with required contracts, JSON safety, core references, and runtime smoke tests.",
    },
    "balanced": {
        "id": "balanced",
        "label": "Balanced Mode",
        "validationDepth": "standard",
        "repairDepth": "targeted_cross_layer_repairs",
        "smokeTestDepth": "standard",
        "estimatedCost": "$0 local",
        "estimatedLatency": "normal",
        "reliabilityScore": 90,
        "description": "Default mode for demos: field-level validation, targeted repair, SQLite execution, and bundle proof.",
    },
    "strict": {
        "id": "strict",
        "label": "Strict Mode",
        "validationDepth": "maximum",
        "repairDepth": "targeted_repairs_plus_deep_policy_checks",
        "smokeTestDepth": "extended",
        "estimatedCost": "$0 local",
        "estimatedLatency": "highest",
        "reliabilityScore": 97,
        "description": "Final-submission mode with deeper dashboard, payment, auth, and runtime consistency checks.",
    },
}


def normalize_mode(mode: str | None) -> str:
    value = (mode or "balanced").strip().lower()
    return value if value in COMPILER_MODES else "balanced"


def mode_profile(mode: str | None) -> Dict:
    return deepcopy(COMPILER_MODES[normalize_mode(mode)])
