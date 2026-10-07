"""把原始 dict 配置解析并校验为不可变的 FlagSet。

配置结构（JSON/YAML 兼容的 dict）::

    {
      "flags": {
        "new-checkout": {
          "default": false,
          "force_off": false,
          "rollouts": [{"dimension": "user_id", "percentage": 25}],
          "overrides": [
            {"dimension": "user_id", "match": "u-1", "value": true,
             "expires_at": 1790000000}
          ]
        }
      }
    }

任何一处非法都会抛出带 InvalidReason 的 FlagConfigError，且整体不生效。
"""

from __future__ import annotations

import time
from typing import Any

from .errors import FlagConfigError, InvalidReason
from .models import FlagConfig, FlagSet, Override, RolloutRule

_FLAG_FIELDS = {"default", "force_off", "rollouts", "overrides"}
_OVERRIDE_FIELDS = {"dimension", "match", "value", "expires_at"}
_ROLLOUT_FIELDS = {"dimension", "percentage"}


def _err(reason: InvalidReason, path: str, message: str) -> FlagConfigError:
    return FlagConfigError(reason, path, message)


def _parse_rollout(raw: Any, path: str) -> RolloutRule:
    if not isinstance(raw, dict):
        raise _err(InvalidReason.NOT_A_MAPPING, path, "灰度规则必须是对象")
    unknown = set(raw) - _ROLLOUT_FIELDS
    if unknown:
        raise _err(InvalidReason.UNKNOWN_FLAG_FIELD, path, f"灰度规则含未知字段 {sorted(unknown)}")
    dimension = raw.get("dimension")
    if not isinstance(dimension, str) or not dimension:
        raise _err(InvalidReason.BAD_ROLLOUT_DIMENSION, path, "灰度维度必须是非空字符串")
    percentage = raw.get("percentage")
    if isinstance(percentage, bool) or not isinstance(percentage, (int, float)):
        raise _err(InvalidReason.BAD_ROLLOUT_PERCENTAGE, path, "percentage 必须是数字")
    if not 0.0 <= percentage <= 100.0:
        raise _err(
            InvalidReason.BAD_ROLLOUT_PERCENTAGE,
            path,
            f"percentage 必须在 [0, 100] 内，当前为 {percentage}",
        )
    return RolloutRule(dimension=dimension, percentage=float(percentage))


def _parse_override(raw: Any, path: str, now: float) -> Override:
    if not isinstance(raw, dict):
        raise _err(InvalidReason.NOT_A_MAPPING, path, "覆盖项必须是对象")
    unknown = set(raw) - _OVERRIDE_FIELDS
    if unknown:
        raise _err(InvalidReason.UNKNOWN_FLAG_FIELD, path, f"覆盖项含未知字段 {sorted(unknown)}")
    dimension = raw.get("dimension")
    match = raw.get("match")
    value = raw.get("value")
    if not isinstance(dimension, str) or not dimension:
        raise _err(InvalidReason.BAD_OVERRIDE, path, "覆盖维度必须是非空字符串")
    if not isinstance(match, str):
        raise _err(InvalidReason.BAD_OVERRIDE, path, "覆盖 match 必须是字符串")
    if not isinstance(value, bool):
        raise _err(InvalidReason.BAD_OVERRIDE, path, "覆盖 value 必须是 bool")
    expires_at = raw.get("expires_at")
    if expires_at is not None:
        if isinstance(expires_at, bool) or not isinstance(expires_at, (int, float)):
            raise _err(InvalidReason.BAD_OVERRIDE, path, "expires_at 必须是数字（epoch 秒）")
        if expires_at <= now:
            raise _err(
                InvalidReason.EXPIRED_OVERRIDE,
                path,
                f"覆盖已过期（expires_at={expires_at} <= now={now}），请删除或续期",
            )
    return Override(dimension=dimension, match=match, value=value, expires_at=expires_at)


def _parse_flag(name: str, raw: Any, path: str, now: float) -> FlagConfig:
    if not isinstance(raw, dict):
        raise _err(InvalidReason.NOT_A_MAPPING, path, "开关配置必须是对象")
    unknown = set(raw) - _FLAG_FIELDS
    if unknown:
        raise _err(InvalidReason.UNKNOWN_FLAG_FIELD, path, f"开关含未知字段 {sorted(unknown)}")
    if "default" not in raw:
        raise _err(InvalidReason.MISSING_DEFAULT, path, "缺少 default 值")
    default = raw["default"]
    if not isinstance(default, bool):
        raise _err(InvalidReason.BAD_DEFAULT_TYPE, path, "default 必须是 bool")
    force_off = raw.get("force_off", False)
    if not isinstance(force_off, bool):
        raise _err(InvalidReason.UNKNOWN_FLAG_FIELD, path, "force_off 必须是 bool")
    rollouts_raw = raw.get("rollouts", [])
    if not isinstance(rollouts_raw, list):
        raise _err(InvalidReason.NOT_A_MAPPING, path, "rollouts 必须是数组")
    rollouts = tuple(
        _parse_rollout(r, f"{path}.rollouts[{i}]") for i, r in enumerate(rollouts_raw)
    )
    overrides_raw = raw.get("overrides", [])
    if not isinstance(overrides_raw, list):
        raise _err(InvalidReason.NOT_A_MAPPING, path, "overrides 必须是数组")
    overrides = tuple(
        _parse_override(o, f"{path}.overrides[{i}]", now)
        for i, o in enumerate(overrides_raw)
    )
    return FlagConfig(
        name=name,
        default=default,
        force_off=force_off,
        rollouts=rollouts,
        overrides=overrides,
    )


def parse_flag_set(raw: Any, *, version: int = 0, now: float | None = None) -> FlagSet:
    """解析并校验原始配置；非法时抛出带 reason 的 FlagConfigError。

    now 用于判定覆盖是否过期，默认取当前时间；测试可注入固定值。
    """
    if now is None:
        now = time.time()
    if not isinstance(raw, dict):
        raise _err(InvalidReason.NOT_A_MAPPING, "$", "配置必须是对象")
    flags_raw = raw.get("flags", {})
    if not isinstance(flags_raw, dict):
        raise _err(InvalidReason.NOT_A_MAPPING, "$.flags", "flags 必须是对象")
    flags: dict[str, FlagConfig] = {}
    for name, flag_raw in flags_raw.items():
        if not isinstance(name, str) or not name:
            raise _err(InvalidReason.BAD_OVERRIDE, "$.flags", "开关名必须是非空字符串")
        flags[name] = _parse_flag(name, flag_raw, f"$.flags.{name}", now)
    return FlagSet(flags=flags, version=version)
