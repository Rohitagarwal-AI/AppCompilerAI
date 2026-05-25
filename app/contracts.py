"""Typed contracts and strict validation helpers for AppCompilerAI.

The project intentionally stays dependency-free for reviewer ergonomics, so
these contracts use dataclasses plus explicit validators instead of Pydantic.
Pipeline stages still expose dictionaries to the UI/API, but every artifact can
be checked against these machine-readable contracts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Dict, Iterable, List, Optional


ALLOWED_HTTP_METHODS = {"GET", "POST", "PATCH", "PUT", "DELETE"}
ALLOWED_FIELD_TYPES = {"string", "number", "object", "boolean"}
ALLOWED_SEVERITIES = {"info", "low", "medium", "high", "critical"}
PUBLIC_CONTRACT_KEYS = [
    "app",
    "intent",
    "entities",
    "roles",
    "database",
    "api",
    "ui",
    "auth",
    "businessLogic",
    "payments",
    "assumptions",
    "clarifications",
    "runtimePlan",
    "metadata",
]
REQUIRED_TOP_LEVEL = ["schemaVersion", "compiler"] + PUBLIC_CONTRACT_KEYS


@dataclass(frozen=True)
class ContractIssue:
    code: str
    severity: str
    message: str
    path: str
    stage: str = "contract_validation"
    blocking: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RepairAction:
    code: str
    stage: str
    path: str
    reason: str
    before: Any
    after: Any
    repaired: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class IntentIR:
    id: str
    rawPrompt: str
    normalizedPrompt: str
    appName: str
    domains: List[str]
    features: List[str]
    entities: List[str]
    roles: List[str]
    constraints: Dict[str, Any]
    ambiguity: Dict[str, Any]
    conflicts: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SystemDesign:
    app: Dict[str, Any]
    architecture: Dict[str, Any]
    entities: List[str]
    roles: List[str]
    features: List[str]
    pages: List[Dict[str, Any]]
    flows: List[Dict[str, Any]]
    assumptions: List[str]
    clarificationQuestions: List[str]


@dataclass
class DatabaseField:
    name: str
    type: str
    kind: str
    required: bool
    references: Optional[str] = None
    values: Optional[List[str]] = None
    format: Optional[str] = None


@dataclass
class DatabaseTable:
    name: str
    label: str
    primaryKey: str
    fields: List[DatabaseField]
    indexes: List[str] = field(default_factory=list)


@dataclass
class ApiEndpoint:
    id: str
    method: str
    path: str
    entity: str
    auth: bool
    response: Dict[str, Any]
    request: Optional[Dict[str, Any]] = None


@dataclass
class UIComponent:
    id: str
    type: str
    dataSource: Optional[str] = None
    entity: Optional[str] = None
    fieldBindings: List[str] = field(default_factory=list)


@dataclass
class UIPage:
    id: str
    title: str
    route: str
    layout: str
    components: List[UIComponent]
    requiredApis: List[str]
    entity: Optional[str] = None


@dataclass
class AuthRole:
    role: str
    allowedEndpoints: List[str]


@dataclass
class BusinessRule:
    id: str
    description: str
    when: Dict[str, Any]
    then: Dict[str, Any]
    dependsOn: List[str]


@dataclass
class AppConfig:
    schemaVersion: str
    compiler: Dict[str, Any]
    app: Dict[str, Any]
    ui: Dict[str, Any]
    api: Dict[str, Any]
    database: Dict[str, Any]
    auth: Dict[str, Any]
    businessLogic: Dict[str, Any]
    assumptions: List[str] = field(default_factory=list)
    clarificationQuestions: List[str] = field(default_factory=list)
    sourceIntentId: str = ""


@dataclass
class RuntimeProof:
    ready: bool
    runtime: str
    routeMap: List[Dict[str, Any]]
    apiHandlers: List[Dict[str, Any]]
    databaseMigrations: List[str]
    bundle: Dict[str, Any]
    smokeTests: List[Dict[str, Any]]
    message: str


@dataclass
class EvaluationReport:
    datasetSize: int
    successRate: float
    runtimeExecutableRate: float
    averageLatencyMs: float
    averageRepairActions: float
    maxRepairActions: int
    failureTypes: Dict[str, int]
    byCategory: Dict[str, Any]
    results: List[Dict[str, Any]]


def to_dict(value: Any) -> Any:
    """Return a deterministic JSON-ready representation for dataclasses/lists."""
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: to_dict(value[key]) for key in sorted(value)}
    return value


def _issue(code: str, severity: str, message: str, path: str, stage: str, blocking: bool = False) -> Dict[str, Any]:
    return ContractIssue(code, severity, message, path, stage, blocking).to_dict()


def _is_non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _require_keys(mapping: Dict[str, Any], keys: Iterable[str], path: str, stage: str) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    for key in keys:
        if key not in mapping:
            issues.append(_issue("contract_missing_key", "critical", f"Missing required key `{key}`.", f"{path}.{key}", stage, True))
    return issues


def validate_intent_contract(intent: Dict[str, Any], stage: str = "intent_extraction") -> List[Dict[str, Any]]:
    issues = _require_keys(
        intent,
        ["id", "rawPrompt", "normalizedPrompt", "appName", "domains", "features", "entities", "roles", "constraints", "ambiguity", "conflicts"],
        "intent",
        stage,
    )
    for key in ["id", "rawPrompt", "normalizedPrompt", "appName"]:
        if key in intent and not isinstance(intent[key], str):
            issues.append(_issue("contract_invalid_type", "critical", f"`{key}` must be a string.", f"intent.{key}", stage, True))
    for key in ["domains", "features", "entities", "roles", "conflicts"]:
        if key in intent and not isinstance(intent[key], list):
            issues.append(_issue("contract_invalid_type", "critical", f"`{key}` must be a list.", f"intent.{key}", stage, True))
    return issues


def validate_design_contract(design: Dict[str, Any], stage: str = "system_design") -> List[Dict[str, Any]]:
    issues = _require_keys(
        design,
        ["app", "architecture", "entities", "roles", "features", "pages", "flows", "assumptions", "clarificationQuestions"],
        "design",
        stage,
    )
    if isinstance(design.get("app"), dict):
        issues.extend(_require_keys(design["app"], ["name", "domain", "summary"], "design.app", stage))
    if not isinstance(design.get("pages", []), list):
        issues.append(_issue("contract_invalid_type", "critical", "`pages` must be a list.", "design.pages", stage, True))
        return issues
    for index, page in enumerate(design.get("pages", [])):
        if not isinstance(page, dict):
            issues.append(_issue("contract_invalid_type", "critical", "Page must be an object.", f"design.pages[{index}]", stage, True))
            continue
        issues.extend(_require_keys(page, ["id", "title", "route", "layout", "components", "requiredApis"], f"design.pages[{index}]", stage))
        if "route" in page and (not isinstance(page["route"], str) or not page["route"].startswith("/")):
            issues.append(_issue("contract_invalid_route", "high", "Page route must start with `/`.", f"design.pages[{index}].route", stage))
    return issues


def validate_config_contract(config: Dict[str, Any], stage: str = "schema_generation") -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    issues.extend(_require_keys(config, REQUIRED_TOP_LEVEL, "config", stage))

    ui = config.get("ui", {})
    api = config.get("api", {})
    database = config.get("database", {})
    auth = config.get("auth", {})
    business = config.get("businessLogic", {})
    payments = config.get("payments", {})
    runtime_plan = config.get("runtimePlan", {})
    for path, value, expected in [
        ("config.entities", config.get("entities"), list),
        ("config.roles", config.get("roles"), list),
        ("config.ui.pages", ui.get("pages"), list),
        ("config.api.endpoints", api.get("endpoints"), list),
        ("config.database.tables", database.get("tables"), list),
        ("config.auth.roles", auth.get("roles"), list),
        ("config.businessLogic.rules", business.get("rules"), list),
        ("config.payments.plans", payments.get("plans", []), list),
        ("config.runtimePlan.routes", runtime_plan.get("routes", []), list),
        ("config.runtimePlan.dashboardWidgets", runtime_plan.get("dashboardWidgets", []), list),
        ("config.assumptions", config.get("assumptions"), list),
        ("config.clarifications", config.get("clarifications"), list),
    ]:
        if not isinstance(value, expected):
            issues.append(_issue("contract_invalid_type", "critical", f"`{path}` must be a {expected.__name__}.", path, stage, True))

    table_names = set()
    for table_index, table in enumerate(database.get("tables", []) if isinstance(database.get("tables"), list) else []):
        path = f"config.database.tables[{table_index}]"
        if not isinstance(table, dict):
            issues.append(_issue("contract_invalid_type", "critical", "Table must be an object.", path, stage, True))
            continue
        issues.extend(_require_keys(table, ["name", "label", "primaryKey", "fields"], path, stage))
        if not _is_non_empty_string(table.get("name")):
            issues.append(_issue("contract_invalid_table", "critical", "Table name must be a non-empty string.", f"{path}.name", stage, True))
            continue
        if table["name"] in table_names:
            issues.append(_issue("duplicate_table", "high", f"Duplicate table `{table['name']}`.", f"{path}.name", stage))
        table_names.add(table["name"])
        fields = table.get("fields", [])
        if not isinstance(fields, list) or not fields:
            issues.append(_issue("table_missing_fields", "critical", f"Table `{table.get('name')}` must define fields.", f"{path}.fields", stage, True))
            continue
        field_names = set()
        for field_index, field_item in enumerate(fields):
            field_path = f"{path}.fields[{field_index}]"
            if not isinstance(field_item, dict):
                issues.append(_issue("contract_invalid_type", "critical", "Field must be an object.", field_path, stage, True))
                continue
            issues.extend(_require_keys(field_item, ["name", "type", "kind", "required"], field_path, stage))
            name = field_item.get("name")
            if not _is_non_empty_string(name):
                issues.append(_issue("field_invalid_name", "critical", "Field name must be a non-empty string.", f"{field_path}.name", stage, True))
                continue
            if name in field_names:
                issues.append(_issue("duplicate_field", "high", f"Duplicate field `{table.get('name')}.{name}`.", field_path, stage))
            field_names.add(name)
            if field_item.get("type") not in ALLOWED_FIELD_TYPES:
                issues.append(_issue("field_invalid_type", "high", f"Field `{name}` has unsupported type `{field_item.get('type')}`.", f"{field_path}.type", stage))
        if table.get("primaryKey") not in field_names:
            issues.append(_issue("primary_key_missing", "critical", f"Primary key `{table.get('primaryKey')}` is not declared as a field.", f"{path}.primaryKey", stage, True))

    endpoint_ids = set()
    route_pairs = set()
    for index, endpoint in enumerate(api.get("endpoints", []) if isinstance(api.get("endpoints"), list) else []):
        path = f"config.api.endpoints[{index}]"
        if not isinstance(endpoint, dict):
            issues.append(_issue("contract_invalid_type", "critical", "Endpoint must be an object.", path, stage, True))
            continue
        issues.extend(_require_keys(endpoint, ["id", "method", "path", "entity", "auth", "response"], path, stage))
        endpoint_id = endpoint.get("id")
        if endpoint_id in endpoint_ids:
            issues.append(_issue("duplicate_endpoint_id", "high", f"Duplicate endpoint id `{endpoint_id}`.", f"{path}.id", stage))
        endpoint_ids.add(endpoint_id)
        method = endpoint.get("method")
        route = endpoint.get("path")
        if method not in ALLOWED_HTTP_METHODS:
            issues.append(_issue("invalid_http_method", "high", f"Unsupported HTTP method `{method}`.", f"{path}.method", stage))
        if not isinstance(route, str) or not route.startswith("/"):
            issues.append(_issue("invalid_api_path", "high", "Endpoint path must start with `/`.", f"{path}.path", stage))
        route_pair = (method, route)
        if route_pair in route_pairs:
            issues.append(_issue("duplicate_api_route", "high", f"Duplicate route `{method} {route}`.", path, stage))
        route_pairs.add(route_pair)

    for index, page in enumerate(ui.get("pages", []) if isinstance(ui.get("pages"), list) else []):
        path = f"config.ui.pages[{index}]"
        if not isinstance(page, dict):
            issues.append(_issue("contract_invalid_type", "critical", "Page must be an object.", path, stage, True))
            continue
        issues.extend(_require_keys(page, ["id", "title", "route", "layout", "components", "requiredApis"], path, stage))
        if not isinstance(page.get("route"), str) or not page.get("route", "").startswith("/"):
            issues.append(_issue("contract_invalid_route", "high", "Page route must start with `/`.", f"{path}.route", stage))
        if not isinstance(page.get("components", []), list):
            issues.append(_issue("contract_invalid_type", "critical", "Page components must be a list.", f"{path}.components", stage, True))
            continue
        for component_index, component in enumerate(page.get("components", [])):
            component_path = f"{path}.components[{component_index}]"
            if not isinstance(component, dict):
                issues.append(_issue("contract_invalid_type", "critical", "Component must be an object.", component_path, stage, True))
                continue
            issues.extend(_require_keys(component, ["id", "type", "dataSource", "fieldBindings"], component_path, stage))
            if "fieldBindings" in component and not isinstance(component["fieldBindings"], list):
                issues.append(_issue("contract_invalid_type", "high", "Component fieldBindings must be a list.", f"{component_path}.fieldBindings", stage))

    for role_index, role in enumerate(auth.get("roles", []) if isinstance(auth.get("roles"), list) else []):
        path = f"config.auth.roles[{role_index}]"
        if not isinstance(role, dict):
            issues.append(_issue("contract_invalid_type", "critical", "Role must be an object.", path, stage, True))
            continue
        issues.extend(_require_keys(role, ["role", "allowedEndpoints"], path, stage))
        if not isinstance(role.get("allowedEndpoints", []), list):
            issues.append(_issue("contract_invalid_type", "high", "allowedEndpoints must be a list.", f"{path}.allowedEndpoints", stage))

    for rule_index, rule in enumerate(business.get("rules", []) if isinstance(business.get("rules"), list) else []):
        path = f"config.businessLogic.rules[{rule_index}]"
        if not isinstance(rule, dict):
            issues.append(_issue("contract_invalid_type", "critical", "Business rule must be an object.", path, stage, True))
            continue
        issues.extend(_require_keys(rule, ["id", "description", "when", "then", "dependsOn"], path, stage))
    return issues


def issue_counts(issues: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for issue in issues:
        code = str(issue.get("code", "unknown"))
        counts[code] = counts.get(code, 0) + 1
    return counts


def has_blocking_issues(issues: Iterable[Dict[str, Any]]) -> bool:
    return any(issue.get("blocking") or issue.get("severity") == "critical" for issue in issues)
