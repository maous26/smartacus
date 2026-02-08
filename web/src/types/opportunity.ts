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
  explanation?: string;
  details?: Record<string, any>;
}

export interface EconomicEvent {
  eventType: string;
  thesis: string;
  confidence: 'weak' | 'moderate' | 'strong' | 'confirmed';
  urgency: UrgencyLevel | 'high' | 'medium' | 'low';  // V2.0: backend may send high/medium/low
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

// Product Spec Generator types
export interface SpecRequirement {
  source: string;
  requirement: string;
  material: string | null;
  tolerance: string | null;
  priority: string;
}

export interface SpecQCTest {
  category: string;
  name: string;
  method: string;
  passCriterion: string;
  priority: string;
}

export interface SpecBundle {
  asin: string;
  generatedAt: string;
  version: string;
  mappingVersion: string;
  inputsHash: string;
  runId?: string;
  improvementScore: number;
  reviewsAnalyzed: number;
  totalRequirements: number;
  totalQcTests: number;
  oemSpecText: string;
  qcChecklistText: string;
  rfqMessageText: string;
  bundle: {
    oem_spec: {
      bloc_a: SpecRequirement[];
      bloc_b: SpecRequirement[];
      general_materials: string[];
      accessories: string[];
    };
    qc_checklist: {
      tests: SpecQCTest[];
    };
    rfq_message: {
      subject: string;
      body: string;
      key_requirements: string[];
    };
  } | null;
}

// Review Intelligence types
export interface DefectSignal {
  defectType: string;
  frequency: number;
  severityScore: number;
  frequencyRate: number;
  exampleQuotes: string[];
}

export interface FeatureRequestSignal {
  feature: string;
  mentions: number;
  confidence: number;
  wishStrength: number;
  sourceQuotes: string[];
}

export interface ReviewProfile {
  asin: string;
  improvementScore: number;
  dominantPain: string | null;
  reviewsAnalyzed: number;
  negativeReviewsAnalyzed: number;
  reviewsReady: boolean;
  hasActionableInsights: boolean;
  thesisFragment: string;
  topDefects: DefectSignal[];
  missingFeatures: FeatureRequestSignal[];
}
