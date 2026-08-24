"""Post-construction `Recipe` operations — patching an ALREADY-BUILT recipe, as opposed to
`recipe.py` (which only ever constructs a fresh one from scratch). Single canonical home for
"inject/strip the per-turn `query` on every `kb-retrieve` node" — `apps/studio` currently carries
TWO independent, hand-written copies of this exact operation (`routes/chat.py::_with_query`,
`eval_adapter.py::_with_query`/`_map_kb_params`) that have quietly DRIFTED apart: chat's patches
EVERY `kb-retrieve` node in the DAG, eval_adapter's patches only the FIRST one. A recipe with 2+
`kb-retrieve` nodes (nothing in `validator.graph_lint`'s 7 rules forbids that — canvas lets an
admin wire up as many as they want) therefore behaves differently depending on whether it's reached
via chat or via eval/publish: exactly the kind of "the recipe that got SCORED isn't the recipe that
RUNS" gap `DEC-D20-07` closed on the harness side of the pipeline, reopened on the chat side by two
copies of the same idea disagreeing. This module is the fix for that drift, but the two `apps/studio`
duplicates are NOT wired to it yet — that's a companion PR (`apps/studio` imports `with_query`/
`without_query` from here and deletes its own two copies), out of scope for this PR. Until that
lands, `with_query`/`without_query` below have no caller in this repo.

Consolidated here (`studio_workbench`) rather than left in `apps_studio` because this is
`Recipe`-shape domain logic — the same category as `create_recipe`/`create_recipe_d4`
already owned by `recipe.py` in this package — not an HTTP-route concern. Picked the "patch EVERY
kb-retrieve node" semantics (chat.py's) as canonical: it is the one that already accounted for
arbitrary, admin-designed canvas DAGs (`eval_adapter.py`'s "first node only" only ever agreed with
it by coincidence, because `create_recipe_d4`'s fixed 4-node DAG happens to have exactly one
`kb-retrieve` node). **Once wired up, this is a real behavior change, not a pure refactor**: on the
real publish path (`create_recipe`, i.e. an admin-drawn canvas), a recipe with 2+
`kb-retrieve` nodes will start getting `query` injected into ALL of them instead of just the first
— `create_recipe_d4`-based golden-set scoring is unaffected (fixed single `kb-retrieve` node), so
this doesn't move today's golden-30 numbers, but it will change eval/publish behavior for any real
multi-`kb-retrieve` canvas once the companion PR flips the call site over."""

from __future__ import annotations

import copy
from collections.abc import Callable

from studio_contracts import NodeType, Recipe

_QUERY_KEY = "query"


def _map_kb_retrieve_params(recipe: Recipe, fn: Callable[[dict[str, object]], dict[str, object]]) -> Recipe:
    """Apply `fn` to `params` of EVERY `kb-retrieve` node in `recipe.dag.nodes`, return a copy.
    A DAG with zero `kb-retrieve` nodes is valid (`end`-only, `tool-call`-only) and returned
    unchanged — this never raises for that shape. Deep-copies `params` before handing it to `fn`:
    `params: dict[str, object]` may hold nested `dict`/`list` values, and `Recipe`/`Node` being
    `frozen=True` only blocks reassigning fields, it does not deep-freeze what those fields point
    to — a shallow `dict(node.params)` would still share any nested mutable value with the
    original recipe, silently defeating the "does not mutate `recipe`" guarantee `with_query`/
    `without_query` make below for a caller that mutates a nested structure in place."""
    new_nodes = [
        node.model_copy(update={"params": fn(copy.deepcopy(dict(node.params)))})
        if node.type is NodeType.KB_RETRIEVE
        else node
        for node in recipe.dag.nodes
    ]
    return recipe.model_copy(update={"dag": recipe.dag.model_copy(update={"nodes": new_nodes})})


def with_query(recipe: Recipe, query: str) -> Recipe:
    """Return a copy of `recipe` with `params["query"] = query` set on every `kb-retrieve` node.
    Does not mutate `recipe` (`Recipe` is `frozen=True`) — safe to call against a recipe that must
    stay stable across many calls (e.g. the base recipe of a golden-set run, or a stored published
    recipe)."""
    return _map_kb_retrieve_params(recipe, lambda params: {**params, _QUERY_KEY: query})


def without_query(recipe: Recipe) -> Recipe:
    """Return a copy of `recipe` with the `query` key REMOVED (not set to `""`) from every
    `kb-retrieve` node's params — the two serialize to different byte strings, and that byte
    string is what `publish.recipe_hash()` hashes. Used to derive the stable "base" recipe of an
    eval run (one recipe object reused across all golden-set cases, `query` injected per-case via
    `with_query` at the call site) — see `eval_adapter.py::EngineAgentRunner.certified_recipe`."""
    return _map_kb_retrieve_params(recipe, lambda params: {k: v for k, v in params.items() if k != _QUERY_KEY})
