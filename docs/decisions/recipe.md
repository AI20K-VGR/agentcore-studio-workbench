---
id: studio.decision-log.recipe
type: decision-log
contract: recipe
pen: SWE — Thiệu Quang Minh
freeze: FREEZE-READY   # chưa FROZEN — xem điều kiện còn thiếu bên dưới
---

# Decision-log — recipe (SWE)

## D11 · 2026-08-03

| # | Quyết định | Lý do | PR / bằng chứng | Trạng thái |
|---|---|---|---|---|
| DL-R1 | `graph_lint()` implement thân hàm thật, 4 luật (node-type ∈ 6 đóng, edge-destination resolvable, no cycle, tool ∈ whitelist), thứ tự kiểm: node-type → edge-destination → cycle → tool-whitelist | Trước là spec-stub `NotImplementedError`; thứ tự cố ý để DFS tìm cycle không phải đoán xử lý dangling edge | [workbench#12](https://github.com/AI20K-VGR/agentcore-studio-workbench/pull/12) | 🟡 chờ review |
| DL-R2 | Q-4 (recipe.dag's node_type = đúng 6 `NodeType`, DE hỏi ở kb#10) — đóng | `recipe.py` và `trace.py` dùng chung `studio_contracts.nodes.NodeType`; Pydantic chặn ở tầng kiểu | [kb#10 comment](https://github.com/AI20K-VGR/agentcore-studio-kb/pull/10#issuecomment-5162808694) | ✅ đóng |
| DL-R3 | Shape `Recipe` (agent_id/tenant_id/agent_config/dag/kb_binding/golden_set_ref/scorecard_threshold) — không đổi field/kiểu nào hôm nay | Đã khớp `studio_contracts.recipe.Recipe` từ D-13, xác nhận qua `builder.py` D3/D4/D6 + `test_recipe_roundtrip.py` | [`recipe.v0.md`](https://github.com/AI20K-VGR/agentcore-studio-workbench/blob/day11/recipe-freeze-ready/docs/contracts/recipe.v0.md) (PR #12, chưa merge `main`) | ✅ đóng |

## D18 · 2026-08-12 — kit#117, `publish()`/`rollback()` thân hàm thật

| # | Quyết định | Lý do | PR / bằng chứng | Trạng thái |
|---|---|---|---|---|
| DL-R4 | Q5 (`docs/test-design/GUIDE-B-recipe.md` §10) — `publish`/`rollback` nhận `conn: DbConnection` (Protocol mới, đặt trong `studio_workbench/protocols.py`, **không** đưa lên `studio_contracts`) thay vì tự mở connection hoặc nhận cả pool | `studio_workbench` không import được `studio_app` (`.importlinter`); nhận đúng 1 connection đã bind sẵn tenant khiến việc tự mở connection không-bind là bất khả thi về mặt cấu trúc (B-P01). Không đưa Protocol lên `studio_contracts`: chỉ 1 consumer (`publish()`/`rollback()`) + 1 producer (`apps/studio`, đã được phép import `studio_workbench`) — cùng lý do AIE-2 đã tự rút lại việc promote `AgentRunner` ([`MRFC-2026-08-03-agentrunner-protocol-seam.md`](https://github.com/AI20K-VGR/agentcore-studio-evalhub/blob/main/docs/mini-rfc/MRFC-2026-08-03-agentrunner-protocol-seam.md) §4) — nên **không cần mini-RFC** | `packages/workbench` branch `swe/day18-publish-rollback` | 🟡 chờ review |
| DL-R5 | Q7 — bật RLS (`ENABLE`+`FORCE ROW LEVEL SECURITY` + policy) cho `wb.recipes`/`wb.recipe_versions`, mẫu `kb_chunks_tenant_isolation` | 2 bảng chứa IP tenant (`agent_config.instructions`, `kb_binding.scope`) với đường ghi/đọc thật lần đầu qua `publish()`/`rollback()` | Ký phần B ở [`packages/kb/docs/mini-rfc-tenant-schema-unify.md`](https://github.com/AI20K-VGR/agentcore-studio-kb/blob/main/docs/mini-rfc-tenant-schema-unify.md) (2026-08-12) + implement cùng branch trên | 🟡 chờ review |
| DL-R6 | `Scorecard.recipe_hash is None` → `publish()` fail-closed (refuse), không tự nới lỏng | Đúng docstring `recipe_hash` (`scorecard.py:216-220`): "cannot verify which recipe this certifies ⇒ REFUSE". Every real `Scorecard` mang `None` tới khi AIE-2 wire producer (`DEC-03`) — `publish()` sẽ luôn refuse tới lúc đó, đây là hành vi đúng, không phải bug | `packages/workbench` branch `swe/day18-publish-rollback` | 🟢 implement xong |

## D24 · 2026-08-24 — kit#206, luật 4 `graph_lint` giữ chặn fan-out (Hub-and-Spoke)

| # | Quyết định | Lý do | PR / bằng chứng | Trạng thái |
|---|---|---|---|---|
| ADR-D24-01 | Luật 4 `graph_lint` **giữ chặn fan-out**. Hub-and-Spoke ở canvas là bố trí hình học; DAG xuất ra vẫn tuyến tính | Kiến trúc 1-LLM-N-tool (`engine#36`) **không** biểu diễn tool bằng cạnh DAG — LLM tự chọn tool lúc chạy qua `TOOL_CALL:`, danh sách đến từ whitelist/registry. Fan-out edge vì vậy là **sai cơ chế**, không phải "đúng nhưng chưa tới lúc". Nới luật 4 mà `_build_next_map` còn last-write-wins ⇒ recipe qua `graph_lint` rồi bị interpreter **nuốt im lặng** mọi `tool-call` trừ cái khai báo cuối: người dùng gắn 3 tool, hệ thống báo chạy thành công, 2 tool không có trong trace | repro `kit#206` (validator PR#33 + engine `main`): `graph_lint` PASS · walk `['n1','n2','t3','end']` · tool-call **bị nuốt** `['t1','t2']` · đường đi thật `routes/runs.py:122` | ✅ quyết — AIE-1 (Trần Bá Đạt) xác nhận `24/08 03:16Z`. 🟡 **điều kiện lật** cần đủ 3: interpreter duyệt nhiều nhánh · có luật gộp state · trace phản ánh nhánh song song. Nới vẫn cần tín hiệu AIE-1 bằng chữ |

## D25 · 2026-08-25 — kit#217/DEC-2, `AgentConfig.instructions` → `system_prompt`

| # | Quyết định | Lý do | PR / bằng chứng | Trạng thái |
|---|---|---|---|---|
| DL-R7 | `AgentConfig.instructions` đổi tên thành `system_prompt` (breaking, `SCHEMA_VERSION` `0.2.0-draft`→`0.3.0-draft`, DEC-2 ở `docs/decisions.md` root kit); `build_agent_config`/`create_recipe` trong `recipe.py` đổi tên tham số theo | `instructions` không phản ánh đúng vai trò field (system prompt của agent). Rollout phối hợp cross-repo (kit#217): contracts trước, workbench/engine song song, rồi apps/studio, apps/web, cuối cùng bump 5 con trỏ `kit` cùng một commit | [contracts#14](https://github.com/AI20K-VGR/agentcore-studio-contracts/pull/14) (mở) | 🟡 chờ merge |

**Ghi chú `DL-R5`:** tên field `agent_config.instructions` trong lý do RLS ở D18 nay là `agent_config.system_prompt` — chỉ tên field đổi, lý do/bằng chứng RLS không đổi.

## Còn mở — chặn `FROZEN` thật sự

| # | Nội dung | Chờ ai |
|---|---|---|
| Q-1 | Cơ chế "freeze" (lật cờ tự do vs cần PR vào `contracts`) — đề xuất ở ADR-D11-01, chưa có đồng thuận | cả nhóm (hạn: hết ngày 03/08) |
| — | PR [workbench#12](https://github.com/AI20K-VGR/agentcore-studio-workbench/pull/12) chưa được review/merge | DE, AIE-1, AIE-2 |
| Q-Publish | `publish(recipe, scorecard)` cần `Scorecard` thật (không phải `SmokeResult`) — thân hàm đã nhận đúng `Scorecard` thật từ D18, nhưng pipeline sinh `Scorecard` thật (judge branch) của AIE-2 chưa xong | AIE-2 |
| Q4 (register §10) | "Đúng 1 live version" cho `(agent_id, tenant_id)` chưa được enforce ở tầng DB (partial unique index / advisory lock) — D18 chỉ enforce ở tầng application, best-effort | SWE, chưa có ETA |

**Chưa lật `freeze: FROZEN`** — điều kiện trên chưa đủ.
