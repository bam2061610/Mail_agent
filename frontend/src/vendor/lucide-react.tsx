import type { ReactNode, SVGProps } from "react";

type LucideProps = SVGProps<SVGSVGElement> & {
  size?: number;
  strokeWidth?: number;
};

function IconBase({
  size = 16,
  strokeWidth = 2,
  children,
  ...props
}: LucideProps & { children: ReactNode }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  );
}

export function Archive(props: LucideProps) {
  return (
    <IconBase {...props}>
      <rect x="3" y="4" width="18" height="4" rx="1" />
      <path d="M5 8v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8" />
      <path d="M12 11v6" />
      <path d="m15 14-3 3-3-3" />
    </IconBase>
  );
}

export function Ban(props: LucideProps) {
  return (
    <IconBase {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M5.7 5.7 18.3 18.3" />
    </IconBase>
  );
}

export function Clock(props: LucideProps) {
  return (
    <IconBase {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </IconBase>
  );
}

export function Check(props: LucideProps) {
  return (
    <IconBase {...props}>
      <path d="M20 6 9 17l-5-5" />
    </IconBase>
  );
}

export function Sparkles(props: LucideProps) {
  return (
    <IconBase {...props}>
      <path d="m12 3 1.8 4.2L18 9l-4.2 1.8L12 15l-1.8-4.2L6 9l4.2-1.8L12 3Z" />
      <path d="M5 3v4" />
      <path d="M3 5h4" />
      <path d="M19 15v6" />
      <path d="M16 18h6" />
    </IconBase>
  );
}

export function Undo2(props: LucideProps) {
  return (
    <IconBase {...props}>
      <path d="m9 14-5-5 5-5" />
      <path d="M4 9h10a6 6 0 1 1 0 12h-1" />
    </IconBase>
  );
}
