# 运行时特性开关服务

在 FastAPI 服务内提供运行时特性开关：支持开关求值、百分比/维度灰度、
不重启热更新、按维度覆盖与强制关闭。

## 配置结构

通过 `POST /flags/reload` 提交完整配置（JSON）：

```json
{
  "flags": {
    "new-checkout": {
      "default": false,
      "force_off": false,
      "rollouts": [
        {"dimension": "user_id", "percentage": 25}
      ],
      "overrides": [
        {"dimension": "user_id", "match": "u-123", "value": true,
         "expires_at": 1890000000}
      ]
    }
  }
}
```

| 字段 | 说明 |
| --- | --- |
| `default` | 必填，bool。所有规则都不命中时的兜底值。 |
| `force_off` | bool，默认 false。为 true 时开关被强制关闭。 |
| `rollouts` | 灰度规则数组：`dimension`（用于哈希的请求维度）+ `percentage`（0~100）。 |
| `overrides` | 覆盖数组：`dimension` + `match`（精确匹配）+ `value`，可选 `expires_at`（epoch 秒）。 |

任何一处非法都会导致**整份配置被拒绝**（HTTP 422），响应体带可区分的原因码
（`reason`）与出错路径（`path`），旧配置原样保留。原因码见
`feature_flags/errors.py` 的 `InvalidReason`，如 `bad_rollout_percentage`、
`expired_override`、`missing_default` 等。过期覆盖会被**拒绝**而不是静默忽略。

## 优先级规则

求值优先级从高到低：

1. **force_off**：强制关闭，任何覆盖都不能让开关返回开启；
2. **overrides**：按声明顺序取第一个命中且未过期的覆盖；
3. **rollouts**：任一灰度规则命中即开启；请求缺少对应维度时不命中；
4. **default**：兜底默认值。

未定义的开关一律返回 `false`（安全默认）。

## 灰度口径

- 桶位计算：`bucket = sha256("开关名:维度值")` 取前 12 位十六进制映射到 `[0, 100)`，
  命中条件为 `bucket < percentage`。
- 同一输入永远落在同一桶位，与进程、重启无关；不同开关的分布相互独立。
- 边界：`percentage = 0` 时任何人都不命中；`percentage = 100` 时（具备该维度的）
  任何人都命中。越界或非数字的百分比在校验阶段被拒绝。
- **请求内一致性**：同一 `EvaluationContext`（对应一次请求生命周期）内同一开关
  只真实求值一次并缓存，期间即使发生热更新，本请求的结果也不变。

## 热更新的原子性

- 配置以不可变快照（`FlagSet`）整体存放，读路径无锁；
- 更新时先完整解析校验，全部通过后在锁内一次性替换引用——
  **要么整体生效，要么整体保持旧值**，不存在半新半旧；
- 进行中的求值持有旧快照引用，不受替换影响，并发读写不会撕裂或串值；
- 每次成功更新 `version` 递增，可通过 `GET /flags` 观察当前版本。

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/flags` | 查看当前生效的配置快照与版本 |
| POST | `/flags/reload` | 热更新配置；非法时 422 且保持旧值 |
| POST | `/flags/evaluate` | 入参 `{"attributes": {...}, "flags": [...]}`，返回各开关结果 |

## 验证方法

运行测试：

```bash
uv run pytest -v
```

测试日志会列出覆盖的业务场景及每个场景下的用例与结果：

- 场景一：优先级（强制关闭 > 覆盖 > 灰度 > 默认值）
- 场景二：灰度放量（0/100 边界、桶位稳定性、放量比例、请求内一致性）
- 场景三：并发热更新（原子替换、并发读写不撕裂、非法更新不影响合法更新）
- 场景四：非法配置（各类非法输入被拒绝且原因可区分）

手动验证服务：

```bash
uv run python main.py   # 启动服务
curl -X POST localhost:8000/flags/reload -H 'Content-Type: application/json' \
  -d '{"flags": {"f": {"default": true}}}'
curl -X POST localhost:8000/flags/evaluate -H 'Content-Type: application/json' \
  -d '{"attributes": {"user_id": "u1"}, "flags": ["f"]}'
```
