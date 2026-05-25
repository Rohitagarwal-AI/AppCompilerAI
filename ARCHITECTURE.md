# AppCompilerAI Architecture

## Summary

AppCompilerAI is organized as a deterministic compiler pipeline. Each stage has a narrow responsibility, emits a structured artifact, and is checked by the validation/runtime gates before the UI or bundle presents it as ready.

## Stages

1. `intentExtractionStage`
   - Input: raw natural-language product prompt
   - Output: normalized intent IR with domains, features, entities, roles, ambiguity, and conflicts

2. `systemDesignStage`
   - Input: intent IR
   - Output: architecture plan with pages, flows, assumptions, and clarification questions

3. `schemaGenerationStage`
   - Input: intent + design
   - Output: strict app config containing UI, API, database, auth, and business rules
   - API payloads are field-level schemas, not symbolic prompt text

4. `consistencyValidationStage`
   - Input: generated config
   - Output: deterministic cross-layer edits before validation

5. `repairStage`
   - Input: refined config
   - Output: repaired config plus structured validation report
   - Repairs are local actions with `code`, `path`, `before`, `after`, `stage`, and `reason`

6. `runtimeSimulationStage`
   - Input: validated config
   - Output: route map, API handlers, SQL migration, bundle files, manifest checks, and smoke tests

## Contract Strategy

The project uses Python 3.11 stdlib dataclasses in `app/contracts.py`.

This keeps the demo easy to run while still providing explicit contracts for:

- Intent IR
- System design
- App config
- UI pages/components
- API endpoints
- Database tables/fields
- Auth roles
- Business rules
- Validation issues
- Repair actions
- Runtime proof
- Evaluation reports

The public API remains JSON dictionaries so the browser UI and local server stay simple.

## Public App Contract

Each compile exposes a production-style public contract:

- `app`
- `intent`
- `entities`
- `roles`
- `database`
- `api`
- `ui`
- `auth`
- `businessLogic`
- `payments`
- `assumptions`
- `clarifications`
- `runtimePlan`
- `metadata`

## Validation Gates

Validation checks include:

- Required top-level schema sections
- Duplicate tables, fields, endpoints, and routes
- Invalid HTTP methods and malformed paths
- UI required APIs and component data sources
- UI field bindings against database fields
- API request/response fields against database fields
- Foreign-key targets
- Auth role endpoint permissions
- Admin access coverage
- Business-rule dependencies
- Prompt conflicts such as no-login plus admin roles or free-only plus premium payments

Unrecoverable errors become `blocked`. Ambiguous or conflicting but executable outputs become `needs_clarification`.

## Runtime Proof

The runtime bundle gate verifies:

- Generated SQL executes in SQLite with foreign keys enabled
- Manifest contains required sections and passes contract validation
- Bundle has required files
- UI/API links resolve
- At least one renderable route exists
- Auth role matrix exists
- Dashboard widgets can fetch from valid entities/APIs
- Payment checkout and premium gating can be evaluated
- RBAC can be enforced from the access matrix

## Cost/Quality Modes

- Fast Mode: required contracts and core runtime checks.
- Balanced Mode: field-level cross-layer checks, targeted repair, SQLite, manifest, and bundle proof.
- Strict Mode: deeper policy checks and extended smoke tests for final production-style configs.

The ZIP endpoint refuses to return a bundle if runtime proof fails.

## Evaluation

The evaluation harness runs 20 prompts:

- 10 realistic product prompts
- 10 edge cases covering vagueness, missing details, conflicting requirements, premium gating, and role ambiguity

Metrics include:

- Success rate
- Runtime executable rate
- SQLite executable rate
- Bundle ready rate
- Repairs per request
- Repair types
- Failure categories
- Latency by stage
- Deterministic strict JSON hash per prompt

## Cost Vs Quality Tradeoff

The demo currently uses zero LLM calls by design. This makes the internship submission deterministic, free, and reproducible.

The architecture is still LLM-ready: a future model adapter can replace one or more generation stages, while the typed contracts, validation repair, runtime gate, and evaluation harness remain the control system around it.
