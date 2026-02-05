'use client';

import { useState, useEffect } from 'react';
import { PipelineStatus } from '@/types/opportunity';
import { formatNumber, formatDateTime } from '@/lib/format';

interface HeaderProps {
  pipelineStatus?: PipelineStatus;
}

export function Header({ pipelineStatus }: HeaderProps) {
  // Utiliser un état pour éviter les différences serveur/client
  const [lastScan, setLastScan] = useState<string>('');

  useEffect(() => {
    if (pipelineStatus?.lastRunAt) {
      setLastScan(formatDateTime(pipelineStatus.lastRunAt));
    }
  }, [pipelineStatus?.lastRunAt]);

  const getStatusBadge = () => {
    if (!pipelineStatus) return null;

    if (pipelineStatus.status === 'completed') {
      return <span className="px-3 py-1.5 rounded-full text-sm font-medium bg-green-100 text-green-800">✓ Actif</span>;
    }
    if (pipelineStatus.status === 'running') {
      return <span className="px-3 py-1.5 rounded-full text-sm font-medium bg-blue-100 text-blue-800">⟳ En cours</span>;
    }
    if (pipelineStatus.status === 'idle') {
      return <span className="px-3 py-1.5 rounded-full text-sm font-medium bg-gray-100 text-gray-800">○ En attente</span>;
    }
    return <span className="px-3 py-1.5 rounded-full text-sm font-medium bg-red-100 text-red-800">✕ Erreur</span>;
  };

  return (
    <header className="bg-white border-b border-gray-200 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-primary-500 to-primary-700 rounded-xl flex items-center justify-center">
              <span className="text-white font-bold text-xl">S</span>
            </div>
            <div>
              <div className="font-bold text-gray-900 text-lg">Smartacus</div>
              <div className="text-xs text-gray-500">Sonde économique Amazon</div>
            </div>
          </div>

          {/* Pipeline status */}
          {pipelineStatus && (
            <div className="flex items-center gap-4">
              <div className="text-right">
                <div className="text-sm text-gray-600">
                  <span className="font-medium">{formatNumber(pipelineStatus.asinsTracked)}</span> ASINs suivis
                </div>
                <div className="text-xs text-gray-500">
                  Dernier scan: {lastScan || '...'}
                </div>
              </div>
              {getStatusBadge()}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
