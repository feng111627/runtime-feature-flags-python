"""开关求值。

优先级（从高到低）：
1. force_off —— 强制关闭，任何覆盖都不能打开；
2. overrides —— 按维度精确匹配的覆盖（未过期）；
3. rollouts —— 按维度一致性哈希的百分比灰度；
4. default —— 开关默认值。

同一 EvaluationContext（一次请求生命周期）内，同一开关的求值结果被缓存，
保证多次求值一致，即使期间发生了热更新。
"""

from __future__ import annotations

import hashlib
import time
from typing import Mapping, Optional

from .models import FlagConfig, FlagSet


def bucket(dimension_value: str, flag_name: str) -> float:
    """把维度值稳定映射到 [0, 100) 的桶位。

    以 "flag名:维度值" 为哈希输入，保证同一用户在不同开关下分布独立，
    且同一输入永远落在同一桶位（与进程、重启无关）。
    """
    key = f"{flag_name}:{dimension_value}".encode("utf-8")
    digest = hashlib.sha256(key).hexdigest()
    # 取前 12 位十六进制，精度足够且避免浮点边界问题
    return (int(digest[:12], 16) % 1_000_000) / 10_000.0


def evaluate(flag: FlagConfig, attributes: Mapping[str, str], now: float) -> bool:
    """按优先级对单个开关求值（不含请求级缓存）。"""
    # 1. 强制关闭：最高优先级，任何覆盖都不能打开
    if flag.force_off:
        return False
    # 2. 覆盖：按声明顺序取第一个命中的未过期覆盖
    for override in flag.overrides:
        if override.expires_at is not None and override.expires_at <= now:
            continue  # 过期覆盖视为不存在（加载时已拒绝，这里是双保险）
        if attributes.get(override.dimension) == override.match:
            return override.value
    # 3. 灰度：任一规则命中即开启；请求缺少该维度时不命中
    for rule in flag.rollouts:
        value = attributes.get(rule.dimension)
        if value is None:
            continue
        if rule.percentage >= 100.0:
            return True
        if rule.percentage <= 0.0:
            continue
        if bucket(value, flag.name) < rule.percentage:
            return True
    # 4. 默认值
    return flag.default


class EvaluationContext:
    """一次请求生命周期内的求值上下文。

    attributes 为请求维度（如 user_id、region）。同一上下文内同一开关
    只真正求值一次，之后命中缓存，保证请求内结果一致。
    """

    def __init__(self, attributes: Optional[Mapping[str, str]] = None) -> None:
        self.attributes: Mapping[str, str] = attributes or {}
        self._cache: dict[str, bool] = {}

    def is_enabled(self, flag_set: FlagSet, name: str) -> bool:
        """求值开关；未定义的开关返回 False（安全的默认）。"""
        if name in self._cache:
            return self._cache[name]
        flag = flag_set.flags.get(name)
        result = evaluate(flag, self.attributes, time.time()) if flag else False
        self._cache[name] = result
        return result
