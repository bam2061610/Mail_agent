import { useMemo, useState } from "react";
import { apiPost, getErrorMessage } from "../api";
import {
  initialSetupAccountForm,
  initialSetupAiForm,
  initialSetupMailboxForm,
  type SetupAccountFormState,
  type SetupAiFormState,
  type SetupCompletePayload,
  type SetupMailboxFormState,
} from "../types";
import { SetupStepAccount } from "./setup/SetupStepAccount";
import { SetupStepAI } from "./setup/SetupStepAI";
import { SetupStepMailbox } from "./setup/SetupStepMailbox";

interface SetupWizardProps {
  onCompleted: () => void;
}

type StepIndex = 0 | 1 | 2 | 3;

const stepLabels = ["Admin", "AI", "Mailbox", "Launch"];

export function SetupWizard({ onCompleted }: SetupWizardProps) {
  const [step, setStep] = useState<StepIndex>(0);
  const [accountForm, setAccountForm] = useState<SetupAccountFormState>(initialSetupAccountForm);
  const [aiForm, setAiForm] = useState<SetupAiFormState>(initialSetupAiForm);
  const [mailboxForm, setMailboxForm] = useState<SetupMailboxFormState>(initialSetupMailboxForm);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [bannerError, setBannerError] = useState("");
  const [bannerSuccess, setBannerSuccess] = useState("");
  const [busyAction, setBusyAction] = useState<"ai" | "mailbox" | "submit" | null>(null);

  const summaryItems = useMemo(
    () => [
      { label: "Admin", value: accountForm.email || "Not set" },
      { label: "AI model", value: aiForm.deepseek_model || "Not set" },
      { label: "Mailbox", value: mailboxForm.email_address || "Not set" },
    ],
    [accountForm.email, aiForm.deepseek_model, mailboxForm.email_address]
  );

  function validateAccount(): Record<string, string> {
    const errors: Record<string, string> = {};
    if (!accountForm.email.trim()) errors.email = "Admin email is required.";
    if (!accountForm.password) errors.password = "Password is required.";
    if (accountForm.password && accountForm.password.length < 8) {
      errors.password = "Password must be at least 8 characters.";
    }
    if (accountForm.confirm_password !== accountForm.password) {
      errors.confirm_password = "Passwords do not match.";
    }
    return errors;
  }

  function validateAi(): Record<string, string> {
    const errors: Record<string, string> = {};
    if (!aiForm.deepseek_api_key.trim()) errors.deepseek_api_key = "DeepSeek API key is required.";
    if (!aiForm.deepseek_model.trim()) errors.deepseek_model = "Model is required.";
    if (!aiForm.deepseek_base_url.trim()) errors.deepseek_base_url = "Base URL is required.";
    return errors;
  }

  function validateMailbox(): Record<string, string> {
    const errors: Record<string, string> = {};
    if (!mailboxForm.email_address.trim()) errors.email_address = "Mailbox email is required.";
    if (!mailboxForm.imap_host.trim()) errors.imap_host = "IMAP host is required.";
    if (!mailboxForm.imap_password.trim()) errors.imap_password = "IMAP password is required.";
    if (!mailboxForm.smtp_host.trim()) errors.smtp_host = "SMTP host is required.";
    if (!mailboxForm.smtp_password.trim()) errors.smtp_password = "SMTP password is required.";
    if (!/^\d+$/.test(mailboxForm.imap_port.trim())) errors.imap_port = "IMAP port must be numeric.";
    if (!/^\d+$/.test(mailboxForm.smtp_port.trim())) errors.smtp_port = "SMTP port must be numeric.";
    return errors;
  }

  function validateCurrentStep(): boolean {
    const errors = step === 0 ? validateAccount() : step === 1 ? validateAi() : step === 2 ? validateMailbox() : {};
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  }

  function buildPayload(): SetupCompletePayload {
    return {
      admin: accountForm,
      ai: aiForm,
      mailbox: {
        name: mailboxForm.name.trim(),
        email_address: mailboxForm.email_address.trim().toLowerCase(),
        imap_host: mailboxForm.imap_host.trim(),
        imap_port: Number(mailboxForm.imap_port || "993"),
        imap_username: mailboxForm.imap_username.trim() || mailboxForm.email_address.trim().toLowerCase(),
        imap_password: mailboxForm.imap_password,
        smtp_host: mailboxForm.smtp_host.trim(),
        smtp_port: Number(mailboxForm.smtp_port || "465"),
        smtp_username: mailboxForm.smtp_username.trim() || mailboxForm.email_address.trim().toLowerCase(),
        smtp_password: mailboxForm.smtp_password,
        smtp_use_tls: mailboxForm.smtp_use_tls,
        smtp_use_ssl: mailboxForm.smtp_use_ssl,
        enabled: true,
        is_default_outgoing: true,
      },
      scheduler_interval_minutes: 5,
      followup_overdue_days: 3,
      max_emails_per_scan: 200,
      ai_analysis_enabled: true,
    };
  }

  async function handleAiTest() {
    const errors = validateAi();
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;
    setBannerError("");
    setBannerSuccess("");
    setBusyAction("ai");
    try {
      await apiPost("/api/setup/test-ai", aiForm);
      setBannerSuccess("AI connection verified.");
    } catch (error) {
      setBannerError(getErrorMessage(error, "Could not verify AI configuration."));
    } finally {
      setBusyAction(null);
    }
  }

  async function handleMailboxTest() {
    const errors = validateMailbox();
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;
    setBannerError("");
    setBannerSuccess("");
    setBusyAction("mailbox");
    try {
      await apiPost("/api/setup/test-mailbox", {
        ...buildPayload().mailbox,
      });
      setBannerSuccess("Mailbox connection verified.");
    } catch (error) {
      setBannerError(getErrorMessage(error, "Could not verify mailbox configuration."));
    } finally {
      setBusyAction(null);
    }
  }

  async function handleSubmit() {
    const accountErrors = validateAccount();
    const aiErrors = validateAi();
    const mailboxErrors = validateMailbox();
    const errors = { ...accountErrors, ...aiErrors, ...mailboxErrors };
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) {
      setStep(Object.keys(accountErrors).length > 0 ? 0 : Object.keys(aiErrors).length > 0 ? 1 : 2);
      return;
    }
    setBusyAction("submit");
    setBannerError("");
    setBannerSuccess("");
    try {
      await apiPost("/api/setup/complete", buildPayload());
      setBannerSuccess("Setup completed. You can sign in now.");
      onCompleted();
    } catch (error) {
      setBannerError(getErrorMessage(error, "Could not finish setup."));
    } finally {
      setBusyAction(null);
    }
  }

  function goNext() {
    setBannerError("");
    setBannerSuccess("");
    if (!validateCurrentStep()) return;
    setStep((current) => Math.min(3, current + 1) as StepIndex);
  }

  function goBack() {
    setBannerError("");
    setBannerSuccess("");
    setStep((current) => Math.max(0, current - 1) as StepIndex);
  }

  return (
    <section className="setup-shell">
      <div className="setup-card">
        <div className="setup-header">
          <div>
            <p className="eyebrow">First-run setup</p>
            <h1>Configure Mail Agent</h1>
            <p className="helper-text">Finish the initial admin, AI, and mailbox setup in one pass.</p>
          </div>
          <div className="setup-stepper" aria-label="Setup steps">
            {stepLabels.map((label, index) => (
              <span key={label} className={`setup-step-chip${index === step ? " is-active" : index < step ? " is-complete" : ""}`}>
                {index + 1}. {label}
              </span>
            ))}
          </div>
        </div>

        {bannerError ? <div className="banner banner-error" role="alert">{bannerError}</div> : null}
        {bannerSuccess ? <div className="banner banner-success">{bannerSuccess}</div> : null}

        {step === 0 ? (
          <SetupStepAccount form={accountForm} errors={fieldErrors} onChange={setAccountForm} />
        ) : null}
        {step === 1 ? (
          <SetupStepAI
            form={aiForm}
            errors={fieldErrors}
            testing={busyAction === "ai"}
            onChange={setAiForm}
            onTest={() => void handleAiTest()}
          />
        ) : null}
        {step === 2 ? (
          <SetupStepMailbox
            form={mailboxForm}
            errors={fieldErrors}
            testing={busyAction === "mailbox"}
            onChange={setMailboxForm}
            onTest={() => void handleMailboxTest()}
          />
        ) : null}
        {step === 3 ? (
          <div className="setup-confirm-grid">
            {summaryItems.map((item) => (
              <div key={item.label} className="setup-summary-card">
                <span className="field-label">{item.label}</span>
                <strong>{item.value}</strong>
              </div>
            ))}
            <div className="setup-summary-card is-wide">
              <span className="field-label">What happens next</span>
              <p className="helper-text">
                Mail Agent will create the first admin user, store your AI and mailbox settings in the database, and unlock the regular sign-in screen.
              </p>
            </div>
          </div>
        ) : null}

        <div className="setup-actions">
          <button className="button button-ghost" type="button" onClick={goBack} disabled={step === 0 || busyAction !== null}>
            Back
          </button>
          {step < 3 ? (
            <button className="button button-primary" type="button" onClick={goNext} disabled={busyAction !== null}>
              Next
            </button>
          ) : (
            <button className="button button-primary" type="button" onClick={() => void handleSubmit()} disabled={busyAction === "submit"}>
              {busyAction === "submit" ? "Launching..." : "Confirm & launch"}
            </button>
          )}
        </div>
      </div>
    </section>
  );
}
