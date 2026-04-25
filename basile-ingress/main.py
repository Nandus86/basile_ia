"""
basile-ingress - Webhook Entry Service
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.database import engine, Base
from app.redis_client import redis_client
from app.api import pipelines, webhook


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await redis_client.connect()
    
    yield
    
    await redis_client.disconnect()
    await engine.dispose()


app = FastAPI(
    title="basile-ingress",
    description="Webhook Entry Service - Normalizes and queues incoming webhooks",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(pipelines.router, prefix="/pipelines", tags=["Pipelines"])
app.include_router(webhook.router, prefix="/webhook", tags=["Webhook"])


@app.get("/")
async def root():
    return {"service": "basile-ingress", "status": "running"}


@app.get("/health")
async def health():
    return {"status": "healthy"}