"""特性开关测试：优先级 / 灰度边界 / 并发热更新 / 非法配置。"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from feature_flags import (
    EvalContext,
    Evaluator,
    FlagConfigError,
    FlagStore,
    InvalidReason,
    parse_flag_set,
)

NOW = "2026-10-07T00:00:00+00:00"
FUTURE = "2099-01-01T00:00:00+00:00"


def make_evaluator(flag_cfg: dict) -> Evaluator:
    return Evaluator(parse_flag_set({"flags": flag_cfg}))


class TestPriority:
    """场景一：优先级——强制关闭 > 覆盖 > 维度规则 > 百分比灰度 > 默认值"""

    def test_force_off_beats_override(self):
        """被强制关闭的开关，即使有开启覆盖也返回关闭"""
        ev = make_evaluator({
            "f": {
                "default": True,
                "force_off": True,
                "overrides": [{"dimension": "user_id", "values": ["u1"], "enabled": True}],
            }
        })
        r = ev.evaluate("f", EvalContext({"user_id": "u1"}))
        assert r.enabled is False and r.source == "force_off"

    def test_override_beats_rule_and_rollout(self):
        """命中覆盖时，忽略维度规则与灰度"""
        ev = make_evaluator({
            "f": {
                "default": False,
                "rollout": {"percentage": 100},
                "rules": [{"dimension": "region", "values": ["cn"], "enabled": True}],
                "overrides": [{"dimension": "user_id", "values": ["u1"], "enabled": False,
                               "expires_at": FUTURE}],
            }
        })
        r = ev.evaluate("f", EvalContext({"user_id": "u1", "region": "cn"}))
        assert r.enabled is False and r.source == "override"

    def test_rule_beats_rollout_and_default(self):
        """命中维度规则时，忽略灰度与默认值"""
        ev = make_evaluator({
            "f": {
                "default": False,
                "rollout": {"percentage": 0},
                "rules": [{"dimension": "region", "values": ["cn"], "enabled": True}],
            }
        })
        r = ev.evaluate("f", EvalContext({"region": "cn"}))
        assert r.enabled is True and r.source == "rule"

    def test_rollout_beats_default(self):
        """灰度命中时覆盖默认值"""
        ev = make_evaluator({"f": {"default": False, "rollout": {"percentage": 100}}})
        r = ev.evaluate("f", EvalContext({"user_id": "anyone"}))
        assert r.enabled is True and r.source == "rollout"

    def test_fallback_to_default(self):
        """无任何规则命中时回落默认值"""
        ev = make_evaluator({"f": {"default": True, "rollout": {"percentage": 0}}})
        r = ev.evaluate("f", EvalContext({"user_id": "u9"}))
        assert r.enabled is True and r.source == "default"

    def test_unknown_flag_is_closed(self):
        """未配置的开关一律返回关闭且来源可解释"""
        ev = make_evaluator({"f": {"default": True}})
        r = ev.evaluate("nope", EvalContext({}))
        assert r.enabled is False and r.source == "unknown_flag"


class TestRolloutBoundary:
    """场景二：灰度边界——0%/100% 行为明确，分桶稳定，请求内一致"""

    def test_zero_percent_never_on(self):
        """percentage=0 时任何用户都不命中灰度"""
        ev = make_evaluator({"f": {"default": False, "rollout": {"percentage": 0}}})
        for i in range(200):
            r = ev.evaluate("f", EvalContext({"user_id": f"u-{i}"}))
            assert r.enabled is False and r.source == "default"

    def test_hundred_percent_always_on(self):
        """percentage=100 时所有用户都命中灰度"""
        ev = make_evaluator({"f": {"default": False, "rollout": {"percentage": 100}}})
        for i in range(200):
            r = ev.evaluate("f", EvalContext({"user_id": f"u-{i}"}))
            assert r.enabled is True and r.source == "rollout"

    def test_bucket_is_deterministic_across_instances(self):
        """同一用户跨求值器实例分桶结果一致（重启/多副本口径相同）"""
        cfg = {"f": {"default": False, "rollout": {"percentage": 50}}}
        results_per_instance = []
        for _ in range(3):
            ev = make_evaluator(cfg)
            results_per_instance.append(
                [ev.evaluate("f", EvalContext({"user_id": f"u-{i}"})).enabled for i in range(100)]
            )
        assert results_per_instance[0] == results_per_instance[1] == results_per_instance[2]

    def test_rollout_is_monotonic_in_percentage(self):
        """放量单调：p% 命中的用户集合是 (p+1)% 的子集，放量不回退"""
        cfg = lambda p: {"f": {"default": False, "rollout": {"percentage": p}}}
        users = [f"u-{i}" for i in range(300)]
        prev = set()
        for p in range(0, 101, 5):
            ev = make_evaluator(cfg(p))
            hit = {u for u in users if ev.evaluate("f", EvalContext({"user_id": u})).enabled}
            assert prev <= hit
            prev = hit

    def test_same_request_ctx_is_consistent(self):
        """同一请求上下文内多次求值结果一致"""
        ev = make_evaluator({"f": {"default": False, "rollout": {"percentage": 50}}})
        ctx = EvalContext({"user_id": "u-42"})
        first = ev.evaluate("f", ctx)
        for _ in range(10):
            assert ev.evaluate("f", ctx).enabled == first.enabled

    def test_ctx_memo_survives_hot_update(self):
        """热更新后，同一请求上下文仍返回更新前的结果（请求内不串值）"""
        store = FlagStore(parse_flag_set({"flags": {"f": {"default": False}}}))
        ctx = EvalContext({})
        assert store.current().evaluate("f", ctx).enabled is False
        store.update({"flags": {"f": {"default": True}}})
        assert store.current().evaluate("f", ctx).enabled is False  # memo 保住请求内一致性
        assert store.current().evaluate("f", EvalContext({})).enabled is True  # 新请求用新配置


class TestConcurrentHotReload:
    """场景三：并发热更新——整体生效或整体保持，无撕裂、不崩溃"""

    def test_concurrent_read_write_no_tearing(self):
        """并发求值与更新：每次求值只得到完整旧值或完整新值"""
        store = FlagStore(parse_flag_set({"flags": {
            "a": {"default": False}, "b": {"default": True},
        }}))
        new_cfg = {"flags": {"a": {"default": True}, "b": {"default": False}}}
        errors: list[Exception] = []
        observations: list[tuple[bool, bool]] = []
        stop = threading.Event()

        def reader():
            try:
                while not stop.is_set():
                    ev = store.current()
                    ctx = EvalContext({})
                    observations.append(
                        (ev.evaluate("a", ctx).enabled, ev.evaluate("b", ctx).enabled)
                    )
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        def writer():
            for _ in range(50):
                store.update(new_cfg)
            stop.set()

        readers = [threading.Thread(target=reader) for _ in range(8)]
        for t in readers:
            t.start()
        writer()
        for t in readers:
            t.join()

        assert not errors
        # 合法状态只有两种：旧 (False, True) 或新 (True, False)；
        # 出现 (False, False)/(True, True) 即为半新半旧的撕裂。
        assert set(observations) <= {(False, True), (True, False)}
        # 更新最终生效：结束后读到的必须是新配置。
        ev = store.current()
        ctx = EvalContext({})
        assert (ev.evaluate("a", ctx).enabled, ev.evaluate("b", ctx).enabled) == (True, False)

    def test_corrupt_update_keeps_old_config_under_concurrency(self):
        """更新到一半发现损坏：整体拒绝，并发读不崩且版本不变"""
        store = FlagStore(parse_flag_set({"flags": {"f": {"default": True}}}))
        corrupt_docs = [
            {"flags": {"f": {"default": "oops"}}},
            {"flags": {"f": {"rollout": {"percentage": 101}}}},
            {"flags": "not-a-dict"},
            {"flags": None},
        ]
        errors: list[Exception] = []
        stop = threading.Event()

        def reader():
            try:
                while not stop.is_set():
                    r = store.current().evaluate("f", EvalContext({}))
                    assert r.enabled is True and r.source == "default"
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        def writer():
            for _ in range(30):
                for doc in corrupt_docs:
                    with pytest.raises(FlagConfigError):
                        store.update(doc)
            stop.set()

        with ThreadPoolExecutor(max_workers=9) as pool:
            for _ in range(8):
                pool.submit(reader)
            pool.submit(writer)
        assert not errors
        assert store.version == 0  # 一次都没更新成功，旧配置完整保留

    def test_version_increases_monotonically(self):
        """每次合法更新版本号严格递增"""
        store = FlagStore()
        assert store.update({"flags": {"f": {"default": True}}}) == 1
        assert store.update({"flags": {"f": {"default": False}}}) == 2
        assert store.version == 2


class TestInvalidConfig:
    """场景四：非法配置——按原因码拒绝，过期/非法覆盖不静默忽略"""

    @pytest.mark.parametrize("percentage", [-1, 101, 1.5, "50", True])
    def test_bad_percentage_rejected(self, percentage):
        """百分比越界或类型错误 -> bad_percentage"""
        with pytest.raises(FlagConfigError) as ei:
            parse_flag_set({"flags": {"f": {"default": True, "rollout": {"percentage": percentage}}}})
        assert ei.value.reason is InvalidReason.BAD_PERCENTAGE

    def test_missing_default_rejected(self):
        """缺少默认值 -> missing_default"""
        with pytest.raises(FlagConfigError) as ei:
            parse_flag_set({"flags": {"f": {"rollout": {"percentage": 10}}}})
        assert ei.value.reason is InvalidReason.MISSING_DEFAULT

    def test_expired_override_rejected_not_ignored(self):
        """过期覆盖必须被拒绝，而不是静默忽略"""
        with pytest.raises(FlagConfigError) as ei:
            parse_flag_set({"flags": {"f": {
                "default": False,
                "overrides": [{"dimension": "user_id", "values": ["u1"], "enabled": True,
                               "expires_at": "2020-01-01T00:00:00+00:00"}],
            }}})
        assert ei.value.reason is InvalidReason.EXPIRED_OVERRIDE

    @pytest.mark.parametrize("bad_time", ["not-a-time", "2026-13-01", "2099-01-01 10:00"])
    def test_bad_override_time_rejected(self, bad_time):
        """覆盖时间格式非法或缺时区 -> bad_override_time"""
        with pytest.raises(FlagConfigError) as ei:
            parse_flag_set({"flags": {"f": {
                "default": False,
                "overrides": [{"dimension": "user_id", "values": ["u1"], "enabled": True,
                               "expires_at": bad_time}],
            }}})
        assert ei.value.reason is InvalidReason.BAD_OVERRIDE_TIME

    def test_empty_dimension_rejected(self):
        """维度名为空 -> empty_dimension"""
        with pytest.raises(FlagConfigError) as ei:
            parse_flag_set({"flags": {"f": {"default": True, "rollout": {"percentage": 10, "dimension": ""}}}})
        assert ei.value.reason is InvalidReason.EMPTY_DIMENSION

    def test_empty_rule_values_rejected(self):
        """规则取值列表为空 -> empty_rule_values"""
        with pytest.raises(FlagConfigError) as ei:
            parse_flag_set({"flags": {"f": {
                "default": True,
                "rules": [{"dimension": "region", "values": [], "enabled": True}],
            }}})
        assert ei.value.reason is InvalidReason.EMPTY_RULE_VALUES

    def test_malformed_document_rejected(self):
        """文档结构损坏（非对象/字段类型错误）-> malformed_document"""
        for bad in ["garbage", 42, {"flags": ["not", "a", "dict"]}, {"flags": {"f": "x"}}]:
            with pytest.raises(FlagConfigError) as ei:
                parse_flag_set(bad)
            assert ei.value.reason is InvalidReason.MALFORMED_DOCUMENT

    def test_valid_future_override_accepted(self):
        """未过期的合法覆盖正常加载并生效"""
        ev = make_evaluator({"f": {
            "default": False,
            "overrides": [{"dimension": "user_id", "values": ["u1"], "enabled": True,
                           "expires_at": FUTURE}],
        }})
        r = ev.evaluate("f", EvalContext({"user_id": "u1"}))
        assert r.enabled is True and r.source == "override"

    def test_rejected_update_leaves_store_untouched(self):
        """非法更新整体拒绝后，store 中的旧配置与版本号都不变"""
        store = FlagStore(parse_flag_set({"flags": {"f": {"default": True}}}))
        before = store.current()
        with pytest.raises(FlagConfigError):
            store.update({"flags": {"f": {"default": True, "rollout": {"percentage": 999}}}})
        assert store.version == 0
        assert store.current() is before
