"""Tenant-Wall seam (R-SPEC A3, T1 IDOR) — bút SWE, spec-only this phase (OJT implementation
slot).

Distinct from P3's `studio_app.middleware.tenant_context_middleware` (which sets the Postgres
RLS session var `app.tenant_id` via `SET LOCAL`, from a header-stub resolution): Tenant-Wall is
the WORKBENCH-side seam that resolves tenant identity from the SESSION (auth-derived, server-
side) at the workbench API boundary — it never trusts a client-declared tenant/agent_id in a
URL path param or request body. This is the 3-layer tenant fence (plan.md):

1. **Tenant-Wall (here, P7/SWE)** — session -> tenant resolve, at the workbench API boundary.
   Stops T1 IDOR: a caller supplying someone else's tenant (or an agent_id belonging to another
   tenant) in the request must never be trusted — the tenant used for every downstream check
   comes ONLY from what this function resolves server-side, never from the request payload.
2. **P3 tenant-context middleware** (`studio_app.middleware`) — takes the resolved tenant and
   sets the Postgres RLS session var (`SET LOCAL app.tenant_id`) for the request's connection.
3. **RLS policy** (P5, kb fence) — the actual row-level enforcement keyed off that session var.

A `resolve_tenant()` implementation that reads a client-supplied tenant field instead of deriving
it from the session recreates T1 — this is the exact bug this seam exists to prevent.

This module ships as a spec stub this phase: `resolve_tenant()` unconditionally raises
`NotImplementedError`. The SWE OJT candidate fills in the real session -> tenant resolution.
"""

from __future__ import annotations


def resolve_tenant(session: object) -> str:
    """Resolve the tenant id for `session`, server-side — never trust a client-declared tenant
    field on the request itself (T1 IDOR).

    P7 stub: SWE OJT fills in the real resolution (session/JWT claim -> tenant). Deliberately
    unimplemented.
    """
    raise NotImplementedError("resolve_tenant: SWE OJT fills in server-side session->tenant resolution (R-SPEC A3)")
