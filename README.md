# agentcore-studio-workbench

> Workbench UI wiring, recipe validator / graph-lint, Tenant-Wall.

**Owner:** SWE — Thiệu Quang Minh · **Loại:** uv workspace member (Python 3.14) · **Repo cha:** [agentcore-studio-kit](https://github.com/hieubui2409/agentcore-studio-kit)

## Repo này là gì
Submodule `packages/workbench` của workspace `agentcore-studio-kit`. Owner: **SWE — Thiệu Quang Minh**. Chứa wiring cho Workbench, recipe validator / graph-lint, Tenant-Wall.

## ⚠️ Không build/test độc lập được
`agentcore-studio-workbench` phụ thuộc `agentcore-studio-contracts` + uv.lock + `docker/postgres-init` của repo cha, và cần **Postgres** cho test. Vì vậy:
- **Làm việc qua repo cha:** `git clone --recursive git@github.com:hieubui2409/agentcore-studio-kit.git`, rồi `cd packages/workbench` để sửa / commit / push chính repo này.
- **Test đầy đủ:** đẩy PR → CI tự **dựng lại full workspace** rồi chạy `pytest packages/workbench/tests` (Phương án B).

## CI
`.github/workflows/ci.yml` chỉ là **stub** gọi reusable workflow chung ở repo cha:
`hieubui2409/agentcore-studio-kit/.github/workflows/reusable-domain-ci.yml@main`.
Muốn đổi quy trình CI thì sửa ở repo cha (1 chỗ).

## Quy tắc
- Chỉ đụng file trong `packages/workbench/**` (fence-lane của bạn) — không sửa surface domain khác.
- Đổi contract → sang repo `agentcore-studio-contracts` (mentor-approval).
- Không commit tài liệu mentor/rubric/answer-key (pre-commit `nda-denylist` chặn).

📖 Phân quyền + luồng thao tác đầy đủ: [GITFLOWS.md](https://github.com/hieubui2409/agentcore-studio-kit/blob/main/GITFLOWS.md)
