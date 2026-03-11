"""
Models API - Auto-discovery of available LLM models from multiple providers
"""
import httpx
import time
import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/models", tags=["models"])

# ─── Cache ───────────────────────────────────────────────────────────────────
_models_cache: Optional[List[Dict[str, Any]]] = None
_cache_timestamp: float = 0
CACHE_TTL_SECONDS = 300  # 5 minutes


# ─── Response Schema ─────────────────────────────────────────────────────────
class ModelInfo(BaseModel):
    id: str
    name: str
    provider: str  # "openai" | "openrouter"
    context_length: int = 0
    pricing: Optional[Dict[str, Any]] = None


class ModelsResponse(BaseModel):
    models: List[ModelInfo]
    total: int
    cached: bool = False


# ─── OpenAI models (well-known, stable list) ─────────────────────────────────
OPENAI_MODELS = [
    {"id": "gpt-4o", "name": "GPT-4o", "provider": "openai", "context_length": 128000},
    {"id": "gpt-4o-mini", "name": "GPT-4o Mini", "provider": "openai", "context_length": 128000},
    {"id": "gpt-4-turbo", "name": "GPT-4 Turbo", "provider": "openai", "context_length": 128000},
    {"id": "gpt-4", "name": "GPT-4", "provider": "openai", "context_length": 8192},
    {"id": "gpt-3.5-turbo", "name": "GPT-3.5 Turbo", "provider": "openai", "context_length": 16385},
    {"id": "o1", "name": "O1", "provider": "openai", "context_length": 200000},
    {"id": "o1-mini", "name": "O1 Mini", "provider": "openai", "context_length": 128000},
    {"id": "o3-mini", "name": "O3 Mini", "provider": "openai", "context_length": 200000},
]


async def fetch_openrouter_models() -> List[Dict[str, Any]]:
    """Fetch available models from OpenRouter API — returns ALL models, no filtering"""
    if not settings.OPENROUTER_API_KEY:
        return []
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "https://openrouter.ai/api/v1/models",
                headers={
                    "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                    "HTTP-Referer": "https://basile.ia",
                }
            )
            response.raise_for_status()
            data = response.json()
            
            raw_models = data.get("data", [])
            logger.info(f"OpenRouter API returned {len(raw_models)} raw models")
            
            models = []
            for m in raw_models:
                model_id = m.get("id", "")
                model_name = m.get("name", model_id)
                context_length = m.get("context_length", 0)
                
                # Extract pricing info
                pricing_data = m.get("pricing", {})
                pricing = None
                if pricing_data:
                    pricing = {
                        "prompt": pricing_data.get("prompt", "0"),
                        "completion": pricing_data.get("completion", "0")
                    }
                
                models.append({
                    "id": model_id,
                    "name": model_name,
                    "provider": "openrouter",
                    "context_length": context_length or 0,
                    "pricing": pricing
                })
            
            logger.info(f"Fetched {len(models)} models from OpenRouter (all included)")
            return models
            
    except httpx.TimeoutException:
        logger.error("OpenRouter API timeout — try again later")
        return []
    except Exception as e:
        logger.error(f"Failed to fetch OpenRouter models: {e}")
        return []


async def get_all_models(force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Get combined list of models from all providers, with caching"""
    global _models_cache, _cache_timestamp
    
    now = time.time()
    if not force_refresh and _models_cache is not None and (now - _cache_timestamp) < CACHE_TTL_SECONDS:
        return _models_cache
    
    # Start with OpenAI models (always available if key is set)
    all_models = []
    
    if settings.OPENAI_API_KEY:
        all_models.extend(OPENAI_MODELS)
    
    # Fetch OpenRouter models
    openrouter_models = await fetch_openrouter_models()
    all_models.extend(openrouter_models)
    
    # Update cache
    _models_cache = all_models
    _cache_timestamp = now
    
    return all_models


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/available", response_model=ModelsResponse)
async def list_available_models(refresh: bool = False):
    """
    List all available LLM models from configured providers.
    Results are cached for 5 minutes. Pass ?refresh=true to force refresh.
    """
    models = await get_all_models(force_refresh=refresh)
    
    now = time.time()
    is_cached = not refresh and (_models_cache is not None and (now - _cache_timestamp) < 1)
    
    return ModelsResponse(
        models=[ModelInfo(**m) for m in models],
        total=len(models),
        cached=is_cached
    )


@router.get("/providers")
async def list_providers():
    """List configured providers and their status"""
    providers = []
    
    if settings.OPENAI_API_KEY:
        providers.append({
            "id": "openai",
            "name": "OpenAI",
            "configured": True,
            "icon": "mdi-creation",
            "color": "#10a37f"
        })
    
    if settings.OPENROUTER_API_KEY:
        providers.append({
            "id": "openrouter",
            "name": "OpenRouter",
            "configured": True,
            "icon": "mdi-router-wireless",
            "color": "#6366f1"
        })
    
    return {"providers": providers}
