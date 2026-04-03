import type { ReactNode } from "react";

type FieldProps = {
  label: ReactNode;
  children: ReactNode;
  full?: boolean;
  hint?: ReactNode;
};

export function Field({ label, children, full, hint }: FieldProps) {
  return (
    <label className={`field${full ? " field-full" : ""}`}>
      <span className="field-label">{label}</span>
      {children}
      {hint ? <span className="field-hint">{hint}</span> : null}
    </label>
  );
}
