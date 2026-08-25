"""Day 9 SWE Wiring Test Suite — Harden: form->recipe valid + negative + INV-1 hardening.

Per docs/requirements/week-1/days/day-09.md (SWE row): "Test form->recipe valid + recipe
thieu field bi reject; harden INV-1 middleware (client-khai-tenant ignore)". No new
production feature is added here (day-09 constraint: "Khong them feature moi - chi
harden") - this file only adds test coverage over existing recipe.py / tenant_wall.py.

Validates:
1. form -> recipe valid (happy path) via create_recipe().
2. Recipe construction rejects when a required field is missing (pydantic ValidationError) -
   for Recipe itself, and for its nested AgentConfig / KbBinding sub-models.
3. Form-level builders reject missing required inputs too (TypeError / ValueError) -
   these must be *real* errors, not silently-swallowed defaults.
4. INV-1 (tenant_wall) hardening: additional fail-closed edge cases not covered by
   test_wiring_d8.py, plus a builder-side test proving create_recipe() has no side
   channel for tenant_id to arrive through besides its one explicit keyword.

   NOTE (post-review, PR#9 review): a prior version of this file's Group 3 also carried
   an "end-to-end INV-1" test that asserted resolve_session() then substituted the
   result into the form dict itself before calling the builder - the substitution
   was the test's own code, not anything in src/, so it passed even against a builder
   mutated to hardcode its tenant. There is no src/ caller wiring resolve_session() into
   any builder (workbench and studio_engine are import-linter sibling layers, so
   workbench cannot be the composition root); the real INV-1 decision point is
   interpreter.run() at the composition root, covered by
   agentcore-studio-app#2::test_inv1_recipe_khai_tenant_khac_thi_session_thang. This file
   only owns the builder half now: proving create_recipe() itself has no back door.

   UPDATE 2026-08-24 (workbench#31 follow-up cleanup): `create_recipe_d6` — the other
   Form-Feed builder this file used to test in parallel — removed (0 production caller).
   `create_dynamic_recipe` (renamed `create_recipe`) is now the one Form-Feed builder left,
   and the "no defaults / no side channel" invariants below (previously proven for both
   builders) are proven for it alone; nothing d6-specific survives migration (its coverage
   was a byte-for-byte duplicate of the create_recipe assertions in the same groups below).

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

from studio_workbench import create_recipe
from studio_workbench.tenant_wall import resolve_session, resolve_tenant_id

ANKOR_ID = UUID("a0000000-0000-0000-0000-000000000001")
OTHER_ID = UUID("b0000000-0000-0000-0000-000000000002")


def _valid_dynamic_form_data() -> dict[str, object]:
    """A well-formed Form UI submission for create_recipe() (all fields present)."""
    return dict(
        agent_id="agent-form-d9",
        tenant_id=ANKOR_ID,
        instructions="Tra cuu chinh sach nghi phep nam.",
        tool_whitelist=["kb_search"],
        nodes=[Node(id="n1", type=NodeType.END, params={})],
        edges=[],
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


def test_form_to_recipe_valid_via_create_recipe() -> None:
    """DoD: a fully-filled form submitted to create_recipe() yields a valid Recipe."""
    nodes = [Node(id="n1", type=NodeType.END, params={})]

    recipe = create_recipe(
        agent_id="agent-dyn-d9",
        tenant_id=ANKOR_ID,
        instructions="Tra cuu tai lieu Callisto.",
        tool_whitelist=["kb_search"],
        nodes=nodes,
        edges=[],
    )

    assert isinstance(recipe, Recipe)
    assert recipe.agent_id == "agent-dyn-d9"
    assert recipe.tenant_id == ANKOR_ID
    assert recipe.kb_binding.kb_id == "kb-callisto-v1"
    assert recipe.kb_binding.scope == "ankor/public"


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
    completeness, independent of any caller-side checks in recipe.py.
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
        "tool_whitelist",
        "nodes",
        "edges",
    ],
)
def test_create_recipe_missing_required_form_field_is_rejected(missing_field: str) -> None:
    """DoD: create_recipe() has NO defaults for its core params - omitting any one of them
    must fail loudly with TypeError, not silently fall back to a hidden default."""
    form_data = _valid_dynamic_form_data()
    del form_data[missing_field]

    with pytest.raises(TypeError):
        create_recipe(**form_data)  # type: ignore[arg-type]


# ===========================================================================
# Group 3 -- harden INV-1 middleware (client-khai-tenant bi ignore)
# ===========================================================================


def test_resolve_tenant_raises_type_error_on_none_session() -> None:
    """Harden: a None session (e.g. auth middleware never ran) must raise TypeError,
    not be silently treated as an empty-but-valid mapping.
    """
    with pytest.raises(TypeError, match="dict-like mapping"):
        resolve_tenant_id(None)


def test_resolve_tenant_rejects_non_uuid_numeric_tenant_id() -> None:
    """Harden: a tenant_id that is a bare int (neither UUID nor UUID-string) must be
    rejected fail-closed, not coerced or silently accepted.
    """
    session = {"tenant_id": 12345, "user": "dozyboy@ankor.vn"}

    with pytest.raises(PermissionError, match="UUID"):
        resolve_tenant_id(session)


def test_resolve_session_filters_blank_entries_out_of_roles_list() -> None:
    """Harden: blank/whitespace-only entries inside a roles list must be dropped,
    never handed downstream as a bogus role.
    """
    session = {
        "tenant_id": ANKOR_ID,
        "user": "dozyboy@ankor.vn",
        "system_roles": ["hr", "", "   ", "finance"],
    }

    ctx = resolve_session(session)

    assert ctx.system_roles == ["hr", "finance"]


def test_create_recipe_rejects_unexpected_tenant_like_keys() -> None:
    """Harden (builder-side): create_recipe() has no side channel for a tenant to
    arrive through besides its one explicit `tenant_id` keyword.

    Replaces a prior test that claimed to lock INV-1 end-to-end but didn't: it built an
    "attacker" form dict, then substituted the session-resolved tenant into that same
    dict *inside the test body* before calling the builder, and asserted the
    substitution it had just performed. The substitution was the fence, and it lived in
    the test, not in src/ - a builder mutated to hardcode its tenant (ignoring
    the tenant_id argument entirely) still passed that test. See PR#9 review for the
    mutation that demonstrated this.

    What this test locks instead: create_recipe() takes named parameters with no
    **kwargs catch-all, so any extra tenant-shaped key in a form payload - "tenant",
    "tenant_slug", or anything else not spelled `tenant_id` - MUST blow up as TypeError,
    not get silently accepted or silently preferred over the real `tenant_id`. That's a
    real, exercisable property of this function. (Migrated from `create_recipe_d6`,
    removed at workbench#31 follow-up cleanup — same invariant, same fence, one builder.)

    What this test does NOT claim: that the *caller* correctly resolves the session
    before calling this builder (that's an API-boundary responsibility, not the
    builder's) - resolve_session()/resolve_tenant_id() correctness is covered by the rest
    of this file's Group 3 and by test_wiring_d8.py. The actual INV-1 decision point
    (recipe-declared tenant vs. session-resolved tenant) lives at the composition root,
    interpreter.run(), covered by
    agentcore-studio-app#2::test_inv1_recipe_khai_tenant_khac_thi_session_thang.
    """
    form_data = _valid_dynamic_form_data()
    form_data["tenant"] = OTHER_ID  # not a real param - must not be silently accepted
    form_data["tenant_slug"] = "borea"  # ditto

    with pytest.raises(TypeError, match="unexpected keyword argument"):
        create_recipe(**form_data)  # type: ignore[arg-type]
