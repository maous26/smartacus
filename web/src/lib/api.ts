/**
 * Smartacus API Client
 * ====================
 *
 * Client pour communiquer avec le backend FastAPI.
 */

import { ShortlistResponse, PipelineStatus } from '@/types/opportunity';

// Configuration
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * Fetch wrapper avec gestion d'erreur
 */
async function fetchApi<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;

  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `API Error: ${response.status}`);
  }

  return response.json();
}

/**
 * API Response types (matching backend Pydantic models)
 */
interface ApiShortlistResponse {
  summary: {
    generated_at: string;
    count: number;
    total_potential_value: number;
    criteria: {
      min_score: number;
      min_value: number;
      max_items: number;
    };
  };
  opportunities: Array<{
    rank: number;
    asin: string;
    title: string | null;
    brand: string | null;
    final_score: number;
    base_score: number;
    time_multiplier: number;
    estimated_monthly_profit: number;
    estimated_annual_value: number;
    risk_adjusted_value: number;
    window_days: number;
    urgency_level: string;
    urgency_label: string;
    thesis: string;
    action_recommendation: string;
    component_scores: Record<string, {
      name: string;
      score: number;
      max_score: number;
      percentage: number;
    }>;
    economic_events: Array<{
      event_type: string;
      thesis: string;
      confidence: string;
      urgency: string;
    }>;
    amazon_price: number | null;
    review_count: number | null;
    rating: number | null;
    detected_at: string;
  }>;
}

interface ApiPipelineStatus {
  last_run_at: string | null;
  status: string;
  asins_tracked: number;
  opportunities_found: number;
  next_run_at: string | null;
}

/**
 * Transform API response to frontend types
 */
function transformShortlistResponse(api: ApiShortlistResponse): ShortlistResponse {
  return {
    summary: {
      generatedAt: api.summary.generated_at,
      count: api.summary.count,
      totalPotentialValue: api.summary.total_potential_value,
      criteria: {
        minScore: api.summary.criteria.min_score,
        minValue: api.summary.criteria.min_value,
        maxItems: api.summary.criteria.max_items,
      },
    },
    opportunities: api.opportunities.map((opp) => ({
      rank: opp.rank,
      asin: opp.asin,
      title: opp.title || undefined,
      brand: opp.brand || undefined,
      finalScore: opp.final_score,
      baseScore: opp.base_score,
      timeMultiplier: opp.time_multiplier,
      estimatedMonthlyProfit: opp.estimated_monthly_profit,
      estimatedAnnualValue: opp.estimated_annual_value,
      riskAdjustedValue: opp.risk_adjusted_value,
      windowDays: opp.window_days,
      urgencyLevel: opp.urgency_level as 'critical' | 'urgent' | 'active' | 'standard' | 'extended',
      urgencyLabel: opp.urgency_label,
      thesis: opp.thesis,
      actionRecommendation: opp.action_recommendation,
      componentScores: Object.fromEntries(
        Object.entries(opp.component_scores).map(([key, val]) => [
          key,
          {
            name: val.name,
            score: val.score,
            maxScore: val.max_score,
            percentage: val.percentage,
          },
        ])
      ),
      economicEvents: opp.economic_events.map((event) => ({
        eventType: event.event_type,
        thesis: event.thesis,
        confidence: event.confidence as 'strong' | 'moderate' | 'weak',
        urgency: event.urgency as 'critical' | 'urgent' | 'active' | 'standard',
      })),
      amazonPrice: opp.amazon_price || undefined,
      reviewCount: opp.review_count || undefined,
      rating: opp.rating || undefined,
      detectedAt: opp.detected_at,
    })),
  };
}

function transformPipelineStatus(api: ApiPipelineStatus): PipelineStatus {
  return {
    lastRunAt: api.last_run_at || '',
    status: api.status as 'idle' | 'running' | 'completed' | 'error',
    asinsTracked: api.asins_tracked,
    opportunitiesFound: api.opportunities_found,
    nextRunAt: api.next_run_at || undefined,
  };
}

/**
 * API Client
 */
// =============================================================================
// AI TYPES
// =============================================================================

export interface AIStatus {
  aiAvailable: boolean;
  providers: {
    anthropic: string;
    openai: string;
  };
  activeSessions: number;
}

export interface ThesisResponse {
  asin: string;
  headline: string;
  thesis: string;
  reasoning: string[];
  confidence: string;
  action: string;
  urgency: string;
  risks: string[];
  nextSteps: string[];
  estimatedMonthlyProfit: number | null;
  costUsd: number;
}

export interface AgentAction {
  action: string;
  label: string;
  description?: string;
  url?: string;
}

export interface AgentMessage {
  role: 'user' | 'agent';
  content: string;
  timestamp: string;
  agentType?: string;
  suggestedActions?: AgentAction[];
  nextStage?: string;
}

export interface AgentResponse {
  agentType: string;
  message: string;
  suggestedActions: AgentAction[];
  questions: string[];
  nextStage: string | null;
  requiresInput: boolean;
  sessionId: string;
}

export const api = {
  /**
   * Download shortlist as CSV file
   */
  async downloadCSV(params?: {
    maxItems?: number;
    minScore?: number;
    minValue?: number;
    urgency?: string;
    eventType?: string;
  }): Promise<void> {
    const searchParams = new URLSearchParams();
    if (params?.maxItems) searchParams.set('max_items', params.maxItems.toString());
    if (params?.minScore) searchParams.set('min_score', params.minScore.toString());
    if (params?.minValue) searchParams.set('min_value', params.minValue.toString());
    if (params?.urgency) searchParams.set('urgency', params.urgency);
    if (params?.eventType) searchParams.set('event_type', params.eventType);

    const query = searchParams.toString();
    const url = `${API_BASE_URL}/api/shortlist/export${query ? `?${query}` : ''}`;

    const response = await fetch(url);
    if (!response.ok) throw new Error('Export failed');

    const blob = await response.blob();
    const downloadUrl = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = downloadUrl;
    a.download = `smartacus_shortlist.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(downloadUrl);
  },

  /**
   * Get the opportunity shortlist
   */
  async getShortlist(params?: {
    maxItems?: number;
    minScore?: number;
    minValue?: number;
  }): Promise<ShortlistResponse> {
    const searchParams = new URLSearchParams();
    if (params?.maxItems) searchParams.set('max_items', params.maxItems.toString());
    if (params?.minScore) searchParams.set('min_score', params.minScore.toString());
    if (params?.minValue) searchParams.set('min_value', params.minValue.toString());

    const query = searchParams.toString();
    const endpoint = `/api/shortlist${query ? `?${query}` : ''}`;

    const response = await fetchApi<ApiShortlistResponse>(endpoint);
    return transformShortlistResponse(response);
  },

  /**
   * Get pipeline status
   */
  async getPipelineStatus(): Promise<PipelineStatus> {
    const response = await fetchApi<ApiPipelineStatus>('/api/pipeline/status');
    return transformPipelineStatus(response);
  },

  /**
   * Health check
   */
  async healthCheck(): Promise<{ status: string; version: string }> {
    return fetchApi('/api/health');
  },

  /**
   * Trigger a pipeline run
   */
  async runPipeline(params?: {
    maxAsins?: number;
    forceRefresh?: boolean;
  }): Promise<{ status: string; message: string; runId: string }> {
    const response = await fetchApi<{
      status: string;
      message: string;
      run_id: string;
    }>('/api/pipeline/run', {
      method: 'POST',
      body: JSON.stringify({
        max_asins: params?.maxAsins,
        force_refresh: params?.forceRefresh,
      }),
    });

    return {
      status: response.status,
      message: response.message,
      runId: response.run_id,
    };
  },

  // ===========================================================================
  // AI ENDPOINTS
  // ===========================================================================

  /**
   * Get AI status
   */
  async getAIStatus(): Promise<AIStatus> {
    const response = await fetchApi<{
      ai_available: boolean;
      providers: { anthropic: string; openai: string };
      active_sessions: number;
    }>('/api/ai/status');

    return {
      aiAvailable: response.ai_available,
      providers: response.providers,
      activeSessions: response.active_sessions,
    };
  },

  /**
   * Generate economic thesis for an opportunity
   */
  async generateThesis(params: {
    asin: string;
    opportunityData: Record<string, unknown>;
    scoreData: Record<string, unknown>;
    events?: Array<Record<string, unknown>>;
  }): Promise<ThesisResponse> {
    const response = await fetchApi<{
      asin: string;
      headline: string;
      thesis: string;
      reasoning: string[];
      confidence: string;
      action: string;
      urgency: string;
      risks: string[];
      next_steps: string[];
      estimated_monthly_profit: number | null;
      cost_usd: number;
    }>('/api/ai/thesis', {
      method: 'POST',
      body: JSON.stringify({
        asin: params.asin,
        opportunity_data: params.opportunityData,
        score_data: params.scoreData,
        events: params.events,
      }),
    });

    return {
      asin: response.asin,
      headline: response.headline,
      thesis: response.thesis,
      reasoning: response.reasoning,
      confidence: response.confidence,
      action: response.action,
      urgency: response.urgency,
      risks: response.risks,
      nextSteps: response.next_steps,
      estimatedMonthlyProfit: response.estimated_monthly_profit,
      costUsd: response.cost_usd,
    };
  },

  /**
   * Present an opportunity to the Discovery agent
   */
  async presentOpportunity(params: {
    asin: string;
    opportunityData: Record<string, unknown>;
    thesis?: Record<string, unknown>;
    sessionId?: string;
  }): Promise<AgentResponse> {
    const response = await fetchApi<{
      message: string;
      suggested_actions: AgentAction[];
      session_id: string;
    }>('/api/ai/agent/present-opportunity', {
      method: 'POST',
      body: JSON.stringify({
        asin: params.asin,
        opportunity_data: params.opportunityData,
        thesis: params.thesis,
        session_id: params.sessionId,
      }),
    });

    return {
      agentType: 'discovery',
      message: response.message,
      suggestedActions: response.suggested_actions,
      questions: [],
      nextStage: null,
      requiresInput: true,
      sessionId: response.session_id,
    };
  },

  /**
   * Send a message to an agent
   */
  async sendAgentMessage(params: {
    agentType: string;
    message: string;
    sessionId?: string;
    context?: Record<string, unknown>;
  }): Promise<AgentResponse> {
    const response = await fetchApi<{
      agent_type: string;
      message: string;
      suggested_actions: AgentAction[];
      questions: string[];
      next_stage: string | null;
      requires_input: boolean;
      session_id: string;
    }>('/api/ai/agent/message', {
      method: 'POST',
      body: JSON.stringify({
        agent_type: params.agentType,
        message: params.message,
        session_id: params.sessionId,
        context: params.context,
      }),
    });

    return {
      agentType: response.agent_type,
      message: response.message,
      suggestedActions: response.suggested_actions,
      questions: response.questions,
      nextStage: response.next_stage,
      requiresInput: response.requires_input,
      sessionId: response.session_id,
    };
  },
};

export default api;
