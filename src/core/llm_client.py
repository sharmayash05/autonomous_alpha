"""
LLM Client - Core interface to LLMs
The Autonomous Alpha - Brutal Trading God

Handles:
- OpenAI-compatible API inference (local or remote)
- Prompt formatting and response parsing
- Retry logic and error handling
"""

import json
import asyncio
import os
import time
from typing import Any
from pathlib import Path

import httpx
from loguru import logger
from pydantic import BaseModel

# Try uvloop on Linux/Mac, winloop on Windows
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    logger.info("Using uvloop for async operations")
except ImportError:
    try:
        import winloop
        asyncio.set_event_loop_policy(winloop.EventLoopPolicy())
        logger.info("Using winloop for async operations")
    except ImportError:
        logger.warning("Neither uvloop nor winloop available, using default asyncio")


class LLMResponse(BaseModel):
    """Structured LLM response"""
    content: str
    model: str
    tokens_used: int
    latency_ms: float
    raw_response: dict | None = None


class LLMClient:
    """
    Unified client for LLM inference.
    Supports OpenAI-compatible APIs (including local servers).
    """
    
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        default_model: str | None = None,
        timeout: float = 120.0,
        max_retries: int = 3,
    ):
        # Load from environment or use defaults
        self.base_url = (base_url or os.getenv("LLM_BASE_URL", "http://localhost:3000/gemini-antigravity/v1")).rstrip("/")
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.default_model = default_model or os.getenv("LLM_MODEL", "gemini-3.0-pro-preview")
        self.timeout = timeout
        self.max_retries = max_retries
        
        # HTTP client with connection pooling
        self._client: httpx.AsyncClient | None = None
        
        logger.info(f"LLM Client initialized: {self.base_url} | Model: {self.default_model}")
        
    async def __aenter__(self):
        """Async context manager entry"""
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout),
            limits=httpx.Limits(max_keepalive_connections=10),
        )
        return self
        
    async def __aexit__(self, *args):
        """Async context manager exit"""
        if self._client:
            await self._client.aclose()
            
    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client"""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
            )
        return self._client
    
    def _get_headers(self) -> dict:
        """Get request headers with authorization"""
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
    
    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 16384,  # Unlimited tokens for deep analysis
        json_mode: bool = False,
        system_prompt: str | None = None,
    ) -> LLMResponse:
        """
        Generate a response from the LLM using OpenAI-compatible API.
        
        Args:
            prompt: The input prompt
            model: Model to use (defaults to self.default_model)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            json_mode: Whether to request JSON output
            system_prompt: Optional system prompt
            
        Returns:
            LLMResponse with generated content
        """
        start_time = time.perf_counter()
        
        model = model or self.default_model
        
        # Build messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        # Build payload (OpenAI format)
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
            
        for attempt in range(self.max_retries):
            try:
                response = await self.client.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._get_headers(),
                    json=payload,
                )
                response.raise_for_status()
                
                data = response.json()
                latency_ms = (time.perf_counter() - start_time) * 1000
                
                # Extract content from OpenAI format
                content = ""
                tokens_used = 0
                
                if "choices" in data and len(data["choices"]) > 0:
                    content = data["choices"][0].get("message", {}).get("content", "")
                    
                if "usage" in data:
                    tokens_used = data["usage"].get("total_tokens", 0)
                
                # RETRY LOGIC: If content is empty, retry (API sometimes returns empty choices)
                if not content or content.strip() == "":
                    logger.warning(f"⚠️ LLM returned empty content (attempt {attempt + 1}/{self.max_retries})")
                    # Log raw response for debugging
                    choices_info = data.get("choices", [])
                    logger.warning(f"   Raw choices: {json.dumps(choices_info)[:200]}")
                    
                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(2 ** attempt)  # Exponential backoff
                        continue  # Retry the request
                    else:
                        logger.error(f"❌ LLM returned empty content after {self.max_retries} attempts")
                
                logger.debug(f"LLM response in {latency_ms:.0f}ms | {tokens_used} tokens")
                
                return LLMResponse(
                    content=content,
                    model=model,
                    tokens_used=tokens_used,
                    latency_ms=latency_ms,
                    raw_response=data,
                )
                
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error on attempt {attempt + 1}: {e.response.status_code} - {e.response.text[:200]}")
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                
            except httpx.RequestError as e:
                logger.error(f"Request error on attempt {attempt + 1}: {e}")
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(2 ** attempt)
                
        raise RuntimeError("Failed to get LLM response after retries")
    
    async def generate_with_think(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 8192,
    ) -> tuple[str, str]:
        """
        Generate response and extract <think> block separately.
        
        Returns:
            Tuple of (thinking_content, final_output)
        """
        response = await self.generate(
            prompt=prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=False,  # Need raw output to extract <think>
        )
        
        content = response.content
        thinking = ""
        output = content
        
        # Extract <think> block if present
        if "<think>" in content and "</think>" in content:
            start = content.index("<think>") + len("<think>")
            end = content.index("</think>")
            thinking = content[start:end].strip()
            output = content[end + len("</think>"):].strip()
            
        return thinking, output
    
    async def health_check(self) -> dict[str, Any]:
        """Check if LLM endpoint is healthy"""
        results = {
            "api_available": False,
            "base_url": self.base_url,
            "model": self.default_model,
        }
        
        try:
            # Try to list models (OpenAI-compatible endpoint)
            response = await self.client.get(
                f"{self.base_url}/models",
                headers=self._get_headers(),
            )
            
            if response.status_code == 200:
                results["api_available"] = True
                data = response.json()
                if "data" in data:
                    results["available_models"] = [m.get("id") for m in data["data"]]
            else:
                # Try a simple generation to test
                try:
                    test_response = await self.generate(
                        prompt="Say 'hello' in one word.",
                        max_tokens=10,
                        temperature=0.1,
                    )
                    results["api_available"] = bool(test_response.content)
                except Exception:
                    pass
                    
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            results["error"] = str(e)
            
        return results


def load_prompt_template(name: str, prompts_dir: Path | None = None) -> str:
    """Load a prompt template from the prompts directory"""
    if prompts_dir is None:
        prompts_dir = Path(__file__).parent.parent.parent / "prompts"
        
    template_path = prompts_dir / f"{name}.md"
    
    if not template_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {template_path}")
        
    return template_path.read_text(encoding="utf-8")


def format_prompt(template: str, **kwargs) -> str:
    """Format a prompt template with provided values"""
    for key, value in kwargs.items():
        placeholder = "{" + key + "}"
        if placeholder in template:
            template = template.replace(placeholder, str(value))
    return template


async def main():
    """Test the LLM client"""
    async with LLMClient() as client:
        # Health check
        health = await client.health_check()
        logger.info(f"Health check: {health}")
        
        if health.get("api_available"):
            # Test generation
            logger.info("Testing LLM generation...")
            response = await client.generate(
                prompt="What is 2 + 2? Reply with just the number.",
                temperature=0.1,
                max_tokens=50,
            )
            logger.info(f"Response: {response.content}")
            logger.info(f"Latency: {response.latency_ms:.0f}ms")
            logger.info(f"Tokens: {response.tokens_used}")
        else:
            logger.error("LLM API not available. Please check your configuration.")


if __name__ == "__main__":
    asyncio.run(main())
