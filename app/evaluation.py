"""Evaluation harness with real prompts, edge cases, and repair metrics."""

from __future__ import annotations

import json
import hashlib
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Dict, List

from .modes import mode_profile, normalize_mode
from .pipeline import compile_prompt

ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "data" / "evaluation_prompts.json"


def load_dataset() -> List[Dict]:
    with DATASET_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def evaluate(write_path: str = "", mode: str = "balanced") -> Dict:
    mode_id = normalize_mode(mode)
    profile = mode_profile(mode_id)
    records = load_dataset()
    results = []
    issue_counter = Counter()
    repair_counter = Counter()
    status_counter = Counter()
    stage_latency = defaultdict(list)
    category_summary = defaultdict(lambda: {"total": 0, "ready": 0, "repairActions": 0, "latencies": []})

    for index, record in enumerate(records):
        # Every fifth prompt receives a synthetic missing-schema fault to prove targeted repair.
        repair_demo_fault = index % 5 == 4
        output = compile_prompt(record["prompt"], repair_demo_fault=repair_demo_fault, mode=mode_id)
        second_output = compile_prompt(record["prompt"], repair_demo_fault=repair_demo_fault, mode=mode_id)
        validation = output["validation"]
        execution = output["execution"]
        ready = output["status"] in {"ready", "needs_clarification"} and execution["ready"]
        repair_count = len(validation.get("repairActions", []))
        latency = output["pipeline"]["totalLatencyMs"]
        status_counter[output["status"]] += 1

        for stage in output["pipeline"]["stages"]:
            stage_latency[stage["stage"]].append(stage["latencyMs"])

        for issue in validation.get("issues", []):
            issue_counter[issue["code"]] += 1
        for repair in validation.get("repairActions", []):
            repair_counter[repair.get("code", "unknown_repair")] += 1

        category = record["category"]
        category_summary[category]["total"] += 1
        category_summary[category]["ready"] += 1 if ready else 0
        category_summary[category]["repairActions"] += repair_count
        category_summary[category]["latencies"].append(latency)

        results.append(
            {
                "id": record["id"],
                "category": category,
                "ready": ready,
                "status": output["status"],
                "latencyMs": latency,
                "stageLatencyMs": {stage["stage"]: stage["latencyMs"] for stage in output["pipeline"]["stages"]},
                "repairActions": repair_count,
                "repairCodes": [repair.get("code", "unknown_repair") for repair in validation.get("repairActions", [])],
                "issueCodes": [issue["code"] for issue in validation.get("issues", [])],
                "runtimeReady": execution["ready"],
                "sqliteReady": any(test["name"] == "sqlite_schema_executes" and test["passed"] for test in execution.get("smokeTests", [])),
                "bundleReady": execution.get("bundle", {}).get("ready", False),
                "bundleDirectory": execution.get("bundle", {}).get("directory", ""),
                "strictConfigHash": hashlib.sha256(output["strictConfigJson"].encode("utf-8")).hexdigest(),
                "deterministic": output["strictConfigJson"] == second_output["strictConfigJson"],
                "ambiguity": output["intent"]["ambiguity"]["level"],
            }
        )

    total = len(results)
    ready_count = sum(1 for result in results if result["ready"])
    repair_counts = [result["repairActions"] for result in results]
    latencies = [result["latencyMs"] for result in results]

    by_category = {}
    for category, summary in category_summary.items():
        by_category[category] = {
            "total": summary["total"],
            "successRate": round(summary["ready"] / summary["total"], 3),
            "averageRepairActions": round(summary["repairActions"] / summary["total"], 3),
            "averageLatencyMs": round(mean(summary["latencies"]), 3),
        }

    report = {
        "datasetSize": total,
        "mode": profile,
        "successRate": round(ready_count / total, 3),
        "validationPassRate": round(sum(1 for result in results if result["status"] != "blocked") / total, 3),
        "runtimeExecutableRate": round(sum(1 for result in results if result["runtimeReady"]) / total, 3),
        "sqliteExecutableRate": round(sum(1 for result in results if result["sqliteReady"]) / total, 3),
        "bundleReadyRate": round(sum(1 for result in results if result["bundleReady"]) / total, 3),
        "deterministicScore": round(sum(1 for result in results if result["deterministic"]) / total, 3),
        "averageLatencyMs": round(mean(latencies), 3),
        "latencyByStageMs": {stage: round(mean(values), 3) for stage, values in sorted(stage_latency.items())},
        "averageRepairActions": round(mean(repair_counts), 3),
        "maxRepairActions": max(repair_counts),
        "failureTypes": dict(issue_counter),
        "repairTypes": dict(repair_counter),
        "statusCounts": dict(status_counter),
        "byCategory": by_category,
        "costQualityTradeoff": {
            "currentMode": "deterministic local compiler",
            "llmCallsPerPrompt": 0,
            "why": "The demo avoids network/model variability so reviewers can test determinism. The stage boundaries are ready for LLM adapters later.",
            "qualityGuardrail": "Validation + repair is mandatory before runtime simulation.",
            "latencyGuardrail": "No full blind retries; only targeted repair of the failed contract.",
            "dependencyStrategy": "Python stdlib contracts keep setup friction low while still enforcing typed artifacts.",
            "mode": profile["label"],
            "validationDepth": profile["validationDepth"],
            "reliabilityScore": profile["reliabilityScore"],
        },
        "results": results,
    }

    if write_path:
        with Path(write_path).open("w", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2, sort_keys=True)
    return report


if __name__ == "__main__":
    destination = ROOT / "appcompilerai-evaluation.json"
    report = evaluate(str(destination))
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"\nSaved report to {destination}")
