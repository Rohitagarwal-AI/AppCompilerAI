"""Stage 6: simulate app execution from the generated configuration."""

from __future__ import annotations

from typing import Dict, List

from .bundler import build_runtime_bundle
from .modes import normalize_mode


def simulate_runtime(config: Dict, mode: str = "balanced") -> Dict:
    mode_id = normalize_mode(mode)
    endpoints = config.get("api", {}).get("endpoints", [])
    tables = config.get("database", {}).get("tables", [])
    pages = config.get("ui", {}).get("pages", [])
    roles = config.get("auth", {}).get("roles", [])
    runtime_plan = config.get("runtimePlan", {})

    route_map = [
        {
            "route": page["route"],
            "layout": page["layout"],
            "components": [component["type"] for component in page.get("components", [])],
            "apiBindings": page.get("requiredApis", []),
        }
        for page in pages
    ]
    api_handlers = [
        {
            "id": endpoint["id"],
            "method": endpoint["method"],
            "path": endpoint["path"],
            "handler": f"handlers.{endpoint['id']}",
            "entity": endpoint.get("entity"),
        }
        for endpoint in endpoints
    ]
    access_matrix = [
        {
            "role": role.get("role"),
            "allowedEndpoints": role.get("allowedEndpoints", []),
            "endpointCount": len(role.get("allowedEndpoints", [])),
        }
        for role in roles
    ]
    bundle = build_runtime_bundle(config, write_files=True)
    migrations = [bundle["schemaSql"]]

    endpoint_ids = {endpoint["id"] for endpoint in endpoints}
    table_names = {table["name"] for table in tables}
    table_fields = {table["name"]: {field["name"] for field in table.get("fields", [])} for table in tables}
    smoke_tests: List[Dict] = []
    smoke_tests.append(
        {
            "name": "all_ui_api_bindings_resolve",
            "passed": all(api_id in endpoint_ids for page in pages for api_id in page.get("requiredApis", [])),
        }
    )
    smoke_tests.append(
        {
            "name": "api_entities_have_tables",
            "passed": all(endpoint.get("entity") in table_names or endpoint.get("entity") == "reports" for endpoint in endpoints),
        }
    )
    smoke_tests.append(
        {
            "name": "has_renderable_route",
            "passed": any(page.get("route") == "/" for page in pages),
        }
    )
    smoke_tests.append(
        {
            "name": "auth_has_role_matrix",
            "passed": bool(config.get("auth", {}).get("roles")),
        }
    )
    smoke_tests.append(
        {
            "name": "routes_can_be_generated",
            "passed": bool(route_map) and all(route["route"].startswith("/") for route in route_map),
            "detail": f"{len(route_map)} routes",
        }
    )
    smoke_tests.append(
        {
            "name": "database_tables_can_be_created",
            "passed": bool(table_names) and all("id" in fields for fields in table_fields.values()),
            "detail": f"{len(table_names)} tables",
        }
    )
    smoke_tests.append(
        {
            "name": "login_auth_rules_resolve",
            "passed": bool(roles) and all(endpoint in endpoint_ids for role in roles for endpoint in role.get("allowedEndpoints", [])),
            "detail": f"{len(roles)} roles",
        }
    )
    dashboard_widgets = runtime_plan.get("dashboardWidgets", [])
    smoke_tests.append(
        {
            "name": "dashboard_widgets_fetch_data",
            "passed": all(widget.get("sourceEntity") in table_names and widget.get("sourceApi") in endpoint_ids for widget in dashboard_widgets),
            "detail": f"{len(dashboard_widgets)} widgets",
        }
    )
    payments = config.get("payments", {})
    premium_required = bool(payments.get("gatedFeatures"))
    premium_rule = any(rule.get("id") == "premium_feature_gate" for rule in config.get("businessLogic", {}).get("rules", []))
    payment_required = bool(payments.get("enabled"))
    smoke_tests.append(
        {
            "name": "payments_checkout_ready",
            "passed": (not payment_required) or (bool(payments.get("plans")) and "start_checkout" in endpoint_ids),
            "detail": "not required" if not payment_required else f"{len(payments.get('plans', []))} plans",
        }
    )
    smoke_tests.append(
        {
            "name": "premium_gating_evaluable",
            "passed": (not premium_required) or (bool(payments.get("plans")) and premium_rule and "start_checkout" in endpoint_ids),
            "detail": "not required" if not premium_required else f"{len(payments.get('plans', []))} plans",
        }
    )
    smoke_tests.append(
        {
            "name": "rbac_can_be_enforced",
            "passed": bool(access_matrix) and all(set(item["allowedEndpoints"]).issubset(endpoint_ids) for item in access_matrix),
            "detail": f"{len(access_matrix)} role rows",
        }
    )
    smoke_tests.extend(bundle["sqliteChecks"])
    smoke_tests.extend(bundle["manifestChecks"])
    smoke_tests.extend(bundle["consistencyChecks"])
    if mode_id == "strict":
        smoke_tests.append(
            {
                "name": "strict_ui_fields_have_database_sources",
                "passed": all(
                    field in table_fields.get(component.get("entity"), set())
                    for page in pages
                    for component in page.get("components", [])
                    for field in component.get("fieldBindings", [])
                ),
                "detail": "all component field bindings resolve",
            }
        )
        smoke_tests.append(
            {
                "name": "strict_runtime_plan_matches_surface",
                "passed": set(runtime_plan.get("apiEndpoints", [])).issubset(endpoint_ids)
                and set(runtime_plan.get("databaseTables", [])).issubset(table_names),
                "detail": "runtime plan links checked",
            }
        )
    smoke_tests.append(
        {
            "name": "runtime_bundle_written",
            "passed": bundle["artifactCount"] >= 4,
            "detail": f"{bundle['artifactCount']} files emitted",
        }
    )

    return {
        "ready": all(test["passed"] for test in smoke_tests) and bundle["ready"],
        "runtime": "schema_to_app_simulator_with_sqlite_bundle",
        "routeMap": route_map,
        "apiHandlers": api_handlers,
        "accessControlMatrix": access_matrix,
        "dashboardWidgets": dashboard_widgets,
        "databaseMigrations": migrations,
        "bundle": {
            "directory": bundle["bundleDir"],
            "files": bundle["files"],
            "sqliteChecks": bundle["sqliteChecks"],
            "manifestChecks": bundle["manifestChecks"],
            "consistencyChecks": bundle["consistencyChecks"],
            "ready": bundle["ready"],
        },
        "smokeTests": smoke_tests,
        "message": "Configuration produced a physical runtime bundle and executed SQL in SQLite memory.",
    }
