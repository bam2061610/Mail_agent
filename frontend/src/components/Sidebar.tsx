import { useTranslation } from "react-i18next";
import type { MailView } from "../types";
import { Badge } from "./common/Badge";

type SidebarProps = {
  view: MailView;
  open: boolean;
  onClose: () => void;
  onViewChange: (view: MailView) => void;
};

const ITEMS: Array<{ key: MailView; labelKey: string; short: string }> = [
  { key: "inbox", labelKey: "nav.inbox", short: "Inbox" },
  { key: "sent", labelKey: "nav.sent", short: "Sent" },
  { key: "spam", labelKey: "nav.spam", short: "Spam" },
  { key: "processed", labelKey: "nav.processed", short: "Processed" },
  { key: "settings", labelKey: "nav.settings", short: "Settings" },
];

export function Sidebar({ view, open, onClose, onViewChange }: SidebarProps) {
  const { t } = useTranslation();

  return (
    <>
      <div className={`sidebar-backdrop${open ? " is-open" : ""}`} onClick={onClose} aria-hidden="true" />
      <aside className={`sidebar${open ? " is-open" : ""}`}>
        <div className="sidebar-brand">
          <Badge tone="accent">Smart Inbox</Badge>
          <div>
            <h2>{t("app.name")}</h2>
            <p>{t("app.tagline")}</p>
          </div>
        </div>
        <nav className="sidebar-nav" aria-label={t("app.workspace")}>
          {ITEMS.map((item) => (
            <button
              key={item.key}
              className={`sidebar-link${view === item.key ? " is-active" : ""}`}
              type="button"
              onClick={() => {
                onViewChange(item.key);
                onClose();
              }}
            >
              <span>{t(item.labelKey, { defaultValue: item.short })}</span>
              <span className="sidebar-link-short" aria-hidden="true">
                {item.short}
              </span>
            </button>
          ))}
        </nav>
      </aside>
    </>
  );
}
