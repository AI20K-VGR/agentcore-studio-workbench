"""wb.* DDL idempotency (P7) — `studio_workbench.schema.ddl()` must be safe to run twice against
a live Postgres, the same guarantee `apps/studio/tests/test_schema.py::test_ensure_and_grant_idempotent`
holds for `core.*`. This test drives `ddl()` directly (not via `ensure_all_schemas`, which lives
in `studio_app` — out of this phase's file-ownership) through the shared `admin_pool` fixture
(root conftest.py), which already calls `ensure_all_schemas` once during setup — so by the time
this test body runs, `wb.recipes`/`wb.recipe_versions` already exist; running `ddl()` twice more
here proves the CREATE ... IF NOT EXISTS body tolerates re-entry with no error.
"""

from __future__ import annotations

from studio_app.core._db import Pool
from studio_workbench.schema import ddl


async def test_wb_ddl_idempotent(admin_pool: Pool) -> None:
    """KHÓA: `ddl()` (CREATE SCHEMA wb + wb.recipes + wb.recipe_versions) runs twice in a row
    without error — the seam `ensure_all_schemas()` (P3, `studio_app.core.schema`) direct-imports
    and calls into at every boot/test-fixture setup."""
    async with admin_pool.connection() as conn:
        await conn.execute(ddl())
        await conn.execute(ddl())

        cur = await conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'wb' ORDER BY table_name"
        )
        rows = await cur.fetchall()

    assert {row[0] for row in rows} == {"recipes", "recipe_versions"}
