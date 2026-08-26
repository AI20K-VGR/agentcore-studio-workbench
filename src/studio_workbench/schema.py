"""wb.* schema DDL seam (schema-per-quadrant, Decision #4).

Phase 7 (Workbench, SWE owner) fills in the real idempotent DDL body (P1 left this an empty-
string stub) — `ensure_all_schemas()` (Phase 3, `studio_app.core.schema`) direct-imports this
module and calls `ddl()`; this file is edited ONLY here, never `apps/studio` (antichain,
plan.md "Dependency matrix & file-ownership").

`wb.recipes` — one row per (agent_id, tenant_id, version): the recipe (R-SPEC A1#1) as stored JSONB
(the wire shape workbench validates through `studio_contracts.Recipe`, never a workbench-local
type) + a `status` lifecycle column (`draft`/`published`/`rolled_back`, spec-only for now — the
concrete state machine lands with `publish.py`'s real implementation) + `recipe_hash` (DEC-03,
`publish.recipe_hash()`) — the SAME value `Scorecard.recipe_hash` carried at publish time, stored
alongside the `recipe` JSONB it was computed from. **Not necessarily** byte-identical to what was
hashed: `publish()` writes `recipe` via `Recipe.model_dump_json(by_alias=True)` (fixed in
workbench#30 — before that PR it omitted `by_alias`, so `Edge.from_` serialized as `"from_"`
instead of the wire alias `"from"`), while `recipe_hash()` hashes `model_dump(mode="json",
by_alias=True)` with sorted keys (see `publish.py`'s module docstring). Rows published before
workbench#30 still carry the pre-fix (no-alias) shape — this table's contents are mixed across that
boundary. Either way, verifying a row means recomputing
`publish.recipe_hash(Recipe.model_validate(row["recipe"]))` from the reconstructed object (safe:
`Edge.populate_by_name=True` accepts both the aliased and unaliased key on input), never a raw
byte/string comparison against the stored JSONB directly.

engine#49 review F-minor (dholmes0207, backfill-script PR) — this recompute-and-compare procedure
FAILS BY DESIGN for any row `apps/studio/scripts/backfill_kb_search_whitelist.py` has patched:
that script deliberately keeps the OLD `recipe_hash` on touched rows (same accepted trade-off as
the `instructions`→`system_prompt` rename below, DEC-2) while the `recipe` JSONB content changes.
A "mismatch" on a backfilled row is expected, not evidence of corruption — cross-check
`updated_at` (bumped by the backfill) or the script's own printed log before treating a mismatch
as a real problem.

`updated_at` is a `wb.recipes`-only signal — `wb.recipe_versions` is append-only and has no such
column (see its `CREATE TABLE` below), and the backfill patches BOTH tables. When checking a
`wb.recipe_versions` row, the script's printed log is the only cross-check available.

`NULL` for any row published before this column existed. `eval.scorecards` (a DIFFERENT quadrant,
`packages/evalhub`) has no writer yet and no `recipe_hash` column of its own — tracked as
`agentcore-studio-evalhub#28`, out of scope here.

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
both tables hold tenant IP (`agent_config.system_prompt`, `kb_binding.scope`) with a real user-read
path once `publish()`/`rollback()` land, so they get the same fence `kb.chunks` already has
(`studio_kb/schema.py`) — `ENABLE`+`FORCE ROW LEVEL SECURITY` plus a `USING`+`WITH CHECK` policy
keyed off `NULLIF(current_setting('app.tenant_id', true), '')::uuid`: an unset/empty session
resolves to `NULL`, and `tenant_id = NULL` is never true, so it fail-closed sees/writes 0 rows
rather than raising or leaking. `FORCE` makes this bite `studio_owner` too, not only `studio_app`
— matters here because `ensure_all_schemas()` runs this DDL via the admin pool.

Idempotent throughout (`CREATE SCHEMA/TABLE IF NOT EXISTS`) — safe to call twice, which is what
`packages/workbench/tests/test_wb_schema.py::test_wb_ddl_idempotent` locks.

`wb.conversations` / `wb.conversation_messages` (workbench#49, `kit#240` tracking issue —
multi-turn chat history + context-window control for the chat agent): storage-only half of that
flow. `POST /chat` today only ever writes `obs.trace_events` (audit, keyed by run/node) — there is
no per-turn Q/A record keyed by a `conversation_id` that a caller can read back sequentially (UI
re-hydrate on page reload, `apps/web#28`) or replay into the next turn's prompt (`history` param,
`engine#47`, a pure function change with no DB access of its own). `wb.conversations` is the
parent row (one per chat session, `agent_id` + `tenant_id`); `wb.conversation_messages` is one row
per turn, `UNIQUE (conversation_id, turn_index)` so `apps/studio#74`'s write path can safely reject
two concurrent requests racing to write the same turn number instead of silently duplicating it.
`run_id` (nullable) is a soft back-reference to `obs.trace_events.run_id` for that turn — audit
convenience only, not a FK (an `obs` row can be pruned/rotated independently of chat history).
`citations` is `JSONB` (nullable) — shape owned by whatever `apps/studio#74` writes there, not by
this schema.

Same RLS fence as `wb.recipes` above (`ENABLE`+`FORCE ROW LEVEL SECURITY`, tenant-keyed
`USING`/`WITH CHECK` policy) — both tables hold real conversation content per tenant. This DDL is
schema-only: no `apps/studio`/`engine` code reads or writes these tables yet (that lands in the
sibling sub-issues once this lands and its pointer bumps in `kit`).
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
    recipe_hash TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
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
    recipe_hash TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Đường thứ hai cho DB đã tồn tại từ trước cột này (cùng khuôn `is_active`/`password_changed_at`
-- ở `apps/studio/core/schema.py`) — `CREATE TABLE IF NOT EXISTS` ở trên là no-op trên bảng đã có.
-- `NULL` (không `NOT NULL`) — khớp đúng kiểu Python `Scorecard.recipe_hash: str | None`
-- (`studio_contracts.scorecard`), và giữ migration này an toàn vô điều kiện trên bảng đã có row,
-- không cần hỏi "row cũ nhận giá trị gì" như khuôn `NOT NULL` các cột khác trong file này đã đặt ra.
ALTER TABLE wb.recipes ADD COLUMN IF NOT EXISTS recipe_hash TEXT NULL;
ALTER TABLE wb.recipe_versions ADD COLUMN IF NOT EXISTS recipe_hash TEXT NULL;

-- Team ERD (docs/design/ERD.png) đặt sẵn cột này cho wb.recipes — cùng đường thứ hai như
-- recipe_hash ở trên cho DB đã tồn tại từ trước.
ALTER TABLE wb.recipes ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

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

CREATE TABLE IF NOT EXISTS wb.conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    agent_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS wb.conversation_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES wb.conversations (id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,
    turn_index INT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    citations JSONB,
    run_id TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (conversation_id, turn_index)
);

ALTER TABLE wb.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE wb.conversations FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS wb_conversations_tenant_isolation ON wb.conversations;
CREATE POLICY wb_conversations_tenant_isolation ON wb.conversations
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);

ALTER TABLE wb.conversation_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE wb.conversation_messages FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS wb_conversation_messages_tenant_isolation ON wb.conversation_messages;
CREATE POLICY wb_conversation_messages_tenant_isolation ON wb.conversation_messages
    USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid);
"""


def ddl() -> str:
    """Return this quadrant's idempotent DDL (`wb.recipes` + `wb.recipe_versions` +
    `wb.conversations` + `wb.conversation_messages`)."""
    return _WB_DDL
