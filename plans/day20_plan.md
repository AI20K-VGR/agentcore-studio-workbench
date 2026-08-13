---
day: 20
gate: gate-2
role: swe
author: Dozyboy
---

# Day 20 (GATE-2) — plan SWE

Theo issue [kit#127](https://github.com/AI20K-VGR/agentcore-studio-kit/issues/127):

## Xong ngày (DoD, nguyên văn issue)

- [ ] Demo spine 4 bước chạy thật
- [ ] AC executable xanh (canvas · KB thật retrieve + T1/T6 · trace viewer + cost cùng-1-số · eval
      v1 verdict · 6 node-type + trade-off số)
- [ ] plan-vs-actual đối chiếu
- [ ] review ≤2 vòng

## Việc dự định làm, theo thứ tự phụ thuộc

1. **Đối chiếu `graph_lint()` (workbench) với DAG 6-node của AIE-1** (`engine#25`,
   `test_dag_6node_spine.py`) — xác nhận 7 luật hiện tại của `validator.py` chấp nhận đúng shape
   AIE-1 vừa chứng minh chạy được (đủ 6 loại node: `kb-retrieve`, `llm-step`, `condition`,
   `tool-call`, `hitl-pause`, `end`). AIE-1 đã chủ động xin review shape-compatibility ở PR#25 —
   đây là điều kiện tiên quyết cho hạng mục "6 node-type" trong DoD.

   Đo bằng `scripts/check_graph_lint_vs_aie1_dag6node.py` (chạy tay, không nằm trong `testpaths`,
   không có job CI nào gọi nó — **ảnh chụp MỘT LẦN tại thời điểm chạy**, không phải thứ được canh
   liên tục qua mọi commit sau này của engine hay workbench. Nếu `graph_lint()` hoặc DAG mẫu của
   AIE-1 đổi sau ngày đo, kết quả này không tự cập nhật — cần chạy lại tay để biết còn đúng hay
   không. Ghi rõ ở đây theo góp ý review PR#23 (AIE-2), để lượt sau không ai tưởng nhầm đây là một
   cổng CI đang canh gác).

2. **Demo spine 4 bước chạy thật** — dùng `apps/studio/scripts/e2e_smoke_eval.py` (đã tồn tại từ
   trước, tự chứng minh 4 quadrant ghép qua Postgres thật: `workbench.create_recipe_d4 →
   engine.interpreter.run → kb.PgKbSearch → evalhub.score_case`) làm bằng chứng chính, thay vì chờ
   route HTTP mới của `apps/studio` (Kế hoạch 2, cần mentor duyệt trước khi lên production — không
   để Day 20 phụ thuộc vào việc đó).

3. **T1/T6** — RED-CHECK sẵn có trong `e2e_smoke_eval.py` (`XF-01`/`XF-02`, dựng `_LeakyKb` cố ý
   hỏng fence) — chạy lại, xác nhận cả 2 case vẫn đỏ đúng như thiết kế.

4. **cost cùng-1-số** — phụ thuộc DE (`kb#22`, cost-lineage) đang `changes-requested`, CHƯA merge.
   `tokens` đã thật (AIE-1 PR#24, đếm theo từ), nhưng `cost` (số tiền) vẫn hardcode `_NO_COST =
   0.0` (`interpreter.py`) vì chưa có bảng giá. **Không tự vá ở workbench** — đây là phụ thuộc
   ngoài, cần escalate, không phải việc SWE tự đóng được.

5. **eval v1 verdict** — `Scorecard.gate.verdict` tính được thật ngay hôm nay qua
   `EvalHarness.run()` (evalhub, đã implement xong) — có thể demo phần TÍNH được (Scorecard sinh
   ra đúng, verdict đúng logic so với threshold), tách riêng khỏi phần "publish có thành công
   không" (route `POST /api/agents/{id}/publish` viết ở Kế hoạch 2 sẽ LUÔN bị chặn ở
   `scorecard.recipe_hash is None` cho tới khi AIE-2 xong DEC-03 — biết trước, không phải bug phát
   sinh ngày gate).

6. **plan-vs-actual** — file evidence riêng (`docs/reports/gate-2/swe-Dozyboy.md`) đối chiếu lại
   plan này sau khi đo xong bằng lệnh thật.

## Rủi ro/phụ thuộc đã biết trước (không đợi tới ngày gate mới phát hiện)

- `cost` phụ thuộc DE (kb#22, đang block).
- `eval v1 verdict` → `publish()` thành công phụ thuộc AIE-2 (`recipe_hash`, DEC-03, chưa có
  producer).
- "6 node-type" phụ thuộc xác nhận tương thích `graph_lint()` ↔ AIE-1's DAG mẫu (mục 1, chưa làm
  tại thời điểm viết plan này).
