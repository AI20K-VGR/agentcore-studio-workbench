"""`validator.agent_shape_lint`/`enforce_agent_shape` spec tests (app#44 rewrite).

Replaces `test_graph_lint.py` (deleted — `graph_lint()` itself is removed, see
`validator.py` module docstring). 1 test per rule + a clean-pass test + an
`enforce_agent_shape` raise test.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from studio_contracts import (
    AgentConfig,
    Dag,
    KbBinding,
    Node,
    NodeType,
    Recipe,
    ScorecardThreshold,
)

from studio_workbench.validator import agent_shape_lint, enforce_agent_shape

# `ANKOR_ID`/`assert_finding_status` khai TẠI CHỖ, không `from conftest import` (workbench#53).
#
# Khớp convention 8 file khác trong package này (`test_publish.py`, `test_wb_schema.py`,
# `test_wiring_d4/d7/d8/d9.py`, ...) — mỗi file tự khai `ANKOR_ID` riêng. Một lượt `/simplify` gom
# hai helper này vào `conftest.py`, và hai file mới của workbench#48 đổi sang `from conftest import`.
#
# Vấn đề: workspace có 6 file `conftest.py` và `tests/` không phải package, nên tên module `conftest`
# bị tranh chấp — bên nào vào `sys.modules` trước thì thắng. Hai triệu chứng đo được:
#
#   mypy packages apps   ->  Module "conftest" has no attribute "ANKOR_ID"   (job `lint` của kit)
#   pytest (gốc kit)     ->  ImportError lúc thu thập, ABORT cả lượt chạy
#
# Cả hai VÔ HÌNH với CI của repo con: job ở đây chỉ chạy `packages/workbench`, nơi không có
# `conftest` nào tranh chấp. Duplicate hai dòng rẻ hơn hẳn mọi cách đi vòng.
ANKOR_ID = UUID("a0000000-0000-0000-0000-000000000001")


def assert_finding_status(findings: list[dict[str, str]], rule: str, expected: str) -> None:
    actual = next(f["status"] for f in findings if f["rule"] == rule)
    assert actual == expected, f"{rule}: expected status {expected!r}, got {actual!r} ({findings})"


# Star-shaped dag — shape-lint doesn't read this, but `Recipe.dag` is a required field.
_MINIMAL_DAG = Dag(nodes=[Node(id="llm-1", type=NodeType.LLM_STEP, params={})], edges=[])


def _valid_recipe(**overrides: object) -> Recipe:
    base: dict[str, object] = {
        "agent_id": "agent-1",
        "tenant_id": ANKOR_ID,
        "agent_config": AgentConfig(
            system_prompt="Answer from KB only.",
            model="gpt-4o-mini",
            tool_whitelist=["calculator"],
        ),
        "dag": _MINIMAL_DAG,
        "kb_binding": KbBinding(kb_id="kb-1", scope="ankor/public"),
        "golden_set_ref": "golden-set-1",
        "scorecard_threshold": ScorecardThreshold(success=0.9, citation_accuracy=0.95),
    }
    base.update(overrides)
    return Recipe(**base)


def test_valid_recipe_passes_every_rule() -> None:
    findings = agent_shape_lint(_valid_recipe())
    assert all(f["status"] == "OK" for f in findings), findings
    enforce_agent_shape(_valid_recipe())  # must not raise


def test_agent_id_blank_fails() -> None:
    findings = agent_shape_lint(_valid_recipe(agent_id="   "))
    assert_finding_status(findings, "agent_id.non_blank", "FAIL")


def test_system_prompt_blank_fails() -> None:
    recipe = _valid_recipe(
        agent_config=AgentConfig(system_prompt="  ", model="gpt-4o-mini", tool_whitelist=["calculator"])
    )
    findings = agent_shape_lint(recipe)
    assert_finding_status(findings, "agent_config.system_prompt_non_blank", "FAIL")


def test_model_blank_fails() -> None:
    recipe = _valid_recipe(agent_config=AgentConfig(system_prompt="hi", model="  ", tool_whitelist=["calculator"]))
    findings = agent_shape_lint(recipe)
    assert_finding_status(findings, "agent_config.model_non_blank", "FAIL")


def test_tool_whitelist_blank_entry_fails() -> None:
    recipe = _valid_recipe(agent_config=AgentConfig(system_prompt="hi", model="m", tool_whitelist=["calculator", "  "]))
    findings = agent_shape_lint(recipe)
    assert_finding_status(findings, "tool_whitelist.no_blank_entries", "FAIL")


def test_tool_whitelist_duplicate_fails() -> None:
    recipe = _valid_recipe(
        agent_config=AgentConfig(system_prompt="hi", model="m", tool_whitelist=["calculator", "calculator"])
    )
    findings = agent_shape_lint(recipe)
    assert_finding_status(findings, "tool_whitelist.no_duplicates", "FAIL")


# engine#49 — đảo A4: `kb_search` giờ là 1 phần tử BÌNH THƯỜNG của `tool_whitelist` (đúng
# `PROJECT-SCOPE-DEMO-DAY30.md`), không còn rule `tool_whitelist.no_kb_search` cấm khai nó (đã xoá
# khỏi `validator.py`) — test cũ `test_tool_whitelist_kb_search_fails` (khẳng định FAIL) bị thay
# bằng test này (khẳng định recipe có `kb_search` trong whitelist qua lint sạch, giống mọi tool
# khác) chứ không xoá trắng, để hành vi đảo A4 có 1 bài khoá thật.
def test_tool_whitelist_with_kb_search_passes_every_rule() -> None:
    recipe = _valid_recipe(agent_config=AgentConfig(system_prompt="hi", model="m", tool_whitelist=["kb_search"]))
    findings = agent_shape_lint(recipe)
    assert all(f["status"] == "OK" for f in findings), findings
    enforce_agent_shape(recipe)  # must not raise


def test_kb_id_blank_fails() -> None:
    recipe = _valid_recipe(kb_binding=KbBinding(kb_id="  ", scope="ankor/public"))
    findings = agent_shape_lint(recipe)
    assert_finding_status(findings, "kb_binding.kb_id_non_blank", "FAIL")


def test_kb_scope_blank_fails() -> None:
    recipe = _valid_recipe(kb_binding=KbBinding(kb_id="kb-1", scope="  "))
    findings = agent_shape_lint(recipe)
    assert_finding_status(findings, "kb_binding.scope_non_blank", "FAIL")


def test_golden_set_ref_blank_fails() -> None:
    findings = agent_shape_lint(_valid_recipe(golden_set_ref="  "))
    assert_finding_status(findings, "golden_set_ref.non_blank", "FAIL")


def test_enforce_agent_shape_raises_on_first_failure() -> None:
    with pytest.raises(ValueError, match="agent_shape_lint: agent_id.non_blank"):
        enforce_agent_shape(_valid_recipe(agent_id=""))
