"""Local test-infra override, scoped to THIS directory only.

Windows defaults `asyncio` to `ProactorEventLoop`, which `psycopg` async refuses ("Psycopg cannot
use the 'ProactorEventLoop' to run in async mode"). The kit-root `conftest.py` (repo cha) không có
fix này, và `apps/studio/tests/conftest.py` chỉ áp dụng cho thư mục đó (pytest merge `conftest.py`
theo cây thư mục, không lan ngang sang `packages/workbench/tests/`) — nên các test DB thật ở đây
(`test_publish.py`, `test_wb_schema.py`) trước giờ luôn bị skip khi thiếu DSN, chưa từng thật sự
chạy trên Windows để lộ lỗ hổng này. Thêm cùng fixture ở đây, cùng mẫu đã áp cho `apps/studio`.

`ANKOR_ID`/`assert_finding_status` bên dưới (app#44) là helper dùng chung cho
`test_agent_shape_lint.py`/`test_agent_topology_lint.py` — trước bản vá `/simplify` mỗi file tự
định nghĩa lại y hệt.
"""

from __future__ import annotations

import asyncio
import sys
from uuid import UUID

import pytest

ANKOR_ID = UUID("a0000000-0000-0000-0000-000000000001")


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


def assert_finding_status(findings: list[dict[str, str]], rule: str, expected: str) -> None:
    actual = next(f["status"] for f in findings if f["rule"] == rule)
    assert actual == expected, f"{rule}: expected status {expected!r}, got {actual!r} ({findings})"
