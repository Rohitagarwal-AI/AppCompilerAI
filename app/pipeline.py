"""Orchestrates the compiler-style app generation pipeline."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Dict, List

from .contracts import validate_config_contract, validate_design_contract, validate_intent_contract
from .design import design_system
from .generator import generate_config
from .intent import extract_intent
from .modes import mode_profile, normalize_mode
from .refinement import refine_config
from .runtime import simulate_runtime
from .utils import now_ms, stable_id
from .validator import validate_and_repair


def _timed(fn, *args):
    started = now_ms()
    value = fn(*args)
    return value, round(now_ms() - started, 3)


def _stage(
    name: str,
    input_summary: Dict[str, Any],
    output_summary: Dict[str, Any],
    latency_ms: float,
    issues: List[Dict[str, Any]] | None = None,
    repairs: List[Dict[str, Any]] | None = None,
    confidence: float = 0.9,
) -> Dict[str, Any]:
    issues = issues or []
    repairs = repairs or []
    status = "failed" if any(issue.get("blocking") or issue.get("severity") == "critical" for issue in issues) else "repaired" if repairs else "success"
    return {
        "stage": name,
        "stageName": name,
        "input": input_summary,
        "output": output_summary,
        "status": status,
        "latencyMs": latency_ms,
        "issues": issues,
        "repairActions": repairs,
        "confidenceScore": round(max(0.0, min(1.0, confidence)), 3),
    }


def _config_summary(config: Dict) -> Dict[str, Any]:
    return {
        "entities": len(config.get("entities", [])),
        "tables": len(config.get("database", {}).get("tables", [])),
        "endpoints": len(config.get("api", {}).get("endpoints", [])),
        "pages": len(config.get("ui", {}).get("pages", [])),
        "roles": len(config.get("auth", {}).get("roles", [])),
        "businessRules": len(config.get("businessLogic", {}).get("rules", [])),
        "paymentsEnabled": bool(config.get("payments", {}).get("enabled")),
    }


def _readiness_score(status: str, validation: Dict, runtime: Dict, mode: str) -> int:
    score = mode_profile(mode)["reliabilityScore"]
    score -= len([issue for issue in validation.get("issues", []) if issue.get("severity") == "high"]) * 3
    score -= len([issue for issue in validation.get("issues", []) if issue.get("severity") == "critical"]) * 10
    if validation.get("clarificationRequired"):
        score -= 6
    if not runtime.get("ready"):
        score -= 25
    if status == "blocked":
        score = min(score, 45)
    return max(0, min(100, int(score)))


def _inject_repair_demo_fault(config: Dict) -> Dict:
    """Used by evaluation/UI to prove targeted repair without corrupting normal output."""
    broken = deepcopy(config)
    tables = broken.get("database", {}).get("tables", [])
    if tables:
        tables.pop()
    if broken.get("ui", {}).get("pages"):
        broken["ui"]["pages"][0].setdefault("requiredApis", []).append("list_missing_demo")
    if broken.get("entities"):
        broken["entities"].append(deepcopy(broken["entities"][0]))
    return broken


def compile_prompt(prompt: str, repair_demo_fault: bool = False, mode: str = "balanced") -> Dict:
    mode_id = normalize_mode(mode)
    profile = mode_profile(mode_id)
    stage_contracts: Dict[str, List[Dict[str, Any]]] = {}
    trace: List[Dict[str, Any]] = []

    intent, latency = _timed(extract_intent, prompt)
    intent_issues = validate_intent_contract(intent)
    stage_contracts["intentExtractionStage"] = intent_issues
    trace.append(
        _stage(
            "intentExtractionStage",
            {"promptChars": len(prompt), "mode": mode_id},
            {
                "domains": intent.get("domains", []),
                "features": intent.get("features", []),
                "entities": intent.get("entities", []),
                "ambiguity": intent.get("ambiguity", {}).get("level"),
                "conflicts": len(intent.get("conflicts", [])),
            },
            latency,
            intent_issues,
            confidence=0.95 if intent.get("ambiguity", {}).get("level") == "low" else 0.78,
        )
    )

    design, latency = _timed(design_system, intent)
    design_issues = validate_design_contract(design)
    stage_contracts["systemDesignStage"] = design_issues
    trace.append(
        _stage(
            "systemDesignStage",
            {"intentId": intent["id"], "entities": intent.get("entities", [])},
            {
                "pages": len(design.get("pages", [])),
                "flows": len(design.get("flows", [])),
                "assumptions": len(design.get("assumptions", [])),
                "clarifications": len(design.get("clarificationQuestions", [])),
            },
            latency,
            design_issues,
            confidence=0.92,
        )
    )

    config, latency = _timed(generate_config, intent, design)
    config.setdefault("metadata", {})["compilerMode"] = mode_id
    config.setdefault("compiler", {})["qualityMode"] = profile
    generation_issues = validate_config_contract(config, "schema_generation")
    stage_contracts["schemaGenerationStage"] = generation_issues
    trace.append(
        _stage(
            "schemaGenerationStage",
            {"designPages": len(design.get("pages", [])), "designEntities": design.get("entities", [])},
            _config_summary(config),
            latency,
            generation_issues,
            confidence=0.9,
        )
    )

    refined, latency = _timed(refine_config, config, intent, design)
    refined.setdefault("metadata", {})["compilerMode"] = mode_id
    if repair_demo_fault:
        refined = _inject_repair_demo_fault(refined)
    consistency_issues = validate_config_contract(refined, "consistency_validation")
    stage_contracts["consistencyValidationStage"] = consistency_issues
    trace.append(
        _stage(
            "consistencyValidationStage",
            _config_summary(config),
            {
                "contractIssues": len(consistency_issues),
                "policy": refined.get("refinement", {}).get("policy"),
                "repairDemoFault": repair_demo_fault,
            },
            latency,
            consistency_issues,
            confidence=0.88 if consistency_issues else 0.94,
        )
    )

    started = now_ms()
    repaired, validation = validate_and_repair(refined, intent, mode=mode_id)
    repair_latency = round(now_ms() - started, 3)
    trace.append(
        _stage(
            "repairStage",
            {"issuesBeforeRepair": len(consistency_issues), "mode": mode_id},
            {
                "validationStatus": validation.get("status"),
                "issues": len(validation.get("issues", [])),
                "repairs": len(validation.get("repairActions", [])),
                "clarificationRequired": validation.get("clarificationRequired", False),
            },
            repair_latency,
            validation.get("issues", []),
            validation.get("repairActions", []),
            confidence=0.93 if validation.get("guarantees", {}).get("crossLayerConsistency") else 0.62,
        )
    )

    runtime, latency = _timed(simulate_runtime, repaired, mode_id)
    trace.append(
        _stage(
            "runtimeSimulationStage",
            _config_summary(repaired),
            {
                "ready": runtime.get("ready"),
                "routes": len(runtime.get("routeMap", [])),
                "apiHandlers": len(runtime.get("apiHandlers", [])),
                "smokeTests": len(runtime.get("smokeTests", [])),
                "bundleReady": runtime.get("bundle", {}).get("ready", False),
            },
            latency,
            [test for test in runtime.get("smokeTests", []) if not test.get("passed")],
            confidence=0.96 if runtime.get("ready") else 0.45,
        )
    )
    repaired["execution"] = runtime

    total_latency = round(sum(item["latencyMs"] for item in trace), 3)
    contract_issue_count = sum(len(issues) for issues in stage_contracts.values())
    if not runtime["ready"] or validation["status"] == "blocked":
        status = "blocked"
    elif validation.get("clarificationRequired"):
        status = "needs_clarification"
    else:
        status = "ready"
    repaired.setdefault("metadata", {})["status"] = status
    repaired.setdefault("metadata", {})["compileMode"] = mode_id
    strict_json = json.dumps(repaired, indent=2, sort_keys=True)
    config_hash = hashlib.sha256(strict_json.encode("utf-8")).hexdigest()
    score = _readiness_score(status, validation, runtime, mode_id)
    stage_contract_report = {
        stage: {
            "passed": not issues,
            "issueCount": len(issues),
            "issues": issues,
        }
        for stage, issues in stage_contracts.items()
    }
    legacy_stage_aliases = {
        "intent_extraction": "intentExtractionStage",
        "system_design": "systemDesignStage",
        "schema_generation": "schemaGenerationStage",
        "refinement": "consistencyValidationStage",
        "validation_repair": "repairStage",
        "runtime_simulation": "runtimeSimulationStage",
    }
    for legacy_name, stage_name in legacy_stage_aliases.items():
        stage_contract_report[legacy_name] = stage_contract_report.get(stage_name, {"passed": True, "issueCount": 0, "issues": []})

    return {
        "compileId": stable_id("compile", f"{mode_id}:{prompt}"),
        "status": status,
        "score": score,
        "mode": profile,
        "pipeline": {
            "stages": trace,
            "trace": trace,
            "totalLatencyMs": total_latency,
            "retryStrategy": "targeted_repair_only",
            "fullRetries": 0,
            "schemaStrategy": "stdlib_dataclasses",
            "stageContracts": stage_contract_report,
            "contractIssueCount": contract_issue_count,
            "deterministicHash": config_hash,
        },
        "intent": intent,
        "design": design,
        "config": repaired,
        "validation": validation,
        "execution": runtime,
        "costQuality": {
            "mode": profile,
            "estimatedCost": profile["estimatedCost"],
            "latency": profile["estimatedLatency"],
            "reliabilityScore": profile["reliabilityScore"],
            "validationDepth": profile["validationDepth"],
            "tradeoff": profile["description"],
        },
        "strictConfigJson": strict_json,
    }
