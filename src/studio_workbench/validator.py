"""Recipe validator seam (bút SWE) — `agent_shape_lint`/`agent_topology_lint` + 2 raise wrapper.

**app#44 rewrite:** `graph_lint()` (the old 7-rule `recipe.dag` topology lint, R-SPEC A1#1) is
REMOVED, not relaxed. It existed to gate `interpreter.run()`'s DAG-walk ("recipe không qua
validator = không interpret"); that gate no longer applies — grepped every production execution
path in `apps/studio` and neither calls `interpreter.run()` anymore: `/chat` and the eval-gate
harness (`eval_adapter.py::run_case`) both go through `studio_engine.agent_loop.run_agent_loop()`,
which never reads `recipe.dag` at all (only `recipe.agent_id` and
`recipe.agent_config.{system_prompt,model,tool_whitelist}` are read). `eval_adapter.py`'s own
docstring already said as much and retired `test_graph_lint_before_interpreter_run.py` for the
same reason.

Replaced by 2 independent lints, different object, different reason to exist:

1. `agent_shape_lint(recipe)` — shape of `agent_config`/`kb_binding`/`golden_set_ref`/`agent_id`.
   Does NOT read `recipe.dag`. Gates the "1 LLM + N tool" architecture
   (`run_agent_loop()`/`/chat`/`/publish`).
2. `agent_topology_lint(recipe)` — shape of `recipe.dag` ONLY. The canvas UI still sends real,
   user-drawn nodes/edges (`routes/publish.py::PublishRequest.nodes/edges`, not a fixed dummy
   shape), and `dag` is still stored in `wb.recipes` and read back to reconstruct the canvas view
   (`apps/web`'s `fromRecipe()`) — a malformed `dag` can still corrupt that read path even though
   nothing executes it anymore. Enforces a star topology: exactly 1 `llm-step` node at the
   center, 0-1 `kb-retrieve` node and 0..N `tool-call` nodes as spokes, each spoke directly
   edged to the LLM node, no other node type, no other edge shape. Deliberately has NO "tool
   hub" node — proposed once already and rejected on the same grounds this rewrite rests on
   (`kit#206`, 2026-08-24: "canvas Hub-and-Spoke fan-out was proposed and AIE-1 confirmed keep
   this rule blocking ... Hub-and-Spoke stays a canvas-layout concept; the exported DAG stays
   linear" — `run_agent_loop()` picks tools from `tool_whitelist` at runtime via the `TOOL_CALL:`
   text signal, never from DAG edges, so a hub node would carry zero execution meaning). Does
   NOT add a 7th `NodeType` either — closed-set enforcement is locked 3 layers deep in this repo
   specifically to forbid the DAG becoming a Turing-complete DSL (`packages/engine/registry.py:
   2-10`, R-SPEC A2); a `tool-call` node carries its own `params["tool"]`, no child node needed.

Deliberately NOT preserved from the old `graph_lint` (product decision, not an oversight — call
sites outside this package that still assume the old 7-rule shape, e.g. `apps/studio`'s routes
and `apps/web`'s TS mirror `graphLint.ts` + its CI parity check, are OUT OF SCOPE for this change
and will break until updated separately): cycle detection (moot — a star graph centered on 1 hub
node cannot contain a cycle by construction, rule 9 below already rejects any edge that isn't
hub-spoke), the temporary "<=1 outgoing edge, `ConditionExecutor` not ready yet" cap (moot — no
`condition` node is allowed at all anymore), and the "walk terminates on `end`" rule (moot — no
`end` node is allowed at all anymore).

Both lints are pure: no I/O, no DB, no network, no execution, no dependency on which tools have
real dispatchers (that is `apps/studio/providers/tool_dispatch.py::SUPPORTED_TOOLS`, app-layer/
deployment knowledge this package must not depend on — `packages/workbench/pyproject.toml` only
depends on `agentcore-studio-contracts`, never `apps/studio` or `packages/engine`; adding either
would invert the dependency direction the whole repo relies on).

Both return ALL findings in one pass (`list[dict[str, str]]`, same plain-dict shape
`routes/runs.py::ConnectivityCheckResponse.results` already uses — a pydantic sub-model here
would hit the exact `== dict` equality bug that shape was chosen to avoid), not raise-on-first —
better for a UI that wants to show every problem at once, not one violation per resubmit.

`enforce_agent_shape`/`enforce_agent_topology` are the raise-based wrappers for the 2 in-package
call sites that need a hard gate with the OLD `graph_lint` calling convention
(`canvas.py::recipe_from_canvas`, `publish.py::publish` — both now call BOTH wrappers, since a
canvas-built recipe needs both its shape and its topology checked). Raises `ValueError` on the
first `FAIL` finding, same "fail-closed, never return a recipe/report the caller might forget to
check" contract `graph_lint` had.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable

from studio_contracts import NodeType, Recipe

# Bản sao literal của `studio_engine.agent_protocol.KB_SEARCH_TOOL` — package này KHÔNG (và không
# nên) phụ thuộc `agentcore-studio-engine` (xem docstring module ở trên: workbench chỉ phụ thuộc
# `agentcore-studio-contracts`). Đổi 1 bên thì phải đổi cả 2 — cùng idiom "accepted duplication"
# `agent_loop.py` đã dùng cho `_CITATION_RE`/belt-1-belt-2.
_KB_SEARCH_TOOL = "kb_search"

_ALLOWED_TOPOLOGY_TYPES = frozenset({NodeType.LLM_STEP, NodeType.KB_RETRIEVE, NodeType.TOOL_CALL})


def _finding(rule: str, ok: bool, detail_fn: Callable[[], str] = lambda: "") -> dict[str, str]:
    """`detail_fn` is only called on `FAIL` — every rule below builds its detail message (list
    comprehensions, `sorted()`, ...) lazily, so the common case (a clean recipe, every rule `OK`)
    never pays for formatting a message nothing will read (`/simplify` efficiency review)."""
    return {"rule": rule, "status": "OK" if ok else "FAIL", "detail": "" if ok else detail_fn()}


def _find_duplicates(items: Iterable[str]) -> list[str]:
    """First-seen-order list of values that appear more than once in `items`. Shared by every
    "no duplicate X" rule below (`/simplify` review — was 3 hand-copies of this exact loop)."""
    seen: set[str] = set()
    dupes: list[str] = []
    for item in items:
        if item in seen and item not in dupes:
            dupes.append(item)
        seen.add(item)
    return dupes


def agent_shape_lint(recipe: Recipe) -> list[dict[str, str]]:
    """Structural shape check for the "1 LLM + N tool" recipe — does NOT read `recipe.dag`.

    Returns every finding, in the fixed order below, regardless of how many fail — never raises,
    never short-circuits. Order is stable so a UI/test can index into it deterministically.
    """
    findings: list[dict[str, str]] = []

    findings.append(
        _finding("agent_id.non_blank", bool(recipe.agent_id.strip()), lambda: "agent_id rỗng hoặc chỉ có khoảng trắng")
    )

    findings.append(
        _finding(
            "agent_config.system_prompt_non_blank",
            bool(recipe.agent_config.system_prompt.strip()),
            lambda: "system_prompt rỗng hoặc chỉ có khoảng trắng",
        )
    )
    findings.append(
        _finding(
            "agent_config.model_non_blank",
            bool(recipe.agent_config.model.strip()),
            lambda: "model rỗng hoặc chỉ có khoảng trắng",
        )
    )

    whitelist = recipe.agent_config.tool_whitelist

    blanks = [i for i, tool in enumerate(whitelist) if not tool.strip()]
    findings.append(_finding("tool_whitelist.no_blank_entries", not blanks, lambda: f"vị trí rỗng: {blanks}"))

    tool_dupes = _find_duplicates(whitelist)
    findings.append(_finding("tool_whitelist.no_duplicates", not tool_dupes, lambda: f"trùng: {sorted(tool_dupes)}"))

    findings.append(
        _finding(
            "tool_whitelist.no_kb_search",
            _KB_SEARCH_TOOL not in whitelist,
            lambda: "kb_search luôn khả dụng (A4, run_agent_loop), không cần/không nên khai trong tool_whitelist",
        )
    )

    findings.append(
        _finding(
            "kb_binding.kb_id_non_blank",
            bool(recipe.kb_binding.kb_id.strip()),
            lambda: "kb_binding.kb_id rỗng hoặc chỉ có khoảng trắng",
        )
    )
    findings.append(
        _finding(
            "kb_binding.scope_non_blank",
            bool(recipe.kb_binding.scope.strip()),
            lambda: "kb_binding.scope rỗng hoặc chỉ có khoảng trắng",
        )
    )

    findings.append(
        _finding(
            "golden_set_ref.non_blank",
            bool(recipe.golden_set_ref.strip()),
            lambda: "golden_set_ref rỗng hoặc chỉ có khoảng trắng",
        )
    )

    return findings


def _enforce(label: str, findings: list[dict[str, str]]) -> None:
    """Shared body of `enforce_agent_shape`/`enforce_agent_topology`: raise `ValueError` on the
    first `FAIL` finding, `label` naming which lint produced it. (`/simplify` review — the 2
    wrappers were identical except this label.)"""
    for finding in findings:
        if finding["status"] == "FAIL":
            raise ValueError(f"{label}: {finding['rule']} — {finding['detail']}")


def enforce_agent_shape(recipe: Recipe) -> None:
    """Hard gate: raise `ValueError` on the first `FAIL` finding from `agent_shape_lint(recipe)`."""
    _enforce("agent_shape_lint", agent_shape_lint(recipe))


def agent_topology_lint(recipe: Recipe) -> list[dict[str, str]]:
    """Star-topology check for `recipe.dag` — does NOT read `agent_config`/`kb_binding`/etc.

    Shape enforced: exactly 1 `llm-step` node at the center; 0-1 `kb-retrieve` node and 0..N
    `tool-call` nodes as spokes, each directly edged to the LLM node; no other node type; no
    other edge shape; no duplicate `tool-call` tool names; no duplicate node ids. See module
    docstring for the full rationale (`kit#206`, R-SPEC A2 closed-NodeType-set).

    Returns every finding, in the fixed order below, regardless of how many fail — never raises.
    Rules 3-9 that need to reference "the LLM node"/"the kb-retrieve node" degrade gracefully
    when that node doesn't exist (0 or >1 candidates) — they report against `None`, never raise
    an internal `KeyError`/`IndexError` on malformed input, since malformed input is exactly what
    this function exists to describe, not crash on.
    """
    findings: list[dict[str, str]] = []
    dag = recipe.dag
    nodes = dag.nodes
    edges = dag.edges
    valid_ids = {node.id for node in nodes}

    dup_ids = _find_duplicates(node.id for node in nodes)
    findings.append(_finding("dag.no_duplicate_node_ids", not dup_ids, lambda: f"trùng id: {sorted(dup_ids)}"))

    disallowed = [node.id for node in nodes if node.type not in _ALLOWED_TOPOLOGY_TYPES]
    findings.append(
        _finding(
            "dag.only_llm_kb_tool_node_types",
            not disallowed,
            lambda: f"node dùng type không cho phép (chỉ llm-step/kb-retrieve/tool-call): {disallowed}",
        )
    )

    llm_nodes = [node for node in nodes if node.type == NodeType.LLM_STEP]
    findings.append(
        _finding(
            "dag.exactly_one_llm_node",
            len(llm_nodes) == 1,
            lambda: f"cần đúng 1 node llm-step, tìm thấy {len(llm_nodes)}: {[n.id for n in llm_nodes]}",
        )
    )
    llm_id = llm_nodes[0].id if len(llm_nodes) == 1 else None

    kb_nodes = [node for node in nodes if node.type == NodeType.KB_RETRIEVE]
    findings.append(
        _finding(
            "dag.at_most_one_kb_retrieve_node",
            len(kb_nodes) <= 1,
            lambda: f"nhiều nhất 1 node kb-retrieve, tìm thấy {len(kb_nodes)}: {[n.id for n in kb_nodes]}",
        )
    )
    kb_id = kb_nodes[0].id if len(kb_nodes) == 1 else None

    tool_nodes = [node for node in nodes if node.type == NodeType.TOOL_CALL]
    # Mọi node được phép làm "cánh" của hình sao (kb-retrieve + tool-call, KHÔNG gồm chính LLM).
    spoke_ids = {i for i in (kb_id, *(node.id for node in tool_nodes)) if i is not None}

    # 1 lần duyệt `edges` DUY NHẤT, dùng chung cho cả luật 5/6 (spoke đã khai phải có cạnh tới
    # hub) lẫn luật 9 (mọi cạnh phải là cạnh hub-spoke hợp lệ) — trước bản vá này 2 luật tự tính
    # lại "cạnh có chạm hub không" ở 2 nơi tách biệt, và chỉ 1 trong 2 nơi lọc cạnh treo
    # (`/simplify` review, altitude+efficiency). Không ép chiều (`from`/`to` đều hợp lệ).
    llm_neighbor_ids: set[str] = set()
    bad_edges: list[str] = []
    for edge in edges:
        resolvable = edge.from_ in valid_ids and edge.to in valid_ids
        other_end = edge.to if edge.from_ == llm_id else edge.from_
        touches_llm = llm_id is not None and (edge.from_ == llm_id or edge.to == llm_id)
        is_valid_spoke_edge = resolvable and touches_llm and other_end in spoke_ids
        if is_valid_spoke_edge:
            llm_neighbor_ids.add(other_end)
        else:
            bad_edges.append(f"{edge.from_!r}->{edge.to!r}")

    findings.append(
        _finding(
            "dag.kb_retrieve_connects_to_llm",
            kb_id is None or kb_id in llm_neighbor_ids,
            lambda: f"node kb-retrieve {kb_id!r} không có cạnh nối trực tiếp với node llm-step",
        )
    )

    unconnected_tools = [node.id for node in tool_nodes if node.id not in llm_neighbor_ids]
    findings.append(
        _finding(
            "dag.tool_call_connects_to_llm",
            not unconnected_tools,
            lambda: f"node tool-call không có cạnh nối trực tiếp với node llm-step: {unconnected_tools}",
        )
    )

    tool_names_by_node = {node.id: node.params.get("tool") for node in tool_nodes}
    blank_tool_nodes = [
        node_id for node_id, tool in tool_names_by_node.items() if not isinstance(tool, str) or not tool.strip()
    ]
    findings.append(
        _finding(
            "dag.tool_call_has_non_blank_tool",
            not blank_tool_nodes,
            lambda: f"node tool-call thiếu/rỗng params['tool']: {blank_tool_nodes}",
        )
    )

    named_tools = [tool for tool in tool_names_by_node.values() if isinstance(tool, str) and tool.strip()]
    dup_tools = _find_duplicates(named_tools)
    findings.append(
        _finding("dag.tool_call_no_duplicate_tools", not dup_tools, lambda: f"tool trùng lặp: {sorted(dup_tools)}")
    )

    findings.append(
        _finding(
            "dag.edges_are_llm_hub_spokes_only",
            not bad_edges,
            lambda: f"cạnh không thuộc hình sao (llm-step <-> kb-retrieve/tool-call): {bad_edges}",
        )
    )

    return findings


def enforce_agent_topology(recipe: Recipe) -> None:
    """Hard gate: raise `ValueError` on the first `FAIL` finding from `agent_topology_lint(recipe)`."""
    _enforce("agent_topology_lint", agent_topology_lint(recipe))
