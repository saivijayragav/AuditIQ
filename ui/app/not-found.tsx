import Link from "next/link";

export default function NotFound() {
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: "var(--bg-primary)",
        color: "var(--text-primary)",
        textAlign: "center",
        padding: "2rem",
      }}
    >
      <h2 style={{ fontSize: "2rem", fontWeight: 800, marginBottom: "1rem" }}>
        404 — Page Not Found
      </h2>
      <p style={{ color: "var(--text-secondary)", marginBottom: "2rem" }}>
        The requested statutory audit page or record does not exist.
      </p>
      <Link
        href="/workspace"
        style={{
          padding: "0.6rem 1.25rem",
          backgroundColor: "var(--accent-blue)",
          color: "#ffffff",
          borderRadius: "6px",
          fontWeight: 600,
          textDecoration: "none",
        }}
      >
        Return to Workspace
      </Link>
    </div>
  );
}

