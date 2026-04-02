import React from "react";
import { DetailPanel } from "../AppLegacy";

export function EmailDetail(props: React.ComponentProps<typeof DetailPanel>) {
  const className = [props.className, "email-detail-shell"].filter(Boolean).join(" ");
  return <DetailPanel {...props} className={className} />;
}
