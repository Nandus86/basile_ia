import logging
from typing import List, Optional, Tuple, Any
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI, create_context_cache
import redis.asyncio as redis
from app.config import settings

logger = logging.getLogger(__name__)

class GeminiCacheService:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    async def get_or_create_cache(
        self, 
        session_id: str, 
        agent_id: str, 
        messages: List[BaseMessage], 
        api_key: str,
        model_name: str = "gemini-1.5-pro",
        tools: Optional[List[Any]] = None
    ) -> Tuple[Optional[str], List[BaseMessage]]:
        """
        Check for existing cache for this session+agent.
        If it exists, return (cache_name, dynamic_messages).
        If not, create it with the static part (SystemMessage + RAG), save to redis, and return (cache_name, dynamic_messages).
        """
        if not api_key:
            return None, messages

        # Encontra o ponto de divisão: mensagens estáticas (SystemMessage) vs dinâmicas
        static_messages = []
        dynamic_messages = []
        for i, msg in enumerate(messages):
            if isinstance(msg, SystemMessage):
                static_messages.append(msg)
            else:
                dynamic_messages = messages[i:]
                break
                
        # Se não há contexto estático para fazer cache, apenas retorna as mensagens originais
        if not static_messages:
            return None, messages

        cache_key = f"gemini_cache:{session_id}:{agent_id}"
        cached_name = await self.redis.get(cache_key)
        
        if cached_name:
            cached_name = cached_name.decode("utf-8")
            logger.info(f"[GeminiCache] Found existing cache {cached_name} for session {session_id} agent {agent_id}")
            return cached_name, dynamic_messages
            
        # Cria novo cache
        try:
            logger.info(f"[GeminiCache] Creating new cache for {session_id}:{agent_id} with {len(static_messages)} static messages")
            
            # Se a versão for flash, usamos flash para o cache também
            cache_model_name = "gemini-1.5-flash" if "flash" in model_name.lower() else "gemini-1.5-pro"
            llm = ChatGoogleGenerativeAI(model=cache_model_name, api_key=api_key)
            if tools:
                llm = llm.bind_tools(tools)
            
            cache = create_context_cache(
                model=llm,
                messages=static_messages,
                ttl="3600s" # Expira no provedor em 1 hora
            )
            
            cache_name = cache.name
            # Salva no Redis com TTL ligeiramente menor (55 minutos = 3300s) para evitar race conditions com o provedor
            await self.redis.set(cache_key, cache_name, ex=3300)
            
            logger.info(f"[GeminiCache] Successfully created cache {cache_name}")
            return cache_name, dynamic_messages
            
        except Exception as e:
            logger.error(f"[GeminiCache] Failed to create cache: {e}")
            return None, messages

class CachedChatGoogleGenerativeAI(ChatGoogleGenerativeAI):
    """
    Extensão do ChatGoogleGenerativeAI que intercepta a chamada ainvoke
    para usar o Context Caching do Google automaticamente.
    """
    _gemini_session_id: Optional[str] = None
    _gemini_agent_id: Optional[str] = None
    
    async def ainvoke(self, input, config=None, stop=None, **kwargs):
        from app.config import settings
        import redis.asyncio as redis
        
        # input is typically a list of messages
        messages = input
        
        if not self._gemini_session_id or not self._gemini_agent_id:
            return await super().ainvoke(input, config=config, stop=stop, **kwargs)
            
        try:
            redis_client = redis.from_url(settings.REDIS_URL)
            cache_service = GeminiCacheService(redis_client)
            
            api_key = self.google_api_key.get_secret_value() if hasattr(self.google_api_key, "get_secret_value") else str(self.google_api_key)
            
            # TODO: tools are not easily extracted here, but create_context_cache 
            # might not need tools for the System Prompt if the model isn't bound yet.
            cache_id, dynamic_messages = await cache_service.get_or_create_cache(
                self._gemini_session_id, self._gemini_agent_id, messages, api_key, self.model
            )
            
            await redis_client.aclose()
            
            if cache_id:
                # We instantiate a temporary LLM with the cache_id
                temp_llm = ChatGoogleGenerativeAI(
                    model=cache_id,
                    api_key=api_key,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
                
                # If we have tools bound, we should bind them to temp_llm too
                # Usually Langchain stores them in kwargs or we are not the bound object.
                # If we are the bound object, self.tools won't exist because bind_tools returns a RunnableBinding.
                # The RunnableBinding calls ainvoke on its bound model (which is us) with tools in kwargs.
                return await temp_llm.ainvoke(dynamic_messages, config=config, stop=stop, **kwargs)
            else:
                return await super().ainvoke(input, config=config, stop=stop, **kwargs)
                
        except Exception as e:
            logger.error(f"[GeminiCache] Error during ainvoke interception: {e}")
            return await super().ainvoke(input, config=config, stop=stop, **kwargs)
