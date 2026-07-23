"""Test suite for Day 4 SWE wiring — kb_binding.{kb_id, scope} & Recipe -> Interpreter entry.

Owner: SWE (Thiệu Quang Minh — Issue #18).
"""

from __future__ import annotations

import pytest
from studio_engine.interpreter import run
from studio_workbench import build_agent_config, create_recipe_d4


def test_build_agent_config_from_form_inputs() -> None:
    """Test that build_agent_config creates a valid Pydantic AgentConfig."""
    config = build_agent_config(
        instructions="Hỗ trợ tra cứu quy định Callisto.",
        model="gemini-2.5-flash",
        tool_whitelist=["kb_search"],
    )
    assert config.instructions == "Hỗ trợ tra cứu quy định Callisto."
    assert config.model == "gemini-2.5-flash"
    assert config.tool_whitelist == ["kb_search"]


def test_create_recipe_d4_contains_kb_binding() -> None:
    """Test that create_recipe_d4 builds a Recipe with valid kb_binding.{kb_id, scope}."""
    recipe = create_recipe_d4(
        agent_id="agent-callisto-01",
        tenant="ankor",
        kb_id="kb-callisto-v1",
        scope="ankor/public",
    )

    assert recipe.agent_id == "agent-callisto-01"
    assert recipe.tenant == "ankor"
    assert recipe.kb_binding is not None
    assert recipe.kb_binding.kb_id == "kb-callisto-v1"
    assert recipe.kb_binding.scope == "ankor/public"
    # Check that node n1 has tenant and section_roles populated in params
    n1 = recipe.dag.nodes[0]
    assert n1.params.get("tenant") == "ankor"
    assert n1.params.get("section_roles") == ["public"]


@pytest.mark.asyncio
async def test_wiring_recipe_to_interpreter_entry() -> None:
    """Test wiring: passing Recipe with kb_binding into interpreter.run()."""
    from studio_engine.demo_stubs import EmptyEmbedding, EmptyKbSearch, FixtureLLM

    recipe = create_recipe_d4()
    result = await run(
        recipe,
        kb_search=EmptyKbSearch(),
        llm=FixtureLLM("smoke-01"),
        embedding=EmptyEmbedding(),
        trace_writer=None,
    )
    assert result.run_id is not None
    assert "n1" in result.final_state
