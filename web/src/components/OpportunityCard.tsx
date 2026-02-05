'use client';

import { Opportunity } from '@/types/opportunity';
import { UrgencyBadge } from './UrgencyBadge';
import { ScoreRing } from './ScoreRing';
import { formatNumber, formatPrice, formatCurrency } from '@/lib/format';

interface OpportunityCardProps {
  opportunity: Opportunity;
  isSelected?: boolean;
  onClick?: () => void;
  isDemo?: boolean;
}

export function OpportunityCard({
  opportunity,
  isSelected = false,
  onClick,
  isDemo = false,
}: OpportunityCardProps) {
  const {
    rank,
    asin,
    title,
    finalScore,
    windowDays,
    urgencyLevel,
    riskAdjustedValue,
    thesis,
    actionRecommendation,
    amazonPrice,
    reviewCount,
    rating,
  } = opportunity;

  return (
    <div
      onClick={onClick}
      className={`
        relative bg-white rounded-xl border-2 p-5 cursor-pointer transition-all duration-200
        hover:shadow-lg hover:border-primary-300
        ${isSelected ? 'border-primary-500 shadow-lg ring-2 ring-primary-200' : 'border-gray-200'}
      `}
    >
      {/* DEMO watermark */}
      {isDemo && (
        <div className="absolute top-2 right-2 bg-amber-100 text-amber-600 text-[10px] font-bold px-1.5 py-0.5 rounded border border-amber-300 uppercase tracking-wider">
          Demo
        </div>
      )}

      {/* Header: Rank + Score + Urgency */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          {/* Rank badge */}
          <div className="flex items-center justify-center w-10 h-10 rounded-full bg-gray-900 text-white font-bold text-lg">
            {rank}
          </div>

          {/* ASIN & Title */}
          <div>
            <div className="font-mono text-sm text-gray-500">{asin}</div>
            {title && (
              <div className="font-medium text-gray-900 max-w-xs truncate" title={title}>
                {title}
              </div>
            )}
          </div>
        </div>

        {/* Score ring */}
        <ScoreRing score={finalScore} size="md" />
      </div>

      {/* Urgency badge */}
      <div className="mb-4">
        <UrgencyBadge level={urgencyLevel} windowDays={windowDays} />
      </div>

      {/* Value */}
      <div className="mb-4 p-3 bg-gradient-to-r from-emerald-50 to-green-50 rounded-lg border border-emerald-200">
        <div className="text-sm text-emerald-700 font-medium">Valeur estimée</div>
        <div className="text-2xl font-bold text-emerald-600">
          {formatCurrency(Math.round(riskAdjustedValue))}<span className="text-sm font-normal text-emerald-500">/an</span>
        </div>
      </div>

      {/* Thesis */}
      <div className="mb-4">
        <div className="text-xs uppercase tracking-wide text-gray-500 mb-1">Thèse</div>
        <div className="text-sm text-gray-700">{thesis}</div>
      </div>

      {/* Action */}
      <div className="p-3 bg-gray-50 rounded-lg border border-gray-200">
        <div className="text-xs uppercase tracking-wide text-gray-500 mb-1">Action recommandée</div>
        <div className="text-sm font-medium text-gray-900">{actionRecommendation}</div>
      </div>

      {/* Footer: Metrics */}
      {(amazonPrice || reviewCount || rating) && (
        <div className="mt-4 pt-4 border-t border-gray-100 flex items-center gap-4 text-sm text-gray-500">
          {amazonPrice && (
            <div>
              <span className="font-medium text-gray-700">{formatPrice(amazonPrice)}</span>
              <span className="ml-1">prix</span>
            </div>
          )}
          {reviewCount && (
            <div>
              <span className="font-medium text-gray-700">{formatNumber(reviewCount)}</span>
              <span className="ml-1">avis</span>
            </div>
          )}
          {rating && (
            <div>
              <span className="font-medium text-gray-700">{rating.toFixed(1)}</span>
              <span className="ml-1">★</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
