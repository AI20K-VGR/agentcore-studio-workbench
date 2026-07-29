# 📊 BÁO CÁO TIẾN ĐỘ NGÀY 8 (D08-REPORT) — SWE

📚 **Personal Self-Study & Knowledge Vault:** https://github.com/Dozyboy/VSF

- **Người thực hiện:** Thiệu Quang Minh
- **Vai trò:** Kỹ sư Phần mềm (SWE)
- **Dự án:** AgentCore Studio - `agentcore-studio-workbench`
- **Ngày:** Thứ Tư, 29/07/2026
- **Nhiệm vụ:** Bút INV-1 middleware — `session → resolve {tenant, user, roles}` server-side + mandatory filter fail-closed; `tenant_id NOT NULL`
- **Issue:** #38 (`Day 8 — SWE (Thiệu Quang Minh) — Bút INV-1 middleware`)
- **Branch:** `feat/day8-tenant-wall-inv1`

---

## 🎯 1. TỔNG QUAN CÔNG VIỆC NGÀY 8 (TENANT-WALL INV-1 MIDDLEWARE)

Trong Ngày 8, vị trí SWE hoàn thiện **Tenant-Wall** — seam bảo mật quan trọng nhất tại workbench API boundary — bằng cách implement đầy đủ `resolve_tenant()` và `resolve_session()` trong `tenant_wall.py`:

1. **Implement `resolve_tenant(session)` (`src/studio_workbench/tenant_wall.py`)**:
   * Đọc `tenant_id` **hoàn toàn server-side** từ session mapping (auth-derived / JWT claims).
   * Hỗ trợ alias key `"tenant"` như fallback của `"tenant_id"`.
   * **Fail-closed (INV-1 mandatory filter)**: `tenant_id` thiếu / None / blank → raise `PermissionError` ngay lập tức, không để request đi tiếp.
   * Validate kiểu session bằng `collections.abc.Mapping` → reject `str`, `int`, object không phải mapping → raise `TypeError`.
   * Ngăn T1 IDOR: tenant dùng cho mọi downstream check **chỉ** đến từ session server-side, không bao giờ từ request payload của client.

2. **Implement `resolve_session(session)` và `ResolvedContext`**:
   * Trả về `ResolvedContext(tenant_id, user, roles)` — dataclass **frozen/immutable** bảo vệ dữ liệu identity sau khi resolve.
   * Resolve đủ 3 trường theo spec issue #38: `{tenant, user, roles}`.
   * `user` fail-closed: thiếu / None / blank → `PermissionError`.
   * `roles`: thiếu → default `[]` (least-privilege); nhận list hoặc OAuth2 space-separated scope string (`"hr finance public"` → `["hr", "finance", "public"]`).
   * Hỗ trợ alias key: `"sub"` / `"user_id"` cho user (JWT standard); `"scope"` cho roles.

3. **Viết Test Suite D8 (`tests/test_wiring_d8.py`)**:
   * 16 test case bao phủ toàn bộ spec:
     - Happy path: tenant, user, roles đầy đủ.
     - Fail-closed paths: missing/None/blank tenant_id; missing/blank user.
     - T1 IDOR prevention: session-derived value luôn thắng client payload.
     - Alias key acceptance: `"tenant"`, `"sub"`, `"scope"`.
     - OAuth2 scope string parsing.
     - `ResolvedContext` frozen (immutable).
     - TypeError trên non-mapping session.

---

## ✅ 2. KẾT QUẢ ĐẠT ĐƯỢC & BẰNG CHỨNG (DoD CHECKLIST)

- [x] **`resolve_tenant()` implemented**: Đọc server-side, fail-closed, T1 IDOR safe, NOT NULL invariant ([`src/studio_workbench/tenant_wall.py`](file:///c:/Users/Admin/OneDrive/Máy%20tính/Minh/agentcore-studio-workbench/src/studio_workbench/tenant_wall.py))
- [x] **`resolve_session()` implemented**: Resolve đủ `{tenant_id, user, roles}`, fail-closed, least-privilege default.
- [x] **`ResolvedContext` dataclass**: Frozen/immutable — không thể mutate sau khi resolve.
- [x] **Test Suite Ngày 8 (`test_wiring_d8.py`)**: 16 test case, **16/16 PASSED** ([`tests/test_wiring_d8.py`](file:///c:/Users/Admin/OneDrive/Máy%20tính/Minh/agentcore-studio-workbench/tests/test_wiring_d8.py))
- [x] **Full Workbench Suite không regression**: 37 passed, 0 failed (bao gồm D3→D8).
- [x] **Branch**: `feat/day8-tenant-wall-inv1`

---

## 📊 3. KẾT QUẢ CHẠY TESTSUITE

```text
======================================================================
📊 KẾT QUẢ KIỂM THỬ SUITE DAY 8 (WORKBENCH)
======================================================================
MODULE                      | TEST SUITE STATUS | PASSED / TOTAL
----------------------------------------------------------------------
test_wiring_d8 (D8 new)     | PASSED            | 16 / 16 (100%)
agentcore-studio-workbench  | PASSED            | 37 / 37 (100%)
======================================================================
🎯 ĐÁNH GIÁ CHUNG: 100% TESTSUITE PASSED (GREEN CI)
======================================================================
```

*(1 SKIPPED: `test_wb_ddl_idempotent` — yêu cầu Postgres, đúng theo thiết kế; 1 XFAIL + 2 XPASS: `test_graph_lint` — stub đang đợi implement, không ảnh hưởng CI)*

---

## 🔒 4. RÀNG BUỘC KỸ THUẬT & QUYẾT ĐỊNH THIẾT KẾ

1. **`collections.abc.Mapping` thay vì duck-typing `__getitem__`**: `str` có `__getitem__` nhưng không phải Mapping — dùng `isinstance(session, Mapping)` để reject chính xác các non-mapping type.
2. **Fail-closed không phải fail-open**: Bất kỳ trường hợp mơ hồ nào (`None`, `""`, key không tồn tại) → `PermissionError`, không bao giờ trả về fallback hay `None`.
3. **`ResolvedContext` là `frozen=True, slots=True`**: Đảm bảo identity không bị mutate sau khi resolve — ai có tham chiếu đến context đều thấy giá trị gốc.
4. **`roles` là least-privilege-safe**: Thiếu `roles` → `[]`, không phải error — phù hợp với nguyên tắc deny-by-default của RLS downstream.
5. **Không chạm sang package khác**: Chỉ sửa `packages/workbench/` — không đụng `contracts`, `engine`, `kb`, hay `app`.

---

## 🚀 5. KẾ HOẠCH NGÀY TIẾP THEO

1. Implement `graph_lint()` 4-rule DAG validator (`validator.py`) — hiện đang là stub `NotImplementedError`, là prerequisite cho `publish()`.
2. Implement `publish()` + `rollback()` (`publish.py`) — gated by `graph_lint` + `scorecard.gate.verdict`.
3. Phối hợp với AIE-2 để kiểm thử luồng Scorecard → Publish đầy đủ.
