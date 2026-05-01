"""
UBID Fabric — AI Service Layer
Provides a unified interface for Cloud AI (Gemini) and Self-Hosted AI (Ollama/Llama).
"""

from typing import Optional, Dict, Any
import httpx
import structlog
from ubid_fabric.config import settings

logger = structlog.get_logger()

class AIService:
    """
    Unified service to interact with LLMs for schema mapping,
    conflict resolution advice, and data cleaning.
    """

    def __init__(self):
        self.provider = settings.ai_provider
        self.base_url = settings.ai_base_url
        self.api_key = settings.ai_api_key
        self.model = settings.ai_model

    async def get_mapping_suggestion(self, source_json: Dict[str, Any], target_json: Dict[str, Any]) -> str:
        """
        Asks the AI to suggest a mapping between two JSON schemas.
        """
        prompt = f"""
        Act as a Data Engineer. Suggest a field mapping between these two JSON objects:
        
        SOURCE SYSTEM DATA:
        {source_json}
        
        TARGET SYSTEM DATA:
        {target_json}
        
        Return a Python dictionary mapping the source field names to target field names.
        Identify any fields that need transformations (like dates or uppercase).
        """
        
        return await self._call_llm(prompt)

    async def _call_llm(self, prompt: str) -> str:
        """
        Routes the call to the appropriate provider.
        """
        if self.provider == "gemini":
            return await self._call_gemini(prompt)
        else:
            # Standard OpenAI-compatible API (Ollama, vLLM, etc.)
            return await self._call_openai_compatible(prompt)

    async def _call_gemini(self, prompt: str) -> str:
        """Calls the Google Gemini API."""
        if not self.api_key:
            return "Error: Gemini API Key not set."
            
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(url, json=payload, timeout=30.0)
                resp.raise_for_status()
                return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            except Exception as e:
                logger.error("ai_call_failed", provider="gemini", error=str(e))
                return f"AI Error: {str(e)}"

    async def _call_openai_compatible(self, prompt: str) -> str:
        """Calls any OpenAI-compatible API (like Ollama or vLLM)."""
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}]
        }
        
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(url, json=payload, headers=headers, timeout=60.0)
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            except Exception as e:
                logger.error("ai_call_failed", provider=self.provider, error=str(e))
                return f"AI Error (Self-Hosted): {str(e)}"
