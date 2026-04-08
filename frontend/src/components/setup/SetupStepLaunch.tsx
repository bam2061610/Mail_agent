import { Field } from "../common/Field";
import type { SetupLaunchFormState } from "../../types";

interface SetupSummaryItem {
  label: string;
  value: string;
}

interface SetupStepLaunchProps {
  form: SetupLaunchFormState;
  errors: Record<string, string>;
  summaryItems: SetupSummaryItem[];
  onChange: (next: SetupLaunchFormState) => void;
}

export function SetupStepLaunch({
  form,
  errors,
  summaryItems,
  onChange,
}: SetupStepLaunchProps) {
  return (
    <div className="setup-step-grid">
      <div className="setup-confirm-grid">
        {summaryItems.map((item) => (
          <div key={item.label} className="setup-summary-card">
            <span className="field-label">{item.label}</span>
            <strong>{item.value}</strong>
          </div>
        ))}
        <div className="setup-summary-card is-wide">
          <span className="field-label">Launch settings</span>
          <div className="mailbox-form-grid">
            <Field label="Scan interval (minutes)" full>
              <div className="setup-field-stack">
                <input
                  value={form.scheduler_interval_minutes}
                  onChange={(event) =>
                    onChange({
                      ...form,
                      scheduler_interval_minutes: event.target.value,
                    })
                  }
                  inputMode="numeric"
                  placeholder="5"
                />
                {errors.scheduler_interval_minutes ? (
                  <span className="field-error">{errors.scheduler_interval_minutes}</span>
                ) : null}
              </div>
            </Field>
            <Field label="Follow-up overdue days" full>
              <div className="setup-field-stack">
                <input
                  value={form.followup_overdue_days}
                  onChange={(event) =>
                    onChange({
                      ...form,
                      followup_overdue_days: event.target.value,
                    })
                  }
                  inputMode="numeric"
                  placeholder="3"
                />
                {errors.followup_overdue_days ? (
                  <span className="field-error">{errors.followup_overdue_days}</span>
                ) : null}
              </div>
            </Field>
            <Field label="Max emails per scan" full>
              <div className="setup-field-stack">
                <input
                  value={form.max_emails_per_scan}
                  onChange={(event) =>
                    onChange({
                      ...form,
                      max_emails_per_scan: event.target.value,
                    })
                  }
                  inputMode="numeric"
                  placeholder="200"
                />
                {errors.max_emails_per_scan ? (
                  <span className="field-error">{errors.max_emails_per_scan}</span>
                ) : null}
              </div>
            </Field>
          </div>
          <div className="setup-toggle-row">
            <label className="settings-toggle">
              <input
                type="checkbox"
                checked={form.ai_analysis_enabled}
                onChange={(event) =>
                  onChange({
                    ...form,
                    ai_analysis_enabled: event.target.checked,
                  })
                }
              />
              <span>Enable AI analysis after setup</span>
            </label>
          </div>
          <p className="helper-text">
            Mail Agent will create the first admin user, save these runtime settings in the
            database, and unlock the regular sign-in screen.
          </p>
        </div>
      </div>
    </div>
  );
}
