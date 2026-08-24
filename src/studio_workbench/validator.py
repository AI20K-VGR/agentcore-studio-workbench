"""Recipe validator / graph-lint seam (R-SPEC A1#1 :36) — bút SWE.

`graph_lint(recipe)` MUST enforce exactly these 7 rules before a recipe is allowed to reach the
engine (AIE-1) interpreter — "recipe không qua validator = không interpret" (R-SPEC A1#1):

1. **node ∈ 6 closed `NodeType`** — every `Node.type` in `recipe.dag.nodes` must be one of the 6
   values in `studio_contracts.NodeType`. `Recipe`/`Node` already close this via pydantic's enum
   validation at normal construction time, so this rule is largely defense-in-depth against a
   recipe that reached this function WITHOUT having gone through full contract validation (e.g.
   built via `model_construct`, or read back from `wb.recipes.recipe` jsonb after a future
   contract change this deployment doesn't know about yet).
2. **every edge has a resolvable destination** — `edge.to` must name a node id that actually
   exists in `recipe.dag.nodes`; a dangling edge is rejected, never silently dropped.
3. **exactly 1 start node** — exactly one node id must have no incoming edge (`edge.to`); 0 or
   >1 candidates means the DAG doesn't describe a single walkable chain and the interpreter
   would have no unambiguous place to begin.
4. **every node has ≤ 1 outgoing edge** — TEMPORARY, tied to AIE-1's `ConditionExecutor`
   progress (kit#87 issue thread, 2026-08-04): the interpreter cannot yet evaluate `condition`
   branching (`Edge.when`), so a node with >1 outgoing edge would let a recipe reach the
   interpreter with a branch it cannot walk. This rejects EVERY recipe with real `condition`
   branching, including structurally valid ones, until `ConditionExecutor` is implemented — at
   which point this rule must be relaxed to allow `condition` nodes to fan out. AIE-1 owns
   the signal for when that is; do not relax unilaterally. First real invocation of this
   signal: kit#206 (2026-08-24) — canvas Hub-and-Spoke fan-out was proposed and AIE-1 (Trần
   Bá Đạt) confirmed **keep this rule blocking**: `engine#36`'s `run_agent_loop()` picks tools
   at runtime from the whitelist/registry via a `TOOL_CALL:` signal, not from DAG fan-out
   edges, so a fan-out edge is the wrong mechanism for representing "1 LLM + N tools" — not
   merely "correct but not yet implemented". Hub-and-Spoke stays a canvas-layout concept; the
   exported DAG stays linear. See `docs/decisions/recipe.md` ADR-D24-01.
5. **no forbidden cycle** — the DAG (`recipe.dag.nodes` + `recipe.dag.edges`) must not contain a
   cycle; a cyclic recipe must never reach the interpreter (R-SPEC A1#1 turing-completeness cap).
6. **the walk terminates ON an `end` node** — starting from the single start node and following
   each node's (at most one) outgoing edge, the chain must reach a node of type
   `NodeType.END`. Running out of edges before hitting an `end` node is rejected; an `end` node
   being merely reachable but not on the walked chain does not satisfy this rule.
7. **tool ∈ `tool_whitelist`** — every tool referenced by a `tool-call` node (its `params["tool"]`)
   must be present in `recipe.agent_config.tool_whitelist`; a tool outside the whitelist is
   rejected.

D11: original 4-rule body (1, 2, 5, 7 above). D12 (kit#87, request from AIE-1 — see issue
thread): added rules 3, 4, 6, closing the gap `interpreter.py`'s own structural defenses had
been covering ad hoc. Order matters — node-type validity and edge-resolvability are checked
first (cheap, and rule 6's walk below must never guess at a dangling `edge.to` or an
unrecognized type), then start-node uniqueness and the outgoing-edge cap (both needed before a
deterministic walk is even possible), then the cycle walk, then the end-node-termination walk
(needs the graph already known acyclic and single-successor), then the tool-whitelist check
last (cheapest, and only meaningful once the graph shape above is already known-good).
"""

from __future__ import annotations

from studio_contracts import NodeType, Recipe


def graph_lint(recipe: Recipe) -> None:
    """Validate `recipe`'s DAG against the 7 rules documented above.

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
                f"graph_lint: node {node.id!r} has type {node.type!r}, not one of the 6 closed NodeType values"
            ) from exc

    # Rule 2 — every edge must resolve to a real node id on both ends. Checked before the
    # start-node/outgoing-edge/cycle rules below so none of them ever has to special-case a
    # `to`/`from_` pointing at a node that doesn't exist.
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

    # Rule 3 — exactly 1 start node (no incoming edge). Mirrors
    # `studio_engine.interpreter._find_start_node_id`, moved upstream so a recipe with 0 or
    # >1 candidates never reaches the interpreter at all.
    edge_targets = {edge.to for edge in dag.edges}
    start_ids = [node.id for node in dag.nodes if node.id not in edge_targets]
    if len(start_ids) != 1:
        raise ValueError(
            f"graph_lint: recipe.dag must have exactly 1 start node (no incoming edge), "
            f"found {len(start_ids)}: {start_ids}"
        )
    start_id = start_ids[0]

    # Rule 4 — exactly 0 or 1 outgoing edge per node (temporary stub until
    # ConditionExecutor lands in AIE-1: see module docstring).
    next_by_id: dict[str, str] = {}
    for edge in dag.edges:
        if edge.from_ in next_by_id:
            raise ValueError(
                f"graph_lint: node {edge.from_!r} has >1 outgoing edge — condition "
                "branching is not evaluated yet (ConditionExecutor is unimplemented)"
            )
        next_by_id[edge.from_] = edge.to

    # Rule 5 — no forbidden cycle. Standard 3-color DFS: WHITE = unvisited, GRAY = on the
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
                raise ValueError(f"graph_lint: recipe.dag has a forbidden cycle involving node {neighbor!r}")
            if color[neighbor] == WHITE:
                _walk(neighbor)
        color[node_id] = BLACK

    # Iterate `dag.nodes` (list, declaration order), never `node_ids` (set): set iteration
    # order depends on PYTHONHASHSEED, which is randomized per-process by default, so which
    # node the walk starts from — and therefore which node a cycle gets reported against —
    # would otherwise vary run to run for the same input (found by AIE-2, 4 different names
    # across 12 seeds on the same cyclic DAG).
    for node in dag.nodes:
        if color[node.id] == WHITE:
            _walk(node.id)

    # Rule 6 — the walk must terminate ON an `end` node, not merely run out of edges.
    # Safe to walk as a simple chain here: rules 3+4 already guarantee exactly 1 start node
    # and <= 1 outgoing edge per node, and rule 5 already guarantees no cycle, so `next_by_id`
    # (built during rule 4) has exactly one deterministic path from `start_id`.
    nodes_by_id = {node.id: node for node in dag.nodes}
    walk_id = start_id
    while True:
        if nodes_by_id[walk_id].type == NodeType.END:
            break
        next_id = next_by_id.get(walk_id)
        if next_id is None:
            raise ValueError(
                f"graph_lint: recipe.dag walk ended at node {walk_id!r} (no outgoing edge) "
                "without reaching an `end` node"
            )
        walk_id = next_id

    # Rule 7 — every `tool-call` node's tool must be in agent_config.tool_whitelist.
    whitelist = set(recipe.agent_config.tool_whitelist)
    for node in dag.nodes:
        if node.type == NodeType.TOOL_CALL:
            tool = node.params.get("tool")
            if tool not in whitelist:
                raise ValueError(
                    f"graph_lint: node {node.id!r} uses tool {tool!r}, "
                    f"not in agent_config.tool_whitelist {sorted(whitelist)!r}"
                )
