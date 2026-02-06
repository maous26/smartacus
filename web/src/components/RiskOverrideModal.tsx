'use client';

/**
 * RiskOverrideModal Component
 * ===========================
 *
 * Modal displayed when user wants to proceed despite incomplete analysis.
 * Forces explicit acknowledgment of risks and captures user hypothesis.
 *
 * Philosophy: "Les gens prendront des risques. Le rôle du système n'est pas
 * de les infantiliser, mais de rendre le risque conscient et traçable."
 */

import { useState } from 'react';
import { ConfidenceLevel } from './ConfidenceState';

interface RiskOverrideModalProps {
  asin: string;
  confidenceLevel: ConfidenceLevel;
  missingInfo: string[];
  onConfirm: (hypothesis: string, reason: HypothesisReason) => void;
  onCancel: () => void;
}

export type HypothesisReason =
  | 'product_improvement'
  | 'marketing_advantage'
  | 'low_volume_test'
  | 'market_knowledge'
  | 'other';

const HYPOTHESIS_OPTIONS: { value: HypothesisReason; label: string; description: string }[] = [
  {
    value: 'product_improvement',
    label: 'Amélioration produit',
    description: 'Je pense pouvoir résoudre les défauts identifiés',
  },
  {
    value: 'marketing_advantage',
    label: 'Avantage marketing',
    description: 'Je parie sur mon exécution marketing',
  },
  {
    value: 'low_volume_test',
    label: 'Test faible volume',
    description: 'Je veux tester à petite échelle',
  },
  {
    value: 'market_knowledge',
    label: 'Connaissance marché',
    description: 'Je connais déjà cette niche',
  },
  {
    value: 'other',
    label: 'Autre',
    description: 'Raison personnelle',
  },
];

export function RiskOverrideModal({
  asin,
  confidenceLevel,
  missingInfo,
  onConfirm,
  onCancel,
}: RiskOverrideModalProps) {
  const [selectedReason, setSelectedReason] = useState<HypothesisReason | null>(null);
  const [customHypothesis, setCustomHypothesis] = useState('');
  const [acknowledged, setAcknowledged] = useState(false);

  const canProceed = selectedReason && acknowledged && (selectedReason !== 'other' || customHypothesis.trim());

  const handleConfirm = () => {
    if (!canProceed || !selectedReason) return;

    const hypothesis = selectedReason === 'other'
      ? customHypothesis
      : HYPOTHESIS_OPTIONS.find(o => o.value === selectedReason)?.label || '';

    onConfirm(hypothesis, selectedReason);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-lg w-full max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="bg-amber-500 text-white p-6">
          <div className="flex items-center gap-3">
            <span className="text-3xl">⚠️</span>
            <div>
              <h2 className="text-xl font-bold">Je choisis d'avancer malgré les risques</h2>
              <p className="text-amber-100 text-sm mt-1">ASIN: {asin}</p>
            </div>
          </div>
        </div>

        {/* Warning recap */}
        <div className="p-6 border-b border-gray-200">
          <div className="bg-red-50 border border-red-200 rounded-xl p-4">
            <h3 className="font-semibold text-red-800 mb-3">
              Vous êtes sur le point d'avancer alors que :
            </h3>
            <ul className="space-y-2">
              {missingInfo.map((info, idx) => (
                <li key={idx} className="flex items-start gap-2 text-red-700 text-sm">
                  <span className="text-red-500 mt-0.5">✗</span>
                  {info}
                </li>
              ))}
              <li className="flex items-start gap-2 text-red-700 text-sm">
                <span className="text-red-500 mt-0.5">✗</span>
                Niveau de confiance : <span className="font-semibold uppercase">{confidenceLevel}</span>
              </li>
            </ul>
            <p className="mt-4 text-red-800 text-sm font-medium">
              Smartacus ne peut pas confirmer la solidité de cette opportunité.
            </p>
          </div>
        </div>

        {/* Hypothesis selection */}
        <div className="p-6 border-b border-gray-200">
          <h3 className="font-semibold text-gray-900 mb-4">
            Quelle est votre hypothèse principale ?
          </h3>
          <div className="space-y-2">
            {HYPOTHESIS_OPTIONS.map((option) => (
              <label
                key={option.value}
                className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                  selectedReason === option.value
                    ? 'border-amber-500 bg-amber-50'
                    : 'border-gray-200 hover:bg-gray-50'
                }`}
              >
                <input
                  type="radio"
                  name="hypothesis"
                  value={option.value}
                  checked={selectedReason === option.value}
                  onChange={() => setSelectedReason(option.value)}
                  className="mt-1"
                />
                <div>
                  <div className="font-medium text-gray-900">{option.label}</div>
                  <div className="text-sm text-gray-500">{option.description}</div>
                </div>
              </label>
            ))}
          </div>

          {selectedReason === 'other' && (
            <textarea
              value={customHypothesis}
              onChange={(e) => setCustomHypothesis(e.target.value)}
              placeholder="Décrivez votre hypothèse..."
              className="mt-4 w-full p-3 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
              rows={3}
            />
          )}
        </div>

        {/* Acknowledgment */}
        <div className="p-6 border-b border-gray-200">
          <label className="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={acknowledged}
              onChange={(e) => setAcknowledged(e.target.checked)}
              className="mt-1"
            />
            <span className="text-sm text-gray-700">
              Je comprends que cette décision est basée sur des données incomplètes et que
              Smartacus n'endosse pas cette opportunité. Je prends cette décision en
              connaissance de cause.
            </span>
          </label>
        </div>

        {/* Actions */}
        <div className="p-6 flex gap-3">
          <button
            onClick={onCancel}
            className="flex-1 py-3 px-4 border border-gray-300 rounded-lg font-medium text-gray-700 hover:bg-gray-50 transition-colors"
          >
            Annuler
          </button>
          <button
            onClick={handleConfirm}
            disabled={!canProceed}
            className={`flex-1 py-3 px-4 rounded-lg font-medium transition-colors ${
              canProceed
                ? 'bg-amber-500 text-white hover:bg-amber-600'
                : 'bg-gray-200 text-gray-400 cursor-not-allowed'
            }`}
          >
            Je continue malgré tout
          </button>
        </div>
      </div>
    </div>
  );
}
