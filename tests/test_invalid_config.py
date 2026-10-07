"""场景四：非法配置 —— 拒绝并给出可区分的原因。"""

import pytest

from feature_flags import FlagConfigError, InvalidReason, parse_flag_set

NOW = 1_800_000_000.0


def expect(reason, raw):
    with pytest.raises(FlagConfigError) as exc_info:
        parse_flag_set(raw, now=NOW)
    assert exc_info.value.reason == reason
    return exc_info.value


def test_顶层不是对象():
    expect(InvalidReason.NOT_A_MAPPING, ["not", "a", "dict"])


def test_缺少default():
    e = expect(InvalidReason.MISSING_DEFAULT, {"flags": {"f": {}}})
    assert "$.flags.f" in e.path


def test_default类型非法():
    expect(InvalidReason.BAD_DEFAULT_TYPE, {"flags": {"f": {"default": "true"}}})


def test_百分比越界():
    expect(InvalidReason.BAD_ROLLOUT_PERCENTAGE,
           {"flags": {"f": {"default": False, "rollouts": [{"dimension": "u", "percentage": 101}]}}})
    expect(InvalidReason.BAD_ROLLOUT_PERCENTAGE,
           {"flags": {"f": {"default": False, "rollouts": [{"dimension": "u", "percentage": -1}]}}})


def test_百分比类型非法_bool不算数字():
    expect(InvalidReason.BAD_ROLLOUT_PERCENTAGE,
           {"flags": {"f": {"default": False, "rollouts": [{"dimension": "u", "percentage": True}]}}})


def test_灰度维度非法():
    expect(InvalidReason.BAD_ROLLOUT_DIMENSION,
           {"flags": {"f": {"default": False, "rollouts": [{"dimension": "", "percentage": 50}]}}})


def test_未知字段被拒绝():
    expect(InvalidReason.UNKNOWN_FLAG_FIELD,
           {"flags": {"f": {"default": True, "typo_field": 1}}})


def test_覆盖结构非法():
    expect(InvalidReason.BAD_OVERRIDE,
           {"flags": {"f": {"default": True, "overrides": [{"dimension": "u", "match": "x"}]}}})


def test_过期覆盖被拒绝而不是静默忽略():
    e = expect(InvalidReason.EXPIRED_OVERRIDE,
               {"flags": {"f": {"default": True, "overrides": [
                   {"dimension": "u", "match": "x", "value": True, "expires_at": NOW - 1}]}}})
    assert "过期" in str(e)


def test_未过期覆盖正常接受():
    fs = parse_flag_set(
        {"flags": {"f": {"default": False, "overrides": [
            {"dimension": "u", "match": "x", "value": True, "expires_at": NOW + 100}]}}},
        now=NOW,
    )
    assert fs.flags["f"].overrides[0].value is True
