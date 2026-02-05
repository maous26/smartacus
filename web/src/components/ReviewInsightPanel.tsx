'use client';

import { useState, useEffect } from 'react';
import { ReviewProfile } from '@/types/opportunity';
import api from '@/lib/api';

interface ReviewInsightPanelProps {
  asin: string;
  isDemo?: boolean;
}

const DEFECT_LABELS: Record<string, string> = {
  mechanical_failure: 'Casse mecanique',
  poor_grip: 'Prise insuffisante',
  installation_issue: 'Installation difficile',
  compatibility_issue: 'Compatibilite',
  material_quality: 'Qualite materiaux',
  vibration_noise: 'Vibration / Bruit',
  heat_issue: 'Surchauffe',
  size_fit: 'Taille / Encombrement',
  durability: 'Durabilite',
};

const PAIN_COLORS: Record<string, string> = {
  mechanical_failure: 'bg-red-100 text-red-800 border-red-300',
  poor_grip: 'bg-red-100 text-red-800 border-red-300',
  durability: 'bg-orange-100 text-orange-800 border-orange-300',
  installation_issue: 'bg-orange-100 text-orange-800 border-orange-300',
  compatibility_issue: 'bg-yellow-100 text-yellow-800 border-yellow-300',
  material_quality: 'bg-yellow-100 text-yellow-800 border-yellow-300',
  vibration_noise: 'bg-blue-100 text-blue-800 border-blue-300',
  heat_issue: 'bg-orange-100 text-orange-800 border-orange-300',
  size_fit: 'bg-gray-100 text-gray-700 border-gray-300',
};

function SeverityBar({ score }: { score: number }) {
  const color = score > 0.7 ? 'bg-red-500' : score > 0.4 ? 'bg-orange-400' : 'bg-yellow-400';
  return (
    <div className="h-1.5 w-20 bg-gray-200 rounded-full overflow-hidden">
      <div className={`h-full ${color} transition-all duration-300`} style={{ width: `${Math.min(score * 100, 100)}%` }} />
    </div>
  );
}

function ScoreGauge({ score }: { score: number }) {
  const percent = Math.round(score * 100);
  const color = score > 0.6 ? 'text-emerald-600' : score > 0.3 ? 'text-yellow-600' : 'text-red-600';
  const bg = score > 0.6 ? 'bg-emerald-500' : score > 0.3 ? 'bg-yellow-500' : 'bg-red-500';
  return (
    <div className="flex items-center gap-3">
      <div className="flex-1 h-2.5 bg-gray-200 rounded-full overflow-hidden">
        <div className={`h-full ${bg} transition-all duration-500 rounded-full`} style={{ width: `${percent}%` }} />
      </div>
      <span className={`text-lg font-bold ${color}`}>{percent}%</span>
    </div>
  );
}

export function ReviewInsightPanel({ asin, isDemo = false }: ReviewInsightPanelProps) {
  const [profile, setProfile] = useState<ReviewProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isDemo) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    api.getReviewProfile(asin)
      .then((data) => { if (!cancelled) setProfile(data); })
      .catch((err) => { if (!cancelled) setError(err.message?.includes('404') ? null : err.message); })
      .finally(() => { if (!cancelled) setLoading(false); });

    return () => { cancelled = true; };
  }, [asin, isDemo]);

  if (isDemo) return null;
  if (loading) {
    return (
      <div className="mb-6">
        <h3 className="text-sm uppercase tracking-wide text-gray-500 mb-3">Intelligence Reviews</h3>
        <div className="bg-gray-50 rounded-xl p-6 border border-gray-200 text-center text-gray-400">
          Chargement...
        </div>
      </div>
    );
  }
  if (error) return null;
  if (!profile || !profile.reviewsReady || profile.topDefects.length === 0) return null;

  const painColors = PAIN_COLORS[profile.dominantPain || ''] || 'bg-gray-100 text-gray-700 border-gray-300';

  return (
    <div className="mb-6">
      <h3 className="text-sm uppercase tracking-wide text-gray-500 mb-3">
        Intelligence Reviews
        <span className="text-xs font-normal text-gray-400 ml-2">
          {profile.reviewsAnalyzed} avis &middot; {profile.negativeReviewsAnalyzed} negatifs
        </span>
      </h3>

      <div className="bg-white rounded-xl border border-amber-200 overflow-hidden">
        {/* Header: Improvement Score + Dominant Pain */}
        <div className="p-4 border-b border-amber-100">
          <div className="flex items-center justify-between gap-4 mb-3">
            <div className="flex-1">
              <div className="text-xs font-semibold text-gray-500 uppercase mb-1.5">
                Potentiel d'amelioration
              </div>
              <ScoreGauge score={profile.improvementScore} />
            </div>
            {profile.dominantPain && (
              <div className="flex-shrink-0">
                <div className="text-xs font-semibold text-gray-500 uppercase mb-1.5">
                  Douleur dominante
                </div>
                <span className={`text-xs font-semibold px-2.5 py-1 rounded border ${painColors}`}>
                  {DEFECT_LABELS[profile.dominantPain] || profile.dominantPain}
                </span>
              </div>
            )}
          </div>
        </div>

        {/* Defects table */}
        <div className="p-4 border-b border-amber-100">
          <div className="text-xs font-semibold text-gray-500 uppercase mb-2">
            Defauts detectes ({profile.topDefects.length})
          </div>
          <div className="space-y-2">
            {profile.topDefects.map((defect, i) => (
              <div key={i} className="flex items-center gap-3 text-sm">
                <span className="w-36 font-medium text-gray-800 truncate">
                  {DEFECT_LABELS[defect.defectType] || defect.defectType}
                </span>
                <span className="w-12 text-right text-gray-500 text-xs">
                  {defect.frequency}x
                </span>
                <span className="w-16 text-right text-gray-400 text-xs">
                  {Math.round(defect.frequencyRate * 100)}%
                </span>
                <SeverityBar score={defect.severityScore} />
                {defect.exampleQuotes.length > 0 && (
                  <span className="flex-1 text-xs text-gray-400 italic truncate" title={defect.exampleQuotes[0]}>
                    &ldquo;{defect.exampleQuotes[0].slice(0, 80)}&rdquo;
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Feature requests */}
        {profile.missingFeatures.length > 0 && (
          <div className="p-4 border-b border-amber-100">
            <div className="text-xs font-semibold text-gray-500 uppercase mb-2">
              Features demandees ({profile.missingFeatures.length})
            </div>
            <div className="space-y-2">
              {profile.missingFeatures.map((feat, i) => (
                <div key={i} className="flex items-center gap-3 text-sm">
                  <span className="flex-1 font-medium text-blue-800">
                    {feat.feature}
                  </span>
                  <span className="text-xs text-gray-500">
                    {feat.mentions} mentions
                  </span>
                  <span className="text-xs font-mono text-gray-400">
                    str={feat.wishStrength.toFixed(1)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Thesis fragment */}
        {profile.thesisFragment && (
          <div className="p-3 bg-amber-50 text-xs text-amber-800">
            {profile.thesisFragment}
          </div>
        )}
      </div>
    </div>
  );
}
