"""场景三：并发热更新 —— 原子替换、不撕裂、失败保持旧值。"""

import threading

from feature_flags import EvaluationContext, FlagConfigError, FlagStore

GOOD_A = {"flags": {"f": {"default": True}}}
GOOD_B = {"flags": {"f": {"default": False}}}
BROKEN = {"flags": {"f": {"default": "not-a-bool"}}}


def test_非法更新不生效_旧配置原样保留():
    store = FlagStore()
    store.update(GOOD_A)
    before = store.snapshot()
    try:
        store.update(BROKEN)
        assert False, "应当抛出 FlagConfigError"
    except FlagConfigError:
        pass
    assert store.snapshot() is before  # 同一个快照对象，未被污染


def test_更新整体生效_版本递增():
    store = FlagStore()
    s1 = store.update(GOOD_A)
    s2 = store.update(GOOD_B)
    assert s2.version == s1.version + 1
    assert store.snapshot().flags["f"].default is False


def test_并发读写不撕裂_求值结果只能是某个完整版本():
    """多线程并发更新与求值：每次求值结果必须整体来自 A 或 B，
    不允许出现崩溃或读到非法中间态。"""
    store = FlagStore()
    store.update(GOOD_A)
    errors: list[Exception] = []
    stop = threading.Event()

    def writer():
        for i in range(500):
            store.update(GOOD_A if i % 2 == 0 else GOOD_B)

    def reader():
        try:
            while not stop.is_set():
                snap = store.snapshot()
                ctx = EvaluationContext({})
                result = ctx.is_enabled(snap, "f")
                assert result is snap.flags["f"].default  # 与快照自洽
                assert snap.version >= 1
        except Exception as e:  # pragma: no cover
            errors.append(e)

    readers = [threading.Thread(target=reader) for _ in range(8)]
    for t in readers:
        t.start()
    for _ in range(4):
        writer()
    stop.set()
    for t in readers:
        t.join()
    assert errors == []


def test_并发更新混杂非法配置_合法更新不受影响():
    store = FlagStore()
    store.update(GOOD_A)
    errors: list[Exception] = []

    def mixed_writer():
        for i in range(200):
            try:
                store.update(GOOD_B if i % 2 else BROKEN)
            except FlagConfigError:
                pass  # 非法配置被拒绝是预期行为
            except Exception as e:  # pragma: no cover
                errors.append(e)

    threads = [threading.Thread(target=mixed_writer) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    # 最终状态是某个完整合法的快照
    snap = store.snapshot()
    assert snap.flags["f"].default in (True, False)
