'use client';

import { useState, useEffect } from 'react';
import { Opportunity, ComponentScore } from '@/types/opportunity';
import { UrgencyBadge } from './UrgencyBadge';
import { ScoreRing } from './ScoreRing';
import { ReviewInsightPanel } from './ReviewInsightPanel';
import { ProductSpecPanel } from './ProductSpecPanel';
import { formatNumber, formatPrice, formatCurrency, formatDate } from '@/lib/format';

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
    urgencyLabel,
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

  useEffect(() => {
    const saved = JSON.parse(localStorage.getItem('smartacus_saved') || '[]') as string[];
    setIsSaved(saved.includes(asin));
  }, [asin]);

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

  return (
    <div className="bg-white rounded-2xl shadow-xl border border-gray-200 overflow-hidden">
      {/* DEMO banner */}
      {isDemo && (
        <div className="bg-amber-400 text-amber-900 text-center text-xs font-bold py-1 uppercase tracking-widest">
          Données de démonstration
        </div>
      )}
      {/* Header */}
      <div className="bg-gradient-to-r from-gray-900 to-gray-800 text-white p-6">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <span className="bg-white text-gray-900 font-bold px-3 py-1 rounded-full text-sm">
                #{rank}
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
            <div className="text-xs text-gray-400 mt-2">Score Final</div>
          </div>
        </div>

        <div className="mt-4">
          <UrgencyBadge level={urgencyLevel} windowDays={windowDays} />
        </div>
      </div>

      {/* Content */}
      <div className="p-6">
        {/* Valeur économique */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="bg-emerald-50 rounded-xl p-4 text-center border border-emerald-200">
            <div className="text-sm text-emerald-700">Mensuel</div>
            <div className="text-xl font-bold text-emerald-600">
              {formatCurrency(Math.round(estimatedMonthlyProfit || 0))}
            </div>
          </div>
          <div className="bg-green-50 rounded-xl p-4 text-center border border-green-200">
            <div className="text-sm text-green-700">Annuel</div>
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

        {/* Thèse */}
        <div className="mb-6">
          <h3 className="text-sm uppercase tracking-wide text-gray-500 mb-2">Thèse économique</h3>
          <div className="bg-gray-50 rounded-xl p-4 border border-gray-200">
            <p className="text-gray-800">{thesis}</p>
          </div>
        </div>

        {/* Action */}
        <div className="mb-6">
          <h3 className="text-sm uppercase tracking-wide text-gray-500 mb-2">Action recommandée</h3>
          <div className="bg-amber-50 rounded-xl p-4 border border-amber-200">
            <p className="text-amber-900 font-medium">{actionRecommendation}</p>
          </div>
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

      {/* Action buttons */}
      <div className="border-t border-gray-200 p-4 bg-gray-50 flex gap-3">
        {isDemo && (
          <div className="flex-1 bg-gray-200 text-gray-500 py-3 px-4 rounded-lg font-medium text-center cursor-not-allowed">
            Sourcing désactivé (mode démo)
          </div>
        )}
        {!isDemo && (
          <button
            onClick={onStartSourcing}
            className="flex-1 bg-primary-600 text-white py-3 px-4 rounded-lg font-medium hover:bg-primary-700 transition-colors"
          >
            Lancer le sourcing
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
          {isSaved ? 'Sauvegarde' : 'Sauvegarder'}
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
    </div>
  );
}
