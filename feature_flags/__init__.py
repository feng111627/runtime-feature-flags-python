"""运行时特性开关：求值、灰度、热更新、覆盖与强制关闭。"""

from .errors import FlagConfigError, InvalidReason
from .evaluation import EvaluationContext, bucket, evaluate
from .models import FlagConfig, FlagSet, Override, RolloutRule
from .store import FlagStore
from .validation import parse_flag_set

__all__ = [
    "EvaluationContext",
    "FlagConfig",
    "FlagConfigError",
    "FlagSet",
    "FlagStore",
    "InvalidReason",
    "Override",
    "RolloutRule",
    "bucket",
    "evaluate",
    "parse_flag_set",
]
