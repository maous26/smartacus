'use client';

import { useState, useEffect } from 'react';
import { SpecBundle } from '@/types/opportunity';
import api from '@/lib/api';

interface ProductSpecPanelProps {
  asin: string;
  isDemo?: boolean;
}

type TabKey = 'oem' | 'qc' | 'rfq';

const PRIORITY_COLORS: Record<string, string> = {
  CRITICAL: 'bg-red-100 text-red-800 border-red-300',
  HIGH: 'bg-orange-100 text-orange-800 border-orange-300',
  MEDIUM: 'bg-yellow-100 text-yellow-800 border-yellow-300',
  LOW: 'bg-gray-100 text-gray-600 border-gray-300',
  MANDATORY: 'bg-red-100 text-red-800 border-red-300',
  RECOMMENDED: 'bg-blue-100 text-blue-700 border-blue-300',
};

function PriorityBadge({ priority }: { priority: string }) {
  const colors = PRIORITY_COLORS[priority] || 'bg-gray-100 text-gray-600 border-gray-300';
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded border ${colors}`}>
      {priority}
    </span>
  );
}

export function ProductSpecPanel({ asin, isDemo = false }: ProductSpecPanelProps) {
  const [spec, setSpec] = useState<SpecBundle | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>('oem');
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    if (isDemo) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    api.getSpecBundle(asin)
      .then((data) => {
        if (!cancelled) setSpec(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message?.includes('404') ? null : err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [asin, isDemo]);

  const handleCopy = async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(label);
      setTimeout(() => setCopied(null), 2000);
    } catch {
      // Fallback
      const area = document.createElement('textarea');
      area.value = text;
      document.body.appendChild(area);
      area.select();
      document.execCommand('copy');
      document.body.removeChild(area);
      setCopied(label);
      setTimeout(() => setCopied(null), 2000);
    }
  };

  // Don't render if demo mode, loading with no data, or no spec available
  if (isDemo) return null;
  if (loading) {
    return (
      <div className="mb-6">
        <h3 className="text-sm uppercase tracking-wide text-gray-500 mb-3">Spec Produit OEM</h3>
        <div className="bg-gray-50 rounded-xl p-6 border border-gray-200 text-center text-gray-400">
          Chargement...
        </div>
      </div>
    );
  }
  if (error) return null;
  if (!spec || !spec.bundle || spec.totalRequirements === 0) return null;

  const { bundle } = spec;
  const tabs: { key: TabKey; label: string; count: number }[] = [
    { key: 'oem', label: 'Spec OEM', count: spec.totalRequirements },
    { key: 'qc', label: 'QC Checklist', count: spec.totalQcTests },
    { key: 'rfq', label: 'Message RFQ', count: 0 },
  ];

  return (
    <div className="mb-6" data-panel="spec">
      <h3 className="text-sm uppercase tracking-wide text-gray-500 mb-3">
        Spec Produit OEM
        <span className="text-xs font-normal text-gray-400 ml-2">
          v{spec.mappingVersion} &middot; {spec.reviewsAnalyzed} avis
        </span>
      </h3>

      <div className="bg-white rounded-xl border border-indigo-200 overflow-hidden">
        {/* Tab bar */}
        <div className="flex border-b border-indigo-100">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex-1 py-2.5 text-sm font-medium transition-colors ${
                activeTab === tab.key
                  ? 'bg-indigo-50 text-indigo-700 border-b-2 border-indigo-500'
                  : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
              }`}
            >
              {tab.label}
              {tab.count > 0 && (
                <span className={`ml-1.5 text-xs px-1.5 py-0.5 rounded-full ${
                  activeTab === tab.key ? 'bg-indigo-200 text-indigo-800' : 'bg-gray-200 text-gray-600'
                }`}>
                  {tab.count}
                </span>
              )}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="p-4">
          {/* OEM Spec tab */}
          {activeTab === 'oem' && (
            <div>
              {/* Bloc A — Defect corrections */}
              {bundle.oem_spec.bloc_a.length > 0 && (
                <div className="mb-4">
                  <div className="text-xs font-semibold text-gray-500 uppercase mb-2">
                    Bloc A — Corrections (Defauts)
                  </div>
                  <div className="space-y-2">
                    {bundle.oem_spec.bloc_a.map((req, i) => (
                      <div key={i} className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1">
                            <div className="text-sm font-medium text-gray-800">{req.requirement}</div>
                            {req.material && (
                              <div className="text-xs text-gray-500 mt-1">
                                Materiau: {req.material}
                              </div>
                            )}
                            {req.tolerance && (
                              <div className="text-xs text-gray-500">
                                Tolerance: {req.tolerance}
                              </div>
                            )}
                          </div>
                          <div className="flex items-center gap-2 flex-shrink-0">
                            <PriorityBadge priority={req.priority} />
                            <span className="text-xs text-gray-400 font-mono">{req.source}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Bloc B — Feature enhancements */}
              {bundle.oem_spec.bloc_b.length > 0 && (
                <div className="mb-4">
                  <div className="text-xs font-semibold text-gray-500 uppercase mb-2">
                    Bloc B — Ameliorations (Features)
                  </div>
                  <div className="space-y-2">
                    {bundle.oem_spec.bloc_b.map((req, i) => (
                      <div key={i} className="bg-blue-50 rounded-lg p-3 border border-blue-200">
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1">
                            <div className="text-sm font-medium text-blue-900">{req.requirement}</div>
                            {req.material && (
                              <div className="text-xs text-blue-600 mt-1">
                                Materiau: {req.material}
                              </div>
                            )}
                          </div>
                          <div className="flex items-center gap-2 flex-shrink-0">
                            <PriorityBadge priority={req.priority} />
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Copy button */}
              <button
                onClick={() => handleCopy(spec.oemSpecText, 'spec')}
                className="w-full mt-2 py-2 text-sm font-medium text-indigo-600 bg-indigo-50 rounded-lg hover:bg-indigo-100 transition-colors border border-indigo-200"
              >
                {copied === 'spec' ? 'Copie !' : 'Copier Spec (Markdown)'}
              </button>
            </div>
          )}

          {/* QC Checklist tab */}
          {activeTab === 'qc' && (
            <div>
              {/* Group by category */}
              {(() => {
                const categories = new Map<string, typeof bundle.qc_checklist.tests>();
                for (const test of bundle.qc_checklist.tests) {
                  const cat = test.category;
                  if (!categories.has(cat)) categories.set(cat, []);
                  categories.get(cat)!.push(test);
                }

                const catLabels: Record<string, string> = {
                  vibration: 'Vibration & Chocs',
                  cycles: 'Endurance & Cycles',
                  thermal: 'Thermique',
                  surface: 'Surface & Visuel',
                  load: 'Charge & Retention',
                  compatibility: 'Compatibilite',
                };

                return Array.from(categories.entries()).map(([cat, tests]) => (
                  <div key={cat} className="mb-4">
                    <div className="text-xs font-semibold text-gray-500 uppercase mb-2">
                      {catLabels[cat] || cat}
                    </div>
                    <div className="space-y-2">
                      {tests.map((test, i) => (
                        <div key={i} className="bg-gray-50 rounded-lg p-3 border border-gray-200">
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-sm font-medium text-gray-800">{test.name}</span>
                            <PriorityBadge priority={test.priority} />
                          </div>
                          <div className="text-xs text-gray-500">
                            <div>Methode: {test.method}</div>
                            <div>Critere: {test.passCriterion}</div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ));
              })()}

              {/* Summary */}
              <div className="flex items-center justify-between mt-3 pt-3 border-t border-gray-200 text-xs text-gray-500">
                <span>
                  {bundle.qc_checklist.tests.filter(t => t.priority === 'MANDATORY').length} obligatoires &middot;{' '}
                  {bundle.qc_checklist.tests.filter(t => t.priority === 'RECOMMENDED').length} recommandes
                </span>
              </div>

              <button
                onClick={() => handleCopy(spec.qcChecklistText, 'qc')}
                className="w-full mt-2 py-2 text-sm font-medium text-indigo-600 bg-indigo-50 rounded-lg hover:bg-indigo-100 transition-colors border border-indigo-200"
              >
                {copied === 'qc' ? 'Copie !' : 'Copier QC Checklist'}
              </button>
            </div>
          )}

          {/* RFQ Message tab */}
          {activeTab === 'rfq' && (
            <div>
              <div className="bg-gray-50 rounded-lg p-4 border border-gray-200 mb-3">
                <div className="text-xs font-semibold text-gray-500 uppercase mb-2">Objet</div>
                <div className="text-sm text-gray-800 font-medium">
                  {bundle.rfq_message.subject}
                </div>
              </div>

              <div className="bg-gray-50 rounded-lg p-4 border border-gray-200 mb-3">
                <div className="text-xs font-semibold text-gray-500 uppercase mb-2">Message</div>
                <pre className="text-sm text-gray-800 whitespace-pre-wrap font-sans leading-relaxed">
                  {bundle.rfq_message.body}
                </pre>
              </div>

              <button
                onClick={() => handleCopy(
                  `Subject: ${bundle.rfq_message.subject}\n\n${bundle.rfq_message.body}`,
                  'rfq'
                )}
                className="w-full mt-2 py-2 text-sm font-medium text-indigo-600 bg-indigo-50 rounded-lg hover:bg-indigo-100 transition-colors border border-indigo-200"
              >
                {copied === 'rfq' ? 'Copie !' : 'Copier RFQ complet'}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
