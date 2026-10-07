# 运行时特性开关（Runtime Feature Flags）

在不重启服务的前提下更新开关配置，支持灰度放量、按维度覆盖与强制关闭，
保证求值结果稳定、可解释，热更新原子生效。

## 配置结构

一份配置是一个 JSON 对象，通过 `POST /flags/reload` 整体提交：

```json
{
  "flags": {
    "new_checkout": {
      "default": false,
      "force_off": false,
      "rollout": { "percentage": 25, "dimension": "user_id" },
      "rules": [
        { "dimension": "region", "values": ["cn-north"], "enabled": true }
      ],
      "overrides": [
        { "dimension": "user_id", "values": ["u-1"], "enabled": true,
          "expires_at": "2026-12-31T23:59:59+00:00" }
      ]
    }
  }
}
```

| 字段 | 说明 |
| --- | --- |
| `default` | 必填，布尔。所有规则都不命中时的兜底值。 |
| `force_off` | 可选，默认 `false`。为 `true` 时开关强制关闭，任何覆盖都不能打开。 |
| `rollout.percentage` | 0–100 的整数。按 `dimension` 的取值哈希分桶，桶号小于百分比即命中。 |
| `rollout.dimension` | 分桶维度，默认 `user_id`。 |
| `rules` | 维度名单规则：请求维度值落在 `values` 中即返回 `enabled`。 |
| `overrides` | 定向覆盖，粒度最细；`expires_at` 为带时区的 ISO8601 时间，可省略。 |

## 优先级规则

求值按以下顺序短路返回，结果中的 `source` 字段标明命中来源，保证可解释：

```
force_off  >  override  >  rules（维度名单）  >  rollout（百分比灰度）  >  default
```

- **强制关闭最高**：`force_off: true` 时直接返回关闭，覆盖、规则、灰度全部不生效。
- **覆盖优先于灰度**：`overrides` 命中即返回，不再看 `rules` 和 `rollout`。
- **未配置的开关**：返回关闭，`source = "unknown_flag"`。

## 灰度口径

- 分桶键为 `"{开关名}:{维度值}"`，取 SHA-256 前 8 字节对 100 取模，落在 `[0, 100)`。
  同一输入在任何进程、任何机器上桶号一致（重启、多副本口径相同）。
- `bucket < percentage` 即命中。因此：
  - `percentage = 0`：永不命中（等价于灰度关闭，回落默认值）；
  - `percentage = 100`：恒命中（等价于全量开启）。
- 放量单调：百分比从 p 调到 p+1 时，已命中用户不会回退。
- 请求维度缺失时，对应规则/灰度视为不命中，继续向下回落。

## 一致性与热更新

- **请求内一致**：同一 `EvalContext` 对同一开关的多次求值被记忆化，
  即使求值间隙发生热更新，本请求内结果也不变、不串值。
- **原子更新**：新配置先完整校验再整体替换快照引用；读到损坏内容或非法配置时
  整体拒绝（HTTP 422 + 原因码），服务保持旧配置，绝不处于半新半旧状态。
- **并发安全**：配置快照不可变，读侧无锁；并发求值与更新不会撕裂。

## 非法配置的原因码

| reason | 含义 |
| --- | --- |
| `malformed_document` | 文档结构损坏（非对象、字段类型错误） |
| `missing_default` | 开关缺少 `default` |
| `bad_percentage` | 百分比不是 `[0,100]` 的整数 |
| `empty_dimension` | 维度名为空 |
| `empty_rule_values` | 规则/覆盖的取值列表为空或含非字符串 |
| `bad_override_time` | 覆盖时间格式非法或缺时区 |
| `expired_override` | 覆盖已过期——拒绝加载，而非静默忽略 |
| `duplicate_flag` | 开关名重复 |

## HTTP 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `POST` | `/flags/evaluate/{name}` | 求值，body `{"dimensions": {"user_id": "u-1"}}`，返回 `enabled` 与 `source` |
| `POST` | `/flags/reload` | 热更新，body 为完整配置；非法时 422 且旧配置不变 |
| `GET` | `/flags/version` | 当前配置版本号（每次成功更新递增） |

## 验证方法

```bash
uv run pytest -q
```

测试覆盖四类业务场景，运行结束会输出“业务场景覆盖报告”，
逐条列出每个场景下的用例与通过情况：

1. **优先级**：强制关闭压过覆盖、覆盖压过规则与灰度、规则压过默认值等 6 例；
2. **灰度边界**：0%/100% 边界、跨实例分桶一致、放量单调、请求内一致等 6 例；
3. **并发热更新**：多线程读写无撕裂、损坏更新整体拒绝且并发读不崩、版本号递增；
4. **非法配置**：各类非法输入按原因码拒绝、过期覆盖不静默忽略、拒绝后旧配置不变。

手动验证热更新：

```bash
uv run python main.py &
curl -X POST localhost:8000/flags/reload -H 'Content-Type: application/json' \
  -d '{"flags": {"new_checkout": {"default": false, "rollout": {"percentage": 50}}}}'
curl -X POST localhost:8000/flags/evaluate/new_checkout \
  -H 'Content-Type: application/json' -d '{"dimensions": {"user_id": "u-1"}}'
```
