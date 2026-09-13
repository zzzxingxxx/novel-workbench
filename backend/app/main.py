from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(title="Novel Workbench API", version="0.1.0")
app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok"}
