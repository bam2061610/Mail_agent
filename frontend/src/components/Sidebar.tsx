import React from "react";
import { useTranslation } from "react-i18next";
import type { ViewKey } from "../types";
import { NavButton } from "../AppLegacy";

type SidebarProps = {
  view: ViewKey;
  activeQueueCount: number;
  sentCount: number;
  waitingCount: number;
  spamCount: number;
  rulesCount: number;
  onViewChange: (view: ViewKey) => void;
};

export function Sidebar(props: SidebarProps) {
  const { t } = useTranslation();
  return (
    <aside className="sidebar">
      <div className="brand">
        <h1>{t("app.name")}</h1>
        <p>{t("app.tagline")}</p>
      </div>
      <div className="nav-section">
        <div className="nav-label">{t("app.workspace")}</div>
        <div className="nav-list">
          <NavButton label={t("nav.focus")} active={props.view === "focus"} onClick={() => props.onViewChange("focus")} />
          <NavButton label={t("nav.active")} active={props.view === "active"} badge={props.activeQueueCount} onClick={() => props.onViewChange("active")} />
          <NavButton label={t("nav.sent")} active={props.view === "sent"} badge={props.sentCount} onClick={() => props.onViewChange("sent")} />
          <NavButton label={t("nav.waiting")} active={props.view === "waiting"} badge={props.waitingCount} onClick={() => props.onViewChange("waiting")} />
          <NavButton label={t("nav.spam")} active={props.view === "spam"} badge={props.spamCount} onClick={() => props.onViewChange("spam")} />
          <NavButton label={t("nav.reports")} active={props.view === "reports"} onClick={() => props.onViewChange("reports")} />
          <NavButton label={t("nav.settings")} active={props.view === "settings"} badge={props.rulesCount} onClick={() => props.onViewChange("settings")} />
        </div>
      </div>
    </aside>
  );
}
