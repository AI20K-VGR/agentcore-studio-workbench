---
id: studio.contract.recipe.v0
type: interface-draft
status: freeze-ready
freeze: FREEZE-READY   # chờ Q-1 (nơi freeze) + 4/4 chữ ký — workshop #84, D11
freeze_target: D11
contract_ref: umbrella-contract §3.1
pen: SWE — Thiệu Quang Minh
date: 2026-08-03
updated: 2026-08-03
---

# 🖊️ recipe — INTERFACE (FREEZE-READY D11)

> ## 🧊 FREEZE-READY (03/08, D11) — hình dạng đã khớp `contracts` từ trước; freeze = khoá GRAPH-LINT.
> Chữ ký `Recipe` (`agent_id · tenant_id: UUID · agent_config · dag · kb_binding · golden_set_ref ·
> scorecard_threshold`) đã khớp `studio_contracts.recipe.Recipe` từ D-13 — không đổi field/kiểu nào
> hôm nay. Việc D11 là khoá **graph-lint** (4 luật DAG-validator, bút SWE đồng thời) — trước đây là
> spec-stub, nay đã có thân hàm thật.
> **Hai cổng còn chờ người:** **Q-1** (nơi bản `FROZEN` đổ vào — xem issue kit#84) + **4/4 chữ ký**.
> Đổi sau freeze = mini-RFC + 4/4 chữ ký + decision-log.

---

## 1. Chữ ký v0 — trùng bản freeze §3.1

```python
class Recipe(BaseModel):
    agent_id: str
    tenant_id: UUID  # D-13 — immutable tenant id, không phải slug
    agent_config: AgentConfig  # {instructions, model, tool_whitelist}
    dag: Dag  # {nodes: [Node{id,type∈6,params}], edges: [Edge{from,to,when?}]}
    kb_binding: KbBinding  # {kb_id, scope}
    golden_set_ref: str
    scorecard_threshold: ScorecardThreshold  # {success, citation_accuracy}
```

Không có gì để "nâng" — bản v0 và bản freeze §3.1 đã là cùng 1 chữ ký từ khi `tenant_id: UUID` được
áp dụng (D-13). Kiểm chứng: `packages/workbench/src/studio_workbench/builder.py` (4 hàm dựng Recipe,
D3/D4/D6) đều dùng đúng shape này, `test_recipe_roundtrip.py` xanh.

---

## 2. Graph-lint — 4 luật, đã có thân hàm thật (D11)

`graph_lint(recipe) -> None` (`src/studio_workbench/validator.py`) là cổng bắt buộc trước khi 1
recipe được phép tới interpreter (AIE-1) — *"recipe không qua validator = không interpret"*
(umbrella §3.1). Trước D11 là spec-stub (`NotImplementedError`); nay có thân hàm thật, 4 luật:

1. **node ∈ 6 `NodeType` đóng** — defense-in-depth: Pydantic đã chặn ở tầng construct bình thường
   (`Node.type: NodeType`), luật này bắt thêm trường hợp recipe tới hàm qua đường vòng
   (`model_construct`, hoặc đọc lại từ `wb.recipes.recipe` jsonb sau 1 lần đổi contract tương lai).
2. **không có chu trình cấm** — DFS 3 màu (WHITE/GRAY/BLACK); chạm lại 1 node đang GRAY = cycle.
3. **mọi edge phải trỏ tới node có thật** — kiểm cả `edge.from_` lẫn `edge.to` tồn tại trong
   `dag.nodes`, tránh interpreter đi vào 1 walk không xác định.
4. **tool trong `tool-call` phải nằm trong `agent_config.tool_whitelist`**.

Thứ tự kiểm cố ý: luật 1 (node type) → luật 3 (edge destination) → luật 2 (cycle) → luật 4
(tool-whitelist). Luật 3 đứng trước luật 2 để vòng DFS không bao giờ phải đoán khi gặp
`edge.to`/`edge.from_` trỏ tới node không tồn tại — dồn hết việc "recipe có tồn tại đủ node không"
về 1 chỗ trước khi đi bộ đồ thị.

Kiểm chứng: `tests/test_graph_lint.py` — `test_graph_lint_accepts_valid_recipe` (recipe hợp lệ lọt
qua sạch) + `test_lint_rejects_bad_graph` (cả 4 vi phạm đều bị chặn đúng luật, đúng message) — cả 2
**PASS**, không còn `xfail`.

---

## 3. `kb_binding` — có trong contract, chưa được engine đọc (ghi rõ để không ai tưởng đã wiring)

`Recipe.kb_binding.scope` mô tả phạm vi KB (tenant/section) theo khai báo của recipe, nhưng
`studio_engine.interpreter.run()` hiện lấy `tenant_id` từ `session_context` (server-resolved, INV-1),
KHÔNG đọc `recipe.kb_binding` để suy tenant hay section_roles — đúng chủ đích (client-declared field
không được tin cho mục đích an ninh). `kb_binding` có tác dụng khai báo/hiển thị ở tầng Workbench UI
hiện tại; wiring "kb_binding.scope quyết fence" là việc của S3 (chunk-level fence), chưa phải S1/S2.
Ghi ở đây để tránh hiểu nhầm field này đã ảnh hưởng hành vi runtime.

---

## 4. Câu hỏi còn mở

| # | Hỏi ai | Nội dung | Trạng thái |
|---|---|---|---|
| Q-1 | mentor / leader | Bản `FROZEN` nằm ở draft riêng từng repo (lật cờ) hay PR bump `SCHEMA_VERSION` ở `contracts`? | 🔴 đã hỏi ở issue [kit#84](https://github.com/AI20K-VGR/agentcore-studio-kit/issues/84), chờ trả lời — áp dụng chung 4 hợp đồng, không riêng recipe |
| Q-2 | mentor / leader | Decision-log chung + hình thức 4 chữ ký | 🔴 đã hỏi ở issue kit#84, chờ trả lời |
| ~~Q-4~~ | ~~DE~~ | ~~`recipe.dag`'s node_type có khớp đúng 6 `NodeType` (dùng chung module với `trace.py`) không?~~ | ✅ **đóng** — xác nhận tại [kb#10 comment](https://github.com/AI20K-VGR/agentcore-studio-kb/pull/10#issuecomment-5162808694): cùng import `studio_contracts.nodes.NodeType`, Pydantic chặn ở tầng kiểu, không phụ thuộc `graph_lint()` |
| Q-Publish | AIE-2 | `publish(recipe, scorecard)` đọc `scorecard.gate.verdict` — SWE chỉ wire, không tự tính lại verdict. Cần AIE-2 xác nhận `Scorecard` thật (không phải `SmokeResult`) sẽ tới từ đâu khi `EvalHarness.run()` xong | 🟡 chờ AIE-2 (liên quan PR [contracts#1](https://github.com/AI20K-VGR/agentcore-studio-contracts/pull/1)) |

---

## 5. Lịch sử

| Bản | Ngày | Đổi gì |
|---|---|---|
| v0 (ngầm định, chưa có file riêng) | 2026-07-21 → 2026-08-02 | Chữ ký sống trong `packages/contracts/src/studio_contracts/recipe.py`, dùng qua `builder.py` D3/D4/D6. Chưa có file mô tả riêng như `kb-search.v0.md`/`trace-event.v0.md`. |
| **freeze-ready** | 2026-08-03 (D11, #82) | Tạo file mô tả này. Graph-lint 4 luật code thật (trước là stub) + test xanh. Không đổi field/kiểu nào trong `Recipe`. Đóng Q-4 (đã xác nhận với DE). Mở Q-1/Q-2 (đã hỏi chung ở kit#84), Q-Publish (chờ AIE-2). `FROZEN` + 4/4 chữ ký chưa đóng — chờ ceremony + Q-1. |
