import type { ReactNode } from "react";

type SummaryPointProps = {
  label: string;
  value: ReactNode;
};

export function SummaryPoint({ label, value }: SummaryPointProps) {
  return (
    <div className="summary-point">
      <span className="summary-point-label">{label}</span>
      <strong className="summary-point-value">{value}</strong>
    </div>
  );
}
