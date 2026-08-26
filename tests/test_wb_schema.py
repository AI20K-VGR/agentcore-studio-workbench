"""wb.* DDL idempotency (P7) — `studio_workbench.schema.ddl()` must be safe to run twice against
a live Postgres, the same guarantee `apps/studio/tests/test_schema.py::test_ensure_and_grant_idempotent`
holds for `core.*`. This test drives `ddl()` directly (not via `ensure_all_schemas`, which lives
in `studio_app` — out of this phase's file-ownership) through the shared `admin_pool` fixture
(root conftest.py), which already calls `ensure_all_schemas` once during setup — so by the time
this test body runs, `wb.recipes`/`wb.recipe_versions`/`wb.conversations`/`wb.conversation_messages`
already exist; running `ddl()` twice more here proves the CREATE ... IF NOT EXISTS body tolerates
re-entry with no error.

The RLS tests below (`workbench#49`, `kit#240` tracking issue: multi-turn chat history) exercise
`wb.conversations`/`wb.conversation_messages` directly with raw SQL through the `pool`/`admin_pool`
fixtures — there is no Python read/write API for these tables yet (that lands in
`apps/studio#74`), so unlike `test_publish.py`'s RLS tests (which drive the fence through
`publish()`), these drive it through plain `INSERT`/`SELECT` statements. Pattern (helper +
paired block/allow shape) copied from `test_publish.py`'s `_bind_tenant`/`test_publish_rls_*`,
including that file's own precedent of NOT importing `ANKOR_ID` from `conftest.py` but redefining
it locally.
"""

from __future__ import annotations

from typing import Any, cast
from uuid import UUID

import psycopg
import pytest
from studio_app.core._db import Pool

from studio_workbench.schema import ddl

ANKOR_ID = UUID("a0000000-0000-0000-0000-000000000001")
BOREA_ID = UUID("b0000000-0000-0000-0000-000000000001")


async def test_wb_ddl_idempotent(admin_pool: Pool) -> None:
    """KHÓA: `ddl()` (CREATE SCHEMA wb + wb.recipes + wb.recipe_versions + wb.conversations +
    wb.conversation_messages) runs twice in a row without error — the seam `ensure_all_schemas()`
    (P3, `studio_app.core.schema`) direct-imports and calls into at every boot/test-fixture setup."""
    async with admin_pool.connection() as conn:
        await conn.execute(ddl())
        await conn.execute(ddl())

        cur = await conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'wb' ORDER BY table_name"
        )
        rows = await cur.fetchall()

    assert {row[0] for row in rows} == {"recipes", "recipe_versions", "conversations", "conversation_messages"}


# ---------------------------------------------------------------------------
# wb.conversations / wb.conversation_messages — RLS tenant-fence (workbench#49, B-P01 shape)


async def _bind_tenant(conn: Any, tenant_id: UUID) -> None:
    await conn.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))


async def test_conversations_rls_blocks_cross_tenant_insert(pool: Any) -> None:
    """KHÓA (B-P01 [2]): a `conn` bound to tenant Y must not be able to INSERT a `wb.conversations`
    row claiming tenant X — the `WITH CHECK` half of `wb_conversations_tenant_isolation` must
    reject it."""
    with pytest.raises(psycopg.Error):
        async with pool.connection() as conn, conn.transaction():
            await _bind_tenant(conn, BOREA_ID)  # wrong tenant on purpose
            await conn.execute(
                "INSERT INTO wb.conversations (tenant_id, agent_id) VALUES (%s, %s)",
                (ANKOR_ID, "cross-tenant-agent"),
            )


async def test_conversations_rls_allows_matching_tenant_write_and_read(pool: Any) -> None:
    """Paired positive control: the same insert, bound to the MATCHING tenant, succeeds and the
    row is readable back through the same app pool (B-P01 [4] — never the admin pool)."""
    async with pool.connection() as conn, conn.transaction():
        await _bind_tenant(conn, ANKOR_ID)
        cursor = await conn.execute(
            "INSERT INTO wb.conversations (tenant_id, agent_id) VALUES (%s, %s) RETURNING id",
            (ANKOR_ID, "matching-tenant-agent"),
        )
        (conversation_id,) = await cursor.fetchone()

    async with pool.connection() as conn, conn.transaction():
        await _bind_tenant(conn, ANKOR_ID)
        cursor = await conn.execute(
            "SELECT agent_id FROM wb.conversations WHERE id = %s",
            (conversation_id,),
        )
        row = await cursor.fetchone()

    assert row is not None
    assert row[0] == "matching-tenant-agent"


async def test_conversations_rls_blocks_cross_tenant_read(pool: Any) -> None:
    """KHÓA (B-P01 [2]): insert as tenant X (owner) — visible to X — then prove it is invisible
    when read back bound to tenant Y. Paired, not a lone negative check: a typo'd `agent_id` would
    also read back as `None`, and would be indistinguishable from RLS actually working."""
    async with pool.connection() as conn, conn.transaction():
        await _bind_tenant(conn, ANKOR_ID)
        cursor = await conn.execute(
            "INSERT INTO wb.conversations (tenant_id, agent_id) VALUES (%s, %s) RETURNING id",
            (ANKOR_ID, "fence-agent"),
        )
        (conversation_id,) = await cursor.fetchone()

    async with pool.connection() as conn, conn.transaction():
        await _bind_tenant(conn, ANKOR_ID)  # right tenant — positive control
        cursor = await conn.execute("SELECT id FROM wb.conversations WHERE id = %s", (conversation_id,))
        visible_to_owner = await cursor.fetchone()

    async with pool.connection() as conn, conn.transaction():
        await _bind_tenant(conn, BOREA_ID)  # wrong tenant on purpose
        cursor = await conn.execute("SELECT id FROM wb.conversations WHERE id = %s", (conversation_id,))
        visible_to_stranger = await cursor.fetchone()

    assert visible_to_owner is not None
    assert visible_to_stranger is None


async def _seed_conversation(pool: Any, *, tenant_id: UUID, agent_id: str) -> UUID:
    """Test helper (not a production API — that lands in `apps/studio#74`): insert one
    `wb.conversations` row bound to `tenant_id`, return its id for `wb.conversation_messages`
    tests below that need a real FK parent."""
    async with pool.connection() as conn, conn.transaction():
        await _bind_tenant(conn, tenant_id)
        cursor = await conn.execute(
            "INSERT INTO wb.conversations (tenant_id, agent_id) VALUES (%s, %s) RETURNING id",
            (tenant_id, agent_id),
        )
        (conversation_id,) = await cursor.fetchone()
    return cast(UUID, conversation_id)


async def test_conversation_messages_rls_blocks_cross_tenant_insert(pool: Any) -> None:
    """KHÓA (B-P01 [2]): same fence as `wb.conversations`, on the child table — a `conn` bound to
    tenant Y must not be able to INSERT a `wb.conversation_messages` row claiming tenant X, even
    when `conversation_id` points at a real (tenant-X) parent row."""
    conversation_id = await _seed_conversation(pool, tenant_id=ANKOR_ID, agent_id="messages-cross-tenant-agent")

    with pytest.raises(psycopg.Error):
        async with pool.connection() as conn, conn.transaction():
            await _bind_tenant(conn, BOREA_ID)  # wrong tenant on purpose
            await conn.execute(
                "INSERT INTO wb.conversation_messages "
                "(conversation_id, tenant_id, turn_index, question, answer) VALUES (%s, %s, %s, %s, %s)",
                (conversation_id, ANKOR_ID, 0, "q", "a"),
            )


async def test_conversation_messages_rls_allows_matching_tenant_write_and_read(pool: Any) -> None:
    """Paired positive control: the same insert, bound to the MATCHING tenant, succeeds and reads
    back through the app pool."""
    conversation_id = await _seed_conversation(pool, tenant_id=ANKOR_ID, agent_id="messages-matching-tenant-agent")

    async with pool.connection() as conn, conn.transaction():
        await _bind_tenant(conn, ANKOR_ID)
        await conn.execute(
            "INSERT INTO wb.conversation_messages "
            "(conversation_id, tenant_id, turn_index, question, answer) VALUES (%s, %s, %s, %s, %s)",
            (conversation_id, ANKOR_ID, 0, "hello", "hi there"),
        )

    async with pool.connection() as conn, conn.transaction():
        await _bind_tenant(conn, ANKOR_ID)
        cursor = await conn.execute(
            "SELECT question, answer FROM wb.conversation_messages WHERE conversation_id = %s",
            (conversation_id,),
        )
        row = await cursor.fetchone()

    assert row is not None
    assert row == ("hello", "hi there")


async def test_conversation_messages_rls_blocks_cross_tenant_read(pool: Any) -> None:
    """KHÓA (B-P01 [2]): insert as tenant X (owner) — visible to X — then prove it is invisible
    to tenant Y, same "prove it exists, then prove the fence hides it" shape used everywhere else
    in this file."""
    conversation_id = await _seed_conversation(pool, tenant_id=ANKOR_ID, agent_id="messages-fence-agent")

    async with pool.connection() as conn, conn.transaction():
        await _bind_tenant(conn, ANKOR_ID)
        await conn.execute(
            "INSERT INTO wb.conversation_messages "
            "(conversation_id, tenant_id, turn_index, question, answer) VALUES (%s, %s, %s, %s, %s)",
            (conversation_id, ANKOR_ID, 0, "q", "a"),
        )

    async with pool.connection() as conn, conn.transaction():
        await _bind_tenant(conn, ANKOR_ID)  # right tenant — positive control
        cursor = await conn.execute(
            "SELECT id FROM wb.conversation_messages WHERE conversation_id = %s", (conversation_id,)
        )
        visible_to_owner = await cursor.fetchone()

    async with pool.connection() as conn, conn.transaction():
        await _bind_tenant(conn, BOREA_ID)  # wrong tenant on purpose
        cursor = await conn.execute(
            "SELECT id FROM wb.conversation_messages WHERE conversation_id = %s", (conversation_id,)
        )
        visible_to_stranger = await cursor.fetchone()

    assert visible_to_owner is not None
    assert visible_to_stranger is None


async def test_conversation_messages_unique_turn_index_per_conversation(pool: Any) -> None:
    """KHÓA (issue text, verbatim): `UNIQUE (conversation_id, turn_index)` exists specifically
    "để `apps/studio` ghi lượt mới an toàn, tránh 2 request đồng thời ghi trùng số thứ tự" — a
    second INSERT reusing the same `(conversation_id, turn_index)` pair must be rejected, not
    silently accepted as a second row for the same turn."""
    conversation_id = await _seed_conversation(pool, tenant_id=ANKOR_ID, agent_id="messages-unique-turn-agent")

    async with pool.connection() as conn, conn.transaction():
        await _bind_tenant(conn, ANKOR_ID)
        await conn.execute(
            "INSERT INTO wb.conversation_messages "
            "(conversation_id, tenant_id, turn_index, question, answer) VALUES (%s, %s, %s, %s, %s)",
            (conversation_id, ANKOR_ID, 0, "first question", "first answer"),
        )

    with pytest.raises(psycopg.Error):
        async with pool.connection() as conn, conn.transaction():
            await _bind_tenant(conn, ANKOR_ID)
            await conn.execute(
                "INSERT INTO wb.conversation_messages "
                "(conversation_id, tenant_id, turn_index, question, answer) VALUES (%s, %s, %s, %s, %s)",
                (conversation_id, ANKOR_ID, 0, "duplicate turn", "should be rejected"),
            )
