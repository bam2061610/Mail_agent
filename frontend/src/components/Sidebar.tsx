import React from "react";
import type { ViewKey } from "../types";
import { NavButton } from "../AppLegacy";

type SidebarProps = {
  view: ViewKey;
  activeQueueCount: number;
  waitingCount: number;
  spamCount: number;
  rulesCount: number;
  onViewChange: (view: ViewKey) => void;
};

export function Sidebar(props: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <h1>Orhun Mail Agent</h1>
        <p>Action dashboard for intake, drafting, automation, and review control.</p>
      </div>
      <div className="nav-section">
        <div className="nav-label">Workspace</div>
        <div className="nav-list">
          <NavButton label="Focus" active={props.view === "focus"} onClick={() => props.onViewChange("focus")} />
          <NavButton label="Active Queue" active={props.view === "active"} badge={props.activeQueueCount} onClick={() => props.onViewChange("active")} />
          <NavButton label="Waiting Queue" active={props.view === "waiting"} badge={props.waitingCount} onClick={() => props.onViewChange("waiting")} />
          <NavButton label="Spam Log" active={props.view === "spam"} badge={props.spamCount} onClick={() => props.onViewChange("spam")} />
          <NavButton label="Reports" active={props.view === "reports"} onClick={() => props.onViewChange("reports")} />
          <NavButton label="Settings" active={props.view === "settings"} badge={props.rulesCount} onClick={() => props.onViewChange("settings")} />
        </div>
      </div>
    </aside>
  );
}
