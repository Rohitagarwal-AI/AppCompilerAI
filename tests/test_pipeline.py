from __future__ import annotations

import json
import unittest
import zipfile
from io import BytesIO

from app.contracts import validate_config_contract
from app.bundler import zip_runtime_bundle
from app.evaluation import evaluate
from app.pipeline import compile_prompt
from app.validator import validate_and_repair


class PipelineTests(unittest.TestCase):
    def test_compile_returns_executable_strict_json(self):
        output = compile_prompt(
            "Build a CRM with login, contacts, dashboard, role-based access, premium plan with payments, and admin analytics."
        )
        self.assertEqual(output["status"], "ready")
        self.assertTrue(output["execution"]["ready"])
        parsed = json.loads(output["strictConfigJson"])
        self.assertIn("ui", parsed)
        self.assertIn("api", parsed)
        self.assertIn("database", parsed)
        for key in ["app", "intent", "entities", "roles", "auth", "businessLogic", "payments", "assumptions", "clarifications", "runtimePlan", "metadata"]:
            self.assertIn(key, parsed)
        self.assertTrue(parsed["validation"]["guarantees"]["validJson"])
        self.assertIn("bundle", output["execution"])
        self.assertTrue(any(test["name"] == "sqlite_schema_executes" and test["passed"] for test in output["execution"]["smokeTests"]))
        self.assertEqual(output["pipeline"]["schemaStrategy"], "stdlib_dataclasses")
        self.assertTrue(output["pipeline"]["stageContracts"]["schema_generation"]["passed"])
        self.assertEqual(len(output["pipeline"]["trace"]), 6)

    def test_output_config_is_deterministic(self):
        prompt = "Create a support desk with tickets, agents, dashboard, notifications, and admin analytics."
        first = compile_prompt(prompt)["strictConfigJson"]
        second = compile_prompt(prompt)["strictConfigJson"]
        self.assertEqual(first, second)

    def test_compiler_modes_change_quality_profile(self):
        fast = compile_prompt("Build an inventory app with products, stock alerts, and admin dashboard.", mode="fast")
        strict = compile_prompt("Build an inventory app with products, stock alerts, and admin dashboard.", mode="strict")
        self.assertEqual(fast["mode"]["id"], "fast")
        self.assertEqual(strict["mode"]["id"], "strict")
        self.assertGreater(strict["mode"]["reliabilityScore"], fast["mode"]["reliabilityScore"])
        self.assertGreaterEqual(len(strict["execution"]["smokeTests"]), len(fast["execution"]["smokeTests"]))

    def test_targeted_repair_engine_fixes_injected_faults(self):
        output = compile_prompt("Build a project management app with tasks and comments.", repair_demo_fault=True)
        self.assertEqual(output["status"], "ready")
        self.assertGreater(len(output["validation"]["repairActions"]), 0)
        self.assertIsInstance(output["validation"]["repairActions"][0], dict)
        self.assertIn("path", output["validation"]["repairActions"][0])
        self.assertTrue(output["validation"]["guarantees"]["crossLayerConsistency"])

    def test_contract_validation_rejects_missing_schema_sections(self):
        issues = validate_config_contract({"schemaVersion": "1.0.0"}, "unit_test")
        self.assertTrue(any(issue["code"] == "contract_missing_key" for issue in issues))
        self.assertTrue(any(issue["blocking"] for issue in issues))

    def test_ui_api_database_field_mappings_are_explicit(self):
        output = compile_prompt("Build a CRM with contacts, companies, dashboard, login, and admin roles.")
        config = output["config"]
        table_names = {table["name"]: {field["name"] for field in table["fields"]} for table in config["database"]["tables"]}
        for endpoint in config["api"]["endpoints"]:
            table_fields = table_names.get(endpoint.get("entity"))
            if not table_fields:
                continue
            if endpoint.get("response", {}).get("entity") != endpoint.get("entity"):
                continue
            response_fields = endpoint.get("response", {}).get("fields", [])
            for field in response_fields:
                self.assertIn(field["name"], table_fields)
        for page in config["ui"]["pages"]:
            entity = page.get("entity")
            if entity not in table_names:
                continue
            for component in page["components"]:
                for field in component["fieldBindings"]:
                    self.assertIn(field, table_names[entity])

    def test_validator_repairs_broken_component_binding(self):
        output = compile_prompt("Build a support desk with tickets, agents, dashboard, and admin roles.")
        broken = json.loads(output["strictConfigJson"])
        target_page = next(page for page in broken["ui"]["pages"] if page.get("entity") in {table["name"] for table in broken["database"]["tables"]})
        target_page["components"][0]["dataSource"] = "missing_api"
        target_page["components"][0]["fieldBindings"] = ["hallucinated_field"]
        repaired, validation = validate_and_repair(broken, output["intent"])
        self.assertTrue(validation["guarantees"]["fieldLevelMappings"])
        self.assertTrue(any(action["code"] == "normalize_component_field_bindings" for action in validation["repairActions"]))
        repaired_page = next(page for page in repaired["ui"]["pages"] if page["id"] == target_page["id"])
        self.assertNotEqual(repaired_page["components"][0]["dataSource"], "missing_api")

    def test_conflicting_prompt_returns_clarification_metadata(self):
        output = compile_prompt("Create a booking app with no login, premium plans, admin analytics, and customer payments.")
        self.assertEqual(output["status"], "needs_clarification")
        self.assertTrue(output["validation"]["clarificationRequired"])
        self.assertTrue(output["config"]["clarificationQuestions"])

    def test_evaluation_dataset_runs(self):
        report = evaluate()
        self.assertEqual(report["datasetSize"], 20)
        self.assertGreaterEqual(report["successRate"], 0.9)
        self.assertGreaterEqual(report["runtimeExecutableRate"], 0.9)
        self.assertIn("latencyByStageMs", report)
        self.assertIn("repairTypes", report)
        self.assertIn("strictConfigHash", report["results"][0])
        self.assertGreaterEqual(report["bundleReadyRate"], 0.9)

    def test_runtime_bundle_zip_contains_artifacts(self):
        output = compile_prompt("Build a CRM with login, contacts, dashboard, and admin analytics.")
        payload = zip_runtime_bundle(output["config"])
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            names = archive.namelist()
        self.assertTrue(any(name.endswith("manifest.json") for name in names))
        self.assertTrue(any(name.endswith("schema.sql") for name in names))
        self.assertTrue(any(name.endswith("preview.html") for name in names))
        self.assertTrue(any(name.endswith("README.md") for name in names))


if __name__ == "__main__":
    unittest.main()
