"""Tenant-Wall seam (R-SPEC A3, T1 IDOR) — INV-1 middleware — bút SWE Day 8.

Distinct from P3's `studio_app.middleware.tenant_context_middleware` (which sets the Postgres
RLS session var `app.tenant_id` via `SET LOCAL`, from a header-stub resolution): Tenant-Wall is
the WORKBENCH-side seam that resolves tenant identity from the SESSION (auth-derived, server-
side) at the workbench API boundary — it never trusts a client-declared tenant/agent_id in a
URL path param or request body. This is the 3-layer tenant fence (plan.md):

1. **Tenant-Wall (here, P7/SWE)** — session -> resolve {tenant, user, system_roles}, at the workbench
   API boundary.
   Stops T1 IDOR: a caller supplying someone else's tenant (or an agent_id belonging to another
   tenant) in the request must never be trusted — the tenant used for every downstream check
   comes ONLY from what this function resolves server-side, never from the request payload.
2. **P3 tenant-context middleware** (`studio_app.middleware`) — takes the resolved tenant and
   sets the Postgres RLS session var (`SET LOCAL app.tenant_id`) for the request's connection.
3. **RLS policy** (P5, kb fence) — the actual row-level enforcement keyed off that session var.

A `resolve_tenant_id()` implementation that reads a client-supplied tenant field instead of deriving
it from the session recreates T1 — this is the exact bug this seam exists to prevent.

INV-1 mandatory filter (fail-closed):
- If `tenant_id` is absent or None in the session → raise `PermissionError` immediately.
- If `user` is absent or None → raise `PermissionError` immediately.
- `system_roles` defaults to `[]` when absent (empty roles is valid — least-privilege).
- The resolved tenant_id MUST be a non-empty string (NOT NULL invariant).

Day 8 implementation: `resolve_tenant_id()` and `resolve_session()` read from a session mapping
(dict-like object representing an auth-derived server-side session / JWT claims payload).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

# ---------------------------------------------------------------------------
# Public data class — resolved context carrier
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ResolvedContext:
    """Immutable carrier for the resolved server-side identity.

    Attributes:
        tenant_id: UUID tenant identifier (T1 IDOR-safe, server-derived).
                   Matches the `tenant_id: UUID` type used across studio_contracts
                   (Recipe, TraceEvent, KbSearch — DEC-B).
        user:      Authenticated user identifier (sub / user_id from JWT).
        system_roles: List of roles/scopes granted to this user within this tenant.
    """

    tenant_id: UUID
    user: str
    system_roles: list[str]


# ---------------------------------------------------------------------------
# Sentinel for missing-key detection (distinct from None)
# ---------------------------------------------------------------------------

_MISSING: Any = object()


# ---------------------------------------------------------------------------
# Core resolution logic
# ---------------------------------------------------------------------------


def resolve_tenant_id(session: object) -> UUID:
    """Resolve the tenant_id for `session`, server-side.

    Reads `tenant_id` exclusively from the server-derived session mapping.
    Never trusts a client-declared tenant field on the request itself (T1 IDOR).

    Returns a `UUID` — matching the `tenant_id: UUID` type used across all
    studio_contracts models (Recipe, TraceEvent, KbSearch — DEC-B).

    INV-1 — fail-closed:
      * `tenant_id` absent or None      →  PermissionError (mandatory, NOT NULL)
      * `tenant_id` blank string        →  PermissionError (blank is equivalent to null)
      * `tenant_id` invalid UUID format →  PermissionError (must be parseable as UUID)

    Args:
        session: A dict-like mapping produced server-side from an auth token
                 (e.g. JWT claims decoded and stored by the auth middleware).
                 Supported keys: ``tenant_id``, ``tenant`` (fallback alias).
                 Value may be a `UUID` object or a UUID-formatted string.

    Returns:
        `UUID` tenant_id (guaranteed non-null, valid UUID).

    Raises:
        PermissionError: If `tenant_id` is missing, None, blank, or not a valid UUID.
        TypeError: If `session` is not a Mapping.
    """
    if not isinstance(session, Mapping):
        raise TypeError(f"resolve_tenant_id: session must be a dict-like mapping, got {type(session).__name__!r}")

    # Support both canonical key and alias
    tenant_id: Any = _MISSING
    for key in ("tenant_id", "tenant"):
        try:
            val = session[key]
            tenant_id = val
            break
        except (KeyError, TypeError):  # fmt: skip
            continue

    # fail-closed: missing or None
    if tenant_id is _MISSING or tenant_id is None:
        raise PermissionError(
            "resolve_tenant_id: tenant_id is absent from session — "
            "request rejected (INV-1 fail-closed, T1 IDOR prevention)"
        )

    # Already a UUID object — return directly
    if isinstance(tenant_id, UUID):
        return tenant_id

    # String path: blank check then UUID parse
    tenant_str = str(tenant_id).strip()
    if not tenant_str:
        raise PermissionError(
            "resolve_tenant_id: tenant_id is blank/empty — request rejected (INV-1 mandatory NOT NULL filter)"
        )

    # fail-closed: invalid UUID format
    try:
        return UUID(tenant_str)
    except ValueError:
        raise PermissionError(
            f"resolve_tenant_id: tenant_id {tenant_str!r} is not a valid UUID — "
            "request rejected (INV-1, DEC-B: tenant_id must be UUID)"
        ) from None


def resolve_session(session: object) -> ResolvedContext:
    """Resolve the full server-side identity: {tenant_id, user, system_roles}.

    Reads all three fields from the server-derived session mapping only.
    Any client-declared identity values in the request body/URL are ignored
    entirely — they must never reach this function.

    INV-1 — fail-closed:
      * `tenant_id` absent/None/blank  →  PermissionError
      * `user` absent/None/blank       →  PermissionError
      * `system_roles` absent          →  defaults to [] (least-privilege, not an error)

    Args:
        session: A dict-like auth-derived session mapping.
                 Expected keys: ``tenant_id`` (or ``tenant``), ``user`` (or ``sub``),
                 ``system_roles`` (or legacy ``roles``, or ``scope`` as space-separated string).

    Returns:
        :class:`ResolvedContext` with guaranteed non-empty ``tenant_id`` and ``user``.

    Raises:
        PermissionError: If ``tenant_id`` or ``user`` is missing/None/blank.
        TypeError: If ``session`` is not a Mapping.
    """
    # Resolve tenant (reuses the fail-closed logic above)
    tenant_id = resolve_tenant_id(session)

    # Resolve user — fail-closed
    user: Any = _MISSING
    for key in ("user", "sub", "user_id"):
        try:
            val = session[key]  # type: ignore[index]
            user = val
            break
        except (KeyError, TypeError):  # fmt: skip
            continue

    if user is _MISSING or user is None:
        raise PermissionError("resolve_session: user is absent from session — request rejected (INV-1 fail-closed)")

    user_str = str(user).strip()
    if not user_str:
        raise PermissionError("resolve_session: user is blank/empty — request rejected (INV-1 mandatory filter)")

    # Resolve system_roles — least-privilege default (empty list is safe). `roles` kept as a
    # legacy fallback key (same alias pattern as tenant/tenant_id and user/sub above) so any
    # caller still building the old dict shape doesn't silently regress to []. Only STOP at a
    # key once it yields a real list/str value — a key that exists but holds an invalid shape
    # (e.g. `system_roles: None`) must fall through to the next candidate key, not short-circuit
    # to the [] default while a valid `roles`/`scope` sits right behind it (review workbench#46).
    system_roles: list[str] = []
    for key in ("system_roles", "roles", "scope"):
        try:
            raw = session[key]  # type: ignore[index]
        except (KeyError, TypeError):  # fmt: skip
            continue

        if isinstance(raw, list):
            system_roles = [str(r).strip() for r in raw if str(r).strip()]
            break
        if isinstance(raw, str) and raw.strip():
            # OAuth2 scope string: "read write admin" → ["read", "write", "admin"]
            system_roles = [r.strip() for r in raw.split() if r.strip()]
            break

    return ResolvedContext(tenant_id=tenant_id, user=user_str, system_roles=system_roles)


__all__ = [
    "ResolvedContext",
    "resolve_session",
    "resolve_tenant_id",
]
