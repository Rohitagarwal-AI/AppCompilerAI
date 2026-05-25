"""Stage 3: generate strict executable app configuration."""

from __future__ import annotations

from typing import Dict, List

from .catalog import DEFAULT_FIELDS
from .utils import slugify, titleize


TYPE_MAP = {
    "text": "string",
    "email": "string",
    "url": "string",
    "enum": "string",
    "money": "number",
    "number": "number",
    "date": "string",
    "datetime": "string",
    "json": "object",
}


def _field_from_spec(spec: str) -> Dict:
    parts = spec.split(":")
    name = slugify(parts[0])
    kind = parts[1] if len(parts) > 1 else "text"
    field = {
        "name": name,
        "type": TYPE_MAP.get(kind, "string"),
        "kind": kind,
        "required": name in ["name", "title", "email", "status"],
    }
    if len(parts) == 3 and parts[1] == "fk":
        field["type"] = "string"
        field["kind"] = "foreign_key"
        field["references"] = slugify(parts[2])
    if kind == "enum":
        field["values"] = ["new", "active", "archived"]
    if kind in ["date", "datetime"]:
        field["format"] = kind
    if kind == "email":
        field["format"] = "email"
    return field


def _table_for_entity(entity: str) -> Dict:
    entity = slugify(entity)
    specs = DEFAULT_FIELDS.get(entity, ["name:text", "status:enum", "owner_id:fk:users"])
    fields = [
        {"name": "id", "type": "string", "kind": "primary_key", "required": True},
        {"name": "created_at", "type": "string", "kind": "datetime", "format": "datetime", "required": True},
        {"name": "updated_at", "type": "string", "kind": "datetime", "format": "datetime", "required": True},
    ]
    existing = {field["name"] for field in fields}
    for spec in specs:
        field = _field_from_spec(spec)
        if field["name"] not in existing:
            fields.append(field)
            existing.add(field["name"])
    return {
        "name": entity,
        "label": titleize(entity),
        "primaryKey": "id",
        "fields": fields,
        "indexes": ["id", "created_at"],
    }


def _schema_fields_for_table(table: Dict, partial: bool = False) -> List[Dict]:
    fields = []
    for field in table.get("fields", []):
        if field.get("kind") == "primary_key":
            continue
        schema_field = {
            "name": field["name"],
            "type": field.get("type", "string"),
            "required": bool(field.get("required") and not partial),
        }
        if field.get("format"):
            schema_field["format"] = field["format"]
        if field.get("values"):
            schema_field["values"] = list(field["values"])
        if field.get("references"):
            schema_field["references"] = field["references"]
        fields.append(schema_field)
    return fields


def _field_names_for_table(table: Dict, include_system: bool = False) -> List[str]:
    system_fields = {"id", "created_at", "updated_at"}
    return [
        field["name"]
        for field in table.get("fields", [])
        if include_system or field.get("name") not in system_fields
    ]


def _request_schema(entity: str, table: Dict, partial: bool = False) -> Dict:
    return {
        "body": {
            "type": "object",
            "entity": slugify(entity),
            "partial": partial,
            "fields": _schema_fields_for_table(table, partial=partial),
        }
    }


def _response_schema(entity: str, table: Dict, response_type: str = "object") -> Dict:
    return {
        "type": response_type,
        "entity": slugify(entity),
        "fields": _schema_fields_for_table(table, partial=True),
    }


def _crud_endpoints(entity: str, table: Dict | None = None) -> List[Dict]:
    entity = slugify(entity)
    table = table or _table_for_entity(entity)
    path = f"/api/{entity.replace('_', '-')}"
    return [
        {
            "id": f"list_{entity}",
            "method": "GET",
            "path": path,
            "entity": entity,
            "auth": True,
            "response": _response_schema(entity, table, "array"),
        },
        {
            "id": f"create_{entity}",
            "method": "POST",
            "path": path,
            "entity": entity,
            "auth": True,
            "request": _request_schema(entity, table, partial=False),
            "response": _response_schema(entity, table, "object"),
        },
        {
            "id": f"get_{entity}",
            "method": "GET",
            "path": f"{path}/:id",
            "entity": entity,
            "auth": True,
            "response": _response_schema(entity, table, "object"),
        },
        {
            "id": f"update_{entity}",
            "method": "PATCH",
            "path": f"{path}/:id",
            "entity": entity,
            "auth": True,
            "request": _request_schema(entity, table, partial=True),
            "response": _response_schema(entity, table, "object"),
        },
        {
            "id": f"delete_{entity}",
            "method": "DELETE",
            "path": f"{path}/:id",
            "entity": entity,
            "auth": True,
            "response": {"type": "object", "fields": [{"name": "deleted", "type": "boolean", "required": True}]},
        },
    ]


def _system_endpoints(features: List[str]) -> List[Dict]:
    endpoints = [
        {
            "id": "get_dashboard_summary",
            "method": "GET",
            "path": "/api/dashboard/summary",
            "entity": "reports",
            "auth": True,
            "response": {
                "type": "object",
                "fields": [
                    {"name": "metrics", "type": "object", "required": True},
                    {"name": "recentActivity", "type": "object", "required": False},
                    {"name": "alerts", "type": "object", "required": False},
                ],
            },
        },
        {
            "id": "get_current_user",
            "method": "GET",
            "path": "/api/auth/me",
            "entity": "users",
            "auth": True,
            "response": _response_schema("users", _table_for_entity("users"), "object"),
        },
        {
            "id": "update_current_user",
            "method": "PATCH",
            "path": "/api/auth/me",
            "entity": "users",
            "auth": True,
            "request": _request_schema("users", _table_for_entity("users"), partial=True),
            "response": _response_schema("users", _table_for_entity("users"), "object"),
        },
        {
            "id": "list_roles",
            "method": "GET",
            "path": "/api/roles",
            "entity": "roles",
            "auth": True,
            "response": _response_schema("roles", _table_for_entity("roles"), "array"),
        },
    ]
    if "payments" in features or "premium_gating" in features:
        endpoints.extend(
            [
                {
                    "id": "get_plans",
                    "method": "GET",
                    "path": "/api/billing/plans",
                    "entity": "subscriptions",
                    "auth": True,
                    "response": {
                        "type": "array",
                        "entity": "subscriptions",
                        "fields": [
                            {"name": "id", "type": "string", "required": True},
                            {"name": "name", "type": "string", "required": True},
                            {"name": "price", "type": "number", "required": True},
                            {"name": "features", "type": "object", "required": False},
                        ],
                    },
                },
                {
                    "id": "start_checkout",
                    "method": "POST",
                    "path": "/api/billing/checkout",
                    "entity": "payments",
                    "auth": True,
                    "request": {
                        "body": {
                            "type": "object",
                            "entity": "subscriptions",
                            "partial": False,
                            "fields": [{"name": "plan_id", "type": "string", "required": True}],
                        }
                    },
                    "response": {
                        "type": "object",
                        "entity": "payments",
                        "fields": [
                            {"name": "checkoutUrl", "type": "string", "required": True, "format": "url"},
                            {"name": "expiresAt", "type": "string", "required": True, "format": "datetime"},
                        ],
                    },
                },
                {
                    "id": "list_payments",
                    "method": "GET",
                    "path": "/api/billing/payments",
                    "entity": "payments",
                    "auth": True,
                    "response": _response_schema("payments", _table_for_entity("payments"), "array"),
                },
            ]
        )
    return endpoints


def _permissions(role: str, endpoint_ids: List[str]) -> Dict:
    if role == "admin":
        allowed = endpoint_ids
    elif role in ["manager", "agent", "teacher", "doctor"]:
        allowed = [eid for eid in endpoint_ids if not eid.startswith("delete_")]
    else:
        allowed = [
            eid
            for eid in endpoint_ids
            if eid.startswith("list_")
            or eid.startswith("get_")
            or eid in ["get_current_user", "update_current_user", "get_dashboard_summary"]
        ]
    return {"role": role, "allowedEndpoints": sorted(set(allowed))}


def _payment_contract(features: List[str]) -> Dict:
    enabled = "payments" in features or "premium_gating" in features
    plans = []
    if enabled:
        plans = [
            {
                "id": "starter",
                "name": "Starter",
                "price": 0,
                "currency": "USD",
                "features": ["core_records", "dashboard"],
            },
            {
                "id": "pro",
                "name": "Pro",
                "price": 29,
                "currency": "USD",
                "features": ["premium", "analytics", "team_roles"],
            },
        ]
    return {
        "enabled": enabled,
        "provider": "simulated_checkout" if enabled else "none",
        "plans": plans,
        "gatedFeatures": ["premium", "analytics"] if "premium_gating" in features else [],
        "requiredApis": ["get_plans", "start_checkout", "list_payments"] if enabled else [],
    }


def _entity_contracts(tables: List[Dict]) -> List[Dict]:
    return [
        {
            "name": table["name"],
            "label": table["label"],
            "primaryKey": table["primaryKey"],
            "fields": _field_names_for_table(table, include_system=True),
        }
        for table in tables
    ]


def _runtime_plan(ui_pages: List[Dict], endpoints: List[Dict], tables: List[Dict], features: List[str]) -> Dict:
    endpoint_ids = {endpoint["id"] for endpoint in endpoints}
    table_names = {table["name"] for table in tables}
    dashboard_widgets = []
    for entity in sorted(table_names):
        api_id = f"list_{entity}"
        if api_id in endpoint_ids and entity not in {"roles"}:
            dashboard_widgets.append(
                {
                    "id": f"{entity}_count",
                    "label": f"{titleize(entity)} count",
                    "sourceEntity": entity,
                    "sourceApi": api_id,
                    "aggregation": "count",
                }
            )
    if not dashboard_widgets and "get_dashboard_summary" in endpoint_ids:
        dashboard_widgets.append(
            {
                "id": "summary_metrics",
                "label": "Summary metrics",
                "sourceEntity": "reports" if "reports" in table_names else "users",
                "sourceApi": "get_dashboard_summary",
                "aggregation": "summary",
            }
        )
    return {
        "routes": [{"route": page["route"], "pageId": page["id"], "requiredApis": page["requiredApis"]} for page in ui_pages],
        "databaseTables": sorted(table_names),
        "apiEndpoints": sorted(endpoint_ids),
        "dashboardWidgets": dashboard_widgets[:8],
        "authChecks": ["session_required", "role_endpoint_matrix"],
        "premiumChecks": ["active_subscription_required"] if "premium_gating" in features else [],
    }


def generate_config(intent: Dict, design: Dict) -> Dict:
    entities = list(design["entities"])
    features = list(design["features"])
    if "users" not in entities:
        entities.insert(0, "users")
    if "roles" not in entities:
        entities.append("roles")
    if "payments" in features or "premium_gating" in features:
        for needed in ["subscriptions", "payments"]:
            if needed not in entities:
                entities.append(needed)
    if "analytics" in features and "reports" not in entities:
        entities.append("reports")

    tables = [_table_for_entity(entity) for entity in entities]
    tables_by_name = {table["name"]: table for table in tables}
    endpoints: List[Dict] = []
    for entity in entities:
        if entity != "roles":
            endpoints.extend(_crud_endpoints(entity, tables_by_name[entity]))
    seen_endpoint_ids = {endpoint["id"] for endpoint in endpoints}
    seen_routes = {(endpoint["method"], endpoint["path"]) for endpoint in endpoints}
    for endpoint in _system_endpoints(features):
        route = (endpoint["method"], endpoint["path"])
        if endpoint["id"] not in seen_endpoint_ids and route not in seen_routes:
            endpoints.append(endpoint)
            seen_endpoint_ids.add(endpoint["id"])
            seen_routes.add(route)
    endpoint_ids = [endpoint["id"] for endpoint in endpoints]

    endpoint_by_id = {endpoint["id"]: endpoint for endpoint in endpoints}
    ui_pages = []
    for page in design["pages"]:
        page_entity = page.get("entity")
        primary_api = page["requiredApis"][0] if page["requiredApis"] else None
        primary_endpoint = endpoint_by_id.get(primary_api or "")
        binding_entity = page_entity or (primary_endpoint or {}).get("entity")
        field_bindings = []
        if binding_entity in tables_by_name:
            field_bindings = _field_names_for_table(tables_by_name[binding_entity])[:8]
        ui_pages.append(
            {
                "id": page["id"],
                "title": page["title"],
                "route": page["route"],
                "entity": binding_entity,
                "layout": page["layout"],
                "components": [
                    {
                        "id": f"{slugify(page['id'])}_{slugify(component)}",
                        "type": component,
                        "dataSource": primary_api,
                        "entity": binding_entity,
                        "fieldBindings": list(field_bindings),
                    }
                    for component in page["components"]
                ],
                "requiredApis": page["requiredApis"],
            }
        )

    business_rules = []
    if "premium_gating" in features:
        business_rules.append(
            {
                "id": "premium_feature_gate",
                "description": "Premium-only actions require an active subscription.",
                "when": {"feature": "premium", "subscription.status": "not_active"},
                "then": {"deny": True, "redirect": "/billing"},
                "dependsOn": ["subscriptions", "payments", "start_checkout"],
            }
        )
    if "rbac" in features or len(design["roles"]) > 1:
        business_rules.append(
            {
                "id": "endpoint_authorization",
                "description": "Every API request must be authorized against the role endpoint matrix.",
                "when": {"request.authenticated": True},
                "then": {"check": "auth.roles.allowedEndpoints"},
                "dependsOn": ["users", "roles"],
            }
        )

    payments = _payment_contract(features)
    roles = design["roles"]
    runtime_plan = _runtime_plan(ui_pages, endpoints, tables, features)
    metadata = {
        "schemaVersion": "2.0.0",
        "generator": "deterministic_rule_based_compiler",
        "sourceIntentId": intent["id"],
        "confidence": 0.92 if intent.get("ambiguity", {}).get("level") == "low" else 0.78,
        "deterministic": True,
    }

    return {
        "schemaVersion": "1.0.0",
        "compiler": {
            "name": "AppCompilerAI",
            "mode": "deterministic_multi_stage",
            "stages": ["intentExtractionStage", "systemDesignStage", "schemaGenerationStage", "consistencyValidationStage", "repairStage", "runtimeSimulationStage"],
        },
        "app": design["app"],
        "intent": {
            "id": intent["id"],
            "domains": intent["domains"],
            "features": features,
            "entities": entities,
            "roles": roles,
            "ambiguity": intent["ambiguity"],
            "conflicts": intent["conflicts"],
        },
        "entities": _entity_contracts(tables),
        "roles": roles,
        "ui": {"pages": ui_pages, "navigation": [{"label": page["title"], "route": page["route"]} for page in ui_pages]},
        "api": {"basePath": "/api", "endpoints": endpoints},
        "database": {"engine": "postgresql_compatible", "tables": tables},
        "auth": {
            "strategy": "session_jwt",
            "roles": [_permissions(role, endpoint_ids) for role in design["roles"]],
            "defaultRole": "member" if "member" in design["roles"] else design["roles"][-1],
        },
        "businessLogic": {"rules": business_rules},
        "payments": payments,
        "assumptions": design["assumptions"],
        "clarifications": design["clarificationQuestions"],
        "clarificationQuestions": design["clarificationQuestions"],
        "runtimePlan": runtime_plan,
        "metadata": metadata,
        "sourceIntentId": intent["id"],
    }
