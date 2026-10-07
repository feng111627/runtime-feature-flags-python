"""配置存储：原子热更新，读写并发安全。

- 更新前完整校验；校验失败则整体保留旧配置。
- 读侧拿到的是不可变快照引用，更新只替换引用，不会撕裂。
"""

from __future__ import annotations

import threading
from datetime import datetime

from .evaluation import Evaluator
from .models import FlagSetConfig


class FlagStore:
    """持有当前生效的配置快照，支持原子替换。"""

    def __init__(self, initial: FlagSetConfig | None = None):
        self._lock = threading.Lock()
        self._evaluator: Evaluator = Evaluator(initial or FlagSetConfig())
        self._version: int = 0

    def current(self) -> Evaluator:
        """获取当前求值器（不可变快照，读取无需加锁）。"""
        raise NotImplementedError

    def update(self, raw: object, *, now: datetime | None = None) -> int:
        """校验并原子替换配置；成功返回新版本号，失败抛 FlagConfigError 且旧配置不变。"""
        raise NotImplementedError

    @property
    def version(self) -> int:
        raise NotImplementedError
