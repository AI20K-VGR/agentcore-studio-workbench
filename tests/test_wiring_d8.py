"""Day 8 SWE Wiring Test Suite — INV-1 Tenant-Wall (tenant_wall.py).

Validates:
1. resolve_tenant() — happy path: reads tenant_id server-side from session.
2. resolve_tenant() — fail-closed: missing tenant_id raises PermissionError.
3. resolve_tenant() — fail-closed: None tenant_id raises PermissionError.
4. resolve_tenant() — fail-closed: blank tenant_id raises PermissionError.
5. resolve_tenant() — T1 IDOR prevention: client payload tenant ignored.
6. resolve_tenant() — alias key "tenant" is accepted as fallback.
7. resolve_tenant() — non-mapping session raises TypeError (not PermissionError).
8. resolve_session() — happy path: resolves {tenant_id, user, roles} fully.
9. resolve_session() — fail-closed: missing user raises PermissionError.
10. resolve_session() — fail-closed: blank user raises PermissionError.
11. resolve_session() — roles absent defaults to [] (least-privilege).
12. resolve_session() — roles as OAuth2 scope string parsed correctly.
13. resolve_session() — sub alias accepted for user key.
14. resolve_session() — ResolvedContext is frozen (immutable).

Owner: SWE (Thiệu Quang Minh). Day 8 — Sprint 1 Chặng 1 Tuần 2.
"""

from __future__ import annotations

from uuid import UUID

import pytest

from studio_workbench.tenant_wall import (
    ResolvedContext,
    resolve_session,
    resolve_tenant,
)

ANKOR_ID = UUID("a0000000-0000-0000-0000-000000000001")
OTHER_ID = UUID("b0000000-0000-0000-0000-000000000002")


# ===========================================================================
# Fixtures
# ===========================================================================

VALID_SESSION: dict[str, object] = {
    "tenant_id": ANKOR_ID,
    "user": "dozyboy@ankor.vn",
    "roles": ["hr", "finance", "public"],
}


# ===========================================================================
# resolve_tenant() — Group 1: Happy path
# ===========================================================================


def test_resolve_tenant_returns_tenant_id_from_session() -> None:
    """DoD 1: resolve_tenant() reads tenant_id server-side from the session dict.

    Returns a UUID matching studio_contracts DEC-B (tenant_id: UUID).
    Must never touch any client-declared field — only reads from session object.
    """
    session = {"tenant_id": ANKOR_ID, "user": "dozyboy@ankor.vn"}
    result = resolve_tenant(session)
    assert result == ANKOR_ID
    assert isinstance(result, UUID)


def test_resolve_tenant_accepts_tenant_alias_key() -> None:
    """DoD 6: resolve_tenant() supports 'tenant' as a fallback alias for 'tenant_id'."""
    session = {"tenant": ANKOR_ID}
    result = resolve_tenant(session)
    assert result == ANKOR_ID
    assert isinstance(result, UUID)


def test_resolve_tenant_accepts_uuid_string() -> None:
    """resolve_tenant() parses a UUID-formatted string into a UUID object."""
    session = {"tenant_id": "a0000000-0000-0000-0000-000000000001"}
    result = resolve_tenant(session)
    assert result == ANKOR_ID
    assert isinstance(result, UUID)


# ===========================================================================
# resolve_tenant() — Group 2: Fail-closed (INV-1 mandatory filter)
# ===========================================================================


def test_resolve_tenant_raises_on_missing_tenant_id() -> None:
    """DoD 2: fail-closed — missing tenant_id key raises PermissionError immediately."""
    session: dict[str, object] = {"user": "dozyboy@ankor.vn"}
    with pytest.raises(PermissionError, match="tenant_id"):
        resolve_tenant(session)


def test_resolve_tenant_raises_on_invalid_uuid_string() -> None:
    """fail-closed — non-UUID string raises PermissionError (DEC-B: tenant_id must be UUID)."""
    session: dict[str, object] = {"tenant_id": "not-a-uuid"}
    with pytest.raises(PermissionError, match="UUID"):
        resolve_tenant(session)


def test_resolve_tenant_raises_on_none_tenant_id() -> None:
    """DoD 3: fail-closed — None tenant_id raises PermissionError (NOT NULL invariant)."""
    session: dict[str, object] = {"tenant_id": None, "user": "dozyboy@ankor.vn"}
    with pytest.raises(PermissionError, match="tenant_id"):
        resolve_tenant(session)


def test_resolve_tenant_raises_on_blank_tenant_id() -> None:
    """DoD 4: fail-closed — blank/empty string tenant_id raises PermissionError."""
    session: dict[str, object] = {"tenant_id": "   ", "user": "dozyboy@ankor.vn"}
    with pytest.raises(PermissionError):
        resolve_tenant(session)


def test_resolve_tenant_non_mapping_session_raises_type_error() -> None:
    """DoD 7: non-mapping session raises TypeError, not PermissionError."""
    with pytest.raises(TypeError, match="dict-like mapping"):
        resolve_tenant("not-a-mapping")  # type: ignore[arg-type]

    with pytest.raises(TypeError):
        resolve_tenant(12345)  # type: ignore[arg-type]


# ===========================================================================
# resolve_tenant() — Group 3: T1 IDOR prevention
# ===========================================================================


def test_resolve_tenant_ignores_client_declared_tenant_in_body() -> None:
    """DoD 5: T1 IDOR prevention.

    The session carries ANKOR_ID server-side. An attacker's fabricated request body
    would carry OTHER_ID — but resolve_tenant() never receives the request body.
    Must return the session-derived UUID, never the attacker's UUID.
    """
    server_session = {"tenant_id": ANKOR_ID, "user": "dozyboy@ankor.vn"}
    _attacker_request_body = {"tenant_id": str(OTHER_ID), "agent_id": "agent-999"}

    result = resolve_tenant(server_session)

    assert result == ANKOR_ID
    assert result != OTHER_ID


# ===========================================================================
# resolve_session() — Group 4: Happy path
# ===========================================================================


def test_resolve_session_returns_full_context() -> None:
    """DoD 8: resolve_session() returns ResolvedContext with all 3 fields."""
    ctx = resolve_session(VALID_SESSION)

    assert isinstance(ctx, ResolvedContext)
    assert ctx.tenant_id == ANKOR_ID
    assert isinstance(ctx.tenant_id, UUID)
    assert ctx.user == "dozyboy@ankor.vn"
    assert ctx.roles == ["hr", "finance", "public"]


def test_resolve_session_accepts_sub_alias_for_user() -> None:
    """DoD 13: resolve_session() accepts 'sub' as a fallback alias for 'user' (JWT standard)."""
    session = {
        "tenant_id": ANKOR_ID,
        "sub": "dozyboy-jwt-sub",
        "roles": ["public"],
    }
    ctx = resolve_session(session)
    assert ctx.user == "dozyboy-jwt-sub"


def test_resolve_session_roles_absent_defaults_to_empty_list() -> None:
    """DoD 11: roles absent from session → defaults to [] (least-privilege, not an error)."""
    session: dict[str, object] = {
        "tenant_id": ANKOR_ID,
        "user": "dozyboy@ankor.vn",
    }
    ctx = resolve_session(session)
    assert ctx.roles == []


def test_resolve_session_roles_as_oauth2_scope_string() -> None:
    """DoD 12: resolve_session() parses OAuth2 space-separated scope string into roles list."""
    session = {
        "tenant_id": ANKOR_ID,
        "user": "dozyboy@ankor.vn",
        "scope": "read write admin",
    }
    ctx = resolve_session(session)
    assert ctx.roles == ["read", "write", "admin"]


# ===========================================================================
# resolve_session() — Group 5: Fail-closed
# ===========================================================================


def test_resolve_session_raises_on_missing_user() -> None:
    """DoD 9: fail-closed — missing user key raises PermissionError."""
    session: dict[str, object] = {"tenant_id": ANKOR_ID}
    with pytest.raises(PermissionError, match="user"):
        resolve_session(session)


def test_resolve_session_raises_on_blank_user() -> None:
    """DoD 10: fail-closed — blank user string raises PermissionError."""
    session: dict[str, object] = {
        "tenant_id": ANKOR_ID,
        "user": "   ",
    }
    with pytest.raises(PermissionError):
        resolve_session(session)


def test_resolve_session_raises_when_tenant_missing() -> None:
    """resolve_session() propagates PermissionError from resolve_tenant() on missing tenant."""
    session: dict[str, object] = {"user": "dozyboy@ankor.vn", "roles": ["public"]}
    with pytest.raises(PermissionError, match="tenant_id"):
        resolve_session(session)


# ===========================================================================
# ResolvedContext — Group 6: Immutability
# ===========================================================================


def test_resolved_context_is_frozen() -> None:
    """DoD 14: ResolvedContext is frozen (immutable) — cannot mutate tenant_id, user, or roles."""
    ctx = resolve_session(VALID_SESSION)

    with pytest.raises((AttributeError, TypeError)):
        ctx.tenant_id = "hacked-tenant"  # type: ignore[misc]

    with pytest.raises((AttributeError, TypeError)):
        ctx.user = "hacked-user"  # type: ignore[misc]
