"""pytest 钩子：在测试总结中输出业务场景覆盖报告。

每个测试类的 docstring 视为一个业务场景，每个用例的 docstring 视为该场景下的具体用例，
运行结束后按 “场景 / 用例 / 结果” 汇总打印，便于审查覆盖了哪些场景。
"""

from __future__ import annotations

_CASES: list[tuple[str, str, str]] = []
_DOCS: dict[str, tuple[str, str]] = {}


def pytest_collection_modifyitems(items):
    for item in items:
        scenario = (item.cls.__doc__ if item.cls and item.cls.__doc__ else "未分组场景").strip()
        case = (item.obj.__doc__ or item.name).strip().splitlines()[0]
        _DOCS[item.nodeid] = (scenario, case)


def pytest_runtest_logreport(report):
    if report.when != "call":
        return
    scenario, case = _DOCS.get(report.nodeid, ("未分组场景", report.nodeid))
    outcome = {"passed": "通过", "failed": "失败", "skipped": "跳过"}.get(report.outcome, report.outcome)
    _CASES.append((scenario, case, outcome))


def pytest_terminal_summary(terminalreporter):
    terminalreporter.write_sep("=", "业务场景覆盖报告")
    current = None
    for scenario, case, outcome in _CASES:
        if scenario != current:
            terminalreporter.write_line(f"\n■ {scenario}")
            current = scenario
        mark = {"通过": "PASS", "失败": "FAIL", "跳过": "SKIP"}.get(outcome, outcome)
        terminalreporter.write_line(f"    [{mark}] {case}")
