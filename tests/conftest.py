"""让测试日志直接呈现：覆盖了哪些业务场景、每个场景的用例与结果。"""

import pytest

# 测试模块 -> 业务场景说明
SCENARIOS = {
    "test_priority": "场景一：优先级（强制关闭 > 覆盖 > 灰度 > 默认值）",
    "test_rollout": "场景二：灰度放量（0/100 边界、稳定性、请求内一致性）",
    "test_hot_reload": "场景三：并发热更新（原子替换、不撕裂、失败保持旧值）",
    "test_invalid_config": "场景四：非法配置（拒绝并给出可区分原因）",
}


def pytest_report_header(config):
    covered = "\n".join(f"  {v}" for v in SCENARIOS.values())
    return f"本次测试覆盖的业务场景：\n{covered}"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == "call":
        module = item.module.__name__.rsplit(".", 1)[-1]
        scenario = SCENARIOS.get(module, module)
        mark = "通过" if report.passed else ("失败" if report.failed else "跳过")
        print(f"\n[场景] {scenario}\n[用例] {item.name} -> {mark}")
