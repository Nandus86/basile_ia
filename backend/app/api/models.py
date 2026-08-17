"""
Models API - Auto-discovery of available LLM models from multiple providers
"""
import httpx
import time
import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db

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
    provider: str  # "openai" | "openrouter" | "google" | "deepseek" | custom_uuid
    context_length: int = 0
    pricing: Optional[Dict[str, Any]] = None


class ModelsResponse(BaseModel):
    models: List[ModelInfo]
    total: int
    cached: bool = False


# ─── OpenAI models (well-known, stable list) ─────────────────────────────────
async def fetch_openai_models() -> List[Dict[str, Any]]:
    """Fetch available models directly from OpenAI API"""
    if not settings.OPENAI_API_KEY:
        return []
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.openai.com/v1/models",
                headers={
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                }
            )
            response.raise_for_status()
            data = response.json()
            
            raw_models = data.get("data", [])
            logger.info(f"OpenAI API returned {len(raw_models)} models")
            
            models = []
            for m in raw_models:
                model_id = m.get("id", "")
                
                models.append({
                    "id": model_id,
                    "name": model_id,
                    "provider": "openai",
                    "context_length": 128000, # OpenAI API doesn't return context length, so default
                })
            
            # Sort models alphabetically
            models.sort(key=lambda x: x["name"])
            return models
            
    except Exception as e:
        logger.error(f"Failed to fetch OpenAI models: {e}")
        # Fallback to standard ones if API fails
        return [
            {"id": "gpt-4o", "name": "gpt-4o", "provider": "openai", "context_length": 128000},
            {"id": "gpt-4o-mini", "name": "gpt-4o-mini", "provider": "openai", "context_length": 128000},
            {"id": "o1-mini", "name": "o1-mini", "provider": "openai", "context_length": 128000},
            {"id": "o3-mini", "name": "o3-mini", "provider": "openai", "context_length": 200000},
        ]


# ─── DeepSeek models (native via .env) ────────────────────────────────────────
async def fetch_deepseek_models() -> List[Dict[str, Any]]:
    """Fetch available models directly from DeepSeek API"""
    if not settings.DEEPSEEK_API_KEY:
        return []
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.deepseek.com/models",
                headers={
                    "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                }
            )
            response.raise_for_status()
            data = response.json()
            
            raw_models = data.get("data", [])
            logger.info(f"DeepSeek API returned {len(raw_models)} models")
            
            models = []
            for m in raw_models:
                model_id = m.get("id", "")
                display_name = "DeepSeek Chat (V3)" if model_id == "deepseek-chat" else ("DeepSeek Reasoner (R1)" if model_id == "deepseek-reasoner" else model_id)
                models.append({
                    "id": model_id,
                    "name": display_name,
                    "provider": "deepseek",
                    "context_length": 64000,
                })
            
            models.sort(key=lambda x: x["name"])
            return models
            
    except Exception as e:
        logger.error(f"Failed to fetch DeepSeek models dynamically: {e}")
        return [
            {"id": "deepseek-chat", "name": "DeepSeek Chat (V3)", "provider": "deepseek", "context_length": 64000},
            {"id": "deepseek-reasoner", "name": "DeepSeek Reasoner (R1)", "provider": "deepseek", "context_length": 64000},
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
            
            extra_variations = [
                {"id": "openai/gpt-oss-120b:exacto", "name": "GPT OSS 120B (Exacto)", "provider": "openrouter", "context_length": 128000, "pricing": None},
                {"id": "openai/gpt-oss-120b:nitro", "name": "GPT OSS 120B (Nitro)", "provider": "openrouter", "context_length": 128000, "pricing": None},
                {"id": "deepinfra/bf16", "name": "DeepInfra (bf16)", "provider": "openrouter", "context_length": 0, "pricing": None},
                {"id": "sambanova", "name": "SambaNova", "provider": "openrouter", "context_length": 0, "pricing": None},
                {"id": "groq", "name": "Groq", "provider": "openrouter", "context_length": 0, "pricing": None},
                {"id": "cerebras/fp16", "name": "Cerebras (fp16)", "provider": "openrouter", "context_length": 0, "pricing": None},
            ]
            
            existing_ids = {m["id"] for m in models}
            for extra in extra_variations:
                if extra["id"] not in existing_ids:
                    models.append(extra)
            
            return models
            
    except httpx.TimeoutException:
        logger.error("OpenRouter API timeout — try again later")
        return []
    except Exception as e:
        logger.error(f"Failed to fetch OpenRouter models: {e}")
        return []


async def fetch_google_models() -> List[Dict[str, Any]]:
    """Fetch available models dynamically from Google Generative Language API"""
    if not settings.GOOGLE_API_KEY:
        return []
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"https://generativelanguage.googleapis.com/v1beta/models?key={settings.GOOGLE_API_KEY}"
            )
            response.raise_for_status()
            data = response.json()
            
            raw_models = data.get("models", [])
            logger.info(f"Google API returned {len(raw_models)} models")
            
            models = []
            for m in raw_models:
                full_name = m.get("name", "")
                model_id = full_name.replace("models/", "") if full_name.startswith("models/") else full_name
                
                supported_methods = m.get("supportedGenerationMethods", [])
                if "generateContent" not in supported_methods:
                    continue
                
                display_name = m.get("displayName", model_id)
                input_limit = m.get("inputTokenLimit", 1048576)
                
                models.append({
                    "id": model_id,
                    "name": display_name,
                    "provider": "google",
                    "context_length": input_limit,
                })
            
            models.sort(key=lambda x: x["name"])
            return models
            
    except Exception as e:
        logger.error(f"Failed to fetch Google models dynamically: {e}")
        return [
            {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash (Fallback)", "provider": "google", "context_length": 1048576},
            {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro (Fallback)", "provider": "google", "context_length": 2097152},
            {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash (Fallback)", "provider": "google", "context_length": 1048576},
            {"id": "gemini-2.5-flash", "name": "Gemini 2.5 Flash (Fallback)", "provider": "google", "context_length": 1048576},
        ]


# ─── Custom DB AI Providers (Dynamic discovery) ──────────────────────────────
async def fetch_custom_provider_models(db: AsyncSession) -> List[Dict[str, Any]]:
    """Fetch models for active custom AI Providers defined in database"""
    from app.models.ai_provider import AIProvider
    from sqlalchemy.future import select
    
    try:
        result = await db.execute(select(AIProvider).where(AIProvider.is_active == True))
        providers = result.scalars().all()
        if not providers:
            return []
            
        custom_models = []
        for p in providers:
            p_id = str(p.id)
            p_name = p.name or "Custom"
            base_url = (p.base_url or "").strip()
            api_key = p.api_key or ""
            
            models_fetched = []
            if base_url:
                from urllib.parse import urlparse
                parsed_u = urlparse(base_url)
                endpoints_to_try = [f"{base_url.rstrip('/')}/models"]
                if not parsed_u.path or parsed_u.path in ("", "/"):
                    endpoints_to_try.append(f"{base_url.rstrip('/')}/v1/models")
                    
                headers = {}
                if api_key:
                    headers["Authorization"] = f"Bearer {api_key}"
                    
                for ep in endpoints_to_try:
                    try:
                        async with httpx.AsyncClient(timeout=4.0) as client:
                            resp = await client.get(ep, headers=headers)
                            if resp.status_code == 200:
                                data = resp.json()
                                raw = data.get("data", [])
                                for m in raw:
                                    m_id = m.get("id", "")
                                    if m_id:
                                        display = m_id
                                        if m_id == "deepseek-chat":
                                            display = "DeepSeek Chat (V3)"
                                        elif m_id == "deepseek-reasoner":
                                            display = "DeepSeek Reasoner (R1)"
                                        models_fetched.append({
                                            "id": m_id,
                                            "name": f"{display}",
                                            "provider": p_id,
                                            "context_length": 64000,
                                        })
                                if models_fetched:
                                    break
                    except Exception:
                        continue
            
            # Fallback if no remote endpoint responded
            if not models_fetched:
                if "deepseek" in p_name.lower() or "deepseek" in base_url.lower():
                    models_fetched.extend([
                        {"id": "deepseek-chat", "name": "DeepSeek Chat (V3)", "provider": p_id, "context_length": 64000},
                        {"id": "deepseek-reasoner", "name": "DeepSeek Reasoner (R1)", "provider": p_id, "context_length": 64000},
                    ])
                elif p.default_model:
                    models_fetched.append({
                        "id": p.default_model,
                        "name": p.default_model,
                        "provider": p_id,
                        "context_length": 128000,
                    })
                    
            custom_models.extend(models_fetched)
            
        return custom_models
    except Exception as e:
        logger.error(f"Failed to fetch custom provider models: {e}")
        return []


async def get_all_models(db: Optional[AsyncSession] = None, force_refresh: bool = False) -> List[Dict[str, Any]]:
    """Get combined list of models from all providers, with caching"""
    global _models_cache, _cache_timestamp
    
    now = time.time()
    if not force_refresh and _models_cache is not None and (now - _cache_timestamp) < CACHE_TTL_SECONDS:
        return _models_cache
    
    all_models = []
    
    if settings.OPENAI_API_KEY:
        openai_models = await fetch_openai_models()
        all_models.extend(openai_models)
        
    if settings.GOOGLE_API_KEY:
        google_models = await fetch_google_models()
        all_models.extend(google_models)
    
    if settings.DEEPSEEK_API_KEY:
        deepseek_models = await fetch_deepseek_models()
        all_models.extend(deepseek_models)
    
    # Fetch OpenRouter models
    openrouter_models = await fetch_openrouter_models()
    all_models.extend(openrouter_models)
    
    # Fetch Custom DB Provider models if DB session is provided
    if db is not None:
        custom_models = await fetch_custom_provider_models(db)
        all_models.extend(custom_models)
    
    # Update cache
    _models_cache = all_models
    _cache_timestamp = now
    
    return all_models


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/available", response_model=ModelsResponse)
async def list_available_models(refresh: bool = False, db: AsyncSession = Depends(get_db)):
    """
    List all available LLM models from configured providers.
    Results are cached for 5 minutes. Pass ?refresh=true to force refresh.
    """
    models = await get_all_models(db=db, force_refresh=refresh)
    
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
        
    if settings.GOOGLE_API_KEY:
        providers.append({
            "id": "google",
            "name": "Google Gemini",
            "configured": True,
            "icon": "mdi-google",
            "color": "#fbbc04"
        })
        
    if settings.DEEPSEEK_API_KEY:
        providers.append({
            "id": "deepseek",
            "name": "DeepSeek",
            "configured": True,
            "icon": "mdi-robot-outline",
            "color": "#4d6bfe"
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
