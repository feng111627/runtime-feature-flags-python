"""开关求值器：优先级、灰度分桶、请求内一致性。

优先级（高 -> 低）：
    force_off > override > 维度规则 rules > 百分比灰度 rollout > 默认值 default
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from .models import FlagSetConfig


def _bucket(flag: str, dimension_value: str) -> int:
    """把 (开关名, 维度值) 稳定映射到 [0, 100) 的桶。

    同一输入永远落在同一桶，与进程、机器无关（SHA-256 前 8 字节取模）。
    """
    digest = hashlib.sha256(f"{flag}:{dimension_value}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % 100


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
        if name in ctx._memo:
            return EvalResult(flag=name, enabled=ctx._memo[name], source="memo")
        result = self._evaluate_uncached(name, ctx)
        ctx._memo[name] = result.enabled
        return result

    def _evaluate_uncached(self, name: str, ctx: EvalContext) -> EvalResult:
        flag = self._config.flags.get(name)
        if flag is None:
            return EvalResult(flag=name, enabled=False, source="unknown_flag")

        # 1. 强制关闭：最高优先级，任何覆盖都不能打开。
        if flag.force_off:
            return EvalResult(flag=name, enabled=False, source="force_off")

        # 2. 定向覆盖：最细粒度，优先于灰度规则。
        for override in flag.overrides:
            value = ctx.dimensions.get(override.dimension)
            if value is not None and value in override.values:
                return EvalResult(flag=name, enabled=override.enabled, source="override")

        # 3. 维度规则（名单灰度）。
        for rule in flag.rules:
            value = ctx.dimensions.get(rule.dimension)
            if value is not None and value in rule.values:
                return EvalResult(flag=name, enabled=rule.enabled, source="rule")

        # 4. 百分比灰度：bucket < percentage 即命中。
        #    percentage=0 时永不命中；percentage=100 时恒命中（桶域为 [0,100)）。
        if flag.rollout is not None:
            value = ctx.dimensions.get(flag.rollout.dimension)
            if value is not None and _bucket(name, value) < flag.rollout.percentage:
                return EvalResult(flag=name, enabled=True, source="rollout")

        # 5. 默认值兜底。
        return EvalResult(flag=name, enabled=flag.default, source="default")
