"""场景一：优先级 —— 强制关闭 > 覆盖 > 灰度 > 默认值。"""

from feature_flags import EvaluationContext, parse_flag_set

NOW = 1_800_000_000.0
FUTURE = NOW + 3600


def make(**flag):
    return parse_flag_set({"flags": {"f": flag}}, now=NOW)


def test_默认值兜底_无规则时返回default():
    fs = make(default=True)
    assert EvaluationContext({"user_id": "u1"}).is_enabled(fs, "f") is True
    fs = make(default=False)
    assert EvaluationContext({"user_id": "u1"}).is_enabled(fs, "f") is False


def test_灰度优先于默认值_命中灰度时覆盖default():
    fs = make(default=False, rollouts=[{"dimension": "user_id", "percentage": 100}])
    assert EvaluationContext({"user_id": "u1"}).is_enabled(fs, "f") is True


def test_覆盖优先于灰度_命中覆盖时忽略灰度结果():
    # 灰度 100% 会开，但覆盖为 False，覆盖赢
    fs = make(
        default=False,
        rollouts=[{"dimension": "user_id", "percentage": 100}],
        overrides=[{"dimension": "user_id", "match": "u1", "value": False}],
    )
    assert EvaluationContext({"user_id": "u1"}).is_enabled(fs, "f") is False
    # 未命中覆盖的用户仍走灰度
    assert EvaluationContext({"user_id": "u2"}).is_enabled(fs, "f") is True


def test_强制关闭最高优先级_任何覆盖都不能打开():
    fs = make(
        default=True,
        force_off=True,
        rollouts=[{"dimension": "user_id", "percentage": 100}],
        overrides=[{"dimension": "user_id", "match": "u1", "value": True}],
    )
    assert EvaluationContext({"user_id": "u1"}).is_enabled(fs, "f") is False


def test_未定义开关返回False():
    fs = make(default=True)
    assert EvaluationContext({}).is_enabled(fs, "not-exist") is False
