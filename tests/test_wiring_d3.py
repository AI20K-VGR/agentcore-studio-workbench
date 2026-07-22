"""Test wiring Recipe to Interpreter entry point (Day 3 SWE deliverable)."""

from __future__ import annotations

import pytest
from studio_contracts import Recipe
from studio_engine.interpreter import run
from studio_workbench import build_agent_config, create_sample_recipe_d3


def test_build_agent_config() -> None:
    """Kiểm tra hàm build_agent_config tạo đúng AgentConfig shape v0."""
    config = build_agent_config(
        instructions="Test prompt",
        model="gemini-2.5-flash",
        tool_whitelist=["kb_search"],
    )
    assert config.instructions == "Test prompt"
    assert config.model == "gemini-2.5-flash"
    assert config.tool_whitelist == ["kb_search"]


def test_create_sample_recipe_d3() -> None:
    """Kiểm tra recipe mẫu D3 gồm 3 node + 1 end node."""
    recipe = create_sample_recipe_d3()
    assert isinstance(recipe, Recipe)
    assert recipe.agent_id == "agent_demo_d3"
    assert len(recipe.dag.nodes) == 4
    assert recipe.dag.nodes[0].type.value == "kb-retrieve"
    assert recipe.dag.nodes[1].type.value == "llm-step"
    assert recipe.dag.nodes[2].type.value == "tool-call"
    assert recipe.dag.nodes[3].type.value == "end"


@pytest.mark.asyncio
async def test_wiring_recipe_to_interpreter() -> None:
    """Kiểm tra xâu kim: Nối Recipe từ Workbench sang Interpreter entry."""
    recipe = create_sample_recipe_d3()
    with pytest.raises(NotImplementedError):
        await run(recipe, trace_writer=None)  # type: ignore[arg-type]
