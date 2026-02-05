'use client';

interface ScoreRingProps {
  score: number;
  maxScore?: number;
  size?: 'sm' | 'md' | 'lg';
  showLabel?: boolean;
}

export function ScoreRing({
  score,
  maxScore = 100,
  size = 'md',
  showLabel = true
}: ScoreRingProps) {
  const percentage = (score / maxScore) * 100;

  // Taille selon size
  const dimensions = {
    sm: { width: 48, strokeWidth: 4, fontSize: 'text-sm' },
    md: { width: 72, strokeWidth: 6, fontSize: 'text-xl' },
    lg: { width: 96, strokeWidth: 8, fontSize: 'text-3xl' },
  };

  const { width, strokeWidth, fontSize } = dimensions[size];
  const radius = (width - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const offset = circumference - (percentage / 100) * circumference;

  // Couleur selon score
  const getColor = () => {
    if (score >= 80) return '#10b981'; // emerald
    if (score >= 60) return '#22c55e'; // green
    if (score >= 40) return '#eab308'; // yellow
    if (score >= 20) return '#f97316'; // orange
    return '#ef4444'; // red
  };

  const color = getColor();

  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width={width} height={width} className="transform -rotate-90">
        {/* Background circle */}
        <circle
          cx={width / 2}
          cy={width / 2}
          r={radius}
          stroke="#e5e7eb"
          strokeWidth={strokeWidth}
          fill="none"
        />
        {/* Progress circle */}
        <circle
          cx={width / 2}
          cy={width / 2}
          r={radius}
          stroke={color}
          strokeWidth={strokeWidth}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-500 ease-out"
        />
      </svg>
      {showLabel && (
        <div className="absolute inset-0 flex items-center justify-center">
          <span className={`font-bold ${fontSize}`} style={{ color }}>
            {score}
          </span>
        </div>
      )}
    </div>
  );
}
