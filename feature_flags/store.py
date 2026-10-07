"""支持原子热更新的开关存储。

设计要点：
- 配置以不可变 FlagSet 快照整体存放，读路径无锁，直接引用当前快照；
- 更新时先完整解析校验，全部通过后在锁内一次性替换引用，
  因此要么整体生效、要么整体保持旧值，不存在半新半旧；
- 校验失败或读到损坏内容时抛 FlagConfigError，旧快照原样保留；
- 求值方持有的是快照引用，更新替换引用不影响进行中的求值，
  不会出现撕裂或串值。
"""

from __future__ import annotations

import threading
from typing import Any, Optional

from .models import FlagSet
from .validation import parse_flag_set


class FlagStore:
    """线程安全的开关存储，支持整体原子替换。"""

    def __init__(self, initial: Optional[FlagSet] = None) -> None:
        self._lock = threading.Lock()
        self._current: FlagSet = initial if initial is not None else FlagSet()

    def snapshot(self) -> FlagSet:
        """获取当前不可变快照（无锁读；引用语义保证不撕裂）。"""
        return self._current

    def update(self, raw: Any) -> FlagSet:
        """校验并整体替换配置。

        校验失败时抛出 FlagConfigError，旧配置原样保留。
        成功时返回新快照，version 自动递增。
        """
        with self._lock:
            new_set = parse_flag_set(raw, version=self._current.version + 1)
            self._current = new_set
            return new_set
