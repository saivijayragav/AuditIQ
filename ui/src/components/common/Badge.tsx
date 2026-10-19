import { type ReactNode } from "react";
import "./Badge.css";

interface BadgeProps {
  children: ReactNode;
  color?: string;
  variant?: "filled" | "outlined" | "muted";
  size?: "sm" | "md";
  pulse?: boolean;
}

export function Badge({
  children,
  color = "var(--text-secondary)",
  variant = "filled",
  size = "sm",
  pulse = false,
}: BadgeProps) {
  return (
    <span
      className={`badge badge--${variant} badge--${size}`}
      style={
        {
          "--badge-color": color,
        } as React.CSSProperties
      }
    >
      {pulse && <span className="badge__dot pulse" />}
      {children}
    </span>
  );
}
