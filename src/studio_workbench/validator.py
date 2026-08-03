"""Recipe validator / graph-lint seam (R-SPEC A1#1 :36) — bút SWE.

`graph_lint(recipe)` MUST enforce exactly these 4 rules before a recipe is allowed to reach the
engine (AIE-1) interpreter — "recipe không qua validator = không interpret" (R-SPEC A1#1):

1. **node ∈ 6 closed `NodeType`** — every `Node.type` in `recipe.dag.nodes` must be one of the 6
   values in `studio_contracts.NodeType`. `Recipe`/`Node` already close this via pydantic's enum
   validation at normal construction time, so this rule is largely defense-in-depth against a
   recipe that reached this function WITHOUT having gone through full contract validation (e.g.
   built via `model_construct`, or read back from `wb.recipes.recipe` jsonb after a future
   contract change this deployment doesn't know about yet).
2. **no forbidden cycle** — the DAG (`recipe.dag.nodes` + `recipe.dag.edges`) must not contain a
   cycle; a cyclic recipe must never reach the interpreter (R-SPEC A1#1 turing-completeness cap).
3. **every edge has a resolvable destination** — `edge.to` must name a node id that actually
   exists in `recipe.dag.nodes`; a dangling edge is rejected, never silently dropped.
4. **tool ∈ `tool_whitelist`** — every tool referenced by a `tool-call` node (its `params["tool"]`)
   must be present in `recipe.agent_config.tool_whitelist`; a tool outside the whitelist is
   rejected.

D11: real 4-rule body implemented below. Order matters — node-type validity is checked
first (defense-in-depth against a bypassed-construction recipe), then edge destinations
(so the cycle walk below never has to guess at a dangling `edge.to`), then the cycle walk
itself, then the tool-whitelist check last (cheapest, and only meaningful once the graph
shape above is already known-good).
"""

from __future__ import annotations

from studio_contracts import NodeType, Recipe


def graph_lint(recipe: Recipe) -> None:
    """Validate `recipe`'s DAG against the 4 rules documented above.

    Raises `ValueError` on the first violation found (never returns a boolean/error-list —
    a recipe either passes cleanly or it does not reach the interpreter at all). Returns
    `None` on success.
    """
    dag = recipe.dag
    node_ids = {node.id for node in dag.nodes}

    # Rule 1 — node ∈ 6 closed NodeType. Pydantic already closes this at normal
    # construction time; `NodeType(node.type)` re-validates so a recipe that reached this
    # function via `model_construct` (bypassing that check) is still caught here rather
    # than crashing the interpreter with an unrecognized node type.
    for node in dag.nodes:
        try:
            NodeType(node.type)
        except ValueError as exc:
            raise ValueError(
                f"graph_lint: node {node.id!r} has type {node.type!r}, "
                "not one of the 6 closed NodeType values"
            ) from exc

    # Rule 3 — every edge must resolve to a real node id on both ends. Checked before the
    # cycle walk (rule 2) so that walk never has to special-case a `to`/`from_` pointing at
    # a node that doesn't exist.
    for edge in dag.edges:
        if edge.from_ not in node_ids:
            raise ValueError(
                f"graph_lint: edge {edge.from_!r} -> {edge.to!r} has no resolvable "
                f"source (node {edge.from_!r} does not exist)"
            )
        if edge.to not in node_ids:
            raise ValueError(
                f"graph_lint: edge {edge.from_!r} -> {edge.to!r} has no resolvable "
                f"destination (node {edge.to!r} does not exist)"
            )

    # Rule 2 — no forbidden cycle. Standard 3-color DFS: WHITE = unvisited, GRAY = on the
    # current recursion stack, BLACK = fully explored. Hitting a GRAY node means the walk
    # looped back on itself.
    adjacency: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    for edge in dag.edges:
        adjacency[edge.from_].append(edge.to)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = dict.fromkeys(node_ids, WHITE)

    def _walk(node_id: str) -> None:
        color[node_id] = GRAY
        for neighbor in adjacency[node_id]:
            if color[neighbor] == GRAY:
                raise ValueError(
                    f"graph_lint: recipe.dag has a forbidden cycle involving node {neighbor!r}"
                )
            if color[neighbor] == WHITE:
                _walk(neighbor)
        color[node_id] = BLACK

    for node_id in node_ids:
        if color[node_id] == WHITE:
            _walk(node_id)

    # Rule 4 — every `tool-call` node's tool must be in agent_config.tool_whitelist.
    whitelist = set(recipe.agent_config.tool_whitelist)
    for node in dag.nodes:
        if node.type == NodeType.TOOL_CALL:
            tool = node.params.get("tool")
            if tool not in whitelist:
                raise ValueError(
                    f"graph_lint: node {node.id!r} uses tool {tool!r}, "
                    f"not in agent_config.tool_whitelist {sorted(whitelist)!r}"
                )
