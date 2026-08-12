"""wb.* schema DDL seam (schema-per-quadrant, Decision #4).

Phase 7 (Workbench, SWE owner) fills in the real idempotent DDL body (P1 left this an empty-
string stub) — `ensure_all_schemas()` (Phase 3, `studio_app.core.schema`) direct-imports this
module and calls `ddl()`; this file is edited ONLY here, never `apps/studio` (antichain,
plan.md "Dependency matrix & file-ownership").

`wb.recipes` — one row per (agent_id, tenant_id, version): the recipe (R-SPEC A1#1) as stored JSONB
(the wire shape workbench validates through `studio_contracts.Recipe`, never a workbench-local
type) + a `status` lifecycle column (`draft`/`published`/`rolled_back`, spec-only for now — the
concrete state machine lands with `publish.py`'s real implementation).

D11 fix: `tenant` was `TEXT` (pre-D-13 slug), now `tenant_id UUID` to match
`studio_contracts.recipe.Recipe.tenant_id` — the contract this table stores rows FOR already
made this switch; the DDL had drifted behind it since no code writes here yet (`publish()` is
still a stub).

`wb.recipe_versions` — append-only history: every version of a recipe that was ever published,
so `publish.rollback()` (spec stub this phase) has something to roll back TO. `recipe_id`
references `wb.recipes` within the SAME schema (same-schema FK is fine; the "no cross-schema FK"
rule from `core.jobs`/`core.outbox` — R-SPEC A1, Decision #4 — is about FKs crossing schema
boundaries, not same-schema ones).

RLS (kit#117, Q7 — signed off via `packages/kb/docs/mini-rfc-tenant-schema-unify.md` item B):
both tables hold tenant IP (`agent_config.instructions`, `kb_binding.scope`) with a real user-read
path once `publish()`/`rollback()` land, so they get the same fence `kb.chunks` already has
(`studio_kb/schema.py`) — `ENABLE`+`FORCE ROW LEVEL SECURITY` plus a `USING`+`WITH CHECK` policy
keyed off `NULLIF(current_setting('app.tenant_id', true), '')::uuid`: an unset/empty session
resolves to `NULL`, and `tenant_id = NULL` is never true, so it fail-closed sees/writes 0 rows
rather than raising or leaking. `FORCE` makes this bite `studio_owner` too, not only `studio_app`
— matters here because `ensure_all_schemas()` runs this DDL via the admin pool.

Idempotent throughout (`CREATE SCHEMA/TABLE IF NOT EXISTS`) — safe to call twice, which is what
`packages/workbench/tests/test_schema.py::test_wb_ddl_idempotent` locks.
"""

from __future__ import annotations

_WB_DDL = """
CREATE SCHEMA IF NOT EXISTS wb;

CREATE TABLE IF NOT EXISTS wb.recipes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id TEXT NOT NULL,
    tenant_id UUID NOT NULL,
    recipe JSONB NOT NULL,
    version INT NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (agent_id, tenant_id, version)
);

CREATE TABLE IF NOT EXISTS wb.recipe_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recipe_id UUID NOT NULL REFERENCES wb.recipes (id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,
    tenant_id UUID NOT NULL,
    recipe JSONB NOT NULL,
    version INT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE wb.recipes ENABLE ROW LEVEL SECURITY;
ALTER TABLE wb.recipes FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS wb_recipes_tenant_isolation ON wb.recipes;
CREATE POLICY wb_recipes_tenant_isolation ON wb.recipes
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE wb.recipe_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE wb.recipe_versions FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS wb_recipe_versions_tenant_isolation ON wb.recipe_versions;
CREATE POLICY wb_recipe_versions_tenant_isolation ON wb.recipe_versions
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
"""


def ddl() -> str:
    """Return this quadrant's idempotent DDL (`wb.recipes` + `wb.recipe_versions`)."""
    return _WB_DDL
