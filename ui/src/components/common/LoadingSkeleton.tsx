import "./LoadingSkeleton.css";

interface LoadingSkeletonProps {
  lines?: number;
  height?: string;
  className?: string;
}

export function LoadingSkeleton({
  lines = 3,
  height = "16px",
  className = "",
}: LoadingSkeletonProps) {
  return (
    <div className={`loading-skeleton ${className}`}>
      {Array.from({ length: lines }, (_, i) => (
        <div
          key={i}
          className="skeleton"
          style={{
            height,
            width: i === lines - 1 ? "60%" : "100%",
          }}
        />
      ))}
    </div>
  );
}

export function CardSkeleton() {
  return (
    <div className="card-skeleton skeleton-card">
      <div className="skeleton" style={{ height: "20px", width: "40%" }} />
      <div className="skeleton" style={{ height: "14px", width: "70%" }} />
      <div className="skeleton" style={{ height: "14px", width: "55%" }} />
      <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-3)" }}>
        <div className="skeleton" style={{ height: "24px", width: "60px" }} />
        <div className="skeleton" style={{ height: "24px", width: "80px" }} />
      </div>
    </div>
  );
}
