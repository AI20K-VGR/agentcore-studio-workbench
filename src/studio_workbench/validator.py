"""Recipe validator / graph-lint seam (R-SPEC A1#1 :36) — bút SWE, spec-only this phase (OJT
implementation slot).

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

This module ships as a spec stub this phase: `graph_lint()` unconditionally raises
`NotImplementedError` — the real 4-rule body is left for the SWE OJT candidate to implement.
`packages/workbench/tests/test_graph_lint.py` pins both the current stub behavior and the 4
rule-specific rejections the real body must produce (xfail, red-by-design until implemented).
"""

from __future__ import annotations

from studio_contracts import Recipe


def graph_lint(recipe: Recipe) -> None:
    """Validate `recipe`'s DAG against the 4 rules documented above.

    Raises on any violation (never returns a boolean/error-list — a recipe either passes
    cleanly or it does not reach the interpreter at all). Returns `None` on success.

    P7 stub: SWE OJT fills in the real 4-rule body. Deliberately unimplemented so
    `test_graph_lint.py` stays red-by-design until then.
    """
    raise NotImplementedError("graph_lint: SWE OJT fills in the 4-rule DAG validator (R-SPEC A1#1)")
