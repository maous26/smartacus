'use client';

import { useState, useEffect } from 'react';
import { Header } from '@/components/Header';
import { OpportunityCard } from '@/components/OpportunityCard';
import { OpportunityDetail } from '@/components/OpportunityDetail';
import { AgentChat } from '@/components/AgentChat';
import { mockShortlistResponse, mockPipelineStatus } from '@/lib/mockData';
import { Opportunity, ShortlistResponse, PipelineStatus } from '@/types/opportunity';
import { formatNumber, formatDate } from '@/lib/format';
import { api } from '@/lib/api';

export default function Home() {
  const [selectedOpportunity, setSelectedOpportunity] = useState<Opportunity | null>(null);
  const [shortlistData, setShortlistData] = useState<ShortlistResponse>(mockShortlistResponse);
  const [pipelineStatus, setPipelineStatus] = useState<PipelineStatus>(mockPipelineStatus);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dataSource, setDataSource] = useState<'api' | 'mock'>('mock');
  const [showAgentChat, setShowAgentChat] = useState(false);

  // Fetch data from API
  useEffect(() => {
    async function fetchData() {
      try {
        setIsLoading(true);
        setError(null);

        const [shortlist, status] = await Promise.all([
          api.getShortlist(),
          api.getPipelineStatus(),
        ]);

        setShortlistData(shortlist);
        setPipelineStatus(status);
        setDataSource('api');
      } catch (err) {
        console.warn('API unavailable, using mock data:', err);
        // Fallback to mock data (already set as default)
        setDataSource('mock');
        setError('Backend non disponible - Données de démonstration');
      } finally {
        setIsLoading(false);
      }
    }

    fetchData();
  }, []);

  const { summary, opportunities } = shortlistData;

  return (
    <div className="min-h-screen bg-gray-50">
      <Header pipelineStatus={pipelineStatus} />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Data source indicator */}
        {dataSource === 'mock' && (
          <div className="mb-4 px-4 py-2 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800">
            <span className="font-medium">Mode démo:</span> Données de démonstration.
            {error && <span className="ml-2 text-amber-600">({error})</span>}
          </div>
        )}

        {dataSource === 'api' && (
          <div className="mb-4 px-4 py-2 bg-green-50 border border-green-200 rounded-lg text-sm text-green-800">
            <span className="font-medium">Connecté:</span> Données temps réel depuis l'API backend
          </div>
        )}

        {/* Summary bar */}
        <div className="bg-white rounded-2xl shadow-sm border border-gray-200 p-6 mb-8">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Shortlist Smartacus</h1>
              <p className="text-gray-500 mt-1">
                Opportunités à exécuter, classées par valeur × urgence
              </p>
            </div>

            <div className="flex items-center gap-8">
              <div className="text-center">
                <div className="text-3xl font-bold text-gray-900">{summary.count}</div>
                <div className="text-sm text-gray-500">Opportunités</div>
              </div>
              <div className="text-center">
                <div className="text-3xl font-bold text-emerald-600">
                  ${formatNumber(Math.round(summary.totalPotentialValue))}
                </div>
                <div className="text-sm text-gray-500">Valeur totale/an</div>
              </div>
              <div className="text-center">
                <div className="text-sm text-gray-500">Critères</div>
                <div className="text-xs text-gray-400">
                  Score ≥ {summary.criteria.minScore} | Valeur ≥ ${formatNumber(summary.criteria.minValue)}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Loading state */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
            <span className="ml-3 text-gray-600">Chargement des opportunités...</span>
          </div>
        )}

        {/* Main content: List + Detail */}
        {!isLoading && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Opportunities list */}
            <div className="space-y-4">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-lg font-semibold text-gray-900">
                  Top {opportunities.length} Opportunités
                </h2>
                <span className="text-sm text-gray-500">
                  Généré le {formatDate(summary.generatedAt)}
                </span>
              </div>

              {opportunities.map((opp) => (
                <OpportunityCard
                  key={opp.asin}
                  opportunity={opp}
                  isSelected={selectedOpportunity?.asin === opp.asin}
                  onClick={() => setSelectedOpportunity(opp)}
                />
              ))}
            </div>

            {/* Detail panel */}
            <div className="lg:sticky lg:top-24 lg:self-start">
              {selectedOpportunity ? (
                <div className="space-y-4">
                  <OpportunityDetail
                    opportunity={selectedOpportunity}
                    onClose={() => setSelectedOpportunity(null)}
                  />

                  {/* Agent Chat Button */}
                  <button
                    onClick={() => setShowAgentChat(true)}
                    className="w-full flex items-center justify-center gap-3 px-6 py-4 bg-gradient-to-r from-primary-600 to-primary-700 text-white rounded-xl shadow-lg hover:from-primary-700 hover:to-primary-800 transition-all group"
                  >
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                    </svg>
                    <div className="text-left">
                      <div className="font-semibold">Analyser avec l'IA</div>
                      <div className="text-sm text-primary-200">Discovery Agent prêt à vous accompagner</div>
                    </div>
                    <svg className="w-5 h-5 group-hover:translate-x-1 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                    </svg>
                  </button>
                </div>
              ) : (
                <div className="bg-white rounded-2xl border-2 border-dashed border-gray-300 p-12 text-center">
                  <div className="text-gray-400 mb-4">
                    <svg className="w-16 h-16 mx-auto" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122" />
                    </svg>
                  </div>
                  <h3 className="text-lg font-medium text-gray-900 mb-2">
                    Sélectionnez une opportunité
                  </h3>
                  <p className="text-gray-500">
                    Cliquez sur une carte pour voir les détails et la thèse économique complète
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Legend */}
        <div className="mt-12 bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="text-sm font-semibold text-gray-700 mb-4">Légende des niveaux d'urgence</h3>
          <div className="flex flex-wrap gap-4">
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-red-500"></span>
              <span className="text-sm text-gray-600">Critique (&lt;14j) - Agir immédiatement</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-orange-500"></span>
              <span className="text-sm text-gray-600">Urgent (14-30j) - Action prioritaire</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-yellow-500"></span>
              <span className="text-sm text-gray-600">Actif (30-60j) - Fenêtre viable</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-green-500"></span>
              <span className="text-sm text-gray-600">Standard (60-90j) - Temps disponible</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-3 h-3 rounded-full bg-gray-400"></span>
              <span className="text-sm text-gray-600">Étendu (&gt;90j) - Pas d'urgence</span>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-200 bg-white mt-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex items-center justify-between text-sm text-gray-500">
            <div>Smartacus © 2024 - Sonde économique Amazon</div>
            <div>
              Micro-niche: <span className="font-medium">Car Phone Mounts</span> |
              Amazon US
            </div>
          </div>
        </div>
      </footer>

      {/* Agent Chat Panel */}
      {showAgentChat && selectedOpportunity && (
        <AgentChat
          opportunity={selectedOpportunity}
          onClose={() => setShowAgentChat(false)}
        />
      )}
    </div>
  );
}
