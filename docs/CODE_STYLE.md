# Code Style

## General

- Simple over clever.
- Small functions.
- Clear naming.
- No duplicated services.
- No giant route files.
- No hidden side effects.
- No automatic expensive operations on page load.
- Destructive/high-risk actions stay disabled for the demo; do not make them merely confirmable.
- External side-effect actions must show exact missing capability/input reasons.
- Do not silently disable dangerous buttons.

## Backend

- Route files should stay thin.
- Services contain business logic.
- Repositories contain persistence logic only.
- Integrations isolate external APIs.
- Schemas define request/response contracts.
- Optional systems must fail gracefully.
- Return structured JSON errors.

## Command Planning And Tools

- Chat command planning belongs in dedicated planner/validator services, not route files.
- LLM output must be parsed into typed `CommandPlan`/step schemas before use.
- Never execute raw model-proposed tool calls.
- `CommandPlanValidator` should assign risk, required confirmation, and blocked reasons.
- Tool handlers should be small typed wrappers around existing services/connectors.
- Tool handlers should call existing connector/service methods instead of duplicating connector logic.
- Tool handlers must not own credentials or bypass connector auth/capability checks.
- Tool outputs should be sanitized before persistence or display.
- Side-effect tools must be idempotent where possible and must expose clear preview payloads.
- Destructive/high-risk tools should remain disabled unless a future decision explicitly enables them.

## Frontend

- Pages compose components.
- Components should be reusable.
- API calls belong in `services/api.ts`.
- Do not copy-paste request logic into pages.
- Display actual backend errors.
- Only show "backend offline" for network failure.
- Keep user-facing UI calm and not text-heavy.
- Dev page can be technical; Chat page should be clean.
- Keep connector-specific logic out of generic task components where possible; use services and capability contracts.

## Performance

- Do not run heavy checks on `/status`.
- Do not reindex automatically.
- Do not generate model responses during health checks.
- Keep context small by default.
