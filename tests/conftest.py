"""Local test-infra override, scoped to THIS directory only.

Windows defaults `asyncio` to `ProactorEventLoop`, which `psycopg` async refuses ("Psycopg cannot
use the 'ProactorEventLoop' to run in async mode"). The kit-root `conftest.py` (repo cha) không có
fix này, và `apps/studio/tests/conftest.py` chỉ áp dụng cho thư mục đó (pytest merge `conftest.py`
theo cây thư mục, không lan ngang sang `packages/workbench/tests/`) — nên các test DB thật ở đây
(`test_publish.py`, `test_wb_schema.py`) trước giờ luôn bị skip khi thiếu DSN, chưa từng thật sự
chạy trên Windows để lộ lỗ hổng này. Thêm cùng fixture ở đây, cùng mẫu đã áp cho `apps/studio`.
"""

from __future__ import annotations

import asyncio
import sys

import pytest


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()
