"""Generate physical runtime bundles and execute SQL proof checks."""

from __future__ import annotations

import html
import json
import sqlite3
import zipfile
from pathlib import Path
from typing import Dict, List

from .contracts import validate_config_contract
from .utils import slugify

ROOT = Path(__file__).resolve().parents[1]
GENERATED_ROOT = ROOT / "generated_apps"

SQL_TYPES = {
    "string": "TEXT",
    "number": "REAL",
    "object": "TEXT",
    "boolean": "INTEGER",
}


def sql_for_table(table: Dict) -> str:
    lines: List[str] = []
    foreign_keys: List[str] = []
    for field in table.get("fields", []):
        name = field["name"]
        if field.get("kind") == "primary_key":
            lines.append(f"  {name} TEXT PRIMARY KEY")
            continue
        sql_type = SQL_TYPES.get(field.get("type", "string"), "TEXT")
        required = " NOT NULL" if field.get("required") else ""
        lines.append(f"  {name} {sql_type}{required}")
        if field.get("references"):
            foreign_keys.append(f"  FOREIGN KEY ({name}) REFERENCES {field['references']}(id)")
    return f"CREATE TABLE IF NOT EXISTS {table['name']} (\n" + ",\n".join(lines + foreign_keys) + "\n);"


def build_sql_schema(config: Dict) -> str:
    tables = config.get("database", {}).get("tables", [])
    return "\n\n".join(sql_for_table(table) for table in tables) + "\n"


def execute_sql_schema(sql_schema: str) -> List[Dict]:
    checks: List[Dict] = []
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("PRAGMA foreign_keys = ON;")
        connection.executescript(sql_schema)
        table_count = len(connection.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall())
        checks.append({"name": "sqlite_schema_executes", "passed": True, "detail": f"{table_count} tables created"})
    except sqlite3.DatabaseError as exc:
        checks.append({"name": "sqlite_schema_executes", "passed": False, "detail": str(exc)})
    finally:
        connection.close()
    return checks


def validate_manifest(manifest: Dict) -> List[Dict]:
    checks: List[Dict] = []
    required = ["schemaVersion", "compiler", "app", "ui", "api", "database", "auth", "businessLogic", "runtime"]
    required.extend(["intent", "entities", "roles", "payments", "assumptions", "clarifications", "runtimePlan", "metadata"])
    missing = [key for key in required if key not in manifest]
    checks.append(
        {
            "name": "manifest_required_keys",
            "passed": not missing,
            "detail": "all required sections present" if not missing else f"missing: {', '.join(missing)}",
        }
    )
    try:
        json.dumps(manifest, sort_keys=True)
        serializable = True
        detail = "manifest is valid JSON"
    except (TypeError, ValueError) as exc:
        serializable = False
        detail = str(exc)
    checks.append({"name": "manifest_json_serializable", "passed": serializable, "detail": detail})

    contract_candidate = {
        "schemaVersion": manifest.get("schemaVersion"),
        "compiler": manifest.get("compiler"),
        "app": manifest.get("app"),
        "intent": manifest.get("intent"),
        "entities": manifest.get("entities"),
        "roles": manifest.get("roles"),
        "ui": manifest.get("ui"),
        "api": manifest.get("api"),
        "database": manifest.get("database"),
        "auth": manifest.get("auth"),
        "businessLogic": manifest.get("businessLogic"),
        "payments": manifest.get("payments"),
        "assumptions": manifest.get("assumptions", []),
        "clarifications": manifest.get("clarifications", []),
        "runtimePlan": manifest.get("runtimePlan", {}),
        "metadata": manifest.get("metadata", {}),
        "clarificationQuestions": manifest.get("clarificationQuestions", []),
        "sourceIntentId": manifest.get("sourceIntentId", ""),
    }
    contract_issues = validate_config_contract(contract_candidate, "runtime_manifest")
    blocking = [issue for issue in contract_issues if issue.get("blocking")]
    checks.append(
        {
            "name": "manifest_contract_valid",
            "passed": not blocking,
            "detail": "contract passed" if not blocking else f"{len(blocking)} blocking contract issues",
            "issues": blocking[:5],
        }
    )
    return checks


def validate_bundle_consistency(config: Dict, files: Dict[str, str], manifest_checks: List[Dict], sqlite_checks: List[Dict]) -> List[Dict]:
    required_files = {"manifest.json", "schema.sql", "preview.html", "README.md"}
    checks = [
        {
            "name": "bundle_required_files",
            "passed": required_files.issubset(files.keys()),
            "detail": "all runtime files present" if required_files.issubset(files.keys()) else "missing runtime files",
        },
        {
            "name": "bundle_manifest_valid",
            "passed": all(check["passed"] for check in manifest_checks),
            "detail": "manifest checks passed",
        },
        {
            "name": "bundle_sql_executes",
            "passed": all(check["passed"] for check in sqlite_checks),
            "detail": "SQLite execution checks passed",
        },
    ]
    endpoints = {endpoint.get("id") for endpoint in config.get("api", {}).get("endpoints", [])}
    required_apis = {
        api_id
        for page in config.get("ui", {}).get("pages", [])
        for api_id in page.get("requiredApis", [])
    }
    missing_bindings = sorted(required_apis - endpoints)
    checks.append(
        {
            "name": "bundle_ui_api_links",
            "passed": not missing_bindings,
            "detail": "all UI APIs resolve" if not missing_bindings else f"missing APIs: {', '.join(missing_bindings)}",
        }
    )
    return checks


def _preview_html(config: Dict) -> str:
    app = config.get("app", {})
    pages = config.get("ui", {}).get("pages", [])
    endpoints = config.get("api", {}).get("endpoints", [])
    tables = config.get("database", {}).get("tables", [])
    page_cards = []
    for page in pages:
        components = "".join(
            f"<li>{html.escape(component.get('type', 'component'))}"
            f"<span>{html.escape(str(component.get('dataSource') or 'local'))}</span></li>"
            for component in page.get("components", [])
        )
        page_cards.append(
            f"""
            <section class="card">
              <div><strong>{html.escape(page.get('title', page.get('id', 'Page')))}</strong><span>{html.escape(page.get('route', '/'))}</span></div>
              <ul>{components}</ul>
            </section>
            """
        )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(app.get('name', 'Generated App'))}</title>
  <style>
    body {{ margin: 0; font-family: Inter, Arial, sans-serif; background: #f7f8f5; color: #182026; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 36px 20px; }}
    header {{ border: 1px solid #d9e0e7; border-radius: 10px; padding: 24px; background: white; }}
    h1 {{ margin: 0 0 8px; }}
    .stats {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 18px; }}
    .stats span {{ border: 1px solid #d9e0e7; border-radius: 999px; padding: 8px 12px; background: #fbfcfd; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 14px; margin-top: 18px; }}
    .card {{ border: 1px solid #d9e0e7; border-radius: 10px; padding: 16px; background: white; }}
    .card div {{ display: flex; justify-content: space-between; gap: 12px; }}
    .card span, li span {{ color: #66717d; }}
    li {{ margin: 8px 0; }}
  </style>
</head>
<body>
  <main>
    <header>
      <p>Generated by AppCompilerAI runtime bundle</p>
      <h1>{html.escape(app.get('name', 'Generated App'))}</h1>
      <p>{html.escape(app.get('summary', 'Schema-driven app preview.'))}</p>
      <div class="stats">
        <span>{len(pages)} pages</span>
        <span>{len(endpoints)} APIs</span>
        <span>{len(tables)} tables</span>
        <span>SQLite verified</span>
      </div>
    </header>
    <div class="grid">{''.join(page_cards)}</div>
  </main>
</body>
</html>
"""


def build_runtime_bundle(config: Dict, write_files: bool = True) -> Dict:
    app_name = config.get("app", {}).get("name", "generated_app")
    bundle_dir = GENERATED_ROOT / slugify(app_name).replace("_", "-")
    sql_schema = build_sql_schema(config)
    sqlite_checks = execute_sql_schema(sql_schema)

    manifest = {
        "schemaVersion": config.get("schemaVersion"),
        "compiler": config.get("compiler"),
        "app": config.get("app", {}),
        "intent": config.get("intent", {}),
        "entities": config.get("entities", []),
        "roles": config.get("roles", []),
        "ui": config.get("ui", {}),
        "api": config.get("api", {}),
        "database": config.get("database", {}),
        "auth": config.get("auth", {}),
        "businessLogic": config.get("businessLogic", {}),
        "payments": config.get("payments", {}),
        "assumptions": config.get("assumptions", []),
        "clarifications": config.get("clarifications", []),
        "clarificationQuestions": config.get("clarificationQuestions", []),
        "runtimePlan": config.get("runtimePlan", {}),
        "metadata": config.get("metadata", {}),
        "sourceIntentId": config.get("sourceIntentId", ""),
        "runtime": {"sqliteChecks": sqlite_checks},
    }
    manifest_checks = validate_manifest(manifest)
    files = {
        "manifest.json": json.dumps(manifest, indent=2, sort_keys=True),
        "schema.sql": sql_schema,
        "preview.html": _preview_html(config),
        "README.md": f"# {app_name}\n\nGenerated by AppCompilerAI.\n\nOpen `preview.html` and inspect `manifest.json` + `schema.sql`.\n",
    }
    consistency_checks = validate_bundle_consistency(config, files, manifest_checks, sqlite_checks)
    if write_files:
        bundle_dir.mkdir(parents=True, exist_ok=True)
        for name, content in files.items():
            (bundle_dir / name).write_text(content, encoding="utf-8")

    return {
        "bundleDir": str(bundle_dir),
        "files": [{"name": name, "bytes": len(content.encode("utf-8"))} for name, content in files.items()],
        "sqliteChecks": sqlite_checks,
        "manifestChecks": manifest_checks,
        "consistencyChecks": consistency_checks,
        "schemaSql": sql_schema,
        "artifactCount": len(files),
        "ready": all(check["passed"] for check in sqlite_checks + manifest_checks + consistency_checks),
    }


def zip_runtime_bundle(config: Dict) -> bytes:
    bundle = build_runtime_bundle(config, write_files=True)
    if not bundle["ready"]:
        failed = [check["name"] for check in bundle["sqliteChecks"] + bundle["manifestChecks"] + bundle["consistencyChecks"] if not check["passed"]]
        raise RuntimeError(f"runtime_bundle_not_ready: {', '.join(failed)}")
    bundle_dir = Path(bundle["bundleDir"])
    zip_path = bundle_dir.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(bundle_dir.iterdir()):
            if path.is_file():
                archive.write(path, arcname=f"{bundle_dir.name}/{path.name}")
    return zip_path.read_bytes()
