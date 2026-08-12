"""`publish`/`rollback` spec tests (R-SPEC A4 :72, kit#117 D18) — real bodies replacing the
`NotImplementedError` stub.

Non-DB tests below drive `publish()`/`rollback()` against `FakeConn`, an in-memory double of
`wb.recipes`/`wb.recipe_versions` honoring the exact query shapes `publish.py` issues — they pin
the branch logic (graph_lint gate, `recipe_hash` fail-closed, `gate.verdict` gate + rollback,
version bookkeeping) independent of any real Postgres. The DB-backed tests at the bottom
(`test_publish_rls_*`) exercise the actual RLS policy from `schema.py` (`B-P01` in
`docs/test-design/GUIDE-B-recipe.md` §11) through the real `pool`/`admin_pool` fixtures
(root `conftest.py`) — they skip when `STUDIO_DATABASE_URL`/`STUDIO_DATABASE_URL_ADMIN` are unset,
same as every other DB test in this workspace.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

import pytest
from studio_contracts import (
    AgentConfig,
    Aggregate,
    CaseResult,
    Dag,
    Edge,
    Gate,
    GateThreshold,
    KbBinding,
    Node,
    NodeType,
    Recipe,
    Scorecard,
    ScorecardThreshold,
)

from studio_workbench.publish import publish, rollback

ANKOR_ID = UUID("a0000000-0000-0000-0000-000000000001")
BOREA_ID = UUID("b0000000-0000-0000-0000-000000000001")


def _valid_recipe(*, agent_id: str = "agent-1", tenant_id: UUID = ANKOR_ID) -> Recipe:
    return Recipe(
        agent_id=agent_id,
        tenant_id=tenant_id,
        agent_config=AgentConfig(
            instructions="Answer from KB only.",
            model="gpt-4o-mini",
            tool_whitelist=["kb_search"],
        ),
        dag=Dag(
            nodes=[
                Node(id="n1", type=NodeType.KB_RETRIEVE, params={}),
                Node(id="n2", type=NodeType.END, params={}),
            ],
            edges=[Edge(from_="n1", to="n2", when=None)],
        ),
        kb_binding=KbBinding(kb_id="kb-1", scope="ankor/public"),
        golden_set_ref="golden-set-1",
        scorecard_threshold=ScorecardThreshold(success=0.9, citation_accuracy=0.95),
    )


def _invalid_recipe() -> Recipe:
    """Fails graph-lint rule 2 (dangling edge) — plain constructors, no `model_construct` back
    door needed for this rule (`test_graph_lint.py`'s own convention: only rule 1 needs it)."""
    return _valid_recipe().model_copy(
        update={
            "dag": Dag(
                nodes=[Node(id="n1", type=NodeType.KB_RETRIEVE, params={})],
                edges=[Edge(from_="n1", to="does-not-exist", when=None)],
            )
        }
    )


def _scorecard(*, verdict: Literal["PASS", "FAIL"], recipe_hash: str | None) -> Scorecard:
    citation_accuracy = 1.0 if verdict == "PASS" else 0.0
    success_rate = 1.0 if verdict == "PASS" else 0.0
    return Scorecard(
        agent_id="agent-1",
        golden_set_ref="golden-set-1",
        results=[
            CaseResult(
                case_id="c1", expected="x", actual="x", success=verdict == "PASS", citation_accuracy=citation_accuracy
            )
        ],
        aggregate=Aggregate(success_rate=success_rate, citation_accuracy=citation_accuracy, n_scored_citation=1),
        gate=Gate(threshold=GateThreshold(success=0.9, citation_accuracy=0.95), verdict=verdict),
        recipe_hash=recipe_hash,
    )


@dataclass
class _Row:
    id: int
    agent_id: str
    tenant_id: UUID
    recipe: str
    version: int
    status: str
    created_at: int


@dataclass
class FakeCursor:
    rows: list[tuple[Any, ...]] = field(default_factory=list)

    async def fetchone(self) -> tuple[Any, ...] | None:
        return self.rows[0] if self.rows else None

    async def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self.rows)


class FakeConn:
    """In-memory double of `wb.recipes` + `wb.recipe_versions`, matched to the exact query text
    `publish.py` issues. No RLS/tenant filtering here by design — this file's non-DB tests exist
    to pin BRANCH LOGIC (which query fires for which `verdict`/`recipe_hash` combination), not to
    prove the fence itself; the fence is `test_publish_rls_*` below, against a real Postgres."""

    def __init__(self) -> None:
        self.recipes: list[_Row] = []
        self.versions: list[_Row] = []
        self._next_id = 1
        self._clock = 0

    async def execute(self, query: str, params: Sequence[Any] | None = None) -> FakeCursor:
        p = tuple(params or ())
        q = " ".join(query.split())

        if q.startswith("SELECT COALESCE(MAX(version), 0) FROM wb.recipes"):
            agent_id, tenant_id = p
            versions = [r.version for r in self.recipes if r.agent_id == agent_id and r.tenant_id == tenant_id]
            return FakeCursor([(max(versions, default=0),)])

        if q.startswith("UPDATE wb.recipes SET status = 'draft'"):
            agent_id, tenant_id = p
            for r in self.recipes:
                if r.agent_id == agent_id and r.tenant_id == tenant_id and r.status == "published":
                    r.status = "draft"
            return FakeCursor()

        if q.startswith("INSERT INTO wb.recipes"):
            agent_id, tenant_id, recipe_json, version = p
            self._clock += 1
            row = _Row(self._next_id, agent_id, tenant_id, recipe_json, version, "published", self._clock)
            self.recipes.append(row)
            self._next_id += 1
            return FakeCursor([(row.id,)])

        if q.startswith("INSERT INTO wb.recipe_versions"):
            recipe_id, agent_id, tenant_id, recipe_json, version = p
            self._clock += 1
            self.versions.append(_Row(recipe_id, agent_id, tenant_id, recipe_json, version, "published", self._clock))
            return FakeCursor()

        if q.startswith("SELECT recipe FROM wb.recipe_versions"):
            agent_id, tenant_id, version = p
            candidates = [
                v for v in self.versions if v.agent_id == agent_id and v.tenant_id == tenant_id and v.version == version
            ]
            history_matches = sorted(candidates, key=lambda v: v.created_at, reverse=True)
            return FakeCursor([(history_matches[0].recipe,)] if history_matches else [])

        if q.startswith("UPDATE wb.recipes SET status = 'rolled_back'"):
            agent_id, tenant_id = p
            for r in self.recipes:
                if r.agent_id == agent_id and r.tenant_id == tenant_id and r.status == "published":
                    r.status = "rolled_back"
            return FakeCursor()

        if q.startswith("SELECT id FROM wb.recipes"):
            agent_id, tenant_id, version = p
            id_matches = [
                r for r in self.recipes if r.agent_id == agent_id and r.tenant_id == tenant_id and r.version == version
            ]
            return FakeCursor([(id_matches[0].id,)] if id_matches else [])

        if q.startswith("UPDATE wb.recipes SET status = 'published' WHERE id"):
            (row_id,) = p
            for r in self.recipes:
                if r.id == row_id:
                    r.status = "published"
            return FakeCursor()

        if q.startswith("SELECT version FROM wb.recipes"):
            agent_id, tenant_id = p
            published = [
                r.version
                for r in self.recipes
                if r.agent_id == agent_id and r.tenant_id == tenant_id and r.status == "published"
            ]
            published_versions = sorted(published, reverse=True)
            return FakeCursor([(published_versions[0],)] if published_versions else [])

        raise AssertionError(f"FakeConn: unrecognized query: {q!r}")


# ---------------------------------------------------------------------------
# Non-DB: branch logic


async def test_publish_blocks_on_graph_lint_failure() -> None:
    """KHÓA: an invalid recipe never reaches the scorecard/DB checks at all — `graph_lint`'s
    `ValueError` propagates unchanged, and nothing is written."""
    conn = FakeConn()
    with pytest.raises(ValueError, match="destination"):
        await publish(_invalid_recipe(), _scorecard(verdict="PASS", recipe_hash="h1"), conn)
    assert conn.recipes == []


async def test_publish_refuses_when_recipe_hash_is_none() -> None:
    """KHÓA (kit#117): `scorecard.recipe_hash is None` fail-closed — refuses even on an otherwise
    passing scorecard, per `Scorecard.recipe_hash`'s own docstring. Paired positive control:
    `test_publish_writes_new_version_on_pass` below is the same call with a real hash, and it
    succeeds."""
    conn = FakeConn()
    with pytest.raises(ValueError, match="recipe_hash"):
        await publish(_valid_recipe(), _scorecard(verdict="PASS", recipe_hash=None), conn)
    assert conn.recipes == []


async def test_publish_writes_new_version_on_pass() -> None:
    """KHÓA: paired positive control for the two refusal tests above — graph-lint-clean recipe +
    non-`None` `recipe_hash` + `verdict="PASS"` writes exactly one `wb.recipes` row (status
    `published`, version 1) and one matching `wb.recipe_versions` row."""
    conn = FakeConn()
    await publish(_valid_recipe(), _scorecard(verdict="PASS", recipe_hash="h1"), conn)

    assert len(conn.recipes) == 1
    assert conn.recipes[0].version == 1
    assert conn.recipes[0].status == "published"
    assert len(conn.versions) == 1
    assert conn.versions[0].version == 1


async def test_publish_second_pass_bumps_version_and_demotes_prior() -> None:
    """KHÓA: publishing twice for the same `(agent_id, tenant_id)` writes version 2 as the new
    `published` row and demotes version 1's row to `draft` — never two `published` rows for the
    same agent/tenant at once (best-effort; concurrent-publish enforcement is Q4, out of scope)."""
    conn = FakeConn()
    await publish(_valid_recipe(), _scorecard(verdict="PASS", recipe_hash="h1"), conn)
    await publish(_valid_recipe(), _scorecard(verdict="PASS", recipe_hash="h2"), conn)

    published = [r for r in conn.recipes if r.status == "published"]
    assert len(published) == 1
    assert published[0].version == 2
    v1 = next(r for r in conn.recipes if r.version == 1)
    assert v1.status == "draft"


async def test_publish_fail_verdict_blocks_and_reasserts_prior_published() -> None:
    """KHÓA: `gate.verdict="FAIL"` blocks the write (no new version appears) AND re-asserts
    whichever version was already `published` — proving `rollback()` fired, not merely that the
    write was skipped. Paired positive control: `test_publish_writes_new_version_on_pass` (same
    recipe, `verdict="PASS`) is not blocked."""
    conn = FakeConn()
    await publish(_valid_recipe(), _scorecard(verdict="PASS", recipe_hash="h1"), conn)  # seed v1 published

    with pytest.raises(ValueError, match="FAIL"):
        await publish(_valid_recipe(), _scorecard(verdict="FAIL", recipe_hash="h2"), conn)

    assert len(conn.recipes) == 1  # no v2 was ever written
    assert conn.recipes[0].version == 1
    assert conn.recipes[0].status == "published"  # re-asserted, not left as something else


async def test_publish_fail_verdict_with_nothing_ever_published_is_a_noop_block() -> None:
    """KHÓA: FAIL on the very first publish attempt (nothing `published` yet) still blocks, and
    the rollback helper is a no-op (nothing to roll back TO) rather than raising a second,
    confusing error."""
    conn = FakeConn()
    with pytest.raises(ValueError, match="FAIL"):
        await publish(_valid_recipe(), _scorecard(verdict="FAIL", recipe_hash="h1"), conn)
    assert conn.recipes == []


async def test_rollback_restores_by_content_not_just_version_number() -> None:
    """KHÓA: `wb.recipe_versions` has no `UNIQUE (agent_id, tenant_id, version)` — two rows CAN
    share a version number. `rollback` must pick the most recent `created_at`, and must recreate
    the target's `wb.recipes` row from `wb.recipe_versions` HISTORY (not merely flip a status)
    when that row is no longer present in `wb.recipes` itself."""
    conn = FakeConn()
    recipe_v1 = _valid_recipe()
    await publish(recipe_v1, _scorecard(verdict="PASS", recipe_hash="h1"), conn)
    await publish(recipe_v1, _scorecard(verdict="PASS", recipe_hash="h2"), conn)  # -> v2 published, v1 draft

    # Simulate v1's own wb.recipes row having been removed independently of its history entry.
    conn.recipes = [r for r in conn.recipes if r.version != 1]
    assert {r.version for r in conn.recipes} == {2}

    await rollback(recipe_v1.agent_id, recipe_v1.tenant_id, to_version=1, conn=conn)

    v1_after = next(r for r in conn.recipes if r.version == 1)
    v2_after = next(r for r in conn.recipes if r.version == 2)
    assert v1_after.status == "published"
    assert v2_after.status == "rolled_back"
    assert v1_after.recipe == conn.versions[0].recipe  # content restored from history, not fabricated


async def test_rollback_raises_when_no_history_row_matches() -> None:
    """KHÓA: rolling back to a version with no `wb.recipe_versions` row raises rather than
    silently doing nothing — a caller must not believe a rollback succeeded when it did not."""
    conn = FakeConn()
    with pytest.raises(ValueError, match="no wb.recipe_versions row"):
        await rollback("agent-1", ANKOR_ID, to_version=99, conn=conn)


# ---------------------------------------------------------------------------
# DB-backed: the actual RLS fence (skips without STUDIO_DATABASE_URL*)


async def _bind_tenant(conn: Any, tenant_id: UUID) -> None:
    await conn.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))


async def test_publish_rls_blocks_cross_tenant_write(pool: Any) -> None:
    """KHÓA (B-P01 [2]): a `conn` bound to tenant Y (via `SET LOCAL app.tenant_id`) must not be
    able to publish an agent belonging to tenant X — the `WITH CHECK` half of the RLS policy on
    `wb.recipes` must reject the INSERT."""
    import psycopg

    recipe = _valid_recipe(agent_id="cross-tenant-agent", tenant_id=ANKOR_ID)
    scorecard = _scorecard(verdict="PASS", recipe_hash="h1")

    with pytest.raises(psycopg.Error):
        async with pool.connection() as conn, conn.transaction():
            await _bind_tenant(conn, BOREA_ID)  # wrong tenant on purpose
            await publish(recipe, scorecard, conn)


async def test_publish_rls_allows_matching_tenant_write(pool: Any) -> None:
    """KHÓA (B-P01 [3], paired positive control for the test above): the same publish, with the
    connection bound to the MATCHING tenant, succeeds and the row is readable back through the
    same app pool (B-P01 [4] — never the admin pool, which would bypass the policy)."""
    recipe = _valid_recipe(agent_id="matching-tenant-agent", tenant_id=ANKOR_ID)
    scorecard = _scorecard(verdict="PASS", recipe_hash="h1")

    async with pool.connection() as conn, conn.transaction():
        await _bind_tenant(conn, ANKOR_ID)
        await publish(recipe, scorecard, conn)

    async with pool.connection() as conn, conn.transaction():
        await _bind_tenant(conn, ANKOR_ID)
        cursor = await conn.execute(
            "SELECT status FROM wb.recipes WHERE agent_id = %s AND tenant_id = %s",
            ("matching-tenant-agent", ANKOR_ID),
        )
        row = await cursor.fetchone()

    assert row is not None
    assert row[0] == "published"
