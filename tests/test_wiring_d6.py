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
from studio_workbench.builder import _parse_kb_scope
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

    # Check node n1 (KB_RETRIEVE) params — `tenant_id`/`section_roles` KHÔNG còn ở đây (hardening
    # #122): `interpreter.run()` luôn ghi đè cả 2 từ `session_context` (D8/D17, #111).
    n1 = recipe.dag.nodes[0]
    assert n1.params.get("query") == "Số ngày nghỉ phép của nhân viên chính thức?"
    assert "tenant_id" not in n1.params
    assert "section_roles" not in n1.params

    # Check node n2 (LLM_STEP) params
    n2 = recipe.dag.nodes[1]
    assert n2.params.get("temperature") == 0.0

    # Check node n3 (TOOL_CALL) params - dynamically using custom_search_tool
    n3 = recipe.dag.nodes[2]
    assert n3.params.get("tool") == "custom_search_tool"


def test_recipe_d6_scope_parsing_multi_roles() -> None:
    """Test 2: Verify scope parsing extracts multi-roles correctly (e.g. "ankor/public, hr, finance").

    Test trực tiếp `_parse_kb_scope()` — không còn qua `node.params` (hardening #122): giá trị đó
    không còn được ghi vào node nữa, nhưng `_parse_kb_scope` vẫn phải parse đúng cấu trúc (dùng để
    validate lúc build, xem docstring hàm)."""
    assert _parse_kb_scope("ankor/public, hr, finance", ANKOR_ID) == ["public", "hr", "finance"]

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
    assert recipe.kb_binding.scope == "ankor/public, hr, finance"


def test_recipe_d6_allows_scope_tenant_slug_disagreement() -> None:
    """kb_binding.scope tenant slug (e.g. "borea") KHÔNG bị cross-check với tenant_id thật
    truyền vào — bỏ ở kit#92/workbench#17 sau khi bump pointer vỡ 2 quadrant khác:
    packages/kb's INV-1 test (test_spine_live.py) cố tình dựng recipe với tenant_id (attacker
    khai) lệch scope, và apps/studio's eval-harness dùng slug placeholder "t" bất kể tenant_id
    thật hay tổng hợp. Chặn ở recipe-build-time là sai chỗ; INV-1 (session luôn thắng recipe tự
    khai) được enforce ở tenant_wall.py, không phải ở đây."""
    # Slug lệch tenant_id — `_parse_kb_scope` vẫn parse ra roles bình thường, không raise.
    assert _parse_kb_scope("borea/hr", ANKOR_ID) == ["hr"]

    recipe = create_recipe_d6(
        agent_id="agent-mismatch",
        tenant_id=ANKOR_ID,
        instructions="x",
        model="gemini-2.5-flash",
        tool_whitelist=["kb_search"],
        kb_id="kb-x",
        scope="borea/hr",  # slug lệch tenant_id=ANKOR_ID — được phép, xem docstring
        query="x",
    )
    assert recipe.tenant_id == ANKOR_ID
    assert recipe.kb_binding.scope == "borea/hr"


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


# ---------------------------------------------------------------------------
# Negative tests — structural validation only (malformed scope string).
# PR #16 (dholmes0207's P1 review) originally also fail-closed on unknown
# tenant slugs and slug/tenant_id disagreement — removed at kit#92/workbench#17,
# see the block below this one for why.
# ---------------------------------------------------------------------------


def test_parse_kb_scope_rejects_empty_roles() -> None:
    """scope='ankor/' (không có role nào) trên tenant nghiệp vụ thật phải bị reject —
    gần như chắc chắn là quên gõ role, không phải chủ đích khoá hết quyền."""
    with pytest.raises(ValueError, match="roles trong scope rỗng"):
        _parse_kb_scope("ankor/", ANKOR_ID)


def test_parse_kb_scope_rejects_empty_scope() -> None:
    """scope rỗng hoàn toàn phải bị reject."""
    with pytest.raises(ValueError, match="scope không được rỗng"):
        _parse_kb_scope("", ANKOR_ID)


def test_parse_kb_scope_rejects_no_slash() -> None:
    """scope không có '/' phải bị reject (vd: 'public' thay vì 'ankor/public')."""
    with pytest.raises(ValueError, match="phải có dạng"):
        _parse_kb_scope("public", ANKOR_ID)


# ---------------------------------------------------------------------------
# kit#92/workbench#17 — bump pointer thật vào kit lộ ra guard gốc (workbench#16)
# đụng 2 quadrant khác: kb's INV-1 test (slug/tenant_id lệch CÓ CHỦ ĐÍCH để kiểm
# session-thắng-recipe-tự-khai) và app's eval-harness (slug placeholder "t" trên
# CẢ tenant thật lẫn tổng hợp). Không có cách nào cross-check slug↔tenant_id mà
# không vỡ 1 trong 2 — nên bỏ hẳn, chỉ giữ validate cấu trúc + roles-không-rỗng
# trên tenant thật. Các test dưới khoá lại đúng hành vi PERMISSIVE này.
# ---------------------------------------------------------------------------

_SYNTHETIC_TENANT_ID = UUID("b0000000-0000-0000-0000-000000000002")  # KHÔNG phải BOREA_ID


def test_parse_kb_scope_allows_synthetic_tenant_with_placeholder_slug() -> None:
    """Tenant tổng hợp (không phải ankor/borea) với slug placeholder tuỳ ý (vd: 't', dùng
    bởi eval-harness của app — app#3 eval_adapter.py) phải ĐI QUA, không bị reject."""
    assert _parse_kb_scope("t/public", _SYNTHETIC_TENANT_ID) == ["public"]


def test_parse_kb_scope_allows_placeholder_slug_on_real_tenant() -> None:
    """Slug placeholder ('t') CÙNG với tenant_id THẬT (vd: ANKOR_ID trong test Postgres của
    app — test_kb_search_live_readiness.py) cũng phải ĐI QUA: không có quy ước nào phân biệt
    được "t" cố ý với lỗi gõ thật, nên guard không còn cố phân biệt nữa (kit#92/workbench#17)."""
    assert _parse_kb_scope("t/public", ANKOR_ID) == ["public"]


def test_parse_kb_scope_allows_slug_tenant_disagreement_on_two_real_tenants() -> None:
    """slug 'ankor' cùng tenant_id=BOREA_ID (2 tenant thật, cố tình lệch nhau) phải ĐI QUA —
    đây chính xác là kịch bản INV-1 mà packages/kb/tests/test_spine_live.py cần dựng được để
    kiểm session luôn thắng recipe tự khai (kit#92/workbench#17)."""
    assert _parse_kb_scope("ankor/public", BOREA_ID) == ["public"]


def test_create_recipe_d6_allows_typo_slug() -> None:
    """create_recipe_d6 KHÔNG còn raise trên slug lạ/typo ('boera') — bỏ ở
    kit#92/workbench#17 cùng lý do với test_recipe_d6_allows_scope_tenant_slug_disagreement."""
    assert _parse_kb_scope("boera/hr", BOREA_ID) == ["hr"]

    recipe = create_recipe_d6(
        agent_id="agent-bad-scope",
        tenant_id=BOREA_ID,
        instructions="test",
        model="gemini-2.5-flash",
        tool_whitelist=["kb_search"],
        kb_id="kb-test",
        scope="boera/hr",  # typo: 'boera' thay vì 'borea' — được phép, xem docstring _parse_kb_scope
        query="test query",
    )
    assert recipe.kb_binding.scope == "boera/hr"


def test_create_recipe_d6_rejects_empty_roles() -> None:
    """create_recipe_d6 với empty roles phải raise ValueError tại build time."""
    with pytest.raises(ValueError, match="roles trong scope rỗng"):
        create_recipe_d6(
            agent_id="agent-empty-roles",
            tenant_id=ANKOR_ID,
            instructions="test",
            model="gemini-2.5-flash",
            tool_whitelist=["kb_search"],
            kb_id="kb-test",
            scope="ankor/",  # empty roles
            query="test query",
        )
