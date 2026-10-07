"""特性开关的不可变配置模型。

配置一旦构建并校验通过即不可变，热更新时整体替换，保证不会出现半新半旧。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Override:
    """针对某个维度取值的强制覆盖。value 为 None 表示未设置。"""

    dimension: str          # 维度名，如 "user_id" / "region"
    match: str              # 维度取值，精确匹配
    value: bool             # 覆盖结果
    expires_at: Optional[float] = None  # 过期时间（epoch 秒），None 表示不过期


@dataclass(frozen=True)
class RolloutRule:
    """灰度规则：对某维度按百分比放量。"""

    dimension: str          # 用于一致性哈希的维度
    percentage: float       # 0~100，含边界


@dataclass(frozen=True)
class FlagConfig:
    """单个开关的完整配置。"""

    name: str
    default: bool
    force_off: bool = False
    rollouts: tuple[RolloutRule, ...] = ()
    overrides: tuple[Override, ...] = ()


@dataclass(frozen=True)
class FlagSet:
    """一份完整、不可变的开关配置快照。"""

    flags: dict[str, FlagConfig] = field(default_factory=dict)
    version: int = 0
