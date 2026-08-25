"""`publish`/`rollback` spec tests (R-SPEC A4 :72, kit#117 D18) — real bodies replacing the
`NotImplementedError` stub.

Non-DB tests below drive `publish()`/`rollback()` against `FakeConn`, an in-memory double of
`wb.recipes`/`wb.recipe_versions` honoring the exact query shapes `publish.py` issues — they pin
the branch logic (agent_shape_lint/agent_topology_lint gate, `recipe_hash` fail-closed, `gate.verdict` gate + rollback,
version bookkeeping) independent of any real Postgres. The DB-backed tests at the bottom
(`test_publish_rls_*`) exercise the actual RLS policy from `schema.py` (`B-P01` in
`docs/test-design/GUIDE-B-recipe.md` §11) through the real `pool`/`admin_pool` fixtures
(root `conftest.py`) — they skip when `STUDIO_DATABASE_URL`/`STUDIO_DATABASE_URL_ADMIN` are unset,
same as every other DB test in this workspace.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

import pytest
from studio_contracts import (
    AgentConfig,
    Aggregate,
    CaseResult,
    Dag,
    Edge,
    Gate,
    GateThreshold,
    KbBinding,
    Node,
    NodeType,
    Recipe,
    Scorecard,
    ScorecardThreshold,
)

from studio_workbench.publish import publish, recipe_hash, rollback

ANKOR_ID = UUID("a0000000-0000-0000-0000-000000000001")
BOREA_ID = UUID("b0000000-0000-0000-0000-000000000001")


def _valid_recipe(*, agent_id: str = "agent-1", tenant_id: UUID = ANKOR_ID) -> Recipe:
    """app#44: star-shaped `dag` (1 `llm-step` hub + 1 `kb-retrieve` spoke directly edged to it) —
    was `kb-retrieve -> end` (no `llm-step` at all), the OLD DAG-walk shape `graph_lint` accepted;
    `publish()` now gates on `enforce_agent_topology` instead, which requires exactly this shape
    (see `validator.py` module docstring). `tool_whitelist` changed `["kb_search"]` ->
    `["calculator"]` for the same reason (`agent_shape_lint`'s `no_kb_search` rule)."""
    return Recipe(
        agent_id=agent_id,
        tenant_id=tenant_id,
        agent_config=AgentConfig(
            system_prompt="Answer from KB only.",
            model="gpt-4o-mini",
            tool_whitelist=["calculator"],
        ),
        dag=Dag(
            nodes=[
                Node(id="n1", type=NodeType.KB_RETRIEVE, params={}),
                Node(id="n2", type=NodeType.LLM_STEP, params={}),
            ],
            edges=[Edge(from_="n1", to="n2", when=None)],
        ),
        kb_binding=KbBinding(kb_id="kb-1", scope="ankor/public"),
        golden_set_ref="golden-set-1",
        scorecard_threshold=ScorecardThreshold(success=0.9, citation_accuracy=0.95),
    )


def _invalid_recipe() -> Recipe:
    """Fails `enforce_agent_topology` — a 2nd edge dangles to a node that doesn't exist, plain
    constructors, no `model_construct` back door needed. The valid `n1 -> n2` edge is kept so
    ONLY the dangling-edge rule (`dag.edges_are_llm_hub_spokes_only`) fails, not an earlier rule
    in `agent_topology_lint`'s fixed order (`enforce_agent_topology` raises on the FIRST `FAIL`)."""
    return _valid_recipe().model_copy(
        update={
            "dag": Dag(
                nodes=[
                    Node(id="n1", type=NodeType.KB_RETRIEVE, params={}),
                    Node(id="n2", type=NodeType.LLM_STEP, params={}),
                ],
                edges=[
                    Edge(from_="n1", to="n2", when=None),
                    Edge(from_="n2", to="does-not-exist", when=None),
                ],
            )
        }
    )


def _scorecard(*, verdict: Literal["PASS", "FAIL"], recipe_hash: str | None, agent_id: str = "agent-1") -> Scorecard:
    citation_accuracy = 1.0 if verdict == "PASS" else 0.0
    success_rate = 1.0 if verdict == "PASS" else 0.0
    return Scorecard(
        agent_id=agent_id,
        golden_set_ref="golden-set-1",
        results=[
            CaseResult(
                case_id="c1", expected="x", actual="x", success=verdict == "PASS", citation_accuracy=citation_accuracy
            )
        ],
        aggregate=Aggregate(success_rate=success_rate, citation_accuracy=citation_accuracy, n_scored_citation=1),
        gate=Gate(threshold=GateThreshold(success=0.9, citation_accuracy=0.95), verdict=verdict),
        recipe_hash=recipe_hash,
    )


@dataclass
class _Row:
    id: int
    agent_id: str
    tenant_id: UUID
    recipe: str
    version: int
    status: str
    created_at: int
    recipe_hash: str | None = None


@dataclass
class _ScorecardRow:
    tenant_id: UUID
    agent_id: str
    golden_set_ref: str
    results: str
    aggregate: str
    gate: str
    recipe_hash: str | None
    recipe_version: int | None


@dataclass
class FakeCursor:
    rows: list[tuple[Any, ...]] = field(default_factory=list)

    async def fetchone(self) -> tuple[Any, ...] | None:
        return self.rows[0] if self.rows else None

    async def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self.rows)


class FakeConn:
    """In-memory double of `wb.recipes` + `wb.recipe_versions`, matched to the exact query text
    `publish.py` issues. No RLS/tenant filtering here by design — this file's non-DB tests exist
    to pin BRANCH LOGIC (which query fires for which `verdict`/`recipe_hash` combination), not to
    prove the fence itself; the fence is `test_publish_rls_*` below, against a real Postgres."""

    def __init__(self) -> None:
        self.recipes: list[_Row] = []
        self.versions: list[_Row] = []
        self.scorecards: list[_ScorecardRow] = []
        self._next_id = 1
        self._clock = 0

    async def execute(self, query: str, params: Sequence[Any] | None = None) -> FakeCursor:
        p = tuple(params or ())
        q = " ".join(query.split())

        if q.startswith("SELECT COALESCE(MAX(version), 0) FROM wb.recipes"):
            agent_id, tenant_id = p
            versions = [r.version for r in self.recipes if r.agent_id == agent_id and r.tenant_id == tenant_id]
            return FakeCursor([(max(versions, default=0),)])

        if q.startswith("UPDATE wb.recipes SET status = 'draft'"):
            agent_id, tenant_id = p
            for r in self.recipes:
                if r.agent_id == agent_id and r.tenant_id == tenant_id and r.status == "published":
                    r.status = "draft"
            return FakeCursor()

        if q.startswith("INSERT INTO wb.recipes"):
            agent_id, tenant_id, recipe_json, version, recipe_hash = p
            self._clock += 1
            row = _Row(self._next_id, agent_id, tenant_id, recipe_json, version, "published", self._clock, recipe_hash)
            self.recipes.append(row)
            self._next_id += 1
            return FakeCursor([(row.id,)])

        if q.startswith("INSERT INTO wb.recipe_versions"):
            recipe_id, agent_id, tenant_id, recipe_json, version, recipe_hash = p
            self._clock += 1
            self.versions.append(
                _Row(recipe_id, agent_id, tenant_id, recipe_json, version, "published", self._clock, recipe_hash)
            )
            return FakeCursor()

        if q.startswith("INSERT INTO eval.scorecards"):
            tenant_id, agent_id, golden_set_ref, results, aggregate, gate, recipe_hash, recipe_version = p
            self.scorecards.append(
                _ScorecardRow(
                    tenant_id, agent_id, golden_set_ref, results, aggregate, gate, recipe_hash, recipe_version
                )
            )
            return FakeCursor()

        if q.startswith("SELECT recipe, recipe_hash FROM wb.recipe_versions"):
            agent_id, tenant_id, version = p
            candidates = [
                v for v in self.versions if v.agent_id == agent_id and v.tenant_id == tenant_id and v.version == version
            ]
            history_matches = sorted(candidates, key=lambda v: v.created_at, reverse=True)
            return FakeCursor([(history_matches[0].recipe, history_matches[0].recipe_hash)] if history_matches else [])

        if q.startswith("UPDATE wb.recipes SET status = 'rolled_back'"):
            agent_id, tenant_id = p
            for r in self.recipes:
                if r.agent_id == agent_id and r.tenant_id == tenant_id and r.status == "published":
                    r.status = "rolled_back"
            return FakeCursor()

        if q.startswith("SELECT id FROM wb.recipes"):
            agent_id, tenant_id, version = p
            id_matches = [
                r for r in self.recipes if r.agent_id == agent_id and r.tenant_id == tenant_id and r.version == version
            ]
            return FakeCursor([(id_matches[0].id,)] if id_matches else [])

        if q.startswith("UPDATE wb.recipes SET status = 'published'"):
            (row_id,) = p
            for r in self.recipes:
                if r.id == row_id:
                    r.status = "published"
            return FakeCursor()

        if q.startswith("SELECT version FROM wb.recipes"):
            agent_id, tenant_id = p
            published = [
                r.version
                for r in self.recipes
                if r.agent_id == agent_id and r.tenant_id == tenant_id and r.status == "published"
            ]
            published_versions = sorted(published, reverse=True)
            return FakeCursor([(published_versions[0],)] if published_versions else [])

        raise AssertionError(f"FakeConn: unrecognized query: {q!r}")


# ---------------------------------------------------------------------------
# `recipe_hash` — DEC-03 producer


def test_recipe_hash_is_deterministic_for_equal_content() -> None:
    """Hai `Recipe` object dựng độc lập từ CÙNG dữ liệu phải ra CÙNG hash — nền tảng của mọi thứ
    khác trong file này: nếu tính chất này sai, `recipe_hash` vô dụng ngay từ định nghĩa."""
    assert recipe_hash(_valid_recipe()) == recipe_hash(_valid_recipe())


def test_recipe_hash_is_deterministic_regardless_of_params_key_order() -> None:
    """KHÓA lý do `sort_keys=True` bắt buộc: `Node.params: dict[str, object]` là dict tự do
    (`recipe.py`), JSON serialize theo thứ tự CHÈN, không sort — dùng `params={}` cho mọi node
    (như `_valid_recipe()`) không thể phát hiện bug này. Ở đây dựng 2 recipe nội dung giống hệt
    nhau (cùng key/value cho node `kb-retrieve`) nhưng `params` chèn theo 2 thứ tự khác nhau —
    trước bản vá `sort_keys=True`, 2 recipe này ra 2 hash KHÁC nhau dù cùng nội dung."""
    forward = _valid_recipe().model_copy(
        update={
            "dag": Dag(
                nodes=[
                    Node(id="n1", type=NodeType.KB_RETRIEVE, params={"kb_id": "x", "top_k": 5}),
                    Node(id="n2", type=NodeType.END, params={}),
                ],
                edges=[Edge(from_="n1", to="n2", when=None)],
            )
        }
    )
    reversed_order = _valid_recipe().model_copy(
        update={
            "dag": Dag(
                nodes=[
                    Node(id="n1", type=NodeType.KB_RETRIEVE, params={"top_k": 5, "kb_id": "x"}),
                    Node(id="n2", type=NodeType.END, params={}),
                ],
                edges=[Edge(from_="n1", to="n2", when=None)],
            )
        }
    )
    assert forward.dag.nodes[0].params == reversed_order.dag.nodes[0].params  # same content
    assert recipe_hash(forward) == recipe_hash(reversed_order)


def test_recipe_hash_changes_when_content_changes() -> None:
    """Đối chứng bài trên — đổi 1 field bất kỳ (ở đây: `system_prompt`) phải đổi hash. Không đổi
    thì hash không đo được gì, cùng lớp lỗi `M-G` mutation-kill mà evalhub đã pin cho `compute.py`."""
    base = _valid_recipe()
    changed = base.model_copy(
        update={"agent_config": base.agent_config.model_copy(update={"system_prompt": "khác hẳn."})}
    )
    assert recipe_hash(base) != recipe_hash(changed)


def test_recipe_hash_is_alias_invariant() -> None:
    """KHÓA đúng lý do `by_alias=True` là bắt buộc, nêu ở docstring module: `Edge.from_` mang
    `Field(alias="from")`, nên `model_dump_json()` (không alias) và `model_dump_json(by_alias=
    True)` ra HAI chuỗi byte khác nhau cho CÙNG một recipe. Test này tự lấy `model_dump_json()`
    KHÔNG alias làm oracle độc lập với hàm đang test, để không vô tình chỉ so `recipe_hash` với
    chính nó."""
    recipe = _valid_recipe()
    no_alias_hash = hashlib.sha256(recipe.model_dump_json().encode("utf-8")).hexdigest()
    assert recipe_hash(recipe) != no_alias_hash


async def test_publish_succeeds_end_to_end_with_real_recipe_hash() -> None:
    """Đối chứng cuối — thay vì fake string `"h1"` như mọi test khác trong file này, dùng ĐÚNG
    `recipe_hash()` sản xuất thật, gọi `publish()` cho MỘT recipe. Trước bản vá DEC-03 này, đường
    thật (`apps/studio/routes/publish.py` → `EvalHarness.run()`) không có cách nào tạo ra giá trị
    khác `None`, nên `publish()` LUÔN 409 bất kể `gate.verdict` — bài này khoá lại rằng với hash
    thật, đường publish giờ đi qua được, không còn refuse vô điều kiện."""
    conn = FakeConn()
    recipe = _valid_recipe()
    await publish(recipe, _scorecard(verdict="PASS", recipe_hash=recipe_hash(recipe)), conn)

    assert len(conn.recipes) == 1
    assert conn.recipes[0].status == "published"


# ---------------------------------------------------------------------------
# Non-DB: branch logic


async def test_publish_blocks_on_topology_lint_failure() -> None:
    """KHÓA: an invalid recipe never reaches the scorecard/DB checks at all —
    `enforce_agent_topology`'s `ValueError` propagates unchanged, and nothing is written."""
    conn = FakeConn()
    with pytest.raises(ValueError, match="edges_are_llm_hub_spokes_only"):
        await publish(_invalid_recipe(), _scorecard(verdict="PASS", recipe_hash="h1"), conn)
    assert conn.recipes == []
    assert conn.scorecards == []


async def test_publish_refuses_when_recipe_hash_is_none() -> None:
    """KHÓA (kit#117): `scorecard.recipe_hash is None` fail-closed — refuses even on an otherwise
    passing scorecard, per `Scorecard.recipe_hash`'s own docstring. Paired positive control:
    `test_publish_writes_new_version_on_pass` below is the same call with a real hash, and it
    succeeds."""
    conn = FakeConn()
    with pytest.raises(ValueError, match="recipe_hash"):
        await publish(_valid_recipe(), _scorecard(verdict="PASS", recipe_hash=None), conn)
    assert conn.recipes == []
    assert conn.scorecards == []


async def test_publish_refuses_when_recipe_hash_does_not_match_recipe() -> None:
    """KHÓA (review PR#27, dholmes0207): `publish()` phải đối chiếu `scorecard.recipe_hash` với
    `recipe_hash(recipe)` THẬT, không chỉ kiểm `is None`. Trước bản vá này, `publish(recipe=B,
    scorecard=chứng-nhận-A)` đi lọt — hàng lưu mang hash của A nhưng nội dung của B, một chứng
    nhận SAI. Dựng 2 recipe nội dung khác nhau thật (không chỉ khác object identity), lấy hash của
    A rồi publish B với hash đó — phải bị từ chối."""
    conn = FakeConn()
    recipe_a = _valid_recipe()
    recipe_b = _valid_recipe().model_copy(
        update={"agent_config": recipe_a.agent_config.model_copy(update={"system_prompt": "recipe B, khác hẳn."})}
    )
    assert recipe_hash(recipe_a) != recipe_hash(recipe_b)  # sanity: thật sự khác nội dung

    with pytest.raises(ValueError, match="recipe_hash"):
        await publish(recipe_b, _scorecard(verdict="PASS", recipe_hash=recipe_hash(recipe_a)), conn)
    assert conn.recipes == []
    assert conn.scorecards == []


async def test_publish_refuses_when_scorecard_agent_id_does_not_match_recipe() -> None:
    """KHÓA (review PR#28, dholmes0207): cổng hash chỉ ghim `recipe`; `scorecard.agent_id` sống
    trên một object KHÁC và không có gì trước đây buộc nó khớp `recipe.agent_id`. Không có cổng
    này, `publish()` sẽ ghi `wb.recipes` cho một agent và `eval.scorecards` cho một agent KHÁC
    trong CÙNG transaction — dò bằng đúng probe review nêu: `recipe.agent_id="agent-1"`,
    `scorecard.agent_id="agent-hoan-toan-khac"`. Phải bị từ chối, và không hàng nào được ghi ở cả
    hai bảng (paired với `test_publish_writes_new_version_on_pass` bên dưới — cùng lời gọi, agent_id
    khớp thì đi qua được)."""
    conn = FakeConn()
    recipe = _valid_recipe(agent_id="agent-1")
    mismatched_scorecard = _scorecard(verdict="PASS", recipe_hash=recipe_hash(recipe), agent_id="agent-hoan-toan-khac")

    with pytest.raises(ValueError, match="agent_id"):
        await publish(recipe, mismatched_scorecard, conn)
    assert conn.recipes == []
    assert conn.scorecards == []


async def test_publish_writes_new_version_on_pass() -> None:
    """KHÓA: paired positive control for the two refusal tests above — graph-lint-clean recipe +
    non-`None` `recipe_hash` + `verdict="PASS"` writes exactly one `wb.recipes` row (status
    `published`, version 1) and one matching `wb.recipe_versions` row.

    Review workbench#30 (TranBaDat2607, request-changes soft): also locks the exact fixed
    behavior — `publish()`'s `recipe_json = recipe.model_dump_json(by_alias=True)` (`publish.py`)
    must serialize `Edge.from_` under its wire alias `"from"`, not the Python field name `"from_"`.
    `recipe_hash()` already had `test_recipe_hash_is_alias_invariant` guarding this; the write path
    fixed here had no equivalent, so a future refactor could silently drop `by_alias=True` again
    and nothing would catch it until it reproduced the exact production bug (app#37)."""
    conn = FakeConn()
    recipe = _valid_recipe()
    await publish(recipe, _scorecard(verdict="PASS", recipe_hash=recipe_hash(recipe)), conn)

    assert len(conn.recipes) == 1
    assert conn.recipes[0].version == 1
    assert conn.recipes[0].status == "published"
    assert len(conn.versions) == 1
    assert conn.versions[0].version == 1

    stored_edges = json.loads(conn.recipes[0].recipe)["dag"]["edges"]
    assert stored_edges, "seed phải có cạnh, không thì assert dưới vô nghĩa"
    assert all("from" in e and "from_" not in e for e in stored_edges), (
        f"recipe_json phải ghi alias dây 'from', không phải tên field Python 'from_' — thấy {stored_edges}"
    )


async def test_publish_stores_recipe_hash_on_both_tables() -> None:
    """KHÓA: `scorecard.recipe_hash` được LƯU LẠI trên cả `wb.recipes` lẫn `wb.recipe_versions`,
    không chỉ dùng làm điều kiện gate rồi bỏ đi — nếu không, không có cách nào sau này trả lời
    "hàng đã publish này khớp hash nào" mà không tính lại từ đầu."""
    conn = FakeConn()
    recipe = _valid_recipe()
    expected_hash = recipe_hash(recipe)
    await publish(recipe, _scorecard(verdict="PASS", recipe_hash=expected_hash), conn)

    assert conn.recipes[0].recipe_hash == expected_hash
    assert conn.versions[0].recipe_hash == expected_hash


async def test_publish_writes_eval_scorecards_audit_row_on_pass() -> None:
    """KHÓA (`evalhub#28` mục 2): PASS phải ghi đúng 1 hàng `eval.scorecards` — mắt xích còn thiếu
    mà issue tự khai: trước bản vá, `Scorecard` chỉ sống trong 1 lần gọi HTTP rồi mất, không cách
    nào sau đó trả lời "scorecard nào đã chứng nhận version nào của agent này". Kiểm nội dung
    THẬT (parse lại JSON), không chỉ đếm số hàng — `results`/`aggregate`/`gate` phải khớp ĐÚNG
    scorecard đã truyền vào, không phải một payload rỗng/giả. `recipe_version` (evalhub#34) phải
    bằng ĐÚNG `next_version` vừa ghi vào `wb.recipes` — publish đầu tiên nên là 1."""
    conn = FakeConn()
    recipe = _valid_recipe()
    scorecard = _scorecard(verdict="PASS", recipe_hash=recipe_hash(recipe))
    await publish(recipe, scorecard, conn)

    assert len(conn.scorecards) == 1
    row = conn.scorecards[0]
    assert row.tenant_id == recipe.tenant_id
    assert row.agent_id == scorecard.agent_id
    assert row.golden_set_ref == scorecard.golden_set_ref
    assert row.recipe_hash == scorecard.recipe_hash
    assert row.recipe_version == conn.recipes[0].version == 1
    assert json.loads(row.results) == [r.model_dump(mode="json") for r in scorecard.results]
    assert json.loads(row.aggregate) == scorecard.aggregate.model_dump(mode="json")
    assert json.loads(row.gate) == scorecard.gate.model_dump(mode="json")


async def test_publish_second_pass_writes_second_eval_scorecards_row() -> None:
    """KHÓA: `eval.scorecards` là audit trail — MỘT hàng MỚI mỗi lần publish PASS, không phải
    upsert/ghi đè hàng cũ. Đối chứng trực tiếp `test_publish_second_pass_bumps_version_and_
    demotes_prior` (bumps version, demotes prior) ở phía `wb.recipes`: phía `eval.scorecards`
    không có khái niệm "demote", mỗi run là một chứng nhận độc lập, kể cả khi publish 2 lần liên
    tiếp cho CÙNG agent/tenant.

    KHÓA thêm (`evalhub#34`, review `workbench#28` mục 🟠2): publish 2 lần liên tiếp CÙNG một
    recipe (nội dung không đổi) cho ra CÙNG một `recipe_hash` ở cả 2 hàng — đúng ca mà review dùng
    để chứng minh "nối bằng hash là một-nhiều". `recipe_version` phải PHÂN BIỆT được hai hàng đó
    (1 và 2) dù hash giống hệt nhau — nếu không, câu hỏi "scorecard nào chứng nhận version nào"
    vẫn treo y như trước khi có cột này."""
    conn = FakeConn()
    recipe = _valid_recipe()
    await publish(recipe, _scorecard(verdict="PASS", recipe_hash=recipe_hash(recipe)), conn)
    await publish(recipe, _scorecard(verdict="PASS", recipe_hash=recipe_hash(recipe)), conn)

    assert len(conn.scorecards) == 2
    assert conn.scorecards[0].recipe_hash == conn.scorecards[1].recipe_hash  # cùng nội dung, cùng hash
    assert [row.recipe_version for row in conn.scorecards] == [1, 2]  # nhưng version phân biệt được


async def test_rollback_recreated_row_carries_forward_recipe_hash() -> None:
    """KHÓA: khi `rollback()` phải TỰ DỰNG LẠI hàng `wb.recipes` (đường "row đã mất" — xem nhánh
    `else` trong `rollback()`), nó phải mang theo ĐÚNG `recipe_hash` đã lưu trong lịch sử
    `wb.recipe_versions`, không được để `NULL` — đây là recipe CŨ được TÁI XÁC NHẬN, không phải
    recipe mới chưa qua gate."""
    conn = FakeConn()
    recipe = _valid_recipe()
    expected_hash = recipe_hash(recipe)
    await publish(recipe, _scorecard(verdict="PASS", recipe_hash=expected_hash), conn)
    conn.recipes.clear()  # mô phỏng hàng wb.recipes gốc đã mất — chỉ còn lịch sử wb.recipe_versions

    await rollback(recipe.agent_id, recipe.tenant_id, to_version=1, conn=conn)

    assert len(conn.recipes) == 1
    assert conn.recipes[0].recipe_hash == expected_hash


async def test_rollback_recreate_branch_refuses_when_history_recipe_hash_is_none() -> None:
    """KHÓA (silent-failure review): nhánh "hàng wb.recipes gốc đã mất, phải dựng lại" trong
    `rollback()` không được ÂM THẦM ghi `status='published'` với `recipe_hash=NULL` — đây là hàng
    published TRƯỚC KHI cột này tồn tại (DEC-03). Trước bản vá, `publish()` từ chối `recipe_hash
    is None` nhưng `rollback()` thì không hề kiểm tra gì, tạo ra một hàng 'published' trông như đã
    được xác minh mà chưa từng được xác minh. Cũng khoá luôn: hàng đang published trước đó KHÔNG bị
    demote khi rollback bị từ chối — không được để endpoint rơi vào trạng thái "không có gì
    published" chỉ vì một lần rollback không hợp lệ."""
    conn = FakeConn()
    recipe = _valid_recipe()
    await publish(recipe, _scorecard(verdict="PASS", recipe_hash=recipe_hash(recipe)), conn)  # seed v1 published
    # Mô phỏng hàng lịch sử v1 KHÔNG có recipe_hash (published trước DEC-03), rồi hàng wb.recipes
    # gốc của v1 bị mất — buộc rollback() phải đi vào nhánh "dựng lại".
    conn.versions[0].recipe_hash = None
    conn.recipes.clear()

    with pytest.raises(ValueError, match="recipe_hash"):
        await rollback(recipe.agent_id, recipe.tenant_id, to_version=1, conn=conn)
    assert conn.recipes == []  # không có hàng nào được tạo ra với recipe_hash=NULL


async def test_publish_second_pass_bumps_version_and_demotes_prior() -> None:
    """KHÓA: publishing twice for the same `(agent_id, tenant_id)` writes version 2 as the new
    `published` row and demotes version 1's row to `draft` — never two `published` rows for the
    same agent/tenant at once (best-effort; concurrent-publish enforcement is Q4, out of scope)."""
    conn = FakeConn()
    recipe = _valid_recipe()
    await publish(recipe, _scorecard(verdict="PASS", recipe_hash=recipe_hash(recipe)), conn)
    await publish(recipe, _scorecard(verdict="PASS", recipe_hash=recipe_hash(recipe)), conn)

    published = [r for r in conn.recipes if r.status == "published"]
    assert len(published) == 1
    assert published[0].version == 2
    v1 = next(r for r in conn.recipes if r.version == 1)
    assert v1.status == "draft"


async def test_publish_fail_verdict_blocks_and_reasserts_prior_published() -> None:
    """KHÓA: `gate.verdict="FAIL"` blocks the write (no new version appears) AND re-asserts
    whichever version was already `published` — proving `rollback()` fired, not merely that the
    write was skipped. Paired positive control: `test_publish_writes_new_version_on_pass` (same
    recipe, `verdict="PASS`) is not blocked."""
    conn = FakeConn()
    recipe = _valid_recipe()
    await publish(recipe, _scorecard(verdict="PASS", recipe_hash=recipe_hash(recipe)), conn)  # seed v1 published

    with pytest.raises(ValueError, match="FAIL"):
        await publish(recipe, _scorecard(verdict="FAIL", recipe_hash=recipe_hash(recipe)), conn)

    assert len(conn.recipes) == 1  # no v2 was ever written
    assert conn.recipes[0].version == 1
    assert conn.recipes[0].status == "published"  # re-asserted, not left as something else
    assert len(conn.scorecards) == 1  # only the seeding PASS wrote an audit row; the FAIL did not


async def test_publish_fail_verdict_with_nothing_ever_published_is_a_noop_block() -> None:
    """KHÓA: FAIL on the very first publish attempt (nothing `published` yet) still blocks, and
    the rollback helper is a no-op (nothing to roll back TO) rather than raising a second,
    confusing error."""
    conn = FakeConn()
    recipe = _valid_recipe()
    with pytest.raises(ValueError, match="FAIL"):
        await publish(recipe, _scorecard(verdict="FAIL", recipe_hash=recipe_hash(recipe)), conn)
    assert conn.recipes == []
    assert conn.scorecards == []


async def test_rollback_restores_by_content_not_just_version_number() -> None:
    """KHÓA: `wb.recipe_versions` has no `UNIQUE (agent_id, tenant_id, version)` — two rows CAN
    share a version number. `rollback` must pick the most recent `created_at`, and must recreate
    the target's `wb.recipes` row from `wb.recipe_versions` HISTORY (not merely flip a status)
    when that row is no longer present in `wb.recipes` itself."""
    conn = FakeConn()
    recipe_v1 = _valid_recipe()
    expected_hash = recipe_hash(recipe_v1)
    await publish(recipe_v1, _scorecard(verdict="PASS", recipe_hash=expected_hash), conn)
    await publish(recipe_v1, _scorecard(verdict="PASS", recipe_hash=expected_hash), conn)  # -> v2 published, v1 draft

    # Simulate v1's own wb.recipes row having been removed independently of its history entry.
    conn.recipes = [r for r in conn.recipes if r.version != 1]
    assert {r.version for r in conn.recipes} == {2}

    await rollback(recipe_v1.agent_id, recipe_v1.tenant_id, to_version=1, conn=conn)

    v1_after = next(r for r in conn.recipes if r.version == 1)
    v2_after = next(r for r in conn.recipes if r.version == 2)
    assert v1_after.status == "published"
    assert v2_after.status == "rolled_back"
    assert v1_after.recipe == conn.versions[0].recipe  # content restored from history, not fabricated


async def test_rollback_raises_when_no_history_row_matches() -> None:
    """KHÓA: rolling back to a version with no `wb.recipe_versions` row raises rather than
    silently doing nothing — a caller must not believe a rollback succeeded when it did not."""
    conn = FakeConn()
    with pytest.raises(ValueError, match="no wb.recipe_versions row"):
        await rollback("agent-1", ANKOR_ID, to_version=99, conn=conn)


# ---------------------------------------------------------------------------
# DB-backed: the actual RLS fence (skips without STUDIO_DATABASE_URL*)


async def _bind_tenant(conn: Any, tenant_id: UUID) -> None:
    await conn.execute("SELECT set_config('app.tenant_id', %s, true)", (str(tenant_id),))


async def test_publish_rls_blocks_cross_tenant_write(pool: Any) -> None:
    """KHÓA (B-P01 [2]): a `conn` bound to tenant Y (via `SET LOCAL app.tenant_id`) must not be
    able to publish an agent belonging to tenant X — the `WITH CHECK` half of the RLS policy on
    `wb.recipes` must reject the INSERT."""
    import psycopg

    recipe = _valid_recipe(agent_id="cross-tenant-agent", tenant_id=ANKOR_ID)
    scorecard = _scorecard(verdict="PASS", recipe_hash=recipe_hash(recipe), agent_id="cross-tenant-agent")

    with pytest.raises(psycopg.Error):
        async with pool.connection() as conn, conn.transaction():
            await _bind_tenant(conn, BOREA_ID)  # wrong tenant on purpose
            await publish(recipe, scorecard, conn)


async def test_publish_rls_allows_matching_tenant_write(pool: Any) -> None:
    """KHÓA (B-P01 [3], paired positive control for the test above): the same publish, with the
    connection bound to the MATCHING tenant, succeeds and the row is readable back through the
    same app pool (B-P01 [4] — never the admin pool, which would bypass the policy)."""
    recipe = _valid_recipe(agent_id="matching-tenant-agent", tenant_id=ANKOR_ID)
    scorecard = _scorecard(verdict="PASS", recipe_hash=recipe_hash(recipe), agent_id="matching-tenant-agent")

    async with pool.connection() as conn, conn.transaction():
        await _bind_tenant(conn, ANKOR_ID)
        await publish(recipe, scorecard, conn)

    async with pool.connection() as conn, conn.transaction():
        await _bind_tenant(conn, ANKOR_ID)
        cursor = await conn.execute(
            "SELECT status FROM wb.recipes WHERE agent_id = %s AND tenant_id = %s",
            ("matching-tenant-agent", ANKOR_ID),
        )
        row = await cursor.fetchone()

    assert row is not None
    assert row[0] == "published"


async def test_publish_writes_real_eval_scorecards_row_on_real_postgres(pool: Any) -> None:
    """KHÓA (`evalhub#28` mục 2), trên Postgres THẬT — không phải `FakeConn`. `eval.scorecards`
    là DDL của quadrant khác (`packages/evalhub/src/studio_evalhub/schema.py`, cột `recipe_hash`
    từ `evalhub#32`, cột `recipe_version` từ `evalhub#34`), dựng qua `admin_pool` fixture chung
    (root `conftest.py` gọi `ensure_all_schemas()` — chạy DDL của MỌI quadrant, không chỉ `wb.*`).
    Đọc lại đúng qua app pool (B-P01 [4] — không dùng admin pool, để chính RLS của `eval.scorecards`
    cũng phải cho qua), và so nội dung JSONB đọc ngược lại với scorecard gốc — không chỉ đếm hàng.

    Cột `agent_id` của `eval.scorecards` lấy từ `scorecard.agent_id` (không phải `recipe.agent_id`
    — hai trường tên trùng nhưng SỐNG trên hai object khác nhau; bảng này mirror đúng shape của
    `Scorecard`, không phải của `Recipe`). Từ review PR#28 (dholmes0207), `publish()` giờ ĐÒI HỎI
    hai trường này khớp nhau (fail-closed nếu lệch — xem `test_publish_refuses_when_scorecard_
    agent_id_does_not_match_recipe`); recipe và scorecard ở đây dùng chung một `agent_id` vì đó là
    điều kiện BẮT BUỘC để publish đi qua, không còn là lựa chọn tự do của bài test.

    `recipe_version` phải bằng ĐÚNG `version` vừa ghi trên hàng `wb.recipes` tương ứng — publish
    đầu tiên cho một agent/tenant mới nên là 1, đọc lại qua CHÍNH Postgres thật (không phải giá trị
    tính tay), để không chỉ pin đúng bằng con số trùng hợp."""
    recipe = _valid_recipe(agent_id="scorecards-audit-agent", tenant_id=ANKOR_ID)
    scorecard = _scorecard(verdict="PASS", recipe_hash=recipe_hash(recipe), agent_id="scorecards-audit-agent")

    async with pool.connection() as conn, conn.transaction():
        await _bind_tenant(conn, ANKOR_ID)
        await publish(recipe, scorecard, conn)

    async with pool.connection() as conn, conn.transaction():
        await _bind_tenant(conn, ANKOR_ID)
        cursor = await conn.execute(
            "SELECT agent_id, golden_set_ref, results, aggregate, gate, recipe_hash, recipe_version "
            "FROM eval.scorecards WHERE tenant_id = %s AND agent_id = %s",
            (ANKOR_ID, "scorecards-audit-agent"),
        )
        row = await cursor.fetchone()
        recipes_cursor = await conn.execute(
            "SELECT version FROM wb.recipes WHERE tenant_id = %s AND agent_id = %s",
            (ANKOR_ID, "scorecards-audit-agent"),
        )
        recipe_row = await recipes_cursor.fetchone()

    assert row is not None
    assert recipe_row is not None
    agent_id, golden_set_ref, results, aggregate, gate, recipe_hash_col, recipe_version_col = row
    assert agent_id == scorecard.agent_id
    assert golden_set_ref == scorecard.golden_set_ref
    assert recipe_hash_col == scorecard.recipe_hash
    assert recipe_version_col == recipe_row[0]
    assert results == [r.model_dump(mode="json") for r in scorecard.results]
    assert aggregate == scorecard.aggregate.model_dump(mode="json")
    assert gate == scorecard.gate.model_dump(mode="json")


async def test_publish_rls_blocks_cross_tenant_eval_scorecards_read(pool: Any) -> None:
    """KHÓA (B-P01 [2], phía `eval.scorecards`): `eval.scorecards` tự bật `FORCE ROW LEVEL
    SECURITY` (`schema.py`) — một `conn` bám tenant KHÁC không được thấy hàng vừa publish, dù
    hàng đó tồn tại thật trong bảng. Paired trong CHÍNH bài này (không tách bài riêng): đọc bằng
    tenant ĐÚNG trước để chứng minh hàng thật sự tồn tại và đọc được, rồi đọc lại CÙNG hàng đó
    bằng tenant SAI — nếu chỉ kiểm nhánh sai, một bài lỗi (vd. `agent_id` gõ sai) cũng cho kết quả
    `None` giống hệt, và sẽ không phân biệt được với RLS đang hoạt động đúng."""
    recipe = _valid_recipe(agent_id="scorecards-fence-agent", tenant_id=ANKOR_ID)
    scorecard = _scorecard(verdict="PASS", recipe_hash=recipe_hash(recipe), agent_id="scorecards-fence-agent")

    async with pool.connection() as conn, conn.transaction():
        await _bind_tenant(conn, ANKOR_ID)
        await publish(recipe, scorecard, conn)

    async with pool.connection() as conn, conn.transaction():
        await _bind_tenant(conn, ANKOR_ID)  # right tenant — positive control
        cursor = await conn.execute(
            "SELECT id FROM eval.scorecards WHERE agent_id = %s",
            ("scorecards-fence-agent",),
        )
        visible_to_owner = await cursor.fetchone()

    async with pool.connection() as conn, conn.transaction():
        await _bind_tenant(conn, BOREA_ID)  # wrong tenant on purpose
        cursor = await conn.execute(
            "SELECT id FROM eval.scorecards WHERE agent_id = %s",
            ("scorecards-fence-agent",),
        )
        visible_to_stranger = await cursor.fetchone()

    assert visible_to_owner is not None  # the row genuinely exists and is readable
    assert visible_to_stranger is None  # ...but RLS fences it off from the wrong tenant
