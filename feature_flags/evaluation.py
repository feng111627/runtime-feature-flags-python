"""开关求值器：优先级、灰度分桶、请求内一致性。

优先级（高 -> 低）：
    force_off > override > 维度规则 rules > 百分比灰度 rollout > 默认值 default
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import FlagSetConfig


@dataclass
class EvalContext:
    """一次请求生命周期内的求值上下文。

    - dimensions: 请求维度，如 {"user_id": "u-1", "region": "cn-north"}
    - 同一上下文对同一开关多次求值结果一致（内部记忆化）。
    """

    dimensions: dict[str, str]
    _memo: dict[str, bool] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class EvalResult:
    """单次求值结果，附带命中来源，保证可解释。"""

    flag: str
    enabled: bool
    source: str  # force_off / override / rule / rollout / default / unknown_flag


class Evaluator:
    """对一份不可变配置快照求值，线程安全（只读）。"""

    def __init__(self, config: FlagSetConfig):
        self._config = config

    def evaluate(self, name: str, ctx: EvalContext) -> EvalResult:
        """求值单个开关；同一 ctx 内结果记忆化，保证请求内一致。"""
        raise NotImplementedError
