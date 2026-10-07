import uvicorn
from fastapi import FastAPI

from feature_flags import FlagStore
from feature_flags.service import build_router

flag_store = FlagStore()

app = FastAPI(title="runtime-feature-flags")
app.include_router(build_router(flag_store))


@app.get("/")
def read_root():
    return {"Hello": "World"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=0)
