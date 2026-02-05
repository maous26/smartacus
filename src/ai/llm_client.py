"""
Smartacus LLM Client
====================

Client abstrait pour les LLMs.
Supporte Claude (Anthropic) et OpenAI comme fallback.

Le LLM est utilisé pour :
1. Générer des thèses économiques argumentées
2. Analyser les reviews et détecter les pain points
3. Piloter les agents d'accompagnement
"""

import os
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    """Providers LLM supportés."""
    ANTHROPIC = "anthropic"
    OPENAI = "openai"


@dataclass
class LLMResponse:
    """Réponse d'un LLM."""
    content: str
    model: str
    provider: LLMProvider
    tokens_input: int
    tokens_output: int
    cost_usd: float

    @property
    def total_tokens(self) -> int:
        return self.tokens_input + self.tokens_output


class LLMClient(ABC):
    """Client LLM abstrait."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Génère une réponse."""
        pass

    @abstractmethod
    async def generate_json(
        self,
        prompt: str,
        system: Optional[str] = None,
        schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Génère une réponse JSON structurée."""
        pass


class AnthropicClient(LLMClient):
    """
    Client pour Claude (Anthropic).

    Modèles disponibles :
    - claude-3-5-sonnet-20241022 (recommandé pour thèses)
    - claude-3-haiku-20240307 (rapide, pour analyse reviews)
    """

    # Pricing par 1M tokens (USD)
    PRICING = {
        "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
        "claude-sonnet-4-20250514": {"input": 3.0, "output": 15.0},
        "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-20250514",
    ):
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.model = model
        self._client = None

        if not self.api_key:
            logger.warning("ANTHROPIC_API_KEY not set - LLM features disabled")

    def _get_client(self):
        """Lazy init du client Anthropic."""
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                raise ImportError("pip install anthropic required")
        return self._client

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        """Calcule le coût en USD."""
        pricing = self.PRICING.get(self.model, {"input": 3.0, "output": 15.0})
        cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
        return round(cost, 6)

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """Génère une réponse avec Claude."""
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY required")

        client = self._get_client()

        messages = [{"role": "user", "content": prompt}]

        kwargs = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
            "temperature": temperature,
        }

        if system:
            kwargs["system"] = system

        response = client.messages.create(**kwargs)

        content = response.content[0].text
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens

        return LLMResponse(
            content=content,
            model=self.model,
            provider=LLMProvider.ANTHROPIC,
            tokens_input=input_tokens,
            tokens_output=output_tokens,
            cost_usd=self._calculate_cost(input_tokens, output_tokens),
        )

    async def generate_json(
        self,
        prompt: str,
        system: Optional[str] = None,
        schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Génère une réponse JSON structurée."""
        json_system = (system or "") + """

IMPORTANT: Tu dois répondre UNIQUEMENT avec du JSON valide.
Pas de texte avant ou après le JSON.
Pas de ```json ou autres markers.
Juste le JSON brut."""

        if schema:
            json_system += f"\n\nSchema attendu:\n{json.dumps(schema, indent=2)}"

        response = await self.generate(
            prompt=prompt,
            system=json_system,
            temperature=0.3,  # Plus déterministe pour JSON
        )

        # Parse JSON
        try:
            # Nettoyer la réponse
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip()

            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}\nContent: {response.content[:500]}")
            raise ValueError(f"LLM did not return valid JSON: {e}")


class OpenAIClient(LLMClient):
    """
    Client pour OpenAI GPT.
    Utilisé comme fallback si Anthropic non disponible.
    """

    PRICING = {
        "gpt-4o": {"input": 2.5, "output": 10.0},
        "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
    ):
        # Support both OPENAI_API_KEY and GPT_API_KEY
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("GPT_API_KEY")
        self.model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import openai
                self._client = openai.OpenAI(api_key=self.api_key)
            except ImportError:
                raise ImportError("pip install openai required")
        return self._client

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        pricing = self.PRICING.get(self.model, {"input": 2.5, "output": 10.0})
        cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000
        return round(cost, 6)

    async def generate(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ) -> LLMResponse:
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY required")

        client = self._get_client()

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        content = response.choices[0].message.content
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens

        return LLMResponse(
            content=content,
            model=self.model,
            provider=LLMProvider.OPENAI,
            tokens_input=input_tokens,
            tokens_output=output_tokens,
            cost_usd=self._calculate_cost(input_tokens, output_tokens),
        )

    async def generate_json(
        self,
        prompt: str,
        system: Optional[str] = None,
        schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        json_system = (system or "") + "\nRespond only with valid JSON, no markdown."

        response = await self.generate(
            prompt=prompt,
            system=json_system,
            temperature=0.3,
        )

        content = response.content.strip()
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]

        return json.loads(content.strip())


def get_llm_client(
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> LLMClient:
    """
    Factory pour obtenir un client LLM.

    Priorité :
    1. Provider explicite
    2. ANTHROPIC_API_KEY présente → Claude
    3. OPENAI_API_KEY ou GPT_API_KEY présente → GPT
    4. Erreur
    """
    openai_key = os.getenv("OPENAI_API_KEY") or os.getenv("GPT_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    if provider == "openai" or (not provider and openai_key and not anthropic_key):
        return OpenAIClient(model=model or "gpt-4o-mini")

    if provider == "anthropic" or anthropic_key:
        return AnthropicClient(model=model or "claude-sonnet-4-20250514")

    if openai_key:
        return OpenAIClient(model=model or "gpt-4o-mini")

    raise ValueError(
        "No LLM API key found. Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or GPT_API_KEY"
    )
