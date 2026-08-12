"""`publish`/`rollback` connection seam (kit#117, Q5) — quadrant-internal, deliberately NOT
promoted to `studio_contracts`.

Precedent: `packages/evalhub/docs/mini-rfc/MRFC-2026-08-03-agentrunner-protocol-seam.md` pre-wrote
(but never submitted) a mini-RFC to promote `AgentRunner` to a 4th `studio_contracts` Protocol,
then talked itself out of it — adding a seam to the bottom, freeze-bound layer "right at the
moment of freezing it" was rated the weaker option against "keep the Protocol quadrant-internal:
0 signatures, `lint-imports` already green" (that RFC's §4). The same reasoning applies here, more
so: `DbConnection` has exactly ONE producer (`apps/studio`, the composition root, once it wires a
real route) and ONE consumer (`publish()`/`rollback()` below) — no second quadrant needs this type
name. `apps/studio` already imports `studio_workbench` freely (it sits above it in
`.importlinter`'s layer order), so it can import this Protocol directly for its own type hints;
there is no cross-quadrant need `studio_contracts` would serve here, unlike `EmbeddingService`/
`LLM`/`TraceWriter`, each consumed by a DIFFERENT quadrant than the one that implements it.

A single connection already bound to the current request's tenant (`SET LOCAL app.tenant_id`
already ran on it — e.g. via `apps/studio`'s `get_request_connection()`), never a pool:
`studio_workbench` cannot import `studio_app` (`.importlinter`) to reach the real pool, and
accepting only an already-bound connection (never a pool this module could use to open its OWN,
unbound one) makes the failure mode `docs/test-design/GUIDE-B-recipe.md` §4.5/§11 (row B-P01)
warns about structurally unreachable from inside `publish()`/`rollback()`.

Shape matches `psycopg.AsyncConnection.execute` (`query, positional-params -> cursor`, cursor
`fetchone`/`fetchall` returning plain tuples) — the same convention `studio_kb.postgres` already
uses, so a real psycopg connection satisfies this Protocol structurally with no adapter.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DbCursor(Protocol):
    async def fetchone(self) -> tuple[Any, ...] | None: ...

    async def fetchall(self) -> list[tuple[Any, ...]]: ...


@runtime_checkable
class DbConnection(Protocol):
    async def execute(self, query: str, params: Sequence[Any] | None = None) -> DbCursor: ...
