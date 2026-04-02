import React from "react";
import { QueuePanel } from "../AppLegacy";

export function EmailList(props: React.ComponentProps<typeof QueuePanel>) {
  return <QueuePanel {...props} />;
}
