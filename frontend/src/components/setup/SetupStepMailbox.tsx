import { Field } from "../common/Field";
import type { SetupMailboxFormState } from "../../types";

interface SetupStepMailboxProps {
  form: SetupMailboxFormState;
  errors: Record<string, string>;
  testing: boolean;
  onChange: (next: SetupMailboxFormState) => void;
  onTest: () => void;
}

export function SetupStepMailbox({ form, errors, testing, onChange, onTest }: SetupStepMailboxProps) {
  return (
    <div className="setup-step-grid">
      <div className="mailbox-form-grid">
        <Field label="Mailbox name" full>
          <div className="setup-field-stack">
            <input
              value={form.name}
              onChange={(event) => onChange({ ...form, name: event.target.value })}
              placeholder="Main mailbox"
            />
          </div>
        </Field>
        <Field label="Email address" full>
          <div className="setup-field-stack">
            <input
              type="email"
              value={form.email_address}
              onChange={(event) => onChange({ ...form, email_address: event.target.value })}
              placeholder="mailbox@example.com"
            />
            {errors.email_address ? <span className="field-error">{errors.email_address}</span> : null}
          </div>
        </Field>
        <Field label="IMAP host" full>
          <div className="setup-field-stack">
            <input
              value={form.imap_host}
              onChange={(event) => onChange({ ...form, imap_host: event.target.value })}
              placeholder="imap.example.com"
            />
            {errors.imap_host ? <span className="field-error">{errors.imap_host}</span> : null}
          </div>
        </Field>
        <Field label="IMAP port" full>
          <div className="setup-field-stack">
            <input
              value={form.imap_port}
              onChange={(event) => onChange({ ...form, imap_port: event.target.value })}
              placeholder="993"
            />
            {errors.imap_port ? <span className="field-error">{errors.imap_port}</span> : null}
          </div>
        </Field>
        <Field label="IMAP username" full>
          <div className="setup-field-stack">
            <input
              value={form.imap_username}
              onChange={(event) => onChange({ ...form, imap_username: event.target.value })}
              placeholder="Defaults to the email address"
            />
          </div>
        </Field>
        <Field label="IMAP password" full>
          <div className="setup-field-stack">
            <input
              type="password"
              value={form.imap_password}
              onChange={(event) => onChange({ ...form, imap_password: event.target.value })}
              autoComplete="off"
            />
            {errors.imap_password ? <span className="field-error">{errors.imap_password}</span> : null}
          </div>
        </Field>
        <Field label="SMTP host" full>
          <div className="setup-field-stack">
            <input
              value={form.smtp_host}
              onChange={(event) => onChange({ ...form, smtp_host: event.target.value })}
              placeholder="smtp.example.com"
            />
            {errors.smtp_host ? <span className="field-error">{errors.smtp_host}</span> : null}
          </div>
        </Field>
        <Field label="SMTP port" full>
          <div className="setup-field-stack">
            <input
              value={form.smtp_port}
              onChange={(event) => onChange({ ...form, smtp_port: event.target.value })}
              placeholder="465"
            />
            {errors.smtp_port ? <span className="field-error">{errors.smtp_port}</span> : null}
          </div>
        </Field>
        <Field label="SMTP username" full>
          <div className="setup-field-stack">
            <input
              value={form.smtp_username}
              onChange={(event) => onChange({ ...form, smtp_username: event.target.value })}
              placeholder="Defaults to the email address"
            />
          </div>
        </Field>
        <Field label="SMTP password" full>
          <div className="setup-field-stack">
            <input
              type="password"
              value={form.smtp_password}
              onChange={(event) => onChange({ ...form, smtp_password: event.target.value })}
              autoComplete="off"
            />
            {errors.smtp_password ? <span className="field-error">{errors.smtp_password}</span> : null}
          </div>
        </Field>
      </div>
      <div className="setup-toggle-row">
        <label className="settings-toggle">
          <input
            type="checkbox"
            checked={form.smtp_use_tls}
            onChange={(event) => onChange({ ...form, smtp_use_tls: event.target.checked })}
          />
          <span>Use STARTTLS</span>
        </label>
        <label className="settings-toggle">
          <input
            type="checkbox"
            checked={form.smtp_use_ssl}
            onChange={(event) => onChange({ ...form, smtp_use_ssl: event.target.checked })}
          />
          <span>Use SSL</span>
        </label>
      </div>
      <div className="setup-inline-actions">
        <button className="button button-secondary" type="button" onClick={onTest} disabled={testing}>
          {testing ? "Testing mailbox..." : "Test mailbox connection"}
        </button>
      </div>
    </div>
  );
}
