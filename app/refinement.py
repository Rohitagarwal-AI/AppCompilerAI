"""Stage 4: deterministic cross-layer refinement before validation."""

from __future__ import annotations

from copy import deepcopy
from typing import Dict


def refine_config(config: Dict, intent: Dict, design: Dict) -> Dict:
    refined = deepcopy(config)
    actions = []

    feature_set = set(design.get("features", []))
    table_names = {table["name"] for table in refined["database"]["tables"]}
    endpoint_ids = {endpoint["id"] for endpoint in refined["api"]["endpoints"]}

    if "premium_gating" in feature_set:
        billing_route = any(page["route"] == "/billing" for page in refined["ui"]["pages"])
        if not billing_route:
            refined["ui"]["pages"].append(
                {
                    "id": "billing",
                    "title": "Billing",
                    "route": "/billing",
                    "layout": "billing_console",
                    "components": [{"id": "billing_plan_picker", "type": "plan_picker", "dataSource": "get_plans"}],
                    "requiredApis": ["get_plans", "start_checkout"],
                }
            )
            actions.append("Added billing page because premium gating was requested.")
        for needed in ["subscriptions", "payments"]:
            if needed not in table_names:
                actions.append(f"Marked {needed} as required by premium gating.")
        for needed_endpoint in ["get_plans", "start_checkout"]:
            if needed_endpoint not in endpoint_ids:
                actions.append(f"Marked {needed_endpoint} endpoint as required by premium gating.")

    if intent.get("conflicts"):
        refined.setdefault("quality", {})
        refined["quality"]["conflictPolicy"] = "compiled_with_safe_defaults_and_clarification_questions"
        actions.append("Captured conflicts in quality metadata so reviewers can inspect the decision.")

    refined["refinement"] = {
        "status": "completed",
        "actions": actions,
        "policy": "minimal deterministic edits before schema validation",
    }
    return refined

