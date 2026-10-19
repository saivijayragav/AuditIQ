import { type ReactNode } from "react";
import "./Card.css";

interface CardProps {
  children: ReactNode;
  className?: string;
  glass?: boolean;
  onClick?: () => void;
  padding?: "none" | "sm" | "md" | "lg";
}

export function Card({
  children,
  className = "",
  glass = false,
  onClick,
  padding = "md",
}: CardProps) {
  const Tag = onClick ? "button" : "div";
  return (
    <Tag
      className={`card card--${padding} ${glass ? "card--glass" : ""} ${onClick ? "card--interactive" : ""} ${className}`}
      onClick={onClick}
    >
      {children}
    </Tag>
  );
}

export function CardHeader({ children }: { children: ReactNode }) {
  return <div className="card__header">{children}</div>;
}

export function CardTitle({ children }: { children: ReactNode }) {
  return <h3 className="card__title">{children}</h3>;
}

export function CardContent({ children }: { children: ReactNode }) {
  return <div className="card__content">{children}</div>;
}
