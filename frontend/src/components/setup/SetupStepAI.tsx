import { Field } from "../common/Field";
import type { SetupAiFormState } from "../../types";

interface SetupStepAIProps {
  form: SetupAiFormState;
  errors: Record<string, string>;
  testing: boolean;
  onChange: (next: SetupAiFormState) => void;
  onTest: () => void;
}

export function SetupStepAI({ form, errors, testing, onChange, onTest }: SetupStepAIProps) {
  return (
    <div className="setup-step-grid">
      <Field label="DeepSeek API key" full hint="Stored in the database after setup completes.">
        <div className="setup-field-stack">
          <input
            type="password"
            value={form.deepseek_api_key}
            onChange={(event) => onChange({ ...form, deepseek_api_key: event.target.value })}
            placeholder="sk-..."
            autoComplete="off"
          />
          {errors.deepseek_api_key ? <span className="field-error">{errors.deepseek_api_key}</span> : null}
        </div>
      </Field>
      <Field label="Model" full>
        <div className="setup-field-stack">
          <input
            value={form.deepseek_model}
            onChange={(event) => onChange({ ...form, deepseek_model: event.target.value })}
            placeholder="deepseek-chat"
          />
          {errors.deepseek_model ? <span className="field-error">{errors.deepseek_model}</span> : null}
        </div>
      </Field>
      <Field label="Base URL" full>
        <div className="setup-field-stack">
          <input
            value={form.deepseek_base_url}
            onChange={(event) => onChange({ ...form, deepseek_base_url: event.target.value })}
            placeholder="https://api.deepseek.com"
          />
          {errors.deepseek_base_url ? <span className="field-error">{errors.deepseek_base_url}</span> : null}
        </div>
      </Field>
      <div className="setup-inline-actions">
        <button className="button button-secondary" type="button" onClick={onTest} disabled={testing}>
          {testing ? "Testing AI..." : "Test AI connection"}
        </button>
      </div>
    </div>
  );
}
