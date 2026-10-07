"""配置存储：原子热更新，读写并发安全。

- 更新前完整校验；校验失败则整体保留旧配置。
- 读侧拿到的是不可变快照引用，更新只替换引用，不会撕裂。
"""

from __future__ import annotations

import threading
from datetime import datetime

from .evaluation import Evaluator
from .models import FlagSetConfig, parse_flag_set


class FlagStore:
    """持有当前生效的配置快照，支持原子替换。

    线程安全说明：
    - 写侧（update）在锁内完成“解析校验 -> 构造新快照 -> 替换引用”；
      校验失败时抛异常，旧快照原封不动。
    - 读侧（current）只读一个引用赋值后的不可变对象，
      CPython 引用赋值原子，且快照本身 frozen，不会读到半新半旧。
    """

    def __init__(self, initial: FlagSetConfig | None = None):
        self._lock = threading.Lock()
        self._evaluator: Evaluator = Evaluator(initial or FlagSetConfig())
        self._version: int = 0

    def current(self) -> Evaluator:
        """获取当前求值器（不可变快照，读取无需加锁）。"""
        return self._evaluator

    def update(self, raw: object, *, now: datetime | None = None) -> int:
        """校验并原子替换配置；成功返回新版本号，失败抛 FlagConfigError 且旧配置不变。"""
        config = parse_flag_set(raw, now=now)  # 在锁外先做完整校验，失败即抛，旧配置不受影响
        evaluator = Evaluator(config)
        with self._lock:
            self._evaluator = evaluator
            self._version += 1
            return self._version

    @property
    def version(self) -> int:
        return self._version
