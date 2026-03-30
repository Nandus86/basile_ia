"""
Basile_IA_Orch - AI Agent Orchestrator
Main FastAPI Application
"""
import logging
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# ── Logging config ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Garante que os módulos da app emitem INFO mesmo com Uvicorn rodando
for _mod in ("app.services.mcp_tools", "app.orchestrator.agent_factory",
             "app.orchestrator.agent_orchestrator", "app.orchestrator.supervisor",
             "app.worker.tasks"):
    logging.getLogger(_mod).setLevel(logging.INFO)
# ─────────────────────────────────────────────────────────────────────────────

from app.database import engine, Base
from app.api import webhook, agents, mcp, mcp_groups, database, health, documents, emotional_profiles, models, skills, information_bases, vfs, memory, workflows, skill_groups, agent_groups, agent_control
from app.api.endpoints import ai_providers, webhooks_config, tracking
from app.weaviate_client import weaviate_client
from app.redis_client import redis_client
from app.services.rabbitmq_service import rabbitmq_client
from app.worker.queue_consumer import start_rabbitmq_consumer


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup: Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    # Connect to RabbitMQ for publishing messages
    await rabbitmq_client.connect()
    
    yield
    # Shutdown: cleanup all connections
    try:
        from app.worker.queue_client import close_arq_pool
        await close_arq_pool()
    except Exception:
        pass
    weaviate_client.disconnect()
    await redis_client.disconnect()
    await rabbitmq_client.disconnect()
    await engine.dispose()


app = FastAPI(
    title="Basile_IA_Orch",
    description="AI Agent Orchestrator with LangGraph",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://basile_ia.nandus.com.br",
        "https://basile_ia.nandus.com.br",
        "http://basile_ia_b.nandus.com.br",
        "https://basile_ia_b.nandus.com.br",
        "http://localhost:3009",
        "http://localhost:8009",
        "*"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(health.router, tags=["Health"])
app.include_router(webhook.router, prefix="/webhook", tags=["Webhook"])
app.include_router(agents.router, prefix="/agents", tags=["Agents"])
app.include_router(mcp.router, prefix="/mcp", tags=["MCP"])
app.include_router(mcp_groups.router, prefix="/mcp-groups", tags=["MCP Groups"])
app.include_router(documents.router, prefix="/documents", tags=["Documents"])
app.include_router(emotional_profiles.router, prefix="/emotional-profiles", tags=["Emotional Profiles"])
app.include_router(skills.router, prefix="/skills", tags=["Skills"])
app.include_router(information_bases.router, prefix="/information-bases", tags=["Information Bases"])
app.include_router(database.router, prefix="/database", tags=["Database"])
app.include_router(models.router, tags=["Models"])
app.include_router(ai_providers.router, prefix="/ai-providers", tags=["AI Providers"])
app.include_router(webhooks_config.router, prefix="/webhooks-config", tags=["Webhook Configs"])
app.include_router(tracking.router, prefix="/tracking", tags=["Tracking"])
app.include_router(workflows.router, prefix="/workflows", tags=["Workflows"])
app.include_router(vfs.router, prefix="/vfs-knowledge-bases", tags=["VFS Knowledge Bases"])
app.include_router(memory.router, prefix="/memory", tags=["Memory Management"])
app.include_router(skill_groups.router, prefix="/skill-groups", tags=["Skill Groups"])
app.include_router(agent_groups.router, prefix="/agent-groups", tags=["Agent Groups"])
app.include_router(agent_control.router, prefix="/agent-control", tags=["Agent Control"])


@app.get("/")
async def root():
    return {
        "name": "Basile_IA_Orch",
        "version": "1.0.0",
        "status": "running"
    }
