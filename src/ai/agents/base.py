"""
Base Agent Framework
====================

Framework de base pour tous les agents Smartacus.
Intègre RAG pour enrichir les réponses avec des connaissances.
"""

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum

from ..llm_client import LLMClient, get_llm_client

logger = logging.getLogger(__name__)

# RAG integration (lazy loaded)
_rag_retriever = None


def get_rag_retriever():
    """Get or create RAG retriever (singleton)."""
    global _rag_retriever
    if _rag_retriever is None:
        try:
            from ...rag import RAGRetriever
            _rag_retriever = RAGRetriever()
            logger.info("RAG retriever initialized")
        except Exception as e:
            logger.warning(f"RAG not available: {e}")
            _rag_retriever = False  # Mark as unavailable
    return _rag_retriever if _rag_retriever else None


class AgentType(Enum):
    """Types d'agents disponibles."""
    DISCOVERY = "discovery"
    ANALYST = "analyst"
    SOURCING = "sourcing"
    NEGOTIATOR = "negotiator"


class AgentStatus(Enum):
    """Statut de l'agent."""
    IDLE = "idle"
    THINKING = "thinking"
    ACTING = "acting"
    WAITING = "waiting"  # Attend input utilisateur
    COMPLETED = "completed"
    ERROR = "error"


@dataclass
class AgentContext:
    """
    Contexte partagé entre les agents.

    Contient toutes les informations sur l'opportunité en cours,
    l'historique des interactions, et les préférences utilisateur.
    """
    # Opportunité courante
    asin: Optional[str] = None
    opportunity_data: Dict[str, Any] = field(default_factory=dict)
    thesis: Optional[Dict[str, Any]] = None

    # Historique de conversation
    messages: List[Dict[str, str]] = field(default_factory=list)

    # Préférences utilisateur
    user_preferences: Dict[str, Any] = field(default_factory=dict)

    # État du workflow
    current_stage: str = "discovery"
    completed_stages: List[str] = field(default_factory=list)

    # Données collectées par les agents
    sourcing_options: List[Dict[str, Any]] = field(default_factory=list)
    negotiation_history: List[Dict[str, Any]] = field(default_factory=list)

    # RAG citations (for traceability)
    rag_citations: List[Dict[str, Any]] = field(default_factory=list)
    session_id: Optional[str] = None

    def add_message(self, role: str, content: str):
        """Ajoute un message à l'historique."""
        self.messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def get_conversation_history(self, max_messages: int = 10) -> str:
        """Retourne l'historique formaté pour le prompt."""
        recent = self.messages[-max_messages:]
        lines = []
        for msg in recent:
            role = "User" if msg["role"] == "user" else "Agent"
            lines.append(f"{role}: {msg['content']}")
        return "\n".join(lines)


@dataclass
class AgentResponse:
    """
    Réponse d'un agent.
    """
    # Contenu de la réponse
    message: str
    thinking: Optional[str] = None  # Raisonnement interne (optionnel)

    # Actions suggérées
    suggested_actions: List[Dict[str, str]] = field(default_factory=list)
    # Ex: [{"action": "contact_supplier", "label": "Contacter ce fournisseur", "data": {...}}]

    # Questions pour l'utilisateur
    questions: List[str] = field(default_factory=list)

    # Données structurées
    data: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    agent_type: AgentType = AgentType.DISCOVERY
    status: AgentStatus = AgentStatus.COMPLETED
    confidence: float = 0.8
    tokens_used: int = 0
    cost_usd: float = 0.0

    # Navigation
    next_stage: Optional[str] = None  # Suggère de passer à l'étape suivante
    requires_input: bool = False

    # RAG sources used
    sources: List[Dict[str, Any]] = field(default_factory=list)


class BaseAgent(ABC):
    """
    Agent de base.

    Chaque agent :
    1. A un rôle spécifique dans le workflow
    2. Utilise le LLM pour raisonner et communiquer
    3. Peut proposer des actions et poser des questions
    4. Maintient un contexte partagé
    """

    agent_type: AgentType = AgentType.DISCOVERY
    name: str = "Base Agent"
    description: str = "Agent de base"

    def __init__(self, llm_client: Optional[LLMClient] = None, use_rag: bool = True):
        self._llm_client = llm_client
        self._total_cost = 0.0
        self._use_rag = use_rag
        self._rag_retriever = None

    @property
    def llm_client(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = get_llm_client()
        return self._llm_client

    @property
    def rag_retriever(self):
        """Get RAG retriever if available and enabled."""
        if not self._use_rag:
            return None
        if self._rag_retriever is None:
            self._rag_retriever = get_rag_retriever()
        return self._rag_retriever

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Prompt système de l'agent."""
        pass

    @abstractmethod
    async def process(
        self,
        user_input: str,
        context: AgentContext,
    ) -> AgentResponse:
        """
        Traite une entrée utilisateur.

        Args:
            user_input: Message de l'utilisateur
            context: Contexte partagé

        Returns:
            AgentResponse avec la réponse et actions
        """
        pass

    async def _retrieve_knowledge(
        self,
        query: str,
        context: AgentContext,
        k: int = 3,
    ) -> tuple[str, List[Dict[str, Any]]]:
        """
        Retrieve relevant knowledge from RAG.

        Args:
            query: Search query
            context: Agent context
            k: Number of results

        Returns:
            Tuple of (formatted context string, list of sources)
        """
        if not self.rag_retriever:
            return "", []

        try:
            # Search with agent-specific filters
            results = self.rag_retriever.search_for_agent(
                query=query,
                agent_type=self.agent_type.value,
                k=k,
            )

            if not results:
                return "", []

            # Format for LLM
            rag_context = self.rag_retriever.format_context(results)

            # Build sources list for traceability
            sources = [
                {
                    "chunk_id": str(r.chunk_id),
                    "doc_type": r.doc_type.value,
                    "domain": r.domain.value,
                    "similarity": r.similarity,
                    "excerpt": r.content[:200] + "..." if len(r.content) > 200 else r.content,
                }
                for r in results
            ]

            # Record citation if session exists
            if context.session_id:
                self.rag_retriever.cite(
                    results=results,
                    session_id=context.session_id,
                    agent_type=self.agent_type.value,
                    query=query,
                )

            logger.debug(f"RAG retrieved {len(results)} chunks for query: {query[:50]}...")
            return rag_context, sources

        except Exception as e:
            logger.warning(f"RAG retrieval failed: {e}")
            return "", []

    async def _call_llm(
        self,
        prompt: str,
        context: AgentContext,
        max_tokens: int = 1024,
        use_rag: bool = True,
    ) -> str:
        """Appelle le LLM avec le contexte et RAG."""
        # Retrieve relevant knowledge
        rag_context = ""
        sources = []
        if use_rag and self._use_rag:
            rag_context, sources = await self._retrieve_knowledge(prompt, context)

        # Construire le prompt complet avec historique
        history = context.get_conversation_history()

        # Build full prompt with RAG context if available
        if rag_context:
            full_prompt = f"""## Connaissances pertinentes (utilisez ces informations pour répondre)
{rag_context}

## Historique de conversation
{history}

## Nouvelle entrée
{prompt}

## Ta réponse (cite les sources si tu les utilises)"""
        else:
            full_prompt = f"""## Historique de conversation
{history}

## Nouvelle entrée
{prompt}

## Ta réponse"""

        response = await self.llm_client.generate(
            prompt=full_prompt,
            system=self.system_prompt,
            max_tokens=max_tokens,
        )

        # Store sources in context for traceability
        if sources:
            context.rag_citations.extend(sources)

        self._total_cost += response.cost_usd
        return response.content

    async def _call_llm_json(
        self,
        prompt: str,
        context: AgentContext,
        schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Appelle le LLM et parse la réponse JSON."""
        history = context.get_conversation_history()
        full_prompt = f"""## Contexte
{history}

## Requête
{prompt}"""

        return await self.llm_client.generate_json(
            prompt=full_prompt,
            system=self.system_prompt,
            schema=schema,
        )

    @property
    def total_cost(self) -> float:
        return self._total_cost
