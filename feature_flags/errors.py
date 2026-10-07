"""特性开关配置校验错误类型。

每种非法配置都有独立的 reason 码，便于调用方区分失败原因。
"""

from __future__ import annotations

from enum import Enum


class InvalidReason(str, Enum):
    """配置非法的可区分原因。"""

    DUPLICATE_FLAG = "duplicate_flag"                # 开关名重复
    MISSING_DEFAULT = "missing_default"              # 缺少默认值
    BAD_PERCENTAGE = "bad_percentage"                # 百分比不在 [0, 100]
    EMPTY_DIMENSION = "empty_dimension"              # 灰度维度名为空
    EMPTY_RULE_VALUES = "empty_rule_values"          # 维度规则取值列表为空
    UNKNOWN_FLAG_OVERRIDE = "unknown_flag_override"  # 覆盖指向不存在的开关
    EXPIRED_OVERRIDE = "expired_override"            # 覆盖已过期
    BAD_OVERRIDE_TIME = "bad_override_time"          # 覆盖时间格式非法
    MALFORMED_DOCUMENT = "malformed_document"        # 配置文档结构损坏


class FlagConfigError(ValueError):
    """配置校验失败，携带可区分的原因码与定位信息。"""

    def __init__(self, reason: InvalidReason, message: str, *, flag: str | None = None):
        self.reason = reason
        self.flag = flag
        super().__init__(f"[{reason.value}] {message}")
