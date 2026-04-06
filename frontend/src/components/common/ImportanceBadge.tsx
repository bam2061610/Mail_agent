type ImportanceBadgeProps = {
  score?: number | null;
  label?: string;
  className?: string;
};

function getImportanceTone(score: number): "critical" | "warning" | "neutral" {
  if (score >= 8) return "critical";
  if (score >= 5) return "warning";
  return "neutral";
}

export function ImportanceBadge({ score, label, className }: ImportanceBadgeProps) {
  if (score == null) return null;

  const tone = getImportanceTone(score);
  const description = label ? `${label}: ${score}/10` : undefined;

  return (
    <span
      className={`importance-badge importance-badge-${tone}${className ? ` ${className}` : ""}`}
      title={description}
      aria-label={description}
    >
      {score}
    </span>
  );
}
