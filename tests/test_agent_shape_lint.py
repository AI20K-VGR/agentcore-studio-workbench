"""`validator.agent_shape_lint`/`enforce_agent_shape` spec tests (app#44 rewrite).

Replaces `test_graph_lint.py` (deleted — `graph_lint()` itself is removed, see
`validator.py` module docstring). 1 test per rule + a clean-pass test + an
`enforce_agent_shape` raise test.
"""

from __future__ import annotations

import pytest
from conftest import ANKOR_ID, assert_finding_status
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


def test_tool_whitelist_kb_search_fails() -> None:
    recipe = _valid_recipe(agent_config=AgentConfig(system_prompt="hi", model="m", tool_whitelist=["kb_search"]))
    findings = agent_shape_lint(recipe)
    assert_finding_status(findings, "tool_whitelist.no_kb_search", "FAIL")


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
