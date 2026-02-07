'use client';

/**
 * PostMortemReminder Component
 * ============================
 *
 * V3.2: Post-mortem loop for risk overrides.
 *
 * Philosophy: "Learning from decisions requires reflection.
 * After 14 days, we ask: 'Comment ça s'est passé?'"
 *
 * Displays pending post-mortems and allows users to record outcomes.
 */

import { useState, useEffect } from 'react';
import { api } from '@/lib/api';

interface PendingOverride {
  id: string;
  asin: string;
  confidenceLevel: string;
  hypothesis: string;
  hypothesisReason: string;
  missingInfo: string[];
  createdAt: string;
  daysAgo: number;
  productTitle: string | null;
  productBrand: string | null;
}

interface PostMortemReminderProps {
  onComplete?: () => void;
}

type Outcome = 'success' | 'partial' | 'failure' | 'abandoned';

const OUTCOME_CONFIG: Record<Outcome, { label: string; emoji: string; color: string; description: string }> = {
  success: {
    label: 'Bon',
    emoji: '✅',
    color: 'bg-emerald-100 text-emerald-800 border-emerald-300 hover:bg-emerald-200',
    description: 'La décision s\'est avérée positive',
  },
  partial: {
    label: 'Mitigé',
    emoji: '🟡',
    color: 'bg-amber-100 text-amber-800 border-amber-300 hover:bg-amber-200',
    description: 'Résultats mixtes ou en attente',
  },
  failure: {
    label: 'Mauvais',
    emoji: '❌',
    color: 'bg-red-100 text-red-800 border-red-300 hover:bg-red-200',
    description: 'La décision n\'a pas fonctionné',
  },
  abandoned: {
    label: 'Abandonné',
    emoji: '⏹️',
    color: 'bg-gray-100 text-gray-800 border-gray-300 hover:bg-gray-200',
    description: 'Projet abandonné avant conclusion',
  },
};

export function PostMortemReminder({ onComplete }: PostMortemReminderProps) {
  const [pendingOverrides, setPendingOverrides] = useState<PendingOverride[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [selectedOutcome, setSelectedOutcome] = useState<Outcome | null>(null);
  const [notes, setNotes] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    fetchPendingPostMortems();
  }, []);

  const fetchPendingPostMortems = async () => {
    try {
      setIsLoading(true);
      const response = await api.getPendingPostMortems();
      // Transform snake_case to camelCase
      const overrides = response.overrides.map((o: any) => ({
        id: o.id,
        asin: o.asin,
        confidenceLevel: o.confidence_level,
        hypothesis: o.hypothesis,
        hypothesisReason: o.hypothesis_reason,
        missingInfo: o.missing_info,
        createdAt: o.created_at,
        daysAgo: o.days_ago,
        productTitle: o.product_title,
        productBrand: o.product_brand,
      }));
      setPendingOverrides(overrides);
    } catch (e) {
      console.error('Failed to fetch pending post-mortems:', e);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSubmitOutcome = async () => {
    if (!selectedOutcome || !pendingOverrides[currentIndex]) return;

    setIsSubmitting(true);
    try {
      await api.recordOverrideOutcome(pendingOverrides[currentIndex].id, {
        outcome: selectedOutcome,
        notes: notes || undefined,
      });

      // Move to next or close
      if (currentIndex < pendingOverrides.length - 1) {
        setCurrentIndex(currentIndex + 1);
        setSelectedOutcome(null);
        setNotes('');
      } else {
        // All done
        if (onComplete) onComplete();
      }
    } catch (e) {
      console.error('Failed to record outcome:', e);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSkip = () => {
    if (currentIndex < pendingOverrides.length - 1) {
      setCurrentIndex(currentIndex + 1);
      setSelectedOutcome(null);
      setNotes('');
    } else if (onComplete) {
      onComplete();
    }
  };

  if (isLoading) {
    return (
      <div className="animate-pulse bg-slate-100 rounded-xl p-6 border border-slate-200">
        <div className="h-4 bg-slate-200 rounded w-1/2 mb-4"></div>
        <div className="h-4 bg-slate-200 rounded w-3/4"></div>
      </div>
    );
  }

  if (pendingOverrides.length === 0) {
    return null; // No pending post-mortems
  }

  const current = pendingOverrides[currentIndex];

  return (
    <div className="bg-indigo-50 rounded-xl border border-indigo-200 overflow-hidden">
      {/* Header */}
      <div className="bg-indigo-100 px-4 py-3 border-b border-indigo-200">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-lg">📝</span>
            <span className="font-semibold text-indigo-900">
              Post-mortem en attente
            </span>
          </div>
          <span className="text-sm text-indigo-600">
            {currentIndex + 1} / {pendingOverrides.length}
          </span>
        </div>
      </div>

      {/* Content */}
      <div className="p-4">
        <div className="mb-4">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-mono text-sm bg-indigo-200 text-indigo-800 px-2 py-0.5 rounded">
              {current.asin}
            </span>
            <span className="text-xs text-indigo-600">
              il y a {current.daysAgo} jours
            </span>
          </div>
          {current.productTitle && (
            <h3 className="font-medium text-indigo-900 line-clamp-1">
              {current.productTitle}
            </h3>
          )}
        </div>

        <div className="bg-white rounded-lg p-3 mb-4 border border-indigo-100">
          <div className="text-xs uppercase tracking-wide text-indigo-500 mb-1">
            Votre hypothèse
          </div>
          <p className="text-sm text-indigo-900">{current.hypothesis}</p>
          <div className="mt-2 text-xs text-indigo-600">
            Niveau de confiance: <span className="capitalize">{current.confidenceLevel}</span>
          </div>
        </div>

        {/* Outcome buttons */}
        <div className="mb-4">
          <div className="text-sm font-medium text-indigo-800 mb-2">
            Comment ça s'est passé ?
          </div>
          <div className="grid grid-cols-4 gap-2">
            {(Object.entries(OUTCOME_CONFIG) as [Outcome, typeof OUTCOME_CONFIG[Outcome]][]).map(
              ([key, config]) => (
                <button
                  key={key}
                  onClick={() => setSelectedOutcome(key)}
                  className={`p-3 rounded-lg border-2 text-center transition-all ${
                    selectedOutcome === key
                      ? `${config.color} border-current ring-2 ring-offset-1`
                      : `${config.color} border-transparent`
                  }`}
                  title={config.description}
                >
                  <div className="text-xl mb-1">{config.emoji}</div>
                  <div className="text-xs font-medium">{config.label}</div>
                </button>
              )
            )}
          </div>
        </div>

        {/* Notes */}
        {selectedOutcome && (
          <div className="mb-4">
            <label className="text-sm font-medium text-indigo-800 mb-1 block">
              Notes (optionnel)
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Ce que vous avez appris..."
              className="w-full p-2 rounded-lg border border-indigo-200 text-sm resize-none focus:ring-2 focus:ring-indigo-300 focus:border-indigo-300"
              rows={2}
            />
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2">
          <button
            onClick={handleSubmitOutcome}
            disabled={!selectedOutcome || isSubmitting}
            className={`flex-1 py-2 px-4 rounded-lg font-medium transition-colors ${
              selectedOutcome && !isSubmitting
                ? 'bg-indigo-600 text-white hover:bg-indigo-700'
                : 'bg-indigo-200 text-indigo-400 cursor-not-allowed'
            }`}
          >
            {isSubmitting ? 'Enregistrement...' : 'Enregistrer'}
          </button>
          <button
            onClick={handleSkip}
            className="py-2 px-4 rounded-lg font-medium text-indigo-600 hover:bg-indigo-100 transition-colors"
          >
            Plus tard
          </button>
        </div>
      </div>

      {/* Footer tip */}
      <div className="bg-indigo-100/50 px-4 py-2 border-t border-indigo-200">
        <p className="text-xs text-indigo-600 text-center italic">
          Ce feedback est pour vous. Il aide à comprendre vos patterns de décision.
        </p>
      </div>
    </div>
  );
}
