'use client';

import { UrgencyLevel } from '@/types/opportunity';

interface UrgencyBadgeProps {
  level: UrgencyLevel;
  windowDays: number;
  className?: string;
}

const urgencyConfig: Record<UrgencyLevel, {
  label: string;
  icon: string;
  bgColor: string;
  textColor: string;
  borderColor: string;
}> = {
  critical: {
    label: 'CRITIQUE',
    icon: '🔴',
    bgColor: 'bg-red-100',
    textColor: 'text-red-800',
    borderColor: 'border-red-300',
  },
  urgent: {
    label: 'URGENT',
    icon: '🟠',
    bgColor: 'bg-orange-100',
    textColor: 'text-orange-800',
    borderColor: 'border-orange-300',
  },
  active: {
    label: 'ACTIF',
    icon: '🟡',
    bgColor: 'bg-yellow-100',
    textColor: 'text-yellow-800',
    borderColor: 'border-yellow-300',
  },
  standard: {
    label: 'STANDARD',
    icon: '🟢',
    bgColor: 'bg-green-100',
    textColor: 'text-green-800',
    borderColor: 'border-green-300',
  },
  extended: {
    label: 'ÉTENDU',
    icon: '⚪',
    bgColor: 'bg-gray-100',
    textColor: 'text-gray-700',
    borderColor: 'border-gray-300',
  },
};

export function UrgencyBadge({ level, windowDays, className = '' }: UrgencyBadgeProps) {
  const config = urgencyConfig[level];

  return (
    <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full border ${config.bgColor} ${config.textColor} ${config.borderColor} ${className}`}>
      <span>{config.icon}</span>
      <span className="font-semibold text-sm">{config.label}</span>
      <span className="text-xs opacity-75">({windowDays}j)</span>
    </div>
  );
}
