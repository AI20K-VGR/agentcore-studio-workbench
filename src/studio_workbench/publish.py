"""Publish / rollback flow seam (R-SPEC A4 :72) — bút SWE.

`publish(recipe, scorecard, conn)` wires, in order:

1. `studio_workbench.validator.graph_lint(recipe)` — a recipe that fails graph-lint is never
   published (R-SPEC A1#1: "recipe không qua validator = không interpret" applies to Publish
   too, not only the interpreter). `ValueError` propagates unchanged.
2. `scorecard.recipe_hash is None` fail-closed (kit#117): `Scorecard.recipe_hash`'s own docstring
   requires treating "cannot verify which recipe this certifies" as REFUSE, never "probably
   fine". Every real `Scorecard` carries `recipe_hash=None` until AIE-2 wires a producer
   (`DEC-03`) — until then `publish()` always refuses here, which is the correct, documented
   behavior, not a bug.
3. `scorecard.gate.verdict` (`studio_contracts.Scorecard`, owned/rendered by AIE-2) —
   `verdict == "FAIL"` is a HARD gate (INV-6), never advisory-only: Publish is blocked and the
   PREVIOUSLY published version is re-asserted live via `rollback()`. SWE only WIRES this gate —
   reading `gate.verdict` and branching on it — it does NOT own computing the Scorecard's
   `results`/`aggregate`, nor the judge/eval-harness that produces them (AIE-2 owns rendering the
   scorecard itself; R-SPEC A4 :72). `gate.verdict` is already branch-agnostic by the time it
   reaches here — this function never reads `CaseResult.judge` and so never needs to know whether
   a case was scored by the judge branch or the exact-match branch (kit#117's "không vỡ khi tụt
   nấc" is satisfied structurally: there is nothing here that COULD break on a tier fallback,
   because nothing here looks at which tier scored a case).
4. On PASS: write the new version into `wb.recipes` + `wb.recipe_versions` (DDL in `schema.py`)
   and flip the "named endpoint" — no separate endpoint table exists anywhere in the 5 schemas
   (`docs/test-design/GUIDE-B-recipe.md` §4.5), so the convention here is: exactly one
   `wb.recipes` row per `(agent_id, tenant_id)` carries `status='published'` at a time; the
   previous holder (if any) flips to `'draft'`. Enforcing that at MOST one row is ever
   `'published'` under concurrent publishes (partial unique index / advisory lock) is Q4 in the
   guide's register — an open, unresolved question, out of scope for this implementation.

`recipe_hash(recipe)` (DEC-03, tracked `agentcore-studio-evalhub/docs/decisions/scorecard.md` —
overdue since D12, closed here) is the missing producer `Scorecard.recipe_hash` needed all along:
`studio_evalhub.compute.compute_scorecard`/`EvalHarness.run` have carried an OPTIONAL
`recipe_hash: str | None = None` kwarg since D20 (`DEC-D20-02`) and thread it straight through —
but no caller on the real path ever COMPUTED a value, so every real `Scorecard` shipped with
`recipe_hash=None` and `publish()`'s own fail-closed rule (line ~72 below) refused every single
call. Lives here, not in `studio_evalhub`, for two independent reasons: (1) `test_src_khong_tu_dan_
xuat_recipe_hash` (evalhub, AST-guard) forbids `hashlib`/`model_dump_json()` inside
`src/studio_evalhub/` outright — evalhub may only RECEIVE a hash, never derive one (`DEC-D20-02`);
(2) `Recipe`'s canonical byte-form is inherently a `studio_contracts`/`studio_workbench` question
(this package already owns every other `Recipe`-shape operation — `builder.py`, `canvas.py`), not
an eval-harness one.

**Canonical form: `sha256(recipe.model_dump_json(by_alias=True))`.** `by_alias=True` is not
decorative — `Edge.from_` carries `Field(alias="from")` (`recipe.py` F12), so
`model_dump_json()` (no alias) and `model_dump_json(by_alias=True)` serialize the SAME recipe to
TWO DIFFERENT byte strings, which would make the hash depend on which serializer flag the caller
happened to use rather than on the recipe's content — always forcing `by_alias=True` here is what
makes the hash a function of the recipe alone. Pydantic v2 serializes `BaseModel` fields in
declared-field order (not sorted), so two `Recipe` objects built from equal data always dump to
byte-identical JSON — no manual key-sorting needed for determinism within one contract version.

**Known, accepted limitation, stated rather than hidden (same posture as `DEC-D20-02`'s own
docstring on this exact point):** this hash is a WRITE-time value only — computed once at publish
time and stored verbatim in `Scorecard.recipe_hash`/`wb.recipes`, never recomputed to verify an
older row later. If `Recipe` ever gains a new field, hashes computed under the new schema will
differ from hashes computed under the old one for what a human would call "the same recipe" — this
is only a problem for a FUTURE re-verify-by-recomputing feature, which does not exist today; it is
not a problem for the current publish/gate pipeline, which only ever compares a hash to itself
within a single call (`compute_scorecard` → `publish`), never recomputes one from stored JSON.

`conn: DbConnection` (kit#117, Q5; `protocols.py` in this same package — deliberately NOT
promoted to `studio_contracts`, see that module's docstring for why) is a single connection the
CALLER already bound to the request's tenant (`SET LOCAL app.tenant_id`, e.g. via `apps/studio`'s
`get_request_connection()`) — never a raw pool. `studio_workbench` cannot import `studio_app`
(`.importlinter`); accepting only an already-bound connection (rather than a pool this module
could use to open its OWN, unbound connection) makes the failure mode
`docs/test-design/GUIDE-B-recipe.md` §4.5/§11 (row B-P01) warns about structurally unreachable
from inside this function.

`rollback(agent_id, tenant_id, *, to_version, conn)` restores the named endpoint for
`(agent_id, tenant_id)` back to a prior `wb.recipe_versions` row, read by content (not just
version number — `wb.recipe_versions` has no `UNIQUE (agent_id, tenant_id, version)` constraint,
unlike `wb.recipes`, so two rows CAN share a version number; the most recent `created_at` wins).
`tenant_id` is `UUID` (D-13), matching both `schema.py`'s `wb.recipes.tenant_id` column and
`studio_contracts.recipe.Recipe.tenant_id`.

RLS on `wb.*` (kit#117, Q7) means an unbound/wrong-tenant `conn` sees and writes 0 rows rather
than raising — the queries below rely on that fence, not on an explicit `tenant_id` check of
their own, being the sole protection (defense-in-depth: both the `WHERE tenant_id = ...`
predicates AND the policy must independently hold).
"""

from __future__ import annotations

import hashlib
from uuid import UUID

from studio_contracts import Recipe, Scorecard

from studio_workbench.protocols import DbConnection
from studio_workbench.validator import graph_lint


def recipe_hash(recipe: Recipe) -> str:
    """Producer for `Scorecard.recipe_hash` (DEC-03) — `sha256(recipe.model_dump_json(by_alias=
    True)).hexdigest()`. See module docstring for why `by_alias=True` is mandatory and why this
    lives here rather than in `studio_evalhub`. Pure/deterministic: same recipe content always
    yields the same hash, no I/O, no randomness — safe to call as many times as needed."""
    canonical = recipe.model_dump_json(by_alias=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def publish(recipe: Recipe, scorecard: Scorecard, conn: DbConnection) -> None:
    """Validate `recipe` (via `graph_lint`), gate-check it against `scorecard.gate.verdict` and
    `scorecard.recipe_hash`, then publish it to the named endpoint. `verdict == "FAIL"` (or a
    missing `recipe_hash`) blocks publish and triggers a `rollback()` re-assertion of whichever
    version was already live. Raises `ValueError` on any rejection — never returns a boolean/
    report object, matching `graph_lint`'s own convention.
    """
    graph_lint(recipe)

    if scorecard.recipe_hash is None:
        raise ValueError(
            f"publish: scorecard.recipe_hash is None for agent_id={recipe.agent_id!r} — cannot "
            "verify which recipe this Scorecard certifies (DEC-03 has no producer yet); refusing"
        )

    if scorecard.gate.verdict == "FAIL":
        await _reassert_last_published(recipe.agent_id, recipe.tenant_id, conn)
        raise ValueError(
            f"publish: gate.verdict='FAIL' for agent_id={recipe.agent_id!r} tenant_id={recipe.tenant_id} "
            "— blocked (INV-6); previously published version re-asserted live"
        )

    cursor = await conn.execute(
        "SELECT COALESCE(MAX(version), 0) FROM wb.recipes WHERE agent_id = %s AND tenant_id = %s",
        (recipe.agent_id, recipe.tenant_id),
    )
    row = await cursor.fetchone()
    next_version = (row[0] if row is not None else 0) + 1

    await conn.execute(
        "UPDATE wb.recipes SET status = 'draft' WHERE agent_id = %s AND tenant_id = %s AND status = 'published'",
        (recipe.agent_id, recipe.tenant_id),
    )

    recipe_json = recipe.model_dump_json()
    cursor = await conn.execute(
        """
        INSERT INTO wb.recipes (agent_id, tenant_id, recipe, version, status, recipe_hash)
        VALUES (%s, %s, %s::jsonb, %s, 'published', %s)
        RETURNING id
        """,
        (recipe.agent_id, recipe.tenant_id, recipe_json, next_version, scorecard.recipe_hash),
    )
    inserted = await cursor.fetchone()
    if inserted is None:
        raise RuntimeError(
            "publish: INSERT INTO wb.recipes did not return an id — RLS policy likely rejected the write"
        )
    recipe_row_id = inserted[0]

    await conn.execute(
        """
        INSERT INTO wb.recipe_versions (recipe_id, agent_id, tenant_id, recipe, version, status, recipe_hash)
        VALUES (%s, %s, %s, %s::jsonb, %s, 'published', %s)
        """,
        (recipe_row_id, recipe.agent_id, recipe.tenant_id, recipe_json, next_version, scorecard.recipe_hash),
    )


async def rollback(agent_id: str, tenant_id: UUID, *, to_version: int, conn: DbConnection) -> None:
    """Roll the named endpoint for `(agent_id, tenant_id)` back to `to_version`, read by content
    from `wb.recipe_versions` history (tie-broken on most recent `created_at` — see module
    docstring). Raises `ValueError` if no matching history row exists.
    """
    cursor = await conn.execute(
        """
        SELECT recipe, recipe_hash FROM wb.recipe_versions
        WHERE agent_id = %s AND tenant_id = %s AND version = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (agent_id, tenant_id, to_version),
    )
    history_row = await cursor.fetchone()
    if history_row is None:
        raise ValueError(
            f"rollback: no wb.recipe_versions row for agent_id={agent_id!r} tenant_id={tenant_id} version={to_version}"
        )
    recipe_json, history_recipe_hash = history_row

    await conn.execute(
        "UPDATE wb.recipes SET status = 'rolled_back' WHERE agent_id = %s AND tenant_id = %s AND status = 'published'",
        (agent_id, tenant_id),
    )

    cursor = await conn.execute(
        "SELECT id FROM wb.recipes WHERE agent_id = %s AND tenant_id = %s AND version = %s",
        (agent_id, tenant_id, to_version),
    )
    existing = await cursor.fetchone()
    if existing is not None:
        await conn.execute("UPDATE wb.recipes SET status = 'published' WHERE id = %s", (existing[0],))
    else:
        # The target version's own wb.recipes row is gone (or never existed independently of
        # history) — recreate it from wb.recipe_versions so the endpoint has something live.
        # `history_recipe_hash` carries forward unchanged — this is the SAME recipe content being
        # re-asserted, not a new one, so the hash that already certified it is still correct; a
        # `NULL` here would silently make a legitimately-hashed recipe look unverified again.
        await conn.execute(
            """
            INSERT INTO wb.recipes (agent_id, tenant_id, recipe, version, status, recipe_hash)
            VALUES (%s, %s, %s::jsonb, %s, 'published', %s)
            """,
            (agent_id, tenant_id, recipe_json, to_version, history_recipe_hash),
        )


async def _reassert_last_published(agent_id: str, tenant_id: UUID, conn: DbConnection) -> None:
    """`publish()`'s FAIL-path helper — re-run `rollback()` against whatever is CURRENTLY
    `status='published'` for `(agent_id, tenant_id)`, so a blocked publish can never leave the
    endpoint pointed at anything other than a previously-known-good version. A no-op (by design)
    when nothing has ever been published yet — there is nothing to roll back TO, and the
    `ValueError` `publish()` raises right after this call already communicates the block.
    """
    cursor = await conn.execute(
        """
        SELECT version FROM wb.recipes
        WHERE agent_id = %s AND tenant_id = %s AND status = 'published'
        ORDER BY version DESC
        LIMIT 1
        """,
        (agent_id, tenant_id),
    )
    row = await cursor.fetchone()
    if row is None:
        return
    await rollback(agent_id, tenant_id, to_version=row[0], conn=conn)
