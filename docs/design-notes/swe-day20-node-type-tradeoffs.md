---
id: studio.design-note.swe.day-20-node-type-tradeoffs
type: design-note
role: SWE — Thiệu Quang Minh
day: 20
date: 2026-08-14
status: draft (chờ mentor duyệt)
scope: 6 node-type (kb-retrieve · llm-step · tool-call · condition · hitl-pause · end) — đánh đổi kỹ thuật + số đo thật
supersedes: honest-TODO §7 của `docs/reports/gate-2/swe-Dozyboy.md` (agentcore-report#80) — mục "6 node-type + trade-off số"
length_target: ≤2 trang
---

# Design-note SWE (D20) — Đánh đổi kỹ thuật giữa 6 node-type, có số đo thật

> Neo: issue [`kit#127`](https://github.com/AI20K-VGR/agentcore-studio-kit/issues/127) (GATE-2, DoD "6 node-type + trade-off số"). `validator.py` (7 luật graph-lint) và `apps/web/src/recipe/contract.ts` (`NODE_SPECS`) đã khoá đúng 6 loại này từ D12/D14 — note này KHÔNG lặp lại code, chỉ trả lời câu "vì sao chọn node nào cho việc gì", có số thật đi kèm thay vì chỉ lý thuyết.

## 0. Nguồn số — đo thật, không bịa

Số ở bảng dưới lấy từ `apps/studio/scripts/e2e_smoke_eval.py` chạy thật hôm nay (D20) trên Postgres cô lập (`docker-compose.test.yml`, cổng 5433), SHA `workbench@0d9f15d` · `engine@bfa19cc` · `kb@cd32d8a`, 5 case `callisto-smoke-5-v0`. **Cảnh báo phạm vi**: đây là độ trễ đo trên 1 máy dev, 1 luồng, dữ liệu nhỏ (140 chunk) — **không phải benchmark production**, chỉ dùng để so sánh THỨ TỰ tương đối giữa các node-type trong cùng 1 lần đo, không dùng để ước lượng SLA thật.

Độ trễ mỗi node = hiệu 2 mốc thời gian `ts` liên tiếp trong trace (node này bắt đầu tới node kế bắt đầu):

| Case | `kb-retrieve` (µs) | `llm-step` (µs) | `tool-call` (µs) |
|---|---|---|---|
| SC-01 | 355 | 144 | 30 |
| SC-02 | 271 | 138 | 34 |
| SC-03 | 324 | 143 | 38 |
| SC-04 | 326 | 136 | 31 |
| SC-05 | 187 | 88 | 23 |
| **Trung bình** | **293** | **130** | **31** |

Token (`llm-step`, cột `tok(p/c)` trong log, `ExtractiveFakeLLM` — double đọc prompt thật, không phải model thật): trung bình **212 prompt / 57 completion** mỗi case.

## 1. Bảng đánh đổi — 6 node-type

| Node-type | Nguồn chi phí chính | Số đo được (D20, xem §0) | Khi nào dùng |
|---|---|---|---|
| `kb-retrieve` | Round-trip Postgres + pgvector cosine search, qua fence `tenant_id`+`section_role` (`postgres.py:75`) | **293µs trung bình**, 0 token — chậm nhất trong 3 node có đo được, vì là node duy nhất chạm mạng+DB | Cần tra cứu dữ liệu ngoài mà agent không "biết sẵn" — luôn đứng đầu DAG trong mọi recipe mẫu hiện có (`create_sample_recipe_d3`, DAG 6-node AIE-1) |
| `llm-step` | Token thật (prompt+completion) — nguồn cost chi phối một khi `cost_of` land ở `contracts` (hiện `_NO_COST=0.0`, xem `docs/reports/gate-2/swe-Dozyboy.md` §4) | **130µs trung bình** (fake), **212/57 token/case** — dominant cost driver dù chưa ra số tiền thật | Cần suy luận/tổng hợp/sinh câu trả lời từ context đã lấy |
| `tool-call` | Tuỳ tool tích hợp — hiện là stub, chưa gọi API ngoài thật nào | **31µs trung bình** (stub, gần free) — 0 token vì chưa có tool thật nào tốn LLM call | Cần hành động ngoài hệ thống (hiện chỉ whitelist `kb_search`, xem `validator.py` luật 4) — **honest gap**: số đo này KHÔNG đại diện cho tool thật (vd gọi API bên thứ 3 sẽ có độ trễ mạng riêng, chưa đo được vì chưa có tool nào khác `kb_search`) |
| `condition` | Thuần logic in-process, không I/O | **chưa đo riêng** — 5 recipe mẫu dùng để đo hôm nay đều không có node `condition` (DAG tuyến tính n1→n2→n3→n4). Theo code (`interpreter.py`, executor rẽ nhánh dựa `when` trên cạnh): không I/O nào, chi phí lý thuyết ~0, nhưng đây là suy luận từ đọc code, KHÔNG phải số đo — khác hẳn 3 dòng trên | Rẽ nhánh luồng theo kết quả node trước (vd route sang judge khi cần, xem `n_routed_to_judge` trong evidence-pack AIE-2) |
| `hitl-pause` | Độ trễ **không giới hạn trên** — chờ người thật bấm duyệt/từ chối | **chưa dùng trong bất kỳ demo spine nào tới D20** — 0 case golden hiện có dùng node này, nên 0 số đo thật. Đây là honest-TODO, không phải "đã có nhưng quên đo" | Cần con người xác nhận trước khi luồng đi tiếp (vd hành động rủi ro cao) — **chưa có ví dụ chạy thật trong repo tính tới D20** |
| `end` | 0 — điểm kết, không xử lý gì thêm | **0µs theo thiết kế** (node cuối, `walk_from_dag` dừng ở đây, `render_timeline` không đo gap sau nó) | Bắt buộc đúng 1 điểm kết mỗi DAG — luật graph-lint riêng canh việc "walk phải kết ở node end" (D14/kit#97, `check-lint-parity`) |

## 2. Đọc bảng — 2 điều rút ra, không phải hiển nhiên trước khi đo

1. **`kb-retrieve` chậm hơn `llm-step` (fake) trong môi trường đo hôm nay**, dù trực giác thường nghĩ "gọi LLM mới chậm". Lý do: `llm-step` ở đây là `ExtractiveFakeLLM` — đọc prompt in-process, không có network call thật tới Gemini. Với LLM thật (`GeminiProvider`, `STUDIO_USE_FAKE_PROVIDERS=false`), thứ tự này gần như chắc chắn đảo ngược — **honest caveat, không đo được cho tới khi có 1 lượt gọi Gemini thật** (cùng mục treo `#59` trong evidence-pack AIE-2).
2. **2/6 node-type (`condition`, `hitl-pause`) chưa có số đo thật nào tính tới D20** — không phải vì quên, mà vì chưa case golden nào trong `callisto-smoke-5-v0`/`callisto-golden-30-v1` đi qua chúng. Muốn có số thật, cần thêm ≥1 golden case dùng `condition` (DE/AIE-2 sở hữu golden-set) và ≥1 demo path dùng `hitl-pause` (chưa có chủ, tương tự finding `INV-1 roles` treo từ D12 trong evidence-pack AIE-2).

## 3. Honest-TODO

| Món | Chủ | Điều kiện lật |
|---|---|---|
| Số đo `condition`/`hitl-pause` | chưa có chủ | ≥1 golden case dùng `condition`; ≥1 demo path dùng `hitl-pause` |
| Thứ tự `kb-retrieve` vs `llm-step` có đảo khi dùng LLM thật không | SWE + AIE-1 | 1 lượt `GeminiProvider` thật (`STUDIO_USE_FAKE_PROVIDERS=false`), so lại §0 |
| `tool-call` chỉ đo được với `kb_search` — chưa có tool thứ 2 nào để so sánh | chưa có chủ | thêm ≥1 tool ngoài `kb_search` vào whitelist + đo lại |
