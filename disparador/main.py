from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.services.rabbitmq_service import disparador_rmq
from app.services.redis_service import disparador_redis
from app.services.basile_client import basile_client
from app.api import webhook, dashboard

@asynccontextmanager
async def lifespan(app: FastAPI):
    await disparador_rmq.connect()
    await disparador_redis.connect()
    yield
    await disparador_rmq.disconnect()
    await disparador_redis.disconnect()
    await basile_client.close()

app = FastAPI(title="Basile Disparador", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(webhook.router, prefix="/webhook", tags=["Webhook"])
app.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])

@app.get("/")
async def root():
    return {"service": "basile-disparador", "status": "running"}
