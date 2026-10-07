"""FastAPI 路由：开关求值与配置热更新。"""

from __future__ import annotations

from fastapi import APIRouter

from .store import FlagStore


def build_router(store: FlagStore) -> APIRouter:
    """构建挂载到应用的路由。"""
    router = APIRouter(prefix="/flags", tags=["feature-flags"])

    @router.post("/evaluate/{name}")
    def evaluate(name: str, dimensions: dict[str, str] = {}):
        raise NotImplementedError

    @router.post("/reload")
    def reload(config: dict):
        raise NotImplementedError

    @router.get("/version")
    def version():
        raise NotImplementedError

    return router
