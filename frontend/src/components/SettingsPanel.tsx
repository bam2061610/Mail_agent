import React from "react";
import { SettingsPanel as LegacySettingsPanel } from "../AppLegacy";

export function SettingsPanel(props: React.ComponentProps<typeof LegacySettingsPanel>) {
  return <LegacySettingsPanel {...props} />;
}
