import { useTranslation } from "react-i18next";
import type { UserItem } from "../types";
import { Badge } from "./common/Badge";
import { SummaryPoint } from "./common/SummaryPoint";

type SettingsPanelProps = {
  currentUser: UserItem | null;
  language: string;
  onLanguageChange: (language: "ru" | "en" | "tr") => void;
  autoSpamEnabled: boolean;
  onAutoSpamChange: (value: boolean) => void;
  scanSinceDate: string;
  onScanSinceDateChange: (value: string) => void;
  signature: string;
  onSignatureChange: (value: string) => void;
  onSaveSignature: () => void;
  savingSignature: boolean;
  onLogout: () => void;
  actionLoading: string | null;
};

export function SettingsPanel(props: SettingsPanelProps) {
  const { t } = useTranslation();

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
