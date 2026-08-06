import logging
from typing import Any, List, Optional
from langchain_openai import ChatOpenAI
from langchain_core.callbacks import CallbackManagerForLLMRun, AsyncCallbackManagerForLLMRun
from langchain_core.outputs import ChatResult
from langchain_core.messages import BaseMessage

from app.config import settings

logger = logging.getLogger(__name__)

class FallbackChatOpenAI(ChatOpenAI):
    """
    ChatOpenAI with automatic fallback to OpenRouter's inclusionai/ling-3.0-flash.
    """
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Store original kwargs to recreate the fallback with the same settings
        self._init_kwargs = kwargs.copy()
        
    def _get_fallback_llm(self) -> ChatOpenAI:
        fallback_params = self._init_kwargs.copy()
        
        fallback_params["model"] = "inclusionai/ling-3.0-flash"
        fallback_params["api_key"] = settings.OPENROUTER_API_KEY
        fallback_params["base_url"] = "https://openrouter.ai/api/v1"
        fallback_params.pop("openai_api_key", None)
        fallback_params.pop("openai_api_base", None)
        
        return ChatOpenAI(**fallback_params)

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        try:
            return super()._generate(messages, stop, run_manager, **kwargs)
        except Exception as e:
            logger.warning(f"OpenAI error: {e}. Falling back to OpenRouter (inclusionai/ling-3.0-flash).")
            fallback_llm = self._get_fallback_llm()
            return fallback_llm._generate(messages, stop, run_manager, **kwargs)

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[AsyncCallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        try:
            return await super()._agenerate(messages, stop, run_manager, **kwargs)
        except Exception as e:
            logger.warning(f"OpenAI error: {e}. Falling back to OpenRouter (inclusionai/ling-3.0-flash).")
            fallback_llm = self._get_fallback_llm()
            return await fallback_llm._agenerate(messages, stop, run_manager, **kwargs)
