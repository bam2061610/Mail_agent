import { useTranslation } from "react-i18next";
import type { MailboxFormState, MailboxItem, UserItem } from "../types";
import { Badge } from "./common/Badge";
import { Field } from "./common/Field";
import { SummaryPoint } from "./common/SummaryPoint";

type SettingsPanelProps = {
  currentUser: UserItem | null;
  language: string;
  onLanguageChange: (language: "ru" | "en" | "tr") => void;
  autoSpamEnabled: boolean;
  onAutoSpamChange: (value: boolean) => void;
  followupOverdueDays: string;
  onFollowupOverdueDaysChange: (value: string) => void;
  scanSinceDate: string;
  onScanSinceDateChange: (value: string) => void;
  signature: string;
  onSignatureChange: (value: string) => void;
  onSaveSignature: () => void;
  savingSignature: boolean;
  mailboxes: MailboxItem[];
  mailboxesLoading: boolean;
  mailboxForm: MailboxFormState;
  editingMailboxId: string | null;
  mailboxSaving: boolean;
  mailboxActionLoadingId: string | null;
  onMailboxFormChange: (next: MailboxFormState) => void;
  onMailboxEdit: (mailbox: MailboxItem) => void;
  onMailboxCancelEdit: () => void;
  onMailboxSave: () => void;
  onMailboxDelete: (mailboxId: string) => void;
  onMailboxScan: (mailboxId: string) => void;
  onMailboxTest: (mailboxId: string) => void;
  onLogout: () => void;
  actionLoading: string | null;
};

export function SettingsPanel(props: SettingsPanelProps) {
  const { t } = useTranslation();
  const canManageMailboxes = props.currentUser?.role === "admin";

  return (
    <section className="settings-panel">
      <div className="settings-card">
        <div className="panel-copy">
          <h3>{t("settings.language")}</h3>
          <p>{props.currentUser?.email || ""}</p>
        </div>
        <div className="language-switch">
          <button
            className={`button button-ghost${props.language === "en" ? " is-active" : ""}`}
            type="button"
            onClick={() => props.onLanguageChange("en")}
          >
            EN
          </button>
          <button
            className={`button button-ghost${props.language === "ru" ? " is-active" : ""}`}
            type="button"
            onClick={() => props.onLanguageChange("ru")}
          >
            RU
          </button>
          <button
            className={`button button-ghost${props.language === "tr" ? " is-active" : ""}`}
            type="button"
            onClick={() => props.onLanguageChange("tr")}
          >
            TR
          </button>
        </div>
      </div>
      <div className="settings-card">
        <div className="panel-copy">
          <h3>{t("settings.scanSinceDate")}</h3>
          <p>{t("settings.scanSinceDateHint")}</p>
        </div>
        <div className="settings-scan-form">
          <input
            type="date"
            value={props.scanSinceDate}
            onChange={(event) => props.onScanSinceDateChange(event.target.value)}
          />
        </div>
      </div>
      <div className="settings-card">
        <div className="panel-copy">
          <h3>Workflow</h3>
          <p>Configure when waiting threads become overdue.</p>
        </div>
        <div className="settings-scan-form">
          <Field label="Follow-up overdue days" full>
            <input
              value={props.followupOverdueDays}
              onChange={(event) => props.onFollowupOverdueDaysChange(event.target.value)}
              inputMode="numeric"
              placeholder="3"
            />
          </Field>
        </div>
      </div>
      <div className="settings-card">
        <div className="panel-copy">
          <h3>{t("settings.autoSpam")}</h3>
          <p>{t("spam.aiAuto", { defaultValue: "AI auto-spam detection" })}</p>
        </div>
        <label className="settings-toggle">
          <input
            type="checkbox"
            checked={props.autoSpamEnabled}
            onChange={(event) => props.onAutoSpamChange(event.target.checked)}
          />
          <span>{props.autoSpamEnabled ? t("spam.aiAuto") : t("spam.manual")}</span>
        </label>
      </div>
      <div className="settings-card settings-signature-card">
        <div className="panel-copy">
          <h3>{t("settings.signature")}</h3>
          <p>{t("detail.signatureHint")}</p>
        </div>
        <div className="settings-signature-form">
          <textarea
            rows={5}
            value={props.signature}
            onChange={(event) => props.onSignatureChange(event.target.value)}
            placeholder={t("detail.signaturePlaceholder")}
          />
          <button
            className="button button-secondary"
            type="button"
            onClick={props.onSaveSignature}
            disabled={props.savingSignature}
          >
            {t("settings.saveSignature")}
          </button>
        </div>
      </div>
      <div className="settings-card settings-mailbox-card">
        <div className="panel-copy">
          <h3>{t("settings.mailboxesTitle")}</h3>
          <p>{t("settings.mailboxesHint")}</p>
        </div>
        <div className="settings-mailbox-stack">
          <div className="mailbox-list">
            {props.mailboxesLoading ? (
              <p className="helper-text">{t("settings.loadingMailboxes")}</p>
            ) : props.mailboxes.length === 0 ? (
              <div className="empty-state">
                <strong>{t("settings.mailboxesEmptyTitle")}</strong>
                <p>{t("settings.mailboxesEmptyHint")}</p>
              </div>
            ) : (
              props.mailboxes.map((mailbox) => {
                const isEditing = props.editingMailboxId === mailbox.id;
                const isBusy = props.mailboxActionLoadingId === mailbox.id;
                return (
                  <article key={mailbox.id} className={`mailbox-item${isEditing ? " is-editing" : ""}`}>
                    <div className="mailbox-item-copy">
                      <div className="mailbox-item-heading">
                        <strong>{mailbox.name}</strong>
                        <div className="inline-badges">
                          {mailbox.enabled ? <Badge tone="success">{t("settings.mailboxEnabled")}</Badge> : <Badge tone="neutral">{t("settings.mailboxDisabled")}</Badge>}
                          {mailbox.is_default_outgoing ? <Badge tone="accent">{t("settings.mailboxDefault")}</Badge> : null}
                        </div>
                      </div>
                      <p>{mailbox.email_address}</p>
                      <p className="helper-text">
                        IMAP {mailbox.imap_host}:{mailbox.imap_port} · SMTP {mailbox.smtp_host}:{mailbox.smtp_port}
                      </p>
                    </div>
                    {canManageMailboxes ? (
                      <div className="mailbox-item-actions">
                        <button className="button button-ghost" type="button" onClick={() => props.onMailboxEdit(mailbox)}>
                          {t("settings.editMailbox")}
                        </button>
                        <button className="button button-ghost" type="button" onClick={() => props.onMailboxTest(mailbox.id)} disabled={isBusy}>
                          {isBusy ? t("settings.testingMailbox") : t("settings.testMailbox")}
                        </button>
                        <button className="button button-ghost" type="button" onClick={() => props.onMailboxScan(mailbox.id)} disabled={isBusy}>
                          {isBusy ? t("settings.scanningMailbox") : t("settings.scanMailbox")}
                        </button>
                        <button className="button button-ghost" type="button" onClick={() => props.onMailboxDelete(mailbox.id)} disabled={isBusy}>
                          {t("settings.deleteMailbox")}
                        </button>
                      </div>
                    ) : null}
                  </article>
                );
              })
            )}
          </div>

          {canManageMailboxes ? (
            <div className="mailbox-form">
              <div className="section-title-row">
                <h4 className="section-title">{props.editingMailboxId ? t("settings.editMailboxTitle") : t("settings.addMailboxTitle")}</h4>
                {props.editingMailboxId ? (
                  <button className="button button-ghost" type="button" onClick={props.onMailboxCancelEdit}>
                    {t("settings.cancelMailboxEdit")}
                  </button>
                ) : null}
              </div>

              <div className="mailbox-form-grid">
                <Field label={t("settings.mailboxName")} full>
                  <input value={props.mailboxForm.name} onChange={(event) => props.onMailboxFormChange({ ...props.mailboxForm, name: event.target.value })} />
                </Field>
                <Field label={t("settings.mailboxEmail")} full>
                  <input value={props.mailboxForm.email_address} onChange={(event) => props.onMailboxFormChange({ ...props.mailboxForm, email_address: event.target.value })} />
                </Field>
                <Field label={t("settings.imapHost")} full>
                  <input value={props.mailboxForm.imap_host} onChange={(event) => props.onMailboxFormChange({ ...props.mailboxForm, imap_host: event.target.value })} />
                </Field>
                <Field label={t("settings.imapPort")} full>
                  <input value={props.mailboxForm.imap_port} onChange={(event) => props.onMailboxFormChange({ ...props.mailboxForm, imap_port: event.target.value })} />
                </Field>
                <Field label={t("settings.imapUsername")} full>
                  <input value={props.mailboxForm.imap_username} onChange={(event) => props.onMailboxFormChange({ ...props.mailboxForm, imap_username: event.target.value })} />
                </Field>
                <Field label={t("settings.imapPassword")} full hint={props.editingMailboxId ? t("settings.mailboxPasswordHint") : undefined}>
                  <input type="password" value={props.mailboxForm.imap_password} onChange={(event) => props.onMailboxFormChange({ ...props.mailboxForm, imap_password: event.target.value })} />
                </Field>
                <Field label={t("settings.smtpHost")} full>
                  <input value={props.mailboxForm.smtp_host} onChange={(event) => props.onMailboxFormChange({ ...props.mailboxForm, smtp_host: event.target.value })} />
                </Field>
                <Field label={t("settings.smtpPort")} full>
                  <input value={props.mailboxForm.smtp_port} onChange={(event) => props.onMailboxFormChange({ ...props.mailboxForm, smtp_port: event.target.value })} />
                </Field>
                <Field label={t("settings.smtpUsername")} full>
                  <input value={props.mailboxForm.smtp_username} onChange={(event) => props.onMailboxFormChange({ ...props.mailboxForm, smtp_username: event.target.value })} />
                </Field>
                <Field label={t("settings.smtpPassword")} full hint={props.editingMailboxId ? t("settings.mailboxPasswordHint") : undefined}>
                  <input type="password" value={props.mailboxForm.smtp_password} onChange={(event) => props.onMailboxFormChange({ ...props.mailboxForm, smtp_password: event.target.value })} />
                </Field>
              </div>

              <div className="mailbox-toggle-row">
                <label className="settings-toggle">
                  <input type="checkbox" checked={props.mailboxForm.enabled} onChange={(event) => props.onMailboxFormChange({ ...props.mailboxForm, enabled: event.target.checked })} />
                  <span>{t("settings.mailboxEnabled")}</span>
                </label>
                <label className="settings-toggle">
                  <input type="checkbox" checked={props.mailboxForm.is_default_outgoing} onChange={(event) => props.onMailboxFormChange({ ...props.mailboxForm, is_default_outgoing: event.target.checked })} />
                  <span>{t("settings.mailboxDefault")}</span>
                </label>
                <label className="settings-toggle">
                  <input type="checkbox" checked={props.mailboxForm.smtp_use_tls} onChange={(event) => props.onMailboxFormChange({ ...props.mailboxForm, smtp_use_tls: event.target.checked })} />
                  <span>{t("settings.smtpTls")}</span>
                </label>
                <label className="settings-toggle">
                  <input type="checkbox" checked={props.mailboxForm.smtp_use_ssl} onChange={(event) => props.onMailboxFormChange({ ...props.mailboxForm, smtp_use_ssl: event.target.checked })} />
                  <span>{t("settings.smtpSsl")}</span>
                </label>
              </div>

              <div className="mailbox-form-actions">
                <button className="button button-primary" type="button" onClick={props.onMailboxSave} disabled={props.mailboxSaving}>
                  {props.mailboxSaving ? t("settings.savingMailbox") : props.editingMailboxId ? t("settings.updateMailbox") : t("settings.addMailbox")}
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </div>
      <div className="settings-grid">
        <SummaryPoint label={t("app.workspace")} value={t("app.name")} />
        <SummaryPoint label="Session" value={props.currentUser?.role || "user"} />
        <SummaryPoint label="Theme" value="Light" />
        <SummaryPoint label="Status" value={<Badge tone="success">Ready</Badge>} />
      </div>
      <button className="button button-secondary" type="button" onClick={props.onLogout} disabled={props.actionLoading === "auth-logout"}>
        {props.actionLoading === "auth-logout" ? t("app.signingOut") : t("app.logout")}
      </button>
    </section>
  );
}
