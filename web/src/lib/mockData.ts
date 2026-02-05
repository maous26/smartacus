/**
 * Données de démonstration pour l'interface
 * Ces données seront remplacées par l'API backend
 *
 * IMPORTANT: Utiliser des dates FIXES pour éviter les erreurs d'hydratation React
 */

import { Opportunity, ShortlistResponse, PipelineStatus } from '@/types/opportunity';

// Dates fixes pour éviter les différences serveur/client
const FIXED_DATE = '2026-02-04T17:00:00.000Z';
const FIXED_LAST_RUN = '2026-02-04T15:00:00.000Z';

export const mockOpportunities: Opportunity[] = [
  {
    rank: 1,
    asin: 'B09XK7NZQP',
    title: 'VANMASS Car Phone Mount [Military-Grade Suction]',
    brand: 'VANMASS',
    finalScore: 82,
    baseScore: 0.73,
    timeMultiplier: 1.45,
    estimatedMonthlyProfit: 2850,
    estimatedAnnualValue: 34200,
    riskAdjustedValue: 23940,
    windowDays: 28,
    urgencyLevel: 'urgent',
    urgencyLabel: '🟠 URGENT - Action prioritaire',
    thesis: 'Supply shock détecté | 3 ruptures/mois | BSR +35% | Marge 42%',
    actionRecommendation: 'PRIORITAIRE: Lancer analyse fournisseurs sous 7 jours',
    componentScores: {
      margin: { name: 'margin', score: 24, maxScore: 30, percentage: 80 },
      velocity: { name: 'velocity', score: 19, maxScore: 25, percentage: 76 },
      competition: { name: 'competition', score: 14, maxScore: 20, percentage: 70 },
      gap: { name: 'gap', score: 9, maxScore: 15, percentage: 60 },
    },
    economicEvents: [
      {
        eventType: 'SUPPLY_SHOCK',
        thesis: '3 ruptures de stock en 30 jours, demande non satisfaite',
        confidence: 'strong',
        urgency: 'urgent',
      },
    ],
    amazonPrice: 29.99,
    reviewCount: 12453,
    rating: 4.4,
    detectedAt: FIXED_DATE,
  },
  {
    rank: 2,
    asin: 'B08L5TNJHG',
    title: 'Miracase Car Phone Holder Mount',
    brand: 'Miracase',
    finalScore: 76,
    baseScore: 0.68,
    timeMultiplier: 1.32,
    estimatedMonthlyProfit: 1920,
    estimatedAnnualValue: 23040,
    riskAdjustedValue: 16128,
    windowDays: 45,
    urgencyLevel: 'active',
    urgencyLabel: '🟡 ACTIF - Fenêtre viable',
    thesis: 'Concurrent effondré | Churn 28% | Place à prendre | Marge 38%',
    actionRecommendation: 'ACTIF: Planifier sourcing dans les 2 semaines',
    componentScores: {
      margin: { name: 'margin', score: 21, maxScore: 30, percentage: 70 },
      velocity: { name: 'velocity', score: 18, maxScore: 25, percentage: 72 },
      competition: { name: 'competition', score: 15, maxScore: 20, percentage: 75 },
      gap: { name: 'gap', score: 7, maxScore: 15, percentage: 47 },
    },
    economicEvents: [
      {
        eventType: 'COMPETITOR_COLLAPSE',
        thesis: 'Leader historique sorti du marché, parts à capturer',
        confidence: 'moderate',
        urgency: 'active',
      },
    ],
    amazonPrice: 24.99,
    reviewCount: 8234,
    rating: 4.3,
    detectedAt: FIXED_DATE,
  },
  {
    rank: 3,
    asin: 'B0BXYZ1234',
    title: 'LISEN MagSafe Car Mount [15W Wireless Charging]',
    brand: 'LISEN',
    finalScore: 71,
    baseScore: 0.65,
    timeMultiplier: 1.28,
    estimatedMonthlyProfit: 1650,
    estimatedAnnualValue: 19800,
    riskAdjustedValue: 13860,
    windowDays: 60,
    urgencyLevel: 'active',
    urgencyLabel: '🟡 ACTIF - Fenêtre viable',
    thesis: 'Quality decay | 18% négatifs | "I wish" +12 | Amélioration possible',
    actionRecommendation: 'ACTIF: Analyser les plaintes récurrentes pour différenciation',
    componentScores: {
      margin: { name: 'margin', score: 20, maxScore: 30, percentage: 67 },
      velocity: { name: 'velocity', score: 16, maxScore: 25, percentage: 64 },
      competition: { name: 'competition', score: 12, maxScore: 20, percentage: 60 },
      gap: { name: 'gap', score: 11, maxScore: 15, percentage: 73 },
    },
    economicEvents: [
      {
        eventType: 'QUALITY_DECAY',
        thesis: 'Reviews négatifs en hausse, opportunité de différenciation qualité',
        confidence: 'strong',
        urgency: 'active',
      },
    ],
    amazonPrice: 34.99,
    reviewCount: 5621,
    rating: 4.1,
    detectedAt: FIXED_DATE,
  },
  {
    rank: 4,
    asin: 'B0CDE56789',
    title: 'andobil Car Phone Holder [2024 Upgraded]',
    brand: 'andobil',
    finalScore: 65,
    baseScore: 0.62,
    timeMultiplier: 1.15,
    estimatedMonthlyProfit: 1280,
    estimatedAnnualValue: 15360,
    riskAdjustedValue: 10752,
    windowDays: 75,
    urgencyLevel: 'standard',
    urgencyLabel: '🟢 STANDARD - Temps disponible',
    thesis: 'Niche stable | Marge correcte | Entrée possible | Risque modéré',
    actionRecommendation: 'SURVEILLER: Ajouter au backlog, réévaluer dans 30 jours',
    componentScores: {
      margin: { name: 'margin', score: 18, maxScore: 30, percentage: 60 },
      velocity: { name: 'velocity', score: 15, maxScore: 25, percentage: 60 },
      competition: { name: 'competition', score: 13, maxScore: 20, percentage: 65 },
      gap: { name: 'gap', score: 10, maxScore: 15, percentage: 67 },
    },
    amazonPrice: 27.99,
    reviewCount: 3892,
    rating: 4.2,
    detectedAt: FIXED_DATE,
  },
  {
    rank: 5,
    asin: 'B0FGH78901',
    title: 'Lamicall Car Vent Phone Mount',
    brand: 'Lamicall',
    finalScore: 58,
    baseScore: 0.58,
    timeMultiplier: 1.05,
    estimatedMonthlyProfit: 980,
    estimatedAnnualValue: 11760,
    riskAdjustedValue: 8232,
    windowDays: 90,
    urgencyLevel: 'standard',
    urgencyLabel: '🟢 STANDARD - Temps disponible',
    thesis: 'Marché mature | Marge faible | Différenciation requise',
    actionRecommendation: 'SURVEILLER: Opportunité secondaire, prioriser autres',
    componentScores: {
      margin: { name: 'margin', score: 15, maxScore: 30, percentage: 50 },
      velocity: { name: 'velocity', score: 14, maxScore: 25, percentage: 56 },
      competition: { name: 'competition', score: 14, maxScore: 20, percentage: 70 },
      gap: { name: 'gap', score: 9, maxScore: 15, percentage: 60 },
    },
    amazonPrice: 19.99,
    reviewCount: 15234,
    rating: 4.5,
    detectedAt: FIXED_DATE,
  },
];

export const mockShortlistResponse: ShortlistResponse = {
  summary: {
    generatedAt: FIXED_DATE,
    count: 5,
    totalPotentialValue: 72912,
    criteria: {
      minScore: 50,
      minValue: 5000,
      maxItems: 5,
    },
  },
  opportunities: mockOpportunities,
};

export const mockPipelineStatus: PipelineStatus = {
  lastRunAt: FIXED_LAST_RUN,
  status: 'completed',
  asinsTracked: 6842,
  opportunitiesFound: 23,
  nextRunAt: '2026-02-05T13:00:00.000Z',
};
