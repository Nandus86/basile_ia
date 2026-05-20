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

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Basile Disparador", lifespan=lifespan)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    try:
        body = await request.body()
        body_str = body.decode('utf-8', errors='replace')
    except Exception:
        body_str = "Could not decode body"
        
    logger.error(f"❌ [Disparador] Payload Validation Error at {request.url}")
    logger.error(f"❌ [Disparador] Erros: {exc.errors()}")
    logger.error(f"❌ [Disparador] Corpo recebido: {body_str}")
    
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder({"detail": exc.errors(), "message": "Falha na validação do payload"}),
    )
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
