"""Test suite for Day 3 SWE wiring — Recipe -> Interpreter entry.

Owner: SWE (Thiệu Quang Minh — Issue Day 3).
"""

from __future__ import annotations

from uuid import UUID

import pytest
from studio_engine.interpreter import run
from studio_workbench import build_agent_config, create_sample_recipe_d3

ANKOR_ID = UUID("a0000000-0000-0000-0000-000000000001")


def test_build_agent_config_structure() -> None:
    """Test build_agent_config helper output."""
    config = build_agent_config(
        instructions="System prompt text",
        model="gemini-2.5-flash",
        tool_whitelist=["kb_search"],
    )
    assert config.instructions == "System prompt text"
    assert config.model == "gemini-2.5-flash"
    assert config.tool_whitelist == ["kb_search"]


def test_create_recipe_d3_structure() -> None:
    """Test that create_sample_recipe_d3 builds a 3-node Recipe instance."""
    recipe = create_sample_recipe_d3()
    assert recipe.agent_id == "agent_demo_d3"
    assert recipe.tenant_id == ANKOR_ID
    assert len(recipe.dag.nodes) == 4
    assert len(recipe.dag.edges) == 3


@pytest.mark.asyncio
async def test_wiring_d3_recipe_to_interpreter() -> None:
    """Test Day 3 wiring: passing Recipe to interpreter.run()."""
    from studio_engine.demo_stubs import EmptyEmbedding, EmptyKbSearch, FixtureLLM

    recipe = create_sample_recipe_d3()
    result = await run(
        recipe,
        kb_search=EmptyKbSearch(),
        llm=FixtureLLM("smoke-01"),
        embedding=EmptyEmbedding(),
        trace_writer=None,
    )
    assert result.run_id is not None
    assert len(result.final_state) > 0
