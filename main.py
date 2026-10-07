"""运行时特性开关服务。

- GET  /                      健康检查
- GET  /flags                 查看当前生效的配置快照与版本
- POST /flags/reload          热更新配置（整体生效或整体保持旧值）
- POST /flags/evaluate        对一次请求求值一组开关（请求内结果一致）
"""

from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from feature_flags import EvaluationContext, FlagConfigError, FlagStore

app = FastAPI(title="runtime-feature-flags")
store = FlagStore()


class EvaluateRequest(BaseModel):
    attributes: dict[str, str] = {}
    flags: list[str]


@app.get("/")
def read_root():
    return {"Hello": "World"}


@app.get("/flags")
def get_flags():
    snap = store.snapshot()
    return {
        "version": snap.version,
        "flags": {
            name: {
                "default": f.default,
                "force_off": f.force_off,
                "rollouts": [vars(r) for r in f.rollouts],
                "overrides": [vars(o) for o in f.overrides],
            }
            for name, f in snap.flags.items()
        },
    }


@app.post("/flags/reload")
def reload_flags(config: dict[str, Any]):
    try:
        snap = store.update(config)
    except FlagConfigError as e:
        # 校验失败：旧配置原样保留，返回可区分的原因
        raise HTTPException(
            status_code=422,
            detail={"reason": e.reason.value, "path": e.path, "message": str(e)},
        )
    return {"version": snap.version, "flag_count": len(snap.flags)}


@app.post("/flags/evaluate")
def evaluate_flags(req: EvaluateRequest):
    snap = store.snapshot()  # 整个请求使用同一快照，不受中途热更新影响
    ctx = EvaluationContext(req.attributes)
    return {
        "version": snap.version,
        "results": {name: ctx.is_enabled(snap, name) for name in req.flags},
    }


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=0)
