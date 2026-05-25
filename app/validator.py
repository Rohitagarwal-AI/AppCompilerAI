"""Stage 5: strict schema validation and targeted repair."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Tuple

from .contracts import (
    REQUIRED_TOP_LEVEL,
    RepairAction,
    has_blocking_issues,
    validate_config_contract,
)
from .generator import _crud_endpoints, _field_names_for_table, _request_schema, _response_schema, _table_for_entity
from .modes import mode_profile, normalize_mode
from .utils import slugify


def _issue(code: str, severity: str, message: str, path: str, blocking: bool = False) -> Dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "message": message,
        "path": path,
        "stage": "validation_repair",
        "blocking": blocking,
    }


def _action(code: str, path: str, reason: str, before: Any, after: Any, repaired: bool = True) -> Dict[str, Any]:
    return RepairAction(
        code=code,
        stage="validation_repair",
        path=path,
        reason=reason,
        before=before,
        after=after,
        repaired=repaired,
    ).to_dict()


def _endpoint_by_id(config: Dict) -> Dict[str, Dict]:
    return {endpoint["id"]: endpoint for endpoint in config.get("api", {}).get("endpoints", []) if "id" in endpoint}


def _table_by_name(config: Dict) -> Dict[str, Dict]:
    return {table["name"]: table for table in config.get("database", {}).get("tables", []) if "name" in table}


def _default_for_key(key: str) -> Any:
    if key == "schemaVersion":
        return "1.0.0"
    if key in {"entities", "roles", "assumptions", "clarifications"}:
        return []
    if key == "compiler":
        return {"name": "AppCompilerAI", "mode": "deterministic_multi_stage", "stages": []}
    return {}


def _table_field_names(table: Dict, include_system: bool = True) -> List[str]:
    system_fields = {"id", "created_at", "updated_at"}
    return [
        field["name"]
        for field in table.get("fields", [])
        if include_system or field.get("name") not in system_fields
    ]


def _schema_field_names(schema: Dict) -> List[str]:
    fields = schema.get("fields", [])
    names = []
    for field in fields:
        if isinstance(field, dict) and "name" in field:
            names.append(field["name"])
        elif isinstance(field, str):
            names.append(field)
    return names


def _add_table(config: Dict, table_name: str, actions: List[Dict[str, Any]]) -> None:
    tables = _table_by_name(config)
    table_name = slugify(table_name)
    if table_name not in tables:
        before = [table.get("name") for table in config.setdefault("database", {}).setdefault("tables", [])]
        table = _table_for_entity(table_name)
        config["database"]["tables"].append(table)
        after = before + [table_name]
        actions.append(_action("add_missing_table", "database.tables", f"Added table required by a reference: `{table_name}`.", before, after))


def _add_crud_endpoint(config: Dict, endpoint_id: str, actions: List[Dict[str, Any]]) -> None:
    if "_" not in endpoint_id:
        return
    verb, entity = endpoint_id.split("_", 1)
    entity = slugify(entity)
    existing = _endpoint_by_id(config)
    if endpoint_id in existing:
        return
    _add_table(config, entity, actions)
    table = _table_by_name(config).get(entity, _table_for_entity(entity))
    before = sorted(existing.keys())
    for endpoint in _crud_endpoints(entity, table):
        if endpoint["id"] == endpoint_id and verb in {"list", "create", "get", "update", "delete"}:
            config.setdefault("api", {}).setdefault("endpoints", []).append(endpoint)
            after = sorted(_endpoint_by_id(config).keys())
            actions.append(_action("add_missing_endpoint", "api.endpoints", f"Added endpoint required by UI: `{endpoint_id}`.", before, after))
            return


def _sync_public_contract(config: Dict, intent: Dict, issues: List[Dict[str, Any]], actions: List[Dict[str, Any]]) -> None:
    tables = config.setdefault("database", {}).setdefault("tables", [])
    table_names = [table.get("name") for table in tables if table.get("name")]
    if not config.get("entities"):
        before = config.get("entities")
        config["entities"] = [
            {
                "name": table["name"],
                "label": table.get("label", table["name"].title()),
                "primaryKey": table.get("primaryKey", "id"),
                "fields": _table_field_names(table, include_system=True),
            }
            for table in tables
        ]
        issues.append(_issue("missing_entities_contract", "medium", "Top-level entities contract was missing or empty.", "entities"))
        actions.append(_action("restore_entities_contract", "entities", "Derived top-level entity contracts from database tables.", before, config["entities"]))

    seen = set()
    deduped = []
    removed = []
    for entity in config.get("entities", []):
        name = entity.get("name") if isinstance(entity, dict) else str(entity)
        if name in seen:
            removed.append(name)
            continue
        seen.add(name)
        deduped.append(entity)
    if removed:
        before = deepcopy(config["entities"])
        config["entities"] = deduped
        issues.append(_issue("duplicate_entity_names", "high", f"Duplicate entities removed: {', '.join(removed)}.", "entities"))
        actions.append(_action("remove_duplicate_entities", "entities", "Removed duplicate entity names to keep generation deterministic.", before, deduped))

    if not config.get("roles"):
        before = config.get("roles")
        config["roles"] = list(intent.get("roles") or ["admin", "member"])
        issues.append(_issue("missing_roles_contract", "medium", "Top-level roles contract was missing or empty.", "roles"))
        actions.append(_action("restore_roles_contract", "roles", "Derived top-level roles from intent.", before, config["roles"]))

    questions = config.get("clarificationQuestions", [])
    if config.get("clarifications") != questions:
        before = deepcopy(config.get("clarifications"))
        config["clarifications"] = list(questions)
        actions.append(_action("sync_clarifications_alias", "clarifications", "Synced public clarifications with compiler clarificationQuestions.", before, config["clarifications"]))

    config.setdefault("intent", {})
    config["intent"].setdefault("id", intent.get("id"))
    config["intent"].setdefault("features", intent.get("features", []))
    config["intent"].setdefault("entities", table_names)
    config["intent"].setdefault("roles", config.get("roles", []))
    config.setdefault("metadata", {}).setdefault("deterministic", True)


def _ensure_payload_schemas(config: Dict, issues: List[Dict[str, Any]], actions: List[Dict[str, Any]]) -> None:
    tables = _table_by_name(config)
    for index, endpoint in enumerate(config.get("api", {}).get("endpoints", [])):
        entity = endpoint.get("entity")
        table = tables.get(entity)
        if not table:
            continue
        path = f"api.endpoints[{index}]"
        request = endpoint.get("request")
        if request and (not isinstance(request.get("body"), dict)):
            before = deepcopy(request)
            partial = endpoint.get("method") in {"PATCH", "PUT"}
            endpoint["request"] = _request_schema(entity, table, partial=partial)
            issues.append(_issue("request_schema_symbolic", "medium", f"Endpoint `{endpoint.get('id')}` used a symbolic request body.", f"{path}.request"))
            actions.append(_action("normalize_request_schema", f"{path}.request", "Expanded symbolic request body into field-level schema.", before, endpoint["request"]))
        response = endpoint.get("response", {})
        if isinstance(response, dict) and response.get("entity") == entity and not response.get("fields"):
            before = deepcopy(response)
            endpoint["response"] = _response_schema(entity, table, response.get("type", "object"))
            issues.append(_issue("response_schema_missing_fields", "medium", f"Endpoint `{endpoint.get('id')}` response lacked explicit fields.", f"{path}.response"))
            actions.append(_action("normalize_response_schema", f"{path}.response", "Expanded response into field-level schema.", before, endpoint["response"]))


def _validate_payload_fields(config: Dict, issues: List[Dict[str, Any]], actions: List[Dict[str, Any]]) -> None:
    tables = _table_by_name(config)
    for index, endpoint in enumerate(config.get("api", {}).get("endpoints", [])):
        entity = endpoint.get("entity")
        table = tables.get(entity)
        if not table:
            issues.append(_issue("api_entity_missing_table", "high", f"Endpoint `{endpoint.get('id')}` references missing table `{entity}`.", f"api.endpoints[{index}].entity"))
            _add_table(config, entity or "records", actions)
            continue
        valid_fields = set(_table_field_names(table, include_system=True))
        for schema_key in ["request", "response"]:
            schema = endpoint.get(schema_key, {})
            body = schema.get("body") if schema_key == "request" and isinstance(schema, dict) else schema
            if not isinstance(body, dict):
                continue
            if schema_key == "response" and body.get("entity") != entity:
                continue
            if schema_key == "request" and body.get("entity") and body.get("entity") != entity:
                continue
            schema_fields = _schema_field_names(body)
            invalid = [name for name in schema_fields if name not in valid_fields]
            if invalid and entity not in {"payments", "subscriptions"}:
                before = deepcopy(body.get("fields", []))
                body["fields"] = [field for field in body.get("fields", []) if not isinstance(field, dict) or field.get("name") in valid_fields]
                issues.append(_issue("payload_field_missing_in_table", "high", f"Endpoint `{endpoint.get('id')}` referenced fields not present on `{entity}`: {', '.join(invalid)}.", f"api.endpoints[{index}].{schema_key}.fields"))
                actions.append(_action("remove_invalid_payload_fields", f"api.endpoints[{index}].{schema_key}.fields", "Removed payload fields that do not exist in the database table.", before, body.get("fields", [])))


def _validate_duplicate_endpoints(config: Dict, issues: List[Dict[str, Any]], actions: List[Dict[str, Any]]) -> None:
    endpoints = config.get("api", {}).get("endpoints", [])
    seen_ids = set()
    seen_routes = set()
    kept = []
    removed = []
    for endpoint in endpoints:
        route_pair = (endpoint.get("method"), endpoint.get("path"))
        endpoint_id = endpoint.get("id")
        if endpoint_id in seen_ids or route_pair in seen_routes:
            removed.append(endpoint)
            issues.append(_issue("duplicate_endpoint", "high", f"Duplicate endpoint `{endpoint_id}` or route `{route_pair}` removed.", "api.endpoints"))
            continue
        seen_ids.add(endpoint_id)
        seen_routes.add(route_pair)
        kept.append(endpoint)
    if removed:
        before = [endpoint.get("id") for endpoint in endpoints]
        config["api"]["endpoints"] = kept
        after = [endpoint.get("id") for endpoint in kept]
        actions.append(_action("remove_duplicate_endpoints", "api.endpoints", "Removed duplicate endpoints to keep routing deterministic.", before, after))


def _validate_ui_bindings(config: Dict, issues: List[Dict[str, Any]], actions: List[Dict[str, Any]]) -> None:
    endpoint_ids = set(_endpoint_by_id(config).keys())
    endpoints = _endpoint_by_id(config)
    tables = _table_by_name(config)
    for page_index, page in enumerate(config.get("ui", {}).get("pages", [])):
        required = page.get("requiredApis", [])
        for api_id in list(required):
            if api_id not in endpoint_ids:
                issues.append(_issue("ui_missing_api", "high", f"Page `{page.get('id')}` requires missing API `{api_id}`.", f"ui.pages[{page_index}].requiredApis"))
                _add_crud_endpoint(config, api_id, actions)
                endpoint_ids = set(_endpoint_by_id(config).keys())
                endpoints = _endpoint_by_id(config)

        fallback = next((api_id for api_id in page.get("requiredApis", []) if api_id in endpoint_ids), None)
        page_entity = page.get("entity") or (endpoints.get(fallback or "", {}).get("entity") if fallback else None)
        if page_entity and page.get("entity") != page_entity:
            before = page.get("entity")
            page["entity"] = page_entity
            actions.append(_action("set_page_entity", f"ui.pages[{page_index}].entity", "Aligned page entity with its primary API binding.", before, page_entity))
        table = tables.get(page_entity or "")
        valid_fields = set(_field_names_for_table(table) if table else [])

        for component_index, component in enumerate(page.get("components", [])):
            path = f"ui.pages[{page_index}].components[{component_index}]"
            source = component.get("dataSource")
            if source and source not in endpoint_ids:
                before = source
                component["dataSource"] = fallback
                issues.append(_issue("component_invalid_data_source", "medium", f"Component `{component.get('id')}` used invalid data source `{source}`.", f"{path}.dataSource"))
                actions.append(_action("repoint_component_data_source", f"{path}.dataSource", "Repointed component to a valid page API binding.", before, component.get("dataSource")))
            if page_entity and component.get("entity") != page_entity:
                before = component.get("entity")
                component["entity"] = page_entity
                actions.append(_action("set_component_entity", f"{path}.entity", "Aligned component entity with page/API entity.", before, page_entity))
            bindings = component.get("fieldBindings")
            if bindings is None:
                bindings = []
            invalid = [field for field in bindings if field not in valid_fields]
            if table and (not bindings or invalid):
                before = deepcopy(bindings)
                component["fieldBindings"] = _field_names_for_table(table)[:8]
                issue_code = "component_missing_field_bindings" if not bindings else "component_invalid_field_binding"
                issues.append(_issue(issue_code, "medium", f"Component `{component.get('id')}` had incomplete field bindings.", f"{path}.fieldBindings"))
                actions.append(_action("normalize_component_field_bindings", f"{path}.fieldBindings", "Bound component fields to valid database fields for its entity.", before, component["fieldBindings"]))


def _validate_relations(config: Dict, issues: List[Dict[str, Any]], actions: List[Dict[str, Any]]) -> None:
    table_names = set(_table_by_name(config).keys())
    for table_index, table in enumerate(list(config.get("database", {}).get("tables", []))):
        for field_index, field in enumerate(table.get("fields", [])):
            ref = field.get("references")
            if ref and ref not in table_names:
                issues.append(_issue("foreign_key_missing_table", "high", f"Field `{table['name']}.{field['name']}` references missing table `{ref}`.", f"database.tables[{table_index}].fields[{field_index}].references"))
                _add_table(config, ref, actions)
                table_names = set(_table_by_name(config).keys())


def _validate_auth(config: Dict, issues: List[Dict[str, Any]], actions: List[Dict[str, Any]]) -> None:
    endpoint_ids = sorted(_endpoint_by_id(config).keys())
    roles = config.setdefault("auth", {}).setdefault("roles", [])
    role_names = {role.get("role") for role in roles}
    if "admin" not in role_names:
        before = deepcopy(roles)
        roles.insert(0, {"role": "admin", "allowedEndpoints": endpoint_ids})
        issues.append(_issue("missing_admin_role", "high", "Auth config must include an admin role.", "auth.roles"))
        actions.append(_action("add_admin_role", "auth.roles", "Added admin role with full endpoint access.", before, roles))

    for role_index, role in enumerate(roles):
        allowed = role.get("allowedEndpoints", [])
        invalid = [endpoint for endpoint in allowed if endpoint not in endpoint_ids]
        if invalid:
            before = list(allowed)
            role["allowedEndpoints"] = [endpoint for endpoint in allowed if endpoint in endpoint_ids]
            issues.append(_issue("role_invalid_endpoint", "medium", f"Role `{role.get('role')}` referenced unknown endpoints.", f"auth.roles[{role_index}].allowedEndpoints"))
            actions.append(_action("remove_invalid_role_endpoints", f"auth.roles[{role_index}].allowedEndpoints", "Removed role permissions for endpoints that do not exist.", before, role["allowedEndpoints"]))
        if role.get("role") == "admin" and set(role.get("allowedEndpoints", [])) != set(endpoint_ids):
            before = list(role.get("allowedEndpoints", []))
            role["allowedEndpoints"] = endpoint_ids
            issues.append(_issue("admin_missing_permissions", "high", "Admin role must be able to access every endpoint.", f"auth.roles[{role_index}].allowedEndpoints"))
            actions.append(_action("restore_admin_permissions", f"auth.roles[{role_index}].allowedEndpoints", "Expanded admin role to the full endpoint matrix.", before, endpoint_ids))


def _validate_payment_contract(config: Dict, intent: Dict, issues: List[Dict[str, Any]], actions: List[Dict[str, Any]]) -> None:
    features = set(intent.get("features", [])) | set(config.get("intent", {}).get("features", []))
    payments_required = bool({"payments", "premium_gating"} & features)
    payments = config.setdefault("payments", {})
    if payments_required and not payments.get("enabled"):
        before = payments.get("enabled")
        payments["enabled"] = True
        issues.append(_issue("payments_required_but_disabled", "high", "Prompt requires payments or premium gating, but payments were disabled.", "payments.enabled"))
        actions.append(_action("enable_payments", "payments.enabled", "Enabled payments because premium/payment requirements exist.", before, True))
    if payments_required and not payments.get("plans"):
        before = deepcopy(payments.get("plans"))
        payments["plans"] = [
            {"id": "starter", "name": "Starter", "price": 0, "currency": "USD", "features": ["core_records"]},
            {"id": "pro", "name": "Pro", "price": 29, "currency": "USD", "features": ["premium", "analytics"]},
        ]
        issues.append(_issue("premium_without_payment_plan", "high", "Premium/payment requirements need at least one concrete plan.", "payments.plans"))
        actions.append(_action("add_payment_plans", "payments.plans", "Added deterministic Starter and Pro plans for premium gating.", before, payments["plans"]))
    if "premium_gating" in features and not any(rule.get("id") == "premium_feature_gate" for rule in config.get("businessLogic", {}).get("rules", [])):
        before = deepcopy(config.setdefault("businessLogic", {}).setdefault("rules", []))
        rule = {
            "id": "premium_feature_gate",
            "description": "Premium-only actions require an active subscription.",
            "when": {"feature": "premium", "subscription.status": "not_active"},
            "then": {"deny": True, "redirect": "/billing"},
            "dependsOn": ["subscriptions", "payments", "start_checkout"],
        }
        config["businessLogic"]["rules"].append(rule)
        issues.append(_issue("premium_rule_missing", "high", "Premium feature requested without a premium gate rule.", "businessLogic.rules"))
        actions.append(_action("add_premium_gate_rule", "businessLogic.rules", "Added explicit premium feature gate.", before, config["businessLogic"]["rules"]))


def _validate_dashboard_widgets(config: Dict, issues: List[Dict[str, Any]], actions: List[Dict[str, Any]]) -> None:
    runtime_plan = config.setdefault("runtimePlan", {})
    endpoints = _endpoint_by_id(config)
    tables = _table_by_name(config)
    before_surface = {
        "routes": deepcopy(runtime_plan.get("routes", [])),
        "databaseTables": deepcopy(runtime_plan.get("databaseTables", [])),
        "apiEndpoints": deepcopy(runtime_plan.get("apiEndpoints", [])),
    }
    runtime_plan["routes"] = [
        {"route": page.get("route"), "pageId": page.get("id"), "requiredApis": page.get("requiredApis", [])}
        for page in config.get("ui", {}).get("pages", [])
    ]
    runtime_plan["databaseTables"] = sorted(tables.keys())
    runtime_plan["apiEndpoints"] = sorted(endpoints.keys())
    after_surface = {
        "routes": runtime_plan["routes"],
        "databaseTables": runtime_plan["databaseTables"],
        "apiEndpoints": runtime_plan["apiEndpoints"],
    }
    if before_surface != after_surface:
        actions.append(_action("sync_runtime_plan_surface", "runtimePlan", "Synced runtime plan with repaired UI/API/database surface.", before_surface, after_surface))

    widgets = runtime_plan.setdefault("dashboardWidgets", [])
    if not widgets:
        api_id = "get_dashboard_summary" if "get_dashboard_summary" in endpoints else next(iter(endpoints), "")
        entity = "reports" if "reports" in tables else next(iter(tables), "users")
        before = []
        widgets.append(
            {
                "id": "summary_metrics",
                "label": "Summary metrics",
                "sourceEntity": entity,
                "sourceApi": api_id,
                "aggregation": "summary",
            }
        )
        issues.append(_issue("dashboard_metric_without_source", "medium", "Dashboard had no metric source widgets.", "runtimePlan.dashboardWidgets"))
        actions.append(_action("add_dashboard_widget_source", "runtimePlan.dashboardWidgets", "Connected dashboard metrics to a concrete entity/API source.", before, widgets))
    for index, widget in enumerate(list(widgets)):
        source_entity = widget.get("sourceEntity")
        source_api = widget.get("sourceApi")
        if source_entity not in tables or source_api not in endpoints:
            before = deepcopy(widget)
            fallback_entity = "reports" if "reports" in tables else next(iter(tables), "users")
            fallback_api = f"list_{fallback_entity}" if f"list_{fallback_entity}" in endpoints else "get_dashboard_summary"
            widget["sourceEntity"] = fallback_entity
            widget["sourceApi"] = fallback_api
            issues.append(_issue("dashboard_metric_invalid_source", "medium", f"Dashboard widget `{widget.get('id')}` referenced missing source.", f"runtimePlan.dashboardWidgets[{index}]"))
            actions.append(_action("repair_dashboard_widget_source", f"runtimePlan.dashboardWidgets[{index}]", "Repointed dashboard widget to a valid entity/API source.", before, widget))


def _validate_business_rules(config: Dict, intent: Dict, issues: List[Dict[str, Any]], actions: List[Dict[str, Any]]) -> None:
    table_names = set(_table_by_name(config).keys())
    endpoint_ids = set(_endpoint_by_id(config).keys())
    dependencies = table_names | endpoint_ids
    for rule_index, rule in enumerate(config.get("businessLogic", {}).get("rules", [])):
        missing = [dep for dep in rule.get("dependsOn", []) if dep not in dependencies]
        if missing:
            before = list(rule.get("dependsOn", []))
            rule["dependsOn"] = [dep for dep in rule.get("dependsOn", []) if dep in dependencies]
            issues.append(_issue("business_rule_missing_dependency", "medium", f"Rule `{rule.get('id')}` had missing dependencies: {', '.join(missing)}.", f"businessLogic.rules[{rule_index}].dependsOn"))
            actions.append(_action("remove_missing_rule_dependencies", f"businessLogic.rules[{rule_index}].dependsOn", "Removed unresolved business-rule dependencies.", before, rule["dependsOn"]))

    if "premium_gating" in intent.get("features", []) and "premium_feature_gate" not in {rule.get("id") for rule in config.get("businessLogic", {}).get("rules", [])}:
        issues.append(_issue("premium_rule_missing", "high", "Premium prompts require an explicit premium feature gate.", "businessLogic.rules", True))

    if intent.get("conflicts"):
        questions = config.setdefault("clarificationQuestions", [])
        for conflict in intent["conflicts"]:
            issues.append(_issue("logical_conflict", "high", conflict["message"], "intent.conflicts"))
            question = f"Resolve conflict: {conflict['message']}"
            if question not in questions:
                before = list(questions)
                questions.append(question)
                actions.append(_action("document_logical_conflict", "clarificationQuestions", "Recorded conflict as a reviewer-visible clarification question while preserving executable artifacts.", before, list(questions), repaired=False))


def validate_and_repair(config: Dict, intent: Dict, mode: str = "balanced") -> Tuple[Dict, Dict]:
    repaired = deepcopy(config)
    issues: List[Dict[str, Any]] = []
    actions: List[Dict[str, Any]] = []
    mode_id = normalize_mode(mode)
    profile = mode_profile(mode_id)

    initial_contract_issues = validate_config_contract(repaired, "pre_repair_contract")
    issues.extend(initial_contract_issues)

    for key in REQUIRED_TOP_LEVEL:
        if key not in repaired:
            before = None
            repaired[key] = _default_for_key(key)
            issues.append(_issue("missing_top_level_key", "critical", f"Missing required top-level key `{key}`.", key, True))
            actions.append(_action("insert_top_level_key", key, f"Inserted required top-level key `{key}`.", before, repaired[key]))

    repaired.setdefault("ui", {}).setdefault("pages", [])
    repaired.setdefault("api", {}).setdefault("endpoints", [])
    repaired.setdefault("database", {}).setdefault("tables", [])
    repaired.setdefault("auth", {}).setdefault("roles", [])
    repaired.setdefault("businessLogic", {}).setdefault("rules", [])
    repaired.setdefault("payments", {}).setdefault("plans", [])
    repaired.setdefault("runtimePlan", {}).setdefault("dashboardWidgets", [])
    repaired.setdefault("clarifications", repaired.get("clarificationQuestions", []))

    _sync_public_contract(repaired, intent, issues, actions)
    _validate_duplicate_endpoints(repaired, issues, actions)
    _ensure_payload_schemas(repaired, issues, actions)
    if mode_id != "fast":
        _validate_payload_fields(repaired, issues, actions)
    _validate_relations(repaired, issues, actions)
    _validate_ui_bindings(repaired, issues, actions)
    _validate_auth(repaired, issues, actions)
    _validate_payment_contract(repaired, intent, issues, actions)
    _validate_dashboard_widgets(repaired, issues, actions)
    _validate_business_rules(repaired, intent, issues, actions)
    _sync_public_contract(repaired, intent, issues, actions)

    final_contract_issues = validate_config_contract(repaired, "post_repair_contract")
    post_repair_blockers = [issue for issue in final_contract_issues if issue.get("blocking")]
    issues.extend(post_repair_blockers)

    unresolved_blocking = has_blocking_issues(post_repair_blockers)
    clarification_required = bool(intent.get("conflicts")) or intent.get("ambiguity", {}).get("level") == "high"
    cross_layer_consistency = not unresolved_blocking
    status = "blocked" if unresolved_blocking else "needs_clarification" if clarification_required else "repaired" if actions else "passed"

    validation = {
        "status": status,
        "issues": issues,
        "repairActions": actions,
        "failureTypes": sorted({issue["code"] for issue in issues if issue.get("severity") in {"high", "critical"}}),
        "clarificationRequired": clarification_required,
        "mode": profile,
        "stageContracts": {
            "preRepairIssueCount": len(initial_contract_issues),
            "postRepairBlockingCount": len(post_repair_blockers),
            "schemaStrategy": "stdlib_dataclasses",
            "validationDepth": profile["validationDepth"],
        },
        "guarantees": {
            "validJson": True,
            "requiredFieldsPresent": not any(issue.get("code") == "contract_missing_key" for issue in post_repair_blockers),
            "crossLayerConsistency": cross_layer_consistency,
            "typeSafety": not unresolved_blocking,
            "fieldLevelMappings": cross_layer_consistency,
            "targetedRepairOnly": True,
        },
    }
    repaired["validation"] = validation
    return repaired, validation
