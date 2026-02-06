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
 */

import { ReviewProfile } from '@/types/opportunity';

export type ConfidenceLevel = 'eclaire' | 'incomplet' | 'fragile';

interface ConfidenceStateProps {
  level: ConfidenceLevel;
  reasons: string[];
  className?: string;
  expanded?: boolean;
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

export function ConfidenceState({ level, reasons, className = '', expanded = false }: ConfidenceStateProps) {
  const config = CONFIG[level];

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

        {reasons.length > 0 && (
          <div className="mt-2">
            <div className={`text-xs uppercase tracking-wide ${config.color} opacity-70 mb-1`}>
              {level === 'eclaire' ? 'Ce qui est solide' : 'Ce qui manque'}
            </div>
            <ul className="space-y-1">
              {reasons.map((reason, idx) => (
                <li key={idx} className={`text-sm ${config.color} flex items-start gap-2`}>
                  <span className="mt-1">
                    {level === 'eclaire' ? '✓' : level === 'incomplet' ? '?' : '✗'}
                  </span>
                  {reason}
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
 */
export function calculateConfidenceLevel(
  reviewProfile: ReviewProfile | null,
  hasSpecBundle: boolean,
  componentScores: Record<string, any> | undefined,
  finalScore: number,
): { level: ConfidenceLevel; reasons: string[] } {
  const reasons: string[] = [];
  let issues = 0;

  // Check reviews
  if (!reviewProfile || !reviewProfile.reviewsReady) {
    reasons.push('Analyse reviews non effectuée');
    issues += 2;
  } else if (reviewProfile.reviewsAnalyzed < 20) {
    reasons.push(`Reviews partiellement analysées (${reviewProfile.reviewsAnalyzed}/20 min.)`);
    issues += 1;
  } else {
    reasons.push(`${reviewProfile.reviewsAnalyzed} reviews analysés`);
  }

  // Check product differentiation
  if (reviewProfile?.dominantPain) {
    reasons.push(`Défaut dominant identifié: ${reviewProfile.dominantPain}`);
  } else {
    reasons.push('Différenciation produit non validée');
    issues += 1;
  }

  // Check spec bundle
  if (hasSpecBundle) {
    reasons.push('Spec OEM générée');
  } else {
    reasons.push('Spec OEM non générée');
    issues += 1;
  }

  // Check data completeness via component scores
  if (componentScores) {
    const margin = componentScores['margin'];
    const velocity = componentScores['velocity'];

    if (margin && margin.score >= margin.maxScore * 0.5) {
      reasons.push('Données prix/marge disponibles');
    } else {
      reasons.push('Marge estimée (non validée)');
      issues += 1;
    }

    if (velocity && velocity.score >= velocity.maxScore * 0.3) {
      reasons.push('Signaux de demande présents');
    }
  } else {
    reasons.push('Données économiques partielles');
    issues += 1;
  }

  // Determine level
  if (issues === 0) {
    return { level: 'eclaire', reasons: reasons.filter(r => !r.includes('non')) };
  } else if (issues <= 2) {
    return {
      level: 'incomplet',
      reasons: reasons.filter(r => r.includes('non') || r.includes('partiel') || r.includes('estimé'))
    };
  } else {
    return {
      level: 'fragile',
      reasons: reasons.filter(r => r.includes('non') || r.includes('partiel') || r.includes('estimé'))
    };
  }
}
