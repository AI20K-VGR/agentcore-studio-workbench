"""Day 3 Wiring Test — SWE (Thiệu Quang Minh).

Kiểm tra luồng 'Xâu Kim' (Walking Skeleton):
1. Xuất AgentConfig đúng shape từ Form UI builder.
2. Đóng gói Recipe mẫu với 3 node (kb-retrieve -> llm-step -> tool-call -> end).
3. Nối (Wire) Recipe truyền vào Cổng vào (entry point) của Interpreter (`studio_engine.interpreter.run`).
"""

from __future__ import annotations

import pytest
from studio_contracts import Recipe
from studio_engine.interpreter import run
from studio_workbench.builder import build_agent_config, create_sample_recipe_d3


def test_build_agent_config_shape() -> None:
    """Kiểm tra hàm build_agent_config trả về đúng shape AgentConfig v0."""
    config = build_agent_config(
        instructions="Hãy tra cứu tài liệu Callisto.",
        model="gemini-2.5-flash",
        tool_whitelist=["kb_search"],
    )
    assert config.instructions == "Hãy tra cứu tài liệu Callisto."
    assert config.model == "gemini-2.5-flash"
    assert config.tool_whitelist == ["kb_search"]


def test_create_sample_recipe_d3_nodes() -> None:
    """Kiểm tra Recipe mẫu Ngày 3 chứa đủ 3 node theo đúng thứ tự + node END."""
    recipe = create_sample_recipe_d3()
    assert isinstance(recipe, Recipe)
    assert recipe.agent_id == "agent_demo_d3"
    assert recipe.tenant == "ankor"

    # Kiểm tra 4 nodes (kb-retrieve, llm-step, tool-call, end)
    node_types = [node.type.value for node in recipe.dag.nodes]
    assert node_types == ["kb-retrieve", "llm-step", "tool-call", "end"]

    # Kiểm tra edges kết nối đúng thứ tự
    edge_pairs = [(e.from_, e.to) for e in recipe.dag.edges]
    assert edge_pairs == [
        ("node_1", "node_2"),
        ("node_2", "node_3"),
        ("node_3", "node_4"),
    ]


@pytest.mark.asyncio
async def test_wiring_recipe_to_interpreter_entry() -> None:
    """Kiểm tra Wiring: Nối Recipe mẫu từ Workbench sang Interpreter entry (`interpreter.run`).

    Vì thân hàm `run()` của Engine do AIE-1 phụ trách ném `NotImplementedError`,
    việc bắt lỗi `NotImplementedError` xác nhận dữ liệu Recipe từ Workbench
    đã được truyền thành công tới cổng vào của Engine.
    """
    recipe = create_sample_recipe_d3()

    with pytest.raises(NotImplementedError) as exc_info:
        await run(recipe, trace_writer=None)  # type: ignore[arg-type]

    assert "spec AIE-1: interpreter run() body" in str(exc_info.value)
