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
        Ensures PII is scrambled before sending to hosted providers.
        """
        scrambled_source = self._scramble_pii(source_json)
        scrambled_target = self._scramble_pii(target_json)

        prompt = f"""
        Act as a Data Engineer. Suggest a field mapping between these two JSON schemas.
        
        CRITICAL: The values below are SYNTHETIC/SCRAMBLED to protect privacy. 
        Focus on Key Names, Nesting Structure, and Data Formats.
        
        SOURCE SYSTEM SCHEMA (Synthetic Samples):
        {scrambled_source}
        
        TARGET SYSTEM SCHEMA (Synthetic Samples):
        {scrambled_target}
        
        Return a JSON object mapping the source field names to target field names.
        Example format: {{"source_key": "target_key"}}
        """
        
        return await self._call_llm(prompt)

    def _scramble_pii(self, data: Any) -> Any:
        """
        Recursively scrambles values in a JSON-like structure to prevent PII exposure.
        Replaces actual values with synthetic placeholders while preserving types.
        """
        if isinstance(data, dict):
            return {k: self._scramble_pii(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._scramble_pii(i) for i in data[:2]]  # Only send top 2 samples
        elif isinstance(data, str):
            # Check if it looks like an ID, Date, or Name
            if len(data) > 20: return "Synthetic_Long_String"
            return "Synthetic_String"
        elif isinstance(data, (int, float)):
            return 999  # Generic number
        elif isinstance(data, bool):
            return data
        return None

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
