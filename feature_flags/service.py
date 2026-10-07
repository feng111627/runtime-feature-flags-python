"""FastAPI 路由：开关求值与配置热更新。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .errors import FlagConfigError
from .evaluation import EvalContext
from .store import FlagStore


class EvaluateRequest(BaseModel):
    dimensions: dict[str, str] = Field(default_factory=dict)


class EvaluateResponse(BaseModel):
    flag: str
    enabled: bool
    source: str


class ReloadResponse(BaseModel):
    version: int


def build_router(store: FlagStore) -> APIRouter:
    """构建挂载到应用的路由。"""
    router = APIRouter(prefix="/flags", tags=["feature-flags"])

    @router.post("/evaluate/{name}", response_model=EvaluateResponse)
    def evaluate(name: str, body: EvaluateRequest | None = None):
        dimensions = body.dimensions if body else {}
        ctx = EvalContext(dimensions=dimensions)
        result = store.current().evaluate(name, ctx)
        return EvaluateResponse(flag=result.flag, enabled=result.enabled, source=result.source)

    @router.post("/reload", response_model=ReloadResponse)
    def reload(config: dict):
        try:
            version = store.update(config)
        except FlagConfigError as exc:
            # 整体拒绝：返回可区分的原因码，服务保持旧配置。
            raise HTTPException(
                status_code=422,
                detail={"reason": exc.reason.value, "flag": exc.flag, "message": str(exc)},
            ) from exc
        return ReloadResponse(version=version)

    @router.get("/version")
    def version():
        return {"version": store.version}

    return router
