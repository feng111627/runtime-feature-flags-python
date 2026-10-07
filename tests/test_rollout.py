"""场景二：灰度放量 —— 边界行为、稳定性与请求内一致性。"""

import threading

from feature_flags import EvaluationContext, bucket, parse_flag_set

NOW = 1_800_000_000.0


def rollout_fs(pct):
    return parse_flag_set(
        {"flags": {"f": {"default": False, "rollouts": [{"dimension": "user_id", "percentage": pct}]}}},
        now=NOW,
    )


def test_百分比为0时_任何用户都不命中():
    fs = rollout_fs(0)
    for i in range(200):
        assert EvaluationContext({"user_id": f"u{i}"}).is_enabled(fs, "f") is False


def test_百分比为100时_任何用户都命中():
    fs = rollout_fs(100)
    for i in range(200):
        assert EvaluationContext({"user_id": f"u{i}"}).is_enabled(fs, "f") is True


def test_缺少灰度维度时_不命中灰度_回落默认值():
    fs = rollout_fs(100)
    assert EvaluationContext({}).is_enabled(fs, "f") is False


def test_桶位稳定_同一输入多次计算结果相同():
    assert bucket("u1", "f") == bucket("u1", "f")
    assert 0.0 <= bucket("u1", "f") < 100.0


def test_放量比例大致符合预期():
    fs = rollout_fs(50)
    hits = sum(
        EvaluationContext({"user_id": f"user-{i}"}).is_enabled(fs, "f")
        for i in range(2000)
    )
    assert 850 < hits < 1150  # 50% ± 7.5%


def test_同一请求内多次求值结果一致():
    fs = rollout_fs(50)
    ctx = EvaluationContext({"user_id": "user-7"})
    first = ctx.is_enabled(fs, "f")
    for _ in range(50):
        assert ctx.is_enabled(fs, "f") is first


def test_请求内一致性不受热更新影响_上下文缓存结果():
    from feature_flags import FlagStore

    store = FlagStore()
    store.update({"flags": {"f": {"default": True}}})
    ctx = EvaluationContext({})
    assert ctx.is_enabled(store.snapshot(), "f") is True
    # 热更新把开关关掉，但同一请求上下文内结果不变
    store.update({"flags": {"f": {"default": False}}})
    assert ctx.is_enabled(store.snapshot(), "f") is True
    # 新请求看到新值
    assert EvaluationContext({}).is_enabled(store.snapshot(), "f") is False
