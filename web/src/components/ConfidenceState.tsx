'use client';

/**
 * ConfidenceState Component
 * ========================
 *
 * Displays the cognitive confidence state for an opportunity.
 * NOT a score - an explicit state that helps users understand
 * how much they can trust the analysis.
 *
 * States:
 * - ÉCLAIRÉ (green): Key signals present, risks identified and measurable
 * - INCOMPLET (yellow): Positive signals but missing key info (default)
 * - FRAGILE (red): Insufficient or contradictory data
 *
 * V3.2: Added reason codes for metrics and debugging
 */

import { ReviewProfile } from '@/types/opportunity';

export type ConfidenceLevel = 'eclaire' | 'incomplet' | 'fragile';

/**
 * Reason codes for confidence calculation.
 * Used for metrics, debugging, and explaining states.
 */
export type ConfidenceReasonCode =
  | 'CONF_REVIEWS_MISSING'      // No reviews analyzed
  | 'CONF_REVIEWS_PARTIAL'      // < 20 reviews
  | 'CONF_REVIEWS_OK'           // >= 20 reviews
  | 'CONF_PAIN_MISSING'         // No dominant pain identified
  | 'CONF_PAIN_OK'              // Dominant pain identified
  | 'CONF_SPEC_MISSING'         // No OEM spec generated
  | 'CONF_SPEC_OK'              // OEM spec generated
  | 'CONF_MARGIN_MISSING'       // Margin not validated
  | 'CONF_MARGIN_OK'            // Margin data available
  | 'CONF_VELOCITY_OK'          // Demand signals present
  | 'CONF_DATA_PARTIAL'         // Economic data partial
  | 'CONF_SIGNAL_CONTRADICT';   // Contradictory signals

interface ReasonWithCode {
  code: ConfidenceReasonCode;
  label: string;
  isPositive: boolean;
}

interface ConfidenceStateProps {
  level: ConfidenceLevel;
  reasons: ReasonWithCode[];
  className?: string;
  expanded?: boolean;
  showCodes?: boolean;  // For debugging
}

interface ConfidenceConfig {
  label: string;
  description: string;
  color: string;
  bgColor: string;
  borderColor: string;
  icon: string;
}

const CONFIG: Record<ConfidenceLevel, ConfidenceConfig> = {
  eclaire: {
    label: 'Éclairé',
    description: 'Les principaux signaux sont présents. Les risques sont identifiés et mesurables. Décision possible avec validation finale humaine.',
    color: 'text-emerald-700',
    bgColor: 'bg-emerald-50',
    borderColor: 'border-emerald-300',
    icon: '🟢',
  },
  incomplet: {
    label: 'Incomplet',
    description: 'Les signaux économiques sont positifs, mais certaines informations clés manquent encore.',
    color: 'text-amber-700',
    bgColor: 'bg-amber-50',
    borderColor: 'border-amber-300',
    icon: '🟡',
  },
  fragile: {
    label: 'Fragile',
    description: 'Les données sont insuffisantes ou contradictoires. Une décision à ce stade serait principalement spéculative.',
    color: 'text-red-700',
    bgColor: 'bg-red-50',
    borderColor: 'border-red-300',
    icon: '🔴',
  },
};

export function ConfidenceState({
  level,
  reasons,
  className = '',
  expanded = false,
  showCodes = false,
}: ConfidenceStateProps) {
  const config = CONFIG[level];
  const positiveReasons = reasons.filter(r => r.isPositive);
  const negativeReasons = reasons.filter(r => !r.isPositive);

  return (
    <div className={`rounded-xl border ${config.bgColor} ${config.borderColor} ${className}`}>
      <div className="p-4">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-lg">{config.icon}</span>
          <span className={`font-semibold ${config.color}`}>
            Niveau de confiance : {config.label}
          </span>
        </div>

        {expanded && (
          <p className={`text-sm ${config.color} opacity-80 mb-3`}>
            {config.description}
          </p>
        )}

        {/* Show what's missing for non-green states */}
        {negativeReasons.length > 0 && (
          <div className="mt-2">
            <div className={`text-xs uppercase tracking-wide ${config.color} opacity-70 mb-1`}>
              Ce qui manque
            </div>
            <ul className="space-y-1">
              {negativeReasons.map((reason, idx) => (
                <li key={idx} className={`text-sm ${config.color} flex items-start gap-2`}>
                  <span className="mt-0.5">
                    {level === 'fragile' ? '✗' : '?'}
                  </span>
                  <span>
                    {reason.label}
                    {showCodes && (
                      <code className="ml-2 text-xs opacity-50">{reason.code}</code>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Show what's solid for green state or if expanded */}
        {(level === 'eclaire' || expanded) && positiveReasons.length > 0 && (
          <div className="mt-2">
            <div className={`text-xs uppercase tracking-wide ${config.color} opacity-70 mb-1`}>
              Ce qui est solide
            </div>
            <ul className="space-y-1">
              {positiveReasons.map((reason, idx) => (
                <li key={idx} className={`text-sm ${config.color} flex items-start gap-2`}>
                  <span className="mt-0.5 text-emerald-500">✓</span>
                  <span>
                    {reason.label}
                    {showCodes && (
                      <code className="ml-2 text-xs opacity-50">{reason.code}</code>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Calculate confidence level from opportunity data
 * Returns structured reasons with codes for metrics
 */
export function calculateConfidenceLevel(
  reviewProfile: ReviewProfile | null,
  hasSpecBundle: boolean,
  componentScores: Record<string, any> | undefined,
  finalScore: number,
): { level: ConfidenceLevel; reasons: ReasonWithCode[]; codes: ConfidenceReasonCode[] } {
  const reasons: ReasonWithCode[] = [];
  let issues = 0;

  // Check reviews
  if (!reviewProfile || !reviewProfile.reviewsReady) {
    reasons.push({
      code: 'CONF_REVIEWS_MISSING',
      label: 'Analyse reviews non effectuée',
      isPositive: false,
    });
    issues += 2;
  } else if (reviewProfile.reviewsAnalyzed < 20) {
    reasons.push({
      code: 'CONF_REVIEWS_PARTIAL',
      label: `Reviews partiellement analysées (${reviewProfile.reviewsAnalyzed}/20 min.)`,
      isPositive: false,
    });
    issues += 1;
  } else {
    reasons.push({
      code: 'CONF_REVIEWS_OK',
      label: `${reviewProfile.reviewsAnalyzed} reviews analysés`,
      isPositive: true,
    });
  }

  // Check product differentiation
  if (reviewProfile?.dominantPain) {
    reasons.push({
      code: 'CONF_PAIN_OK',
      label: `Défaut dominant identifié: ${reviewProfile.dominantPain}`,
      isPositive: true,
    });
  } else {
    reasons.push({
      code: 'CONF_PAIN_MISSING',
      label: 'Différenciation produit non validée',
      isPositive: false,
    });
    issues += 1;
  }

  // Check spec bundle
  if (hasSpecBundle) {
    reasons.push({
      code: 'CONF_SPEC_OK',
      label: 'Spec OEM générée',
      isPositive: true,
    });
  } else {
    reasons.push({
      code: 'CONF_SPEC_MISSING',
      label: 'Spec OEM non générée',
      isPositive: false,
    });
    issues += 1;
  }

  // Check data completeness via component scores
  if (componentScores) {
    const margin = componentScores['margin'];
    const velocity = componentScores['velocity'];

    if (margin && margin.score >= margin.maxScore * 0.5) {
      reasons.push({
        code: 'CONF_MARGIN_OK',
        label: 'Données prix/marge disponibles',
        isPositive: true,
      });
    } else {
      reasons.push({
        code: 'CONF_MARGIN_MISSING',
        label: 'Marge estimée (non validée)',
        isPositive: false,
      });
      issues += 1;
    }

    if (velocity && velocity.score >= velocity.maxScore * 0.3) {
      reasons.push({
        code: 'CONF_VELOCITY_OK',
        label: 'Signaux de demande présents',
        isPositive: true,
      });
    }
  } else {
    reasons.push({
      code: 'CONF_DATA_PARTIAL',
      label: 'Données économiques partielles',
      isPositive: false,
    });
    issues += 1;
  }

  // Extract codes for logging
  const codes = reasons.map(r => r.code);

  // Determine level
  if (issues === 0) {
    return { level: 'eclaire', reasons, codes };
  } else if (issues <= 2) {
    return { level: 'incomplet', reasons, codes };
  } else {
    return { level: 'fragile', reasons, codes };
  }
}

/**
 * Legacy wrapper for backward compatibility
 */
export function calculateConfidenceLevelLegacy(
  reviewProfile: ReviewProfile | null,
  hasSpecBundle: boolean,
  componentScores: Record<string, any> | undefined,
  finalScore: number,
): { level: ConfidenceLevel; reasons: string[] } {
  const result = calculateConfidenceLevel(reviewProfile, hasSpecBundle, componentScores, finalScore);
  return {
    level: result.level,
    reasons: result.reasons.filter(r => !r.isPositive).map(r => r.label),
  };
}
