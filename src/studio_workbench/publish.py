"""Publish / rollback flow seam (R-SPEC A4 :72) — bút SWE, spec-only this phase (OJT
implementation slot).

`publish(recipe, scorecard)` MUST wire 2 things, in this order:

1. run `studio_workbench.validator.graph_lint(recipe)` first — a recipe that fails graph-lint is
   never published (R-SPEC A1#1: "recipe không qua validator = không interpret" applies to
   Publish too, not only the interpreter);
2. read `scorecard.gate.verdict` (`studio_contracts.Scorecard`, owned/rendered by AIE-2) —
   `verdict == "FAIL"` is a HARD gate (INV-6), never advisory-only: Publish is blocked and the
   PREVIOUSLY published version is rolled back automatically (via `rollback()` below). SWE only
   WIRES this gate — reading `gate.verdict` and branching on it — it does NOT own computing the
   Scorecard's `results`/`aggregate`, nor the judge/eval-harness that produces them (AIE-2 owns
   rendering the scorecard itself; R-SPEC A4 :72). A SWE implementation that re-derives or
   second-guesses the verdict (instead of reading it as given) recreates the exact ownership
   overlap this boundary exists to prevent.

Only after both checks pass does `publish()` write the new version into `wb.recipes` +
`wb.recipe_versions` (this phase's DDL, `schema.py`) and flip the named endpoint to serve it.

`rollback(agent_id, tenant, to_version=...)` restores the named endpoint to a prior
`wb.recipe_versions` row — the version history `schema.py`'s DDL exists to make possible.

This module ships as a spec stub this phase: both functions unconditionally raise
`NotImplementedError`. The SWE OJT candidate fills in the real bodies later; this module only
specifies the wiring contract (which seam calls which, in what order, on what verdict).
"""

from __future__ import annotations

from studio_contracts import Recipe, Scorecard


def publish(recipe: Recipe, scorecard: Scorecard) -> None:
    """Validate `recipe` (via `graph_lint`) and gate-check it against `scorecard.gate.verdict`,
    then publish it to a named endpoint. `verdict == "FAIL"` blocks publish and triggers an
    automatic `rollback()` to the previously published version.

    P7 stub: SWE OJT fills in the real body (graph_lint -> verdict check -> write
    wb.recipes/recipe_versions -> flip endpoint). Deliberately unimplemented.
    """
    raise NotImplementedError("publish: SWE OJT fills in the graph_lint + verdict-gated publish flow (R-SPEC A4)")


def rollback(agent_id: str, tenant: str, *, to_version: int) -> None:
    """Roll the named endpoint for `(agent_id, tenant)` back to `to_version`, read from
    `wb.recipe_versions` history.

    P7 stub: SWE OJT fills in the real body. Deliberately unimplemented.
    """
    raise NotImplementedError("rollback: SWE OJT fills in the recipe_versions rollback body (R-SPEC A4)")
