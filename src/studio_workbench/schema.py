"""wb.* schema DDL seam (schema-per-quadrant, Decision #4).

Phase 7 (Workbench, SWE owner) fills in the real idempotent DDL body (P1 left this an empty-
string stub) — `ensure_all_schemas()` (Phase 3, `studio_app.core.schema`) direct-imports this
module and calls `ddl()`; this file is edited ONLY here, never `apps/studio` (antichain,
plan.md "Dependency matrix & file-ownership").

`wb.recipes` — one row per (agent_id, tenant, version): the recipe (R-SPEC A1#1) as stored JSONB
(the wire shape workbench validates through `studio_contracts.Recipe`, never a workbench-local
type) + a `status` lifecycle column (`draft`/`published`/`rolled_back`, spec-only for now — the
concrete state machine lands with `publish.py`'s real implementation).

`wb.recipe_versions` — append-only history: every version of a recipe that was ever published,
so `publish.rollback()` (spec stub this phase) has something to roll back TO. `recipe_id`
references `wb.recipes` within the SAME schema (same-schema FK is fine; the "no cross-schema FK"
rule from `core.jobs`/`core.outbox` — R-SPEC A1, Decision #4 — is about FKs crossing schema
boundaries, not same-schema ones).

Idempotent throughout (`CREATE SCHEMA/TABLE IF NOT EXISTS`) — safe to call twice, which is what
`packages/workbench/tests/test_schema.py::test_wb_ddl_idempotent` locks.
"""

from __future__ import annotations

_WB_DDL = """
CREATE SCHEMA IF NOT EXISTS wb;

CREATE TABLE IF NOT EXISTS wb.recipes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id TEXT NOT NULL,
    tenant TEXT NOT NULL,
    recipe JSONB NOT NULL,
    version INT NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (agent_id, tenant, version)
);

CREATE TABLE IF NOT EXISTS wb.recipe_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recipe_id UUID NOT NULL REFERENCES wb.recipes (id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    tenant TEXT NOT NULL,
    recipe JSONB NOT NULL,
    version INT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def ddl() -> str:
    """Return this quadrant's idempotent DDL (`wb.recipes` + `wb.recipe_versions`)."""
    return _WB_DDL
