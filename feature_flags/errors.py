"""特性开关配置校验的错误类型。

每种非法配置都有独立的 reason 码，便于调用方区分失败原因。
"""

from __future__ import annotations

from enum import Enum


class InvalidReason(str, Enum):
    """配置非法的可区分原因。"""

    NOT_A_MAPPING = "not_a_mapping"            # 顶层或字段类型不是字典
    UNKNOWN_FLAG_FIELD = "unknown_flag_field"  # 开关里出现未知字段
    MISSING_DEFAULT = "missing_default"        # 缺少 default 值
    BAD_DEFAULT_TYPE = "bad_default_type"      # default 不是 bool
    BAD_ROLLOUT_PERCENTAGE = "bad_rollout_percentage"  # 百分比非数字或越界
    BAD_ROLLOUT_DIMENSION = "bad_rollout_dimension"    # 灰度维度非法
    BAD_OVERRIDE = "bad_override"              # 覆盖项结构非法
    EXPIRED_OVERRIDE = "expired_override"      # 覆盖已过期
    DUPLICATE_FLAG = "duplicate_flag"          # 开关名重复（由调用方保证唯一时不会触发）


class FlagConfigError(ValueError):
    """配置校验失败。reason 区分原因，path 定位出错位置。"""

    def __init__(self, reason: InvalidReason, path: str, message: str) -> None:
        self.reason = reason
        self.path = path
        super().__init__(f"[{reason.value}] {path}: {message}")
