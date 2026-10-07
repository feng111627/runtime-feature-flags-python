"""特性开关配置的数据结构与校验。

配置结构（JSON/YAML 可序列化为 dict）::

    {
      "flags": {
        "new_checkout": {
          "default": false,
          "rollout": {"percentage": 25, "dimension": "user_id"},
          "rules": [{"dimension": "region", "values": ["cn-north"], "enabled": true}],
          "overrides": [
            {"dimension": "user_id", "values": ["u-1"], "enabled": true,
             "expires_at": "2026-12-31T23:59:59+00:00"}
          ],
          "force_off": false
        }
      }
    }
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class Rollout:
    """按维度哈希的百分比灰度。"""

    percentage: int          # 0-100，含边界
    dimension: str = "user_id"


@dataclass(frozen=True)
class DimensionRule:
    """按维度取值名单的灰度规则。"""

    dimension: str
    values: frozenset[str]
    enabled: bool = True


@dataclass(frozen=True)
class Override:
    """定向覆盖，可带过期时间。"""

    dimension: str
    values: frozenset[str]
    enabled: bool
    expires_at: datetime | None = None


@dataclass(frozen=True)
class FlagConfig:
    """单个开关的完整配置。"""

    name: str
    default: bool
    rollout: Rollout | None = None
    rules: tuple[DimensionRule, ...] = ()
    overrides: tuple[Override, ...] = ()
    force_off: bool = False


@dataclass(frozen=True)
class FlagSetConfig:
    """一份完整、不可变的开关配置快照（热更新的原子单位）。"""

    flags: dict[str, FlagConfig] = field(default_factory=dict)


def parse_flag_set(raw: object, *, now: datetime | None = None) -> FlagSetConfig:
    """把原始 dict 解析并校验为 FlagSetConfig；非法时抛 FlagConfigError。"""
    raise NotImplementedError
