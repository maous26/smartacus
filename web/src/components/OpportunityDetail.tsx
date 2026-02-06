'use client';

/**
 * OpportunityDetail Component
 * ===========================
 *
 * V3.1 - Honest framing based on UX philosophy:
 * "Smartacus n'est pas là pour décider à ta place.
 *  Il est là pour t'empêcher de décider pour de mauvaises raisons."
 *
 * Key principles:
 * - Always show limitations
 * - Separate factual vs interpretive vs missing
 * - Never conclude without explicit uncertainty
 */

import { useState, useEffect } from 'react';
import { Opportunity, ComponentScore, ReviewProfile, SpecBundle } from '@/types/opportunity';
import { UrgencyBadge } from './UrgencyBadge';
import { ScoreRing } from './ScoreRing';
import { ReviewInsightPanel } from './ReviewInsightPanel';
import { ProductSpecPanel } from './ProductSpecPanel';
import { ConfidenceState, calculateConfidenceLevel, ConfidenceLevel } from './ConfidenceState';
import { RiskOverrideModal, HypothesisReason } from './RiskOverrideModal';
import { formatNumber, formatPrice, formatCurrency, formatDate } from '@/lib/format';
import { api } from '@/lib/api';

interface AutoThesis {
  headline: string | null;
  thesis: string;
  confidence: number | null;
  urgency: string | null;
  actionRecommendation: string | null;
  economicEstimates: Record<string, number> | null;
  generatedAt: string | null;
}

interface OpportunityDetailProps {
  opportunity: Opportunity;
  onClose?: () => void;
  onStartSourcing?: () => void;
  isDemo?: boolean;
}

function ScoreBar({ name, score, maxScore }: { name: string; score: number; maxScore: number }) {
  const percentage = (score / maxScore) * 100;

  const getBarColor = () => {
    if (percentage >= 80) return 'bg-emerald-500';
    if (percentage >= 60) return 'bg-green-500';
    if (percentage >= 40) return 'bg-yellow-500';
    if (percentage >= 20) return 'bg-orange-500';
    return 'bg-red-500';
  };

  return (
    <div className="mb-3">
      <div className="flex justify-between text-sm mb-1">
        <span className="font-medium text-gray-700 capitalize">{name}</span>
        <span className="text-gray-500">{score}/{maxScore}</span>
      </div>
      <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
        <div
          className={`h-full ${getBarColor()} transition-all duration-500`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}

export function OpportunityDetail({ opportunity, onClose, onStartSourcing, isDemo = false }: OpportunityDetailProps) {
  const {
    rank,
    asin,
    title,
    brand,
    finalScore,
    baseScore,
    timeMultiplier,
    windowDays,
    urgencyLevel,
    estimatedMonthlyProfit,
    estimatedAnnualValue,
    riskAdjustedValue,
    thesis,
    actionRecommendation,
    componentScores,
    economicEvents,
    amazonPrice,
    reviewCount,
    rating,
    detectedAt,
  } = opportunity;

  const [isSaved, setIsSaved] = useState(false);
  const [autoThesis, setAutoThesis] = useState<AutoThesis | null>(null);
  const [reviewProfile, setReviewProfile] = useState<ReviewProfile | null>(null);
  const [hasSpecBundle, setHasSpecBundle] = useState(false);
  const [showRiskModal, setShowRiskModal] = useState(false);

  // Calculate confidence state
  const { level: confidenceLevel, reasons: confidenceReasons } = calculateConfidenceLevel(
    reviewProfile,
    hasSpecBundle,
    componentScores,
    finalScore
  );

  useEffect(() => {
    const saved = JSON.parse(localStorage.getItem('smartacus_saved') || '[]') as string[];
    setIsSaved(saved.includes(asin));
  }, [asin]);

  // Fetch auto-generated thesis if available
  useEffect(() => {
    if (isDemo) return;
    api.getAutoThesis(asin).then(setAutoThesis).catch(() => setAutoThesis(null));
  }, [asin, isDemo]);

  // Fetch review profile for confidence calculation
  useEffect(() => {
    if (isDemo) return;
    api.getReviewProfile(asin).then(setReviewProfile).catch(() => setReviewProfile(null));
  }, [asin, isDemo]);

  // Check if spec bundle exists
  useEffect(() => {
    if (isDemo) return;
    api.getSpecBundle(asin).then((spec) => setHasSpecBundle(!!spec)).catch(() => setHasSpecBundle(false));
  }, [asin, isDemo]);

  const handleSave = () => {
    const saved = JSON.parse(localStorage.getItem('smartacus_saved') || '[]') as string[];
    if (saved.includes(asin)) {
      localStorage.setItem('smartacus_saved', JSON.stringify(saved.filter((a: string) => a !== asin)));
      setIsSaved(false);
    } else {
      saved.push(asin);
      localStorage.setItem('smartacus_saved', JSON.stringify(saved));
      setIsSaved(true);
    }
  };

  const handleProceedAnyway = () => {
    if (confidenceLevel !== 'eclaire') {
      setShowRiskModal(true);
    } else if (onStartSourcing) {
      onStartSourcing();
    }
  };

  const handleRiskConfirm = async (hypothesis: string, reason: HypothesisReason) => {
    // Log the risk override
    try {
      await api.createRiskOverride({
        asin,
        confidenceLevel,
        hypothesis,
        hypothesisReason: reason,
        missingInfo: confidenceReasons.filter(r => r.includes('non') || r.includes('partiel')),
      });
    } catch (e) {
      console.error('Failed to log risk override:', e);
    }

    setShowRiskModal(false);
    if (onStartSourcing) {
      onStartSourcing();
    }
  };

  // Determine what we know vs don't know
  const whatWeKnow: string[] = [];
  const whatWeDontKnow: string[] = [];

  if (componentScores) {
    if (componentScores['margin']?.score >= componentScores['margin']?.maxScore * 0.5) {
      whatWeKnow.push('Structure de prix cohérente');
    } else {
      whatWeDontKnow.push('Marge réelle non validée');
    }
    if (componentScores['velocity']?.score >= componentScores['velocity']?.maxScore * 0.3) {
      whatWeKnow.push('Demande mesurable sur le marché');
    }
  }

  if (windowDays > 30) {
    whatWeKnow.push(`Fenêtre temporelle estimée: ${windowDays} jours`);
  } else {
    whatWeDontKnow.push('Fenêtre courte, timing serré');
  }

  if (reviewProfile?.reviewsReady && reviewProfile.reviewsAnalyzed >= 20) {
    whatWeKnow.push(`${reviewProfile.reviewsAnalyzed} avis analysés`);
    if (reviewProfile.dominantPain) {
      whatWeKnow.push(`Défaut dominant identifié`);
    }
  } else {
    whatWeDontKnow.push('Analyse détaillée des avis non complète');
  }

  if (!hasSpecBundle) {
    whatWeDontKnow.push('Différenciation produit non validée');
  }

  whatWeDontKnow.push('Contraintes industrielles non évaluées');

  return (
    <div className="bg-white rounded-2xl shadow-xl border border-gray-200 overflow-hidden">
      {/* DEMO banner */}
      {isDemo && (
        <div className="bg-amber-400 text-amber-900 text-center text-xs font-bold py-1 uppercase tracking-widest">
          Données de démonstration
        </div>
      )}

      {/* Header - V3.1: More neutral framing */}
      <div className="bg-gradient-to-r from-gray-900 to-gray-800 text-white p-6">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <span className="bg-white/20 text-white font-medium px-3 py-1 rounded-full text-sm">
                Opportunité détectée
              </span>
              <span className="font-mono text-gray-300">{asin}</span>
            </div>
            {title && (
              <h2 className="text-xl font-semibold mb-1">{title}</h2>
            )}
            {brand && (
              <div className="text-gray-400">par {brand}</div>
            )}
          </div>

          <div className="text-right">
            <ScoreRing score={finalScore} size="lg" />
            <div className="text-xs text-gray-400 mt-2">Score économique</div>
          </div>
        </div>

        <div className="mt-4">
          <UrgencyBadge level={urgencyLevel} windowDays={windowDays} />
        </div>
      </div>

      {/* Content */}
      <div className="p-6">
        {/* V3.1: Honest intro message */}
        <div className="mb-6 p-4 bg-slate-50 rounded-xl border border-slate-200">
          <p className="text-sm text-slate-700">
            Cette opportunité a été détectée à partir de données de marché Amazon
            (prix, ventes, concurrence, timing).{' '}
            <span className="font-medium">Ce n'est pas une recommandation d'achat.</span>
          </p>
          <p className="text-sm text-slate-600 mt-2">
            Smartacus identifie des signaux économiques intéressants, puis met en évidence
            ce qui est solide, ce qui est incertain, et ce qui manque encore avant toute décision.
          </p>
        </div>

        {/* V3.1: Confidence State */}
        <ConfidenceState
          level={confidenceLevel}
          reasons={confidenceReasons}
          expanded={confidenceLevel !== 'eclaire'}
          className="mb-6"
        />

        {/* What we know vs don't know */}
        <div className="grid grid-cols-2 gap-4 mb-6">
          <div className="bg-emerald-50 rounded-xl p-4 border border-emerald-200">
            <h4 className="text-sm font-semibold text-emerald-800 mb-2">Ce que nous savons</h4>
            <ul className="space-y-1">
              {whatWeKnow.map((item, idx) => (
                <li key={idx} className="text-sm text-emerald-700 flex items-start gap-2">
                  <span className="text-emerald-500 mt-0.5">✓</span>
                  {item}
                </li>
              ))}
              <li className="text-sm text-emerald-700 flex items-start gap-2">
                <span className="text-emerald-500 mt-0.5">✓</span>
                Score économique: {finalScore}/100
              </li>
            </ul>
          </div>
          <div className="bg-amber-50 rounded-xl p-4 border border-amber-200">
            <h4 className="text-sm font-semibold text-amber-800 mb-2">Ce que nous ne savons pas encore</h4>
            <ul className="space-y-1">
              {whatWeDontKnow.map((item, idx) => (
                <li key={idx} className="text-sm text-amber-700 flex items-start gap-2">
                  <span className="text-amber-500 mt-0.5">?</span>
                  {item}
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Valeur économique */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="bg-emerald-50 rounded-xl p-4 text-center border border-emerald-200">
            <div className="text-sm text-emerald-700">Mensuel estimé</div>
            <div className="text-xl font-bold text-emerald-600">
              {formatCurrency(Math.round(estimatedMonthlyProfit || 0))}
            </div>
          </div>
          <div className="bg-green-50 rounded-xl p-4 text-center border border-green-200">
            <div className="text-sm text-green-700">Annuel estimé</div>
            <div className="text-xl font-bold text-green-600">
              {formatCurrency(Math.round(estimatedAnnualValue || 0))}
            </div>
          </div>
          <div className="bg-blue-50 rounded-xl p-4 text-center border border-blue-200">
            <div className="text-sm text-blue-700">Ajusté risque</div>
            <div className="text-xl font-bold text-blue-600">
              {formatCurrency(Math.round(riskAdjustedValue || 0))}
            </div>
          </div>
        </div>

        {/* Thèse - V3.1: Conditional framing */}
        <div className="mb-6">
          <h3 className="text-sm uppercase tracking-wide text-gray-500 mb-2">
            Thèse économique
            {autoThesis && (
              <span className="ml-2 text-xs bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded-full font-normal">
                Auto-générée
              </span>
            )}
          </h3>
          <div className={`rounded-xl p-4 border ${autoThesis ? 'bg-indigo-50 border-indigo-200' : 'bg-gray-50 border-gray-200'}`}>
            {autoThesis?.headline && (
              <div className="font-semibold text-indigo-900 mb-2">{autoThesis.headline}</div>
            )}
            <p className={autoThesis ? 'text-indigo-800' : 'text-gray-800'}>
              {autoThesis?.thesis || thesis}
            </p>
            {/* V3.1: Always show "but" */}
            <div className="mt-3 pt-3 border-t border-gray-200">
              <p className="text-sm text-gray-600 italic">
                <strong>Mais :</strong> {whatWeDontKnow.slice(0, 2).join(', ')}.
              </p>
            </div>
          </div>
        </div>

        {/* Action - V3.1: Conditional, not absolute */}
        <div className="mb-6">
          <h3 className="text-sm uppercase tracking-wide text-gray-500 mb-2">
            {confidenceLevel === 'eclaire' ? 'GO conditionnel' : 'Avant de décider'}
          </h3>
          <div className={`rounded-xl p-4 border ${
            confidenceLevel === 'eclaire'
              ? 'bg-emerald-50 border-emerald-200'
              : 'bg-amber-50 border-amber-200'
          }`}>
            <p className={`font-medium ${
              confidenceLevel === 'eclaire' ? 'text-emerald-900' : 'text-amber-900'
            }`}>
              {autoThesis?.actionRecommendation || actionRecommendation}
            </p>
            {confidenceLevel !== 'eclaire' && (
              <p className="text-sm text-amber-700 mt-2">
                ⚠️ Analyse incomplète. Validations supplémentaires recommandées avant de lancer.
              </p>
            )}
          </div>
        </div>

        {/* V3.1: Key insight */}
        <div className="mb-6 p-4 bg-slate-100 rounded-xl border border-slate-200">
          <p className="text-sm text-slate-700 text-center italic">
            👉 Votre avantage ne vient pas du score.
            <br />
            Il vient de votre capacité à agir là où les autres ne regardent pas.
          </p>
        </div>

        {/* Review Intelligence Panel */}
        <ReviewInsightPanel asin={asin} isDemo={isDemo} />

        {/* Product Spec Panel */}
        <ProductSpecPanel asin={asin} isDemo={isDemo} />

        {/* Score breakdown */}
        {componentScores && Object.keys(componentScores).length > 0 && (
          <div className="mb-6">
            <h3 className="text-sm uppercase tracking-wide text-gray-500 mb-3">Décomposition du score</h3>
            <div className="bg-gray-50 rounded-xl p-4 border border-gray-200">
              {Object.entries(componentScores).map(([name, comp]) => (
                <ScoreBar
                  key={name}
                  name={name}
                  score={comp.score}
                  maxScore={comp.maxScore}
                />
              ))}

              <div className="mt-4 pt-4 border-t border-gray-200 flex items-center justify-between text-sm">
                <div>
                  <span className="text-gray-500">Base: </span>
                  <span className="font-medium">{(baseScore * 100).toFixed(0)}%</span>
                </div>
                <div>
                  <span className="text-gray-500">Multiplicateur temps: </span>
                  <span className="font-medium">×{timeMultiplier.toFixed(2)}</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Economic events */}
        {economicEvents && economicEvents.length > 0 && (
          <div className="mb-6">
            <h3 className="text-sm uppercase tracking-wide text-gray-500 mb-3">Événements économiques</h3>
            <div className="space-y-2">
              {economicEvents.map((event, idx) => (
                <div
                  key={idx}
                  className="bg-purple-50 rounded-lg p-3 border border-purple-200"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-mono text-xs bg-purple-200 text-purple-800 px-2 py-0.5 rounded">
                      {event.eventType}
                    </span>
                    <span className="text-xs text-purple-600">{event.confidence}</span>
                  </div>
                  <p className="text-sm text-purple-900">{event.thesis}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Product metrics */}
        <div className="grid grid-cols-4 gap-4 p-4 bg-gray-50 rounded-xl border border-gray-200">
          {amazonPrice && (
            <div className="text-center">
              <div className="text-2xl font-bold text-gray-900">{formatPrice(amazonPrice)}</div>
              <div className="text-xs text-gray-500">Prix Amazon</div>
            </div>
          )}
          {reviewCount && (
            <div className="text-center">
              <div className="text-2xl font-bold text-gray-900">{formatNumber(reviewCount)}</div>
              <div className="text-xs text-gray-500">Avis</div>
            </div>
          )}
          {rating && (
            <div className="text-center">
              <div className="text-2xl font-bold text-gray-900">{rating.toFixed(1)} ★</div>
              <div className="text-xs text-gray-500">Note</div>
            </div>
          )}
          <div className="text-center">
            <div className="text-2xl font-bold text-gray-900">{windowDays}</div>
            <div className="text-xs text-gray-500">Jours fenêtre</div>
          </div>
        </div>

        {/* Footer */}
        <div className="mt-6 pt-4 border-t border-gray-200 flex items-center justify-between text-xs text-gray-500">
          <div>Détecté le {formatDate(detectedAt)}</div>
          <a
            href={`https://www.amazon.fr/dp/${asin}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary-600 hover:text-primary-700 font-medium"
          >
            Voir sur Amazon.fr →
          </a>
        </div>
      </div>

      {/* Action buttons - V3.1: Context-aware */}
      <div className="border-t border-gray-200 p-4 bg-gray-50 flex gap-3">
        {isDemo && (
          <div className="flex-1 bg-gray-200 text-gray-500 py-3 px-4 rounded-lg font-medium text-center cursor-not-allowed">
            Sourcing désactivé (mode démo)
          </div>
        )}
        {!isDemo && confidenceLevel === 'eclaire' && (
          <button
            onClick={onStartSourcing}
            className="flex-1 bg-emerald-600 text-white py-3 px-4 rounded-lg font-medium hover:bg-emerald-700 transition-colors"
          >
            Lancer le sourcing
          </button>
        )}
        {!isDemo && confidenceLevel !== 'eclaire' && (
          <button
            onClick={handleProceedAnyway}
            className="flex-1 bg-amber-500 text-white py-3 px-4 rounded-lg font-medium hover:bg-amber-600 transition-colors"
          >
            ⚠️ Je veux quand même avancer
          </button>
        )}
        <button
          onClick={handleSave}
          className={`px-4 py-3 border rounded-lg font-medium transition-colors ${
            isSaved
              ? 'border-emerald-300 bg-emerald-50 text-emerald-700'
              : 'border-gray-300 text-gray-700 hover:bg-gray-100'
          }`}
        >
          {isSaved ? 'Sauvegardé' : 'Sauvegarder'}
        </button>
        {onClose && (
          <button
            onClick={onClose}
            className="px-4 py-3 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-100 transition-colors"
          >
            Fermer
          </button>
        )}
      </div>

      {/* Risk Override Modal */}
      {showRiskModal && (
        <RiskOverrideModal
          asin={asin}
          confidenceLevel={confidenceLevel}
          missingInfo={whatWeDontKnow}
          onConfirm={handleRiskConfirm}
          onCancel={() => setShowRiskModal(false)}
        />
      )}
    </div>
  );
}
