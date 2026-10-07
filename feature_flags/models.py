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

from .errors import FlagConfigError, InvalidReason


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


def _require_mapping(node: object, where: str, *, flag: str | None = None) -> dict:
    if not isinstance(node, dict):
        raise FlagConfigError(
            InvalidReason.MALFORMED_DOCUMENT, f"{where} 必须是对象，得到 {type(node).__name__}", flag=flag
        )
    return node


def _require_bool(node: object, where: str, *, flag: str | None = None) -> bool:
    if not isinstance(node, bool):
        raise FlagConfigError(
            InvalidReason.MALFORMED_DOCUMENT, f"{where} 必须是布尔值，得到 {node!r}", flag=flag
        )
    return node


def _require_str_list(node: object, where: str, *, flag: str | None = None) -> frozenset[str]:
    if (
        not isinstance(node, list)
        or not node
        or any(not isinstance(v, str) or not v for v in node)
    ):
        raise FlagConfigError(
            InvalidReason.EMPTY_RULE_VALUES, f"{where} 必须是非空字符串数组，得到 {node!r}", flag=flag
        )
    return frozenset(node)


def _parse_rollout(node: object, *, flag: str) -> Rollout | None:
    if node is None:
        return None
    data = _require_mapping(node, "rollout", flag=flag)
    percentage = data.get("percentage")
    if not isinstance(percentage, int) or isinstance(percentage, bool) or not 0 <= percentage <= 100:
        raise FlagConfigError(
            InvalidReason.BAD_PERCENTAGE, f"rollout.percentage 必须是 [0,100] 的整数，得到 {percentage!r}", flag=flag
        )
    dimension = data.get("dimension", "user_id")
    if not isinstance(dimension, str) or not dimension:
        raise FlagConfigError(InvalidReason.EMPTY_DIMENSION, "rollout.dimension 不能为空", flag=flag)
    return Rollout(percentage=percentage, dimension=dimension)


def _parse_rules(node: object, *, flag: str) -> tuple[DimensionRule, ...]:
    if node is None:
        return ()
    if not isinstance(node, list):
        raise FlagConfigError(InvalidReason.MALFORMED_DOCUMENT, "rules 必须是数组", flag=flag)
    rules: list[DimensionRule] = []
    for i, item in enumerate(node):
        data = _require_mapping(item, f"rules[{i}]", flag=flag)
        dimension = data.get("dimension")
        if not isinstance(dimension, str) or not dimension:
            raise FlagConfigError(InvalidReason.EMPTY_DIMENSION, f"rules[{i}].dimension 不能为空", flag=flag)
        values = _require_str_list(data.get("values"), f"rules[{i}].values", flag=flag)
        enabled = _require_bool(data.get("enabled", True), f"rules[{i}].enabled", flag=flag)
        rules.append(DimensionRule(dimension=dimension, values=values, enabled=enabled))
    return tuple(rules)


def _parse_overrides(node: object, *, flag: str, now: datetime) -> tuple[Override, ...]:
    if node is None:
        return ()
    if not isinstance(node, list):
        raise FlagConfigError(InvalidReason.MALFORMED_DOCUMENT, "overrides 必须是数组", flag=flag)
    overrides: list[Override] = []
    for i, item in enumerate(node):
        data = _require_mapping(item, f"overrides[{i}]", flag=flag)
        dimension = data.get("dimension")
        if not isinstance(dimension, str) or not dimension:
            raise FlagConfigError(InvalidReason.EMPTY_DIMENSION, f"overrides[{i}].dimension 不能为空", flag=flag)
        values = _require_str_list(data.get("values"), f"overrides[{i}].values", flag=flag)
        enabled = _require_bool(data.get("enabled"), f"overrides[{i}].enabled", flag=flag)
        expires_at: datetime | None = None
        raw_exp = data.get("expires_at")
        if raw_exp is not None:
            if not isinstance(raw_exp, str):
                raise FlagConfigError(
                    InvalidReason.BAD_OVERRIDE_TIME, f"overrides[{i}].expires_at 必须是 ISO8601 字符串", flag=flag
                )
            try:
                expires_at = datetime.fromisoformat(raw_exp)
            except ValueError as exc:
                raise FlagConfigError(
                    InvalidReason.BAD_OVERRIDE_TIME, f"overrides[{i}].expires_at 无法解析: {raw_exp!r}", flag=flag
                ) from exc
            if expires_at.tzinfo is None:
                raise FlagConfigError(
                    InvalidReason.BAD_OVERRIDE_TIME, f"overrides[{i}].expires_at 必须带时区", flag=flag
                )
            if expires_at <= now:
                raise FlagConfigError(
                    InvalidReason.EXPIRED_OVERRIDE,
                    f"overrides[{i}] 已过期（expires_at={raw_exp!r} <= now），拒绝加载而非静默忽略",
                    flag=flag,
                )
        overrides.append(Override(dimension=dimension, values=values, enabled=enabled, expires_at=expires_at))
    return tuple(overrides)


def parse_flag_set(raw: object, *, now: datetime | None = None) -> FlagSetConfig:
    """把原始 dict 解析并校验为 FlagSetConfig；非法时抛 FlagConfigError。

    任何一处非法都会整体拒绝（调用方据此保证热更新要么全生效要么全不生效）。
    """
    now = now or datetime.now().astimezone()
    doc = _require_mapping(raw, "配置文档")
    flags_node = _require_mapping(doc.get("flags", {}), "flags")

    flags: dict[str, FlagConfig] = {}
    for name, node in flags_node.items():
        if not isinstance(name, str) or not name:
            raise FlagConfigError(InvalidReason.MALFORMED_DOCUMENT, f"开关名必须是非空字符串，得到 {name!r}")
        if name in flags:
            raise FlagConfigError(InvalidReason.DUPLICATE_FLAG, f"开关 {name!r} 重复定义", flag=name)
        data = _require_mapping(node, f"flags.{name}", flag=name)
        if "default" not in data:
            raise FlagConfigError(InvalidReason.MISSING_DEFAULT, f"开关 {name!r} 缺少 default", flag=name)
        default = _require_bool(data["default"], f"flags.{name}.default", flag=name)
        force_off = _require_bool(data.get("force_off", False), f"flags.{name}.force_off", flag=name)
        flags[name] = FlagConfig(
            name=name,
            default=default,
            rollout=_parse_rollout(data.get("rollout"), flag=name),
            rules=_parse_rules(data.get("rules"), flag=name),
            overrides=_parse_overrides(data.get("overrides"), flag=name, now=now),
            force_off=force_off,
        )
    return FlagSetConfig(flags=flags)
