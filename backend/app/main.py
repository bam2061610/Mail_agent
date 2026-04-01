from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.config import settings

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(title=settings.app_name, lifespan=lifespan)

@app.get("/health")
def health():
    return {"status": "ok", "environment": settings.environment}
