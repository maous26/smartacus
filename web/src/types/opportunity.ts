/**
 * Types pour les opportunités Smartacus
 */

export type UrgencyLevel = 'critical' | 'urgent' | 'active' | 'standard' | 'extended';

export type OpportunityStatus = 'exceptional' | 'strong' | 'moderate' | 'weak' | 'rejected';

export interface ComponentScore {
  name: string;
  score: number;
  maxScore: number;
  percentage: number;
  details?: Record<string, any>;
}

export interface EconomicEvent {
  eventType: string;
  thesis: string;
  confidence: 'weak' | 'moderate' | 'strong' | 'confirmed';
  urgency: UrgencyLevel;
}

export interface Opportunity {
  rank: number;
  asin: string;
  title?: string;
  brand?: string;
  imageUrl?: string;

  // Scores
  finalScore: number;
  baseScore: number;
  timeMultiplier: number;

  // Valeur économique
  estimatedMonthlyProfit: number;
  estimatedAnnualValue: number;
  riskAdjustedValue: number;

  // Fenêtre temporelle
  windowDays: number;
  urgencyLevel: UrgencyLevel;
  urgencyLabel: string;

  // Thèse
  thesis: string;
  actionRecommendation: string;

  // Détails
  componentScores?: Record<string, ComponentScore>;
  economicEvents?: EconomicEvent[];

  // Metadata
  detectedAt: string;
  amazonPrice?: number;
  reviewCount?: number;
  rating?: number;
}

export interface ShortlistSummary {
  generatedAt: string;
  count: number;
  totalPotentialValue: number;
  criteria: {
    minScore: number;
    minValue: number;
    maxItems: number;
  };
}

export interface ShortlistResponse {
  summary: ShortlistSummary;
  opportunities: Opportunity[];
}

export interface PipelineStatus {
  lastRunAt: string;
  status: 'idle' | 'running' | 'completed' | 'error';
  asinsTracked: number;
  opportunitiesFound: number;
  nextRunAt?: string;
}
