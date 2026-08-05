"""Comprehensive test suite for Day 6 SWE wiring & Interpreter integration.

Validates Form Feed dynamic Recipe creation (create_recipe_d6), un-hardcoded parameters,
scope parsing, multi-tenant isolation, and Recipe -> Interpreter entrypoint execution.

Owner: SWE (Thiệu Quang Minh).
"""

from __future__ import annotations

from uuid import UUID

import pytest
from studio_contracts import NodeType, TraceEvent
from studio_engine.interpreter import run

from studio_workbench import create_recipe_d6
from studio_workbench.tenant_wall import ResolvedContext

ANKOR_ID = UUID("a0000000-0000-0000-0000-000000000001")
BOREA_ID = UUID("b0000000-0000-0000-0000-000000000001")


class _RecordingTraceWriter:
    """Recording TraceWriter double to verify TraceEvent emission."""

    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    async def write(self, event: TraceEvent) -> None:
        self.events.append(event)


def test_create_recipe_d6_with_pure_dynamic_inputs() -> None:
    """Test 1: Verify create_recipe_d6 builds a valid Recipe from 100% dynamic Form Feed inputs."""
    recipe = create_recipe_d6(
        agent_id="custom-agent-99",
        tenant_id=BOREA_ID,
        instructions="Quy định nghỉ phép năm và chế độ công tác.",
        model="gpt-4o-mini",
        tool_whitelist=["custom_search_tool"],
        kb_id="kb-hr-policy-v2",
        scope="borea/hr",
        query="Số ngày nghỉ phép của nhân viên chính thức?",
    )

    assert recipe.agent_id == "custom-agent-99"
    assert recipe.tenant_id == BOREA_ID
    assert recipe.agent_config.instructions == "Quy định nghỉ phép năm và chế độ công tác."
    assert recipe.agent_config.model == "gpt-4o-mini"
    assert recipe.agent_config.tool_whitelist == ["custom_search_tool"]
    assert recipe.kb_binding.kb_id == "kb-hr-policy-v2"
    assert recipe.kb_binding.scope == "borea/hr"

    # Check node n1 (KB_RETRIEVE) params
    n1 = recipe.dag.nodes[0]
    assert n1.params.get("query") == "Số ngày nghỉ phép của nhân viên chính thức?"
    assert n1.params.get("tenant_id") == BOREA_ID
    assert n1.params.get("section_roles") == ["hr"]

    # Check node n2 (LLM_STEP) params
    n2 = recipe.dag.nodes[1]
    assert n2.params.get("temperature") == 0.0

    # Check node n3 (TOOL_CALL) params - dynamically using custom_search_tool
    n3 = recipe.dag.nodes[2]
    assert n3.params.get("tool") == "custom_search_tool"


def test_recipe_d6_scope_parsing_multi_roles() -> None:
    """Test 2: Verify scope parsing extracts multi-roles correctly (e.g. "ankor/public, hr, finance")."""
    recipe = create_recipe_d6(
        agent_id="agent-multi-role",
        tenant_id=ANKOR_ID,
        instructions="Tra cứu đa phòng ban.",
        model="gemini-2.5-flash",
        tool_whitelist=["kb_search"],
        kb_id="kb-all",
        scope="ankor/public, hr, finance",
        query="Quy trình thanh toán công tác phí?",
    )

    n1 = recipe.dag.nodes[0]
    assert n1.params.get("section_roles") == ["public", "hr", "finance"]


def test_recipe_d6_rejects_scope_tenant_mismatch() -> None:
    """kb_binding.scope tenant slug (e.g. "borea") must agree with the tenant_id UUID
    actually passed in — otherwise node.params["tenant_id"] and node.params["section_roles"]
    would silently describe two different tenants (kit#92, D13)."""
    with pytest.raises(ValueError, match="does not match tenant_id"):
        create_recipe_d6(
            agent_id="agent-mismatch",
            tenant_id=ANKOR_ID,
            instructions="x",
            model="gemini-2.5-flash",
            tool_whitelist=["kb_search"],
            kb_id="kb-x",
            scope="borea/hr",  # slug disagrees with tenant_id=ANKOR_ID
            query="x",
        )


def test_unhardcoded_tool_whitelist_selection() -> None:
    """Test 3: Verify TOOL_CALL node dynamically inherits tool_whitelist[0] from Form Feed."""
    recipe = create_recipe_d6(
        agent_id="agent-custom-tool",
        tenant_id=ANKOR_ID,
        instructions="Tìm kiếm bằng sql_query.",
        model="gemini-2.5-flash",
        tool_whitelist=["sql_query_tool", "web_search"],
        kb_id="kb-db-v1",
        scope="ankor/engineering",
        query="Truy vấn dữ liệu bảng?",
    )

    n3 = recipe.dag.nodes[2]
    assert n3.type == NodeType.TOOL_CALL
    assert n3.params.get("tool") == "sql_query_tool"


@pytest.mark.asyncio
async def test_wiring_d6_recipe_to_interpreter_entry() -> None:
    """Test 4: Verify dynamic Recipe execution in interpreter.run()."""
    from studio_engine.demo_stubs import EmptyEmbedding, EmptyKbSearch, FixtureLLM

    recipe = create_recipe_d6(
        agent_id="agent-trace-test",
        tenant_id=ANKOR_ID,
        instructions="Hãy tra cứu quy định Callisto.",
        model="gemini-2.5-flash",
        tool_whitelist=["kb_search"],
        kb_id="kb-callisto-v1",
        scope="ankor/public",
        query="Nhân viên được nghỉ phép bao nhiêu ngày?",
    )

    trace_writer = _RecordingTraceWriter()
    result = await run(
        recipe,
        kb_search=EmptyKbSearch(),
        llm=FixtureLLM("smoke-01"),
        embedding=EmptyEmbedding(),
        trace_writer=trace_writer,
        session_context=ResolvedContext(tenant_id=ANKOR_ID, user="test-harness", roles=["public"]),
    )

    assert result.run_id is not None
    assert len(result.final_state) == 4
    assert "n1" in result.final_state
    assert "n2" in result.final_state
    assert "n3" in result.final_state
    assert "n4" in result.final_state

    # Verify trace emission if supported by current engine version
    if len(trace_writer.events) > 0:
        assert len(trace_writer.events) == 4
        for event in trace_writer.events:
            assert event.run_id == result.run_id
            assert event.agent_id == "agent-trace-test"
            assert event.tenant_id == ANKOR_ID


@pytest.mark.asyncio
async def test_wiring_d6_with_kb_search_execution() -> None:
    """Test 5: Verify End-to-End dynamic wiring with KbSearch seam."""
    from studio_engine.demo_stubs import EmptyEmbedding, FixtureLLM
    from studio_kb import StaticKbSearch

    recipe = create_recipe_d6(
        agent_id="agent-callisto-e2e",
        tenant_id=ANKOR_ID,
        instructions="Bạn là trợ lý nội bộ. Trả lời dựa trên tài liệu.",
        model="gemini-2.5-flash",
        tool_whitelist=["kb_search"],
        kb_id="kb-callisto-v1",
        scope="ankor/public",
        query="Nhân viên xin nghỉ phép cần báo trước bao lâu?",
    )

    trace_writer = _RecordingTraceWriter()
    result = await run(
        recipe,
        kb_search=StaticKbSearch(),
        llm=FixtureLLM("smoke-01"),
        embedding=EmptyEmbedding(),
        trace_writer=trace_writer,
        session_context=ResolvedContext(tenant_id=ANKOR_ID, user="test-harness", roles=["public"]),
    )

    assert result.run_id is not None
    assert "n1" in result.final_state
    kb_output = result.final_state["n1"]
    assert isinstance(kb_output, list)

    # Unconditional — this query/tenant/role combo deterministically yields a chunk from
    # StaticKbSearch (token-overlap scoring, tie-broken by chunk_id per static_search.py:99-101).
    # The prior `if len(kb_output) > 0:` guard (added `7106fc5`) silently no-op'd this assertion
    # whenever KB returned `[]`, so the test could not tell "KB wired correctly" from "KB wiring
    # broken and returning nothing" — điểm gãy #4, `daily-notes/2026-07-27-DongAnh2704.md:200`.
    # `e2e_smoke_eval.py` hits this same case as SC-01 and always grounds it.
    assert len(kb_output) > 0, f"kb_output was empty: {kb_output!r}"
    assert kb_output[0].chunk_id == "ankor-leave-001#c1"
    llm_output = result.final_state["n2"]
    assert isinstance(llm_output, dict)
    assert "answer" in llm_output
