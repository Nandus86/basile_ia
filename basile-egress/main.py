"""
basile-egress - Result Output Service
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.database import engine, Base
from app.redis_client import redis_client
from app.api import result, status


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await redis_client.connect()
    
    yield
    
    await redis_client.disconnect()
    await engine.dispose()


app = FastAPI(
    title="basile-egress",
    description="Result Output Service - Sends results to external webhooks",
    version="1.0.0",
    lifespan=lifespan,
    root_path="/egress-api"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(result.router, prefix="/result", tags=["Result"])
app.include_router(status.router, prefix="/status", tags=["Status"])


@app.get("/")
async def root():
    return {"service": "basile-egress", "status": "running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}