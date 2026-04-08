import { Field } from "../common/Field";
import type { SetupAccountFormState } from "../../types";

interface SetupStepAccountProps {
  form: SetupAccountFormState;
  errors: Record<string, string>;
  onChange: (next: SetupAccountFormState) => void;
}

export function SetupStepAccount({ form, errors, onChange }: SetupStepAccountProps) {
  return (
    <div className="setup-step-grid">
      <Field label="Admin email" full>
        <div className="setup-field-stack">
          <input
            type="email"
            value={form.email}
            onChange={(event) => onChange({ ...form, email: event.target.value })}
            placeholder="admin@example.com"
            autoComplete="username"
          />
          {errors.email ? <span className="field-error">{errors.email}</span> : null}
        </div>
      </Field>
      <Field label="Display name" full hint="Optional. Defaults to the email address.">
        <div className="setup-field-stack">
          <input
            value={form.full_name}
            onChange={(event) => onChange({ ...form, full_name: event.target.value })}
            placeholder="Operations Admin"
            autoComplete="name"
          />
        </div>
      </Field>
      <Field label="Password" full>
        <div className="setup-field-stack">
          <input
            type="password"
            value={form.password}
            onChange={(event) => onChange({ ...form, password: event.target.value })}
            autoComplete="new-password"
            placeholder="At least 8 characters"
          />
          {errors.password ? <span className="field-error">{errors.password}</span> : null}
        </div>
      </Field>
      <Field label="Confirm password" full>
        <div className="setup-field-stack">
          <input
            type="password"
            value={form.confirm_password}
            onChange={(event) => onChange({ ...form, confirm_password: event.target.value })}
            autoComplete="new-password"
            placeholder="Repeat the password"
          />
          {errors.confirm_password ? <span className="field-error">{errors.confirm_password}</span> : null}
        </div>
      </Field>
    </div>
  );
}
