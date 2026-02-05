'use client';

import { useState, useRef, useEffect } from 'react';
import { api, AgentMessage, AgentAction, AgentResponse } from '@/lib/api';
import { Opportunity } from '@/types/opportunity';

interface AgentChatProps {
  opportunity: Opportunity;
  onClose: () => void;
}

const AGENT_INFO = {
  discovery: {
    name: 'Discovery Agent',
    icon: '🔍',
    color: 'bg-blue-500',
    description: 'Présentation et qualification des opportunités',
  },
  analyst: {
    name: 'Analyst Agent',
    icon: '📊',
    color: 'bg-purple-500',
    description: 'Analyse approfondie et validation',
  },
  sourcing: {
    name: 'Sourcing Agent',
    icon: '🏭',
    color: 'bg-green-500',
    description: 'Accompagnement fournisseurs',
  },
  negotiator: {
    name: 'Negotiator Agent',
    icon: '🤝',
    color: 'bg-orange-500',
    description: 'Aide à la négociation',
  },
};

export function AgentChat({ opportunity, onClose }: AgentChatProps) {
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [currentAgent, setCurrentAgent] = useState<keyof typeof AGENT_INFO>('discovery');
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const agentConfig = AGENT_INFO[currentAgent];

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Initialize conversation with Discovery Agent
  useEffect(() => {
    initializeConversation();
  }, [opportunity.asin]);

  async function initializeConversation() {
    setIsLoading(true);
    setError(null);
    setMessages([]);

    try {
      const response = await api.presentOpportunity({
        asin: opportunity.asin,
        opportunityData: {
          asin: opportunity.asin,
          title: opportunity.title,
          brand: opportunity.brand,
          amazon_price: opportunity.amazonPrice,
          final_score: opportunity.finalScore,
          window_days: opportunity.windowDays,
          urgency_level: opportunity.urgencyLevel,
          review_count: opportunity.reviewCount,
          rating: opportunity.rating,
        },
        thesis: {
          headline: opportunity.thesis,
          thesis: opportunity.actionRecommendation,
        },
      });

      setSessionId(response.sessionId);
      addAgentMessage(response);
    } catch (err) {
      console.error('Failed to initialize conversation:', err);
      setError('Impossible de démarrer la conversation. Vérifiez que l\'API IA est configurée.');
    } finally {
      setIsLoading(false);
    }
  }

  function addAgentMessage(response: AgentResponse) {
    const newMessage: AgentMessage = {
      role: 'agent',
      content: response.message,
      timestamp: new Date().toISOString(),
      agentType: response.agentType,
      suggestedActions: response.suggestedActions,
      nextStage: response.nextStage || undefined,
    };
    setMessages((prev) => [...prev, newMessage]);

    // Auto-switch agent if suggested
    if (response.nextStage && response.nextStage in AGENT_INFO) {
      setCurrentAgent(response.nextStage as keyof typeof AGENT_INFO);
    }
  }

  async function handleSendMessage(e: React.FormEvent) {
    e.preventDefault();
    if (!inputValue.trim() || isLoading) return;

    const userMessage: AgentMessage = {
      role: 'user',
      content: inputValue,
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);
    setError(null);

    try {
      const response = await api.sendAgentMessage({
        agentType: currentAgent,
        message: inputValue,
        sessionId: sessionId || undefined,
        context: {
          asin: opportunity.asin,
          opportunity_data: {
            title: opportunity.title,
            amazon_price: opportunity.amazonPrice,
          },
        },
      });

      setSessionId(response.sessionId);
      addAgentMessage(response);
    } catch (err) {
      console.error('Failed to send message:', err);
      setError('Erreur lors de l\'envoi du message.');
    } finally {
      setIsLoading(false);
    }
  }

  async function handleActionClick(action: AgentAction) {
    if (action.url) {
      window.open(action.url, '_blank');
      return;
    }

    // Send action as a message
    const actionMessage = action.label;
    setInputValue('');
    setIsLoading(true);

    const userMessage: AgentMessage = {
      role: 'user',
      content: actionMessage,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMessage]);

    try {
      const response = await api.sendAgentMessage({
        agentType: currentAgent,
        message: actionMessage,
        sessionId: sessionId || undefined,
        context: {
          asin: opportunity.asin,
          opportunity_data: {
            title: opportunity.title,
            amazon_price: opportunity.amazonPrice,
          },
        },
      });

      setSessionId(response.sessionId);
      addAgentMessage(response);
    } catch (err) {
      console.error('Failed to handle action:', err);
      setError('Erreur lors de l\'action.');
    } finally {
      setIsLoading(false);
    }
  }

  function switchAgent(agent: keyof typeof AGENT_INFO) {
    setCurrentAgent(agent);
    // Add system message about agent switch
    const systemMessage: AgentMessage = {
      role: 'agent',
      content: `Vous êtes maintenant connecté avec **${AGENT_INFO[agent].name}**. ${AGENT_INFO[agent].description}.`,
      timestamp: new Date().toISOString(),
      agentType: agent,
    };
    setMessages((prev) => [...prev, systemMessage]);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="flex flex-col w-full max-w-2xl h-[80vh] mx-4 bg-white rounded-2xl shadow-2xl border border-gray-200 overflow-hidden animate-slide-up">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-gray-50 border-b">
        <div className="flex items-center gap-3">
          <div className={`w-10 h-10 ${agentConfig.color} rounded-full flex items-center justify-center text-white text-xl`}>
            {agentConfig.icon}
          </div>
          <div>
            <h3 className="font-semibold text-gray-900">{agentConfig.name}</h3>
            <p className="text-xs text-gray-500">{agentConfig.description}</p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-2 text-gray-400 hover:text-gray-600 transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Agent Switcher */}
      <div className="flex gap-1 px-3 py-2 bg-gray-50 border-b overflow-x-auto">
        {(Object.keys(AGENT_INFO) as Array<keyof typeof AGENT_INFO>).map((agent) => (
          <button
            key={agent}
            onClick={() => switchAgent(agent)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-colors whitespace-nowrap ${
              currentAgent === agent
                ? `${AGENT_INFO[agent].color} text-white`
                : 'bg-gray-200 text-gray-600 hover:bg-gray-300'
            }`}
          >
            <span>{AGENT_INFO[agent].icon}</span>
            <span>{AGENT_INFO[agent].name.replace(' Agent', '')}</span>
          </button>
        ))}
      </div>

      {/* Product Context */}
      <div className="px-4 py-2 bg-blue-50 border-b text-sm">
        <span className="text-blue-600 font-medium">Opportunité:</span>{' '}
        <span className="text-blue-800">{opportunity.title?.slice(0, 50)}...</span>
        <span className="text-blue-600 ml-2">Score: {opportunity.finalScore}/100</span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-red-700 text-sm">
            {error}
          </div>
        )}

        {messages.map((msg, idx) => (
          <div
            key={idx}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                msg.role === 'user'
                  ? 'bg-primary-600 text-white'
                  : 'bg-gray-100 text-gray-800'
              }`}
            >
              {/* Agent badge */}
              {msg.role === 'agent' && msg.agentType && (
                <div className="flex items-center gap-1 mb-2 text-xs text-gray-500">
                  <span>{AGENT_INFO[msg.agentType as keyof typeof AGENT_INFO]?.icon}</span>
                  <span>{AGENT_INFO[msg.agentType as keyof typeof AGENT_INFO]?.name}</span>
                </div>
              )}

              {/* Message content with markdown-like formatting */}
              <div className="prose prose-sm max-w-none">
                {msg.content.split('\n').map((line, i) => {
                  // Bold text
                  const boldLine = line.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
                  // Headers
                  if (line.startsWith('### ')) {
                    return (
                      <h4 key={i} className="font-semibold text-gray-900 mt-3 mb-1">
                        {line.replace('### ', '')}
                      </h4>
                    );
                  }
                  // List items
                  if (line.match(/^\d+\.\s/)) {
                    return (
                      <p key={i} className="ml-4" dangerouslySetInnerHTML={{ __html: boldLine }} />
                    );
                  }
                  return (
                    <p key={i} className="mb-1" dangerouslySetInnerHTML={{ __html: boldLine }} />
                  );
                })}
              </div>

              {/* Suggested actions */}
              {msg.suggestedActions && msg.suggestedActions.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {msg.suggestedActions.map((action, actionIdx) => (
                    <button
                      key={actionIdx}
                      onClick={() => handleActionClick(action)}
                      className="px-3 py-1.5 bg-white border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition-colors"
                    >
                      {action.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-2xl px-4 py-3">
              <div className="flex items-center gap-2">
                <div className="flex gap-1">
                  <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                  <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                  <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                </div>
                <span className="text-sm text-gray-500">L'agent réfléchit...</span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSendMessage} className="p-4 border-t bg-gray-50">
        <div className="flex gap-2">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Posez votre question..."
            className="flex-1 px-4 py-2 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={isLoading || !inputValue.trim()}
            className="px-4 py-2 bg-primary-600 text-white rounded-xl font-medium hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
            </svg>
          </button>
        </div>
      </form>
      </div>
    </div>
  );
}
