"""Stage 2: turn intent into product architecture."""

from __future__ import annotations

from typing import Dict, List

from .utils import slugify, titleize, unique


def _entity_label(entity: str) -> str:
    return titleize(entity.replace("_", " "))


def _entity_page(entity: str) -> Dict:
    label = _entity_label(entity)
    return {
        "id": f"{slugify(entity)}_list",
        "title": label,
        "route": f"/{slugify(entity).replace('_', '-')}",
        "entity": slugify(entity),
        "layout": "data_workspace",
        "components": ["toolbar", "filter_bar", "data_table", "record_drawer"],
        "requiredApis": [f"list_{slugify(entity)}", f"create_{slugify(entity)}", f"update_{slugify(entity)}"],
    }


def design_system(intent: Dict) -> Dict:
    entities = unique(intent["entities"])
    roles = unique(intent["roles"])
    features = unique(intent["features"])

    if "dashboard" in features or "analytics" in features:
        home_components = ["metric_grid", "activity_feed", "chart_panel", "action_queue"]
    else:
        home_components = ["welcome_panel", "quick_actions", "recent_records"]

    pages = [
        {
            "id": "dashboard",
            "title": "Dashboard",
            "route": "/",
            "layout": "dashboard",
            "components": home_components,
            "requiredApis": ["get_dashboard_summary"],
        }
    ]
    pages.extend(_entity_page(entity) for entity in entities if entity not in ["roles"])

    if "payments" in features or "premium_gating" in features:
        pages.append(
            {
                "id": "billing",
                "title": "Billing",
                "route": "/billing",
                "layout": "billing_console",
                "components": ["plan_picker", "invoice_table", "payment_status"],
                "requiredApis": ["get_plans", "start_checkout", "list_payments"],
            }
        )
    if "auth" in features or roles:
        pages.append(
            {
                "id": "settings",
                "title": "Settings",
                "route": "/settings",
                "layout": "settings",
                "components": ["profile_form", "role_matrix", "audit_log"],
                "requiredApis": ["get_current_user", "update_current_user", "list_roles"],
            }
        )

    flows = [
        {
            "id": "record_crud",
            "name": "Record management",
            "steps": ["open list page", "filter records", "create or edit record", "validate", "persist"],
            "entities": entities,
        }
    ]
    if "premium_gating" in features:
        flows.append(
            {
                "id": "premium_upgrade",
                "name": "Premium upgrade",
                "steps": ["view locked feature", "choose plan", "checkout", "activate subscription", "unlock feature"],
                "entities": ["subscriptions", "payments"],
            }
        )
    if "rbac" in features or len(roles) > 1:
        flows.append(
            {
                "id": "role_based_access",
                "name": "Role-based access",
                "steps": ["authenticate", "load role", "authorize endpoint", "render permitted UI"],
                "entities": ["users", "roles"],
            }
        )

    assumptions: List[str] = []
    if intent["ambiguity"]["level"] != "low":
        assumptions.append("Ambiguous prompt compiled into a safe MVP with explicit assumptions instead of failing silently.")
    if "auth" not in features:
        assumptions.append("Auth was added as optional email login because generated apps usually need user ownership.")
        features.append("auth")
    if "dashboard" not in features:
        assumptions.append("A dashboard route was added as the default first screen.")
        features.append("dashboard")

    clarification_questions = []
    if intent["ambiguity"]["level"] == "high":
        clarification_questions.append("Who are the exact primary users and permission boundaries?")
    for conflict in intent["conflicts"]:
        clarification_questions.append(f"Please resolve: {conflict['message']}")

    return {
        "app": {
            "name": intent["appName"],
            "domain": intent["domains"][0],
            "summary": f"{titleize(intent['domains'][0])} generated from natural language through a compiler-style pipeline.",
        },
        "architecture": {
            "style": "modular_crud_saas",
            "frontend": "schema_driven_pages",
            "backend": "contract_first_rest_api",
            "database": "relational_with_foreign_keys",
            "auth": "role_based_session_auth",
        },
        "entities": entities,
        "roles": roles,
        "features": unique(features),
        "pages": pages,
        "flows": flows,
        "assumptions": assumptions,
        "clarificationQuestions": clarification_questions,
    }

