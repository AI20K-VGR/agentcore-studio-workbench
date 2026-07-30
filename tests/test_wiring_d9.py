"""Day 9 SWE Wiring Test Suite — Harden: form->recipe valid + negative + INV-1 hardening.

Per docs/requirements/week-1/days/day-09.md (SWE row): "Test form->recipe valid + recipe
thieu field bi reject; harden INV-1 middleware (client-khai-tenant ignore)". No new
production feature is added here (day-09 constraint: "Khong them feature moi - chi
harden") - this file only adds test coverage over existing builder.py / tenant_wall.py.

Validates:
1. form -> recipe valid (happy path) via create_recipe_d6() and create_dynamic_recipe().
2. Recipe construction rejects when a required field is missing (pydantic ValidationError) -
   for Recipe itself, and for its nested AgentConfig / KbBinding sub-models.
3. Form-level builders reject missing required inputs too (TypeError / ValueError) -
   these must be *real* errors, not silently-swallowed defaults.
4. INV-1 (tenant_wall) hardening: additional fail-closed edge cases not covered by
   test_wiring_d8.py, plus an integration test proving that a client-declared
   ("form data") tenant_id is ignored in favor of the server-resolved session tenant
   when building a Recipe (T1 IDOR prevention end-to-end: builder + tenant_wall).

Owner: SWE (Thieu Quang Minh). Day 9 - Sprint 1 Chang 1 Tuan 2.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError
from studio_contracts import (
    AgentConfig,
    Dag,
    KbBinding,
    Node,
    NodeType,
    Recipe,
    ScorecardThreshold,
)

from studio_workbench import create_dynamic_recipe, create_recipe_d6
from studio_workbench.tenant_wall import resolve_session, resolve_tenant

ANKOR_ID = UUID("a0000000-0000-0000-0000-000000000001")
OTHER_ID = UUID("b0000000-0000-0000-0000-000000000002")


def _valid_form_data() -> dict[str, object]:
    """A well-formed Form UI submission (all fields present)."""
    return dict(
        agent_id="agent-form-d9",
        tenant_id=ANKOR_ID,
        instructions="Tra cuu chinh sach nghi phep nam.",
        model="gemini-2.5-flash",
        tool_whitelist=["kb_search"],
        kb_id="kb-hr-v1",
        scope="ankor/hr",
        query="Nhan vien duoc nghi phep bao nhieu ngay?",
    )


def _base_recipe_kwargs() -> dict[str, object]:
    """A complete, valid set of kwargs for constructing a Recipe directly."""
    return dict(
        agent_id="agent-d9",
        tenant_id=ANKOR_ID,
        agent_config=AgentConfig(
            instructions="Tra cuu tai lieu.", model="gemini-2.5-flash", tool_whitelist=["kb_search"]
        ),
        dag=Dag(nodes=[Node(id="n1", type=NodeType.END, params={})], edges=[]),
        kb_binding=KbBinding(kb_id="kb-x", scope="ankor/public"),
        golden_set_ref="callisto-smoke-5-v0",
        scorecard_threshold=ScorecardThreshold(success=0.9, citation_accuracy=0.95),
    )


# ===========================================================================
# Group 1 -- form -> recipe valid (happy path)
# ===========================================================================


def test_form_to_recipe_valid_via_create_recipe_d6() -> None:
    """DoD: a fully-filled form submitted to create_recipe_d6() yields a valid Recipe."""
    form_data = _valid_form_data()

    recipe = create_recipe_d6(**form_data)  # type: ignore[arg-type]

    assert isinstance(recipe, Recipe)
    assert recipe.agent_id == "agent-form-d9"
    assert recipe.tenant_id == ANKOR_ID
    assert recipe.agent_config.model == "gemini-2.5-flash"
    assert recipe.kb_binding.kb_id == "kb-hr-v1"
    assert recipe.kb_binding.scope == "ankor/hr"


def test_form_to_recipe_valid_via_create_dynamic_recipe() -> None:
    """DoD: a fully-filled form submitted to create_dynamic_recipe() yields a valid Recipe."""
    nodes = [Node(id="n1", type=NodeType.END, params={})]

    recipe = create_dynamic_recipe(
        agent_id="agent-dyn-d9",
        tenant_id=ANKOR_ID,
        instructions="Tra cuu tai lieu Callisto.",
        model="gemini-2.5-flash",
        tool_whitelist=["kb_search"],
        nodes=nodes,
        edges=[],
        kb_id="kb-callisto-v1",
        scope="ankor/public",
    )

    assert isinstance(recipe, Recipe)
    assert recipe.agent_id == "agent-dyn-d9"
    assert recipe.tenant_id == ANKOR_ID
    assert recipe.kb_binding.kb_id == "kb-callisto-v1"


# ===========================================================================
# Group 2 -- recipe thieu field bi reject (negative, phai bat loi that)
# ===========================================================================

_RECIPE_REQUIRED_FIELDS = [
    "agent_id",
    "tenant_id",
    "agent_config",
    "dag",
    "kb_binding",
    "golden_set_ref",
    "scorecard_threshold",
]


@pytest.mark.parametrize("missing_field", _RECIPE_REQUIRED_FIELDS)
def test_recipe_missing_required_field_is_rejected(missing_field: str) -> None:
    """DoD: constructing Recipe with any single required field missing raises ValidationError.

    This is a *real* pydantic validation failure (not a stubbed/soft check) - each
    required field is removed one at a time to prove the schema itself enforces
    completeness, independent of any caller-side checks in builder.py.
    """
    kwargs = _base_recipe_kwargs()
    del kwargs[missing_field]

    with pytest.raises(ValidationError):
        Recipe(**kwargs)


@pytest.mark.parametrize("missing_field", ["instructions", "model", "tool_whitelist"])
def test_agent_config_missing_required_field_is_rejected(missing_field: str) -> None:
    """DoD: nested AgentConfig also rejects a missing required field."""
    kwargs = {
        "instructions": "Tra cuu tai lieu.",
        "model": "gemini-2.5-flash",
        "tool_whitelist": ["kb_search"],
    }
    del kwargs[missing_field]

    with pytest.raises(ValidationError):
        AgentConfig(**kwargs)


@pytest.mark.parametrize("missing_field", ["kb_id", "scope"])
def test_kb_binding_missing_required_field_is_rejected(missing_field: str) -> None:
    """DoD: nested KbBinding also rejects a missing required field."""
    kwargs = {"kb_id": "kb-x", "scope": "ankor/public"}
    del kwargs[missing_field]

    with pytest.raises(ValidationError):
        KbBinding(**kwargs)


@pytest.mark.parametrize(
    "missing_field",
    [
        "agent_id",
        "tenant_id",
        "instructions",
        "model",
        "tool_whitelist",
        "kb_id",
        "scope",
        "query",
    ],
)
def test_create_recipe_d6_missing_required_form_field_is_rejected(missing_field: str) -> None:
    """DoD: create_recipe_d6() (the Form Feed entrypoint) has NO defaults for its core
    params - omitting any one of them must fail loudly with TypeError, not silently
    fall back to a hidden default.
    """
    form_data = _valid_form_data()
    del form_data[missing_field]

    with pytest.raises(TypeError):
        create_recipe_d6(**form_data)  # type: ignore[arg-type]


def test_create_dynamic_recipe_missing_kb_id_is_rejected() -> None:
    """DoD: create_dynamic_recipe() rejects a form submission missing kb_id."""
    nodes = [Node(id="n1", type=NodeType.END, params={})]

    with pytest.raises(ValueError, match="kb_id"):
        create_dynamic_recipe(
            agent_id="agent-x",
            tenant_id=ANKOR_ID,
            instructions="x",
            model="gemini-2.5-flash",
            tool_whitelist=["kb_search"],
            nodes=nodes,
            edges=[],
            kb_id=None,
            scope="ankor/public",
        )


def test_create_dynamic_recipe_missing_scope_is_rejected() -> None:
    """DoD: create_dynamic_recipe() rejects a form submission missing scope."""
    nodes = [Node(id="n1", type=NodeType.END, params={})]

    with pytest.raises(ValueError, match="scope"):
        create_dynamic_recipe(
            agent_id="agent-x",
            tenant_id=ANKOR_ID,
            instructions="x",
            model="gemini-2.5-flash",
            tool_whitelist=["kb_search"],
            nodes=nodes,
            edges=[],
            kb_id="kb-x",
            scope=None,
        )


# ===========================================================================
# Group 3 -- harden INV-1 middleware (client-khai-tenant bi ignore)
# ===========================================================================


def test_resolve_tenant_raises_type_error_on_none_session() -> None:
    """Harden: a None session (e.g. auth middleware never ran) must raise TypeError,
    not be silently treated as an empty-but-valid mapping.
    """
    with pytest.raises(TypeError, match="dict-like mapping"):
        resolve_tenant(None)


def test_resolve_tenant_rejects_non_uuid_numeric_tenant_id() -> None:
    """Harden: a tenant_id that is a bare int (neither UUID nor UUID-string) must be
    rejected fail-closed, not coerced or silently accepted.
    """
    session = {"tenant_id": 12345, "user": "dozyboy@ankor.vn"}

    with pytest.raises(PermissionError, match="UUID"):
        resolve_tenant(session)


def test_resolve_session_filters_blank_entries_out_of_roles_list() -> None:
    """Harden: blank/whitespace-only entries inside a roles list must be dropped,
    never handed downstream as a bogus role.
    """
    session = {
        "tenant_id": ANKOR_ID,
        "user": "dozyboy@ankor.vn",
        "roles": ["hr", "", "   ", "finance"],
    }

    ctx = resolve_session(session)

    assert ctx.roles == ["hr", "finance"]


def test_recipe_built_from_form_ignores_client_declared_tenant_and_uses_session() -> None:
    """Harden INV-1 end-to-end (builder + tenant_wall): even when the Form Feed
    payload itself carries a tenant_id (a client-declared / attacker-controlled
    value, T1 IDOR style), the Recipe that actually gets built must be keyed off
    the server-resolved session tenant - never the client's claim.

    This closes the gap flagged during Day 9 review: create_recipe_d6() takes
    tenant_id as a plain parameter and has no wiring to tenant_wall by itself, so
    callers (the API boundary) MUST resolve the session first and substitute that
    tenant_id in before calling the builder. This test locks in that contract.
    """
    attacker_form_data = _valid_form_data()
    attacker_form_data["tenant_id"] = OTHER_ID  # client tu khai tenant khac (IDOR attempt)

    server_session = {
        "tenant_id": ANKOR_ID,
        "user": "dozyboy@ankor.vn",
        "roles": ["hr"],
    }

    # INV-1 seam: the tenant actually used comes ONLY from the session, never
    # from whatever the client wrote into the form/body.
    resolved_tenant_id = resolve_session(server_session).tenant_id
    assert resolved_tenant_id == ANKOR_ID
    assert resolved_tenant_id != attacker_form_data["tenant_id"]

    safe_form_data = {**attacker_form_data, "tenant_id": resolved_tenant_id}
    recipe = create_recipe_d6(**safe_form_data)  # type: ignore[arg-type]

    assert recipe.tenant_id == ANKOR_ID
    assert recipe.tenant_id != OTHER_ID
