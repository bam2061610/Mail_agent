import React from "react";

type BadgeProps = {
  className?: string;
  children: React.ReactNode;
};

export function Badge(props: BadgeProps) {
  return <span className={`badge ${props.className || ""}`.trim()}>{props.children}</span>;
}
