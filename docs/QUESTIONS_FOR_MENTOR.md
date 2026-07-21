# ❓ BỘ CÂU HỎI LÀM RÕ HỢP ĐỒNG & THIẾT KẾ (QUESTION-BATCH FOR MENTOR)

- **Người gửi:** SWE — Thiệu Quang Minh
- **Ngày gửi:** 21/07/2026
- **Mục tiêu:** Clarify-first — Làm rõ các điểm mơ hồ về Hợp đồng v0 và cơ chế Workbench trước khi triển khai code chi tiết.

---

## 🙋 BỘ 3 CÂU HỎI CHÍNH

### 1. Về Hợp đồng `recipe.py` (Contract #1) & Isolation Level
> **Câu hỏi:** Trong `Recipe` v0, phần `agent_config` đã bao gồm `instructions`, `model`, và `tool_whitelist`. Đối với trường `tenant`, Workbench sẽ validate và inject `tenant` ID ở tầng API Header (`Tenant-Wall`) hay bắt buộc trường `tenant` phải nằm trực tiếp trong `Recipe` metadata Pydantic model?

### 2. Về Cơ chế Fallback UI (Canvas ➔ Form + Mermaid Render)
> **Câu hỏi:** Theo `DESCOPE.md` (Nấc 2), khi tụt nấc từ Canvas React Flow về Form + Mermaid, sơ đồ Mermaid chuỗi chữ sẽ được Render trực tiếp ở phía Frontend (Client-side) dựa trên DAG JSON hay phía Backend Python (`studio_workbench`) sẽ cung cấp helper method `recipe_to_mermaid(recipe: Recipe) -> str`?

### 3. Về Luồng Publish & Phê duyệt Scorecard (`publish.py`)
> **Câu hỏi:** Hàm `publish(recipe, scorecard)` có yêu cầu kiểm tra bắt buộc `scorecard.pass == True` ngay tại `publish.py` của Workbench không, hay việc cấp quyền Publish sẽ do `EvalHub` (AIE-2) đóng dấu token/signature độc lập trước khi gửi sang Workbench?

---

## 📌 GHI CHÚ
- Bộ câu hỏi này tuân thủ đúng tiêu chuẩn DoD Ngày 2 ($\ge 3$ câu hỏi clarify trước khi gõ logic chính).
