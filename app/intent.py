"""Stage 1: convert open-ended user text into structured intent."""

from __future__ import annotations

import re
from typing import Dict, List

from .catalog import (
    CONFLICT_PATTERNS,
    ENTITY_PATTERNS,
    FEATURE_PATTERNS,
    PRODUCT_PATTERNS,
    ROLE_PATTERNS,
    VAGUE_TERMS,
)
from .utils import stable_id, titleize, unique


def _contains_any(text: str, patterns: List[str]) -> bool:
    return any(pattern in text for pattern in patterns)


def _matches(text: str, catalog: Dict[str, List[str]]) -> List[str]:
    output = []
    for key, patterns in catalog.items():
        if _contains_any(text, patterns):
            output.append(key)
    return unique(output)


def _extract_named_app(prompt: str, domains: List[str]) -> str:
    clean = re.sub(r"\s+", " ", prompt.strip())
    if not clean:
        return "Generated App"
    if domains:
        return titleize(domains[0].replace("_", " "))
    first_words = clean.split(" ")[:4]
    return " ".join(word.capitalize() for word in first_words if word)


def extract_intent(prompt: str) -> Dict:
    normalized = re.sub(r"\s+", " ", prompt.lower()).strip()
    domains = _matches(normalized, PRODUCT_PATTERNS)
    features = _matches(normalized, FEATURE_PATTERNS)
    entities = _matches(normalized, ENTITY_PATTERNS)
    roles = _matches(normalized, ROLE_PATTERNS)

    if "admin" in normalized and "auth" not in features:
        features.append("auth")
    if "premium" in normalized and "payments" not in features:
        features.append("payments")
    if "premium_gating" in features and "subscriptions" not in entities:
        entities.append("subscriptions")
    if "payments" in features and "payments" not in entities:
        entities.append("payments")
    if not roles:
        roles = ["admin", "member"]
    elif "admin" not in roles and ("rbac" in features or "auth" in features):
        roles.insert(0, "admin")
    if "users" not in entities and ("auth" in features or roles):
        entities.insert(0, "users")
    if not entities:
        entities = ["users", "records"]
    if not domains:
        domains = ["custom_application"]

    conflicts = []
    for conflict_id, left_patterns, right_patterns in CONFLICT_PATTERNS:
        if _contains_any(normalized, left_patterns) and _contains_any(normalized, right_patterns):
            conflicts.append(
                {
                    "id": conflict_id,
                    "severity": "blocking",
                    "message": f"Prompt contains conflicting requirements for {conflict_id.replace('_', ' ')}.",
                }
            )

    vague_score = 0
    word_count = len(normalized.split())
    if word_count < 8:
        vague_score += 2
    if not any(domain != "custom_application" for domain in domains):
        vague_score += 2
    if len(entities) <= 2 and any(term in normalized.split() for term in VAGUE_TERMS):
        vague_score += 1

    missing = []
    if "auth" not in features:
        missing.append("auth model")
    if len(entities) <= 2:
        missing.append("core data model")
    if "dashboard" not in features:
        missing.append("primary landing/dashboard experience")
    if "payments" in features and "subscriptions" not in entities:
        missing.append("subscription lifecycle")

    intent = {
        "id": stable_id("intent", normalized or "empty"),
        "rawPrompt": prompt,
        "normalizedPrompt": normalized,
        "appName": _extract_named_app(prompt, domains),
        "domains": domains,
        "features": unique(features),
        "entities": unique(entities),
        "roles": unique(roles),
        "constraints": {
            "determinism": "stable rule ordering and sorted output",
            "outputMode": "strict_json",
            "requiresExecutionProof": True,
        },
        "ambiguity": {
            "score": vague_score,
            "level": "high" if vague_score >= 4 else "medium" if vague_score >= 2 else "low",
            "missingSignals": missing,
        },
        "conflicts": conflicts,
    }
    return intent
